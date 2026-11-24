import { iconToSVG, iconToHTML } from "@iconify/utils";
import { sanitizeSVG } from "./sanitize";

export async function hass_base_el() {
  await Promise.race([
    customElements.whenDefined("home-assistant"),
    customElements.whenDefined("hc-main"),
  ]);

  const element = customElements.get("home-assistant")
    ? "home-assistant"
    : "hc-main";

  while (!document.querySelector(element))
    await new Promise((r) => window.setTimeout(r, 100));
  return document.querySelector(element);
}

export async function hass() {
  const base: any = await hass_base_el();
  while (!base.hass) await new Promise((r) => window.setTimeout(r, 100));
  return base.hass;
}

export const loadConfigDashboard = async () => {
  await customElements.whenDefined("partial-panel-resolver");
  const ppResolver = document.createElement("partial-panel-resolver");
  const routes = (ppResolver as any)._getRoutes([
    {
      component_name: "config",
      url_path: "a",
    },
  ]);
  await routes?.routes?.a?.load?.();
  await customElements.whenDefined("ha-panel-config");
  const configRouter: any = document.createElement("ha-panel-config");
  await configRouter?.routerOptions?.routes?.dashboard?.load?.(); // Load ha-config-dashboard
  await configRouter?.routerOptions?.routes?.general?.load?.(); // Load ha-settings-row
  await configRouter?.routerOptions?.routes?.entities?.load?.(); // Load ha-data-table
  await customElements.whenDefined("ha-config-dashboard");
};

export const renderIcon = (icon) => {
  if (!icon) return null;

  let renderedIcon;
  if (icon.renderer == "iconify") {
    renderedIcon = iconToSVG(icon);
  } else {
    renderedIcon = icon;
    renderedIcon.attributes = {
      height: "1em",
      width: "1em",
      viewBox: icon.viewBox.join(" "),
    };
  }

  return {
    path: icon.path ?? "",
    secondaryPath: icon.path2 ?? "",
    viewBox: renderedIcon.viewBox,
    format: "iconhub",
    // After iconToSVG, because that puts other values of the icon into the body
    innerSVG: sanitizeSVG(renderedIcon.body),
    attributes: renderedIcon.attributes,
  };
};

export const renderIconHTML = (icon) => {
  const icn = renderIcon(icon);
  if (!icn) return "";

  // iconToHTML doesn't escape the attributes
  const viewBox = icn.attributes.viewBox.replace(/[^\d\s.,e+-]/gi, "");
  return iconToHTML(icn.innerSVG, { ...icn.attributes, viewBox });
};

// Commit history of one set in the Iconify icon-sets repository
export const historyUrl = (prefix: string) =>
  `https://github.com/iconify/icon-sets/commits/master/json/${prefix}.json`;

// Link from a downloaded set, if it is safe to click (no "javascript:")
export const webUrl = (url?: string) =>
  /^https?:\/\//i.test(url ?? "") ? url : undefined;

// Unix time (seconds) as date and time in the user's language
export const formatTime = (hass, seconds?: number | null) =>
  seconds
    ? new Date(seconds * 1000).toLocaleString(hass?.locale?.language, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "never";
