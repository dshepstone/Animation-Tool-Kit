# Animation Tool Kit 1.1.21 — Animation Tweaker brush sliders

## New: brush Size and Strength sliders in Animation Tweaker

The **Sculpt** tab of **Animation Tweaker** now has **Size** and **Strength** sliders under the sculpt brushes, so you can set the current brush's radius and how strongly it moves the surface without opening Maya's Tool Settings.

- Maya keeps a size and strength for each brush, so the sliders change to match when you switch brushes.
- They follow **B**-drag (size) and **M**-drag (strength) in the viewport, and keep Maya's Tool Settings window in step when it is open.
- The sliders run 0 to 100, like Maya's own. Type a larger size in the field for big meshes.
- They switch on once a sculpt brush has been picked.

Animation Tweaker is now 1.2.0. The help page and the interactive guide cover the new sliders.

## Retained features

Includes everything from 1.1.20: quick tangent buttons that change only the targeted keys and the Playblast Creator 2.0.6 FFmpeg 9.1 fix; from 1.1.19 Overlap 0.5.1 (Reset and Reload selected), from 1.1.18 Noise Generator 1.2.0, from 1.1.17 toolbar layouts (Settings → Layout), from 1.1.16 Animation Tweaker, and from 1.1.15 the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards. Then open **Animation Tweaker**, pick a mesh, click **Sculpt**, pick a brush and drag **Size** or **Strength**.
