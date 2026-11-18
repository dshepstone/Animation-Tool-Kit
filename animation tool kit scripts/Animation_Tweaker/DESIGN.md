# Animation Tweaker — design notes

## Clean-room statement

Animation Tweaker was written for ATK as a functional replacement for a
licensed third-party mesh-polish tool (animPolish). The only input taken from
that tool was a **list of features**, written down by the licence holder from
using it. No source code, scripts, node graphs, attribute names, UI layouts,
icons or documentation of the third-party tool were looked at, searched for or
reproduced. The architecture, module layout, node and attribute names, keying
logic, maths and UI below are original to ATK.

## Architecture

```
atk_tweaker/
  __init__.py        show(), shutdown() and toolbar right-click actions
  qt_compat.py       PySide6, falling back to PySide2
  core.py            pure Python: deltas, relax, inflate, Gaussian filter,
                     surface binding, keying plans, metadata JSON, naming,
                     clipboard JSON, Alembic job strings. No Maya imports.
  engine.py          tweak node, target read/write, keys, proxies, masks,
                     sculpt sessions, inflate/relax
  effects.py         frame-baked Smooth Motion / Stick / Push Out / Pin
  surface_handle.py  softMod + uvPin handle
  utilities.py       follower bake, transform bake, smooth preview, cameras,
                     colours, channel clipboard, live face extract
  cache_versions.py  Alembic export, versions, attach, swap, delete
  ui.py              dockable window; calls the modules above, holds no logic
  help_view.py       offline HTML help viewer
```

Design rules:

1. **The scene is the database.** Everything the tool needs to continue lives
   in the scene: the tweak node and its JSON, the proxy channels, and even an
   in-progress sculpt (a JSON record on the sculpt mesh). There is no Python
   state to lose on Reload Scripts, and every session can be committed or
   cancelled later.
2. **One node per mesh.** `<mesh>_atkTweaks` is a blendShape created with
   `after=True`, so it sits after the skinCluster. Each tweak is a target with
   no geometry: its object-space offsets are written straight into
   `inputTarget[0].inputTargetGroup[i].inputTargetItem[6000]`
   (`inputPointsTarget` + `inputComponentsTarget`, sparse, run-length
   component ranges). No duplicate meshes, clusters or helper nodes stay in
   the scene.
3. **Read fast, write undoably.** Points are read with OpenMaya 2 (`MFnMesh`,
   `MDGContext` for other frames). Targets, aliases, metadata and keys are
   written with `cmds.setAttr` and friends so every operation is a single
   Undo chunk (`engine.undo_chunk`).
4. **Maths is testable.** All numeric work goes through `core.py`, which the
   unit tests exercise without Maya. The Maya modules only gather inputs and
   write outputs.
5. **Data, never code.** Metadata, sculpt sessions, cache versions and the
   channel clipboard are JSON. Nothing is passed to `exec`/`eval`, and the
   tool writes no script files. (`mel.eval` is used only to open Maya's own
   Paint Blend Shape Weights tool with a fixed command; the target name passed
   to it is sanitised to `[A-Za-z0-9_]`.) A unit test enforces the
   no-`exec`/`eval` rule.

### Names used in the scene

| Item | Name |
| --- | --- |
| Tweak node | `<mesh>_atkTweaks` (blendShape) |
| Marker / metadata / proxy flag | `atkTweakerNode`, `atkTweakerMeta`, `atkTweakerProxies` |
| Weight aliases and proxy channels | `tw_<label>` |
| Proxy divider | `TWEAKS` enum on the mesh transform |
| Sculpt mesh | `<mesh>_atkSculpt`, record in `atkTweakerSculpt` |
| Highlight shader | `atkTweakerSculpt_MAT` (deleted when unused) |
| Effect levels | `fx_smooth_motion`, `fx_stick`, `fx_push_out`, `fx_pin` |
| Surface handle | `<mesh>_surfHandle_pin / _aim / _handle / _softMod / _uvPin`, record in `atkTweakHandle` |
| Colour materials | `atkColour_<rrggbb>` |
| Channel clipboard | optionVar `atkTweakerChannelClipboard` |
| Cache control | `ATK_TweakCache_CTL`, state in `atkCacheState`, source tag `atkCacheSource` |

### Metadata

