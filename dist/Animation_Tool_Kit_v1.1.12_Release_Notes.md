# Animation Tool Kit 1.1.12 — Workspace Switch Crash Fix

## Fixed: Maya locking up and crashing after switching workspaces

- In 1.1.11, switching Maya workspaces and then relaunching the toolbar from the **ATK** shelf button could freeze Maya and then crash it.
- Cause: the 1.1.11 exit-crash fix kept a Python wrapper of Maya's toolbar workspaceControl widget in a module global, so the watcher could be detached from it later. When you switch workspaces, Maya deletes that widget itself. shiboken can't tell when Maya deletes a widget that Maya owns, so the stored wrapper kept pointing at freed memory and still reported itself as valid. On the next launch the toolbar called `removeEventFilter` on that dead widget, which locked up Maya and then crashed it.
- Fix: the toolbar no longer stores any wrapper of a Maya-owned widget. It looks the workspaceControl up fresh through Maya whenever it needs it, on rebuild and at shutdown. Qt already drops the event filter by itself when Maya deletes the old control.
- The 1.1.11 exit-crash fix is kept. The `quitApplication` cleanup still stops and deletes the dock watcher while Python and Qt are both still running.

## Retained features

Includes everything from 1.1.11 and 1.1.10: the Maya exit-crash fix, Timeline Ticks, the ATK website logo button and the Playblast Creator 2.0.5 reliability fixes.

## Usage

Install by extracting `AnimationToolKit_v1_1_12.zip` and dragging `install_atk_toolbar.mel` into Maya. **Restart Maya after upgrading** so the patched toolbar module is loaded.

## Validation

Cloud release checks rerun the unit tests and the cross-platform Playblast checks, and validate the portable ZIP. Live Maya isn't available in the cloud, so the fix still needs a workstation check: switch workspaces a few times, relaunch from the ATK shelf button, then close Maya.
