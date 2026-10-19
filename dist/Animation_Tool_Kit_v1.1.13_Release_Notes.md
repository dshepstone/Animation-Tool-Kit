# Animation Tool Kit 1.1.13 — Walk Off Node

## New: Walk Off Node

Turns a treadmill walk cycle into a walk that travels through the scene.

In a typical cycle setup the IK feet, IK hands and waist / COG loop in place with cycle infinity, while the base or layout node at the top of the rig slides forward to carry the character. Walk Off Node:

1. Samples each chosen control's world-space position and rotation on every frame of the range, with the cycle and the slide both playing.
2. Bakes keyed custom attributes (foot roll, toe tap and so on) across the range, so they keep animating once the cycle is removed.
3. Removes the base node's slide. By default the base holds its first-frame pose. You can choose **Reset to origin** instead.
4. Keys the sampled world path back onto the controls, sets their infinity to constant and runs an Euler filter.

The feet plant, and the character walks off the node. The whole operation is a single Undo.

Find it in the toolbar's **timing** group. The range can be the playback range or a shift-dragged Time Slider range, and it can be longer than one cycle. Controls are processed parent-first, and locked axes are left alone.

## Xform Copy Paste: walk-cycle guidance

Xform Copy Paste has a new **Walk Cycle** section with a **Walk Off Node...** button, and its Help covers the workflow. It also explains why *Copy Multi + Paste Keys* alone can't do this job: the paste only overwrites keys that already exist, and a cycle has none past its first loop.

## Retained features

Includes everything from 1.1.12: the workspace-switch lockup/crash fix, the Maya exit-crash fix, Timeline Ticks, the ATK website logo button and the Playblast Creator 2.0.5 reliability fixes.

## Usage

Install by extracting `AnimationToolKit_v1_1_13.zip` and dragging `install_atk_toolbar.mel` into Maya. **Restart Maya after upgrading.**

## Validation

Tested in Maya on a walk cycle before release. Cloud release checks run the unit tests, including a simulated-scene test for Walk Off Node, plus the cross-platform Playblast checks, and validate the portable ZIP.
