# Animation Tool Kit 1.1.19 — Overlap 0.5.1

## New: Overlap Reset and Reload selected

**Overlap** has two new buttons next to **Load selected**:

- **Reset.** Clears the control list, removes the preview locators and endpoint, and returns every setting to its default. Start / end is set to the playback range. Keys you have already baked stay.
- **Reload selected.** Starts a fresh pass on the controls selected in Maya: the list is replaced, the previous preview is cleared and Start / end matches the playback range. Your spring settings are kept. With nothing selected, the controls already in the list are reloaded.

**Up** and **Down** are now on their own row, and the list buttons have tooltips. The user guide covers both new buttons.

## Retained features

Includes everything from 1.1.18: Noise Generator 1.2.0 (presets, inbetween bake, Pin Noise, Ease In / Ease Out, tabs), from 1.1.17 toolbar layouts (Settings → Layout), from 1.1.16 Animation Tweaker, and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards. Then click **Overlap** on the toolbar.
