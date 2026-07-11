# Animation Tool Kit v1.1.3

Version **1.1.3** introduces major improvements to the ATK toolbar’s docking, positioning, and vertical layout, along with the addition of the new **Blue Pencil Flipbook Manager** for Autodesk Maya.

## What's New

### Blue Pencil Flipbook Manager

The **Blue Pencil Flipbook Manager** is now included in the Animation Tool Kit and can be launched directly from the ATK toolbar.

Designed for Maya’s Blue Pencil workflow, the manager includes:

- Drawing-frame thumbnails
- Frame type identification
- Filtered drawing playback
- Quick-access Blue Pencil tools
- Frame management actions
- Customizable hotkeys
- Integrated HTML help documentation
- A modern dark interface matching the ATK toolbar

The tool is registered in the **Viewport Tools** section beside the Onion Skin tool.

> The Blue Pencil Flipbook Manager is currently designed for the Maya 2026 Blue Pencil system.

---

## Toolbar Docking Improvements

The ATK toolbar now provides more flexible and reliable placement options inside Maya.

Available docked positions include:

- **Above the timeline**
- **Below the shelf**
- **Left of the viewport**
- **Right of the viewport**

The preferred dock position can be selected from:

`ATK Settings → Workspace → Docked Position`

Changing the setting immediately moves and rebuilds the toolbar in the selected location.

### Automatic Orientation

The toolbar automatically adjusts its layout based on where it is docked:

- Top and bottom docking areas use a **horizontal toolbar**
- Left and right docking areas use a **vertical toolbar**

Orientation is also corrected when moving the toolbar directly from one dock area to another.

### Improved Vertical Toolbar

The vertical toolbar now includes:

- A scrollable tool list
- A vertical Inbetweener slider
- Centred toolbar icons
- Automatic height limits based on the available screen space
- Reliable access to every installed tool, even on smaller displays

### Content-Fitted Docking

The docked toolbar now fits closely around its contents instead of occupying a large empty section of Maya’s interface.

Horizontal bars use only the required height, while vertical bars use only the required width.

---

## Improved Toolbar Dragging

A dedicated grip handle has been added to make the toolbar easier to tear away from its dock.

The updated dragging system includes:

- More stable toolbar movement
- Edge-based snap docking
- Improved left and right viewport docking
- Protection against the toolbar moving off-screen
- Reduced movement jitter
- Correct orientation after drag-and-drop docking
- Saved dock-position synchronization

Floating the toolbar now uses a short fade and resize transition instead of abruptly appearing as a separate window.

---

## ATK Logo Button

A new **ATK logo button** has been added beside the Settings button.

Clicking the logo opens the Animation Tool Kit website:

[Visit shepstone.ca](https://shepstone.ca/)

The logo has also been enlarged and updated with a white outline for better visibility against Maya’s dark interface.

---

## Fixes and Reliability Improvements

- Fixed invalid Maya `workspaceControl` docking arguments
- Fixed horizontal toolbars remaining horizontal when docked on the left or right
- Fixed vertical toolbars remaining vertical when moved to a top or bottom dock
- Fixed toolbar jitter during grip-handle dragging
- Fixed floating toolbars moving outside the visible screen
- Improved detection of Maya’s active docking area
- Added dock geometry monitoring for direct dock-to-dock moves
- Improved toolbar resizing after docking or changing orientation
- Improved toolbar rebuilding after changing workspace settings
- Updated installer support for the Blue Pencil Flipbook Manager package and icon

---

## Installation

1. Download the latest release ZIP from the **Assets** section below.
2. Extract the downloaded ZIP.
3. Open Autodesk Maya.
4. Drag `install_atk_toolbar.mel` into the Maya viewport.
5. Wait for the installation confirmation.
6. Use the new **ATK** shelf button to open the toolbar.

### Updating an Existing Installation

You can install version 1.1.3 over an existing ATK installation.

The installer will update the toolbar scripts, tool packages, icons, and related files in your Maya user directories.

Restart Maya after installation if an older version of a tool remains loaded in memory.

---

## Full Changelog

[Compare ATK v1.1.2 with ATK v1.1.3](https://github.com/dshepstone/Animation-Tool-Kit/compare/ATK_v1-1-2...ATK_1.1.3)
