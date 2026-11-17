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
let rafQueue = [];

const collapsedRect = {left: 16, top: 700, width: 64, height: 64, right: 80, bottom: 764};
const expandedRect = {left: 16, top: 300, width: 420, height: 460, right: 436, bottom: 760};
const toggleButton = {
  disabled: false,
  textContent: "C",
  getBoundingClientRect: () => collapsedRect,
  click() { clickCount += 1; expanded = !expanded; }
};
const collapsedRoot = {querySelector: () => toggleButton, querySelectorAll: () => [toggleButton]};
const expandedRoot = {
  querySelectorAll: () => [toggleButton],
  getBoundingClientRect: () => expandedRect
};
const document = {
  readyState: "complete",
  documentElement: {clientWidth: 1280, clientHeight: 800},
  querySelector(selector) {
    if (selector === ".st-key-panel-toggle") return collapsedRoot;
    if (selector === ".st-key-control-hub-shell") return expanded ? expandedRoot : null;
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
  getComputedStyle: () => ({display: "block", visibility: "visible", opacity: "1"}),
  requestAnimationFrame(callback) { rafQueue.push(callback); },
  addEventListener() {}
};
class MutationObserver {
  constructor(callback) { observerCallback = callback; }
  observe() {}
}
vm.runInNewContext(source, {window, document, MutationObserver}, {filename: "dom_bridge.js"});
const flush = () => { while (rafQueue.length) rafQueue.shift()(); };

observerCallback();
flush();
assert.equal(posted.at(-1).state, "collapsed");
assert.equal(posted.at(-1).collapsedButton.width, 64);
assert.equal(posted.at(-1).viewport.dpr, 1.25);

webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 1);
assert.equal(expanded, true);

observerCallback();
flush();
assert.equal(posted.at(-1).state, "expanded");
assert.equal(posted.at(-1).expandedShell.width, 420);

webMessageHandler({data: {type: "controlador.toggle"}});
assert.equal(clickCount, 2);
assert.equal(expanded, false);

console.log("DOM bridge tests passed: collapsed layout, expanded layout, DPR and bidirectional toggle.");
