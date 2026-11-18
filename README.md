# Animation Tool Kit (ATK) Toolbar

Animation Tool Kit (ATK) Toolbar is a dockable Maya toolbar that installs and launches a curated set of animation, rigging, viewport, and pipeline tools.

Version **1.1.16** adds **Animation Tweaker** to the rigging group. It sculpts
corrections and polish onto animated meshes after the skin, keys them as
static, pulse or pose-to-pose tweaks, and bakes Smooth Motion, Stick to Surface,
Push Out and Pin to World effects. It also has a surface-riding soft-modification
handle and cache versions. It keeps everything from 1.1.15, including the
toolkit-wide bug fixes, Key Cleanup and Stagger Keys.
See [release notes](Animation_Tool_Kit_v1.1.16_Release_Notes.md).

For an existing video, use **Output → Destination → Force overwrite existing
output**, or choose a different filename. Failed encoding preserves the old video.

Video export requires an FFmpeg build with the chosen codec; **libx264** is the
recommended H.264 software fallback on Windows, macOS, and Linux. Choose the
executable in Settings. Maya itself and a working viewport are required to capture.

## What the installer does

When you drag-and-drop `install_atk_toolbar.mel` into Maya, the installer:

- Copies the `atk_toolbar` Python package into your Maya user scripts directory.
- Copies tool scripts from `animation tool kit scripts/` into your Maya user scripts directory.
- Copies tool icons into your Maya user icons directory.
- Adds an **ATK** shelf button to launch the toolbar.
- Launches the toolbar immediately after install.

## Folder layout for distribution

Keep these items side-by-side in the same folder before sending to users:

- `install_atk_toolbar.mel`
- `atk_toolbar/`
- `animation tool kit scripts/`

For **User Directory Check**, the installer first looks for:

- `animation tool kit scripts/User-Directory-Check/user_directory_check_icon.png`

If that file is missing, it falls back to:

- `icon/user_directory_check_icon.png`

## Installation steps (for artists)

1. Open Maya.
2. Drag `install_atk_toolbar.mel` from Explorer/Finder into the Maya viewport.
3. Wait for the install confirmation dialog.
4. Use the new **ATK** shelf button to open the toolbar.

## Notes

- **Timeline Ticks** provides a compact Key / Extreme / Breakdown / Inbetween
  window, plus a single-slot yellow/red/blue palette and menu on the main ATK
  toolbar. Labels follow key moves and deletions, including Add/Remove Frames
  and Undo/Redo while tracking is active. The window also includes green. Install using
  the usual ATK installer, then launch it from the timing group. See its
  [usage and limitations](animation%20tool%20kit%20scripts/Timeline_Ticks_1_0_0/README.md).

- **Key Cleanup** removes redundant keys, static channels, sub-frame keys and
  Euler flips on the selection or the whole scene. It's in the timing group. See its
  [usage notes](animation%20tool%20kit%20scripts/Key_Cleanup_1_0_0/README.md).

- **Stagger Keys** offsets keys across a selection in selection order, to block
  in overlap on tails, spines and fingers. It's in the timing group. See its
  [usage notes](animation%20tool%20kit%20scripts/Stagger_Keys_1_0_0/README.md).

- **Walk Off Node** turns a treadmill walk cycle into a walk that travels. It keys
  the IK feet, hands and waist where they really are in world space, removes the
  base / layout node's slide and the cycle, so the character walks off the node.
  It's in the timing group, and also opens from **Xform Copy Paste**. See its
  [usage notes](animation%20tool%20kit%20scripts/Walk_Off_Node_1_0_0/README.md).

- **Animation Tweaker** sculpts corrections onto animated meshes after the skin
  and keys them as static, pulse or pose-to-pose tweaks. It also has Inflate,
  Relax, frame-baked effects (Smooth Motion, Stick to Surface, Push Out, Pin to
  World), a surface-riding handle, production utilities and cache versions.
  It's in the rigging group. Every tweak is a target on one blendShape per mesh,
  so nothing else is left in the scene. See its
  [usage notes](animation%20tool%20kit%20scripts/Animation_Tweaker/README.md).

- The installer copies files into Maya user preference/script locations (per-user install).
- If a tool file or icon is missing, Maya will show a warning and continue installing the rest.
