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
  sculpt-from-zero muting, Refine, Amplify, Rename, Paint mask and Delete.
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
- `DESIGN.md` – design notes and the feature map

Tests: `python -m unittest discover -s tests -p "test_animation_tweaker.py"`
(no Maya) and `mayapy tests/check_animation_tweaker_maya.py` (inside Maya).

This is original ATK code. See `DESIGN.md` for how it was designed.
