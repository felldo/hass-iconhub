// Icon bodies come from third parties and end up in innerHTML. Checks that
// everything that could run code or load something is removed, and that the
// features real icons use are kept.
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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let current; // What the mocked backend answers with
let count = 0;

const dom = new JSDOM("<!doctype html><body></body>", {
  runScripts: "outside-only",
  pretendToBeVisual: true,
});
const w = dom.window;
const ha = w.document.createElement("home-assistant");
ha.hass = {
  connection: {
    sendMessagePromise: async (msg) => {
      if (msg.type === "iconhub/activesets") return ["test"];
      if (msg.type === "iconhub/icon") return current;
      return [];
    },
  },
};
w.customElements.define("home-assistant", class extends w.HTMLElement {});
w.document.body.appendChild(ha);
w.eval(readFileSync(LOADER, "utf8"));
await sleep(50);

const render = async (icon) => {
  current = icon;
  return w.customIcons.test.getIcon(`icon-${count++}`); // Never cached
};
const ICONIFY = { renderer: "iconify", left: 0, top: 0, width: 24, height: 24, rotate: 0 };
const LOCAL = { renderer: null, viewBox: ["0", "0", "24", "24"], path: "M0 0" };

// The icon as the browser sees it
const parse = (innerSVG) => {
  const g = w.document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.innerHTML = innerSVG;
  return g;
};

const HOSTILE = {
  "script element": `<script>alert(1)</script>`,
  "script with href": `<script href="data:text/javascript,alert(1)"/>`,
  "image onerror": `<image href="data:x" onerror="alert(1)"/>`,
  "external image": `<image xlink:href="https://evil.example/x.png"/>`,
  "animate onbegin": `<animate attributeName="x" dur="1s" onbegin="alert(1)"/>`,
  "animateTransform onend": `<animateTransform attributeName="transform" dur="1s" onend="alert(1)"/>`,
  "set onbegin": `<set attributeName="x" to="1" onbegin="alert(1)"/>`,
  "event handler on a shape": `<path d="M0 0" OnClick="alert(1)"/>`,
  foreignObject: `<foreignObject><img src="x" onerror="alert(1)"/></foreignObject>`,
  "iframe in foreignObject": `<foreignObject><iframe src="javascript:alert(1)"></iframe></foreignObject>`,
  iframe: `<iframe src="javascript:alert(1)"></iframe>`,
  "breaking out of the svg": `</svg><img src="x" onerror="alert(1)">`,
  "breaking out of the g": `</g></svg></g><img src="x" onerror="alert(1)">`,
  "script in a nested svg": `<svg onload="alert(1)"><script>alert(1)</script></svg>`,
  "javascript link": `<a href="javascript:alert(1)"><path d="M0 0"/></a>`,
  "javascript xlink": `<a xlink:href="java&#x09;script:alert(1)"><path d="M0 0"/></a>`,
  "set turning a link into javascript": `<a id="l"><set attributeName="href" to="javascript:alert(1)"/></a>`,
  "animated xlink:href": `<animate attributeName="xlink:href" values="javascript:alert(1)"/>`,
  "animated event handler": `<set attributeName="onmouseover" to="alert(1)"/>`,
  "external use": `<use href="https://evil.example/x.svg#a"/>`,
  "data use": `<use xlink:href="data:image/svg+xml,evil.example#a"/>`,
  "relative use": `<use href="/local/evil.example.svg#a"/>`,
  feImage: `<filter><feImage href="https://evil.example/x.png"/></filter>`,
  "import in style": `<style>@import "https://evil.example/x.css";</style>`,
  "url in style": `<style>path{background:url(https://evil.example/x)}</style>`,
  "protocol-relative url in style": `<style>path{fill:url( '//evil.example/x')}</style>`,
  "escaped url in style": `<style>path{fill:u\\72l(https://evil.example/x)}</style>`,
  "image-set in style": `<style>path{background:image-set("https://evil.example/x" 1x)}</style>`,
  // The removed <script> would join the text around it into a new token
  "import split by a script in style": `<style>@imp<script>x</script>ort "https://evil.example/x.css";</style>`,
  "url split by a script in style": `<style>path{fill:ur<script>x</script>l(https://evil.example/x)}</style>`,
  // Browsers build the style sheet from the text children only
  "url split by an element in style": `<style>:host{background:ur<g>x</g>l(https://evil.example/x)}</style>`,
  "url in a style attribute": `<path style="fill:url(https://evil.example/x)"/>`,
  "escaped url in a style attribute": `<path style="fill:\\75rl(https://evil.example/x)"/>`,
  "url in a presentation attribute": `<path filter="url(https://evil.example/x#a)"/>`,
  "url in an animation": `<set attributeName="filter" to="url(https://evil.example/x#a)"/>`,
  "mutation through style": `<style><a title="</style><img src=x onerror=alert(1)>"></a></style>`,
  "mutation through title": `<title><style></title><img src=x onerror=alert(1)></style></title>`,
  "mutation through math": `<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>`,
  "mutation through cdata": `<![CDATA[><img src=x onerror=alert(1)>]]>`,
};

const FORBIDDEN =
  "script, image, img, iframe, foreignObject, foreignobject, a, feImage, embed, object, math";

