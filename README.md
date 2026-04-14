# Animation Tool Kit (ATK) Toolbar

Animation Tool Kit (ATK) Toolbar is a dockable Maya toolbar that installs and launches a curated set of animation, rigging, viewport, and pipeline tools.

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


## Toolbar script tools

The ATK toolbar currently registers the following script tools (in toolbar order):

1. Inbetweener
2. Add / Remove Frames
3. TweenMachine
4. Noise Generator
5. Xform Copy Paste
6. Bookmarks
7. Micro Manipulator
8. Temp Pivot
9. Onion Skin
10. AnimSnap
11. Wire Shape Tool
12. Reset Tool
13. Selection Set
14. Diget Mirror
15. SavePlus
16. Studio Library
17. User Directory Check

## Open-source script license details

### Studio Library
- Repository: https://github.com/krathjen/studiolibrary
- Bundled version in ATK: `studiolibrary-2.21.1`
- License in this repository: **GNU Lesser General Public License v3.0 (LGPL-3.0)**
- Primary credited author/copyright holder in bundled source: **Kurt Rathjen**

### tweenMachine
- Repository: https://github.com/The-Maize/tweenMachine/tree/master
- Bundled location in ATK: `animation tool kit scripts/tweenMachine/`
- License in this repository: **MIT License**
- Credited authors in bundled license: **Justin S Barrett**, with modifications by **Wade Schneider** and **Andrew Silke**

## Contributors (tools and scripts)

### ATK repository contributors
- David Shepstone
- Claude (Anthropic)

### Third-party script contributors included with ATK
- Kurt Rathjen (Studio Library)
- Justin S Barrett (tweenMachine)
- Wade Schneider (tweenMachine updates)
- Andrew Silke (tweenMachine updates)
