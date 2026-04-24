## Add/Remove Inbetweens Tool

**Created by David Shepstone**

This repository contains a Maya Python utility that helps animators quickly add or remove inbetween frames to retime their animation without destroying spacing. The UI is implemented with PySide2/PySide6 so it runs on Maya 2020 through 2026.

### Key Features

* **Modern dockable panel** – the UI is hosted in a Maya `workspaceControl`, so it can float, dock into any pane, or be tabbed alongside existing Maya panels.
* **Compact card-based layout** – three focused sections (Scope, Insert/Remove Frames, Key Spacing) with segmented controls and colour-coded action buttons keep the window small and easy to move.
* **Scope segmented control** – switch between **Selected** objects and **All Keyed** curves with one click. Toggle **Use Time Range (ripple)** to work on the highlighted time slider range with ripple retiming.
* **Insert / Remove Frames** – pick an amount and click ▲ Insert or ▼ Remove; every operation is a single undo step.
* **Key Spacing (Ripple)** – select keys in the time slider and redistribute them to an even interval (0=consecutive, 2=every other frame, etc.), rippling later keys so timing is preserved.
* **Menu bar with HTML Help** – the top-level **Help** menu opens a dedicated Help/How To window (rendered as HTML) with sections for How To, Keyboard Shortcuts and About.
* **Status feedback** – inline status line plus Maya heads-up messages for every action.

### Installation

#### Quick Install (Drag & Drop)

1. Download the files from the `dist` folder:
   - `install_InsertRemoveFrames.mel`
   - `add-remove.png` (icon file)
2. Place both files in the same folder on your computer.
3. Drag and drop `install_InsertRemoveFrames.mel` into the Maya viewport.
4. The installer will:
   - Extract and install `insert_remove_frames_tool.py` to your Maya scripts directory
   - Copy the `add-remove.png` icon to your Maya preferences/icons folder
   - Open the tool window automatically
   - Display a dialog asking if you want to add a shelf button
5. Choose **Yes** to add a shelf button for quick access, or **No** to skip shelf button creation.

The shelf button (if installed) will be named **Inbetweens** and will appear on your currently active shelf tab.

**Note:** You can re-run the installer at any time to refresh the script or update the shelf button. Existing shelf buttons with the same command are automatically replaced.

### Usage

#### Opening the Tool

There are three ways to launch the Add/Remove Inbetweens tool:

1. **Shelf Button** (if installed): Click the **Inbetweens** button on your shelf
2. **Python Command** (Script Editor): Execute this command in Maya's Python Script Editor:
   ```python
   import insert_remove_frames_tool as irft
   irft.show()
   ```
3. **MEL Command** (Script Editor): Execute this MEL command:
   ```mel
   python("import insert_remove_frames_tool as irft; irft.show()");
   ```

You can also add the Python command to a hotkey in Maya's Hotkey Editor for instant access.

#### How It Works

The tool provides several ways to manipulate animation timing:

**Insert/Remove Frames:**
1. In the **Scope** card, click **Selected** or **All Keyed** to define the retiming scope.
2. Leave **Use Time Range (ripple)** off to affect keys at and after the current time, or enable it to operate on the highlighted time slider range (or playback range) with ripple adjustments to later keys.
3. Set the number of **Frames** in the spin box.
4. Press **▲ Insert** to push keys forward or **▼ Remove** to pull keys backward.

**Key Spacing (Ripple):**
1. Select keyframes in Maya's time slider (highlight the frames you want to re-space).
2. Set the **Spacing** value:
   - `0` = keys on consecutive frames (ones)
   - `2` = every other frame (interval of 2)
   - `n` = interval of `n` frames between keys
3. Click **Apply** to redistribute the selected keys; later keys on those curves ripple to preserve timing.

**Docking & Help:**
- Drag the panel's title bar onto any Maya dock area to dock or tab it.
- Open **Help → How To...** for the full HTML how-to guide, **Help → Keyboard Shortcuts**, or **Help → About**.
- Use **Tools → Reset to Defaults** to return every control to its default state.

**Additional Features:**
- Each operation wraps in a single undo chunk (Ctrl+Z/Cmd+Z to undo)
- Tangents and curve shapes are preserved
- Locked or non-keyable channels are gracefully skipped
- **Keyboard shortcuts**: Ctrl/Cmd+↑ to insert, Ctrl/Cmd+↓ to remove

### Technical Details

**Compatibility:**
- Maya 2020 - 2026+
- Works with both PySide2 and PySide6
- Compatible with Windows, macOS, and Linux

**File Locations:**
- Script installed to: `~/maya/scripts/insert_remove_frames_tool.py`
- Icon installed to: `~/maya/prefs/icons/add-remove.png`

**Supported Animation Curve Types:**
- Transform (animCurveTL, animCurveTA, animCurveTT, animCurveTU)
- Morph (animCurveML, animCurveMA, animCurveMT, animCurveMU)

### License & Credits

Created by **David Shepstone**

This tool is provided as-is for use in animation workflows. Feel free to use, modify, and distribute for your animation projects.
