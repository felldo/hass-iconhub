import createDOMPurify from "dompurify";

// Icon bodies are third party content (Iconify sets, Fontawesome, the user's
// own files) and are put into the page with innerHTML. Everything that could
// run code or load something from elsewhere is removed from them here.

const CONFIG = {
  USE_PROFILES: { svg: true, svgFilters: true },
  // Not in DOMPurify's SVG profile, but needed by thousands of Iconify icons
  // (line-md, noto, meteocons...). Made safe by the hooks below.
  ADD_TAGS: ["animate", "set", "use"],
  ADD_ATTR: ["attributeName", "calcMode", "from", "href", "to"],
  FORBID_TAGS: ["a", "feimage", "image"],
  // Would remove ids like "body" or "title", breaking references to them. The
  // icons are only used in shadow roots, where ids can't shadow anything.
  SANITIZE_DOM: false,
  RETURN_DOM_FRAGMENT: true as const,
};

// CSS that can load something: url() and src() of anything but "#id",
// image-set() (takes plain strings) and at-rules. Escapes are rejected because
// they can be used to hide all of these.
const UNSAFE_CSS =
  /\\|@(?:import|font-face|namespace)|(?:url|src)\(\s*(?!["']?#)|image-set\(/i;

const purify = createDOMPurify(window);

purify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName !== "style") return;
  // Checked before DOMPurify looks at the children. Any element inside the
  // style would be removed (<script>) or skipped (<g>) later, joining the text
  // around it into a new token: "ur<script>x</script>l(" becomes "url(". So a
  // style must consist of text only.
  if ((node as Element).firstElementChild || UNSAFE_CSS.test(node.textContent ?? ""))
    node.parentNode?.removeChild(node);
});

purify.addHook("uponSanitizeAttribute", (_node, data) => {
  const { attrName, attrValue } = data;
  if (attrName === "href" || attrName === "xlink:href") {
    // Only references within the icon
    if (!attrValue.startsWith("#")) data.keepAttr = false;
  } else if (attrName === "attributename") {
    // Animations must not replace a checked link or add an event handler
    if (/href|^\s*on/i.test(attrValue)) data.keepAttr = false;
  } else if (UNSAFE_CSS.test(attrValue)) {
    data.keepAttr = false;
  }
});

/** Content for an <svg> element, without anything harmful. */
export const sanitizeSVG = <T extends string | null | undefined>(body: T): T => {
  if (!body) return body;
  // Wrapped, because it would be parsed as HTML otherwise. Anything trying to
  // break out of the <svg> ends up outside of it and is dropped.
  const fragment = purify.sanitize(`<svg>${body}</svg>`, CONFIG);
  return (fragment.querySelector("svg")?.innerHTML ?? "") as T;
};
