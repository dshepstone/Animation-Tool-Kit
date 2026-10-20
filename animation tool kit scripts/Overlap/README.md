# Overlap for ATK

Overlap 0.5.0 is included in the Animation Tool Kit animation/timing group.
Click its pendulum icon to open the tool. No separate installation or download
is required. The standard ATK installer copies the full `atk_overlap` package,
including its HTML guide, icon, and licence, into Maya's user scripts directory.

The bundle provides per-axis spring overlap, offset pivot support, deterministic
locator previews, and an optimized bake that keys the controls directly. The
bake leaves no animation layer, blend node or other Overlap node connected, and
one Undo reverts it. Layers baked by 0.4.0 and earlier can still be deleted.
File and Help menus provide presets, a shelf launcher, the offline reference,
suggested settings/examples, and About/licence details.

This copy uses `atk_overlap` as its module name and `ATKOverlapWindow` as its
window identity so it can coexist with the standalone `kinequill` package.
ATK's tool visibility settings and Reload Scripts include it automatically.

Source: David Shepstone's standalone Overlap 0.4.0, commit `78d88a8` in
`dshepstone/kinequill`. Adaptations are the package/shelf import, window
identity, safe window replacement after ATK reloads tool modules, and (0.5.0)
the direct-to-controls bake with `Overlap_*` helper names.
The original copyright and separate licence are retained in `atk_overlap/LICENSE`.
