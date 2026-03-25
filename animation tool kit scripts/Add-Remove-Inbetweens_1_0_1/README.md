## Add/Remove Inbetweens Tool

**Created by David Shepstone**

This repository contains a Maya Python utility that helps animators quickly add or remove inbetween frames to retime their animation without destroying spacing. The UI is implemented with PySide2/PySide6 so it runs on Maya 2020 through 2026.

### Key Features

* **Target & Range controls** – operate on the keyed attributes of the current selection or the entire scene. Toggle **Use Time Range** to work on the highlighted time slider range or the playback range with ripple-style retiming for keys past the range.
* **Amount section** – choose how many frames to affect via the spin box or the large ▲/▼ buttons for inserting or removing blank frames.
* **Set Inbetween utility** – select keys in the time slider and insert the desired number of blank frames between them, with automatic ripple of later keys on those curves and any selected controls.
* **Apply & Safety tools** – reuse the most recent insert/remove choice through the Apply button, keep the operation undo-friendly, and optionally close the window after applying.
* **Contextual help** – a built-in help dialog explains every control, keyboard shortcut, and the difference between inserting and removing blank frames.

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
1. Choose **Selected objects** or **All keyed in scene** to define the retiming scope.
2. Leave **Use Time Range** off to affect keys at and after the current time, or enable it to operate on the highlighted time slider range (or playback range) with ripple adjustments to later keys.
3. Set the number of frames to insert or remove using the spin box.
4. Press the **▲** button to insert (push keys forward) or **▼** button to remove (pull keys backward).
5. Use the **Apply** button to repeat the last insert/remove action.

**Set Inbetween Spacing:**
1. Select keyframes in Maya's time slider (highlight the frames you want to space).
2. Set the **Inbetweens** value:
   - `0` = keeps keys on consecutive frames (ones)
   - `1` = adds one blank frame between each key
   - `2` = adds two blank frames between each key
   - etc.
3. Click **Set Inbetween** to apply the spacing.
4. Any keys after the selection on those curves—and on currently selected controls—will ripple to preserve timing.

**Additional Features:**
- Each operation wraps in a single undo chunk (Ctrl+Z/Cmd+Z to undo)
- Tangents and curve shapes are preserved
- Locked or non-keyable channels are gracefully skipped
- **Keyboard shortcuts**: Ctrl/Cmd+↑ to insert, Ctrl/Cmd+↓ to remove
- Click the **?** button for built-in help and detailed explanations

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
