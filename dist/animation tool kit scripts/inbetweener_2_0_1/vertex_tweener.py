"""
Inbetweener Tool - Maya Animation Breakdown Tool
A high-performance tweening utility for Maya animators to break down poses and manage arcs.

Author: Pipeline Tools
Version: 2.1.0
"""

import os

import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui
import maya.api.OpenMaya as om


# ============================================================================
# QT COMPATIBILITY LAYER
# ============================================================================

def _import_qt_modules():
    """Resolve the Qt bindings bundled with the current Maya session."""
    binding_attempts = (
        ("PySide6", "shiboken6"),
        ("PySide6", "shiboken2"),
        ("PySide2", "shiboken2"),
        ("PySide2", "shiboken6"),
    )

    last_error = None
    for qt_mod_name, shiboken_name in binding_attempts:
        try:
            qt_mod = __import__(qt_mod_name, fromlist=["QtCore", "QtGui", "QtWidgets"])
            shiboken_mod = __import__(shiboken_name)
        except ImportError as exc:
            last_error = exc
            continue

        try:
            qt_core = getattr(qt_mod, "QtCore")
            qt_gui = getattr(qt_mod, "QtGui")
            qt_widgets = getattr(qt_mod, "QtWidgets")
        except AttributeError as exc:
            last_error = exc
            continue

        return qt_core, qt_gui, qt_widgets, shiboken_mod

    raise ImportError("Vertex Tweener requires PySide2/PySide6 with shiboken") from last_error


QtCore, QtGui, QtWidgets, shiboken = _import_qt_modules()


# ============================================================================
# PREFERENCES
# ============================================================================

PREF_AUTO_KEY = "vertexTweener_autoKey"
PREF_SLIDER_VALUE = "vertexTweener_sliderValue"
PREF_MOTION_TRAILS = "vertexTweener_motionTrails"
PREF_OVERSHOOT_MODE = "vertexTweener_overshootMode"
PREF_SKIP_SCAN_CONFIRM = "vertexTweener_skipScanConfirm"


def get_pref(key, default):
    if cmds.optionVar(exists=key):
        if isinstance(default, bool): return cmds.optionVar(q=key) == 1
        elif isinstance(default, int): return cmds.optionVar(q=key)
        elif isinstance(default, float): return cmds.optionVar(q=key)
    return default


def set_pref(key, value):
    if isinstance(value, bool): cmds.optionVar(iv=(key, 1 if value else 0))
    elif isinstance(value, int): cmds.optionVar(iv=(key, value))
    elif isinstance(value, float): cmds.optionVar(fv=(key, value))


# Attributes whose rest/default value is 1.0 (not 0.0).
# Covers standard Maya names plus common rig conventions.
SCALE_ATTRS = {'sx', 'sy', 'sz', 'scaleX', 'scaleY', 'scaleZ'}

# Substrings that indicate an attribute should default to 1.0
# (catches custom rig attrs like headScale, armVolume, fingerCurl_vis, etc.)
_UNIT_DEFAULT_PATTERNS = (
    'scale', 'Scale', 'scl', 'Scl',
    'volume', 'Volume', 'vol', 'Vol',
    'vis', 'Vis', 'visibility', 'Visibility',
    'envelope', 'Envelope',
    'weight', 'Weight',
    'influence', 'Influence',
    'blend', 'Blend',
    'multiplier', 'Multiplier', 'mult', 'Mult',
)

# Name of the network node used to store scanned default pose values
DEFAULT_POSE_NODE = "inbetweener_defaultPose"


# ============================================================================
# DEFAULT POSE STORAGE
# ============================================================================

class DefaultPoseStore:
    """Scans and stores default/rest pose values on a Maya network node.

    The node holds one dynamic attribute per controller attribute, encoding the
    default value so Blend-to-Default can use the real rest pose instead of
    guessing 0/1.
    """

    @staticmethod
    def _attr_key(full_attr):
        """Convert 'namespace:ctrl.translateX' to a safe attribute name."""
        return full_attr.replace(':', '_NS_').replace('.', '_DOT_').replace('|', '_PIPE_')

    @staticmethod
    def scan_defaults(roots=None):
        """Scan selected controls (or hierarchy) and store their current values.

        Call this while the rig is in its default/bind pose.
        Returns the number of attributes stored.
        """
        if roots is None:
            roots = cmds.ls(selection=True, long=True)
        if not roots:
            return 0

        # Collect all controls using long (unique) DAG paths.
        # Include every transform and joint beneath each root.
        controls = set()
        for root in roots:
            controls.add(root)
            descendants = cmds.listRelatives(root, allDescendents=True,
                                             type=('transform', 'joint'),
                                             fullPath=True) or []
            controls.update(descendants)

        if not controls:
            return 0

        # Create or reuse the storage node
        if cmds.objExists(DEFAULT_POSE_NODE):
            try:
                cmds.lockNode(DEFAULT_POSE_NODE, lock=False)
            except RuntimeError:
                pass
            cmds.delete(DEFAULT_POSE_NODE)

        node = cmds.createNode('network', name=DEFAULT_POSE_NODE)
        cmds.addAttr(node, longName='inbetweenerVersion', dataType='string')
        cmds.setAttr(node + '.inbetweenerVersion', '2.1', type='string')

        count = 0
        for ctrl in sorted(controls):
            # Resolve the minimal unique name Maya uses (what cmds.ls returns).
            # This is the name that on_bd_pressed will construct keys with.
            ls_names = cmds.ls(ctrl)
            if not ls_names:
                continue
            display_name = ls_names[0]

            # Query attributes using the long DAG path — always unambiguous,
            # even when multiple nodes share the same short name.
            keyable_attrs = cmds.listAttr(ctrl, keyable=True) or []

            # Also pick up non-keyable but channel-box-visible attributes
            # (some rigs mark attrs as non-keyable but still display them).
            cb_attrs = cmds.listAttr(ctrl, channelBox=True) or []
            all_attrs = sorted(set(keyable_attrs) | set(cb_attrs))

            for attr in all_attrs:
                long_attr = "{}.{}".format(ctrl, attr)          # unambiguous query
                store_attr = "{}.{}".format(display_name, attr)  # matches BD lookup
                try:
                    if cmds.getAttr(long_attr, lock=True):
                        continue
                    val = cmds.getAttr(long_attr)
                    if not isinstance(val, (int, float)):
                        continue
                except (RuntimeError, TypeError, ValueError):
                    continue

                safe_key = DefaultPoseStore._attr_key(store_attr)
                try:
                    cmds.addAttr(node, longName=safe_key, attributeType='double')
                    cmds.setAttr("{}.{}".format(node, safe_key), float(val))
                    count += 1
                except RuntimeError:
                    pass

        cmds.setAttr(node + '.visibility', False)
        cmds.lockNode(node, lock=True)
        return count

    @staticmethod
    def _looks_like_unit_attr(attr_name):
        """Return True if the attribute name suggests a default of 1.0."""
        if attr_name in SCALE_ATTRS:
            return True
        for pat in _UNIT_DEFAULT_PATTERNS:
            if pat in attr_name:
                return True
        return False

    @staticmethod
    def get_default(full_attr):
        """Look up the stored default for *full_attr*.

        Priority order:
        1. Scanned default-pose node (most accurate — real rest pose)
        2. Maya's attribute default value via attributeQuery, but only when
           it looks trustworthy (non-zero, or the attr name doesn't suggest
           a 1.0 default).
        3. Heuristic: 1.0 for scale/visibility/volume-like attrs, 0.0 otherwise
        """
        # 1. Check the scanned pose node first
        if cmds.objExists(DEFAULT_POSE_NODE):
            safe_key = DefaultPoseStore._attr_key(full_attr)
            node_attr = "{}.{}".format(DEFAULT_POSE_NODE, safe_key)
            if cmds.objExists(node_attr):
                try:
                    return cmds.getAttr(node_attr)
                except RuntimeError:
                    pass

        attr_name = full_attr.rsplit('.', 1)[-1] if '.' in full_attr else full_attr
        looks_unit = DefaultPoseStore._looks_like_unit_attr(attr_name)

        # 2. Query Maya's own attribute default value
        parts = full_attr.split('.', 1)
        if len(parts) == 2:
            obj, attr = parts
            try:
                defaults = cmds.attributeQuery(attr, node=obj, listDefault=True)
                if defaults:
                    maya_default = float(defaults[0])
                    # If Maya says non-zero, trust it.
                    # If Maya says 0 but the name looks like a unit attr,
                    # the rigger likely forgot to set defaultValue in addAttr
                    # — fall through to heuristic.
                    if maya_default != 0.0 or not looks_unit:
                        return maya_default
            except (RuntimeError, ValueError):
                pass

        # 3. Heuristic fallback
        return 1.0 if looks_unit else 0.0

    @staticmethod
    def has_stored_defaults():
        """Return True if the default-pose storage node exists."""
        return cmds.objExists(DEFAULT_POSE_NODE)


# ============================================================================
# CORE INTERPOLATION LOGIC
# ============================================================================

