# Animation Tool Kit 1.1.28 — Wire Shapes 2.3.1: shapes align to the selection

## Fixed: Snap to Selection outside Joint Mode

Shapes built with **Snap to Selection** now line up with what is selected.
With nothing selected they are still built at 0,0,0.

- **Orientation:** a new **Match Rotation** option (on by default) turns
  the new control to the selected object's world orientation: rotation,
  joint orient, rotate axis and every parent included. The control also
  takes the object's rotate order. Scale, shear and mirroring (negative
  scale, as on right-side rig controls) are not copied, so the control keeps
  scale 1 and a clean orientation. Turn it off for position only.
- **Pivot:** the control is placed on the object's rotate pivot, so a wrist
  control whose pivot was moved gets its new shape on that pivot. The shape
  keeps its own pivot at its origin. Before, the pivot was re-centred on the
  shape, which moved it off the target for offset shapes such as Lollipop,
  Flag, Paddle, Half Circle and Pyramid.
- **Components:** selecting vertices, edges, faces or CVs builds one
  control at their centre, oriented like their object. Before, the control
  stayed at the origin. A selected shape node counts as its transform.
- **Several objects:** every shape now builds one control per selected
  object. Before, only the classic shapes did; the others made a single
  control on the last object.
- The Offset Dummy uses the same alignment, and each click is one undo step.

Joint Mode uses the same clean orientation for its controls and groups.

## Retained features

Includes everything from 1.1.27: the Joint Mode per-joint list with a size
per controller that loads the selection; from 1.1.26 FK parent-constraint
chains, Best Option, a shape per joint and Batch Rename; from 1.1.25 the fix
that stops Reload Scripts deleting Maya's Time Slider; and all earlier tools
and fixes.
