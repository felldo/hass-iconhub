import { svg } from "lit";
import { hass, renderIcon } from "../helpers";

const icon_cache = {};
const list_cache = {};
const pending = {};
(window as any).icon_cache = icon_cache;

const EMPTY_ICON = { path: "", viewBox: [0, 0, 0, 0] };
const RETRIES = 3;
// home-assistant-js-websocket rejects with this code when the connection drops
const ERR_CONNECTION_LOST = 3;

const _fetchIcon = async (iconSet: string, iconName: string) => {
  // The icon is requested directly. Previously the full icon list of the set
  // was downloaded first just to check that the name exists (16k names for
  // material-symbols) before even the first icon could be shown. The backend
  // now answers unknown icons with an error, so that check is not needed.
  for (let attempt = 0; attempt < RETRIES; attempt++) {
    try {
      const conn = (await hass()).connection;
      const icon = await conn.sendMessagePromise({
        type: "iconhub/icon",
        set: iconSet,
        icon: iconName,
      });
      return renderIcon(icon) ?? EMPTY_ICON;
    } catch (err) {
      // Error from the backend (unknown icon, broken SVG...) - retrying won't help
      if (err?.code !== undefined && err.code !== ERR_CONNECTION_LOST)
        return EMPTY_ICON;
      // Connection lost (e.g. HA restart, app resumed from background) -
      // wait for the reconnect and try again
      await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
    }
  }
  return EMPTY_ICON;
};

const getIcon = (iconSet: string, iconName: string) => {
  if (iconName.includes("#")) {
    iconName = iconName.split("#")[0];
  }
  const cached = icon_cache[iconSet]?.[iconName];
  if (cached) return Promise.resolve(cached);

  // Icons used to be fetched through a serial queue: each icon waited for
  // every icon requested before it (very slow in the icon picker or on slow
  // devices), and if a single request failed the queue worker crashed and no
  // more custom icons loaded until the page was reloaded.
  // Now requests run in parallel, never reject, and elements asking for the
  // same icon share one request. Failed icons are not cached, so they are
  // retried the next time they are requested.
  const key = `${iconSet}:${iconName}`;
  if (!pending[key]) {
    pending[key] = _fetchIcon(iconSet, iconName).then((icon) => {
      if (icon !== EMPTY_ICON) icon_cache[iconSet][iconName] = icon;
      delete pending[key];
      return icon;
    });
  }
  return pending[key];
};

const _preload_cache = async (iconSet: string) => {
  const conn = (await hass()).connection;
  const icons = await conn.sendMessagePromise({
    type: "iconhub/icon_cache",
    set: iconSet,
  });

  for (const icon of icons) {
    if (!icon) continue; // Older versions could cache null for missing icons
    icon_cache[iconSet][icon.icon] = renderIcon(icon);
  }
};

const getIconList = (iconSet: string) => {
  if (!list_cache[iconSet]) {
    list_cache[iconSet] = hass()
      .then((h) =>
        h.connection.sendMessagePromise({
          type: "iconhub/list",
          set: iconSet,
        })
      )
      .catch(() => {
        delete list_cache[iconSet];
        return [];
      });
  }
  return list_cache[iconSet];
};

// The icon sets are only known after a websocket round trip, so ha-icon
// elements can be rendered before they are registered in window.customIcons
// (typically on page load or in the companion apps). Home Assistant then marks
// the element as a legacy icon, renders nothing and never tries again; the
// _loadIcon patch below only helps elements loaded after it was installed.
// Once the sets are registered, find those elements and load them again.
const reloadEarlyIcons = (sets: string[]) => {
  const visit = (root: Document | ShadowRoot | Element) => {
    for (const el of root.querySelectorAll("*")) {
      if (el.localName === "ha-icon") {
        const icon = (el as any).icon;
        // Only the elements Home Assistant gave up on. Others are already
        // being handled by the _loadIcon patch and must not be loaded twice.
        if (
          (el as any)._legacy &&
          typeof icon === "string" &&
          sets.includes(icon.split(":")[0])
        ) {
          (el as any)._legacy = false;
          (el as any)._loadIcon?.();
        }
      }
      if (el.shadowRoot) visit(el.shadowRoot);
    }
  };
  visit(document);
};

// Prefix used in an icon name -> IconHub set it belongs to (incl. aliases)
const SET_OF_PREFIX: Record<string, string> = {};