class TweenEngine:
    """Handles both Tweener (current time) and BN (selected keys) calculations."""

    # Cache populated on slider press for fast drag interpolation.
    # List of (full_attr, prev_val, next_val) tuples — only scalar attrs.
    _cached_attrs = []

    @staticmethod
    def cache_selection():
        """Query and cache keyframe boundary values for the current selection.

        Called once on slider press so that drag only does lightweight lerp.
        Returns the number of cached attributes.
        """
        TweenEngine._cached_attrs = []
        target_attrs = TweenEngine.get_selected_keyframe_attrs()
        selection = list(target_attrs.keys()) if target_attrs else cmds.ls(selection=True)
        if not selection:
            return 0

        current_time = cmds.currentTime(query=True)

        for obj in selection:
            if target_attrs:
                keyable_attrs = sorted(target_attrs.get(obj, []))
            else:
                keyable_attrs = cmds.listAttr(obj, keyable=True) or []
            for attr in keyable_attrs:
                full_attr = "{}.{}".format(obj, attr)
                try:
                    if cmds.getAttr(full_attr, lock=True):
                        continue
                except (RuntimeError, TypeError, ValueError):
                    continue

                prev_val, next_val, has_keys = TweenEngine.get_keyframe_values(
                    obj, attr, current_time
                )
                if not has_keys:
                    continue

                # Only cache scalar (float/int) values — skip compound attrs
                if not isinstance(prev_val, (int, float)):
                    continue
                if not isinstance(next_val, (int, float)):
                    continue

                TweenEngine._cached_attrs.append((full_attr, prev_val, next_val))

        return len(TweenEngine._cached_attrs)

    @staticmethod
    def apply_cached_tween(bias):
        """Fast interpolation using cached data — called during slider drag.

        Only performs setAttr calls with pre-computed lerp, no Maya queries.
        """
        t = bias / 100.0
        count = 0
        for full_attr, prev_val, next_val in TweenEngine._cached_attrs:
            new_value = prev_val + (next_val - prev_val) * t
            try:
                cmds.setAttr(full_attr, new_value)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                pass
        return count

    @staticmethod
    def clear_cache():
        """Release cached data after slider release."""
        TweenEngine._cached_attrs = []

    @staticmethod
    def get_keyframe_values(obj, attr, current_time):
        full_attr = "{}.{}".format(obj, attr)
        keyframes = cmds.keyframe(full_attr, query=True, timeChange=True)

        if not keyframes or len(keyframes) < 2:
            return None, None, False

        prev_time = None
        next_time = None

        for kf_time in keyframes:
            if kf_time < current_time:
                prev_time = kf_time
            elif kf_time > current_time:
                next_time = kf_time
                break

        if prev_time is None:
            prev_time, next_time = keyframes[0], keyframes[1]
        elif next_time is None:
            prev_time, next_time = keyframes[-2], keyframes[-1]

        prev_value = cmds.getAttr(full_attr, time=prev_time)
        next_value = cmds.getAttr(full_attr, time=next_time)
        return prev_value, next_value, True

    @staticmethod
    def get_selected_keyframe_attrs():
        """Return a mapping of object -> set(attrs) from selected keyframes."""
        selected_curves = cmds.keyframe(q=True, selected=True, name=True)
        if not selected_curves:
            return {}

        target_attrs = {}
        for curve in set(selected_curves):
            dest_plugs = cmds.listConnections(curve, s=False, d=True, plugs=True) or []
            for plug in dest_plugs:
                obj_attr = plug.split('.', 1)
                if len(obj_attr) != 2:
                    continue
                obj, attr = obj_attr
                target_attrs.setdefault(obj, set()).add(attr)
        return target_attrs

    @staticmethod
    def apply_tween(bias):
        """Full query-and-apply tween for one-shot use (quick buttons).

        For slider drag, use cache_selection() + apply_cached_tween() instead.
        """
        target_attrs = TweenEngine.get_selected_keyframe_attrs()
        selection = list(target_attrs.keys()) if target_attrs else cmds.ls(selection=True)
        if not selection:
            return 0

        current_time = cmds.currentTime(query=True)
        count = 0

        for obj in selection:
            if target_attrs:
                keyable_attrs = sorted(target_attrs.get(obj, []))
            else:
                keyable_attrs = cmds.listAttr(obj, keyable=True) or []
            for attr in keyable_attrs:
                full_attr = "{}.{}".format(obj, attr)
                try:
                    if cmds.getAttr(full_attr, lock=True):
                        continue
                except (RuntimeError, TypeError, ValueError):
                    continue

                prev_val, next_val, has_keys = TweenEngine.get_keyframe_values(obj, attr, current_time)
                if not has_keys:
                    continue

                # Skip compound (non-scalar) attribute values
                if not isinstance(prev_val, (int, float)):
                    continue
                if not isinstance(next_val, (int, float)):
                    continue

                new_value = prev_val + (next_val - prev_val) * (bias / 100.0)
                try:
                    cmds.setAttr(full_attr, new_value)
                    count += 1
                except (RuntimeError, TypeError, ValueError):
                    pass

        return count

    @staticmethod
    def apply_neighbor_blend(weight, blend_to_next=True):
        """BN logic: Blends selected keyframes in Graph Editor toward neighbors."""
        n_weight = weight / 100.0
        selected_curves = cmds.keyframe(q=True, selected=True, name=True)
        if not selected_curves: return

        for curve in selected_curves:
            indices = cmds.keyframe(curve, q=True, selected=True, indexValue=True)
            for idx in indices:
                curr_val = cmds.keyframe(curve, index=(idx,), q=True, valueChange=True)[0]
                try:
                    target_idx = idx + 1 if blend_to_next else idx - 1
                    target_val = cmds.keyframe(curve, index=(target_idx,), q=True, valueChange=True)[0]
                    new_val = curr_val + (target_val - curr_val) * n_weight
                    cmds.keyframe(curve, index=(idx,), valueChange=new_val)
                except IndexError: continue

    @staticmethod
    def get_default_value_for_curve(curve):
        """Determine the default/rest value for an animation curve's attribute."""
        attr_name = curve.split('_')[-1] if '_' in curve else curve
        return 1.0 if attr_name in SCALE_ATTRS else 0.0

    @staticmethod
    def apply_ease_blend(weight, blend_to_next=True):
        """BE logic: Blends selected keyframes to create eased motion between neighbors.

        Calculates where the key should be to create an ease-in-out curve,
        then blends toward that eased position.

        Positive weight: ease motion toward next key (ease-in)
        Negative weight: ease motion toward previous key (ease-out)
        """
        n_weight = abs(weight) / 100.0  # Linear weight mapping for tight control
        selected_curves = cmds.keyframe(q=True, selected=True, name=True)
        if not selected_curves: return

        for curve in selected_curves:
            indices = cmds.keyframe(curve, q=True, selected=True, indexValue=True)
            if not indices:
                continue

            for idx in indices:
                try:
                    # Get current keyframe value and time
                    curr_val = cmds.keyframe(curve, index=(idx,), q=True, valueChange=True)[0]
                    curr_time = cmds.keyframe(curve, index=(idx,), q=True, timeChange=True)[0]

                    # Get surrounding keyframes to calculate eased position
                    prev_idx = idx - 1
                    next_idx = idx + 1

                    # Need both prev and next keys to calculate ease
                    if prev_idx < 0 or next_idx >= cmds.keyframe(curve, q=True, keyframeCount=True):
                        continue

                    prev_val = cmds.keyframe(curve, index=(prev_idx,), q=True, valueChange=True)[0]
                    prev_time = cmds.keyframe(curve, index=(prev_idx,), q=True, timeChange=True)[0]
                    next_val = cmds.keyframe(curve, index=(next_idx,), q=True, valueChange=True)[0]
                    next_time = cmds.keyframe(curve, index=(next_idx,), q=True, timeChange=True)[0]

                    # Calculate normalized time position (0 to 1) between prev and next
                    time_range = next_time - prev_time
                    if time_range == 0:
                        continue
                    t = (curr_time - prev_time) / time_range

                    # Calculate eased position using cubic ease-in-out
                    # This determines where the key should be for smooth easing
                    if blend_to_next:
                        # Ease-in: slow start, accelerate toward next
                        # Use t^3 for ease-in curve
                        eased_t = t * t * t
                    else:
                        # Ease-out: fast start, decelerate toward prev
                        # Use 1 - (1-t)^3 for ease-out curve
                        eased_t = 1 - pow(1 - t, 3)

                    # Calculate the eased value (where key should be for eased motion)
                    eased_val = prev_val + (next_val - prev_val) * eased_t

                    # Blend current value toward eased value based on weight
                    # Linear blend for tight slider-to-key correlation
                    new_val = curr_val + (eased_val - curr_val) * n_weight
                    cmds.keyframe(curve, index=(idx,), valueChange=new_val)

                except (IndexError, TypeError):
                    continue


