# Animation Tool Kit 1.1.26 — Wire Shapes 2.2.0: FK constraint chains, Best Option, Batch Rename

## Changed: clearer chain and constraint options in Joint Mode

- **Link controls** (Multi-Joint) replaces the "FK hierarchy" tick box:
  - **Parent-constraint chain (FK)** — the new default. Every `<control>_GRP`
    stays flat in the outliner and is parent-constrained to the control
    above it.
  - **Nested hierarchy (FK)** — each group is parented under the control
    above, as before.
  - **Not linked** — independent controls.
- **Drive joints** (was "Constrain") lists real constraints only — Parent
  constraint, Orient constraint, Point + Orient — from each control to its
  joint. Nothing is parented, and joints stay where they are in the outliner.
- A joint that already has that constraint is skipped with a warning instead
  of getting a second target, which would blend the old and new controls when
  you rebuild. Names already used in the scene are reported too.
- Control shapes are renamed to match their control (`Sign_CTRL_1Shape`).

## New: Best Option

In Joint Mode a **Best for Joints** section sits above the shapes. **Best
Option** picks the shape for each joint from its name: root/world → Root,
COG/pelvis/hips → Circle 4-Arrow, head/chest → Cube, eye → Sphere,
jaw/clavicle/toe → Half Circle, hand → Square, `_end`/`_tip` joints →
Diamond 3D, and an FK ring around the bone for every other joint. Next to it
are the shapes that suit joint controls best.

## New: a different shape per joint

In Multi-Joint mode click **Per-joint shapes...**, select the chain and click
**Load Joints from Selection**. Each joint gets a row with its control name:
choose its shape from the row's list (each defaults to its Best Option), or
select rows and click any shape button to assign it. **Build Controls** builds
the whole chain in one undo step.

## New: Batch Rename tab

Rename the selection in selection order from a pattern such as
`FlagPole_#_JNT` (`#` numbers, `##` pads to 01, `{name}` keeps the current
name) with a start number and step. **Include children (same type)** renames
a whole joint chain from its root joint and leaves constraints alone. Also
**Search and Replace** and **Prefix / Suffix**. Each click is one undo step.

## Retained features

Includes everything from 1.1.25: Reload Scripts no longer deletes Maya's Time
Slider; from 1.1.24 Wire Shapes Joint Mode and docking above a hidden Time
Slider; from 1.1.23 the install freeze and start-up flashing fixes; and all
earlier tools and fixes.
