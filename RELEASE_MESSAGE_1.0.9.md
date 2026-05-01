# Animation Tool Kit v1.0.9

Animation Tool Kit (ATK) **v1.0.9** is now available.

This release ships the latest bundled ATK toolbar package and tool collection for Autodesk Maya, with updated distribution archives and installer-ready layout.

---

## Release information

- **Version:** 1.0.9
- **Package:** `Animation_Tool_Kit_v1_0_9.zip`
- **Type:** Production release
- **Platform:** Autodesk Maya (Python-based toolset)
- **Install method:** Drag-and-drop `install_atk_toolbar.mel` into Maya

---

## Included tools

ATK v1.0.9 includes the following tools in the dockable toolbar:

### Timing
- Inbetweener (v2.0.2)
- Add / Remove Frames (v1.0.2)
- Tangent Tools (v1.0.0)
- TweenMachine (v3.x)
- Noise Generator (v1.0.0)
- Xform Copy Paste (v2.0.0)
- Bookmarks (v0.1.0)

### Viewport
- Micro Manipulator (v1.0.0)
- Temp Pivot (v1.0.5)
- Onion Skin (v2.1.0)
- AnimSnap (v1.0.0)

### Rigging
- Wire Shape Tool (v1.0.0)
- Reset Tool (v2.0.1)
- Selection Set (v2.0.4)
- Character Snapshot (v1.0.0)
- Mirror Controls (v2.3.1)

### Pipeline
- SavePlus (v2.0.4)
- Studio Library (v2.21.1)
- Playblast Creator (v2.0.4)
- User Directory Check (v1.0.0)

---

## Installation

1. Download `Animation_Tool_Kit_v1_0_9.zip` from the release assets.
2. Extract the archive.
3. In Maya, drag and drop `install_atk_toolbar.mel` into the viewport.
4. Confirm install when prompted.
5. Launch the toolbar from the new **ATK** shelf button.

---

## Notes

- This release is packaged for per-user installation into Maya user script/icon locations.
- If a specific tool file or icon is missing, the installer continues and logs warnings.
- Existing users can reinstall to refresh the toolbar package and bundled scripts.

---

## Known compatibility

- Designed for Maya environments that support the shipped Python/Qt stack used by ATK tools.
- Some third-party bundled tools may have their own version-specific requirements.

---

## Credits

Thanks to all contributors and third-party tool authors included in the ATK bundle.

For licensing details, see:
- `ATK_LICENSE.md`
- `THIRD_PARTY_NOTICES.md`
