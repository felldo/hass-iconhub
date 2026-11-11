# IconHub

Use your own SVG icons, Iconify icon sets, Fontawesome Pro and SVG webfonts in Home Assistant.

![example image](https://github.com/user-attachments/assets/de32cf37-4564-420e-b6c8-917cc97aa108)

## Installation

- Install IconHub through HACS [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=felldo&repository=hass-iconhub)
- Restart Home Assistant
- Click this [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=iconhub)
  - Alternatively, go to your integrations configuration, click "Add Integration" and find "IconHub"

## Usage

- Go to your integrations configuration, click "IconHub" and then "CONFIGURE".

![configuration](https://github.com/user-attachments/assets/3e88a032-0fb1-4975-95e6-07a809cd2239)

- Here, in the Configuration Panel, you can pick which icon sets you want to use.
  Iconify icon sets are downloaded automatically when you enable them.

![select sets](https://github.com/user-attachments/assets/84c3289c-ec4b-40c8-b54d-be4f2f1dd89d)

- After enabling icon sets and refreshing your browser (F5) you will be able to find your icons in the icon picker.

![icon picker](https://github.com/user-attachments/assets/fb17667e-8161-48a8-adc9-78893961dd05)

## Icon sets

### Your own icons

To use your own icons, place their .svg files in `<config>/iconhub` (the directory should have been created by IconHub automatically).
You can also place icons in subdirectories.

If you add new icons, you need to push the RELOAD button before they can be used.

Make sure the "Local" collection is enabled, and they will then be available using the `local:` prefix.

> **Note about safety:**
>
> SVG files may contain SVG and Javascript and shall be considered unsafe.
> Home Assistant normally protects you from harmful code in SVG icons, but in order to make e.g. full color or animated icons work this protection has been removed by IconHub.
>
> Only use icons you trust (and preferably have inspected the code for). The author of IconHub takes no responsibility for the contents of any icon set - not even those included in Iconify.

> **Note about colors:**
>
> SVG files can contain color information.
> Some SVGs are meant to be used as icons, and will have no color or the magic `currentcolor` value. Those will follow the color of your entities (e.g. turning yellow when an entity is switched on or adjusting to a light color).
> Some SVGs are _not_ meant to be used as icons, they can include elements of one or more colors.
>
> If you want to use a colorized file as a color changing icon, you may need to modify the file yourself. This will require a little bit of CSS knowledge.
>
> - First: Make a backup of your svg file.
> - Open the .svg file in a text editor.
> - Look for anything that looks like `fill: #123456;` or `stroke: red;` or something like that.
>   The easiest way would be to change those to `fill: currentcolor;` or `stroke: currentcolor;` (make sure to keep the semicolon `;`).
> - Also look for anything like `stroke="blue"`. Any instances of those can be removed.
> - You probably don't want to change anything that says `fill: none;` or `fill="none"`, though. Experiment.
> - Make sure to go into the configuration and push the RELOAD button after making your changes.

### Iconify

[Iconify](https://iconify.design/) is a framework for several popular icon sets.

When you enable an Iconify icon set, IconHub downloads just that set from the [Iconify icon-sets repository](https://github.com/iconify/icon-sets) and stores it in `<config>/iconhub/iconify/`. The previews in the configuration panel are loaded by your browser from the Iconify API.

The icon sets are updated frequently. Use the UPDATE button in the IconHub configuration panel to download the latest version of all enabled sets.

### Fontawesome Pro icons

If you bought the fontawesome package, you should have received the icon set as a zip file or something.

Somewhere in this file, there's a folder named `metadata` which contains a file `icons.json`.

Copy and rename this file to `<config>/iconhub/fontawesome.json`.

Push the RELOAD button in the IconHub configuration panel.

### Webfonts

There is some support for svg webfonts like [RPG Awesome](https://github.com/nagoshiashumari/Rpg-Awesome/).

To use those, get the `<whatever>-webfont.svg` file and copy that to `<config>/iconhub/`.

Push the RELOAD button in the IconHub configuration panel.

Note that SVG webfonts has been deprecated and removed from the SVG standard. Things may or may not work.

## FAQ

### Does this replace `hass-fontawesome`?

Yes

### How do I migrate?

- Remove `hass-fontawesome`
- Install IconHub
- Open the IconHub configuration panel (see [Usage](#usage) above) and enable the icon sets you use

### How do I migrate from Custom Icons (`custom_icons`)?

IconHub is based on [Custom Icons](https://github.com/thomasloven/hass-custom_icons) by Thomas Lovén, but uses its own domain (`iconhub`), so both can't share a configuration.

- Install IconHub and add the integration (see [Installation](#installation)) **before** removing Custom Icons. IconHub then takes over the icon sets you had enabled in Custom Icons.
- Remove the Custom Icons integration (and its HACS entry) and restart Home Assistant
- Check the enabled icon sets in the IconHub configuration panel
- Icon names and prefixes stay the same (e.g. `local:my-icon`, `fapro-solid:house`, `tabler:home`), so dashboards and entities don't need to be changed

Your existing `<config>/custom_icons` directory is used automatically as long as there is no `<config>/iconhub` directory. To switch to the new location, rename `custom_icons` to `iconhub` and restart Home Assistant.

IconHub doesn't use the large `iconify-icon-sets-master.zip` archive Custom Icons downloaded. You can delete it from `<config>/custom_icons/`.

### Do I need all that `#fullcolor` nonsense from `hass-fontawesome`?

No