class WorldTweenEngine:
    """Handles world-space matrix interpolation for tweening in global coordinates."""

    @staticmethod
    def get_selected_keyframe_objects():
        """Return transform objects connected to selected keyframes."""
        selected_curves = cmds.keyframe(q=True, selected=True, name=True)
        if not selected_curves:
            return []

        objects = set()
        for curve in set(selected_curves):
            dest_plugs = cmds.listConnections(curve, s=False, d=True, plugs=True) or []
            for plug in dest_plugs:
                obj = plug.split('.', 1)[0]
                objects.add(obj)
        return cmds.ls(list(objects), type=('transform', 'joint')) or []

    @staticmethod
    def get_world_matrix_at_time(obj, time):
        """Get the world matrix of an object at a specific time without changing timeline.

        Uses Maya's ability to query worldMatrix attribute at a specific time.
        """
        try:
            # Query worldMatrix attribute at specific time (no timeline scrubbing!)
            matrix_list = cmds.getAttr(obj + '.worldMatrix[0]', time=time)
            return om.MMatrix(matrix_list)
        except (RuntimeError, ValueError):
            return None

    @staticmethod
    def matrix_to_transform_components(matrix):
        """Extract translation and rotation from an MMatrix."""
        transform_matrix = om.MTransformationMatrix(matrix)
        translation = transform_matrix.translation(om.MSpace.kWorld)
        rotation = transform_matrix.rotation(asQuaternion=True)
        return translation, rotation

    @staticmethod
    def get_keyframe_times(obj, current_time):
        """Find the previous and next keyframe times for transform attributes."""
        # Check for keyframes on translate or rotate attributes
        for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
            full_attr = "{}.{}".format(obj, attr)
            keyframes = cmds.keyframe(full_attr, query=True, timeChange=True)
            if keyframes and len(keyframes) >= 2:
                prev_time = None
                next_time = None

                for kf_time in keyframes:
                    if kf_time < current_time:
                        prev_time = kf_time
                    elif kf_time > current_time:
                        next_time = kf_time
                        break

                if prev_time is None:
                    prev_time, next_time = keyframes[0], keyframes[1]
                elif next_time is None:
                    prev_time, next_time = keyframes[-2], keyframes[-1]

                return prev_time, next_time

        return None, None

    @staticmethod
    def apply_world_tween(bias):
        """World Space Tweener: Blends objects in world space using matrix interpolation.

        Queries world matrices at specific times WITHOUT changing the timeline.
        Auto-keying is handled on slider release to prevent mid-drag corruption.
        """
        selection = WorldTweenEngine.get_selected_keyframe_objects() or cmds.ls(selection=True, type=('transform', 'joint'))
        if not selection:
            return 0

        current_time = cmds.currentTime(query=True)
        t = bias / 100.0
        count = 0

        for obj in selection:
            prev_time, next_time = WorldTweenEngine.get_keyframe_times(obj, current_time)
            if prev_time is None or next_time is None:
                continue

            prev_matrix = WorldTweenEngine.get_world_matrix_at_time(obj, prev_time)
            next_matrix = WorldTweenEngine.get_world_matrix_at_time(obj, next_time)

            if prev_matrix is None or next_matrix is None:
                continue

            prev_trans, prev_rot = WorldTweenEngine.matrix_to_transform_components(prev_matrix)
            next_trans, next_rot = WorldTweenEngine.matrix_to_transform_components(next_matrix)

            interp_trans = prev_trans + (next_trans - prev_trans) * t
            interp_rot = om.MQuaternion.slerp(prev_rot, next_rot, t)

            interp_matrix = om.MTransformationMatrix()
            interp_matrix.setTranslation(interp_trans, om.MSpace.kWorld)
            interp_matrix.setRotation(interp_rot)

            matrix_list = list(interp_matrix.asMatrix())
            cmds.xform(obj, matrix=matrix_list, worldSpace=True)
            count += 1

        return count


# ============================================================================
# MOTION TRAILS MANAGER
# ============================================================================

class MotionTrailsManager:
    active_trails = []
    @classmethod
    def toggle_motion_trails(cls, enable):
        if enable: cls.create_motion_trails()
        else: cls.delete_motion_trails()

    @classmethod
    def create_motion_trails(cls):
        cls.delete_motion_trails()
        selection = cmds.ls(selection=True, type=('transform', 'joint'))
        if not selection: return
        for obj in selection:
            try:
                safe_name = obj.replace('"', '\\"')
                snapshot = mel.eval('snapshot -motionTrail 1 -increment 1 -startTime `playbackOptions -q -min` -endTime `playbackOptions -q -max` "{}"'.format(safe_name))
                if snapshot: cls.active_trails.extend(cmds.ls(snapshot))
            except RuntimeError: pass

    @classmethod
    def delete_motion_trails(cls):
        for trail in cls.active_trails:
            if cmds.objExists(trail):
                try: cmds.delete(trail)
                except RuntimeError: pass
        cls.active_trails = []

    @classmethod
    def refresh_motion_trails(cls):
        if cls.active_trails: cls.create_motion_trails()


# ============================================================================
# CUSTOM SLIDER UI
# ============================================================================

class VertexTickedSlider(QtWidgets.QSlider):
    """A slider that draws custom 10% tick marks with color-coded overshoots."""
    def __init__(self, orientation, is_tw=True, is_world=False, label_text="", parent=None):
        super(VertexTickedSlider, self).__init__(orientation, parent)
        self.is_tw = is_tw # Tweener vs BN logic
        self.is_world = is_world  # World Tweener uses gold/yellow styling
        self.label_text = label_text  # Text to display in center box (e.g., "TW", "BN")
        self.overshoot_mode = True
        self.keyed_value = None  # Slider value where a key was set (special tick)
        self.setTickPosition(QtWidgets.QSlider.NoTicks)

    def paintEvent(self, event):
        super(VertexTickedSlider, self).paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self)

        s_min, s_max = self.minimum(), self.maximum()
        s_range = float(s_max - s_min)

        # Draw ticks every 10%
        for val in range(s_min, s_max + 1, 10):
            x = groove.left() + ((val - s_min) / s_range * groove.width())
            y = groove.center().y()

            # Color Logic
            if self.is_world:
                # Gold/Yellow for World Tweener
                if val == self.value():
                    color = QtGui.QColor(255, 215, 0)  # Bright gold for current
                else:
                    color = QtGui.QColor(200, 160, 0)  # Darker gold for others
            elif self.is_tw and (val < 0 or val > 100):
                # Red/Orange for Local Tweener overshoots
                color = QtGui.QColor(255, 80, 80) if val == self.value() else QtGui.QColor(255, 140, 60)
            else:
                # Blue/Grey for normal range and BN
                color = QtGui.QColor(100, 180, 255) if val == self.value() else QtGui.QColor(150, 150, 150)

            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            # Make 0, 50, 100 slightly larger
            size = 5 if val % 50 == 0 else 3
            painter.drawEllipse(QtCore.QPointF(x, y), size, size)

        # Draw keyed-position tick (bright green diamond)
        if self.keyed_value is not None:
            kx = groove.left() + ((self.keyed_value - s_min) / s_range * groove.width())
            ky = groove.center().y()
            keyed_color = QtGui.QColor(0, 230, 120)  # Bright green
            painter.setBrush(keyed_color)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 180, 90), 1))
            diamond = QtGui.QPolygonF([
                QtCore.QPointF(kx, ky - 7),
                QtCore.QPointF(kx + 5, ky),
                QtCore.QPointF(kx, ky + 7),
                QtCore.QPointF(kx - 5, ky),
            ])
            painter.drawPolygon(diamond)

        # Draw label box at handle position (this becomes the visual handle)
        if self.label_text:
            # Calculate handle position based on current value
            current_val = self.value()
            handle_x = groove.left() + ((current_val - s_min) / s_range * groove.width())
            handle_y = groove.center().y()

            # Draw box at handle position
            box_width = 35
            box_height = 20
            # Clamp box position to stay within widget bounds (with 5px margin)
            margin = 5
            box_x = handle_x - box_width/2
            box_x = max(margin, min(box_x, self.width() - box_width - margin))
            box_rect = QtCore.QRectF(box_x, handle_y - box_height/2, box_width, box_height)

            # Box color based on slider type
            if self.is_world:
                box_color = QtGui.QColor(255, 215, 0, 230)  # Gold with transparency
                text_color = QtGui.QColor(40, 40, 40)  # Dark text
                border_color = QtGui.QColor(200, 160, 0)  # Darker gold border
            elif self.is_tw:
                box_color = QtGui.QColor(100, 180, 255, 230)  # Blue with transparency
                text_color = QtGui.QColor(255, 255, 255)  # White text
                border_color = QtGui.QColor(60, 120, 200)  # Darker blue border
            else:
                box_color = QtGui.QColor(150, 150, 150, 230)  # Grey with transparency
                text_color = QtGui.QColor(255, 255, 255)  # White text
                border_color = QtGui.QColor(100, 100, 100)  # Darker grey border

            # Draw border
            painter.setPen(QtGui.QPen(border_color, 2))
            painter.setBrush(box_color)
            painter.drawRoundedRect(box_rect, 4, 4)

            # Draw text
            painter.setPen(text_color)
            font = QtGui.QFont()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(box_rect, QtCore.Qt.AlignCenter, self.label_text)

        painter.end()


