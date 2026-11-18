$ErrorActionPreference = 'Stop'

# Diagnostico somente leitura da hierarquia de janelas do MetaTrader 5.
# Nao altera janelas, processos, arquivos do MT5, EA, registro ou politicas do Windows.
$source = @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class Mt5WindowReadOnlyProbe
{
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);
    private static IntPtr _mdiClient;

    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hwnd, StringBuilder name, int max);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int max);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hwnd, ref POINT point);
    [DllImport("user32.dll", EntryPoint="GetDpiForWindow")] private static extern uint GetDpiForWindowNative(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern IntPtr GetParent(IntPtr hwnd);
    [DllImport("user32.dll", EntryPoint="SendMessageTimeoutW", SetLastError=true)] public static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW")] public static extern IntPtr GetWindowLongPtr64(IntPtr hwnd, int index);
    [DllImport("user32.dll", EntryPoint="GetWindowLongW")] public static extern IntPtr GetWindowLong32(IntPtr hwnd, int index);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X, Y; }

    public static uint GetWindowDpi(IntPtr hwnd)
    {
        try { return GetDpiForWindowNative(hwnd); }
        catch (EntryPointNotFoundException) { return 0; }
    }

    private static bool FindMdiClientCallback(IntPtr hwnd, IntPtr lParam)
    {
        var cls = new StringBuilder(128);
        GetClassName(hwnd, cls, cls.Capacity);
        if (String.Equals(cls.ToString(), "MDIClient", StringComparison.OrdinalIgnoreCase))
        {
            _mdiClient = hwnd;
            return false;
        }
        return true;
    }

    public static IntPtr FindMdiClient(IntPtr topWindow)
    {
        _mdiClient = IntPtr.Zero;
        EnumChildWindows(topWindow, FindMdiClientCallback, IntPtr.Zero);
        return _mdiClient;
    }

    public static IntPtr GetActiveMdiChild(IntPtr mdiClient, out bool timedOut)
    {
        const uint WM_MDIGETACTIVE = 0x0229;
        const uint SMTO_ABORTIFHUNG = 0x0002;
        timedOut = false;
        if (mdiClient == IntPtr.Zero) return IntPtr.Zero;
        IntPtr activeChild;
        IntPtr completed = SendMessageTimeout(mdiClient, WM_MDIGETACTIVE, IntPtr.Zero, IntPtr.Zero,
            SMTO_ABORTIFHUNG, 1000, out activeChild);
        timedOut = completed == IntPtr.Zero;
        return timedOut ? IntPtr.Zero : activeChild;
    }

    public static string WindowLine(IntPtr hwnd, string kind, int depth)
    {
        uint pid;
        uint threadId = GetWindowThreadProcessId(hwnd, out pid);
        IntPtr parent = GetParent(hwnd);
        var cls = new StringBuilder(256);
        var title = new StringBuilder(512);
        RECT r, client;
        POINT clientOrigin = new POINT { X = 0, Y = 0 };
        GetClassName(hwnd, cls, cls.Capacity);
        GetWindowText(hwnd, title, title.Capacity);
        GetWindowRect(hwnd, out r);
        bool hasClient = GetClientRect(hwnd, out client);
        bool hasClientOrigin = ClientToScreen(hwnd, ref clientOrigin);
        uint dpi = GetWindowDpi(hwnd);
        IntPtr style = IntPtr.Size == 8 ? GetWindowLongPtr64(hwnd, -16) : GetWindowLong32(hwnd, -16);
        IntPtr ex = IntPtr.Size == 8 ? GetWindowLongPtr64(hwnd, -20) : GetWindowLong32(hwnd, -20);
        return new string(' ', Math.Max(0, depth) * 2) + kind +
            " hwnd=0x" + hwnd.ToInt64().ToString("X") +
            " pid=" + pid +
            " tid=" + threadId +
            " parent=0x" + parent.ToInt64().ToString("X") +
            " visible=" + (IsWindowVisible(hwnd) ? "1" : "0") +
            " iconic=" + (IsIconic(hwnd) ? "1" : "0") +
            " rect=(" + r.Left + "," + r.Top + "," + r.Right + "," + r.Bottom + ")" +
            " client=" + (hasClient ? "(" + client.Left + "," + client.Top + "," + client.Right + "," + client.Bottom + ")" : "[unavailable]") +
            " client_screen_origin=" + (hasClientOrigin ? "(" + clientOrigin.X + "," + clientOrigin.Y + ")" : "[unavailable]") +
            " dpi=" + dpi +
            " style=0x" + style.ToInt64().ToString("X") +
            " ex=0x" + ex.ToInt64().ToString("X") +
            " class=[" + cls + "] title=[" + title + "]";
    }
}
'@

