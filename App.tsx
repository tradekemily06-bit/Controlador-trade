import { useState } from "react";

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

function Signal({
  direction,
  label,
  percentage,
}: {
  direction: "up" | "down" | "wait";
  label: string;
  percentage?: number;
}) {
  return (
    <div className={`signal signal--${direction}`}>
      <span className="signal__arrow" aria-hidden="true">
        {direction === "up" ? "↑" : direction === "down" ? "↓" : "●"}
      </span>
      <span>{label}</span>
      {direction !== "wait" && percentage !== undefined && (
        <strong>{percentage}%</strong>
      )}
    </div>
  );
}

export default function App() {
  const [open, setOpen] = useState(false);
  const [activeArea, setActiveArea] = useState<Area>("COCKPIT");
  const [leverage, setLeverage] = useState(false);
  const [currentSignal] = useState<{
    direction: "up" | "down" | "wait";
    label: string;
    percentage?: number;
  } | null>(null);

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
          {currentSignal ? (
            <Signal {...currentSignal} />
          ) : (
            <span className="availability">Indisponível</span>
          )}
        </div>
      </aside>

      {open && (
        <section className="panel" aria-label="Painel Controlador-Trader">
          <header className="panel__header">
            <div>
              <h1>Controlador-Trader</h1>
            </div>
            <span className="mode">DEMO</span>
          </header>

          <nav className="tabs" aria-label="Módulos principais">
            {(Object.keys(areas) as Area[]).map((area) => (
              <button
                className={activeArea === area ? "tab tab--active" : "tab"}
                type="button"
                key={area}
                onClick={() => setActiveArea(area)}
              >
                {area}
              </button>
            ))}
          </nav>

          <div className="panel__body">
            <div className="module-list">
              {areas[activeArea].map((module) => (
                <button className="module" type="button" key={module}>
                  <span>{module}</span>
                  <span aria-hidden="true">›</span>
                </button>
              ))}
            </div>
          </div>

          <footer className="panel__footer">
            <div className="system-state">
              <span>Estado do sistema</span>
              <strong>Indisponível</strong>
            </div>
            <label className="leverage">
              <strong>Alavancagem</strong>
              <input
                type="checkbox"
                checked={leverage}
                onChange={(event) => setLeverage(event.target.checked)}
              />
              <span className="switch" aria-hidden="true" />
            </label>
            <button className="real-mode" type="button" disabled>
              REAL — DESABILITADO
            </button>
          </footer>
        </section>
      )}
    </main>
  );
}
