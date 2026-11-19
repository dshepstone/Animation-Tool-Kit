# Animation Tweaker for ATK

Animation Tweaker 1.0.0 sculpts shot-specific corrections and polish onto
animated meshes, after the skin. It is part of the Animation Tool Kit rigging
group: click its icon to open the dockable window. The standard ATK installer
copies the `atk_tweaker` package, including its offline HTML guide and icon,
into Maya's user scripts directory. No separate install is needed.

## What it does

- **Sculpt and commit.** Sculpt a copy of the mesh as it is on the current
  frame; Commit stores the difference as a tweak. Static, Pulse (0-1-0) and
  Sequence (pose-to-pose on independent levels) keying, Blank and Hold poses,
  muting tweaks while sculpting, Refine, Amplify, Rename, Paint mask and Delete.
- **Sculpt brushes.** Maya's sculpting brushes (Shape, Detail, Mask), symmetry,
  brush settings and Select on the Sculpt tab. Picking a brush selects the
  sculpt copy first.
- **Animate tweaks.** Key selected tweaks (current weight, 0 or 1), remove or
  clear keys, jump between keys, open the Graph Editor, or re-key as Static,
  Pulse or Pose. Hand keys switch a tweak to *keyed* mode so automatic keys
  never overwrite them.
- **Shape.** Inflate/Deflate along normals and Laplacian Relax, masked by the
  soft selection.
- **Effects** baked per frame: Smooth Motion, Stick to Surface, Push Out and
  Pin to World.
- **Surface Handle.** A softMod whose handle rides the deforming surface.
- **Utilities.** Locator/card baked to a vertex, bake transforms, smooth
  preview toggle, camera cycling, colour materials, channel copy/paste and a
  live face extract.
- **Cache versions.** Alembic export, versioned import, attach, swap, delete.

## How it stores things

One blendShape per mesh, `<mesh>_atkTweaks`, placed after the skinCluster.
Every tweak is a target whose object-space offsets are written directly into
the node, with no target meshes kept. Tweak details are JSON in a string
attribute on that node. Optional proxy channels sit on the mesh transform
under a `TWEAKS` divider. Deleting the node removes the tool from the mesh.

## Scripting

The engine has no UI:

```python
from atk_tweaker import engine, effects, core
engine.start_sculpt("body", mode=core.MODE_SEQUENCE, layer="L1")
# ... sculpt body_atkSculpt ...
engine.commit_sculpt("body")
effects.smooth_motion("body", 1, 120, sigma=2.0)
```

## Files

- `atk_tweaker/core.py` – pure-Python maths and planning (no Maya, unit tested)
- `atk_tweaker/engine.py` – tweak node, targets, keys, proxies, sculpt sessions
- `atk_tweaker/effects.py`, `surface_handle.py`, `utilities.py`, `cache_versions.py`
- `atk_tweaker/ui.py` – dockable window (`ATKAnimationTweakerWindow`)
- `atk_tweaker/resources/help.html` – offline guide (Help menu)
- `guide/animation_tweaker_guide.html` – interactive guide: click any control to see
  how to use it, plus step-by-step workflows. Also online at
  https://shepstone.ca/software/maya-tool-kit/animation-tweaker-guide/
- `DESIGN.md` – design notes and the feature map

Tests: `python -m unittest discover -s tests -p "test_animation_tweaker.py"`
(no Maya) and `mayapy tests/check_animation_tweaker_maya.py` (inside Maya).

This is original ATK code. See `DESIGN.md` for how it was designed.
