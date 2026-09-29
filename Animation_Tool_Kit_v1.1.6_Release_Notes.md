# Animation Tool Kit v1.1.6

Version **1.1.6** is a fix release for **Playblast Creator** and the toolbar's **Reload Scripts** button. Playblasts now save reliably to the folder you choose, and MP4/MOV output unlocks as soon as FFmpeg is set up.

## Fixes

### Playblast Creator — Saving to a Chosen Folder

Saving a playblast to a specific folder sometimes failed without telling you. This is now fixed.

- **Clear success and failure messages**: the Output Log shows **"Playblast saved to"** with the real file path only when the file was written. If nothing was saved, it now says so and gives the reason. For example, a file with the same name already exists and **Overwrite** is off.
- **Tokens in the output folder now work**: `{project}`, `{temp}`, `{scene}` and `{timestamp}` are all filled in before the folder is created. Previously a folder literally named `{project}` or `{scene}` could be created instead.
- **Relative folders are consistent**: a relative path such as `movies/blasts` now always sits inside your Maya project, rather than moving around as Maya's working folder changes.
- **The output folder is remembered**: the tool keeps your last output folder after you close it or restart Maya.
- **FFmpeg failures are caught**: if FFmpeg fails to write the video, the log says so instead of reporting success.

### Playblast Creator — MP4 / MOV with FFmpeg

When FFmpeg was already set, the MP4 and MOV codecs on the **Encoding** tab could still show as unavailable until Maya was restarted. This is now fixed.

- The tool checks FFmpeg again each time its window opens
- Choosing FFmpeg with the **...** button, or typing its path, takes effect straight away. You no longer need to click **Apply Tool Settings** first.
- FFmpeg paths are accepted in more forms: pasted with quotes (Windows **Copy as path**), the FFmpeg folder or its `bin` folder, or just `ffmpeg` if it is on your system PATH
- A warning appears if the `PLAYBLAST_CREATOR_FFMPEG` environment variable overrides the path entered in the tool
- The **Temp Format** option **jpg** now works. Previously it was silently replaced by png.

> **Tip:** The **Temp Format** setting on the Settings tab is only for the frames made before encoding. Choose **.mp4** or **.mov** under **Encoding → Container**.

### Toolbar — Reload Scripts

**ATK Settings → Reload Scripts** now fully reloads updated tools without restarting Maya.

- Helper files are reloaded too: Playblast Creator presets, all SavePlus modules and all Studio Library packages. Previously a tool's main file was reloaded but it kept using the old helper files.
- The Playblast Creator Maya plug-in is now reloaded as well
- If the open scene has a Playblast Creator shot mask, the plug-in is not reloaded, because that would remove the shot mask. A message explains this. Delete the shot mask or restart Maya to load the new plug-in.
- Tool windows that are already open keep running the old code. Relaunch them from the toolbar.

---

## Installation

1. Download the latest release ZIP from the **Assets** section below.
2. Extract the downloaded ZIP.
3. Open Autodesk Maya.
4. Drag `install_atk_toolbar.mel` into the Maya viewport.
5. Wait for the installation confirmation.
6. Use the new **ATK** shelf button to open the toolbar.

### Updating an Existing Installation

You can install version 1.1.6 over an existing ATK installation.

**Restart Maya once after installing 1.1.6.** The improved Reload Scripts button is part of this update, so the older version still in memory cannot load it. Future updates can then be loaded with **Reload Scripts**.

---

## Full Changelog

[Compare ATK v1.1.5 with ATK v1.1.6](https://github.com/dshepstone/Animation-Tool-Kit/compare/ATK_1.1.5...ATK_1.1.6)
