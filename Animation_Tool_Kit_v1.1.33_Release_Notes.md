# Animation Tool Kit 1.1.33 — Temp Pivot failure report and fixes

Temp Pivot is now version 1.0.6.

## New: a report when a temp pivot cannot be made

Before, if a control could not take a temp pivot, nothing visible happened:
the reason only went to the Output Log, which is folded away, or to the
Script Editor. Now a pop-up lists every reason, with what to do about it.
The same report is printed in the Script Editor so it can be copied, and a
short warning appears on Maya's command line.

The report covers:

- nothing selected, or a selection that is not a control (a material, a set,
  or one of the Temp Pivot's own nodes)
- a control that already has a temp pivot rig
- a control already driven by another constraint (it is named in the report)
- a control whose translate and rotate channels are all locked, or all
  driven by an expression, set driven key or other connection
- a control with zero scale, whose orientation cannot be read
- any unexpected Maya error, with the partly built nodes removed

The same report appears if **Complete Setup** or **Toggle** fails.

## Fixed

- **Joints were refused.** Joint-based controls (FK chains) were treated as
  "not a transform" and skipped without a message. They now work.
- **Partly locked controls broke the setup.** A control with, say, locked
  translates made the constraint fail halfway, leaving stray nodes. The
  constraint now skips the channels it cannot drive, and the log says which.
- **Half-built rigs.** If Complete Setup failed partway, the pivot null was
  left inside a new group with no rig. Everything is now put back so you can
  fix the cause and click Complete Setup again.
- **Two characters with the same control names.** Rigs were named without
  the namespace, so building a pivot on `charB:hand_ctrl` deleted the
  constraint of the pivot on `charA:hand_ctrl`. Rig names now include the
  namespace and are always unique, each rig node records which rig it
  belongs to, and the Active Pivot Rigs list picks rigs by their pivot null.
- **Twisted pivots on rotate orders other than xyz.** The pivot null now
  copies the control's rotate order before matching its rotation.
- **Pivot offset after moving the pivot.** Leftover rotate/scale pivot
  translate values are cleared when the pivot is frozen, so the control
  rotates around exactly the point you picked.
- **Controls with "TMP" in their name were ignored.** Only the tool's own
  nodes are skipped now.
- **Component selections** (CVs, vertices) now count as selecting their
  control.
- **Auto-key after reopening a scene.** A rig saved while ON stopped
  auto-keying after the scene was reopened; opening the tool re-arms it.
- **Rigs inside namespaces** (for example in an imported shot) are found by
  the tool.
- A constraint on a control only counts as "existing" when it really drives
  that control, not when it is merely parented under it.

## Retained features

Includes everything from 1.1.32: the Smart Select Sets pop-out close button,
and all earlier tools and fixes.
