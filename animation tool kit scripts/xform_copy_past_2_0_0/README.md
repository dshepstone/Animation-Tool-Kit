# xform_copy_paste — Copy Xform World Space

A Maya animation utility that copies and pastes world-space transforms (translate, rotate, scale) between objects. Animators also know this as **"Sticky Tool"** or **"Animation Recorder"**.

Reduces the need for locators as temporary references and makes transferring world-space xforms easy — for example, copying master control animation to COG and IKs.

---

## Installation

Drag `install_xform_copy_paste.mel` from your file browser onto the Maya viewport. The installer will:

1. Copy `xform_copy_paste.py` to your Maya user scripts folder
2. Copy the shelf icon to your Maya icons folder
3. Add a single **XformCP** shelf button to your currently active shelf

All files (`install_xform_copy_paste.mel`, `xform_copy_paste.py`, `xform_copy_paste.png`) must be in the **same folder** when you drag-and-drop.

---

## The XformCP Shelf Button

A **plain click** opens the tool window. **Modifier clicks** fire actions directly without opening the window:

| Modifier click | Action | Description |
|---|---|---|
| (plain click) | Open Window | Open the Copy Xform World Space tool window |
| Alt+Click | Auto Xform | Copy from first selected object, paste to all remaining selected at current frame |
| Ctrl+Click | Paste Xform | Paste stored xform to selected objects at current frame |
| Shift+Click | Next Frame | Paste stored xform at current frame, then advance timeline by 1 |
| Ctrl+Shift+Click | Copy Range | Copy world-space xform for every frame in the playback range |
| Ctrl+Alt+Click | Bake Frames | Bake stored range xform to selected objects across the playback range |
| Ctrl+Alt+Shift+Click | Paste All Keys | Paste stored xform at every existing keyframe time on selected objects |

> The two multi-object range actions (**Copy Xform WS Multi Objects Playback Range** and **Paste Xform WS Keys Playback Range**) are available as buttons inside the tool window.

---

## Typical Workflows

**Single frame transfer:**
1. Select source object, then target object(s)
2. Click **Auto Xform** — source xform is copied and pasted to targets in one step

**Range bake:**
1. Select source object → click **Copy Range** (stores all frames in playback range)
2. Select target object(s) → click **Bake Frames** (applies stored xform to every frame)

**Step through frames manually:**
1. Select source → click **Paste Xform** to copy single-frame xform
2. Select target → click **Next Frame** repeatedly to paste and step forward

---

## Requirements

- Maya 2020+ with PySide2 or PySide6 (the tool window auto-detects the binding)
- The core transform functions also run under Maya 2017+ / Python 2.7; only the
  redesigned Qt window needs a PySide-capable Maya.

---

## Development & Tests

Unit tests run outside Maya using mocked `maya.cmds`:

```bash
python -m pytest tests/
```

---

## License

MIT
