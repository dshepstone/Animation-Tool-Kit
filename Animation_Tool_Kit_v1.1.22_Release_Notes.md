# Animation Tool Kit 1.1.22 — Animation Tweaker weight sliders follow the frame

## Fixed: tweak weight sliders follow the timeline again

In **Animation Tweaker**, the weight slider of a keyed tweak (for example one keyed with **Key 0** and **Key 1**) should show the keyed value on every frame. After the window was closed and opened again, the sliders stopped updating when the frame changed, even though the keys themselves were right.

- The window now picks up frame changes again whenever it is shown or reopened, and catches up with the current frame straight away.
- On a frame change, keyed weights are read from their keys on that frame. A weight you have dragged but not keyed still shows your value until the frame changes.

Animation Tweaker is now 1.2.1.

## Retained features

Includes everything from 1.1.21: Animation Tweaker brush **Size** and **Strength** sliders; from 1.1.20 quick tangent buttons that change only the targeted keys and the Playblast Creator 2.0.6 FFmpeg 9.1 fix; from 1.1.19 Overlap 0.5.1 (Reset and Reload selected), from 1.1.18 Noise Generator 1.2.0, from 1.1.17 toolbar layouts (Settings → Layout), from 1.1.16 Animation Tweaker, and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards.
