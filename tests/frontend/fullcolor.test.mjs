// Full-color icons in a simulated Home Assistant frontend.
//
// ha-icon / ha-svg-icon are simplified stand-ins that behave like Home
// Assistant's (lit only updates the parts it rendered, foreign nodes stay).
// "otherPatch" reproduces another icon integration that replaces
// ha-icon._setCustomPath without calling the previous version - the cause of
// blank full-color icons in IconHub 2.0.0.
//
// Run after `npm run build`: npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const LOADER = fileURLToPath(
  new URL("../../custom_components/iconhub/loader.js", import.meta.url)
);

const HA_ENVIRONMENT = `
const NS = "http://www.w3.org/2000/svg";
class HaSvgIcon extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); this.updateComplete = Promise.resolve(); }
  set path(v) { this._p = v; this._schedule(); } get path() { return this._p; }
  set viewBox(v) { this._vb = v; this._schedule(); }
  _schedule() { this.updateComplete = Promise.resolve().then(() => this._render()); }
  _render() {
    // Like lit: only the parts it owns are updated, foreign nodes stay
    let svg = this.shadowRoot.querySelector("svg");
    if (!svg) { svg = document.createElementNS(NS, "svg"); svg.appendChild(document.createElementNS(NS, "g")); this.shadowRoot.appendChild(svg); }
    svg.setAttribute("viewBox", this._vb || "0 0 24 24");
    svg.querySelector("g").innerHTML = this._p ? '<path d="' + this._p + '"/>' : "";
  }
}
customElements.define("ha-svg-icon", HaSvgIcon);

class HaIcon extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); this.updateComplete = Promise.resolve(); }
  set icon(v) { this._icon = v; this.__path = undefined; this.__vb = undefined; this._loadIcon(); this.requestUpdate(); }
  get icon() { return this._icon; }
  // @state() emulation
  set _path(v) { this.__path = v; this.requestUpdate(); } get _path() { return this.__path; }
  set _viewBox(v) { this.__vb = v; this.requestUpdate(); } get _viewBox() { return this.__vb; }
  set _legacy(v) { this.__legacy = v; this.requestUpdate(); } get _legacy() { return this.__legacy; }
  requestUpdate() {
    if (this._pending) return; this._pending = true;
    this.updateComplete = Promise.resolve().then(() => { this._pending = false; this._render(); this.updated && this.updated(new Map()); });
  }
  _render() {
    if (this._legacy) { this.shadowRoot.innerHTML = "<iron-icon></iron-icon>"; return; }
    let s = this.shadowRoot.querySelector("ha-svg-icon");
    if (!s) { this.shadowRoot.innerHTML = ""; s = document.createElement("ha-svg-icon"); this.shadowRoot.appendChild(s); }
    s.path = this._path; s.viewBox = this._viewBox;
  }
}
HaIcon.prototype._loadIcon = async function () {
  if (!this.icon) return;
  const req = this.icon; const [p, n] = this.icon.split(":", 2);
  if (p !== "mdi") {
    const ci = (window.customIcons || {})[p];
    if (ci) { this._setCustomPath(ci.getIcon(n), req); return; }
    this._legacy = true; return;
  }
  this._legacy = false; this._path = "M-MDI";
};
HaIcon.prototype._setCustomPath = async function (promise, req) {
  const icon = await promise; if (this.icon !== req) return;
  this._path = icon.path; this._secondaryPath = icon.secondaryPath; this._viewBox = icon.viewBox;
};
customElements.define("ha-icon", HaIcon);

// Mocked HA connection
const ha = document.createElement("home-assistant");
ha.hass = { connection: { sendMessagePromise: async (m) => {
  if (m.type === "iconhub/activesets") return ["fluent-color", "local"];
  if (m.type === "iconhub/icon_cache") return [];
  if (m.type === "iconhub/list") return [];
  if (m.type === "iconhub/icon") {
    if (m.set === "fluent-color") return { renderer: "iconify", left: 0, top: 0, width: 16, height: 16, rotate: 0, vFlip: false, hFlip: false, body: '<path fill="url(#grad)" d="M' + m.icon + '"/>', prefix: m.set, icon: m.icon };
    if (m.set === "local") return { renderer: null, viewBox: ["0","0","24","24"], path: "M-LOCAL", path2: "", body: "<path d='M-LOCAL'/>", prefix: m.set, icon: m.icon };
  }
  throw { code: "not_found" };
}}};
customElements.define("home-assistant", class extends HTMLElement {});
document.body.appendChild(ha);

window.otherPatch = () => {
  // What the other integration does (from the user's console output)
  HaIcon.prototype.setAttribute = HTMLElement.prototype.setAttribute;
  HaSvgIcon.prototype.clearPaths = function () {
    // Worst case: removes everything it didn't render
    const svg = this.shadowRoot.querySelector("svg");
    if (svg) [...svg.children].slice(1).forEach((c) => c.remove());
  };
  HaSvgIcon.prototype.setPaths = function () {};
  HaIcon.prototype._setCustomPath = async function (t, e) {
    const o = await t; if (e !== this.icon) return;
    this._path = o.path; this._viewBox = o.viewBox;
    await this.UpdateComplete;
    const s = this.shadowRoot.querySelector("ha-svg-icon");
    if (s && s.setPaths) { s.clearPaths(); s.setPaths(o.paths); o.format && s.classList.add(...o.format.split("-")); }
  };
};
`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const layerOf = (el) =>
  el.shadowRoot
    .querySelector("ha-svg-icon")
    ?.shadowRoot.querySelector("svg > .iconhubLayer");