`atkTweakerMeta` holds
`{"version": 1, "targets": {"<index>": {label, kind, mode, frame, layer, ramp_in, ramp_out}}}`.
`core.decode_metadata` tolerates missing or broken JSON (it returns an empty
record) so a damaged scene never stops the window from opening.

### Keying

`core.sequence_plan` turns a level's `(target, frame)` list into keys: 1 on
the pose's frame, 0 on each neighbour's frame, linear tangents. Neighbouring
weights therefore always sum to 1 (a true crossfade). Artist levels hold at
the ends; effect levels fade to 0 one frame outside their range. Any insert
or delete rekeys the level from scratch, so keys can never drift from the
metadata.

A new pose takes over its level on its frame (the neighbours are keyed to 0
there). The sculpt delta was measured against the mesh *with* the level's
in-between shape showing, so `engine.commit_delta` folds that shape (each
pose's offsets times its weight on the frame, `level_contribution`) into the
new pose. Targets muted while sculpting are left out, since they were not in
the measured mesh. Blank and Hold poses do not carry the level.

## Feature map

| # | Source feature | ATK Animation Tweaker | How the ATK approach differs |
| --- | --- | --- | --- |
| 1 | Sculpt on a duplicate of the evaluated mesh | `engine.start_sculpt` copies the evaluated shape with `MFnMesh.copy` into a new transform at the same world matrix | No `duplicate` of the deformed mesh (which drags intermediate shapes along); the session record lives on the sculpt mesh, so it survives Reload Scripts |
| 1 | Highlight shader, hide original | `highlight`, `hide_original` options | Shader is created on demand and deleted when no sculpt uses it; visibility is left alone if it is connected |
| 1 | Commit stores delta; cancel restores | `commit_sculpt` / `cancel_sculpt` | Delta measured against the mesh resampled on the sculpt frame through `MDGContext`, so changing frame while sculpting is harmless |
| 1 | Static / pulse / sequence keying | `core.MODE_*`, `core.pulse_keys`, `core.sequence_plan` | Keys are generated from metadata by pure functions and fully rebuilt per level |
| 1 | Sequence levels crossfading pose to pose | `layer` field, `engine.rekey_level` | Levels are free-text names; a pose on an occupied frame/level refines that pose instead of stacking |
| 1 | Sequence Blank | `engine.blank_pose` | An empty target (zero components) |
| 1 | Sequence Hold | `engine.hold_pose` | Copies the previous pose's stored offsets with `core.previous_pose` |
| 1 | Sculpt-from-zero muting (all / static / sequence / level) | `core.targets_to_mute`, `engine._mute/_unmute` | Mute = temporarily disconnect the driver and zero the weight; restore record stored in the scene |
| 1 | Refine a tweak | `start_sculpt(refine=i)` + `core.refine_delta` | Correction is divided by the tweak's current weight, so the refined tweak matches the sculpt exactly |
| 1 | Amplify / scale | `engine.scale_tweak` | Any factor, including negative (flip) |
| 1 | Delete (target, curves, proxy, rekey) | `engine.delete_tweak(s)` | Removes the multi instances and alias, then rekeys only the affected levels |
| 1 | Per-mesh tweak list with weight sliders and key buttons | Sculpt tab tree with `WeightCell` | Also shows kind, mode, frame and level; rename and paint from the list |
| — | Proxy keyable attributes under a divider | `engine.set_proxies` | Toggling moves existing animation between weight and proxy instead of discarding it |
| — | Soft-selection masks | `engine.soft_selection_masks` (OpenMaya rich selection) | Face/edge selections are converted to vertices; masks are baked into the stored offsets |
| — | Paint mask | `engine.paint_mask` | Uses the blendShape's own per-target weights with Maya's paint tool, so painting is live and non-destructive |
| 2 | Inflate / deflate along normals | `engine.inflate` + `core.inflate_delta` | Maya vertex normals with a Newell-normal fallback |
| 2 | Relax (iterations, strength) | `engine.relax` + `core.relax_points` | Jacobi Laplacian; unmasked vertices stay fixed but still anchor the masked ones |
| 3 | Smooth Motion (temporal Gaussian) | `effects.smooth_motion` + `core.temporal_gaussian` | Edge-clamped kernel of 3σ radius; world- or object-space option |
| 3 | Stick to Surface | `effects.stick_to_surface` + `core.bind_to_surface/follow_surface` | Binding = triangle, barycentric coords and offset in the triangle's local frame, so the offset rotates with the driver |
| 3 | Push Out with skin offset | `effects.push_out` + `core.push_out_point` | Signed-distance test along the driver normal; only vertices closer than the offset move |
| 3 | Pin to World | `effects.pin_to_world` | Offsets are converted back to object space per frame from the mesh's world matrix |
| 3 | Effects as per-frame sequence targets on a dedicated layer | `effects._store`, `fx_*` levels | Re-running deletes the old level *before* sampling; ends fade out |
| 4 | Surface handle (softMod riding the surface via uvPin) | `surface_handle.create_handle` | uvPin reads the geometry *entering* the softMod (no cycle); the softMod's bind matrix is the aim group's inverse, so the rest pose is neutral wherever the pin moves |
| 4 | No-UV warning | warning + static placement | The handle is still usable, just not pinned |
| 4 | Falloff radius / mode / curve attributes | `falloffRadius`, `falloffMode`, `falloffShape`, `envelope` on the handle | Named falloff presets (`core.FALLOFF_PRESETS`) rebuild the softMod's ramp |
| 4 | Sphere display toggle and colour | `implicitSphere` under the aim group, `showFalloff`, RGB override | Sphere radius is connected to the falloff radius |
| 4 | Add / remove geometry | `add_geometry` / `remove_geometry` | Plain `deformer -e -g` membership |
| 4 | Orient to world | `orientToWorld` → `choice` node between full and translation-only pin matrices | Live switch, keyable, no re-creation |
| 4 | Aim at an object | `aim_at` / `clear_aim` on the intermediate aim group | Aim lives between pin and handle so the handle's own channels stay free |
| 5 | Bake locator/card to vertex | `utilities.bake_followers` | Cards get orientation from the vertex normal and an edge tangent; Euler-filtered |
| 5 | Bake mesh transforms | `utilities.bake_transforms` | Removes the constraints that were baked |
| 5 | Smooth-preview toggle | `utilities.toggle_smooth_preview` | Whole selected hierarchy, toggled from the first mesh's state |
| 5 | Cycle viewport cameras, skip ortho | `utilities.cycle_camera` + `core.next_camera` | Works on the focused or active model panel |
| 5 | Quick colour materials (palette + random) | `utilities.apply_colour` | Materials shared per colour; random colours are kept saturated and mid-bright |
| 5 | Copy/paste channel values | `utilities.copy/paste_channels`, `core.encode/decode_clipboard` | JSON in an optionVar, versioned format tag; never a `.py` file and never executed; honours Auto Key |
| 5 | Extract faces as a live blended copy | `utilities.extract_faces` | A `deleteComponent` node feeds the copy from the original's evaluated mesh, so the extract stays live without a blendShape |
| 6 | Alembic export with original-path attribute | `cache_versions.export_selected` | `atkCacheSource` attribute carried through `-attr` |
| 6 | Import versions into a control group | `cache_versions.import_version` | Versions are groups under `ATK_TweakCache_CTL` with an enum of version names |
| 6 | Swap version | `cache_versions.swap` | Re-points the attach blendShapes' `inputGeomTarget`, shows only the active version |
| 6 | Attach polished cache via blendShape with envelope | `cache_versions.attach` | One control `envelope` drives every attach blendShape |
| 6 | Delete | `delete_version`, `detach`, `delete_all` | State is JSON on the control; read with `json` only |

## Known limits and things to verify in Maya

The code was written without Maya available. These parts depend on Maya
behaviour that the unit tests cannot see and are covered by
`tests/check_animation_tweaker_maya.py` or need a manual check:

- `cmds.blendShape(..., after=True)` placing the node after the skinCluster.
- Writing `pointArray`/`componentList` targets with `cmds.setAttr` and reading
  them back.
- `MDGContextGuard` / `MDGContext` sampling on 2025–2027.
- softMod `bindPreMatrix` versus `preMatrix/postMatrix` (the code connects
  whichever exists) and the uvPin input plug names.
- `artBlendShapeSelectTarget` choosing the painted target (a warning tells the
  artist to choose it manually if it fails).
- Tweaks are offsets in the mesh's object space after the skin. They follow
  the transform, not individual joints; a large pose change needs a sequence
  pose or a Surface Handle.
