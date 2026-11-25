# Animation Tool Kit 1.1.27 — Wire Shapes 2.3.0: per-controller size, list follows the selection

## New: a size for each controller

The Joint Mode per-joint list (Multi-Joint → **Per-joint shapes...**) has a
**Size** column. Each row's size is read like the Size field above it
(x Radius, x Bone or units).

- Rows you have not changed follow the Size field.
- With several rows selected, changing one row's size sets them all.
- **All: Size** sets every row back to the Size field.

## Changed: the list loads your selection

- Opening **Per-joint shapes...** loads the joints you have selected
  straight away, using the Chain options. You no longer need to click Load
  first.
- While you have not edited it, the list follows the selection: select
  another chain and the list updates.
- Once you change a shape or size, the list stays as it is.
  **Load Selection** reloads it from the selection and keeps the shape and
  size you gave each joint that is still in it. **Clear** empties it and it
  follows the selection again.
- The window releases its selection callback when it closes, before Reload
  Scripts and when Maya quits.

## Retained features

Includes everything from 1.1.26: FK parent-constraint chains, Drive joints
constraints, Best Option, a shape per joint and the Batch Rename tab; from
1.1.25 the fix that stops Reload Scripts deleting Maya's Time Slider; and all
earlier tools and fixes.
