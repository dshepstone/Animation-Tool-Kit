# Animation Tool Kit 1.1.16 — Animation Tweaker

## New: Animation Tweaker

Sculpt shot-specific corrections and polish onto animated characters, after the skin, and key them on and off. Find it in the toolbar's **rigging** group.

Each mesh gets one blendShape, `<mesh>_atkTweaks`, placed after the skinCluster. Every tweak is a target on it whose offsets are written straight into the node. No duplicate meshes, clusters or other helpers are left in the scene. Every button is a single Undo.

- **Sculpt and commit.** Click **Sculpt** to get a copy of the mesh as it is on the current frame. Sculpt it with any Maya tool, then **Commit** to store the difference as a tweak, or **Cancel**. The copy can be highlighted and the original hidden while you work.
- **Keying modes.** *Static* is always on. *Pulse* keys 0-1-0 around the frame with ramp-in and ramp-out frames. *Sequence* keys pose to pose on independent levels: each pose is 1 on its frame and 0 on its neighbours' frames, so poses crossfade. **Blank pose** adds an empty pose and **Hold pose** copies the previous pose to the current frame.
- **Sculpt from zero** mutes all tweaks, the static ones, the sequence ones or one level while you sculpt.
- **Tweak list** for each mesh, with weight sliders and key buttons. You can **Refine** a tweak (the new sculpt is added to it), **Amplify** it, rename it, paint where it applies with Maya's blendShape weight painting, or **Delete** it (its keys and proxy go too, and its level is rekeyed).
- Optional **proxy channels** for each tweak on the mesh transform, under a `TWEAKS` divider.
- **Shape:** Inflate/Deflate along the normals, and Relax (Laplacian smoothing) with iterations and strength. Both work on the current frame and are masked by the soft selection.
- **Effects** baked as one pose per frame on their own level: **Smooth Motion** (a Gaussian filter over time), **Stick to Surface**, **Push Out** with a skin offset, and **Pin to World**.
- **Surface Handle:** a soft-modification handle that rides the skin using the mesh's UVs. It has falloff radius, mode and shape settings, a falloff sphere you can show and colour, orient to world, and aim at an object. You can add or remove meshes.
- **Utilities:** bake a locator or card onto a vertex, bake transforms, toggle smooth preview, cycle the viewport through the scene cameras, quick colour materials, copy and paste channel values, and extract faces as a live copy.
- **Cache versions:** export the selected meshes to Alembic, import caches as versions, attach a version onto the original meshes with an envelope, swap versions and delete them.

The window has an offline user guide under **Help**. See the tool's [usage notes](animation%20tool%20kit%20scripts/Animation_Tweaker/README.md) and [design notes](animation%20tool%20kit%20scripts/Animation_Tweaker/DESIGN.md).

Animation Tweaker is original ATK code. It was written from a feature list only; see the design notes.

## Tests

- New automated tests cover Animation Tweaker's maths and bookkeeping: the stored offsets, Relax, Inflate, the Gaussian filter over time, surface binding, the Pulse and Sequence keys, the per-tweak data, and adding and deleting tweaks against a simulated Maya. CI runs them.
- `tests/check_animation_tweaker_maya.py` runs the tool inside Maya with `mayapy`.

**Animation Tweaker has not yet been tested inside Maya.** Run the Maya check and try the tool on a shot before rolling this release out.

## Retained features

Includes everything from 1.1.15: the toolkit-wide bug fixes, Key Cleanup, Stagger Keys, the Maya exit-crash fix, the Overlap clean bake, the full Reload Scripts and Walk Off Node.

## Usage

Drag `install_atk_toolbar.mel` into Maya. If the toolbar is already installed, **Settings → Reload Scripts** is enough afterwards.
