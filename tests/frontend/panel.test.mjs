// Smoke test of the configuration panel bundle (panel.js) in jsdom.
// Home Assistant's own elements (ha-card, ha-switch, ...) are not defined
// here and render as unknown elements, which is enough to check that the
// panel renders, lists the icon sets and handles toggling.
//
// Run after `npm run build`: npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const PANEL = fileURLToPath(
  new URL("../../custom_components/iconhub/panel.js", import.meta.url)
);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const SETS = {
  local: { name: "Local", prefix: "local", total: 1, active: true, sample_icons: [] },
  "set-a": {
    name: "Set A",
    prefix: "set-a",
    total: 10,
    active: false,
    renderer: "iconify",
    sample_icons: [],
    sample_names: ["a", "b"],
    author: { name: "Someone", url: "https://example.com" },
  },
};

async function setUp(selectResult) {
  const dom = new JSDOM("<!doctype html><body></body>", {
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const w = dom.window;
  // Not implemented by jsdom
  w.IntersectionObserver = class {
    constructor(cb) { this.cb = cb; }
    observe(el) { this.cb([{ isIntersecting: true, target: el }]); }
    disconnect() {}
  };
  const messages = [];
  const hass = {
    connection: {
      sendMessagePromise: async (msg) => {
        messages.push(msg);
        if (msg.type === "iconhub/sets") return structuredClone(SETS);
        if (msg.type === "iconhub/select") return selectResult(msg);
        return null;
      },
      sendMessage: (msg) => messages.push(msg),
    },
  };
  w.eval(readFileSync(PANEL, "utf8"));
  const panel = w.document.createElement("iconhub-panel");
  panel.hass = hass;
  w.document.body.appendChild(panel);
  await sleep(100);
  const card = panel.shadowRoot.querySelector("iconhub-select-set-card");
  return { w, panel, card, messages };
}

test("panel renders the icon sets", async () => {
  const { card, messages } = await setUp(() => null);
  assert.ok(messages.some((m) => m.type === "iconhub/sets"));
  assert.ok(card, "set card not rendered");
  const text = card.shadowRoot.textContent;
  assert.match(text, /Local/);
  assert.match(text, /Set A/);
  const samples = card.shadowRoot.querySelector("iconhub-iconify-samples");
  assert.ok(samples, "Iconify previews not rendered");
  await sleep(20);
  const mask = samples.shadowRoot.querySelector(".mask");
  assert.ok(mask, "preview icons not rendered");
  assert.match(mask.getAttribute("style"), /api\.iconify\.design\/set-a\/a\.svg/);
});

test("toggling a set sends select", async () => {
  const { card, messages } = await setUp(() => null);
  const switches = card.shadowRoot.querySelectorAll("ha-switch");
  const sw = switches[1]; // set-a
  sw.checked = true;
  sw.dispatchEvent(new card.ownerDocument.defaultView.Event("change"));
  await sleep(50);
  const select = messages.find((m) => m.type === "iconhub/select");
  // Compared as JSON: objects from the jsdom window have another prototype
  assert.equal(
    JSON.stringify(select),
    JSON.stringify({ type: "iconhub/select", set: "set-a", active: true })
  );
});

test("a failed toggle shows the error and flips the switch back", async () => {
  const { card } = await setUp(() => {
    throw { code: "download_failed", message: "offline" };
  });
  const sw = card.shadowRoot.querySelectorAll("ha-switch")[1];
  sw.checked = true;
  sw.dispatchEvent(new card.ownerDocument.defaultView.Event("change"));
  await sleep(50);
  assert.equal(sw.checked, false, "switch not flipped back");
  assert.match(card.shadowRoot.textContent, /set-a: offline/);
});
