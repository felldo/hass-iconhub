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
  "set-c": {
    name: "Set C",
    prefix: "set-c",
    total: 3,
    active: true,
    renderer: "iconify",
    sample_icons: [],
    sample_names: ["c"],
    downloaded: 1700000000,
  },
};

const STATUS = {
  auto_update: true,
  update_interval: 7,
  running: false,
  last_success: 1700000000,
  last_attempt: 1700000000,
  error: null,
  next_update: 4000000000,
};

async function setUp(selectResult, handlers = {}, beforeMount = () => {}) {
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
        if (handlers[msg.type]) return handlers[msg.type](msg);
        return null;
      },
      sendMessage: (msg) => messages.push(msg),
    },
  };
  w.eval(readFileSync(PANEL, "utf8"));
  beforeMount(w);
  const panel = w.document.createElement("iconhub-panel");
  panel.hass = hass;
  w.document.body.appendChild(panel);
  await sleep(100);
  const card = panel.shadowRoot.querySelector("iconhub-select-set-card");
  const download = panel.shadowRoot.querySelector("iconhub-download-card");
  return { w, panel, card, download, messages };
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

test("enabled sets show when they were downloaded", async () => {
  const { card } = await setUp(() => null);
  const rows = card.shadowRoot.querySelectorAll("ha-settings-row");
  assert.match(rows[2].textContent, /Downloaded .*2023/);
  // Not for disabled sets
  assert.doesNotMatch(rows[1].textContent, /Downloaded/);
});

test("the update status is shown", async () => {
  const { download } = await setUp(() => null, {
    "iconhub/iconify_status": () => ({ ...STATUS, error: "offline" }),
  });
  const text = download.shadowRoot.textContent;
  assert.match(text, /Last update: .*2023/);
  assert.match(text, /Next update: .*2096/);
  const alert = download.shadowRoot.querySelector('ha-alert[title="Last update failed"]');
  assert.ok(alert, "failure not shown");
  assert.match(alert.textContent, /2023.*offline/);
  assert.equal(
    download.shadowRoot.querySelector("#auto-update-switch").checked,
    true
  );
});

test("the panel works without an update status", async () => {
  // E.g. a backend without the status command: answered with null
  const { download } = await setUp(() => null);
  assert.match(download.shadowRoot.textContent, /Update Iconify Icons/);
  assert.equal(download.shadowRoot.querySelector("#auto-update-switch").disabled, true);
});

test("toggling automatic updates sends auto_update", async () => {
  const { download, messages } = await setUp(() => null, {
    "iconhub/iconify_status": () => STATUS,
    "iconhub/auto_update": (msg) => ({ ...STATUS, auto_update: msg.enabled, next_update: null }),
  });
  const sw = download.shadowRoot.querySelector("#auto-update-switch");
  sw.checked = false;
  sw.dispatchEvent(new download.ownerDocument.defaultView.Event("change"));
  await sleep(50);
  const msg = messages.find((m) => m.type === "iconhub/auto_update");
  assert.equal(
    JSON.stringify(msg),
    JSON.stringify({ type: "iconhub/auto_update", enabled: false })
  );
  assert.match(download.shadowRoot.textContent, /Automatic updates are off/);
});

test("a failed auto update toggle flips the switch back", async () => {
  const { download } = await setUp(() => null, {
    "iconhub/iconify_status": () => STATUS,
    "iconhub/auto_update": () => {
      throw { code: "not_loaded", message: "IconHub is not set up" };
    },
  });
  const sw = download.shadowRoot.querySelector("#auto-update-switch");
  sw.checked = false;
  sw.dispatchEvent(new download.ownerDocument.defaultView.Event("change"));
  await sleep(50);
  assert.equal(sw.checked, true, "switch not flipped back");
  assert.match(download.shadowRoot.textContent, /IconHub is not set up/);
});

test("changing the interval sends auto_update with the days", async () => {
  const { download, messages } = await setUp(() => null, {
    "iconhub/iconify_status": () => STATUS,
    "iconhub/auto_update": (msg) => ({ ...STATUS, update_interval: msg.interval }),
  });
  const field = download.shadowRoot.querySelector("#update-interval");
  // A native input: HA elements like ha-textfield aren't always loaded in
  // panels and then render as nothing
  assert.equal(field.tagName, "INPUT");
  assert.equal(field.value, "7");
  field.value = "3";
  field.dispatchEvent(new download.ownerDocument.defaultView.Event("change"));
  await sleep(50);
  const msg = messages.find((m) => m.type === "iconhub/auto_update");
  assert.equal(
    JSON.stringify(msg),
    JSON.stringify({ type: "iconhub/auto_update", interval: 3 })
  );
  assert.match(download.shadowRoot.textContent, /every\s+3 days/);
});

