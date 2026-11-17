# Animation Tool Kit 1.1.15 — toolkit-wide bug-fix pass, Key Cleanup and Stagger Keys

Every tool on the toolbar was reviewed. This release fixes the bugs that review found and adds two tools to the timing group.

## New tools

- **Key Cleanup** removes redundant keys inside flat holds, deletes static channels, snaps sub-frame keys to whole frames and runs the Euler filter. It works on the selected controls, the selected Graph Editor keys or the whole scene. Each pass is a single Undo. See its [usage notes](animation%20tool%20kit%20scripts/Key_Cleanup_1_0_0/README.md).
- **Stagger Keys** offsets keys across a selection in selection order, so each control of a tail, spine or finger chain starts a few frames after the one before it. It can also move everything by the same amount. See its [usage notes](animation%20tool%20kit%20scripts/Stagger_Keys_1_0_0/README.md).

Both tools also put their common actions in the toolbar button's right-click menu.

## Fixed

### Maya crashing on close

Closing Maya 2027 with the ATK toolbar loaded could still crash during shutdown, with an access violation in `shiboken6.abi3.dll`. ATK 1.1.11 fixed one cause of this, the toolbar's dock watcher, but other tools left objects behind:

- **Timeline Ticks** starts with every toolbar. It adds an overlay and an event filter to Maya's Time Slider, and Maya callbacks into Python. Its teardown used `deleteLater()`, which never runs once Maya is quitting, so they survived until Python shut down.
- **Bookmarks**, once opened, does the same with its timeline overlay.

When Maya quits, ATK now shuts down every loaded tool while Python and Qt are still running. It removes the Maya callbacks, removes the event filters from Maya's widgets, and deletes the overlays and tool windows straight away. **Reload Scripts** uses the same shutdown.

### Playblast Creator: "playblast_creator.py was not found on MAYA_PLUG_IN_PATH" at startup

Playblast Creator switched on Maya's auto-load for its plug-in. Maya stored only the file name, then looked for it at the next start before the ATK toolbar had added the plug-in's folder, so every Maya start logged this error. The toolbar now loads the plug-in from its full path when it starts, and turns Maya's own auto-load for it off. That also clears the old setting. The error can appear once more, on the first start after upgrading, until Maya saves its plug-in preferences.

### SavePlus 2.0.7

- **Version numbers were built wrongly for some file names.** A name with two numbers lost everything before the last one: `shot010_anim_v003.ma` was saved as `_anim_v004.ma`. A project-prefixed name rolling over from 9 gained a digit: `A01_anim_v009.ma` became `A01_anim_v0010.ma`. Both now increment the last number and keep the rest of the name.
- **Use Reference Path** raised an error on an unsaved scene when you accepted the suggested asset name.

### Add / Remove Frames 1.0.3

- **Remove could scramble animation.** Removing more frames than the gap in front of the next key pushed keys onto, or past, the keys before them. Remove now only removes blank frames. It stops before keys would collide and reports how many frames it removed.
- **Settings were not remembered.** Use Time Range, Frames and Spacing reset to their defaults every time the window opened.
- **Key Spacing with a highlighted Time Slider range** also re-spaced a key one frame past the highlight.
- A locked animation curve no longer makes the whole shift fail.

### AnimSnap 1.1.1 and Xform Copy Paste 2.0.1

- **Rotations were wrong between controls with different rotate orders.** The world rotation was copied as raw numbers, which only works when source and target share a rotate order. It is now converted to the target's rotate order.
- Xform Copy Paste runs an Euler filter after the multi-frame pastes (**Bake Frames** and **Keys Playback Range**), so baked rotations do not flip by 360 degrees.

### Hotkey setup (AnimSnap, Reset Tool, Xform Copy Paste)

- Assigning a new key to an action left the old key bound as well. The old key is now released.
- The key picker failed on Maya 2022–2024 (PySide2) in AnimSnap and Xform Copy Paste.

### Reset Tool 2.0.2

- A reset is now a single Undo. It used to need one Undo per channel.
- With Auto Key on, channels that are already animated are keyed at the reset value, so the reset is not lost on the next frame change.

### Micro Manipulator 1.0.1

- The window was built twice on first launch, because the module opened itself when imported.
- Pressing a scrubber with nothing selected closed an undo chunk that was never opened, which could corrupt Maya's undo queue.
- With Auto Key on, channels that are already animated are keyed when you release the scrubber.
- Works on Maya 2022–2024 (PySide2) as well.

### Wire Shape Tool 2.0.1

- **Wrap Selection in Offset Groups** worked but then reported a failure, and failed for real when a selected object was a child of another selected object.
- With several objects selected, the classic shapes created one copy per object but only named and snapped the first. Each copy is now named and snapped to its own object. With **Snap to Selection** off, a single shape is created.

### Smart Select Sets 2.5.1

- **Sets leaked between scenes.** After opening a scene with no saved sets, the previous scene's sets stayed in the window and were written into the new scene when the window closed.
- Opening and closing the window no longer adds an empty data node to a scene that has no sets.
- **Load from Scene** now reports its result.

### Noise Generator 1.1.1

- **Bake on N's** stopped with an error when the bake range covered every key of a curve that had been renamed.

### Bookmarks 0.1.1

- An import error while building the panel is now reported, instead of opening the developer test window inside Maya.

### Toolbar

- The inline frame stepper reports how many frames were actually removed.
- The About tab reads the toolbar version from the package, so it cannot fall out of date.

## Checked and left as they are

Temp Pivot, Onion Skin, Inbetweener, Tangent Tools, Character Snapshot, Mirror Controls, Blue Pencil Flipbook Manager, Overlap, Timeline Ticks, Walk Off Node, Playblast Creator, User Directory Check and the bundled TweenMachine and Studio Library were checked for import, registry and window-construction errors. No changes were needed.

## Tests

- New automated tests cover SavePlus versioning, Key Cleanup, Stagger Keys, frame removal and the clean-up when Maya quits.
- A registry check confirms that every toolbar entry points at a function that exists, that the installer copies every tool, and that no tool opens its window when imported.
- The Bookmarks test suite now runs outside Maya and is part of CI.
- CI uploads the packaged ZIP as a build artifact on every run.

None of these tests run inside Maya. Please test the tools you rely on in Maya before rolling this release out.

## Retained features

Includes everything from 1.1.14: the Overlap clean bake, the full Reload Scripts, Walk Off Node, the workspace-switch and Maya exit-crash fixes, Timeline Ticks and the Playblast Creator 2.0.5 reliability fixes.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards.
