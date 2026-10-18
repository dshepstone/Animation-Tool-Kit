# Timeline Ticks 1.0.0

A compact Maya tool with coloured tick overlays and K / E / B / I
labels directly on the Time Slider. Supports PySide2 and PySide6 (Maya 2022+).

## Install and launch

Run the repository's `install_atk_toolbar.mel` installer. The three-strip colour
palette appears in ATK's timing tools. Click its arrow and choose **Open Timeline
Ticks** for the full window. For standalone use, copy `timeline_ticks.py` and
`timeline_ticks_tracking.py` to your Maya user scripts directory and run:

```python
import timeline_ticks
timeline_ticks.show()
```

## Use

The main ATK toolbar uses **one standard icon slot** with three stacked colour
strips: yellow, red and blue, plus a narrow menu arrow. Click a strip to colour
existing keys in the highlighted
Time Slider range, or at the current frame when there is no highlighted range.
The floating window does not need to be open. Click the arrow or right-click any
colour strip for the same three colours, all four classifications, Clear, and
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
6. **Clear All Marks** removes every annotation in the scene, including marks on
   unselected controls and outside the visible range. Keyframes and native
   breakdown flags stay unchanged. Ctrl+Z restores the removed annotations.
7. Uncheck **Show coloured marks** to hide the overlay without removing data or
   stopping key tracking. Recheck it to show the latest key positions. The palette
   menu also provides **Hide Coloured Marks**, **Show Coloured Marks** and
   **Clear All Marks**. Visibility is a session display setting.

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
  unchanged. Closing the window removes the overlay and stops its drawing timer;
  key tracking continues until the tool service is shut down or Maya closes.
- The tracking service starts when ATK builds its toolbar or when the standalone
  tool opens. It follows exact Maya keyframe edit callbacks on all annotated
  curves, including unselected controls and animation layers. Dragging keys,
  relative shifts, scaling, subframe moves and ATK Add/Remove Frames move labels
  with those keys. Value/tangent edits leave their labels unchanged.
- Deleting a key removes its stored annotation; deleting its animation curve
  removes all of that curve's annotations. Undo/Redo restores/removes labels
  alongside the keys, without adding an extra undo step. A new key created at
  a deleted key's old time does not inherit the deleted label. Copies/pastes
  create unlabelled new keys rather than copying classifications.
- Keep tracking active when editing annotated scenes. Editing while ATK/the
  standalone service has never been started, or with a custom tool that bypasses
  Maya's key edit callbacks, cannot be tracked. Old labels already stranded by
  earlier versions cannot be reassociated automatically. Run
  `timeline_ticks.start_tracking()` to enable tracking without a window, or
  `timeline_ticks.shutdown()` to remove all callbacks and the window.
- Annotation times are stored in seconds, independent of displayed frame rate.
  Pending key edits are synchronized before scene save. Callback registration
  and deleted-key undo history are session-only; no executable scene scripts are
  saved. Reloading scripts or reinstalling stops old callbacks before starting
  a new service.
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
`tests/check_timeline_ticks_tracking_maya.py` checks real move, delete, Undo/Redo,
group shifts, reverse scaling, subframes, whole-curve deletion, actual ATK
Add/Remove Frames shifts, saving before idle and continued tracking after load.
