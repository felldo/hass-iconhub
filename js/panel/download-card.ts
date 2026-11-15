import { LitElement, html, css } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";
import { formatTime, historyUrl } from "../helpers";

interface ChangedNames {
  count: number;
  names: string[];
}

interface SetChanges {
  name: string;
  old_version: string | null;
  new_version: string | null;
  old_total: number | null;
  new_total: number | null;
  added: ChangedNames;
  changed: ChangedNames;
  removed: ChangedNames;
}

interface SetCheck {
  name: string;
  local_version: string | null;
  remote_version: string | null;
  local_total: number | null;
  remote_total: number | null;
  downloaded: number | null;
  update_available: boolean;
}

interface CheckResult {
  checked: number;
  sets: Record<string, SetCheck>;
}

interface UpdateStatus {
  auto_update: boolean;
  update_interval: number;
  running: boolean;
  last_success: number | null;
  last_attempt: number | null;
  error: string | null;
  next_update: number | null;
  changes: Record<string, SetChanges> | null;
  changes_time: number | null;
}

@customElement("iconhub-download-card")
export class IconHubDownloadCard extends LitElement {
  @property() hass;

  @property() download_error?: string;

  @query("#download-button") download_button;

  @state() status?: UpdateStatus | null;

  @state() auto_update_error?: string;

  @state() check?: CheckResult;

  @state() check_error?: string;

  @state() checking = false;

  // How often the status is fetched again while an update is running
  static poll_interval = 3000;

  private poll_timer?: number;

  protected firstUpdated() {
    this._load_status();
    this._check();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.clearTimeout(this.poll_timer);
    this.poll_timer = undefined;
  }

  async _load_status() {
    window.clearTimeout(this.poll_timer);
    this.poll_timer = undefined;
    const was_running = !!this.status?.running;
    try {
      this.status = await this.hass.connection.sendMessagePromise({
        type: "iconhub/iconify_status",
      });
    } catch (err) {
      this.status = null; // Shown as unknown; the rest of the card works
    }
    if (this.status?.running) {
      // E.g. an automatic update: show the result once it has finished
      if (this.isConnected)
        this.poll_timer = window.setTimeout(
          () => this._load_status(),
          IconHubDownloadCard.poll_interval
        );
    } else if (was_running) {
      // Finished: the icon sets show new download dates
      this.dispatchEvent(new Event("reload"));
      this._check();
    }
  }

  // Which enabled sets have a newer version. Only downloads the list of
  // sets (and doesn't store it), so it's done whenever the panel is opened.
  async _check() {
    if (this.checking) return;
    this.checking = true;
    this.check_error = undefined;
    try {
      this.check = await this.hass.connection.sendMessagePromise({
        type: "iconhub/iconify_check",
      });
    } catch (err) {
      this.check = undefined;
      this.check_error = err?.message ?? String(err);
    } finally {
      this.checking = false;
    }
  }

  async _set_interval(ev) {
    const field = ev.target;
    const previous = this.status?.update_interval ?? 7;
    const days = Number(field.value);
    this.auto_update_error = undefined;
    if (!Number.isInteger(days) || days < 1 || days > 365) {
      field.value = String(previous);
      this.auto_update_error = "Enter a whole number of days from 1 to 365";
      return;
    }
    if (days === previous) return;
    try {
      this.status = await this.hass.connection.sendMessagePromise({
        type: "iconhub/auto_update",
        interval: days,
      });
    } catch (err) {
      field.value = String(previous);
      this.auto_update_error = err?.message ?? String(err);
    }
  }

  async _toggle_auto_update(ev) {
    // Taken right away: event.target is reset once dispatching ends
    const toggle = ev.target;
    const enabled = toggle.checked;
    this.auto_update_error = undefined;
    try {
      this.status = await this.hass.connection.sendMessagePromise({
        type: "iconhub/auto_update",
        enabled,
      });
    } catch (err) {
      toggle.checked = !enabled; // Flip the switch back
      this.auto_update_error = err?.message ?? String(err);
    }
  }

  _render_status() {
    const status = this.status;
    if (!status) return "";
    let next = "Automatic updates are off";
    if (status.running) next = "Update running...";
    else if (status.auto_update && status.next_update != null)
      next =
        status.next_update * 1000 <= Date.now()
          ? "Next update: within the next hour"
          : `Next update: ${formatTime(this.hass, status.next_update)}`;
    return html`
      <div class="status">
        <div>Last update: ${formatTime(this.hass, status.last_success)}</div>
        <div>${next}</div>
      </div>
      ${status.error && !status.running && !this.download_error
        ? html`<ha-alert alert-type="warning" title="Last update failed">
            ${formatTime(this.hass, status.last_attempt)}: ${status.error}
          </ha-alert>`
        : ""}
    `;
  }

