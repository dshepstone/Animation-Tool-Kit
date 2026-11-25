# Animation Tool Kit 1.1.30 — Tween Machine opens again

## Fixed: Tween Machine would not open

Clicking **TweenMachine** on the toolbar printed
`ATK Toolbar: error launching 'tween_machine': setAttr: Error reading data
element number 1` and no window appeared. tweenMachine saves its settings to a
`tweenMachineData` node in the scene, and under Maya's Python 3 it handed
`setAttr` raw bytes instead of text, which Maya refuses. It now stores the data
as text, so the window opens.

The same fix also covers three smaller problems in the bundled tweenMachine:

- A `tweenMachineData` node left behind by the failed launch (or made by hand)
  without its `data` attribute is repaired instead of causing a second error.
- Scenes carrying data from an older tweenMachine (`tmXML` node) read it
  correctly instead of failing.
- tweenMachine falls back to the standard XML module on Python versions that
  no longer include `cElementTree`.

## Retained features

Includes everything from 1.1.29: Reload Scripts reopening floating tool
windows, the Wire Shapes Batch Rename fix, Wire Shapes Joint Mode, the Time
Slider fixes from 1.1.24–1.1.25, and all earlier tools and fixes.
