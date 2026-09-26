# Animation Tool Kit v1.1.5

Version **1.1.5** updates **SavePlus** to **2.0.6**. You can now put a one-click **Save Plus** button on your Maya shelf, so you can version up your scene without opening the SavePlus window.

## What's New

### SavePlus 2.0.6 — Save Plus Shelf Button

The **SavePlus** tab has a new **Add Save Plus to Shelf** button, just below the Save Plus, Save As New and Create Backup buttons.

Click it once to add a **Save+** button to your **Custom** shelf. If you don't have a Custom shelf, the button goes on the shelf that is currently open.

Clicking **Save+** on the shelf:

- Runs the same **Save Plus** as the SavePlus window: it increments the version number and saves a new copy, keeping your previous version
- Follows your **Respect Maya project structure** setting
- Adds the new version to the SavePlus **History**
- Shows the new file name in the viewport
- Updates the SavePlus window if it is open

If the scene has never been saved, the full SavePlus window opens instead so you can name it.

Clicking **Add Save Plus to Shelf** again updates the existing shelf button instead of adding a second one. The shelf is saved straight away, so the button is still there after you restart Maya.

---

## Fixes and Reliability Improvements

- **Updates load without restarting Maya**: SavePlus now reloads all of its files each time its window opens, so a reinstall followed by a toolbar reload shows the new version straight away
- **Version in the title bar**: the SavePlus window title now shows the version (for example **SavePlus v2.0.6**), so you can check which version is running
- **Script Editor output restored**: while the SavePlus window was open, all Python output and errors, including those from other tools, went only to the SavePlus log. They now appear in the Script Editor as well
- The Script Editor shows which folder SavePlus was loaded from each time it opens
- The release ZIP no longer includes Python cache (`__pycache__`) files

---

## Installation

1. Download the latest release ZIP from the **Assets** section below.
2. Extract the downloaded ZIP.
3. Open Autodesk Maya.
4. Drag `install_atk_toolbar.mel` into the Maya viewport.
5. Wait for the installation confirmation.
6. Use the new **ATK** shelf button to open the toolbar.

### Updating an Existing Installation

You can install version 1.1.5 over an existing ATK installation.

**Restart Maya once after installing 1.1.5.** Older versions of SavePlus stay loaded in memory until Maya restarts. From 1.1.5 onwards, SavePlus reloads itself when its window opens.

### Adding the Save Plus Shelf Button

1. Open **SavePlus** from the ATK toolbar.
2. On the **SavePlus** tab, click **Add Save Plus to Shelf**.
3. Use the **Save+** button on your Custom shelf to version up your scene with one click.

---

## Full Changelog

[Compare ATK v1.1.4 with ATK v1.1.5](https://github.com/dshepstone/Animation-Tool-Kit/compare/d8d18ec...ATK_1.1.5)
