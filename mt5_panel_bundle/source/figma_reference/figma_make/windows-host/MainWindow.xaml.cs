using Microsoft.Web.WebView2.Core;
using System;
using System.Runtime.InteropServices;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;

namespace ControlHubMt5Host;

public partial class MainWindow : Window
{
    private readonly DispatcherTimer _followTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    private readonly DispatcherTimer _bridgeTimer = new() { Interval = TimeSpan.FromSeconds(5) };
    private readonly HttpClient _runtimeHttp = new() { Timeout = TimeSpan.FromSeconds(3) };
    private bool _bridgeBusy;
    private string _symbol = (Environment.GetEnvironmentVariable("CONTROLHUB_SYMBOL") ?? "").Trim();
    private string _timeframe = (Environment.GetEnvironmentVariable("CONTROLHUB_TIMEFRAME") ?? "5m").Trim();
    private DateTime _lastChartContextRead = DateTime.MinValue;
    private IntPtr _mt5Window = IntPtr.Zero;
    private bool _webReady;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += OnLoaded;
        Closed += (_, _) => { _followTimer.Stop(); _bridgeTimer.Stop(); _runtimeHttp.Dispose(); };
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        try
        {
            await PanelView.EnsureCoreWebView2Async();
            PanelView.CoreWebView2.Settings.AreDevToolsEnabled = false;
            PanelView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            PanelView.CoreWebView2.Settings.IsStatusBarEnabled = false;
            PanelView.CoreWebView2.NavigationCompleted += async (_, args) =>
            {
                _webReady = args.IsSuccess;
                if (!args.IsSuccess) Title = "Control Hub — painel indisponível";
                else await InstallRuntimeDomBridgeAsync();
            };
            PanelView.Source = new Uri("http://127.0.0.1:4173/");
            _followTimer.Tick += (_, _) => FollowMt5Window();
            _followTimer.Start();
            _bridgeTimer.Tick += async (_, _) => await RefreshRuntimeBridgeAsync();
            _bridgeTimer.Start();
            await RefreshRuntimeBridgeAsync();
        }
        catch (Exception ex)
        {
            MessageBox.Show("Não foi possível abrir o painel. Inicie a prévia local do projeto Figma na porta 4173 e verifique o WebView2 Runtime.\n\nDetalhe: " + ex.Message, "Control Hub — integração", MessageBoxButton.OK, MessageBoxImage.Warning);
            Close();
        }
    }



    private async System.Threading.Tasks.Task InstallRuntimeDomBridgeAsync()
    {
        const string script = @"window.__controlHubRuntimeUpdate = function(raw) {
          try {
            const data = JSON.parse(raw);
            const state = document.querySelector('.system-state strong');
            if (state) state.textContent = data.state || 'Indisponível';
            const host = document.querySelector('.signals');
            if (!host) return;
            const s = data.signal || {};
            host.replaceChildren();
            if (!s.available) {
              const span = document.createElement('span'); span.className = 'availability'; span.textContent = s.label || 'Indisponível'; host.appendChild(span); return;
            }
            const row = document.createElement('div'); row.className = 'signal signal--' + (['up','down','wait'].includes(s.direction) ? s.direction : 'wait');
            const arrow = document.createElement('span'); arrow.className = 'signal__arrow'; arrow.setAttribute('aria-hidden','true'); arrow.textContent = s.direction === 'up' ? '↑' : (s.direction === 'down' ? '↓' : '●');
            const label = document.createElement('span'); label.textContent = s.label || 'AGUARDAR'; row.append(arrow,label);
            if (s.direction !== 'wait' && Number.isFinite(s.score)) { const score = document.createElement('strong'); score.textContent = s.score + '%'; row.appendChild(score); }
            host.appendChild(row);
          } catch (_) {}
        };";
        await PanelView.ExecuteScriptAsync(script);
    }

    // Ponte externa: consulta o runtime local e atualiza apenas os valores exibidos no DOM.
    // Nenhum arquivo do painel Figma e editado; nenhuma rota envia ordens.
    private async System.Threading.Tasks.Task RefreshRuntimeBridgeAsync()
    {
        if (_bridgeBusy || !_webReady || PanelView.CoreWebView2 is null) return;
        _bridgeBusy = true;
        ReadActiveChartContext();
        var state = "Indisponível";
        object signal = new { available = false, label = "Indisponível", direction = "wait", score = (int?)null };
        try
        {
            using var healthResponse = await _runtimeHttp.GetAsync("http://127.0.0.1:8000/api/health");
            if (healthResponse.IsSuccessStatusCode)
            {
                using var healthJson = JsonDocument.Parse(await healthResponse.Content.ReadAsStringAsync());
                if (healthJson.RootElement.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True)
                {
                    state = "Sistema online";
                    if (!string.IsNullOrWhiteSpace(_symbol))
                    {
                        var requestBody = JsonSerializer.Serialize(new { symbol = _symbol, timeframe = string.IsNullOrWhiteSpace(_timeframe) ? "5m" : _timeframe, limit = 100 });
                        using var content = new StringContent(requestBody, Encoding.UTF8, "application/json");
                        using var analysisResponse = await _runtimeHttp.PostAsync("http://127.0.0.1:8000/api/runtime/analysis", content);
                        if (analysisResponse.IsSuccessStatusCode)
                        {
                            using var analysisJson = JsonDocument.Parse(await analysisResponse.Content.ReadAsStringAsync());
                            var root = analysisJson.RootElement;
                            var label = ReadString(root, "signal") ?? ReadNestedString(root, "analysis", "signal") ?? "AGUARDAR";
                            var score = ReadInt(root, "score") ?? ReadNestedInt(root, "analysis", "score");
                            var normalized = label.ToUpperInvariant();
                            var direction = normalized.Contains("COMPRAR") || normalized.Contains("BUY") ? "up" :
                                            normalized.Contains("VENDER") || normalized.Contains("SELL") ? "down" : "wait";
                            signal = new { available = true, label = direction == "wait" ? "AGUARDAR" : (direction == "up" ? "COMPRAR" : "VENDER"), direction, score };
                        }
                    }
                }
            }
        }
        catch { state = "Indisponível"; }

        try
        {
            var payload = JsonSerializer.Serialize(new { state, signal });
            var argument = JsonSerializer.Serialize(payload);
            await PanelView.ExecuteScriptAsync($"window.__controlHubRuntimeUpdate && window.__controlHubRuntimeUpdate({argument});");
        }
        catch { /* WebView pode estar navegando; a próxima leitura tenta novamente. */ }
        finally { _bridgeBusy = false; }
    }

    // Leitura somente de um arquivo escrito pelo EA auxiliar no MT5.
    // O EA nao negocia: apenas publica simbolo e periodo do grafico onde esta anexado.
    private void ReadActiveChartContext()
    {
        if ((DateTime.UtcNow - _lastChartContextRead).TotalSeconds < 2) return;
        _lastChartContextRead = DateTime.UtcNow;
        try
        {
            var commonFiles = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "MetaQuotes", "Terminal", "Common", "Files", "ControlHub", "active_chart.json");
            if (!File.Exists(commonFiles)) return;
            using var chart = JsonDocument.Parse(File.ReadAllText(commonFiles));
            var root = chart.RootElement;
            var symbol = ReadString(root, "symbol");
            var timeframe = ReadString(root, "timeframe");
            if (!string.IsNullOrWhiteSpace(symbol)) _symbol = symbol.Trim();
            if (!string.IsNullOrWhiteSpace(timeframe)) _timeframe = timeframe.Trim();
        }
        catch { /* Arquivo ausente/incompleto: manter configuracao manual sem inventar ativo. */ }
    }

    private static string? ReadString(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    private static int? ReadInt(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) ? number : null;

    private static string? ReadNestedString(JsonElement root, string parent, string name) =>
        root.TryGetProperty(parent, out var nested) ? ReadString(nested, name) : null;

    private static int? ReadNestedInt(JsonElement root, string parent, string name) =>
        root.TryGetProperty(parent, out var nested) ? ReadInt(nested, name) : null;

    private void FollowMt5Window()
    {
        if (!TryFindMt5Window(out var target) || !GetWindowRect(target, out var rect) || IsIconic(target))
        {
            if (IsVisible) Hide();
            _mt5Window = IntPtr.Zero;
            return;
        }

        _mt5Window = target;
        if (!IsVisible) Show();

        // Overlay separado alinhado ao canto direito da janela principal do MT5.
        // Isso não injeta código no terminal nem altera o gráfico/EA.
        const int margin = 12;
        const int width = 420;
        int mt5Width = rect.Right - rect.Left;
        int mt5Height = rect.Bottom - rect.Top;
        int overlayWidth = Math.Min(width, Math.Max(320, mt5Width / 3));
        int overlayHeight = Math.Min(760, Math.Max(420, mt5Height - 80));
        double dpi = 1.0;
        var source = PresentationSource.FromVisual(this);
        if (source?.CompositionTarget is not null)
            dpi = source.CompositionTarget.TransformFromDevice.M11;
        Left = (rect.Right - overlayWidth - margin) * dpi;
        Top = (rect.Top + 50) * dpi;
        Width = overlayWidth * dpi;
        Height = overlayHeight * dpi;
        Topmost = true;
    }

    private static bool TryFindMt5Window(out IntPtr hwnd)
    {
        // C# nao permite capturar um parametro out dentro da callback do EnumWindows.
        // Guardamos o resultado numa variavel local e copiamos para hwnd ao final.
        IntPtr found = IntPtr.Zero;
        EnumWindows((candidate, _) =>
        {
            if (!IsWindowVisible(candidate) || IsIconic(candidate)) return true;
            var title = new System.Text.StringBuilder(512);
            GetWindowText(candidate, title, title.Capacity);
            string text = title.ToString();
            if (text.Contains("MetaTrader 5", StringComparison.OrdinalIgnoreCase) ||
                text.Contains(" - MetaTrader", StringComparison.OrdinalIgnoreCase))
            {
                found = candidate;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        hwnd = found;
        return hwnd != IntPtr.Zero;
    }

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int maxCount);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [StructLayout(LayoutKind.Sequential)] private struct RECT { public int Left, Top, Right, Bottom; }
}
