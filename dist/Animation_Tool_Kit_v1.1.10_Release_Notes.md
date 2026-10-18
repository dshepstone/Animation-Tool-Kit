# Animation Tool Kit 1.1.10 — Timeline Ticks

## New: Timeline Ticks

- One standard toolbar slot provides directly clickable yellow, red and blue strips plus a menu arrow.
- Classify existing keys as Key, Extreme, Breakdown or Inbetween; Breakdown uses Maya's native flag.
- Coloured marks align with native tick positions and persist as plain scene metadata, without executable scene scripts.
- Active tracking follows key moves, scaling, subframes, deletion and curve deletion, including actual ATK Add/Remove Frames and ranged ripple edits.
- Undo/Redo restores marks with key edits without extra undo steps. Pending changes flush before saving.
- Clear All Marks clears annotations across the scene in one undoable operation, including unselected controls and out-of-range marks.
- Hide/Show Coloured Marks changes visibility while tracking continues.
- Tracking starts with ATK independently of the floating window. Reloading or reinstalling removes old callbacks. Both tool modules are included in the installer and package; PySide2 and PySide6 are supported.

## Retained improvements

Includes the updated ATK website logo button and Playblast Creator 2.0.5 reliability fixes: hardware H.264 software fallback, protected video replacement, explicit overwrite controls and portable capture paths.

## Usage and limitations

Install by extracting `AnimationToolKit_v1_1_10.zip` and dragging `install_atk_toolbar.mel` into Maya. See the Timeline Ticks README for scope controls and full usage.

Tracking must be running during key edits. Edits before startup and custom code bypassing Maya key-edit callbacks cannot be reconstructed. Copied keys are unlabelled. Earlier stranded annotations need manual correction. Interactive Time Slider, drag and workspace verification remains a limitation, particularly for custom Time Slider replacements.

## Validation

The feature handoff records 27 passing unit tests, real Maya 2027 tracking checks and Maya 2026 persistence/offscreen Qt checks. Cloud release checks rerun the unit tests and cross-platform Playblast verification and validate the portable ZIP. Live Maya is unavailable in the cloud; the prior Maya results are not a new cloud validation.
