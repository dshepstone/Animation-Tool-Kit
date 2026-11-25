# Animation Tool Kit 1.1.34 — Mirror Pose

New tool: **Mirror Pose** 1.0.0, on the toolbar in the rigging group.

## New: mirror a whole pose in one click

Select any control on a character and click **Mirror Pose**. The pose turns
into its mirror image:

- left and right controls swap their poses (arms, legs, hands, fingers, IK
  and FK controls, pole vectors), including custom attributes such as finger
  curls, foot roll and IK/FK switches
- centre controls (COG, pelvis, spine, chest, neck, head, jaw) flip across the
  character, so a body that turns, leans or shifts to the left now does it to
  the right
- one-sided parts with no partner (a hair strand or prop only on one side)
  flip in place, the same way as centre controls
- controls that place the character in the shot (world, global, main,
  placement...) stay where they are, so the character mirrors in place
  instead of jumping across the scene

A run or walk pose becomes the opposite step. Click again to get the original
pose back, or press Ctrl+Z.

Right-click the button for **Mirror Selected Controls Only**: the selected
controls swap with their partners (and selected centre controls flip), and the
rest of the character is left alone.

### Works on most rigs without set-up

Mirror Pose reads each control's real frame at the rig's rest pose (parent
space, joint orient, rotate axis, rotate order) and mirrors through those
frames, so it gets the signs right on rigs whose two sides are built
differently and on rigs built facing along X. The mirror plane comes from the
rig's own left/right pairs.

Left/right partners are found from common names (lf/rt, lt/rt, l/r,
left/right, lft/rgt, L_/R_, _L/_R, armLeft/armRight). If the rig has a
**Character Snapshot**, Mirror Pose uses its manual pairs, exclusions and rest
pose.

### Never fails silently

A pop-up explains anything that stops the mirror: nothing selected, no rig
controls in the selection, no left/right pairs found, or an unexpected Maya
error. The Script Editor lists the details of every run: where the pairs
came from, the one-sided controls flipped in place, and any locked or driven
channels that were left as they were.

With auto-key on, channels that already have keys are keyed on the current
frame.

## Retained features

Includes everything from 1.1.33: the Temp Pivot failure report and fixes, and
all earlier tools and fixes.
