import { useEffect, useState } from "react";

const areas = {
  COCKPIT: [
    "Operação",
    "Motor de Decisão",
    "Gestão de Risco",
    "Notificações",
    "MT5 DEMO / Simulação",
    "Kill Switch",
  ],
  ANÁLISE: [
    "Análise de Mercado",
    "Memória",
    "Estatísticas",
    "Relatórios",
  ],
  ESTUDO: [
    "Laboratório",
    "Replay",
    "Simulador",
    "Aprendizado",
    "Descobertas",
    "Escola / Tutorial / Onboarding",
  ],
  "MAIS / ADMIN": [
    "Configurações",
    "Auditoria",
    "Segurança",
    "Conexões",
    "Multi-Broker",
  ],
};

type Area = keyof typeof areas;
type SignalState = {
  direction: "up" | "down" | "wait";
  label: string;
  percentage?: number;
};

function Signal({ direction, label, percentage }: SignalState) {
  return (
    <div className={`signal signal--${direction}`}>
      <span className="signal__arrow" aria-hidden="true">
        {direction === "up" ? "↑" : direction === "down" ? "↓" : "●"}
      </span>
      <span>{label}</span>
      {percentage !== undefined && (
        <strong>{percentage}%</strong>
      )}
    </div>
  );
}

function signalFromPayload(payload: any): SignalState {
  const data = payload?.analysis ?? payload?.runtime?.analysis ?? payload?.runtime ?? payload;
  const rawSignal = String(data?.signal ?? "AGUARDAR").toUpperCase();
  const score = Number(data?.score);
  if (rawSignal === "COMPRAR" || rawSignal === "BUY" || rawSignal === "CALL") {
    return { direction: "up", label: "COMPRAR", percentage: Number.isFinite(score) ? score : undefined };
  }
  if (rawSignal === "VENDER" || rawSignal === "SELL" || rawSignal === "PUT") {
    return { direction: "down", label: "VENDER", percentage: Number.isFinite(score) ? score : undefined };
  }
  return { direction: "wait", label: "AGUARDAR", percentage: Number.isFinite(score) ? score : undefined };
}

export default function App() {
  const [open, setOpen] = useState(false);
  const [activeArea, setActiveArea] = useState<Area>("COCKPIT");
  const [leverage, setLeverage] = useState(false);
  const [systemState, setSystemState] = useState("Indisponível");
  const [currentSignal, setCurrentSignal] = useState<SignalState | null>(null);
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadConnectionState() {
      try {
        const [healthResponse, preferencesResponse] = await Promise.all([
          fetch("/api/health", { headers: { Accept: "application/json" } }),
          fetch("/api/preferences", { headers: { Accept: "application/json" } }),
        ]);
        if (!healthResponse.ok) throw new Error("API indisponível");
        const health = await healthResponse.json();
        const preferencesPayload = preferencesResponse.ok ? await preferencesResponse.json() : null;
        if (cancelled) return;
        setSystemState(health?.ok ? "Sistema online" : "Indisponível");
        const prefs = preferencesPayload?.preferences;
        if (prefs && typeof prefs.leverage_enabled === "boolean") setLeverage(prefs.leverage_enabled);
        setPreferencesLoaded(true);
      } catch {
        if (!cancelled) {
          setSystemState("Indisponível");
          setPreferencesLoaded(true);
        }
      }
    }
    void loadConnectionState();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    async function loadDemoAnalysis() {
      try {
        const preferencesResponse = await fetch("/api/preferences", { headers: { Accept: "application/json" } });
        if (!preferencesResponse.ok) throw new Error("Preferências indisponíveis");
        const preferencesPayload = await preferencesResponse.json();
        const prefs = preferencesPayload?.preferences ?? {};
        const response = await fetch("/api/runtime/analysis", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            symbol: String(prefs.default_symbol ?? "EURUSD"),
            timeframe: String(prefs.default_timeframe ?? "5m"),
            confirmed: false,
          }),
        });
        if (!response.ok) throw new Error("Análise DEMO indisponível");
        const payload = await response.json();
        if (!cancelled) setCurrentSignal(signalFromPayload(payload));
      } catch {
        if (!cancelled) setCurrentSignal({ direction: "wait", label: "AGUARDAR" });
      }
    }
    void loadDemoAnalysis();
    return () => { cancelled = true; };
  }, [open]);

  async function updateLeverage(enabled: boolean) {
    setLeverage(enabled);
    try {
      const response = await fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ leverage_enabled: enabled }),
      });
      if (!response.ok) throw new Error("Não foi possível salvar a preferência");
      const payload = await response.json();
      const savedValue = payload?.preferences?.leverage_enabled;
      if (typeof savedValue === "boolean") setLeverage(savedValue);
    } catch {
      setLeverage(!enabled);
    }
  }

  return (
    <main className="workspace">
      <aside className="control-anchor" aria-label="Controlador-Trader">
        <button
          className="control-trigger"
          type="button"
          aria-label={open ? "Fechar Controlador-Trader" : "Abrir Controlador-Trader"}
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          C
        </button>
        <div className="signals" aria-label="Sinais atuais">
          {currentSignal ? <Signal {...currentSignal} /> : <span className="availability">Indisponível</span>}
        </div>
      </aside>

      {open && (
        <section className="panel" aria-label="Painel Controlador-Trader">
          <header className="panel__header">
            <div><h1>Controlador-Trader</h1></div>
            <span className="mode">DEMO</span>
          </header>
          <nav className="tabs" aria-label="Módulos principais">
            {(Object.keys(areas) as Area[]).map((area) => (
              <button className={activeArea === area ? "tab tab--active" : "tab"} type="button" key={area} onClick={() => setActiveArea(area)}>
                {area}
              </button>
            ))}
          </nav>
          <div className="panel__body">
            <div className="module-list">
              {areas[activeArea].map((module) => (
                <button className="module" type="button" key={module}>
                  <span>{module}</span><span aria-hidden="true">›</span>
                </button>
              ))}
            </div>
          </div>
          <footer className="panel__footer">
            <div className="system-state"><span>Estado do sistema</span><strong>{systemState}</strong></div>
            <label className="leverage">
              <strong>Alavancagem</strong>
              <input type="checkbox" checked={leverage} disabled={!preferencesLoaded} onChange={(event) => void updateLeverage(event.target.checked)} />
              <span className="switch" aria-hidden="true" />
            </label>
            <button className="real-mode" type="button" disabled>REAL — DESABILITADO</button>
          </footer>
        </section>
      )}
    </main>
  );
}