const assertSafe = (innerSVG) => {
  const g = parse(innerSVG);
  assert.equal(g.querySelector(FORBIDDEN), null, innerSVG);
  for (const el of [g, ...g.querySelectorAll("*")]) {
    assert.equal(el.namespaceURI, "http://www.w3.org/2000/svg", innerSVG);
    for (const { name, value } of el.attributes) {
      assert.doesNotMatch(name, /^on/i, innerSVG);
      assert.doesNotMatch(value, /javascript:|evil\.example/i, innerSVG);
      if (/href$/i.test(name)) assert.match(value, /^#/, innerSVG);
      if (/^attributename$/i.test(name))
        assert.doesNotMatch(value, /href|^on/i, innerSVG);
    }
    if (el.localName === "style") {
      assert.doesNotMatch(el.textContent, /evil\.example|@import/i, innerSVG);
      assert.equal(el.firstElementChild, null, innerSVG);
    }
  }
};

for (const [name, body] of Object.entries(HOSTILE)) {
  for (const [kind, icon] of Object.entries({ iconify: ICONIFY, local: LOCAL })) {
    test(`removed from ${kind} icons: ${name}`, async () => {
      const { innerSVG } = await render({ ...icon, body: `<path d="M1 1"/>${body}` });
      assertSafe(innerSVG);
      assert.match(innerSVG, /M1 1/, "the rest of the icon is gone");
    });
  }
}

test("removed from iconify icons: markup in the transformed size", async () => {
  // iconToSVG puts these values into the body
  const { innerSVG } = await render({
    ...ICONIFY,
    hFlip: true,
    width: `"><image href="x" onerror="alert(1)"/><g x="`,
    body: `<path d="M1 1"/>`,
  });
  assertSafe(innerSVG);
});

// Everything these contain is used by icons in the Iconify sets
const HARMLESS = {
  "animate and set (line-md)": `<path fill="none" stroke="currentColor" stroke-dasharray="20" stroke-dashoffset="20" d="M3 3h18"><animate fill="freeze" attributeName="stroke-dashoffset" begin="0.2s;b.end" dur="0.4s" values="20;0" id="a"></animate><set fill="freeze" attributeName="opacity" begin="a.end" to="1"></set></path>`,
  "animateTransform (svg-spinners)": `<path d="M1 1"><animateTransform attributeName="transform" dur="0.75s" repeatCount="indefinite" type="rotate" values="0 12 12;360 12 12"></animateTransform></path>`,
  animateMotion: `<circle r="1"><animateMotion calcMode="spline" dur="1s" keySplines=".4 0 .2 1" keyTimes="0;1" path="M0 0L1 1" repeatCount="indefinite"></animateMotion></circle>`,
  "use and symbol (noto, meteocons)": `<defs><path id="p" d="M1 1"></path><symbol id="s" viewBox="0 0 2 2"><path d="M1 1"></path></symbol></defs><use href="#p" fill="red"></use><use xlink:href="#s" width="2" height="2"></use>`,
  "gradients and filters (fluent-emoji)": `<g filter="url(#f)"><path fill="url(#g)" d="M1 1"></path></g><defs><radialGradient id="g" cx="0" cy="0" r="1" gradientTransform="rotate(9)" gradientUnits="userSpaceOnUse"><stop offset=".5" stop-color="#fff" stop-opacity="0"></stop></radialGradient><filter id="f" width="1" height="1" x="0" y="0" color-interpolation-filters="sRGB" filterUnits="userSpaceOnUse"><feFlood flood-opacity="0" result="b"></feFlood><feBlend in="SourceGraphic" in2="b" result="s"></feBlend><feColorMatrix in="s" values="0 0 0 0 0" result="h"></feColorMatrix><feOffset dx="1" dy="-1"></feOffset><feGaussianBlur stdDeviation=".5"></feGaussianBlur><feComposite in2="h" k2="-1" k3="1" operator="arithmetic"></feComposite></filter></defs>`,
  "masks, clip paths and quoted references": `<defs><mask id="m" style="mask-type:luminance"><path fill="#fff" d="M1 1"></path></mask><clipPath id="c"><rect width="1" height="1" rx="1"></rect></clipPath></defs><g mask="url(#m)" clip-path="url(&quot;#c&quot;)"><path style="mix-blend-mode:multiply;fill:url('#x')" d="M1 1"></path></g>`,
  "ids named like document properties": `<defs><path id="body" d="M1 1"></path></defs><use href="#body"></use>`,
  "style (Fontawesome duotone)": `<defs><style>.fa-secondary{opacity:.4}</style></defs><path class="fa-secondary" d="M1 1"></path>`,
  "nested svg (Fontawesome)": `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path fill="currentColor" d="M1 1"></path></svg>`,
};

for (const [name, body] of Object.entries(HARMLESS)) {
  for (const [kind, icon] of Object.entries({ iconify: ICONIFY, local: LOCAL })) {
    test(`kept in ${kind} icons: ${name}`, async () => {
      const { innerSVG } = await render({ ...icon, body });
      assert.ok(
        parse(innerSVG).isEqualNode(parse(body)),
        `expected ${parse(body).innerHTML}\n     got ${innerSVG}`
      );
    });
  }
}

test("an icon without a body stays without one", async () => {
  const { innerSVG } = await render({ ...LOCAL, body: undefined });
  assert.ok(!innerSVG);
});