async function setUp(scenario) {
  const dom = new JSDOM("<!doctype html><body></body>", {
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const w = dom.window;
  w.eval(HA_ENVIRONMENT);

  // Rendered before the loader runs, like the sidebar on page load
  const early = w.document.createElement("ha-icon");
  w.document.body.appendChild(early);
  early.icon = "fluent-color:home-16";
  await sleep(20);

  if (scenario === "other-before") w.eval("otherPatch()");
  w.eval(readFileSync(LOADER, "utf8"));
  await sleep(50);
  if (scenario === "other-after") w.eval("otherPatch()");

  const el = w.document.createElement("ha-icon");
  w.document.body.appendChild(el);
  el.icon = "fluent-color:home-16";
  await sleep(300);
  return { w, el, early };
}

for (const scenario of ["none", "other-before", "other-after"]) {
  test(`full-color icons (${scenario})`, async (t) => {
    const { el, early } = await setUp(scenario);

    await t.test("layer is drawn", () => {
      const layer = layerOf(el);
      assert.ok(layer, "no full-color layer");
      assert.match(layer.innerHTML, /d="Mhome-16"/);
      assert.match(layer.innerHTML, /display: none/, "single-color path not hidden");
    });

    await t.test("early-rendered icon is drawn", () => {
      assert.match(layerOf(early)?.innerHTML ?? "", /Mhome-16/);
    });

    await t.test("layer is restored after removal", async () => {
      layerOf(el).remove();
      await sleep(50);
      assert.ok(layerOf(el));
    });

    await t.test("layer follows icon changes", async () => {
      el.icon = "fluent-color:home-20";
      await sleep(200);
      assert.match(layerOf(el).innerHTML, /Mhome-20/);
      assert.doesNotMatch(layerOf(el).innerHTML, /Mhome-16/);

      el.icon = "mdi:home";
      await sleep(200);
      assert.equal(layerOf(el), null, "layer left on an mdi icon");

      el.icon = "fapro:thing";
      await sleep(200);
      assert.match(layerOf(el)?.innerHTML ?? "", /M-LOCAL/, "alias prefix not drawn");
      const svg = el.shadowRoot.querySelector("ha-svg-icon").shadowRoot;
      assert.equal(svg.querySelectorAll(".iconhubLayer").length, 1);
    });
  });
}
