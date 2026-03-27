# xform_copy_paste — Copy Xform World Space

A Maya animation utility that copies and pastes world-space transforms (translate, rotate, scale) between objects. Animators also know this as **"Sticky Tool"** or **"Animation Recorder"**.

Reduces the need for locators as temporary references and makes transferring world-space xforms easy — for example, copying master control animation to COG and IKs.

---

## Installation

Drag `install_xform_copy_paste.mel` from your file browser onto the Maya viewport. The installer will:

1. Copy `xform_copy_paste.py` to your Maya user scripts folder
2. Copy the shelf icon to your Maya icons folder
3. Add 6 shelf buttons to your currently active shelf

All files (`install_xform_copy_paste.mel`, `xform_copy_paste.py`, `XformCP_Icon.png`) must be in the **same folder** when you drag-and-drop.

---

## Shelf Buttons

| Button | Hotkey | Description |
|---|---|---|
| Auto Xform | Alt+Click | Copy from first selected object, paste to all remaining selected at current frame |
| Copy Range | Ctrl+Shift+Click | Copy world-space xform for every frame in the playback range |
| Paste Xform | Ctrl+Click | Paste stored xform to selected objects at current frame |
| Paste All Keys | Ctrl+Alt+Shift+Click | Paste stored xform at every existing keyframe time on selected objects |
| Bake Frames | Ctrl+Alt+Click | Bake stored range xform to selected objects across the playback range |
| Next Frame | Shift+Click | Paste stored xform at current frame, then advance timeline by 1 |

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

- Maya 2022+ (Python 3) recommended
- Maya 2017–2020 (Python 2.7) supported with minor compatibility notes

---

## Development & Tests

Unit tests run outside Maya using mocked `maya.cmds`:

```bash
python -m pytest tests/
```

---

## License

MIT