  _render_check() {
    if (this.check_error)
      return html`<div class="section dim">
        Could not check for updates: ${this.check_error}
      </div>`;
    if (!this.check) {
      return this.checking
        ? html`<div class="section dim">Checking for updates...</div>`
        : "";
    }
    const sets = Object.entries(this.check.sets ?? {});
    if (!sets.length) return "";
    const outdated = sets.filter(([, set]) => set.update_available).length;
    return html`
      <div class="section" id="check">
        <div class="section-header">
          ${outdated
            ? `Updates available for ${outdated} of ${sets.length} enabled Iconify sets`
            : `All ${sets.length} enabled Iconify sets are up to date`}
          <span class="dim">
            (checked ${formatTime(this.hass, this.check.checked)})
          </span>
        </div>
        ${sets.map(
          ([prefix, set]) => html`
            <div class="set-row ${set.update_available ? "outdated" : ""}">
              <span class="set-name">
                ${set.name} (<span class="prefix">${prefix}:</span>)
              </span>
              <span class="set-info">${this._check_text(set)}</span>
              <a href=${historyUrl(prefix)} target="_blank">History</a>
            </div>
          `
        )}
      </div>
    `;
  }

  _check_text(set: SetCheck) {
    if (!set.downloaded) return "not downloaded yet";
    if (!set.update_available)
      return set.local_version
        ? `${set.local_version}, up to date`
        : "up to date";
    const parts: string[] = [];
    if (set.remote_version && set.remote_version !== set.local_version)
      parts.push(`${set.local_version ?? "?"} → ${set.remote_version}`);
    if (set.remote_total !== set.local_total) {
      const diff = (set.remote_total ?? 0) - (set.local_total ?? 0);
      parts.push(
        `${set.local_total ?? "?"} → ${set.remote_total ?? "?"} icons` +
          (set.local_total != null && set.remote_total != null
            ? ` (${diff > 0 ? "+" : ""}${diff})`
            : "")
      );
    }
    return parts.join(", ") || "update available";
  }

  _render_changes() {
    const status = this.status;
    if (!status?.changes || !status.changes_time) return "";
    const changes = Object.entries(status.changes);
    return html`
      <div class="section" id="changes">
        <div class="section-header">
          Changes in the last update
          <span class="dim"
            >(${formatTime(this.hass, status.changes_time)})</span
          >
        </div>
        ${changes.length
          ? changes.map(
              ([prefix, set]) => html`
                <details>
                  <summary>
                    ${set.name} (<span class="prefix">${prefix}:</span>)
                    ${set.new_version && set.new_version !== set.old_version
                      ? `${set.old_version ?? "?"} → ${set.new_version}: `
                      : ""}${this._changes_text(set)}
                  </summary>
                  ${this._render_names("New", set.added)}
                  ${this._render_names("Changed", set.changed)}
                  ${this._render_names("Removed", set.removed)}
                  <a href=${historyUrl(prefix)} target="_blank">History</a>
                </details>
              `
            )
          : html`<div class="dim">
              No changes - the enabled sets were already up to date.
            </div>`}
      </div>
    `;
  }

  _changes_text(set: SetChanges) {
    const parts: [number | undefined, string][] = [
      [set.added?.count, "new"],
      [set.changed?.count, "changed"],
      [set.removed?.count, "removed"],
    ];
    return (
      parts
        .filter(([count]) => count)
        .map(([count, label]) => `${count} ${label}`)
        .join(", ") || "set information updated"
    );
  }

  _render_names(label: string, names?: ChangedNames) {
    if (!names?.count) return "";
    const more = names.count - names.names.length;
    return html`<div class="names">
      <b>${label}:</b> ${names.names.join(", ")}${more > 0
        ? ` and ${more} more`
        : ""}
    </div>`;
  }

  async _download_iconify() {
    this.dispatchEvent(new Event("clear"));
    this.download_button.disabled = true;
    this.download_error = undefined;
    try {
      await this.hass.connection.sendMessagePromise({
        type: "iconhub/iconify_update",
      });
    } catch (err) {
      this.download_error = err?.message ?? String(err);
    } finally {
      this.dispatchEvent(new Event("reload"));
      this.download_button.disabled = false;
      this._load_status();
      this._check();
    }
  }

  async _flush_icons() {
    await this.hass.connection.sendMessage({
      type: "iconhub/flush_icons",
    });
    this.dispatchEvent(new Event("reload"));
  }

