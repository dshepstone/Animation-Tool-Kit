# Animation Tool Kit 1.1.24 — Wire Shapes Joint Mode, toolbar docking fix

## New: Wire Shapes 2.1.0 Joint Mode

Tick **Joint Mode** in the Wire Shapes window, select joints and click any
shape to build it as a control on the joints.

- Each control sits on its joint's pivot with the joint's rotation axes and
  rotate order, so rotating the control X turns the joint about the same X.
- **Shape faces: Down the chain (auto)** reads each joint's orientation and
  turns the shape to face the axis that points at the next joint, so circles
  ring the bone. You can also pick a joint axis, or keep the shape as built.
  Works with every shape.
- **Single Joint** builds one control on each selected joint. **Multi-Joint
  Chain** builds a control on every joint below the selection, or from a start
  joint to an end joint, with optional **Skip end joints** and **FK
  hierarchy**.
- **Name** pattern: `#` is the number (`##` pads to 01) and `{joint}` is the
  joint's name, with a start number and a live preview. `FlagPole_#_CTRL`
  gives `FlagPole_1_CTRL`, `FlagPole_2_CTRL`, ...
- **Size** as a multiple of the joint radius or bone length, or in units.
- Optional **Zero group** (`<control>_GRP`) so channels start at zero, and an
  optional **Orient** or **Parent** constraint from each control to its joint.
- One click is one undo step.

## Fixed: toolbar docked under the Help Line instead of above the timeline

If Maya's Time Slider was hidden, the toolbar had nothing to dock against and
fell back to the very bottom of the Maya window, under the Help Line. When the
toolbar is set to dock above the timeline it now shows the Time Slider again
(Windows > UI Elements > Time Slider) and docks above it. If the Time Slider
still cannot be found it docks above the Range Slider rather than at the
bottom of the window.

## Retained features

Includes everything from 1.1.23: the install freeze and start-up flashing
fixes; from 1.1.22 Animation Tweaker 1.2.1 weight sliders that follow the
frame; from 1.1.21 the brush **Size** and **Strength** sliders; and all
earlier tools and fixes.