test("an invalid interval is rejected without a request", async () => {
  const { download, messages } = await setUp(() => null, {
    "iconhub/iconify_status": () => STATUS,
  });
  const field = download.shadowRoot.querySelector("#update-interval");
  for (const value of ["0", "2.5", "1000", ""]) {
    field.value = value;
    field.dispatchEvent(new download.ownerDocument.defaultView.Event("change"));
    await sleep(20);
    assert.equal(field.value, "7", `${value} not reset`);
  }
  assert.ok(!messages.some((m) => m.type === "iconhub/auto_update"));
  assert.match(download.shadowRoot.textContent, /1 to 365/);
});

test("a running update is followed until it has finished", async () => {
  let running = true;
  const { download, messages } = await setUp(() => null, {
    "iconhub/iconify_status": () => ({ ...STATUS, running }),
  }, (w) => {
    w.customElements.get("iconhub-download-card").poll_interval = 30;
  });
  assert.match(download.shadowRoot.textContent, /Update running/);
  const count = (type) => messages.filter((m) => m.type === type).length;
  const setsBefore = count("iconhub/sets");
  await sleep(100);
  assert.ok(count("iconhub/iconify_status") > 2, "status not fetched again");

  running = false;
  await sleep(100);
  assert.doesNotMatch(download.shadowRoot.textContent, /Update running/);
  assert.ok(count("iconhub/sets") > setsBefore, "sets not reloaded after the update");
  // Polling has stopped
  const polls = count("iconhub/iconify_status");
  await sleep(100);
  assert.equal(count("iconhub/iconify_status"), polls);
});

const CHECK = {
  checked: 1700000000,
  sets: {
    "set-a": {
      name: "Set A",
      local_version: "1.1",
      remote_version: "1.2",
      local_total: 10,
      remote_total: 45,
      downloaded: 1700000000,
      update_available: true,
    },
    "set-d": {
      name: "Set D",
      local_version: "2.0",
      remote_version: "2.1",
      local_total: 50,
      remote_total: 50,
      downloaded: 1700000000,
      update_available: true,
    },
    "set-c": {
      name: "Set C",
      local_version: null,
      remote_version: null,
      local_total: 3,
      remote_total: 3,
      downloaded: 1700000000,
      update_available: false,
    },
  },
};

