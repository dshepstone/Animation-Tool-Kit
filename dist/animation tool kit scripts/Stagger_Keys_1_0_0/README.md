# Stagger Keys 1.0.0

Offsets animation in time across a selection. Select the controls of a tail, spine or finger chain in order and each one starts a few frames after the one before it, which is a quick way to block in overlap.

## Use

1. Select the controls in the order they should move.
2. Launch **Stagger Keys** from the ATK toolbar's timing group.
3. Choose a mode and a frame amount.
4. Click **Later** or **Earlier**. Each click is a single Undo; click again to add more offset.

The common amounts are also in the toolbar button's right-click menu.

## Modes

| Mode | Result |
|---|---|
| Stagger by selection order | The first selected control keeps its timing. The second moves by the frame amount, the third by twice that, and so on. |
| Offset all the same amount | Every selected control moves by the frame amount. |

**Reverse order** makes the last selected control the one that stays put.

If keys are selected in the Graph Editor, only those keys move. Otherwise every key on the selected controls moves.

## Scripting

```python
import stagger_keys
stagger_keys.stagger(2)        # 0, +2, +4, ... by selection order
stagger_keys.offset_all(-1)    # everything 1 frame earlier
```

## Limits

- Locked curves are skipped.
- Whole-frame offsets only.