Add-Type -TypeDefinition $source -Language CSharp

$mt5 = @(Get-Process -Name terminal64, terminal -ErrorAction SilentlyContinue)
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('Diagnostico read-only MT5. Nenhuma janela ou processo foi modificado.')
$lines.Add('Data local: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$lines.Add('')

foreach ($p in $mt5) {
    $lines.Add('=== PROCESSO: ' + $p.ProcessName + ' PID=' + $p.Id + ' ===')
    $childCallback = [Mt5WindowReadOnlyProbe+EnumWindowsProc] {
        param([IntPtr]$hwnd, [IntPtr]$unused)
        $lines.Add([Mt5WindowReadOnlyProbe]::WindowLine($hwnd, 'CHILD', 1))
        return $true
    }
    $topCallback = [Mt5WindowReadOnlyProbe+EnumWindowsProc] {
        param([IntPtr]$hwnd, [IntPtr]$unused)
        $pidValue = [uint32]0
        [void][Mt5WindowReadOnlyProbe]::GetWindowThreadProcessId($hwnd, [ref]$pidValue)
        if ($pidValue -eq [uint32]$p.Id) {
            $lines.Add([Mt5WindowReadOnlyProbe]::WindowLine($hwnd, 'TOP', 0))
            $mdi = [Mt5WindowReadOnlyProbe]::FindMdiClient($hwnd)
            if ($mdi -ne [IntPtr]::Zero) {
                $lines.Add([Mt5WindowReadOnlyProbe]::WindowLine($mdi, 'MDICLIENT', 1))
                $mdiTimedOut = $false
                $activeChart = [Mt5WindowReadOnlyProbe]::GetActiveMdiChild($mdi, [ref]$mdiTimedOut)
                if ($mdiTimedOut) {
                    $lines.Add('  ACTIVE_MDI_CHILD: indisponivel (timeout da thread de interface do MT5).')
                } elseif ($activeChart -ne [IntPtr]::Zero) {
                    $lines.Add([Mt5WindowReadOnlyProbe]::WindowLine($activeChart, 'ACTIVE_MDI_CHILD', 2))
                } else {
                    $lines.Add('  ACTIVE_MDI_CHILD: nenhum filho MDI ativo foi retornado.')
                }
            } else {
                $lines.Add('  MDICLIENT: nao encontrado nesta janela de topo.')
            }
            [void][Mt5WindowReadOnlyProbe]::EnumChildWindows($hwnd, $childCallback, [IntPtr]::Zero)
        }
        return $true
    }
    [void][Mt5WindowReadOnlyProbe]::EnumWindows($topCallback, [IntPtr]::Zero)
    $lines.Add('')
}
if ($mt5.Count -eq 0) {
    $lines.Add('Nenhum processo terminal64.exe ou terminal.exe foi encontrado. Abra o MT5 e execute novamente.')
}

$path = Join-Path $env:TEMP 'ControladorTrading-MT5-window-tree-PS.txt'
[System.IO.File]::WriteAllLines($path, $lines, [System.Text.Encoding]::UTF8)
Write-Host 'Relatorio somente leitura salvo em:'
Write-Host $path
Write-Host 'Abra o arquivo e compartilhe o conteudo. Ele destaca MDIClient e ACTIVE_MDI_CHILD, alem de HWND, parent HWND, PID/TID, classes, titulos, estilos e coordenadas.'
