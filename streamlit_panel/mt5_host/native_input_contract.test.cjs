'use strict';

const fs = require('node:fs');
const assert = require('node:assert/strict');

const workflow = fs.readFileSync('.github/workflows/verify-original-streamlit-panel.yml', 'utf8');

const requiredInputContract = [
  'COREWEBVIEW2_MOUSE_EVENT_KIND_MOVE',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_DOWN',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_LEFT_BUTTON_UP',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_DOWN',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_RIGHT_BUTTON_UP',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_DOWN',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_MIDDLE_BUTTON_UP',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_WHEEL',
  'COREWEBVIEW2_MOUSE_EVENT_KIND_HORIZONTAL_WHEEL',
  'ScreenToClient(m_appWindow->GetMainWindow(), &point)',
  'GET_WHEEL_DELTA_WPARAM(wParam)',
  'if (point.x < 0 || point.x >= right || point.y < top || point.y >= height) return;',
];

for (const token of requiredInputContract) {
  assert.ok(workflow.includes(token), `Missing native input contract: ${token}`);
}

console.log('Native WebView2 mouse mapping and wheel-coordinate contract: OK');
