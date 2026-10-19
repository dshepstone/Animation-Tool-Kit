# Walk Off Node 1.0.0

Turns a treadmill walk cycle into a walk that travels through the scene.

In a typical cycle setup the character's controls (IK feet, IK hands, waist / COG) loop in place with cycle infinity. Meanwhile the rig's base or layout node, at the top of the hierarchy, slides forward to carry the character along. Walk Off Node keys where those controls really are in world space, removes the base node's slide and removes the cycle, so the feet plant and the character walks off the node.

## Use

1. Launch **Walk Off Node** from the ATK toolbar's timing group, or click **Walk Off Node...** in Xform Copy Paste.
2. Select the controls that should travel and click **Load Selected**: IK feet, IK hands, waist / COG and pole vectors.
3. Select the sliding base / layout node and click **Set**.
4. Choose the range. **Playback** uses the playback range. **Timeline Selection** uses a shift-dragged Time Slider range. The range can be longer than one cycle.
5. Click **Walk Off Node**. The whole operation is a single Undo.

## What it does

1. Samples every control's world-space translate and rotate on every frame, with the cycle and the slide both playing.
2. Bakes keyed custom attributes (foot roll, toe tap and so on) across the range, so they keep animating once the cycle is removed.
3. Deletes the base node's transform keys. By default it holds the base at its first-frame pose. You can choose **Reset to origin** instead.
4. Replaces the controls' translate/rotate keys in the range with the sampled world path, sets their infinity to constant and runs an Euler filter.

## Options

| Option | Default | Notes |
|---|---|---|
| Key every | 1 frame | Higher values give lighter curves, but a planted foot can slide between keys. |
| Match world rotation | On | Needed when the walk turns or the base rotates. |
| Bake keyed custom attributes | On | Keeps foot roll and similar attributes animating after the cycle is removed. |
| Remove cycle | On | Sets pre/post infinity to constant on the baked curves. |
| Base node after | Hold first-frame pose | Or reset the base to the origin. |

## Tips

- Include every control that should travel with the body and is **not** a child of another included control. Controls under the COG (spine, head, FK arms) follow it, so they don't need baking.
- Locked axes are left alone. Channels driven by constraints or expressions can't be keyed, so the tool warns and skips them.
- Scripting: `walk_off_node.walk_off_node(controls, base_nodes, start, end, step=1)`.
