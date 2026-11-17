import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

// Navigation order and module labels follow the supplied Streamlit source.
// The first and last labels use the user's approved names.
const AREAS = {
  "CABINE DE COMANDO": [
    "Operação",
    "Motor de Decisão",
    "Gestão de Risco",
    "Notificações",
    "Ambiente MT5 DEMO",
    "Kill Switch",
  ],
  "ANÁLISE": [
    "Análise de Mercado",
    "Memória",
    "Estatísticas",
    "Relatórios",
  ],
  "ESTUDO": [
    "Laboratório",
    "Replay",
    "Simulador",
    "Aprendizado",
    "Descobertas",
    "Escola / Tutorial / Onboarding",
  ],
  "RESERVA FISCAL": ["Reserva Fiscal"],
  "ASSISTENTE DO ECOSSISTEMA": ["Assistente do Ecossistema"],
  "CENTRAL": [
    "Financeiro",
    "Configurações",
    "Auditoria",
    "Segurança",
    "Conexões",
    "Multi-Broker",
  ],
};

function ControlHub() {
  const [open, setOpen] = useState(false);
  const [area, setArea] = useState("CABINE DE COMANDO");
  const [module, setModule] = useState(AREAS["CABINE DE COMANDO"][0]);

  function selectArea(nextArea) {
    setArea(nextArea);
    setModule(AREAS[nextArea][0]);
  }

  const singleModuleArea =
    area === "RESERVA FISCAL" || area === "ASSISTENTE DO ECOSSISTEMA";

  return (
    <main className="chart-surface" aria-label="Controlador Trading">
      {open && (
        <section className="control-hub" aria-label="Painel Controlador-Trader">
          <header className="hub-header">
            <div className="hub-title">Controlador-Trader</div>
            <span className="demo-pill">DEMO</span>
          </header>

          <div className="open-signal-strip" aria-live="polite">
            <span className="open-signal">INDISPONÍVEL</span>
            <span className="open-score">—</span>
          </div>

          <nav className="area-navigation" aria-label="Áreas principais">
            {Object.keys(AREAS).map((name) => (
              <button
                type="button"
                key={name}
                className={area === name ? "area-tab active" : "area-tab"}
                aria-pressed={area === name}
                onClick={() => selectArea(name)}
              >
                {name}
              </button>
            ))}
          </nav>

          {!singleModuleArea && (
            <div className="module-navigation" aria-label="Módulos">
              {AREAS[area].map((name) => (
                <button
                  type="button"
                  key={name}
                  className={module === name ? "module-row selected" : "module-row"}
                  aria-pressed={module === name}
                  onClick={() => setModule(name)}
                >
                  <span>{name}</span>
                  <span className="chevron" aria-hidden="true">›</span>
                </button>
              ))}
            </div>
          )}

          <footer className="hub-footer">
            <div className="footer-row">
              <span>Estado do sistema</span>
              <strong>INDISPONÍVEL</strong>
            </div>
            <div className="footer-row">
              <span>Alavancagem</span>
              <strong>—</strong>
            </div>
            <div className="footer-row real-disabled">
              <span>REAL</span>
              <strong>DESABILITADO</strong>
            </div>
          </footer>
        </section>
      )}

      <section className="panel-toggle" aria-label={open ? "Painel aberto" : "Painel recolhido"}>
        <button
          className="closed-trigger"
          type="button"
          aria-label={open ? "Recolher painel" : "Abrir painel Controlador-Trader"}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          C
        </button>
        <div className="closed-readout" aria-live="polite">
          <div className="closed-signal">INDISPONÍVEL</div>
          <div className="closed-score">—</div>
          <div className="closed-status">INDISPONÍVEL</div>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ControlHub />
  </React.StrictMode>,
);
