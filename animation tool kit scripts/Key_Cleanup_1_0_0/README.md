# Key Cleanup 1.0.0

Tidies animation curves before polish or hand-off. It works on the selected controls, on the keys selected in the Graph Editor, or on the whole scene.

## Use

1. Launch **Key Cleanup** from the ATK toolbar's timing group.
2. Choose the scope: **Selected** or **Whole scene**.
3. Optionally limit the frame range to the playback range or the shift-dragged Time Slider range.
4. Click a pass, or **Run All Passes**.

Each button is a single Undo. The four passes are also in the toolbar button's right-click menu, where they run on the selection with the default settings.

## Passes

| Pass | What it does |
|---|---|
| Remove Redundant Keys | Deletes keys that sit inside a flat hold. The first and last key of each hold stay, so timing does not change. A key is only removed when both curve segments it touches are flat, including the tangents of the keys on either side. |
| Delete Static Channels | Deletes curves that never change value: every key holds the same value and every tangent is flat. Equal keys joined by sloped tangents still move, so those curves are kept. The attribute keeps its value. Referenced curves are left alone. |
| Snap Keys to Whole Frames | Moves sub-frame keys, left by retiming or scaling, onto whole frames. |
| Euler Filter | Removes 360-degree flips on the rotate channels, one object at a time. |

**Value tolerance** sets how close two key values must be to count as the same. The default is 0.001.

## Scripting

```python
import key_cleanup
key_cleanup.remove_redundant_keys()            # selection, all keys
key_cleanup.delete_static_channels("scene")    # whole scene
key_cleanup.clean_all("selected", time_range=(1, 48))
```

## Limits

- Only time-based curves are touched. Set-driven-key curves belong to the rig and are skipped.
- Locked curves are skipped.
- The frame range applies to Remove Redundant Keys and Snap Keys. Delete Static Channels and Euler Filter always look at the whole curve.
