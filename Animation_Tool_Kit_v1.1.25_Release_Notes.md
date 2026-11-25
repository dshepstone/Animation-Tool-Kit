# Animation Tool Kit 1.1.25 — Reload Scripts no longer deletes the Time Slider

## Fixed: the Time Slider went blank after Reload Scripts

**Settings → Reload Scripts** could delete Maya's Time Slider, leaving an
empty strip above the Range Slider. The toolbar then had nothing to dock
against and moved to the bottom of the Maya window.

- Reload Scripts closes every open tool window before reloading. Timeline
  Ticks and Bookmarks draw their markers as overlays on the Time Slider
  itself, and Reload Scripts treated those overlays as tool windows: it went
  looking for the dock around them and deleted Maya's slider widget
  (`timeControl1`) instead. Reload Scripts now recognises widgets drawn on
  Maya's own UI and leaves them to the tools' own shut-down, never deletes
  one of Maya's UI elements (Time Slider, Range Slider, Shelf, Channel Box
  and the rest), and only deletes a dock that really is a tool's workspace
  control. Docked tool windows still close and reopen as before.
- If the Time Slider strip is already empty when the toolbar starts, the
  toolbar now warns in the Script Editor. Restart Maya to rebuild it.

## If your Time Slider is already blank

Restart Maya: it always rebuilds the Time Slider at start-up. Then install
1.1.25 by dragging `install_atk_toolbar.mel` into Maya.

## Retained features

Includes everything from 1.1.24: **Wire Shapes** 2.1.0 **Joint Mode** and the
toolbar docking above a hidden Time Slider; from 1.1.23 the install freeze and
start-up flashing fixes; and all earlier tools and fixes.
