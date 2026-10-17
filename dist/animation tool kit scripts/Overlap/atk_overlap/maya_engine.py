"""Maya adapter: source capture -> deterministic solve -> preview or layer.

All Maya operations run on the main thread. A Session owns only its helper
group; baked layers are scene deliverables and survive session cleanup.
"""
from contextlib import contextmanager
import math

from maya import cmds
from maya.api import OpenMaya as om

from .settings import Settings
from .solver import Spring
from .reduction import reduce_keys


class Cancelled(RuntimeError):
    pass


def position(matrix):
    return om.MTransformationMatrix(matrix).translation(om.MSpace.kTransform)


def quaternion(matrix):
    return om.MTransformationMatrix(matrix).rotation(asQuaternion=True)


def compose(p, q):
    tm = om.MTransformationMatrix()
    tm.setTranslation(om.MVector(p), om.MSpace.kTransform)
    tm.setRotation(q)
    return tm.asMatrix()


def interpolate(a, b, weight):
    return compose(position(a) * (1 - weight) + position(b) * weight,
                   om.MQuaternion.slerp(quaternion(a), quaternion(b), weight))


def matrix_attr(node, attribute):
    return om.MMatrix(cmds.getAttr(node + "." + attribute))


def ui_distance(value):
    return om.MDistance(value, om.MDistance.kCentimeters).asUnits(om.MDistance.uiUnit())


def internal_distance(value):
    return om.MDistance(value, om.MDistance.uiUnit()).asCentimeters()


def ui_angle(value):
    return om.MAngle(value, om.MAngle.kRadians).asUnits(om.MAngle.uiUnit())


def internal_angle(value):
    return om.MAngle(value, om.MAngle.uiUnit()).asRadians()


def world_pivot(node):
    """Maya's real rotation center, including pivot compensation, in centimeters."""
    return om.MVector([internal_distance(v) for v in cmds.xform(
        node, query=True, worldSpace=True, rotatePivot=True)])


def lerp_vector(a, b, weight):
    return a * (1 - weight) + b * weight


@contextmanager
def scene_state(label):
    """Restore user state, even on error. Never force-enable undo."""
    time = cmds.currentTime(query=True)
    selection = cmds.ls(selection=True, long=True) or []
    auto = cmds.autoKeyframe(query=True, state=True)
    layers = {n: (cmds.animLayer(n, query=True, selected=True),
                  cmds.animLayer(n, query=True, preferred=True))
              for n in (cmds.ls(type="animLayer") or [])}
    cmds.undoInfo(openChunk=True, chunkName=label)
    try:
        cmds.autoKeyframe(state=False)
        yield
    finally:
        try:
            cmds.currentTime(time, edit=True)
            cmds.select([n for n in selection if cmds.objExists(n)], replace=True)
            cmds.autoKeyframe(state=auto)
            for n, (selected, preferred) in layers.items():
                if cmds.objExists(n):
                    cmds.animLayer(n, edit=True, selected=selected, preferred=preferred)
        finally:
            cmds.undoInfo(closeChunk=True)


