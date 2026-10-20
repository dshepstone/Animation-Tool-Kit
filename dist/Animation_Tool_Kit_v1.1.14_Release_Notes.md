# Animation Tool Kit 1.1.14 — Overlap clean bake

## Fixed: Overlap left its bake wired into the controls

Overlap used to bake onto a new animation layer, `Kinequill_overlap1`. Each control then stayed connected through that layer's blend nodes, so the result was never a plain keyed control.

Overlap 0.5.0 bakes straight onto the controls' own animation curves:

- **Nothing stays connected.** After **Bake to controls**, each control channel is an ordinary time curve. No animation layer, blend node, preview locator or endpoint locator is left in the scene.
- **Keys inside the frame range are replaced; keys outside it are kept.** Unchecked channels are untouched.
- **One Undo reverts the whole bake**, including the removed helpers.
- **Every helper node is named `Overlap_*`** (preview, endpoint and demo). Nothing new is named Kinequill.

## Better optimized bake

**Optimize bake** is now on by default. It keys the first and last frames and every real swing peak with auto (spline) tangents. It then checks Maya's evaluated curve against the simulation and adds a key only where a frame is off by more than the tolerance (default 0.25°). Slow settling gets few keys, and a still tail gets none. Settling jitter below the tolerance no longer forces a key on every frame. Turn it off to key every frame.

## Scenes baked with earlier versions

The old `Kinequill_overlap` layers are listed under **Legacy layer**. **Delete bake** removes the layer, and the empty `BaseAnimation` root if nothing else uses it. Channels still driven by animation layers are refused at bake time with a clear message, because writing a combined result into one layer would double-count the others.

## Retained features

Includes everything from 1.1.13: Walk Off Node, the workspace-switch and Maya exit-crash fixes, Timeline Ticks, the ATK website logo button and the Playblast Creator 2.0.5 reliability fixes.

## Usage

Install by extracting `AnimationToolKit_v1_1_14.zip` and dragging `install_atk_toolbar.mel` into Maya. **Restart Maya after upgrading.**

## Validation

Tested headlessly in Maya 2027 on the ProRigs pendulum scene. The legacy layer was removed and three controls were baked with Rotate X. Each control was left with only an `animCurveTA` on `rotateX`, with no anim layers and no Overlap or Kinequill nodes, and one Undo restored the scene. The Maya integration check (`tests/check_overlap_integration.py`) and the new key-reduction unit tests pass.