  render() {
    return html`
      <ha-card outlined>
        <h1 class="card-header">IconHub</h1>
        <div class="card-content">
          <ha-alert alert-type="warning" title="Dangers of external SVG icons">
            SVG icons can theoretically contain javascript and listeners or link
            to external resources. <br />

            Home Assistant normally protects against this, but in order to
            enable advanced features such as duotone or color support
            <b>that protection is disabled for all IconHub icons</b>. <br />

            Iconify icons are allegedly validated and cleaned from any such
            potentially harmful elements, but be careful. <br />
            <br />

            I as the author of this Home Assistant component take no
            responsibility for the content of the icon sets.
          </ha-alert>

          <br />
          <ha-settings-row>
            <span slot="heading">Reload Local Icons</span>
            <span slot="description">
              Reload icons in the
              <tt>iconhub</tt>
              directory<br />
              (this includes Fontawesome-pro icons if available)
            </span>
            <ha-button @click=${() => this._flush_icons()}>Reload</ha-button>
          </ha-settings-row>
          <br />

          <ha-alert alert-type="info" title="About Iconify icons">
            <a href="https://iconify.design/">Iconify</a> is a collection of
            several popular icon sets. An icon set is downloaded from GitHub when
            you enable it below. Updates are published frequently. With
            automatic updates on, the enabled sets are updated regularly (every
            7 days by default) - if an icon seems to be missing, use the Update
            button to download the latest version right away.
          </ha-alert>

          <ha-settings-row>
            <span slot="heading">Update Iconify Icons</span>
            <span slot="description">
              Download the latest list of icon sets and the latest version of
              all enabled sets from
              <a href="https://github.com/iconify/icon-sets">GitHub</a>.
            </span>
            <div class="buttons">
              <ha-button
                id="check-button"
                .disabled=${this.checking}
                @click=${() => this._check()}
                >Check</ha-button
              >
              <ha-button
                id="download-button"
                @click=${() => this._download_iconify()}
                >Update</ha-button
              >
            </div>
          </ha-settings-row>
          ${this.download_error
            ? html`<ha-alert alert-type="error" title="Update failed">
                ${this.download_error}
              </ha-alert>`
            : ""}
          <ha-settings-row>
            <span slot="heading">Automatic Updates</span>
            <span slot="description">
              Update the list of icon sets and all enabled sets every
              ${this.status?.update_interval ?? 7} days.
            </span>
            <ha-switch
              id="auto-update-switch"
              .checked=${this.status?.auto_update ?? true}
              .disabled=${!this.status}
              @change=${(ev) => this._toggle_auto_update(ev)}
            ></ha-switch>
          </ha-settings-row>
          <ha-settings-row>
            <span slot="heading">Update Interval</span>
            <span slot="description">Days between automatic updates</span>
            <!-- A plain input: ha-textfield isn't always loaded in panels -->
            <label class="interval">
              <input
                id="update-interval"
                type="number"
                min="1"
                max="365"
                step="1"
                inputmode="numeric"
                .value=${String(this.status?.update_interval ?? 7)}
                .disabled=${!this.status?.auto_update}
                @change=${(ev) => this._set_interval(ev)}
              />
              days
            </label>
          </ha-settings-row>
          ${this.auto_update_error
            ? html`<ha-alert
                alert-type="error"
                title="Could not change automatic updates"
              >
                ${this.auto_update_error}
              </ha-alert>`
            : ""}
          ${this._render_status()} ${this._render_check()}
          ${this._render_changes()}
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
      .interval {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--primary-text-color);
      }
      .interval input {
        width: 5em;
        padding: 8px;
        font: inherit;
        color: var(--primary-text-color);
        background: var(--input-fill-color, var(--secondary-background-color));
        border: 1px solid var(--divider-color);
        border-bottom: 1px solid var(--input-idle-line-color, var(--secondary-text-color));
        border-radius: 4px 4px 0 0;
      }
      .interval input:focus {
        outline: none;
        border-bottom: 2px solid var(--primary-color);
      }
      .interval input:disabled {
        opacity: 0.5;
      }
      a {
        color: var(--primary-color);
        text-decoration: none;
      }
      .status {
        color: var(--secondary-text-color);
        padding: 0 16px 8px;
      }
      .buttons {
        display: flex;
        gap: 8px;
      }
      .section {
        padding: 8px 16px;
      }
      .section-header {
        font-weight: 500;
        margin-bottom: 4px;
      }
      .dim {
        color: var(--secondary-text-color);
        font-weight: normal;
      }
      .set-row {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 12px;
        padding: 2px 0;
        color: var(--secondary-text-color);
      }
      .set-row.outdated {
        color: var(--primary-text-color);
      }
      .set-name {
        flex: 1 1 200px;
      }
      .prefix {
        font-family: monospace;
      }
      details {
        padding: 2px 0;
      }
      summary {
        cursor: pointer;
      }
      .names {
        font-size: 0.9em;
        padding: 2px 0 2px 16px;
        word-break: break-word;
      }
    `;
  }
}
