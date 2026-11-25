# Animation Tool Kit 1.1.31 — Smart Select Sets pop-outs and button order

Smart Select Sets is now version 2.6.0.

## Pop-outs stay open when the main window closes

Closing the main Smart Select Sets window no longer closes its pop-out pickers.
The pop-outs keep selecting, and their right-click menus keep working. Click
**Selection Set** on the toolbar again to bring the main window back with the
same sets. Once the main window is closed and the last pop-out is closed, the
tool shuts down and saves the sets to the scene as before.

## Pop-outs stay in front of Maya only

Pop-outs were set to stay on top of every window on the desktop, so they
covered a browser or any other application you switched to. They now stay in
front of Maya's windows and go behind other applications together with Maya.

## Drag buttons into a new position

Drag a button onto another button to move it there: drop on the right half of
a button to place it after that button, or on the left half to place it
before. This works inside a category, across categories and in pop-outs.
Dropping a button on the free space of another category still moves it to that
category, now at the end. The order is saved with the scene and in exported
JSON files. Sets saved by earlier versions keep their alphabetical order until
you move them. New sets are added at the end of their category, and a
duplicated set appears right after the original.

## Fixed: a deleted category name could not be created again

A category could stay in the saved data without a box on screen, for example
after Load or reopening the scene brought back an empty category that had been
deleted. Creating a category with that name then failed with "already exists".
**New Category** now shows that category again instead.

## Fixed: the Rename button on a category did nothing

The **Rename** button on a category box raised an error and did nothing. It now
renames the category (for Uncategorized it changes the label shown).

## Retained features

Includes everything from 1.1.30: the TweenMachine fix (it opens again under
Maya's Python 3), and from 1.1.29 Reload Scripts reopening floating tool
windows, the Batch Rename fix, Wire Shapes Joint Mode, and all earlier tools and
fixes.
