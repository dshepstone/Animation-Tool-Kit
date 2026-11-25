# Animation Tool Kit 1.1.29 — Reload Scripts and Batch Rename fixes

## Fixed: Reload Scripts left floating tool windows on the old code

Since 1.1.25, Reload Scripts treated a floating tool window parented to Maya's
main window (Tangent Tools, for example) as part of Maya's own interface. It
neither closed nor reopened that window, so the window kept running the old
code. Reload Scripts now recognises a tool's own floating window and closes and
reopens it as before. It still leaves Maya's Time Slider and the overlays drawn
on it alone.

## Fixed: Batch Rename with a child selected before its parent

In **Wire Shapes** 2.3.2, renaming a selection where a child comes before its
parent renamed everything correctly but then raised an error while selecting
the result. Batch Rename now selects the renamed objects at their new names.

## Retained features

Includes everything from 1.1.28: Wire Shapes Joint Mode, FK parent-constraint
chains, Best Option, per-joint shapes and sizes, Batch Rename, and shapes that
align to the selection's pivot and orientation; the Time Slider fixes from
1.1.24–1.1.25; and all earlier tools and fixes.
