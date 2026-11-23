# Animation Tool Kit 1.1.20 — Tangent button fix

## Fixed: quick tangent buttons change only the keys you mean

The **Auto Spline (Legacy)**, **Linear** and **Stepped** buttons beside **Tangent Tools** (and the same buttons in the Tangent Tools window) used to change every key on the selected objects unless keys were selected in the Graph Editor. They now pick their keys in this order:

1. **Highlighted Time Slider range** (shift-drag): only the keys inside the range.
2. **Keys selected in the Graph Editor** or Dope Sheet: only those keys.
3. **Nothing highlighted or selected**: only the key on the current frame, in the Time Slider or the Graph Editor.

Channels highlighted in the Channel Box narrow the timeline cases to those channels. Each click is one undo step. If there is no key on the current frame, nothing changes and Maya shows a warning. Stepped still sets only the out tangent.

Tangent Tools is now 1.0.1.

## Retained features

Includes everything from 1.1.19: Overlap 0.5.1 (Reset and Reload selected), from 1.1.18 Noise Generator 1.2.0 (presets, inbetween bake, Pin Noise, Ease In / Ease Out, tabs), from 1.1.17 toolbar layouts (Settings → Layout), from 1.1.16 Animation Tweaker, and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards. Then select a keyed control and click a tangent button on the toolbar.