const setup = async () => {
  const conn = (await hass()).connection;
  const sets = await conn.sendMessagePromise({
    type: "iconhub/activesets",
  });

  const wnd = window as any;

  if (!("customIcons" in wnd)) {
    wnd.customIcons = {};
  }

  for (const prefix of sets) {
    icon_cache[prefix] = {};
    SET_OF_PREFIX[prefix] = prefix;
    wnd.customIcons[prefix] = {
      getIcon: (iconName) => getIcon(prefix, iconName),
      getIconList: () => getIconList(prefix),
    };
    _preload_cache(prefix);
  }

  // Backwards compatibility with hass-fontawesome

  const add_alias = (set, alias) => {
    if (sets.includes(set)) {
      SET_OF_PREFIX[alias] = set;
      wnd.customIcons[alias] = {
        getIcon: (iconName) => getIcon(set, iconName),
        getIconList: () => [],
      };
    }
  };
  add_alias("local", "fapro");
  add_alias("fa6-regular", "far");
  add_alias("fa6-solid", "fas");
  add_alias("fa6-brands", "fab");

  customElements
    .whenDefined("ha-icon")
    .then(() => reloadEarlyIcons([...sets, "fapro", "far", "fas", "fab"]));
};

const customIconRegistered = setup().catch(() => console.error("Couldn't add custom icons to frontend"));

interface Icon {
  path: string;
  secondaryPath: string;
  viewBox: string;
}
// Extended interface for IconHub
interface CustomIcon extends Icon {
  format: "iconhub";
  innerSVG: string;
}

// Fullcolor support patch of ha-icon
//
// Home Assistant only draws single-color paths for custom icons. Full-color
// icons are drawn by adding a <g class="iconhubLayer"> layer with the icon's
// SVG inside the <svg> rendered by ha-svg-icon.
//
// Which SVG an ha-icon needs is looked up from its `icon` name in our icon
// cache - not passed through ha-icon's private _setCustomPath. Other icon
// integrations (e.g. ones with their own "fullcolor" support) replace
// _setCustomPath without calling the previous version, which made IconHub's
// full-color icons stay blank. The layer is synced after every render of the
// ha-icon and restored if something else removes it, so it no longer matters
// which integration patched ha-icon last or in which order things happen.

const SVG_NS = "http://www.w3.org/2000/svg";

// Hides the single-color path(s) while the full-color layer draws the icon
const HIDE_PATHS = "<style>svg > g:first-of-type > path { display: none; }</style>";

const wantedSVG = (haIcon): string | undefined => {
  const icon = haIcon.icon;
  if (typeof icon !== "string" || !icon.includes(":")) return undefined;
  const [prefix, rawName] = icon.split(":", 2);
  const set = SET_OF_PREFIX[prefix];
  if (!set || !rawName) return undefined;
  const cached: CustomIcon | undefined = icon_cache[set]?.[rawName.split("#")[0]];
  if (cached?.format !== "iconhub" || !cached.innerSVG) return undefined;
  return cached.innerSVG;
};

const syncCustomLayer = async (haIcon) => {
  const svgIcon = haIcon.shadowRoot?.querySelector("ha-svg-icon");
  if (!svgIcon) return; // Legacy icon or not rendered yet
  await svgIcon.updateComplete;
  const root = svgIcon.shadowRoot?.querySelector("svg");
  if (!root) return;

  // Restore the layer if another integration's patch clears the <svg>
  if (!root._iconhubObserver) {
    root._iconhubObserver = new MutationObserver(() => syncCustomLayer(haIcon));
    root._iconhubObserver.observe(root, { childList: true });
  }

  const wanted = wantedSVG(haIcon);
  let layer = root.querySelector(":scope > .iconhubLayer");
  if (!wanted) {
    layer?.remove();
    return;
  }
  if (!layer) {
    layer = document.createElementNS(SVG_NS, "g");
    layer.setAttribute("class", "iconhubLayer");
    root.appendChild(layer);
  }
  if (layer._iconhubSVG !== wanted) {
    layer.innerHTML = HIDE_PATHS + wanted;
    layer._iconhubSVG = wanted;
  }
};

customElements.whenDefined("ha-icon").then(() => {
  const HaIcon = customElements.get("ha-icon");

  // Only used when no other integration replaced it later. The layer doesn't
  // depend on it, this just adds the layer as early as possible.
  const o_setCustomPath = HaIcon.prototype._setCustomPath;
  HaIcon.prototype._setCustomPath = async function (promise, requestedIcon) {
    await o_setCustomPath?.call(this, promise, requestedIcon);
    await promise;
    if (requestedIcon !== this.icon) return;
    await this.updateComplete;
    syncCustomLayer(this);
  };

  const o_loadIcon = HaIcon.prototype._loadIcon;
  HaIcon.prototype._loadIcon = async function () {
    // Icons rendered before the icon sets are registered would otherwise be
    // treated as unknown (legacy) icons
    await customIconRegistered;
    await o_loadIcon?.call(this);
    syncCustomLayer(this);
  };

  // Re-apply the layer after every render. This also covers the icon arriving
  // (path/viewBox change), the icon name changing and ha-svg-icon being
  // replaced, e.g. when an icon rendered as legacy is loaded again.
  const o_updated = HaIcon.prototype.updated;
  HaIcon.prototype.updated = function (changedProps) {
    o_updated?.call(this, changedProps);
    syncCustomLayer(this);
  };
});
