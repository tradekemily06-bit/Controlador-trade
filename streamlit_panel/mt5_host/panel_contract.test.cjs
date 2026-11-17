const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const appPath = path.resolve(__dirname, "..", "app.py");
const app = fs.readFileSync(appPath, "utf8");

// Guard the approved panel's integration contract without rewriting its UI.
const required = [
  'st.set_page_config(page_title="Controlador-Trader · Streamlit"',
  ".st-key-panel-toggle",
  ".st-key-control-hub-shell",
  'with st.container(key="panel-toggle")',
  'with st.container(key="control-hub-shell")',
  'st.session_state.panel_open = False',
  'st.session_state.panel_open = True',
  'st.button("C", key="open_control_hub"',
  'st.button("C", key="close_control_hub_top"',
  'st.stop()',
  'width: 64px',
  'height: 64px',
  'max-height: min(84vh, 460px)',
  'DEMO'
];
for (const token of required) {
  assert.ok(app.includes(token), `Original panel contract missing: ${token}`);
}

assert.ok(
  app.indexOf('with st.container(key="panel-toggle")') <
    app.indexOf('with st.container(key="control-hub-shell")'),
  "Collapsed C state must remain the first panel branch."
);
assert.ok(
  app.indexOf('st.button("C", key="open_control_hub"') <
    app.indexOf('st.stop()'),
  "Collapsed C must be rendered before Streamlit stops the collapsed branch."
);

console.log("Original panel contract passed: C states, selectors, dimensions and DEMO marker preserved.");
