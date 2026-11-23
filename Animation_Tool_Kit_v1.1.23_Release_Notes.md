# Animation Tool Kit 1.1.23 — install and start-up fix

## Fixed: Maya froze on install and the main window flashed at the next start

Dropping `install_atk_toolbar.mel` into Maya could freeze Maya. After forcing
Maya closed, the next start made the Maya main window flash on and off until
Maya was closed again.

- The toolbar's floating-window clean-up (removing the minimise and maximise
  buttons, resizing and focusing the window) could act on **Maya's main
  window** instead of the toolbar's own window. Changing the main window's
  flags hides it and shows it again, which froze Maya and, at start-up, made
  the main window flash. That clean-up now runs only on the toolbar's own
  floating window: it recognises Maya's main window reliably and does nothing
  while the toolbar is docked.
- The toolbar no longer loads the Playblast Creator plug-in or starts the
  Timeline Ticks tracker while Maya is still restoring its interface at
  start-up. Both now start a moment later, once Maya is ready.
- Automatic re-orientation of a docked toolbar waits until Maya's main window
  is shown and runs only a few times in a row, so it can never loop.
- The drag-and-drop installer copies the files during the drop, then opens the
  toolbar and the "Installed Successfully" message once Maya is idle, instead
  of inside the drop itself.

## If Maya still shows the problem from an earlier version

Install 1.1.23 by dragging `install_atk_toolbar.mel` into Maya. If an earlier
version left Maya flashing at start-up, close Maya, start it once more and
then install 1.1.23. Nothing else needs to be reset.

## Retained features

Includes everything from 1.1.22: Animation Tweaker 1.2.1 weight sliders that
follow the frame; from 1.1.21 the brush **Size** and **Strength** sliders; from
1.1.20 quick tangent buttons that change only the targeted keys and the Playblast
Creator 2.0.6 FFmpeg 9.1 fix; from 1.1.19 Overlap 0.5.1, from 1.1.18 Noise
Generator 1.2.0, from 1.1.17 toolbar layouts (Settings → Layout), from 1.1.16
Animation Tweaker, and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup,
Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload
Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed,
**Settings → Reload Scripts** is enough afterwards.