class Session:
    def __init__(self, controls, settings=None):
        self.settings = settings or Settings()
        self.controls = []
        for node in controls:
            found = cmds.ls(node, long=True) or []
            if len(found) != 1:
                raise ValueError("Control must resolve uniquely: " + node)
            if found[0] not in self.controls:
                self.controls.append(found[0])
        if not self.controls:
            raise ValueError("Load at least one transform control")
        self.samples = []
        self.results = []
        self.frames = []
        self.source_settings = None
        self.solved_settings = None
        self.preview_group = None
        self.tip = None
        self.offsets = None
        self.ancestors = []
        self.orders = []
        self.components = []
        self.last_bake_stats = None
        self.validate()

    def validate(self):
        self.ancestors = []
        self.orders = []
        for index, node in enumerate(self.controls):
            if not cmds.objExists(node) or cmds.nodeType(node) != "transform":
                raise ValueError("Use transform controls, not joints: " + node)
            for attr in ("rotateAxis", "shear"):
                if any(abs(v) > 1e-7 for v in cmds.getAttr(node + "." + attr)[0]):
                    raise ValueError("Nonzero {} is unsupported: {}".format(attr, node))
            channels = "rotate" if self.settings.mode == "rotation" else "translate"
            for axis in self.settings.channels:
                plug = node + "." + channels + axis
                if cmds.getAttr(plug, lock=True) or not cmds.getAttr(plug, keyable=True):
                    raise ValueError("Channel must be unlocked and keyable: " + plug)
                incoming = cmds.listConnections(plug, source=True, destination=False) or []
                if incoming and not all(cmds.nodeType(n).startswith(("animCurve", "animBlendNode"))
                                        for n in incoming):
                    raise ValueError("Driven/constrained output channel is unsupported: " + plug)
            candidates = [i for i, parent in enumerate(self.controls)
                          if node.startswith(parent + "|")]
            ancestor = max(candidates, key=lambda i: len(self.controls[i])) if candidates else None
            if ancestor is not None and ancestor >= index:
                raise ValueError("Order controls root to tip using the list arrows")
            self.ancestors.append(ancestor)
            self.orders.append(cmds.getAttr(node + ".rotateOrder"))

    def default_tip_offset(self, index):
        """Continue the last selected segment in world space, then convert locally."""
        node = self.controls[index]
        world = matrix_attr(node, "worldMatrix[0]")
        center = world_pivot(node)
        ancestor = self.ancestors[index]
        if self.settings.tip_mode == "chain" and ancestor is not None:
            segment = center - world_pivot(self.controls[ancestor])
            if segment.length() > 1e-7:
                return om.MVector(om.MPoint(center + segment) * world.inverse())
        vector = [0., 0., 0.]
        vector["XYZ".index(self.settings.axis[-1])] = internal_distance(self.settings.length) * (
            -1 if self.settings.axis[0] == "-" else 1)
        return om.MVector(om.MPoint(center) * world.inverse()) + om.MVector(vector)

    def validate_levers(self, offsets, component_row):
        if self.settings.mode == "rotation" and len(self.settings.channels) == 1:
            axis_index = "XYZ".index(self.settings.channels)
            for i, offset in enumerate(offsets):
                lever = (offset - component_row[i][0]).normal()
                if abs(lever[axis_index]) > .99999:
                    raise ValueError("Endpoint lies on Rotate {} for {}. Use Auto chain and "
                                     "replace the endpoint, or move it off that axis.".format(
                                         self.settings.channels, self.controls[i].split("|")[-1]))

    def create_tip(self):
        """Editable endpoint on the last control. Sample consumes it as an offset."""
        with scene_state("Kinequill endpoint"):
            if self.tip and cmds.objExists(self.tip):
                cmds.delete(self.tip)
            self.tip = cmds.spaceLocator(name="Kinequill_endpoint#")[0]
            cmds.parent(self.tip, self.controls[-1], relative=True)
            vector = [ui_distance(v) for v in self.default_tip_offset(len(self.controls) - 1)]
            cmds.setAttr(self.tip + ".translate", *vector)
        return self.tip

    def sample(self, start, end, progress=None):
        """Sequentially capture source. progress(fraction, label) may cancel."""
        if int(start) != start or int(end) != end or end < start:
            raise ValueError("Use an integer frame range with end >= start")
        self.validate()
        # Drop stale results before attempting capture; failed capture cannot bake.
        self.samples, self.results, self.frames, self.components = [], [], [], []
        begin = int(start) - self.settings.preroll
        frames = list(range(begin, int(end) + 1))
        samples = []
        offsets = []
        components = []
        with scene_state("Kinequill sample"):
            for fi, frame in enumerate(frames):
                if progress:
                    progress(fi / len(frames), "Sampling frame {}".format(frame))
                cmds.currentTime(frame, edit=True)
                row = []
                component_row = []
                for node in self.controls:
                    world = matrix_attr(node, "worldMatrix[0]")
                    tm = om.MTransformationMatrix(world)
                    if any(abs(v - 1) > 1e-5 for v in tm.scale(om.MSpace.kTransform)) or any(
                            abs(v) > 1e-5 for v in tm.shear(om.MSpace.kTransform)):
                        raise ValueError("Unit world scale and no shear required: " + node)
                    local = matrix_attr(node, "matrix")
                    local_tm = om.MTransformationMatrix(local)
                    if any(abs(v - 1) > 1e-5 for v in local_tm.scale(om.MSpace.kTransform)):
                        raise ValueError("Unit local scale required: " + node)
                    effective_parent = local.inverse() * world
                    row.append((world, effective_parent))
                    pivot = om.MVector(om.MPoint(world_pivot(node)) * world.inverse())
                    translation = om.MVector([internal_distance(v) for v in
                                              cmds.getAttr(node + ".translate")[0]])
                    # Position(matrix) includes pivot compensation. It is not the
                    # translate channel value when pivots and rotations are nonzero.
                    rotation = om.MVector([internal_angle(v) for v in
                                           cmds.getAttr(node + ".rotate")[0]])
                    component_row.append((pivot, position(local) - translation, translation, rotation))
                samples.append(row)
                components.append(component_row)
                if fi == 0:
                    for i, node in enumerate(self.controls):
                        # Direct next selected descendant defines chain segment.
                        if i + 1 < len(self.controls) and self.ancestors[i + 1] == i:
                            endpoint = world_pivot(self.controls[i + 1])
                            offset = om.MPoint(endpoint) * row[i][0].inverse()
                            offsets.append(om.MVector(offset))
                        else:
                            offsets.append(self.default_tip_offset(i))
                    if self.tip and cmds.objExists(self.tip):
                        # Tip is parented to the last control: local translation is the offset.
                        offsets[-1] = om.MVector([internal_distance(v) for v in
                                                 cmds.getAttr(self.tip + ".translate")[0]])
                    if any((v - component_row[i][0]).length() < 1e-7
                           for i, v in enumerate(offsets)):
                        raise ValueError("Coincident chain pivots: supply separate controls or a valid tip")
                    self.validate_levers(offsets, component_row)
        self.samples, self.frames, self.offsets = samples, frames, offsets
        self.components = components
        self.start, self.end = int(start), int(end)
        self.seconds_per_frame = om.MTime(1, om.MTime.uiUnit()).asUnits(om.MTime.kSeconds)
        self.source_settings = self.settings
        return self

    def solve(self, progress=None):
        if not self.samples:
            raise ValueError("Sample source animation first")
        self.validate()
        self.validate_levers(self.offsets, self.components[0])
        # These settings change source sampling or the endpoint construction.
        for field in ("mode", "preroll", "axis", "length", "tip_mode"):
            if getattr(self.settings, field) != getattr(self.source_settings, field):
                raise ValueError("Settings changed: refresh source animation first")
        self.results = []
        self.solved_settings = None
        states = []
        for i, (world, _) in enumerate(self.samples[0]):
            goal = position(world) if self.settings.mode == "translation" else om.MVector(
                om.MPoint(self.offsets[i]) * world)
            states.append(Spring(goal))
        results = []
        previous_eulers = [None] * len(self.controls)
        # Adaptive minimum keeps numerical damping modest at high frequencies.
        steps = max(self.settings.substeps, int(math.ceil(
            self.seconds_per_frame * self.settings.frequency * 32)))
        dt = self.seconds_per_frame / steps
        for fi, frame in enumerate(self.frames):
            if progress:
                progress(fi / len(self.frames), "Solving frame {}".format(frame))
            output = None
            for sub in range(steps if fi else 1):
                alpha = (sub + 1) / steps if fi else 1.0
                originals = [interpolate(self.samples[max(0, fi - 1)][i][0], item[0], alpha)
                             for i, item in enumerate(self.samples[fi])]
                parents = [interpolate(self.samples[max(0, fi - 1)][i][1], item[1], alpha)
                           for i, item in enumerate(self.samples[fi])]
                solved = []
                output = []
                for i, original in enumerate(originals):
                    ancestor = self.ancestors[i]
                    delta = (originals[ancestor].inverse() * solved[ancestor]
                             if ancestor is not None else om.MMatrix())
                    base = original * delta
                    parent = parents[i] * delta
                    p, q = position(base), quaternion(base)
                    pivot_local = lerp_vector(self.components[max(0, fi - 1)][i][0],
                                              self.components[fi][i][0], alpha)
                    pivot = om.MVector(om.MPoint(pivot_local) * base)
                    target = p if self.settings.mode == "translation" else om.MVector(
                        om.MPoint(self.offsets[i]) * base)
                    tip = om.MVector(states[i].step(target, dt, self.settings.frequency,
                                                  self.settings.damping)) if fi else target
                    if self.settings.mode == "translation":
                        p = p + (tip - p) * self.settings.strength
                    else:
                        source_direction = target - pivot
                        direction = tip - pivot
                        if direction.length() > 1e-7:
                            swing = source_direction.rotateTo(direction)
                            swing = om.MQuaternion.slerp(om.MQuaternion(), swing,
                                                         self.settings.strength)
                            q = q * swing
                            # Rotate the transform origin about the actual rotation
                            # pivot. Keeping the origin fixed would move the joint.
                            p = pivot + (p - pivot).rotateBy(swing)
                    world = compose(p, q)
                    local = world * parent.inverse()
                    source_local = original * parents[i].inverse()
                    channel_t = lerp_vector(self.components[max(0, fi - 1)][i][2],
                                            self.components[fi][i][2], alpha)
                    channel_r = lerp_vector(self.components[max(0, fi - 1)][i][3],
                                            self.components[fi][i][3], alpha)
                    source_euler = om.MEulerRotation(channel_r.x, channel_r.y, channel_r.z, self.orders[i])
                    euler = om.MTransformationMatrix(local).rotation()
                    euler.reorderIt(self.orders[i])
                    euler = euler.closestSolution(previous_eulers[i] or source_euler)
                    bias = lerp_vector(self.components[max(0, fi - 1)][i][1],
                                       self.components[fi][i][1], alpha)
                    if self.settings.mode == "rotation":
                        # Apply the mask before solving descendants, not just when
                        # writing keys. Disabled local channels keep source values.
                        values = [euler[j] if a in self.settings.channels else channel_r[j]
                                  for j, a in enumerate("XYZ")]
                        euler = om.MEulerRotation(*values, self.orders[i])
                        q_local = euler.asQuaternion()
                        pivot_parent = om.MVector(om.MPoint(pivot_local) * source_local)
                        local = compose(pivot_parent - pivot_local.rotateBy(q_local), q_local)
                    else:
                        proposed = position(local) - bias
                        channel_t = om.MVector([proposed[j] if a in self.settings.channels else channel_t[j]
                                                for j, a in enumerate("XYZ")])
                        euler = source_euler
                        local = compose(channel_t + bias, source_euler.asQuaternion())
                    world = local * parent
                    solved.append(world)
                    if sub == (steps - 1 if fi else 0):
                        previous_eulers[i] = euler
                    output.append((world, tuple(ui_distance(v) for v in channel_t),
                                   tuple(ui_angle(v) for v in (euler.x, euler.y, euler.z))))
            if frame >= self.start:
                results.append((frame, output))
        self.results = results
        self.solved_settings = self.settings
        return self

    def _ready(self):
        if (not self.results or self.solved_settings is None or
                self.settings.simulation_key() != self.solved_settings.simulation_key()):
            raise ValueError("Generate a preview/solve with the current settings first")

    def clear_preview(self):
        if self.preview_group and cmds.objExists(self.preview_group):
            cmds.delete(self.preview_group)
        self.preview_group = None

    def preview(self, progress=None):
        self._ready()
        with scene_state("Kinequill preview"):
            self.clear_preview()
            group = cmds.group(empty=True, name="Kinequill_preview#")
            self.preview_group = group
            try:
                proxies = []
                for node in self.controls:
                    proxy = cmds.spaceLocator(name=node.split("|")[-1].replace(":", "_") + "_KQ#")[0]
                    cmds.parent(proxy, group)
                    cmds.setAttr(proxy + ".overrideEnabled", True)
                    cmds.setAttr(proxy + ".overrideColor", 18)
                    proxies.append(proxy)
                eulers = [None] * len(proxies)
                for fi, (frame, row) in enumerate(self.results):
                    if progress:
                        progress(fi / len(self.results), "Writing preview")
                    for i, (proxy, (world, _, _)) in enumerate(zip(proxies, row)):
                        euler = om.MTransformationMatrix(world).rotation()
                        if eulers[i] is not None:
                            euler = euler.closestSolution(eulers[i])
                        eulers[i] = euler
                        values = tuple(ui_distance(v) for v in position(world)) + tuple(ui_angle(v) for v in euler)
                        for attr, value in zip(("tx", "ty", "tz", "rx", "ry", "rz"), values):
                            cmds.setKeyframe(proxy, attribute=attr, time=frame, value=value,
                                             inTangentType="linear", outTangentType="linear")
            except BaseException:
                self.clear_preview()
                raise
        return group

    def bake(self, progress=None):
        self._ready()
        self.validate()
        layer = None
        prefix = "r" if self.settings.mode == "rotation" else "t"
        attrs = [prefix + a.lower() for a in self.settings.channels]
        self.last_bake_stats = None
        before = len(self.results) * len(self.controls) * len(attrs)
        after = 0
        with scene_state("Kinequill bake"):
            try:
                layer = cmds.animLayer("Kinequill_overlap#", override=True, passthrough=True)
                cmds.addAttr(layer, longName="overlapBake", attributeType="bool", defaultValue=True)
                for node in self.controls:
                    for attr in attrs:
                        cmds.animLayer(layer, edit=True, attribute=node + "." + attr)
                for index, node in enumerate(self.controls):
                    for ai, attr in enumerate(attrs):
                        if progress:
                            progress((index * len(attrs) + ai) / (len(self.controls) * len(attrs)),
                                     "Reducing / baking {}.{}".format(node.split("|")[-1], attr))
                        axis = "xyz".index(attr[-1])
                        component = 2 if self.settings.mode == "rotation" else 1
                        samples = [(frame, row[index][component][axis]) for frame, row in self.results]
                        # Rotation tolerance is explicitly degrees, independent of
                        # Maya's current angular display unit.
                        tolerance = self.settings.key_tolerance
                        if self.settings.mode == "rotation":
                            tolerance = om.MAngle(tolerance, om.MAngle.kDegrees).asUnits(om.MAngle.uiUnit())
                        keys = reduce_keys(samples, tolerance) if self.settings.optimize_bake else samples
                        after += len(keys)
                        for ki, (frame, value) in enumerate(keys):
                            if progress and ki % 100 == 0:
                                progress((index * len(attrs) + ai) / (len(self.controls) * len(attrs)),
                                         "Writing {}.{}".format(node.split("|")[-1], attr))
                            cmds.setKeyframe(node, attribute=attr, time=frame, value=value,
                                             animLayer=layer, noResolve=True,
                                             inTangentType="linear", outTangentType="linear")
                # One-frame boundary handles; source wins outside the chosen interval.
                for frame, value in ((self.start - 1, 0), (self.start, 1),
                                     (self.end, 1), (self.end + 1, 0)):
                    cmds.setKeyframe(layer, attribute="weight", time=frame, value=value,
                                     inTangentType="linear", outTangentType="linear")
            except BaseException:
                if layer and cmds.objExists(layer):
                    cmds.delete(layer)
                raise
        self.last_bake_stats = {"before": before, "after": after, "layer": layer}
        return layer

    def cleanup(self):
        """Remove only this session's endpoint and previews; retain baked output."""
        with scene_state("Kinequill cleanup"):
            self.clear_preview()
            if self.tip and cmds.objExists(self.tip):
                cmds.delete(self.tip)
            self.tip = None
