# Timeline Ticks 1.0.0

A compact two-row Maya tool with coloured tick overlays and K / E / B / I
labels directly on the Time Slider. Supports PySide2 and PySide6 (Maya 2022+).

## Install and launch

Run the repository's `install_atk_toolbar.mel` installer, then click **Timeline
Ticks** in ATK's timing tools. For standalone use, copy `timeline_ticks.py` to
your Maya user scripts directory and run this Python shelf command:

```python
import timeline_ticks
timeline_ticks.show()
```

## Use

The main ATK toolbar has **three colour buttons: yellow, red and blue**, beside
the Timeline Ticks launcher. Click one to colour existing keys in the highlighted
Time Slider range, or at the current frame when there is no highlighted range.
The floating window does not need to be open. Right-click the launcher or any
colour button for the same three colours, all four classifications, Clear, and
the option to open the full tool. These quick actions always use the highlighted
range/current frame; use the full tool for Graph Editor selected-key scope.

1. Select animated controls so their keys appear on the Time Slider.
2. Choose **Current frame**, **Highlighted range** (Shift-drag the Time Slider),
   or **Selected keys** (Graph Editor selections on curves shown in the Time Slider).
3. Click a type: **Key** (red), **Extreme** (yellow), **Breakdown** (blue),
   or **Inbetween** (green).
4. Click a yellow, red, blue or green swatch to override the colour while keeping
   the label. Unlabelled keys receive the Key label.
5. **Clear** removes annotations in that scope. Ctrl+Z undoes an edit.

Only existing keys on the Time Slider's displayed curves are affected. No
keys or poses are created. Breakdown sets Maya's actual native breakdown flag;
the other type buttons clear it. Swatches and Clear preserve native breakdown
state. Extreme and Inbetween are annotations rather than additional Maya key types.

## Persistence and limits

- Annotations save in a plain network node in the scene. Save the scene after
  editing. Reopen the bar after loading a scene to display its annotations.
- Colours use a transparent, mouse-pass-through overlay.
  Quick toolbar actions also activate the overlay without opening the floating
  bar. Scrubbing and selecting remain available. Maya's global tick preferences are
  unchanged. Closing the bar removes the overlay and stops its refresh timer.
- Annotations attach to a curve UUID and an absolute time, stored in seconds so
  changing the scene frame rate keeps the same key identity. They **do not follow
  retimed keys or copy/paste**. Relabel after retiming. Annotations only display
  when a key exists at their stored time; a replacement key at that time inherits
  the old label until cleared.
- Colours align with the native key tick at the start of its frame cell, with
  the standard Time Slider's end gutters accounted for. If channels at one
  time have different annotations, vertical colour segments on that same tick
  and a **+** indicate the mixed classification.
- Referenced/locked curves may reject native breakdown changes. Maya reports
  the error in the Script Editor; Undo can reverse any partial edit.
- Importing multiple scenes with annotation stores requires manually resolving
  duplicate stores; the tool refuses to guess which store to overwrite.
- Overlay alignment and coexistence with custom Maya Time Slider replacements
  require visual checking in your Maya version. Custom slider replacements
  may use different end gutters.

## Validation

`tests/test_timeline_ticks.py` covers scope, scene persistence, undo chunks,
classification and curve isolation using a simulated Maya command surface.
`tests/check_timeline_ticks_maya.py` exercises actual Maya animation curves,
scene save/reopen, undo/redo and Qt rendering under mayapy with only the missing
interactive Time Slider query substituted. Live Time Slider alignment still
needs an interactive Maya session.
