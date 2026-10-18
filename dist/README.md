# Animation Tool Kit (ATK) Toolbar

Animation Tool Kit (ATK) Toolbar is a dockable Maya toolbar that installs and launches a curated set of animation, rigging, viewport, and pipeline tools.

Version **1.1.7** includes **Overlap 0.4.0** in the animation/timing group, next
to Noise Generator. Its full package, pendulum icon, offline HTML help, and
separate licence ship with ATK; no standalone install is required. The tool
supports per-axis overlap, offset pivots, optimized baking, and bake deletion.

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

- The installer copies files into Maya user preference/script locations (per-user install).
- If a tool file or icon is missing, Maya will show a warning and continue installing the rest.
