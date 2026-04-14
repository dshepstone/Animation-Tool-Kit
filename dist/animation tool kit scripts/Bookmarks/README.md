# Maya Time Bookmarks

A lightweight bookmark tool for Autodesk Maya that lets animators mark named frame ranges directly on the timeline.  Bookmarks are saved inside the Maya scene file, travel with the scene, and survive save/reload.

---

## Features

- **Named bookmarks** with a custom colour, start/end frame, and optional notes
- **Coloured bands** painted transparently over the native Maya timeline
- **Keyboard shortcuts** on the timeline (no menu diving required)
- **Bookmark panel** for create / edit / delete / navigate
- **Scene-embedded persistence** via `cmds.fileInfo` — no sidecar files
- Supports **Maya 2022–2025** (PySide2 and PySide6)

---

## Installation (drag-and-drop)

1. Download `maya_time_bookmarks_v0.1.0.zip` and extract it anywhere on disk.
2. Open the extracted folder in your OS file browser.
3. Drag **`install.mel`** from the folder and drop it onto the **Maya viewport**.
4. The installer will:
   - Add the `src/` directory to `sys.path` for the current session.
   - Append a persistent `sys.path` entry to `~/maya/<version>/prefs/scripts/userSetup.py`.
   - Create a **"Time Bookmarks"** shelf tab with a **TB** button.
5. Click **OK** in the confirmation dialog.

> **Reinstalling / updating**: simply drag `install.mel` again.  The installer
> detects existing entries and replaces the shelf button cleanly.

---

## Manual installation

If drag-and-drop is unavailable, add the following to your `userSetup.py`
(or run it once in the Script Editor):

```python
import sys
sys.path.insert(0, r"/path/to/extracted/maya_time_bookmarks_v0.1.0/src")
```

Then launch the tool from the Script Editor:

```python
import time_bookmarks.main
time_bookmarks.main.launch()
```

---

## Shelf button setup (manual)

In the Script Editor → Python tab, run:

```python
import maya.cmds as cmds
cmds.shelfButton(
    parent="Custom",
    label="Time Bookmarks",
    annotation="Open Time Bookmarks panel",
    command="import time_bookmarks.main\ntime_bookmarks.main.launch()",
    sourceType="python",
    imageOverlayLabel="TB",
)
```

---

## Timeline shortcuts

All shortcuts require a **left-click** on the timeline while holding the listed
modifier keys.  Shortcuts never consume the click — Maya's normal scrubbing
still works.

| Modifier(s)              | Action                                    |
|--------------------------|-------------------------------------------|
| Ctrl + Alt               | Create a bookmark at the current frame    |
| Ctrl                     | Jump to the **next** bookmark             |
| Shift                    | Jump to the **previous** bookmark         |
| Ctrl + Shift             | Set playback range to bookmark at frame   |
| Alt                      | Toggle timeline overlay visibility        |
| Alt + Shift              | Show / raise the bookmark panel           |
| Ctrl + Alt + Shift       | Remove the bookmark covering this frame   |

---

## Bookmark panel

Open with the **TB** shelf button or `Alt+Shift+Click` on the timeline.

| Control              | Action                                           |
|----------------------|--------------------------------------------------|
| **+** button         | Create a new bookmark                            |
| Double-click row     | Edit the bookmark (name, range, colour, notes)   |
| **Edit** button      | Edit the selected bookmark                       |
| **Delete** button    | Delete the selected bookmark                     |
| **Jump To** button   | Move the timeline cursor to that bookmark's start|

---

## userSetup.py snippet

For a permanent installation that survives Maya updates, add these two lines to
`~/maya/scripts/userSetup.py` (create the file if it does not exist):

```python
import sys
sys.path.insert(0, r"/absolute/path/to/maya_time_bookmarks_v0.1.0/src")
```

To auto-launch on Maya startup, also add:

```python
import maya.utils
maya.utils.executeDeferred("import time_bookmarks.main; time_bookmarks.main.launch()")
```

---

## Repository layout

```
.
├── build.py                  # Run to create dist/maya_time_bookmarks_v*.zip
├── install.mel               # Drag-and-drop installer for Maya
├── icons/
│   └── time_bookmarks.svg    # Shelf button icon source
├── src/
│   └── time_bookmarks/
│       ├── core/             # BookmarkService, BookmarkController, protocols
│       ├── data/             # Bookmark dataclass + BookmarkSerializer
│       ├── maya/             # MayaTimeAdapter, MayaScenePersistence,
│       │                     # MayaQtBridge, TimelineEventFilter
│       ├── ui/               # BookmarkPanel, TimelineOverlay, dialogs, widgets
│       ├── dev_launch.py     # Standalone launch (no Maya required)
│       ├── main.py           # maya.cmds-aware entry point
│       └── qt_compat.py      # PySide2 / PySide6 shim
└── tests/                    # pytest suite (152 tests, no Maya required)
```

---

## Building the distribution zip

```bash
python build.py
# → dist/maya_time_bookmarks_v0.1.0.zip
```

---

## Running the test suite

```bash
pip install -e ".[test]"        # installs pytest + pytest-qt
QT_QPA_PLATFORM=offscreen pytest tests/ --ignore=tests/integration
```

All 152 tests run without Maya.  Integration tests in `tests/integration/`
require a live Maya session.

---

## Compatibility

| Maya version | Qt binding | Status      |
|--------------|------------|-------------|
| 2022         | PySide2    | Supported   |
| 2023         | PySide2    | Supported   |
| 2024         | PySide2    | Supported   |
| 2025         | PySide6    | Supported   |
