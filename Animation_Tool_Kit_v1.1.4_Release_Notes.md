# Animation Tool Kit v1.1.4

Version **1.1.4** adds a new **Troubleshoot Rig Setup** function to **Mirror Controls**, so rigs whose hands and fingers would not mirror correctly now mirror properly. It also stops minimized ATK tool windows from floating over the middle of the Maya interface.

## What's New

### Mirror Controls 2.4.0 — Troubleshoot Rig Setup

Some rigs would not mirror their hands and fingers correctly, even after taking a Character Snapshot. Thumbs curled the wrong way, and some finger, leg and face controls mirrored with the wrong sign.

This happens with rigs that have "odd" setups, for example:

- Extra 180° offset groups on one side only
- Finger controls sitting close to 45° in the default A-pose
- Angled (oblique) thumb controls
- Curl attributes wired differently on each side

The new **Troubleshoot Rig Setup** function finds and fixes these problems automatically. Open it from the purple **Troubleshoot Rig Setup** button in the Character Snapshot panel, or from **Tools → Troubleshoot Rig Setup…**

When you click **Run Analysis**, the troubleshooter:

- Puts the whole rig into its snapshot default pose, then restores your animation afterwards
- Works out the exact mirror for every left/right pair and centre control from each control's real orientation
- Tests custom attributes such as curls to find whether they should copy or flip
- Checks every result in the scene before offering it
- Lists every corrected channel, plus any rig problems it finds

Click **Apply Fix** to store the result in the Character Snapshot. **Mirror**, **Flip** and **Mirror Middle** then use it automatically. The fix is kept when the snapshot is re-taken.

The troubleshooter also:

- **Works in animated shots**: characters that are moved or turned in the scene mirror across their own centre, not the world's
- **Repairs wrong pairings**: for example, a manual pair that linked `L_handThumb` to `R_handThumb2`
- **Can fix just part of a rig**: choose **Selected controls** to fix one area, such as a hand
- **Reports rig problems it can't fix**: attributes that exist on one side only, driver networks wired differently per side, and default poses that aren't symmetric

Controls whose axes don't line up with their partner's are now mirrored using their full orientation, instead of simple copy/flip rules. This covers angled controls, mismatched rotate orders and uneven default values.

**Edit Rules** now shows fixed channels as **(rig fix: …)**. Your own manual overrides still take priority.

---

## Minimized Tool Windows

Minimizing an ATK tool window used to leave a small title bar floating over the viewport or picker.

Minimized tools now line up neatly along the bottom of the screen Maya is on:

- Bars fill from left to right, and start a new row above when the bottom row is full
- Gaps are reused when a tool is restored
- Bars are placed on whichever monitor Maya is on
- Click a bar to reopen the tool

This applies to every tool opened from the ATK toolbar, including dialogs a tool opens later. **Mirror Controls** and **Character Snapshot** also get it when launched from a shelf button.

> This change applies to Windows only. macOS and Linux are unaffected.

---

## Fixes and Reliability Improvements

- Fixed thumb, knee, leg-bend, ball and several face controls mirroring with the wrong sign on rigs with oblique or re-oriented controls
- Fixed **Mirror Middle** flipping `rotateX` on world-aligned centre controls (it now copies it) once a rig fix is stored
- Fixed minimized tool windows floating over the middle of the Maya interface
- Improved the disabled-button styling in Mirror Controls dialogs

---

## Installation

1. Download the latest release ZIP from the **Assets** section below.
2. Extract the downloaded ZIP.
3. Open Autodesk Maya.
4. Drag `install_atk_toolbar.mel` into the Maya viewport.
5. Wait for the installation confirmation.
6. Use the new **ATK** shelf button to open the toolbar.

### Updating an Existing Installation

You can install version 1.1.4 over an existing ATK installation.

The installer will update the toolbar scripts, tool packages, icons, and related files in your Maya user directories. This includes the new `atk_toolbar/atk_window.py` file.

Restart Maya after installation if an older version of a tool remains loaded in memory.

### Fixing a Rig That Won't Mirror

1. Open the scene and make sure the rig has a Character Snapshot. Take the snapshot at the rig's default pose.
2. Open **Mirror Controls** and click **Troubleshoot Rig Setup**.
3. Click **Run Analysis** and review the list of corrections.
4. Click **Apply Fix**.
5. Mirror as normal.

---

## Full Changelog

[Compare ATK v1.1.3 with ATK v1.1.4](https://github.com/dshepstone/Animation-Tool-Kit/compare/ATK_1.1.3...ATK_1.1.4)
