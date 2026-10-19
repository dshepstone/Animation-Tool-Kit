# Animation Tool Kit 1.1.11 — Exit Crash Fix

## Fixed: Maya crashing on close

- Closing Maya with the ATK toolbar loaded could crash during shutdown with an access violation in `shiboken6.abi3.dll`. This was seen in both Maya 2026 and Maya 2027.1, after Maya had already logged a normal exit.
- Cause: the toolbar's dock watcher was an unparented, Python-owned Qt event filter installed on Maya's workspaceControl widget. It stayed alive until the Python interpreter finalized, and shiboken then tried to destroy it after Qt and Maya had started tearing down their widgets.
- Fix: a single `quitApplication` scriptJob now removes the event filter and deletes the watcher while Python and Qt are still fully alive. Python references to the toolbar widget and release animation are dropped at the same time. The job is registered once and is not duplicated by reloading or reinstalling the toolbar.
- Rebuilding the toolbar now detaches the watcher from its previous widget and recreates it if Maya has already deleted it.

## Retained features

Includes everything from 1.1.10: Timeline Ticks, the updated ATK website logo button and the Playblast Creator 2.0.5 reliability fixes.

## Usage

Install by extracting `AnimationToolKit_v1_1_11.zip` and dragging `install_atk_toolbar.mel` into Maya. Restart Maya after upgrading so the patched toolbar module is loaded.

## Validation

The fix was identified from three Windows crash dumps (Maya 2026 and 2027.1), all faulting in shiboken's exit-time cleanup. Cloud release checks rerun the unit tests and cross-platform Playblast verification and validate the portable ZIP. Live Maya is unavailable in the cloud, so the exit-crash fix still needs a real Maya open/close check.