test("the check shows which sets have a newer version", async () => {
  const { download, messages } = await setUp(() => null, {
    "iconhub/iconify_status": () => STATUS,
    "iconhub/iconify_check": () => CHECK,
  });
  const check = download.shadowRoot.querySelector("#check");
  assert.ok(check, "check result not shown");
  const text = check.textContent.replace(/\s+/g, " ");
  assert.match(text, /Updates available for 2 of 3 enabled Iconify sets/);
  // The icon count is shown even if only the version changed
  assert.match(text, /Set D \(set-d:\) 2\.0 → 2\.1 · 50 icons History/);
  assert.match(text, /1\.1 \u2192 1\.2/);
  assert.match(text, /10 \u2192 45 icons \(\+35\)/);
  assert.match(text, /Set C \(set-c:\) 3 icons · up to date/);
  const links = [...check.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  assert.ok(links.includes("https://github.com/iconify/icon-sets/commits/master/json/set-a.json"));

  // The Check button checks again
  const before = messages.filter((m) => m.type === "iconhub/iconify_check").length;
  download.shadowRoot.querySelector("#check-button").click();
  await sleep(50);
  assert.equal(messages.filter((m) => m.type === "iconhub/iconify_check").length, before + 1);
});

test("a failed check is shown", async () => {
  const { download } = await setUp(() => null, {
    "iconhub/iconify_status": () => STATUS,
    "iconhub/iconify_check": () => {
      throw { code: "download_failed", message: "offline" };
    },
  });
  assert.match(download.shadowRoot.textContent, /Could not check for updates: offline/);
});

test("the changes of the last update are listed", async () => {
  const changes = {
    "set-a": {
      name: "Set A",
      old_version: "1.1",
      new_version: "1.2",
      old_total: 10,
      new_total: 12,
      added: { count: 5, names: ["n1", "n2", "n3"] },
      changed: { count: 0, names: [] },
      removed: { count: 1, names: ["gone"] },
    },
  };
  const { download } = await setUp(() => null, {
    "iconhub/iconify_status": () => ({ ...STATUS, changes, changes_time: 1700000000 }),
  });
  const section = download.shadowRoot.querySelector("#changes");
  assert.ok(section, "changes not shown");
  const text = section.textContent.replace(/\s+/g, " ");
  assert.match(text, /Changes in the last update/);
  assert.match(text, /Set A \(set-a:\) 1\.1 \u2192 1\.2: 5 new, 1 removed/);
  assert.match(text, /New: n1, n2, n3 and 2 more/);
  assert.match(text, /Removed: gone/);
  assert.doesNotMatch(text, /Changed:/);
});

test("an update without changes says so", async () => {
  const { download } = await setUp(() => null, {
    "iconhub/iconify_status": () => ({ ...STATUS, changes: {}, changes_time: 1700000000 }),
  });
  assert.match(download.shadowRoot.querySelector("#changes").textContent, /No changes/);
});

test("enabled sets link to their history", async () => {
  const { card } = await setUp(() => null);
  const row = card.shadowRoot.querySelectorAll("ha-settings-row")[2];
  const link = [...row.querySelectorAll("a")].find((a) => a.textContent === "History");
  assert.equal(
    link?.getAttribute("href"),
    "https://github.com/iconify/icon-sets/commits/master/json/set-c.json"
  );
});

test("sample icons are sanitized", async () => {
  const { card } = await setUp(() => null);
  const sample = (extra) => ({
    renderer: null,
    viewBox: ["0", "0", "24", "24"],
    path: "M1 1",
    body: `<path d="M1 1"/>`,
    ...extra,
  });
  card.sets = {
    local: {
      ...SETS.local,
      sample_icons: [
        sample({ body: `<path d="M1 1"/><image href="x" onerror="alert(1)"/>` }),
        sample({ viewBox: ['0"><img', "src=x", 'onerror="alert(1)"><svg', 'x="'] }),
        sample({ viewBox: ["0,0,24,24"] }),
      ],
    },
  };
  await sleep(50);
  const icons = [...card.shadowRoot.querySelectorAll("iconhub-icon")];
  assert.equal(icons.length, 3);
  for (const { shadowRoot } of icons) {
    assert.equal(
      shadowRoot.querySelector("image, img, [onerror]"),
      null,
      shadowRoot.innerHTML
    );
    assert.ok(shadowRoot.querySelector("svg > path"), "icon not drawn");
  }
  const svg = icons[2].shadowRoot.querySelector("svg");
  assert.equal(svg.getAttribute("viewBox"), "0,0,24,24");
});

test("sample names cannot add CSS to the previews", async () => {
  const { card } = await setUp(() => null);
  card.sets = {
    "set-a": {
      ...SETS["set-a"],
      sample_names: ["x);background:url(https://evil.example/p);position:fixed;x:(", "a"],
    },
  };
  await sleep(50);
  const samples = card.shadowRoot.querySelector("iconhub-iconify-samples");
  await sleep(20);
  const masks = [...samples.shadowRoot.querySelectorAll(".mask")];
  assert.equal(masks.length, 2);
  for (const mask of masks) {
    const style = mask.getAttribute("style");
    // Only the two mask declarations, each with one quoted URL
    assert.doesNotMatch(style, /[;:]\s*(background|position)|evil\.example\/p/, style);
    assert.equal(style.match(/url\("https:\/\/api\.iconify\.design\/set-a\/[^"]*"\)/g)?.length, 2, style);
  }
});

test("only web links to authors are clickable", async () => {
  const { card } = await setUp(() => null);
  card.sets = {
    "set-a": { ...SETS["set-a"], author: { name: "Evil", url: "javascript:alert(1)" } },
    "set-c": { ...SETS["set-c"], author: { name: "Good", url: "https://example.com" } },
  };
  await sleep(50);
  const links = [...card.shadowRoot.querySelectorAll("a")].map((a) =>
    a.getAttribute("href")
  );
  assert.ok(!links.some((href) => /^javascript:/i.test(href)), links.join());
  assert.ok(links.includes("https://example.com"));
  assert.match(card.shadowRoot.textContent, /Evil/);
});