class VertexTweenerUI(QtWidgets.QDialog):
    instance = None

    @classmethod
    def show_dialog(cls):
        # Close and discard previous instance if it exists but is stale
        if cls.instance is not None:
            try:
                if not shiboken.isValid(cls.instance):
                    cls.instance = None
            except RuntimeError:
                cls.instance = None

        if cls.instance is None:
            cls.instance = VertexTweenerUI()

        cls.instance.show()
        cls.instance.raise_()
        cls.instance.activateWindow()
        return cls.instance

    def __init__(self, parent=None):
        if parent is None:
            ptr = omui.MQtUtil.mainWindow()
            parent = shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
        super(VertexTweenerUI, self).__init__(parent)
        
        self.setWindowTitle("Inbetweener v2.1")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setMinimumWidth(420)

        self.undo_chunk_open = False
        self.world_undo_chunk_open = False
        self.bn_undo_chunk_open = False
        self.bd_undo_chunk_open = False
        self.be_undo_chunk_open = False

        # Store original keyframe values for BN/BD/BE sliders
        self.bn_original_values = []
        self.bd_original_values = []
        self.be_original_values = []

        # Maya autoKeyframe state saved during slider drag
        self._saved_autokey_state = False

        self.create_widgets()
        self.create_layout()
        self.create_connections()
        self.on_accordion_toggled(self.accordion_toggle.isChecked())
        self.collapsed_size = self.sizeHint()

        # Load preferences — block signals to prevent triggering handlers during init
        self.overshoot_checkbox.setChecked(get_pref(PREF_OVERSHOOT_MODE, True))
        self.on_overshoot_toggled(self.overshoot_checkbox.isChecked())

        # All sliders start at their neutral center position
        self.slider.blockSignals(True)
        self.slider.setValue(50)
        self.slider.blockSignals(False)

        self.world_slider.blockSignals(True)
        self.world_slider.setRange(0, 100)
        self.world_slider.setValue(50)
        self.world_slider.blockSignals(False)

        self.bn_slider.blockSignals(True)
        self.bn_slider.setValue(50)
        self.bn_slider.blockSignals(False)

        self.bd_slider.blockSignals(True)
        self.bd_slider.setValue(0)
        self.bd_slider.blockSignals(False)

        self.be_slider.blockSignals(True)
        self.be_slider.setValue(50)
        self.be_slider.blockSignals(False)

        self._update_world_tick_labels()
        self._update_bn_tick_labels()
        self._update_bd_tick_labels()
        self._update_be_tick_labels()

        self.motion_trails_checkbox.setChecked(get_pref(PREF_MOTION_TRAILS, False))

    def _make_group_box(self, title, color="#5285A6"):
        """Create a styled group frame with a colored header bar."""
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame {{ background: #3a3a3a; border: 1px solid #555; border-radius: 4px; }}"
        )
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        header = QtWidgets.QLabel(title)
        header.setStyleSheet(
            "QLabel {{ color: {c}; font-weight: bold; font-size: 11px;"
            " background: transparent; border: none; padding: 2px 0; }}".format(c=color)
        )
        layout.addWidget(header)
        return frame, layout

    def _make_descriptor(self, text):
        """Create a small descriptor label for slider context."""
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(
            "color: #999; font-size: 9px; background: transparent; border: none;"
            " padding: 0 2px;"
        )
        lbl.setWordWrap(True)
        return lbl

    def create_widgets(self):
        # ---- Global stylesheet for modern Maya 2026 look ----
        self.setStyleSheet("""
            QDialog {
                background: #3c3c3c;
            }
            QPushButton {
                background: #4a4a4a; color: #ddd; border: 1px solid #666;
                border-radius: 3px; padding: 4px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #5a5a5a; border-color: #888; }
            QPushButton:pressed { background: #333; }
            QCheckBox { color: #ccc; font-size: 11px; spacing: 4px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            QToolButton {
                background: #4a4a4a; color: #ccc; border: 1px solid #555;
                border-radius: 3px; padding: 5px 10px; font-size: 11px;
            }
            QToolButton:hover { background: #555; }
            QToolButton:checked { background: #505050; border-color: #777; }
        """)

        self.menu_bar = QtWidgets.QMenuBar()
        help_menu = self.menu_bar.addMenu("Help")
        self.help_action = help_menu.addAction("Tool Guide && Reference")

        # ---- Value readout ----
        self.value_label = QtWidgets.QLabel("Local 50%")
        font = QtGui.QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.value_label.setFont(font)
        self.value_label.setAlignment(QtCore.Qt.AlignCenter)
        self.value_label.setStyleSheet("color: #E0E0E0; padding: 2px;")

        # ---- LOCAL TWEENER ----
        self.slider = VertexTickedSlider(QtCore.Qt.Horizontal, is_tw=True, is_world=False, label_text="LT")
        self.slider.setMinimumHeight(45)
        self.slider.setTracking(True)

        self.fraction_labels_top_layout = QtWidgets.QHBoxLayout()
        self.fraction_labels_bottom_layout = QtWidgets.QHBoxLayout()
        self.tick_labels_layout = QtWidgets.QHBoxLayout()

        # Quick preset buttons
        self.btn_0 = QtWidgets.QPushButton("0")
        self.btn_1_8 = QtWidgets.QPushButton("1/8")
        self.btn_1_4 = QtWidgets.QPushButton("1/4")
        self.btn_1_3 = QtWidgets.QPushButton("1/3")
        self.btn_1_2 = QtWidgets.QPushButton("1/2")
        self.btn_2_3 = QtWidgets.QPushButton("2/3")
        self.btn_3_4 = QtWidgets.QPushButton("3/4")
        self.btn_7_8 = QtWidgets.QPushButton("7/8")
        self.btn_1 = QtWidgets.QPushButton("1")

        # ---- WORLD TWEENER ----
        self.world_slider = VertexTickedSlider(QtCore.Qt.Horizontal, is_tw=True, is_world=True, label_text="WT")
        self.world_slider.setMinimumHeight(45)
        self.world_slider.setMinimumWidth(350)
        self.world_slider.setTracking(True)
        self.world_tick_labels_layout = QtWidgets.QHBoxLayout()

        # ---- Accordion ----
        self.accordion_toggle = QtWidgets.QToolButton()
        self.accordion_toggle.setText("  Blending Tools")
        self.accordion_toggle.setCheckable(True)
        self.accordion_toggle.setChecked(False)
        self.accordion_toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.accordion_toggle.setArrowType(QtCore.Qt.RightArrow)
        self.accordion_toggle.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.accordion_container = QtWidgets.QWidget()
        self.accordion_container.setVisible(False)

        # ---- BN SLIDER ----
        self.bn_slider = VertexTickedSlider(QtCore.Qt.Horizontal, is_tw=False, is_world=False, label_text="BN")
        self.bn_slider.setRange(0, 100)
        self.bn_slider.setValue(50)
        self.bn_slider.setMinimumHeight(45)
        self.bn_slider.setMinimumWidth(350)
        self.bn_tick_labels_layout = QtWidgets.QHBoxLayout()

        # ---- BD SLIDER ----
        self.bd_slider = VertexTickedSlider(QtCore.Qt.Horizontal, is_tw=False, is_world=False, label_text="BD")
        self.bd_slider.setRange(0, 100)
        self.bd_slider.setValue(0)
        self.bd_slider.setMinimumHeight(45)
        self.bd_slider.setMinimumWidth(350)
        self.bd_tick_labels_layout = QtWidgets.QHBoxLayout()

        # ---- BE SLIDER ----
        self.be_slider = VertexTickedSlider(QtCore.Qt.Horizontal, is_tw=False, is_world=False, label_text="BE")
        self.be_slider.setRange(0, 100)
        self.be_slider.setValue(50)
        self.be_slider.setMinimumHeight(45)
        self.be_slider.setMinimumWidth(350)
        self.be_tick_labels_layout = QtWidgets.QHBoxLayout()

        # ---- Scan Defaults button ----
        self.scan_defaults_btn = QtWidgets.QPushButton("Scan Default Pose")
        self.scan_defaults_btn.setToolTip(
            "Select rig controls (or root) in default pose, then click to store their rest values.\n"
            "Blend-to-Default will use these values instead of guessing 0/1."
        )

        # ---- Options ----
        self.motion_trails_checkbox = QtWidgets.QCheckBox("Motion Trails")
        self.motion_trails_checkbox.setToolTip("Display motion trail arcs for selected objects")
        self.overshoot_checkbox = QtWidgets.QCheckBox("Overshoot")
        self.overshoot_checkbox.setToolTip("Extend Local Tweener range to -50% / 150%")
        self.reset_btn = QtWidgets.QPushButton("Reset All")
        self.reset_btn.setToolTip("Reset all sliders to their neutral positions")

        # ---- Status bar ----
        self.status_label = QtWidgets.QLabel("Select objects or Graph Editor keys to begin")
        self.status_label.setStyleSheet(
            "color: #999; font-size: 10px; padding: 3px 6px;"
            " background: #333; border: 1px solid #444; border-radius: 3px;"
        )
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)

    def create_layout(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setMenuBar(self.menu_bar)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # ---- Value Readout ----
        main.addWidget(self.value_label)

        # ================================================================
        # LOCAL TWEENER GROUP
        # ================================================================
        lt_group, lt_layout = self._make_group_box("LOCAL TWEENER", "#6BB5FF")
        lt_layout.addWidget(self._make_descriptor(
            "Blends selected objects between previous and next keyframes at the current time. "
            "Works with transforms, joints, and any rig control with keyable attributes."
        ))
        self._populate_fraction_labels()
        lt_layout.addLayout(self.fraction_labels_top_layout)
        lt_layout.addLayout(self.fraction_labels_bottom_layout)
        lt_layout.addWidget(self.slider)
        lt_layout.addLayout(self.tick_labels_layout)

        # Quick preset row
        presets_row = QtWidgets.QHBoxLayout()
        presets_row.setSpacing(3)
        for b in [self.btn_0, self.btn_1_8, self.btn_1_4, self.btn_1_3,
                   self.btn_1_2, self.btn_2_3, self.btn_3_4, self.btn_7_8, self.btn_1]:
            b.setFixedHeight(22)
            presets_row.addWidget(b)
        lt_layout.addLayout(presets_row)

        # Options row inside LT group
        opts_row = QtWidgets.QHBoxLayout()
        opts_row.setSpacing(12)
        opts_row.addWidget(self.overshoot_checkbox)
        opts_row.addWidget(self.motion_trails_checkbox)
        opts_row.addStretch()
        lt_layout.addLayout(opts_row)

        main.addWidget(lt_group)

        # ================================================================
        # WORLD TWEENER GROUP
        # ================================================================
        wt_group, wt_layout = self._make_group_box("WORLD TWEENER", "#FFD700")
        wt_layout.addWidget(self._make_descriptor(
            "Blends in world space using matrix interpolation with quaternion slerp. "
            "Ideal for maintaining arcs on parented or space-switched controls."
        ))
        wt_layout.addWidget(self.world_slider)
        wt_layout.addLayout(self.world_tick_labels_layout)
        main.addWidget(wt_group)

        # ================================================================
        # ACCORDION: GRAPH EDITOR TOOLS
        # ================================================================
        main.addSpacing(4)
        main.addWidget(self.accordion_toggle)
        main.addWidget(self.accordion_container)

        self.accordion_layout = QtWidgets.QVBoxLayout(self.accordion_container)
        self.accordion_layout.setContentsMargins(0, 6, 0, 0)
        self.accordion_layout.setSpacing(6)

        # ---- BN GROUP ----
        bn_group, bn_layout = self._make_group_box("BLEND TO NEIGHBOR", "#7EC8A0")
        bn_layout.addWidget(self._make_descriptor(
            "Blends selected controls toward their neighboring keyframe values. "
            "Drag left for previous neighbor, right for next."
        ))
        bn_layout.addWidget(self.bn_slider)
        bn_layout.addLayout(self.bn_tick_labels_layout)
        self.accordion_layout.addWidget(bn_group)

        # ---- BD GROUP ----
        bd_group, bd_layout = self._make_group_box("BLEND TO DEFAULT", "#E8A87C")
        bd_layout.addWidget(self._make_descriptor(
            "Blends selected controls from their current values toward the rest pose. "
            "Use 'Scan Default Pose' to capture accurate rest values from your rig."
        ))
        bd_layout.addWidget(self.bd_slider)
        bd_layout.addLayout(self.bd_tick_labels_layout)

        # Scan Defaults row
        scan_row = QtWidgets.QHBoxLayout()
        scan_row.addWidget(self.scan_defaults_btn)
        self.scan_defaults_status = QtWidgets.QLabel("")
        self.scan_defaults_status.setStyleSheet(
            "color: #999; font-size: 10px; background: transparent; border: none;"
        )
        scan_row.addWidget(self.scan_defaults_status)
        scan_row.addStretch()
        bd_layout.addLayout(scan_row)
        self._refresh_scan_defaults_status()

        self.accordion_layout.addWidget(bd_group)

        # ---- BE GROUP ----
        be_group, be_layout = self._make_group_box("BLEND TO EASE", "#C49BD6")
        be_layout.addWidget(self._make_descriptor(
            "Applies cubic easing curves to selected controls at current time. "
            "Drag left for ease-out (decelerate), right for ease-in (accelerate)."
        ))
        be_layout.addWidget(self.be_slider)
        be_layout.addLayout(self.be_tick_labels_layout)
        self.accordion_layout.addWidget(be_group)

        # ---- Reset ----
        self.accordion_layout.addWidget(self.reset_btn)

        # ================================================================
        # STATUS BAR
        # ================================================================
        main.addWidget(self.status_label)

    def create_connections(self):
        # Local Tweener
        self.slider.valueChanged.connect(self.on_slider_changed)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)

        # World Tweener
        self.world_slider.valueChanged.connect(self.on_world_slider_changed)
        self.world_slider.sliderPressed.connect(self.on_world_slider_pressed)
        self.world_slider.sliderReleased.connect(self.on_world_slider_released)

        # Blend to Neighbor
        self.bn_slider.valueChanged.connect(self.on_bn_changed)
        self.bn_slider.sliderPressed.connect(self.on_bn_pressed)
        self.bn_slider.sliderReleased.connect(self.on_bn_released)

        # Blend to Default
        self.bd_slider.valueChanged.connect(self.on_bd_changed)
        self.bd_slider.sliderPressed.connect(self.on_bd_pressed)
        self.bd_slider.sliderReleased.connect(self.on_bd_released)

        # Blend to Ease
        self.be_slider.valueChanged.connect(self.on_be_changed)
        self.be_slider.sliderPressed.connect(self.on_be_pressed)
        self.be_slider.sliderReleased.connect(self.on_be_released)

        # Quick Snap Buttons (apply to both local and world sliders)
        self.btn_1_8.clicked.connect(lambda: self.set_slider_fraction(1, 8))
        self.btn_1_4.clicked.connect(lambda: self.set_slider_fraction(1, 4))
        self.btn_1_2.clicked.connect(lambda: self.set_slider_fraction(1, 2))
        self.btn_3_4.clicked.connect(lambda: self.set_slider_fraction(3, 4))
        self.btn_7_8.clicked.connect(lambda: self.set_slider_fraction(7, 8))

        self.btn_0.clicked.connect(lambda: self.set_slider_fraction(0, 1))
        self.btn_1_3.clicked.connect(lambda: self.set_slider_fraction(1, 3))
        self.btn_2_3.clicked.connect(lambda: self.set_slider_fraction(2, 3))
        self.btn_1.clicked.connect(lambda: self.set_slider_fraction(1, 1))

        # Scan Defaults
        self.scan_defaults_btn.clicked.connect(self.on_scan_defaults)

        # Options
        self.reset_btn.clicked.connect(self.reset_all)
        self.overshoot_checkbox.toggled.connect(self.on_overshoot_toggled)
        self.motion_trails_checkbox.toggled.connect(self.on_trails_toggled)
        self.help_action.triggered.connect(self.show_help_dialog)
        self.accordion_toggle.toggled.connect(self.on_accordion_toggled)

    def on_slider_changed(self, value):
        self.value_label.setText("Local {}%".format(value))
        # Use cached data for fast drag — no Maya queries during drag
        if TweenEngine._cached_attrs:
            count = TweenEngine.apply_cached_tween(value)
            if count:
                self.status_label.setText("Tweening {} attribute{}".format(count, 's' if count != 1 else ''))
            if self.motion_trails_checkbox.isChecked():
                MotionTrailsManager.refresh_motion_trails()

    def on_slider_pressed(self):
        self.slider.keyed_value = None
        self.slider.update()
        self._suspend_maya_autokey()
        self.undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexTW")
        # Cache all keyframe data up front — the only expensive query
        cached = TweenEngine.cache_selection()
        if not cached:
            self.status_label.setText("No keyframes found on selection")

    def on_slider_released(self):
        final_val = self.slider.value()

        # Apply final value from cache to ensure it sticks
        if TweenEngine._cached_attrs:
            TweenEngine.apply_cached_tween(final_val)

        # Always set keyframes to lock in the tween
        self._auto_key_current_position()

        if self.undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.undo_chunk_open = False

        self._restore_maya_autokey()
        TweenEngine.clear_cache()

        # Show keyed position tick, then reset slider to center
        self.slider.keyed_value = final_val
        self.slider.blockSignals(True)
        self.slider.setValue(50)
        self.slider.blockSignals(False)
        self.slider.update()
        self.value_label.setText("Local 50%")
        self.status_label.setText("Keyed at {}%".format(final_val))

    def on_world_slider_changed(self, value):
        self.value_label.setText("World {}%".format(value))
        count = WorldTweenEngine.apply_world_tween(value)
        if count:
            self.status_label.setText("World tweening {} object{}".format(count, 's' if count != 1 else ''))
        else:
            self.status_label.setText("No keyframes found on selection")
        if self.motion_trails_checkbox.isChecked(): MotionTrailsManager.refresh_motion_trails()

    def on_world_slider_pressed(self):
        self.world_slider.keyed_value = None
        self.world_slider.update()
        self._suspend_maya_autokey()
        self.world_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="WorldTW")

    def on_world_slider_released(self):
        final_val = self.world_slider.value()

        # Always set keyframes to lock in the tween
        self._auto_key_current_position()

        if self.world_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.world_undo_chunk_open = False

        self._restore_maya_autokey()

        # Show keyed position tick, then reset slider to center
        self.world_slider.keyed_value = final_val
        self.world_slider.blockSignals(True)
        self.world_slider.setValue(50)
        self.world_slider.blockSignals(False)
        self.world_slider.update()
        self.value_label.setText("World 50%")
        self.status_label.setText("Keyed at {}%".format(final_val))

    def on_bn_changed(self, value):
        self.value_label.setText("BN {}%".format(value))
        if value == 50 or not self.bn_original_values:
            if value == 50:
                self.status_label.setText("BN neutral")
            return

        if value < 50:
            blend_to_next = False
            weight = (50 - value) / 50.0
        else:
            blend_to_next = True
            weight = (value - 50) / 50.0

        count = 0
        for entry in self.bn_original_values:
            full_attr = entry['attr']
            original_val = entry['original']
            prev_val = entry.get('prev')
            next_val = entry.get('next')

            target_val = next_val if blend_to_next else prev_val
            if target_val is None:
                continue

            new_val = original_val + (target_val - original_val) * weight
            try:
                cmds.setAttr(full_attr, new_val)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                continue

        if count:
            self.status_label.setText("Blending {} attribute{}".format(count, 's' if count != 1 else ''))
        else:
            self.status_label.setText("No neighbor keyframes found")

    def on_bn_pressed(self):
        self.bn_slider.keyed_value = None
        self.bn_slider.update()
        self._suspend_maya_autokey()
        self.bn_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexBN")

        # Cache current values and neighbor values for all selected controls
        self.bn_original_values = []
        selection = cmds.ls(selection=True)
        if not selection:
            return

        current_time = cmds.currentTime(query=True)

        for obj in selection:
            keyable_attrs = cmds.listAttr(obj, keyable=True) or []
            for attr in keyable_attrs:
                full_attr = "{}.{}".format(obj, attr)
                try:
                    if cmds.getAttr(full_attr, lock=True):
                        continue
                except (RuntimeError, TypeError, ValueError):
                    continue

                keyframes = cmds.keyframe(full_attr, query=True, timeChange=True)
                if not keyframes or len(keyframes) < 2:
                    continue

                # Find the key at current time (or closest)
                current_val = cmds.getAttr(full_attr)
                if not isinstance(current_val, (int, float)):
                    continue

                # Find prev and next keyframe values relative to current time
                prev_val = None
                next_val = None
                for kf_time in keyframes:
                    if kf_time < current_time - 0.001:
                        prev_val = cmds.getAttr(full_attr, time=kf_time)
                    elif kf_time > current_time + 0.001:
                        next_val = cmds.getAttr(full_attr, time=kf_time)
                        break

                # Skip if no neighbors at all
                if prev_val is None and next_val is None:
                    continue

                # Validate scalar
                if prev_val is not None and not isinstance(prev_val, (int, float)):
                    prev_val = None
                if next_val is not None and not isinstance(next_val, (int, float)):
                    next_val = None

                if prev_val is None and next_val is None:
                    continue

                self.bn_original_values.append({
                    'attr': full_attr,
                    'original': current_val,
                    'prev': prev_val,
                    'next': next_val,
                })

        if not self.bn_original_values:
            self.status_label.setText("No neighbor keyframes found on selection")

    def on_bn_released(self):
        final_val = self.bn_slider.value()

        # Apply final value
        if self.bn_original_values:
            if final_val != 50:
                self.on_bn_changed(final_val)
            # Always set keyframes to lock in the blend
            self._auto_key_current_position()

        if self.bn_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.bn_undo_chunk_open = False
        self._restore_maya_autokey()
        self.bn_original_values = []

        # Show keyed position tick, then reset slider to center
        self.bn_slider.keyed_value = final_val
        self.bn_slider.blockSignals(True)
        self.bn_slider.setValue(50)
        self.bn_slider.blockSignals(False)
        self.bn_slider.update()
        self.value_label.setText("BN 50%")
        self.status_label.setText("Keyed at BN {}%".format(final_val))

    def on_bd_changed(self, value):
        """BD slider: Blend from original pose (at 0) toward default/rest pose (at 100)."""
        self.value_label.setText("BD {}%".format(value))
        if value == 0 or not self.bd_original_values:
            return

        n_weight = value / 100.0
        count = 0

        for entry in self.bd_original_values:
            new_val = entry['original'] + (entry['default'] - entry['original']) * n_weight
            try:
                cmds.setAttr(entry['attr'], new_val)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                continue

        if count:
            self.status_label.setText("Blending {} attribute{} to default".format(count, 's' if count != 1 else ''))
        else:
            self.status_label.setText("No attributes found")

    def on_bd_pressed(self):
        self.bd_slider.keyed_value = None
        self.bd_slider.update()
        self._suspend_maya_autokey()
        self.bd_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexBD")

        self.bd_original_values = []
        selection = cmds.ls(selection=True)
        if not selection:
            return

        # Prompt user if no default pose has been scanned yet
        if not DefaultPoseStore.has_stored_defaults():
            result = cmds.confirmDialog(
                title='Scan Default Pose',
                message=(
                    'No default pose has been scanned for this rig.\n\n'
                    'For accurate results, select your rig controls (or root) '
                    'while in the default/bind pose, then click "Scan Default Pose" '
                    'in the Blend to Default section.\n\n'
                    'Continue anyway using Maya attribute defaults?'
                ),
                button=['Continue', 'Cancel'],
                defaultButton='Cancel',
                cancelButton='Cancel',
                dismissString='Cancel',
            )
            if result != 'Continue':
                self.status_label.setText("Scan default pose first for accurate BD blending")
                return

        for obj in selection:
            keyable_attrs = cmds.listAttr(obj, keyable=True) or []
            for attr in keyable_attrs:
                full_attr = "{}.{}".format(obj, attr)
                try:
                    if cmds.getAttr(full_attr, lock=True):
                        continue
                except (RuntimeError, TypeError, ValueError):
                    continue

                # Only process attributes that have animation
                if not cmds.keyframe(full_attr, query=True, keyframeCount=True):
                    continue

                current_val = cmds.getAttr(full_attr)
                if not isinstance(current_val, (int, float)):
                    continue

                # Look up stored default — scanned node > Maya default > fallback
                default_val = DefaultPoseStore.get_default(full_attr)

                self.bd_original_values.append({
                    'attr': full_attr,
                    'original': current_val,
                    'default': default_val,
                })

        if not self.bd_original_values:
            self.status_label.setText("No animated attributes on selection")

    def on_bd_released(self):
        final_val = self.bd_slider.value()

        if self.bd_original_values:
            if final_val != 0:
                self.on_bd_changed(final_val)
            # Always set keyframes to lock in the blend
            self._auto_key_current_position()

        if self.bd_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.bd_undo_chunk_open = False
        self._restore_maya_autokey()
        self.bd_original_values = []

        # Show keyed position tick, then reset slider to zero
        self.bd_slider.keyed_value = final_val
        self.bd_slider.blockSignals(True)
        self.bd_slider.setValue(0)
        self.bd_slider.blockSignals(False)
        self.bd_slider.update()
        self.value_label.setText("BD 0%")
        self.status_label.setText("Keyed at BD {}%".format(final_val))

    def on_be_changed(self, value):
        """BE slider: Blend toward eased position using pre-computed targets."""
        self.value_label.setText("BE {}%".format(value))
        if value == 50 or not self.be_original_values:
            if value == 50:
                self.status_label.setText("BE neutral")
            return

        weight = abs(value - 50) / 50.0
        blend_to_next = value > 50
        count = 0

        for entry in self.be_original_values:
            eased_val = entry['ease_in'] if blend_to_next else entry['ease_out']
            new_val = entry['original'] + (eased_val - entry['original']) * weight
            try:
                cmds.setAttr(entry['attr'], new_val)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                continue

        if count:
            self.status_label.setText("Easing {} attribute{}".format(count, 's' if count != 1 else ''))
        else:
            self.status_label.setText("No attributes found")

    def on_be_pressed(self):
        self.be_slider.keyed_value = None
        self.be_slider.update()
        self._suspend_maya_autokey()
        self.be_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexBE")

        self.be_original_values = []
        selection = cmds.ls(selection=True)
        if not selection:
            return

        current_time = cmds.currentTime(query=True)

        for obj in selection:
            keyable_attrs = cmds.listAttr(obj, keyable=True) or []
            for attr in keyable_attrs:
                full_attr = "{}.{}".format(obj, attr)
                try:
                    if cmds.getAttr(full_attr, lock=True):
                        continue
                except (RuntimeError, TypeError, ValueError):
                    continue

                keyframes = cmds.keyframe(full_attr, query=True, timeChange=True)
                if not keyframes or len(keyframes) < 3:
                    continue

                current_val = cmds.getAttr(full_attr)
                if not isinstance(current_val, (int, float)):
                    continue

                # Find prev and next keyframe times
                prev_time = None
                next_time = None
                for kf_time in keyframes:
                    if kf_time < current_time - 0.001:
                        prev_time = kf_time
                    elif kf_time > current_time + 0.001:
                        next_time = kf_time
                        break

                if prev_time is None or next_time is None:
                    continue

                prev_val = cmds.getAttr(full_attr, time=prev_time)
                next_val = cmds.getAttr(full_attr, time=next_time)

                if not isinstance(prev_val, (int, float)) or not isinstance(next_val, (int, float)):
                    continue

                time_range = next_time - prev_time
                if time_range == 0:
                    continue

                t = (current_time - prev_time) / time_range
                ease_in_t = t * t * t
                ease_out_t = 1 - pow(1 - t, 3)

                self.be_original_values.append({
                    'attr': full_attr,
                    'original': current_val,
                    'ease_in': prev_val + (next_val - prev_val) * ease_in_t,
                    'ease_out': prev_val + (next_val - prev_val) * ease_out_t,
                })

        if not self.be_original_values:
            self.status_label.setText("Need 3+ keyframes for easing")

    def on_be_released(self):
        final_val = self.be_slider.value()

        if self.be_original_values:
            if final_val != 50:
                self.on_be_changed(final_val)
            # Always set keyframes to lock in the blend
            self._auto_key_current_position()

        if self.be_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.be_undo_chunk_open = False
        self._restore_maya_autokey()
        self.be_original_values = []

        # Show keyed position tick, then reset slider to center
        self.be_slider.keyed_value = final_val
        self.be_slider.blockSignals(True)
        self.be_slider.setValue(50)
        self.be_slider.blockSignals(False)
        self.be_slider.update()
        self.value_label.setText("BE 50%")
        self.status_label.setText("Keyed at BE {}%".format(final_val))

    def on_scan_defaults(self):
        """Scan selected controls' current pose as the default/rest pose."""
        selection = cmds.ls(selection=True)
        if not selection:
            self.status_label.setText("Select rig controls or root joint in default pose first")
            return

        # Show confirmation dialog (unless user opted out)
        if not get_pref(PREF_SKIP_SCAN_CONFIRM, False):
            if not self._show_scan_confirm_dialog():
                return

        count = DefaultPoseStore.scan_defaults()
        if count:
            self.status_label.setText("Stored {} default attribute values".format(count))
        else:
            self.status_label.setText("No keyable attributes found on selection")
        self._refresh_scan_defaults_status()

    def _show_scan_confirm_dialog(self):
        """Show a confirmation dialog before scanning the default pose.

        Returns True if the user confirmed, False if they cancelled.
        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Scan Default Pose")
        dialog.setFixedWidth(460)
        dialog.setStyleSheet("""
            QDialog { background: #3c3c3c; }
            QLabel { color: #ddd; background: transparent; border: none; }
            QPushButton {
                padding: 8px 24px; font-size: 12px; font-weight: bold;
                border-radius: 4px; border: 1px solid #555;
            }
            QCheckBox { color: #aaa; font-size: 11px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
        """)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # --- Header row: warning icon + title/subtitle ---
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(14)

        # Warning icon (using Qt's built-in standard icon)
        icon_label = QtWidgets.QLabel()
        style = dialog.style()
        warning_icon = style.standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning)
        icon_label.setPixmap(warning_icon.pixmap(48, 48))
        icon_label.setFixedSize(52, 52)
        icon_label.setAlignment(QtCore.Qt.AlignTop)
        header_row.addWidget(icon_label)

        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(4)
        title_lbl = QtWidgets.QLabel("Is this the Default Pose?")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        title_col.addWidget(title_lbl)

        subtitle_lbl = QtWidgets.QLabel(
            "Your character must be in its rest position (T-Pose, A-Pose, or bind pose) "
            "before capturing. All selected controllers and their children will be scanned."
        )
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setStyleSheet("font-size: 11px; color: #bbb;")
        title_col.addWidget(subtitle_lbl)
        header_row.addLayout(title_col, 1)
        layout.addLayout(header_row)

        # --- Viewport snapshot placeholder ---
        snap_frame = QtWidgets.QFrame()
        snap_frame.setFixedHeight(160)
        snap_frame.setStyleSheet(
            "QFrame { background: #2b2b2b; border: 1px solid #555; border-radius: 6px; }"
        )
        snap_layout = QtWidgets.QVBoxLayout(snap_frame)
        snap_layout.setAlignment(QtCore.Qt.AlignCenter)

        # Try to load defaultPose.png from the same directory as the script
        image_loaded = False
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            script_dir = cmds.internalVar(userScriptDir=True)

        for search_dir in [script_dir, cmds.internalVar(userScriptDir=True)]:
            img_path = os.path.join(search_dir, 'defaultPose.png')
            if os.path.isfile(img_path):
                pixmap = QtGui.QPixmap(img_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaledToHeight(140, QtCore.Qt.SmoothTransformation)
                    img_label = QtWidgets.QLabel()
                    img_label.setPixmap(scaled)
                    img_label.setAlignment(QtCore.Qt.AlignCenter)
                    img_label.setStyleSheet("border: none;")
                    snap_layout.addWidget(img_label)
                    image_loaded = True
                    break

        if not image_loaded:
            placeholder = QtWidgets.QLabel("Ensure your rig is in the default pose\nbefore clicking Yes")
            placeholder.setAlignment(QtCore.Qt.AlignCenter)
            placeholder.setStyleSheet(
                "color: #888; font-size: 13px; font-style: italic; border: none;"
            )
            snap_layout.addWidget(placeholder)

        layout.addWidget(snap_frame)

        # --- Tip text ---
        tip_lbl = QtWidgets.QLabel(
            "The best way to capture accurate defaults is to reference the rig into a fresh "
            "Maya session with no animation applied. You don't need to close this session \u2014 "
            "the stored defaults will be shared across all scenes."
        )
        tip_lbl.setWordWrap(True)
        tip_lbl.setStyleSheet("font-size: 11px; color: #999; padding: 0 4px;")
        layout.addWidget(tip_lbl)

        # --- Don't show again checkbox ---
        skip_cb = QtWidgets.QCheckBox("Don't show this again")
        layout.addWidget(skip_cb)

        # --- Button row ---
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)

        yes_btn = QtWidgets.QPushButton("\u2713  Yes")
        yes_btn.setStyleSheet(
            "QPushButton { background: #4a7a5a; color: #fff; }"
            "QPushButton:hover { background: #5a9a6a; }"
        )
        yes_btn.setFixedHeight(36)
        yes_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        no_btn = QtWidgets.QPushButton("No")
        no_btn.setStyleSheet(
            "QPushButton { background: #555; color: #ccc; }"
            "QPushButton:hover { background: #666; }"
        )
        no_btn.setFixedHeight(36)
        no_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        btn_row.addWidget(yes_btn, 2)
        btn_row.addWidget(no_btn, 1)
        layout.addLayout(btn_row)

        # --- Connections ---
        confirmed = [False]

        def on_yes():
            confirmed[0] = True
            if skip_cb.isChecked():
                set_pref(PREF_SKIP_SCAN_CONFIRM, True)
            dialog.accept()

        def on_no():
            dialog.reject()

        yes_btn.clicked.connect(on_yes)
        no_btn.clicked.connect(on_no)

        dialog.exec_()
        return confirmed[0]

    def _refresh_scan_defaults_status(self):
        """Update the label next to the Scan Defaults button."""
        if DefaultPoseStore.has_stored_defaults():
            self.scan_defaults_status.setText("Defaults stored")
            self.scan_defaults_status.setStyleSheet(
                "color: #88CC88; font-size: 10px; background: transparent; border: none;"
            )
        else:
            self.scan_defaults_status.setText("No defaults scanned")
            self.scan_defaults_status.setStyleSheet(
                "color: #CC8888; font-size: 10px; background: transparent; border: none;"
            )

    def _suspend_maya_autokey(self):
        """Temporarily disable Maya's native autoKeyframe during slider drag.

        This prevents Maya from auto-keying on every setAttr call, which causes
        the 'autoKeyframe; // Result: 1' spam and creates unwanted mid-drag keys.
        """
        try:
            self._saved_autokey_state = cmds.autoKeyframe(q=True, state=True)
            if self._saved_autokey_state:
                cmds.autoKeyframe(state=False)
        except RuntimeError:
            self._saved_autokey_state = False

    def _restore_maya_autokey(self):
        """Restore Maya's autoKeyframe to its state before the drag started."""
        try:
            if self._saved_autokey_state:
                cmds.autoKeyframe(state=True)
        except RuntimeError:
            pass

    def _auto_key_current_position(self):
        """Set keyframes on all selected objects at current time to lock in the tween.

        Keys any keyable attribute that already has animation curves,
        supporting transforms, joints, and custom rig controls.
        """
        selection = cmds.ls(selection=True)
        if not selection:
            return

        current_time = cmds.currentTime(query=True)
        for obj in selection:
            keyable_attrs = cmds.listAttr(obj, keyable=True) or []
            for attr in keyable_attrs:
                full_attr = "{}.{}".format(obj, attr)
                try:
                    if cmds.getAttr(full_attr, lock=True):
                        continue
                    # Only key attributes that already have animation
                    if cmds.keyframe(full_attr, query=True, keyframeCount=True):
                        cmds.setKeyframe(full_attr, time=current_time)
                except (RuntimeError, TypeError):
                    continue

    def _populate_fraction_labels(self):
        for layout in (self.fraction_labels_top_layout, self.fraction_labels_bottom_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()

        top_fractions = [("1/8", 1, 8), ("1/4", 1, 4), ("1/2", 1, 2), ("3/4", 3, 4), ("7/8", 7, 8)]
        bottom_fractions = [("0", 0, 1), ("1/3", 1, 3), ("2/3", 2, 3), ("1", 1, 1)]

        self._add_fraction_labels(self.fraction_labels_top_layout, top_fractions)
        self._add_fraction_labels(self.fraction_labels_bottom_layout, bottom_fractions)

    def _add_fraction_labels(self, layout, fractions):
        positions = [(label, float(num) / float(den)) for label, num, den in fractions]
        positions.sort(key=lambda item: item[1])

        current_pos = 0.0
        for label, pos in positions:
            stretch = max(0, int(round((pos - current_pos) * 100)))
            layout.addStretch(stretch)
            lbl = QtWidgets.QLabel(label); lbl.setStyleSheet("color: #888; font-size: 9px;")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            layout.addWidget(lbl)
            current_pos = pos

        trailing_stretch = max(0, int(round((1.0 - current_pos) * 100)))
        layout.addStretch(trailing_stretch)

    def set_slider_val(self, val):
        """Quick button handler - applies tween, keys, then resets to center."""
        self._suspend_maya_autokey()
        cmds.undoInfo(openChunk=True)

        # One-shot full query-and-apply (no drag, so no need for cache)
        TweenEngine.apply_tween(val)

        # Always key to lock in the position
        self._auto_key_current_position()

        cmds.undoInfo(closeChunk=True)
        self._restore_maya_autokey()

        # Show keyed position tick, then reset slider to center
        self.slider.keyed_value = val
        self.slider.blockSignals(True)
        self.slider.setValue(50)
        self.slider.blockSignals(False)
        self.slider.update()

        self.value_label.setText("Local 50%")
        self.status_label.setText("Keyed at {}%".format(val))

    def set_slider_fraction(self, numerator, denominator):
        value = int(round(100.0 * (float(numerator) / float(denominator))))
        self.set_slider_val(value)

    def reset_all(self):
        """Reset all sliders to center position."""
        self.slider.blockSignals(True)
        self.slider.setValue(50)
        self.slider.blockSignals(False)

        self.world_slider.blockSignals(True)
        self.world_slider.setValue(50)
        self.world_slider.blockSignals(False)

        self.bn_slider.blockSignals(True)
        self.bn_slider.setValue(50)
        self.bn_slider.blockSignals(False)

        self.bd_slider.blockSignals(True)
        self.bd_slider.setValue(0)
        self.bd_slider.blockSignals(False)

        self.be_slider.blockSignals(True)
        self.be_slider.setValue(50)
        self.be_slider.blockSignals(False)

        self.value_label.setText("50%")

    def on_overshoot_toggled(self, checked):
        set_pref(PREF_OVERSHOOT_MODE, checked)
        # Only Local Tweener supports overshoot
        if checked:
            self.slider.setRange(-50, 150)
        else:
            self.slider.setRange(0, 100)
        self._update_tick_labels(checked)
        # World slider always stays 0-100 (no overshoot)

    def on_trails_toggled(self, checked):
        set_pref(PREF_MOTION_TRAILS, checked)
        MotionTrailsManager.toggle_motion_trails(checked)

    def on_accordion_toggled(self, checked):
        self.accordion_container.setVisible(checked)
        self.accordion_toggle.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
        self.adjustSize()
        if not checked:
            self.collapsed_size = self.sizeHint()
            self.resize(self.collapsed_size)

    def _update_tick_labels(self, overshoot):
        while self.tick_labels_layout.count():
            item = self.tick_labels_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        ticks = [(-50, "-50%"), (0, "0%"), (50, "50%"), (100, "100%"), (150, "150%")] if overshoot else [(0, "0%"), (50, "50%"), (100, "100%")]
        for i, (v, t) in enumerate(ticks):
            lbl = QtWidgets.QLabel(t); lbl.setStyleSheet("color: #666; font-size: 9px;")
            lbl.setAlignment(QtCore.Qt.AlignLeft if i==0 else QtCore.Qt.AlignRight if i==len(ticks)-1 else QtCore.Qt.AlignCenter)
            self.tick_labels_layout.addWidget(lbl, 1 if i not in [0, len(ticks)-1] else 0)

    def _update_world_tick_labels(self):
        while self.world_tick_labels_layout.count():
            item = self.world_tick_labels_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # World tweener always uses 0-100% range (no overshoot)
        ticks = [(0, "0%"), (50, "50%"), (100, "100%")]
        for i, (v, t) in enumerate(ticks):
            lbl = QtWidgets.QLabel(t); lbl.setStyleSheet("color: #666; font-size: 9px;")
            lbl.setAlignment(QtCore.Qt.AlignLeft if i==0 else QtCore.Qt.AlignRight if i==len(ticks)-1 else QtCore.Qt.AlignCenter)
            self.world_tick_labels_layout.addWidget(lbl, 1 if i not in [0, len(ticks)-1] else 0)

    def _update_bn_tick_labels(self):
        while self.bn_tick_labels_layout.count():
            item = self.bn_tick_labels_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        ticks = [(0, "Prev"), (50, "50"), (100, "Next")]
        for i, (v, t) in enumerate(ticks):
            lbl = QtWidgets.QLabel(t); lbl.setStyleSheet("color: #666; font-size: 9px;")
            lbl.setAlignment(QtCore.Qt.AlignLeft if i == 0 else QtCore.Qt.AlignRight if i == len(ticks) - 1 else QtCore.Qt.AlignCenter)
            self.bn_tick_labels_layout.addWidget(lbl, 1 if i not in [0, len(ticks) - 1] else 0)

    def _update_bd_tick_labels(self):
        while self.bd_tick_labels_layout.count():
            item = self.bd_tick_labels_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        ticks = [(0, "Original"), (50, "50%"), (100, "Default")]
        for i, (v, t) in enumerate(ticks):
            lbl = QtWidgets.QLabel(t); lbl.setStyleSheet("color: #666; font-size: 9px;")
            lbl.setAlignment(QtCore.Qt.AlignLeft if i == 0 else QtCore.Qt.AlignRight if i == len(ticks) - 1 else QtCore.Qt.AlignCenter)
            self.bd_tick_labels_layout.addWidget(lbl, 1 if i not in [0, len(ticks) - 1] else 0)

    def _update_be_tick_labels(self):
        while self.be_tick_labels_layout.count():
            item = self.be_tick_labels_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        ticks = [(0, "Ease Out"), (50, "50"), (100, "Ease In")]
        for i, (v, t) in enumerate(ticks):
            lbl = QtWidgets.QLabel(t); lbl.setStyleSheet("color: #666; font-size: 9px;")
            lbl.setAlignment(QtCore.Qt.AlignLeft if i == 0 else QtCore.Qt.AlignRight if i == len(ticks) - 1 else QtCore.Qt.AlignCenter)
            self.be_tick_labels_layout.addWidget(lbl, 1 if i not in [0, len(ticks) - 1] else 0)

    def closeEvent(self, event):
        MotionTrailsManager.delete_motion_trails()
        self._restore_maya_autokey()
        if self.undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.world_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.bn_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.bd_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.be_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        super(VertexTweenerUI, self).closeEvent(event)

    def show_help_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Inbetweener v2.1 - Help")
        dialog.setMinimumSize(520, 600)
        layout = QtWidgets.QVBoxLayout(dialog)

        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml("""
        <style>
            body { font-family: monospace; color: #DDD; background: #2b2b2b; }
            h2 { color: #6BB5FF; border-bottom: 1px solid #555; padding-bottom: 4px; }
            h3 { color: #FFD700; margin-bottom: 4px; }
            .section { margin-bottom: 12px; }
            .key { color: #FF9966; font-weight: bold; }
            .tip { color: #88CC88; }
            ul { margin-top: 2px; }
            li { margin-bottom: 2px; }
        </style>
        <h2>Overview</h2>
        <div class="section">
            <p>The <b>Inbetweener Tool</b> provides five slider modes for creating breakdowns
            and refining animation curves in Autodesk Maya. It works with <b>transforms, joints,
            NURBS curve controls</b>, and any object with keyable attributes.</p>
            <p>Version 2.1.0 &mdash; Pipeline Tools</p>
        </div>

        <h2>Local Tweener (LT)</h2>
        <div class="section">
            <p>Blends the current pose between the <b>previous</b> and <b>next</b> keyframes
            at the current time.</p>
            <ul>
                <li><span class="key">0%</span> = Previous keyframe pose</li>
                <li><span class="key">50%</span> = Halfway between (linear interpolation)</li>
                <li><span class="key">100%</span> = Next keyframe pose</li>
                <li><span class="key">Overshoot</span>: -50% to 150% for exaggerated motion</li>
            </ul>
            <p><b>Selection:</b> Select objects in the viewport, or select specific attributes
            via Graph Editor keyframes. Works with transforms, joints, and custom rig controls.</p>
            <p><b>Quick Buttons:</b> 1/8, 1/4, 1/2, 3/4, 7/8 and 0, 1/3, 2/3, 1 for precise
            common breakdown positions.</p>
        </div>

        <h2>World Tweener (WT)</h2>
        <div class="section">
            <p>Blends objects in <b>world space</b> using matrix interpolation with quaternion
            slerp for rotation. No viewport flickering.</p>
            <ul>
                <li>Range: <span class="key">0%</span> to <span class="key">100%</span> (no overshoot)</li>
                <li>Ideal for maintaining world-space arcs on constrained or parented controls</li>
                <li>Works with transforms and joints</li>
            </ul>
            <p><b>When to use:</b> When local-space tweening produces incorrect arcs due to
            parent space changes between keys (e.g., IK/FK switching, space-matched controls).</p>
        </div>

        <h2>Blend to Neighbor (BN)</h2>
        <div class="section">
            <p>Blends <b>selected Graph Editor keyframes</b> toward their neighboring keys.</p>
            <ul>
                <li><span class="key">&lt; 50</span>: Blend toward <b>previous</b> neighbor key</li>
                <li><span class="key">&gt; 50</span>: Blend toward <b>next</b> neighbor key</li>
                <li><span class="key">50</span>: No change (neutral)</li>
            </ul>
            <p><b>Selection:</b> Select controls in the viewport, or select keys in the Graph Editor.</p>
            <p><b>Use cases:</b> Smoothing motion, pulling timing toward holds, evening out spacing.</p>
        </div>

        <h2>Blend to Default (BD)</h2>
        <div class="section">
            <p>Blends selected controls from their <b>current values</b> toward the <b>rest pose</b>.</p>
            <ul>
                <li><span class="key">0</span>: Original values (no change)</li>
                <li><span class="key">100</span>: Default/rest pose</li>
            </ul>
            <p><b>Scan Default Pose:</b> Select your rig controls (or root) while in the
            default pose, then click &ldquo;Scan Default Pose&rdquo; to store accurate rest
            values. Without scanning, BD falls back to 0 for translate/rotate and 1 for scale.</p>
            <p><b>Selection:</b> Select controls in the viewport, or select keys in the Graph Editor.</p>
            <p><b>Use cases:</b> Zeroing out overshoot, resetting controls to neutral,
            reducing extreme poses.</p>
        </div>

        <h2>Blend to Ease (BE)</h2>
        <div class="section">
            <p>Calculates <b>cubic eased positions</b> and blends selected controls toward them
            for natural acceleration/deceleration.</p>
            <ul>
                <li><span class="key">&gt; 50</span>: Ease-in (slow start, accelerate — t&sup3;)</li>
                <li><span class="key">&lt; 50</span>: Ease-out (fast start, decelerate — 1-(1-t)&sup3;)</li>
                <li><span class="key">50</span>: No change (neutral)</li>
            </ul>
            <p><b>Selection:</b> Select controls in the viewport, or select keys in the Graph Editor.
            Controls need keyframes on both sides of the current time.</p>
        </div>

        <h2>Options</h2>
        <div class="section">
            <ul>
                <li><span class="key">Auto Keying</span>: All sliders automatically set keyframes
                on release. A green diamond tick marks the keyed position on the slider.</li>
                <li><span class="key">Motion Trails</span>: Displays motion trail arcs for selected
                objects to visualize the animation path.</li>
                <li><span class="key">Overshoot Mode</span>: Extends Local Tweener range to
                -50% / 150% for exaggerated breakdown poses.</li>
                <li><span class="key">Scan Default Pose</span>: Stores the current pose of selected
                controls as the rest/default pose for Blend-to-Default.</li>
            </ul>
        </div>

        <h2>Tips &amp; Workflow</h2>
        <div class="section">
            <ul>
                <li class="tip">All slider operations are fully undoable with Ctrl+Z</li>
                <li class="tip">All sliders work with both viewport selection and Graph Editor key selection</li>
                <li class="tip">Sliders reset to neutral on release — the object stays at its tweened position</li>
                <li class="tip">Constrained or expression-driven attributes are automatically skipped</li>
                <li class="tip">Custom rig attributes (float, enum, etc.) are supported by LT if they have keyframes</li>
                <li class="tip">Use Quick Buttons for precise mathematical breakdowns (thirds, quarters, eighths)</li>
            </ul>
        </div>

        <h2>Troubleshooting</h2>
        <div class="section">
            <ul>
                <li><b>Slider does nothing:</b> Check that selected objects have keyframes on both
                sides of the current time. For BN/BD/BE, ensure keys are selected in Graph Editor.</li>
                <li><b>Some attributes don't tween:</b> Locked or constrained attributes are skipped.
                Check the Channel Box for lock icons.</li>
                <li><b>World Tweener skips objects:</b> WT only works with transforms and joints
                that have translate/rotate keyframes.</li>
                <li><b>Undo not working:</b> Each full slider drag is one undo step. Press Ctrl+Z
                to revert the entire drag operation.</li>
            </ul>
        </div>
        """)
        layout.addWidget(text_edit)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.exec_()

def show():
    return VertexTweenerUI.show_dialog()
