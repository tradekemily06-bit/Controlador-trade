const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "dom_bridge.js"), "utf8");
let observerCallback;
let webMessageHandler;
let posted = [];
let clickCount = 0;
let expanded = false;
let collapsedAvailable = true;
let expandedAvailable = true;
let buttonDisabled = false;
let expandedDisplay = "block";
let rafQueue = [];

const collapsedRect = {left: 16, top: 700, width: 64, height: 64, right: 80, bottom: 764};
const expandedRect = {left: 16, top: 300, width: 420, height: 460, right: 436, bottom: 760};
const toggleButton = {
  get disabled() { return buttonDisabled; },
  textContent: "C",
  getBoundingClientRect: () => collapsedRect,
  click() { clickCount += 1; expanded = !expanded; }
};
const collapsedRoot = {
  querySelector: () => toggleButton,
  querySelectorAll: () => [toggleButton]
};
const expandedRoot = {
  querySelectorAll: () => [toggleButton],
  getBoundingClientRect: () => expandedRect
};
const document = {
  readyState: "complete",
  documentElement: {clientWidth: 1280, clientHeight: 800},
  querySelector(selector) {
    if (selector === ".st-key-panel-toggle") return collapsedAvailable ? collapsedRoot : null;
    if (selector === ".st-key-control-hub-shell") return expandedAvailable && expanded ? expandedRoot : null;
    return null;
  }
};
const webview = {
  postMessage(message) { posted.push(message); },
  addEventListener(name, handler) { if (name === "message") webMessageHandler = handler; }
};
const window = {
  chrome: {webview},
  devicePixelRatio: 1.25,
  getComputedStyle: () => ({
    display: expandedDisplay,
    visibility: "visible",
    opacity: "1"
  }),
  requestAnimationFrame(callback) { rafQueue.push(callback); },
  addEventListener() {}
};
class MutationObserver {
  constructor(callback) { observerCallback = callback; }
  observe() {}
}
vm.runInNewContext(source, {window, document, MutationObserver}, {filename: "dom_bridge.js"});
const flush = () => { while (rafQueue.length) rafQueue.shift()(); };

// Initial collapsed measurement and CSS-pixel/DPR reporting.
observerCallback();
flush();
assert.equal(posted.at(-1).state, "collapsed");
assert.equal(posted.at(-1).collapsedButton.width, 64);
assert.equal(posted.at(-1).viewport.dpr, 1.25);

// Multiple DOM mutations in one frame are coalesced; unchanged layouts are not resent.
const initialMessages = posted.length;
observerCallback();
observerCallback();
assert.equal(rafQueue.length, 1);
flush();
assert.equal(posted.length, initialMessages);

// Native host asks the real Streamlit C control to expand.
webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 1);
assert.equal(expanded, true);
observerCallback();
flush();
assert.equal(posted.at(-1).state, "expanded");
assert.equal(posted.at(-1).expandedShell.width, 420);
assert.equal(posted.at(-1).x, 16);
assert.equal(posted.at(-1).y, 300);
assert.equal(posted.at(-1).width, 420);
assert.equal(posted.at(-1).height, 460);

// Cross-check the exact top-level coordinate contract consumed by native ApplyLayout.
const nativeHost = fs.readFileSync(path.join(__dirname, "bench_host.cpp"), "utf8");
for (const field of ["x", "y", "width", "height"]) {
  assert.ok(nativeHost.includes('ReadNumber(json, "' + field + '"'));
  assert.equal(typeof posted.at(-1)[field], "number");
}

// Updated viewport and DPR are reflected in the next layout message.
document.documentElement.clientWidth = 1440;
window.devicePixelRatio = 1.5;
observerCallback();
flush();
assert.equal(posted.at(-1).viewport.width, 1440);
assert.equal(posted.at(-1).viewport.dpr, 1.5);

// A hidden expanded shell is not reported as an interactive visible region.
expandedDisplay = "none";
observerCallback();
flush();
assert.equal(posted.at(-1).state, "collapsed");
assert.equal(posted.at(-1).expandedShell, null);
expandedDisplay = "block";

// Disabled Streamlit buttons must not receive a synthetic click.
buttonDisabled = true;
webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 1);
buttonDisabled = false;

// If Streamlit temporarily removes the collapsed branch during rerun, bridge fails closed.
collapsedAvailable = false;
expanded = false;
webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 1);
collapsedAvailable = true;

// Expand then collapse through the same bridge message.
webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 2);
assert.equal(expanded, true);
observerCallback();
flush();
webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 3);
assert.equal(expanded, false);

console.log("DOM bridge tests passed: state, DOM rects, DPR/resize, coalescing, hidden/disabled/missing controls and bidirectional toggle.");
