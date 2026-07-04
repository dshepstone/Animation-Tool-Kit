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

Click the **XformCP** shelf button to open the tool window.

---

## Functions

| Function | Description |
|---|---|
| Auto Xform World Space | Copy from first selected object, paste to all remaining selected at current frame |
| Copy Xform World Space | Store the first selected object's world-space xform at the current frame |
| Copy Xform WS Playback Range | Store the first selected object's xform for every frame in the playback range |
| Copy Xform WS Multi Objects Range | Store ALL selected objects across the playback range (matched by selection order) |
| Paste Xform World Space | Paste stored xform to selected objects at current frame |
| Paste Xform WS All Keys | Paste stored xform at every existing keyframe time on selected objects |
| Paste Xform WS Bake Frames | Bake stored range xform to selected objects across the playback range |
| Paste Xform WS Next Frame | Paste stored xform at current frame, then advance timeline by 1 |
| Paste Xform WS Keys Playback Range | Paste stored multi-object data onto existing keys only, matched by selection order |

Locked or connected channels (e.g. locked scale on rig controls) are skipped with a warning instead of aborting the paste.

---

## Keyboard Shortcuts

Every function can be bound to a Maya hotkey. Click **Setup / Edit Hotkeys...** in the tool window, click the field next to a function, press the desired key combination, and hit **Apply**. Bindings are written to your active Maya hotkey set and saved with your preferences, so they persist between sessions.

Maya's default `Maya_Default` hotkey set is locked — if it is active you will be prompted to choose or create a custom hotkey set first. The commands also appear in Maya's Hotkey Editor under **Custom Scripts > Xform Copy Paste**.

---

## Typical Workflows

**Single frame transfer:**
1. Select source object, then target object(s)
2. Click **Auto Xform World Space** — source xform is copied and pasted to targets in one step

**Range bake:**
1. Select source object → click **Copy Xform WS Playback Range** (stores all frames in playback range)
2. Select target object(s) → click **Paste Xform WS Bake Frames** (applies stored xform to every frame)

**Retime existing keys from multiple sources:**
1. Select all source controllers → click **Copy Xform WS Multi Objects Range**
2. Select corresponding target controllers (same order/count) → click **Paste Xform WS Keys Playback Range**

**Step through frames manually:**
1. Select source → click **Copy Xform World Space**
2. Select target → click **Paste Xform WS Next Frame** repeatedly to paste and step forward

---

## Status Indicator

The coloured pill at the top of the window shows what is currently stored:

- **Grey** — nothing stored
- **Green** — single-frame xform stored
- **Blue** — single-object playback-range data stored
- **Purple** — multi-object playback-range data stored

---

## Requirements

- Maya 2025+ (PySide6) recommended
- Maya 2022–2024 (PySide2) supported

---

## License

MIT
