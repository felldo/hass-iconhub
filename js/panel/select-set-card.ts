import { LitElement, html, css } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import { renderIconHTML } from "../helpers";

@customElement("iconhub-icon")
class IconHubIcon extends LitElement {
  @property() icon;

  render() {
    return unsafeHTML(renderIconHTML(this.icon));
  }
}

// Preview of an Iconify set that may not be downloaded yet. The sample icons
// are loaded by the browser from the Iconify API - only once the row is
// scrolled into view, as there are several hundred sets.
@customElement("iconhub-iconify-samples")
class IconHubIconifySamples extends LitElement {
  @property() prefix: string;
  @property() names: string[] = [];
  @property() palette = false;
  @state() visible = false;
  @state() failed = false;

  private observer?: IntersectionObserver;

  connectedCallback() {
    super.connectedCallback();
    this.observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        this.visible = true;
        this.observer?.disconnect();
      }
    });
    this.observer.observe(this);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.observer?.disconnect();
  }

  _url(name: string) {
    return `https://api.iconify.design/${this.prefix}/${name}.svg`;
  }

  render() {
    if (!this.visible || this.failed) {
      // Offline (or not visible yet): show the names instead
      return html`<span class="names">${this.names.join(", ")}</span>`;
    }
    return this.names.map((name) =>
      this.palette
        ? // Colored icons are shown as they are
          html`<img
            src=${this._url(name)}
            title=${name}
            alt=${name}
            @error=${() => (this.failed = true)}
          />`
        : // Monochrome icons follow the theme's text color
          html`<span
            class="mask"
            title=${name}
            style="mask-image: url(${this._url(name)}); -webkit-mask-image: url(${this._url(name)})"
          ></span>`
    );
  }

  static get styles() {
    return css`
      :host {
        display: inline-flex;
        gap: 4px;
        vertical-align: top;
        min-height: 2.5em;
        align-items: center;
      }
      img,
      .mask {
        width: 2.5em;
        height: 2.5em;
      }
      .mask {
        display: inline-block;
        background-color: currentColor;
        mask-repeat: no-repeat;
        mask-position: center;
        mask-size: contain;
        -webkit-mask-repeat: no-repeat;
        -webkit-mask-position: center;
        -webkit-mask-size: contain;
      }
      .names {
        font-size: 0.9em;
        opacity: 0.7;
      }
    `;
  }
}

@customElement("iconhub-select-set-card")
export class IconHubSelectSetCard extends LitElement {
  @property() hass;
  @property() sets;
  @state() busy: Record<string, boolean> = {};
  @state() error?: string;

  async _toggle_set(prefix, ev) {
    const state = this.sets[prefix].active;
    this.busy = { ...this.busy, [prefix]: true };
    this.error = undefined;
    try {
      // Enabling an Iconify set downloads it, which can take a moment
      await this.hass.connection.sendMessagePromise({
        type: "iconhub/select",
        set: prefix,
        active: !state,
      });
      this.sets[prefix].active = !state;
    } catch (err) {
      ev.target.checked = state; // Flip the switch back
      this.error = `${prefix}: ${err?.message ?? String(err)}`;
    } finally {
      this.busy = { ...this.busy, [prefix]: false };
      this.requestUpdate();
    }
  }

  render() {
    return html`
      <ha-card outlined>
        <h1 class="card-header">Icon sets</h1>
        <div class="card-content">
          <p>Only enabled icon sets will be available.</p>
          <p>Remember to refresh your browser after enabling new icon sets.</p>
          <p>
            Iconify icon sets are downloaded when you enable them. The previews
            are loaded from the Iconify API.
          </p>
          ${this.error
            ? html`<ha-alert alert-type="error" title="Could not change icon set">
                ${this.error}
              </ha-alert>`
            : ""}

          ${Object.keys(this.sets).map((prefix) => {
            const set = this.sets[prefix];
            return html`
              <ha-settings-row>
                <span slot="heading">
                  ${set.name} (<span
                    class="prefix ${set.active ? "active" : ""}"
                    >${prefix}:</span
                  >)
                </span>
                <span slot="description">
                  <div>
                    ${set.total} icons
                    ${set.author
                      ? html`by ${set.author.name} -
                          <a href="${set.author.url}" target="_blank">
                            ${set.author.url}
                          </a>`
                      : ""}
                  </div>
                  ${set.sample_names?.length
                    ? html`<div class="samples">
                        <iconhub-iconify-samples
                          .prefix=${prefix}
                          .names=${set.sample_names}
                          .palette=${!!set.palette}
                        ></iconhub-iconify-samples>
                        <a
                          href="https://icon-sets.iconify.design/${prefix}/"
                          target="_blank"
                        >
                          <ha-icon .icon=${"mdi:open-in-new"}> </ha-icon>
                        </a>
                      </div>`
                    : set.sample_icons?.length
                    ? html` <div class="samples">
                        ${set.sample_icons?.map((i) => {
                          return html`<iconhub-icon
                            .icon=${i}
                          ></iconhub-icon>`;
                        })}
                        ${set.sample_icons?.[0]?.renderer == "iconify"
                          ? html`
                              <a
                                href="https://icon-sets.iconify.design/${prefix}/"
                                target="_blank"
                              >
                                <ha-icon .icon=${"mdi:open-in-new"}> </ha-icon>
                              </a>
                            `
                          : ""}
                      </div>`
                    : ""}
                </span>

                <ha-switch
                  .checked=${set.active}
                  .disabled=${!!this.busy[prefix]}
                  @change=${(ev) => this._toggle_set(prefix, ev)}
                >
                </ha-switch>
              </ha-settings-row>
            `;
          })}
        </div>
      </ha-card>
    `;
  }

  static get styles() {
    return css`
      .card-header {
        display: flex;
        justify-content: space-between;
      }
      a {
        color: var(--primary-color);
        text-decoration: none;
      }
      .prefix {
        font-family: monospace;
      }
      .prefix.active {
        color: var(--primary-color);
      }
      ha-icon-button > * {
        display: flex;
        color: var(--primary-text-color);
      }
      .samples * {
        vertical-align: bottom;
      }
      iconhub-icon {
        fill: currentColor;
        font-size: 2.5em;
        vertical-align: top;
        margin-right: 4px;
        transition: font-size 0.2s;
      }
      iconhub-icon:hover {
        color: var(--accent-color);
      }
    `;
  }
}
