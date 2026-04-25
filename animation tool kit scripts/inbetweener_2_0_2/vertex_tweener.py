"""
Inbetweener Tool - Maya Animation Breakdown Tool
A high-performance tweening utility for Maya animators to break down poses and manage arcs.

Author: Pipeline Tools
Version: 2.2.0
"""

import math
import os

import maya.cmds as cmds
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
    """Handles the LOCAL Tweener slider (classic TweenMachine behavior).

    The tweener interpolates every selected key between the nearest
    UNSELECTED keys that sit just before and after the selection on the
    same curve. That is: a selection of three adjacent keys gets blended
    as a group between the key just before the first selected key and
    the key just after the last selected key, using the slider bias.

    When no keys are selected in the Graph Editor, the tool falls back
    to current-time behavior on the viewport selection.
    """

    # Cache populated on slider press for fast drag interpolation.
    # Each entry is a dict. Two modes coexist:
    #
    #   Current-time mode (viewport selection, no graph editor keys):
    #       {'attr', 'prev', 'next'}
    #
    #   Per-selected-key mode (Graph Editor keys selected):
    #       {'curve', 'index', 'prev', 'next'}
    #       where 'prev' and 'next' are the selection-BOUND values on the
    #       curve (NOT the key's immediate neighbors). That is the whole
    #       point of Tweener — every selected key is tweened between the
    #       same pair of boundary values, just like a classic tween
    #       machine slider.
    _cached_attrs = []

    @staticmethod
    def cache_selection():
        """Query and cache keyframe boundary values for the current selection.

        Called once on slider press so that drag only does lightweight lerp.
        If keys are selected in the Graph Editor, operate per-selected-key
        against each curve's selection BOUNDS (tween-machine style).
        Returns the number of cached entries.
        """
        TweenEngine._cached_attrs = []

        groups = BlendEngine._get_selection_info()
        if groups:
            for group in groups:
                prev_val = group['bound_prev_val']
                next_val = group['bound_next_val']
                # Need BOTH bounds to tween. If one side of the selection
                # sits at the first/last key on the curve there is nothing
                # to tween against on that side, so skip those keys.
                if prev_val is None or next_val is None:
                    continue
                if not isinstance(prev_val, (int, float)):
                    continue
                if not isinstance(next_val, (int, float)):
                    continue
                for key in group['keys']:
                    TweenEngine._cached_attrs.append({
                        'curve': group['curve'],
                        'index': key['index'],
                        'prev': prev_val,
                        'next': next_val,
                    })
            return len(TweenEngine._cached_attrs)

        selection = cmds.ls(selection=True)
        if not selection:
            return 0

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

                TweenEngine._cached_attrs.append({
                    'attr': full_attr,
                    'prev': prev_val,
                    'next': next_val,
                })

        return len(TweenEngine._cached_attrs)

    @staticmethod
    def apply_cached_tween(bias):
        """Fast interpolation using cached data — called during slider drag.

        Only performs setAttr / keyframe calls with pre-computed lerp.
        """
        t = bias / 100.0
        count = 0
        for entry in TweenEngine._cached_attrs:
            new_value = entry['prev'] + (entry['next'] - entry['prev']) * t
            try:
                if 'curve' in entry:
                    cmds.keyframe(
                        entry['curve'], index=(entry['index'],),
                        valueChange=new_value)
                else:
                    cmds.setAttr(entry['attr'], new_value)
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
        If keys are selected in the Graph Editor, tween every selected key
        on each curve between the curve's selection BOUNDS — i.e. the key
        just before and the key just after the selection — like a classic
        TweenMachine.
        """
        t = bias / 100.0
        count = 0

        groups = BlendEngine._get_selection_info()
        if groups:
            for group in groups:
                prev_val = group['bound_prev_val']
                next_val = group['bound_next_val']
                if prev_val is None or next_val is None:
                    continue
                if not isinstance(prev_val, (int, float)):
                    continue
                if not isinstance(next_val, (int, float)):
                    continue
                new_value = prev_val + (next_val - prev_val) * t
                for key in group['keys']:
                    try:
                        cmds.keyframe(
                            group['curve'], index=(key['index'],),
                            valueChange=new_value)
                        count += 1
                    except (RuntimeError, TypeError, ValueError):
                        pass
            return count

        selection = cmds.ls(selection=True)
        if not selection:
            return 0

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

                prev_val, next_val, has_keys = TweenEngine.get_keyframe_values(obj, attr, current_time)
                if not has_keys:
                    continue

                # Skip compound (non-scalar) attribute values
                if not isinstance(prev_val, (int, float)):
                    continue
                if not isinstance(next_val, (int, float)):
                    continue

                new_value = prev_val + (next_val - prev_val) * t
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
    """Handles world-space matrix interpolation for tweening in global coordinates.

    Like ``TweenEngine`` (the Local Tweener), WorldTweenEngine supports
    two modes:

      * Current-time mode — used when the viewport selection has
        keyframes but no keys are selected in the Graph Editor. Blends
        each object between its nearest prev/next transform keyframes
        around the current scene time.

      * Per-selected-key mode — used when keys are selected in the
        Graph Editor. Each selected transform key is reshaped between
        the same object's SELECTION BOUND keys (the last unselected
        key before the selection and the first unselected key after)
        in world space, mirroring the Local Tweener's behavior but in
        global coordinates.
    """

    # Per-selected-key cache populated on slider press. List of dicts,
    # one per object with selected transform keys. See cache_selected_keys.
    _key_cache = []

    _TRANSFORM_ATTRS = ('tx', 'ty', 'tz', 'rx', 'ry', 'rz')

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

    # ------------------------------------------------------------------
    # Per-selected-key mode
    # ------------------------------------------------------------------
    @staticmethod
    def _selected_transform_keys_by_object():
        """Group selected transform keys by their owning object.

        Returns ``{obj: {attr: [(curve, index, time), ...]}}`` for every
        transform attribute (tx/ty/tz/rx/ry/rz) that has at least one
        selected key.
        """
        selected_curves = cmds.keyframe(q=True, selected=True, name=True)
        if not selected_curves:
            return {}

        grouped = {}
        for curve in set(selected_curves):
            try:
                dest_plugs = cmds.listConnections(
                    curve, s=False, d=True, plugs=True) or []
            except (RuntimeError, TypeError):
                continue
            if not dest_plugs:
                continue
            plug = dest_plugs[0]
            if '.' not in plug:
                continue
            obj, attr = plug.split('.', 1)
            if attr not in WorldTweenEngine._TRANSFORM_ATTRS:
                continue

            sel_indices = cmds.keyframe(
                curve, q=True, selected=True, indexValue=True) or []
            sel_times = cmds.keyframe(
                curve, q=True, selected=True, timeChange=True) or []
            if not sel_indices:
                continue

            attr_map = grouped.setdefault(obj, {})
            entries = attr_map.setdefault(attr, [])
            for i, raw_idx in enumerate(sel_indices):
                try:
                    entries.append((
                        curve,
                        int(raw_idx),
                        sel_times[i] if i < len(sel_times) else None,
                    ))
                except (TypeError, ValueError):
                    continue

        return grouped

    @staticmethod
    def _find_object_selection_bounds(obj, selected_times):
        """Find the nearest unselected prev/next transform key on ``obj``.

        Scans all six transform curves to build a combined list of key
        times, then picks the greatest time strictly less than
        ``min(selected_times)`` as the prev bound and the smallest time
        strictly greater than ``max(selected_times)`` as the next bound.
        """
        if not selected_times:
            return None, None
        min_sel = min(selected_times)
        max_sel = max(selected_times)

        all_times = set()
        for attr in WorldTweenEngine._TRANSFORM_ATTRS:
            plug = "{}.{}".format(obj, attr)
            times = cmds.keyframe(plug, q=True, timeChange=True) or []
            all_times.update(times)
        if not all_times:
            return None, None

        prev_bound = None
        next_bound = None
        for t in sorted(all_times):
            if t < min_sel - 1e-6:
                prev_bound = t
            elif t > max_sel + 1e-6 and next_bound is None:
                next_bound = t
                break
        return prev_bound, next_bound

    @staticmethod
    def cache_selected_keys():
        """Build a per-selected-key world-tween cache.

        For each object with selected transform keys:
          * Resolve the object's selection bounds (prev/next unselected
            transform key times across all transform curves combined).
          * Query world matrices at those bound times.
          * Cache the parent-inverse matrix at EACH selected key time
            (so decomposition doesn't need timeline scrubbing).
          * Record the (curve, index, attr) of every selected transform
            key so apply() can write per-channel values via
            ``cmds.keyframe``.

        Returns the number of selected keys cached.
        """
        WorldTweenEngine._key_cache = []
        grouped = WorldTweenEngine._selected_transform_keys_by_object()
        if not grouped:
            return 0

        count = 0
        for obj, attr_map in grouped.items():
            # Validate object is a transform
            if not cmds.objExists(obj):
                continue
            if not cmds.ls(obj, type=('transform', 'joint')):
                continue

            # Gather every selected key time on this object
            per_key = []  # list of (attr, curve, index, time)
            for attr, entries in attr_map.items():
                for curve, idx, t_val in entries:
                    if t_val is None:
                        continue
                    per_key.append((attr, curve, idx, t_val))
            if not per_key:
                continue

            selected_times = [entry[3] for entry in per_key]
            prev_time, next_time = WorldTweenEngine._find_object_selection_bounds(
                obj, selected_times)
            if prev_time is None or next_time is None:
                continue

            prev_mat = WorldTweenEngine.get_world_matrix_at_time(obj, prev_time)
            next_mat = WorldTweenEngine.get_world_matrix_at_time(obj, next_time)
            if prev_mat is None or next_mat is None:
                continue
            prev_trans, prev_rot = WorldTweenEngine.matrix_to_transform_components(
                prev_mat)
            next_trans, next_rot = WorldTweenEngine.matrix_to_transform_components(
                next_mat)

            # Rotation order is time-invariant (0=XYZ..5=ZYX in cmds;
            # MEulerRotation.reorder() accepts the same 0..5 values).
            try:
                rot_order = cmds.getAttr(obj + '.rotateOrder')
            except (RuntimeError, TypeError):
                rot_order = 0

            # Group per-frame: multiple channels may share the same key time.
            frames = {}  # time -> list of (attr, curve, index)
            for attr, curve, idx, t_val in per_key:
                frames.setdefault(t_val, []).append((attr, curve, idx))

            # Pre-cache parentInverseMatrix at each selected key time so
            # we can do world->local without scrubbing during drag.
            frame_list = []
            for t_val, channels in frames.items():
                try:
                    parent_inv_list = cmds.getAttr(
                        obj + '.parentInverseMatrix[0]', time=t_val)
                    parent_inv = om.MMatrix(parent_inv_list)
                except (RuntimeError, ValueError):
                    parent_inv = om.MMatrix()  # identity fallback
                frame_list.append({
                    'time': t_val,
                    'parent_inv': parent_inv,
                    'channels': channels,
                })
                count += len(channels)

            WorldTweenEngine._key_cache.append({
                'obj': obj,
                'rot_order': rot_order,
                'prev_trans': prev_trans,
                'prev_rot': prev_rot,
                'next_trans': next_trans,
                'next_rot': next_rot,
                'frames': frame_list,
            })

        return count

    @staticmethod
    def apply_cached_world_tween(bias):
        """Apply the per-selected-key world tween at the given bias.

        Interpolates each object's world matrix between its cached
        selection-bound matrices, then for every selected transform key
        on that object: multiplies by the cached parent-inverse matrix
        to get the local matrix, decomposes it to translate/Euler in
        the object's rotation order, and writes the result into the
        specific (curve, index) for each selected channel.

        Because we cached parentInverseMatrix per key at press time,
        this needs zero timeline scrubbing and no Maya DG re-eval.
        """
        if not WorldTweenEngine._key_cache:
            return 0

        t = bias / 100.0
        count = 0

        for obj_entry in WorldTweenEngine._key_cache:
            prev_trans = obj_entry['prev_trans']
            next_trans = obj_entry['next_trans']
            prev_rot = obj_entry['prev_rot']
            next_rot = obj_entry['next_rot']
            rot_order = obj_entry['rot_order']

            # Interpolate world-space translation linearly and rotation via slerp.
            interp_trans = prev_trans + (next_trans - prev_trans) * t
            interp_rot = om.MQuaternion.slerp(prev_rot, next_rot, t)

            interp_tm = om.MTransformationMatrix()
            interp_tm.setTranslation(interp_trans, om.MSpace.kWorld)
            interp_tm.setRotation(interp_rot)
            world_mat = interp_tm.asMatrix()

            for frame in obj_entry['frames']:
                local_mat = world_mat * frame['parent_inv']
                local_tm = om.MTransformationMatrix(local_mat)
                local_trans = local_tm.translation(om.MSpace.kTransform)
                local_euler = local_tm.rotation(asQuaternion=False)
                # MEulerRotation.reorder accepts 0..5 matching Maya's
                # rotateOrder values (0=XYZ .. 5=ZYX).
                try:
                    local_euler = local_euler.reorder(rot_order)
                except (AttributeError, RuntimeError):
                    pass

                comps = {
                    'tx': local_trans.x,
                    'ty': local_trans.y,
                    'tz': local_trans.z,
                    'rx': math.degrees(local_euler.x),
                    'ry': math.degrees(local_euler.y),
                    'rz': math.degrees(local_euler.z),
                }

                for attr, curve, idx in frame['channels']:
                    val = comps.get(attr)
                    if val is None:
                        continue
                    try:
                        cmds.keyframe(curve, index=(idx,), valueChange=val)
                        count += 1
                    except (RuntimeError, TypeError, ValueError):
                        continue

        return count

    @staticmethod
    def clear_key_cache():
        """Release the per-selected-key world-tween cache."""
        WorldTweenEngine._key_cache = []


# ============================================================================
# BLEND ENGINE (BN / BD / BE)
# ============================================================================

class BlendEngine:
    """Shared cache/apply helpers for Blend-to-Neighbor, -Default, -Ease.

    All three sliders need the same behavior: when called they must operate on
    whatever is currently selected — a set of rig controls in the viewport, a
    single object, or a set of keys on a curve in the Graph Editor. The helper
    below resolves that selection once so every slider can reuse it.
    """

    @staticmethod
    def iter_selected_attrs():
        """Yield (obj, attr) pairs for the current selection.

        Preference order:
        1. Graph Editor key selection — yields only the specific attrs whose
           keys are selected on each curve.
        2. Viewport selection — yields every keyable attribute on each object.
        """
        target_attrs = TweenEngine.get_selected_keyframe_attrs()
        if target_attrs:
            for obj in target_attrs:
                for attr in sorted(target_attrs[obj]):
                    yield obj, attr
            return

        for obj in cmds.ls(selection=True) or []:
            for attr in cmds.listAttr(obj, keyable=True) or []:
                yield obj, attr

    @staticmethod
    def _get_selection_info():
        """Gather rich per-curve selection info for every curve with selected keys.

        Returns a list of group dicts (one per curve). Each group contains:

          curve            : the animation curve node name
          plug             : destination plug (``obj.attr``) the curve drives
          keys             : list of per-selected-key entries, each a dict of
                             {index, time, value, prev_val, prev_time,
                              next_val, next_time}. prev/next here refer to
                             the IMMEDIATE neighbor key on the curve,
                             regardless of whether it is selected.
          bound_prev_val   : value of the nearest UNSELECTED key immediately
                             before the earliest selected key on this curve
                             (None if the selection starts at index 0).
          bound_prev_time  : time of that key.
          bound_next_val   : value of the nearest UNSELECTED key immediately
                             after the latest selected key on this curve
                             (None if the selection ends at the last key).
          bound_next_time  : time of that key.

        The per-key ``prev/next`` fields drive Blend-to-Neighbor (each key
        blends against its immediate left/right key). The group-level
        ``bound_prev/bound_next`` fields drive Tweener (interpolate every
        selected key between the selection bounds — classic TweenMachine
        behavior) and Blend-to-Ease (reshape the selected range into an
        eased curve between the selection bounds).

        Original values are cached up front so multi-key drags always
        compute against the pre-drag state, not mid-drag values.
        """
        selected_curves = cmds.keyframe(q=True, selected=True, name=True)
        if not selected_curves:
            return []

        groups = []
        for curve in set(selected_curves):
            try:
                dest_plugs = cmds.listConnections(
                    curve, s=False, d=True, plugs=True) or []
            except (RuntimeError, TypeError):
                continue
            if not dest_plugs:
                continue
            plug = dest_plugs[0]
            if '.' not in plug:
                continue

            try:
                if cmds.getAttr(plug, lock=True):
                    continue
            except (RuntimeError, TypeError, ValueError):
                continue

            # Cache ALL key times/values for this curve in one query each.
            # This is cheaper than per-index queries when there are many
            # selected keys, and guarantees we have a consistent snapshot.
            all_times = cmds.keyframe(curve, q=True, timeChange=True) or []
            all_values = cmds.keyframe(curve, q=True, valueChange=True) or []
            if not all_times or len(all_times) != len(all_values):
                continue
            total = len(all_times)

            raw_sel_indices = cmds.keyframe(
                curve, q=True, selected=True, indexValue=True) or []
            if not raw_sel_indices:
                continue
            sel_indices = sorted({int(i) for i in raw_sel_indices
                                  if 0 <= int(i) < total})
            if not sel_indices:
                continue

            keys = []
            for idx in sel_indices:
                entry = {
                    'index': idx,
                    'time': all_times[idx],
                    'value': all_values[idx],
                    'prev_val': all_values[idx - 1] if idx > 0 else None,
                    'prev_time': all_times[idx - 1] if idx > 0 else None,
                    'next_val': all_values[idx + 1] if idx + 1 < total else None,
                    'next_time': all_times[idx + 1] if idx + 1 < total else None,
                }
                keys.append(entry)

            # Selection bounds: the key immediately before the earliest
            # selected key is, by definition, NOT selected (because the
            # earliest selected key is the smallest selected index).
            min_idx = sel_indices[0]
            max_idx = sel_indices[-1]
            bound_prev_idx = min_idx - 1 if min_idx > 0 else None
            bound_next_idx = max_idx + 1 if max_idx + 1 < total else None

            groups.append({
                'curve': curve,
                'plug': plug,
                'keys': keys,
                'bound_prev_val': (all_values[bound_prev_idx]
                                   if bound_prev_idx is not None else None),
                'bound_prev_time': (all_times[bound_prev_idx]
                                    if bound_prev_idx is not None else None),
                'bound_next_val': (all_values[bound_next_idx]
                                   if bound_next_idx is not None else None),
                'bound_next_time': (all_times[bound_next_idx]
                                    if bound_next_idx is not None else None),
            })

        return groups

    @staticmethod
    def cache_bn():
        """Blend-to-Neighbor cache.

        BN is the "spacing" slider: each selected key blends toward its
        OWN immediate left or right neighbor on the curve, regardless of
        whether that neighbor is itself selected. This is distinct from
        Tweener (which uses the selection bounds) and from Blend-to-Ease
        (which reshapes the selection range).

        Per-selected-key mode stores each key's original value plus the
        values of the immediate prev/next key. Current-time fallback
        stores the prev/next VALUES at the current time.
        """
        groups = BlendEngine._get_selection_info()
        if groups:
            cache = []
            for group in groups:
                for key in group['keys']:
                    prev_val = key['prev_val']
                    next_val = key['next_val']
                    if prev_val is not None and not isinstance(prev_val, (int, float)):
                        prev_val = None
                    if next_val is not None and not isinstance(next_val, (int, float)):
                        next_val = None
                    if prev_val is None and next_val is None:
                        continue
                    cache.append({
                        'curve': group['curve'],
                        'index': key['index'],
                        'original': key['value'],
                        'prev': prev_val,
                        'next': next_val,
                    })
            return cache

        current_time = cmds.currentTime(query=True)
        cache = []
        for obj, attr in BlendEngine.iter_selected_attrs():
            full_attr = "{}.{}".format(obj, attr)
            try:
                if cmds.getAttr(full_attr, lock=True):
                    continue
            except (RuntimeError, TypeError, ValueError):
                continue

            keyframes = cmds.keyframe(full_attr, query=True, timeChange=True)
            if not keyframes or len(keyframes) < 2:
                continue

            current_val = cmds.getAttr(full_attr)
            if not isinstance(current_val, (int, float)):
                continue

            prev_val = None
            next_val = None
            for kf_time in keyframes:
                if kf_time < current_time - 0.001:
                    prev_val = cmds.getAttr(full_attr, time=kf_time)
                elif kf_time > current_time + 0.001:
                    next_val = cmds.getAttr(full_attr, time=kf_time)
                    break

            if prev_val is not None and not isinstance(prev_val, (int, float)):
                prev_val = None
            if next_val is not None and not isinstance(next_val, (int, float)):
                next_val = None
            if prev_val is None and next_val is None:
                continue

            cache.append({
                'attr': full_attr,
                'original': current_val,
                'prev': prev_val,
                'next': next_val,
            })
        return cache

    @staticmethod
    def apply_bn(value, cache):
        if value == 50 or not cache:
            return 0
        if value < 50:
            blend_to_next = False
            weight = (50 - value) / 50.0
        else:
            blend_to_next = True
            weight = (value - 50) / 50.0

        count = 0
        for entry in cache:
            target_val = entry['next'] if blend_to_next else entry['prev']
            if target_val is None:
                continue
            new_val = entry['original'] + (target_val - entry['original']) * weight
            try:
                if 'curve' in entry:
                    cmds.keyframe(
                        entry['curve'], index=(entry['index'],),
                        valueChange=new_val)
                else:
                    cmds.setAttr(entry['attr'], new_val)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                continue
        return count

    @staticmethod
    def cache_bd():
        """Blend-to-Default cache.

        BD is the "return to rest" slider: every selected key blends
        toward the attribute's scanned default pose (or Maya's attribute
        default as a fallback). The default is resolved once per curve
        since every key on the same curve targets the same default value.

        Per-selected-key mode stores each key's original value and the
        default for its owning attribute. Current-time fallback stores
        the attribute value and its default.
        """
        groups = BlendEngine._get_selection_info()
        if groups:
            cache = []
            for group in groups:
                default_val = DefaultPoseStore.get_default(group['plug'])
                if not isinstance(default_val, (int, float)):
                    continue
                for key in group['keys']:
                    cache.append({
                        'curve': group['curve'],
                        'index': key['index'],
                        'original': key['value'],
                        'default': default_val,
                    })
            return cache

        cache = []
        for obj, attr in BlendEngine.iter_selected_attrs():
            full_attr = "{}.{}".format(obj, attr)
            try:
                if cmds.getAttr(full_attr, lock=True):
                    continue
            except (RuntimeError, TypeError, ValueError):
                continue

            if not cmds.keyframe(full_attr, query=True, keyframeCount=True):
                continue

            current_val = cmds.getAttr(full_attr)
            if not isinstance(current_val, (int, float)):
                continue

            default_val = DefaultPoseStore.get_default(full_attr)
            cache.append({
                'attr': full_attr,
                'original': current_val,
                'default': default_val,
            })
        return cache

    @staticmethod
    def apply_bd(value, cache):
        if value == 0 or not cache:
            return 0
        n_weight = value / 100.0
        count = 0
        for entry in cache:
            new_val = entry['original'] + (entry['default'] - entry['original']) * n_weight
            try:
                if 'curve' in entry:
                    cmds.keyframe(
                        entry['curve'], index=(entry['index'],),
                        valueChange=new_val)
                else:
                    cmds.setAttr(entry['attr'], new_val)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                continue
        return count

    @staticmethod
    def cache_be():
        """Blend-to-Ease cache.

        BE is the "reshape the selected range" slider. For each curve
        with selected keys we treat the selection as a contiguous range
        anchored by the two SELECTION BOUNDARY keys (the key just before
        and the key just after the selection on that curve). Every
        selected key is then mapped to an eased position along the
        (bound_prev -> bound_next) interval based on its time:

            t = (key_time - bound_prev_time) / (bound_next_time - bound_prev_time)

        The ease-in target uses t**3 (accelerate toward next), and the
        ease-out target uses 1 - (1-t)**3 (decelerate from prev). At the
        slider extremes the selected keys collectively land on a cubic
        ease curve between the bounds — i.e. the shape of the range
        changes, rather than every key moving in lockstep.

        Current-time fallback preserves the old "pose at current time"
        ease behavior for viewport selections.
        """
        groups = BlendEngine._get_selection_info()
        if groups:
            cache = []
            for group in groups:
                prev_val = group['bound_prev_val']
                next_val = group['bound_next_val']
                prev_time = group['bound_prev_time']
                next_time = group['bound_next_time']
                if (prev_val is None or next_val is None
                        or prev_time is None or next_time is None):
                    continue
                if not isinstance(prev_val, (int, float)):
                    continue
                if not isinstance(next_val, (int, float)):
                    continue
                time_range = next_time - prev_time
                if time_range == 0:
                    continue
                delta = next_val - prev_val
                for key in group['keys']:
                    # Clamp t to [0, 1] in case of unusual key arrangements
                    # (e.g. keys outside the bound times shouldn't overshoot).
                    t = (key['time'] - prev_time) / time_range
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    ease_in_t = t * t * t
                    ease_out_t = 1 - pow(1 - t, 3)
                    cache.append({
                        'curve': group['curve'],
                        'index': key['index'],
                        'original': key['value'],
                        'ease_in': prev_val + delta * ease_in_t,
                        'ease_out': prev_val + delta * ease_out_t,
                    })
            return cache

        current_time = cmds.currentTime(query=True)
        cache = []
        for obj, attr in BlendEngine.iter_selected_attrs():
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

            cache.append({
                'attr': full_attr,
                'original': current_val,
                'ease_in': prev_val + (next_val - prev_val) * ease_in_t,
                'ease_out': prev_val + (next_val - prev_val) * ease_out_t,
            })
        return cache

    @staticmethod
    def apply_be(value, cache):
        if value == 50 or not cache:
            return 0
        weight = abs(value - 50) / 50.0
        blend_to_next = value > 50
        count = 0
        for entry in cache:
            eased_val = entry['ease_in'] if blend_to_next else entry['ease_out']
            new_val = entry['original'] + (eased_val - entry['original']) * weight
            try:
                if 'curve' in entry:
                    cmds.keyframe(
                        entry['curve'], index=(entry['index'],),
                        valueChange=new_val)
                else:
                    cmds.setAttr(entry['attr'], new_val)
                count += 1
            except (RuntimeError, TypeError, ValueError):
                continue
        return count


def _auto_key_selection():
    """Set keys on every already-animated keyable attr on the selection.

    Used by every slider's release handler to lock in the tweened pose.
    Works for both viewport selection and Graph-Editor-filtered attrs; the
    attrs that the tweener actually touched are exactly those that have
    animation curves, so we key everything that has a curve.

    When the user has keys selected in the Graph Editor, the slider already
    modified those keys directly via cmds.keyframe(valueChange=...), so
    there is nothing more to do here — skip the auto-key step to avoid
    creating phantom keys at the current time.
    """
    if cmds.keyframe(q=True, selected=True, name=True):
        return

    selection = cmds.ls(selection=True) or []
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
                if cmds.keyframe(full_attr, query=True, keyframeCount=True):
                    cmds.setKeyframe(full_attr, time=current_time)
            except (RuntimeError, TypeError):
                continue


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
        # Skip the default Qt slider draw; we render the entire control ourselves
        # so the stock groove/handle don't compete with the modern visuals.
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self)

        s_min, s_max = self.minimum(), self.maximum()
        s_range = float(s_max - s_min) or 1.0
        cy = groove.center().y()

        # Mode accent palette
        if self.is_world:
            accent = QtGui.QColor(255, 215, 0)
            accent_dark = QtGui.QColor(200, 160, 0)
            text_on_accent = QtGui.QColor(40, 40, 40)
        elif self.is_tw:
            accent = QtGui.QColor(100, 180, 255)
            accent_dark = QtGui.QColor(60, 120, 200)
            text_on_accent = QtGui.QColor(255, 255, 255)
        else:
            accent = QtGui.QColor(176, 176, 176)
            accent_dark = QtGui.QColor(110, 110, 110)
            text_on_accent = QtGui.QColor(255, 255, 255)

        # Modern thin pill track
        track_h = 4.0
        track_rect = QtCore.QRectF(
            groove.left(), cy - track_h / 2.0,
            groove.width(), track_h,
        )
        track_grad = QtGui.QLinearGradient(track_rect.topLeft(), track_rect.bottomLeft())
        track_grad.setColorAt(0.0, QtGui.QColor(28, 28, 30))
        track_grad.setColorAt(1.0, QtGui.QColor(52, 54, 60))
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 90), 1))
        painter.setBrush(track_grad)
        painter.drawRoundedRect(track_rect, track_h / 2.0, track_h / 2.0)

        # Tick marks: clean notches at 0/50/100, refined dots between
        for val in range(s_min, s_max + 1, 10):
            x = groove.left() + ((val - s_min) / s_range * groove.width())
            is_active_pos = (val == self.value())
            is_major = (val % 50 == 0)

            if self.is_tw and not self.is_world and (val < 0 or val > 100):
                tick_color = QtGui.QColor(255, 80, 80) if is_active_pos else QtGui.QColor(255, 140, 60)
            else:
                tick_color = accent if is_active_pos else QtGui.QColor(122, 126, 134)

            if is_major:
                pen = QtGui.QPen(tick_color.lighter(115), 1.6)
                pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(x, cy - 6), QtCore.QPointF(x, cy + 6))
            else:
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(tick_color)
                painter.drawEllipse(QtCore.QPointF(x, cy), 2.0, 2.0)

        # Keyed-position diamond with soft halo
        if self.keyed_value is not None:
            kx = groove.left() + ((self.keyed_value - s_min) / s_range * groove.width())
            halo = QtGui.QRadialGradient(QtCore.QPointF(kx, cy), 12)
            halo.setColorAt(0.0, QtGui.QColor(0, 230, 120, 110))
            halo.setColorAt(1.0, QtGui.QColor(0, 230, 120, 0))
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QtCore.QPointF(kx, cy), 12, 12)

            painter.setBrush(QtGui.QColor(0, 230, 120))
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 180, 90), 1))
            diamond = QtGui.QPolygonF([
                QtCore.QPointF(kx, cy - 6),
                QtCore.QPointF(kx + 4.5, cy),
                QtCore.QPointF(kx, cy + 6),
                QtCore.QPointF(kx - 4.5, cy),
            ])
            painter.drawPolygon(diamond)

        # Modern handle pill (soft shadow + gradient + inner highlight)
        if self.label_text:
            current_val = self.value()
            handle_x = groove.left() + ((current_val - s_min) / s_range * groove.width())

            box_w, box_h = 36.0, 22.0
            margin = 4.0
            bx = handle_x - box_w / 2.0
            bx = max(margin, min(bx, self.width() - box_w - margin))
            box_rect = QtCore.QRectF(bx, cy - box_h / 2.0, box_w, box_h)

            shadow_rect = box_rect.translated(0, 1.5)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(0, 0, 0, 95))
            painter.drawRoundedRect(shadow_rect, 7, 7)

            grad = QtGui.QLinearGradient(box_rect.topLeft(), box_rect.bottomLeft())
            grad.setColorAt(0.0, accent.lighter(115))
            grad.setColorAt(1.0, accent_dark)
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 110), 1))
            painter.setBrush(grad)
            painter.drawRoundedRect(box_rect, 7, 7)

            inner = box_rect.adjusted(1, 1, -1, -1)
            shine = QtGui.QLinearGradient(inner.topLeft(), inner.bottomLeft())
            shine.setColorAt(0.0, QtGui.QColor(255, 255, 255, 70))
            shine.setColorAt(0.5, QtGui.QColor(255, 255, 255, 0))
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(shine)
            painter.drawRoundedRect(inner, 6, 6)

            painter.setPen(text_on_accent)
            font = QtGui.QFont()
            font.setPointSize(10)
            font.setBold(True)
            font.setLetterSpacing(QtGui.QFont.PercentageSpacing, 102)
            painter.setFont(font)
            painter.drawText(box_rect, QtCore.Qt.AlignCenter, self.label_text)

        painter.end()


# ============================================================================
# POP-OUT SLIDER WINDOW
# ============================================================================

class SliderPopOut(QtWidgets.QDialog):
    """A compact, stand-alone floating window containing one slider.

    Users can pop out any of the Inbetweener sliders into a small independent
    window — handy when only one slider is needed and screen space is tight.
    Each pop-out is fully self-contained: its own cache, its own undo chunk,
    its own handlers. They all share the same engine backends, so they work
    on whatever is currently selected (viewport objects or Graph Editor keys).
    """

    # slider_type -> configuration
    CONFIGS = {
        'LT': {'name': 'Local Tweener', 'color': '#6BB5FF', 'neutral': 50,
               'label': 'LT', 'is_world': False, 'is_tw': True},
        'WT': {'name': 'World Tweener', 'color': '#FFD700', 'neutral': 50,
               'label': 'WT', 'is_world': True, 'is_tw': True},
        'BN': {'name': 'Blend to Neighbor', 'color': '#7EC8A0', 'neutral': 50,
               'label': 'BN', 'is_world': False, 'is_tw': False},
        'BD': {'name': 'Blend to Default', 'color': '#E8A87C', 'neutral': 0,
               'label': 'BD', 'is_world': False, 'is_tw': False},
        'BE': {'name': 'Blend to Ease', 'color': '#C49BD6', 'neutral': 50,
               'label': 'BE', 'is_world': False, 'is_tw': False},
    }

    # Keep hard references so Qt/Python don't garbage-collect open pop-outs.
    _open_windows = []

    def __init__(self, slider_type, overshoot=False, parent=None):
        if slider_type not in self.CONFIGS:
            raise ValueError("Unknown SliderPopOut type: {}".format(slider_type))

        if parent is None:
            ptr = omui.MQtUtil.mainWindow()
            parent = shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
        super(SliderPopOut, self).__init__(parent)

        self.slider_type = slider_type
        self.config = self.CONFIGS[slider_type]
        self.neutral = self.config['neutral']

        self.cache = []
        self.undo_chunk_open = False

        self.setWindowTitle("Inbetweener - " + self.config['name'])
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        # Keep pop-outs alive even after the main window closes
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setMinimumWidth(300)
        self.setMaximumHeight(140)

        self._build_ui(overshoot)
        self._connect()

        SliderPopOut._open_windows.append(self)

    def _build_ui(self, overshoot):
        self.setStyleSheet("""
            QDialog { background: #3c3c3c; }
            QLabel { color: #ddd; background: transparent; border: none; }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # Header: colored title + value readout on the right
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(6)

        title = QtWidgets.QLabel(self.config['name'])
        title.setStyleSheet(
            "color: {}; font-weight: bold; font-size: 11px;".format(self.config['color'])
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self.value_label = QtWidgets.QLabel(
            "{} {}%".format(self.config['label'], self.neutral)
        )
        val_font = QtGui.QFont()
        val_font.setPointSize(11)
        val_font.setBold(True)
        self.value_label.setFont(val_font)
        self.value_label.setStyleSheet("color: #E0E0E0;")
        header_row.addWidget(self.value_label)

        layout.addLayout(header_row)

        # The slider itself
        self.slider = VertexTickedSlider(
            QtCore.Qt.Horizontal,
            is_tw=self.config['is_tw'],
            is_world=self.config['is_world'],
            label_text=self.config['label'],
        )
        self.slider.setMinimumHeight(40)
        self.slider.setTracking(True)
        if self.slider_type == 'LT' and overshoot:
            self.slider.setRange(-50, 150)
        else:
            self.slider.setRange(0, 100)
        self.slider.setValue(self.neutral)
        layout.addWidget(self.slider)

        # Compact status line
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet(
            "color: #999; font-size: 9px; padding: 2px 4px;"
            " background: #333; border: 1px solid #444; border-radius: 3px;"
        )
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def _connect(self):
        self.slider.valueChanged.connect(self._on_changed)
        self.slider.sliderPressed.connect(self._on_pressed)
        self.slider.sliderReleased.connect(self._on_released)

    # ------------------------------------------------------------------
    # Press / Drag / Release handlers
    # ------------------------------------------------------------------
    def _on_pressed(self):
        self.slider.keyed_value = None
        self.slider.update()
        self.undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="Inbetweener_{}_popout".format(self.slider_type))

        if self.slider_type == 'LT':
            cached = TweenEngine.cache_selection()
            if not cached:
                self.status_label.setText("No keyframes found on selection")
        elif self.slider_type == 'WT':
            # Cache per-selected-key data if keys are selected in the
            # Graph Editor. Cache is empty -> _on_changed falls back to
            # current-time world tween on the viewport selection.
            WorldTweenEngine.cache_selected_keys()
        elif self.slider_type == 'BN':
            self.cache = BlendEngine.cache_bn()
            if not self.cache:
                self.status_label.setText("No neighbor keyframes found")
        elif self.slider_type == 'BD':
            if not DefaultPoseStore.has_stored_defaults():
                self.status_label.setText("Tip: scan default pose for best results")
            self.cache = BlendEngine.cache_bd()
            if not self.cache:
                self.status_label.setText("No animated attributes on selection")
        elif self.slider_type == 'BE':
            self.cache = BlendEngine.cache_be()
            if not self.cache:
                self.status_label.setText("Need 3+ keyframes for easing")

    def _on_changed(self, value):
        self.value_label.setText("{} {}%".format(self.config['label'], value))
        count = 0
        if self.slider_type == 'LT':
            if TweenEngine._cached_attrs:
                count = TweenEngine.apply_cached_tween(value)
        elif self.slider_type == 'WT':
            if WorldTweenEngine._key_cache:
                count = WorldTweenEngine.apply_cached_world_tween(value)
            else:
                count = WorldTweenEngine.apply_world_tween(value)
        elif self.slider_type == 'BN':
            if value == 50:
                self.status_label.setText("BN neutral")
                return
            count = BlendEngine.apply_bn(value, self.cache)
        elif self.slider_type == 'BD':
            count = BlendEngine.apply_bd(value, self.cache)
        elif self.slider_type == 'BE':
            if value == 50:
                self.status_label.setText("BE neutral")
                return
            count = BlendEngine.apply_be(value, self.cache)

        if count:
            self.status_label.setText(
                "Affecting {} attr{}".format(count, 's' if count != 1 else '')
            )

    def _on_released(self):
        final_val = self.slider.value()

        # Apply the final value from cache so it sticks, then key the pose.
        if self.slider_type == 'LT':
            if TweenEngine._cached_attrs:
                TweenEngine.apply_cached_tween(final_val)
            TweenEngine.clear_cache()
            _auto_key_selection()
        elif self.slider_type == 'WT':
            # Apply final value from per-key cache (if any) so it sticks.
            if WorldTweenEngine._key_cache:
                WorldTweenEngine.apply_cached_world_tween(final_val)
            WorldTweenEngine.clear_key_cache()
            _auto_key_selection()
        elif self.slider_type == 'BN':
            if self.cache:
                if final_val != 50:
                    BlendEngine.apply_bn(final_val, self.cache)
                _auto_key_selection()
        elif self.slider_type == 'BD':
            if self.cache:
                if final_val != 0:
                    BlendEngine.apply_bd(final_val, self.cache)
                _auto_key_selection()
        elif self.slider_type == 'BE':
            if self.cache:
                if final_val != 50:
                    BlendEngine.apply_be(final_val, self.cache)
                _auto_key_selection()

        self.cache = []

        if self.undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.undo_chunk_open = False

        # Show keyed position tick, then snap slider back to neutral
        self.slider.keyed_value = final_val
        self.slider.blockSignals(True)
        self.slider.setValue(self.neutral)
        self.slider.blockSignals(False)
        self.slider.update()
        self.value_label.setText("{} {}%".format(self.config['label'], self.neutral))
        self.status_label.setText("Keyed at {}%".format(final_val))

    def set_overshoot(self, enabled):
        """External hook to toggle LT overshoot range after construction."""
        if self.slider_type != 'LT':
            return
        self.slider.blockSignals(True)
        if enabled:
            self.slider.setRange(-50, 150)
        else:
            self.slider.setRange(0, 100)
        self.slider.setValue(self.neutral)
        self.slider.blockSignals(False)
        self.slider.update()

    def closeEvent(self, event):
        if self.undo_chunk_open:
            try:
                cmds.undoInfo(closeChunk=True)
            except RuntimeError:
                pass
            self.undo_chunk_open = False
        try:
            SliderPopOut._open_windows.remove(self)
        except ValueError:
            pass
        super(SliderPopOut, self).closeEvent(event)


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
        
        self.setWindowTitle("Inbetweener v2.2")
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

    def _make_group_box(self, title, color="#5285A6", popout_type=None):
        """Create a styled group frame with a colored header bar.

        When *popout_type* is given (e.g. 'LT', 'BN'), a small pop-out button
        is added to the header row so the user can spawn a stand-alone mini
        window containing just that slider.
        """
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame {{ background: #3a3a3a; border: 1px solid #555; border-radius: 4px; }}"
        )
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)

        header = QtWidgets.QLabel(title)
        header.setStyleSheet(
            "QLabel {{ color: {c}; font-weight: bold; font-size: 11px;"
            " background: transparent; border: none; padding: 2px 0; }}".format(c=color)
        )
        header_row.addWidget(header)
        header_row.addStretch()

        if popout_type is not None:
            popout_btn = QtWidgets.QToolButton()
            # Unicode "north-east arrow" makes a compact, universally-available icon.
            popout_btn.setText("\u2197")
            popout_btn.setToolTip(
                "Pop out this slider into a small stand-alone window"
            )
            popout_btn.setStyleSheet(
                "QToolButton { background: #4a4a4a; color: #ddd; border: 1px solid #666;"
                " border-radius: 3px; padding: 0 6px; font-size: 12px; font-weight: bold; }"
                "QToolButton:hover { background: #5a5a5a; border-color: #888; }"
                "QToolButton:pressed { background: #333; }"
            )
            popout_btn.setFixedHeight(20)
            popout_btn.clicked.connect(lambda _=False, t=popout_type: self._open_popout(t))
            header_row.addWidget(popout_btn)

        layout.addLayout(header_row)
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
        lt_group, lt_layout = self._make_group_box("LOCAL TWEENER", "#6BB5FF", popout_type='LT')
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
        opts_row.addStretch()
        lt_layout.addLayout(opts_row)

        main.addWidget(lt_group)

        # ================================================================
        # WORLD TWEENER GROUP
        # ================================================================
        wt_group, wt_layout = self._make_group_box("WORLD TWEENER", "#FFD700", popout_type='WT')
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
        bn_group, bn_layout = self._make_group_box("BLEND TO NEIGHBOR", "#7EC8A0", popout_type='BN')
        bn_layout.addWidget(self._make_descriptor(
            "Blends selected controls toward their neighboring keyframe values. "
            "Drag left for previous neighbor, right for next."
        ))
        bn_layout.addWidget(self.bn_slider)
        bn_layout.addLayout(self.bn_tick_labels_layout)
        self.accordion_layout.addWidget(bn_group)

        # ---- BD GROUP ----
        bd_group, bd_layout = self._make_group_box("BLEND TO DEFAULT", "#E8A87C", popout_type='BD')
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
        be_group, be_layout = self._make_group_box("BLEND TO EASE", "#C49BD6", popout_type='BE')
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
        self.help_action.triggered.connect(self.show_help_dialog)
        self.accordion_toggle.toggled.connect(self.on_accordion_toggled)

    def on_slider_changed(self, value):
        self.value_label.setText("Local {}%".format(value))
        # Use cached data for fast drag — no Maya queries during drag
        if TweenEngine._cached_attrs:
            count = TweenEngine.apply_cached_tween(value)
            if count:
                self.status_label.setText("Tweening {} attribute{}".format(count, 's' if count != 1 else ''))

    def on_slider_pressed(self):
        self.slider.keyed_value = None
        self.slider.update()
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
        # If the press handler cached selected keys, drive the per-key
        # world tween; otherwise fall back to current-time world tween.
        if WorldTweenEngine._key_cache:
            count = WorldTweenEngine.apply_cached_world_tween(value)
            if count:
                self.status_label.setText(
                    "World tweening {} key{}".format(count, 's' if count != 1 else ''))
            return
        count = WorldTweenEngine.apply_world_tween(value)
        if count:
            self.status_label.setText("World tweening {} object{}".format(count, 's' if count != 1 else ''))
        else:
            self.status_label.setText("No keyframes found on selection")

    def on_world_slider_pressed(self):
        self.world_slider.keyed_value = None
        self.world_slider.update()
        self.world_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="WorldTW")
        # Pre-cache per-selected-key data (no-op if nothing is selected
        # in the Graph Editor). apply_world_tween handles the fallback
        # current-time path when the cache is empty.
        WorldTweenEngine.cache_selected_keys()

    def on_world_slider_released(self):
        final_val = self.world_slider.value()

        # Apply final value from the per-key cache so it sticks.
        if WorldTweenEngine._key_cache:
            WorldTweenEngine.apply_cached_world_tween(final_val)

        # Always set keyframes to lock in the tween (skipped automatically
        # when keys are selected — _auto_key_selection already guards that).
        self._auto_key_current_position()

        WorldTweenEngine.clear_key_cache()

        if self.world_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.world_undo_chunk_open = False

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
        if value == 50:
            self.status_label.setText("BN neutral")
            return
        count = BlendEngine.apply_bn(value, self.bn_original_values)
        if count:
            self.status_label.setText("Blending {} attribute{}".format(count, 's' if count != 1 else ''))
        elif self.bn_original_values:
            self.status_label.setText("No neighbor keyframes found")

    def on_bn_pressed(self):
        self.bn_slider.keyed_value = None
        self.bn_slider.update()
        self.bn_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexBN")
        self.bn_original_values = BlendEngine.cache_bn()
        if not self.bn_original_values:
            self.status_label.setText("No neighbor keyframes found on selection")

    def on_bn_released(self):
        final_val = self.bn_slider.value()

        # Apply final value
        if self.bn_original_values:
            if final_val != 50:
                BlendEngine.apply_bn(final_val, self.bn_original_values)
            # Always set keyframes to lock in the blend
            self._auto_key_current_position()

        if self.bn_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.bn_undo_chunk_open = False
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
        count = BlendEngine.apply_bd(value, self.bd_original_values)
        if count:
            self.status_label.setText("Blending {} attribute{} to default".format(count, 's' if count != 1 else ''))
        elif value != 0 and self.bd_original_values:
            self.status_label.setText("No attributes found")

    def on_bd_pressed(self):
        self.bd_slider.keyed_value = None
        self.bd_slider.update()
        self.bd_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexBD")

        self.bd_original_values = []
        # Respect both Graph-Editor and viewport selection for "nothing selected" check
        has_selection = bool(TweenEngine.get_selected_keyframe_attrs()) or bool(cmds.ls(selection=True))
        if not has_selection:
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

        self.bd_original_values = BlendEngine.cache_bd()
        if not self.bd_original_values:
            self.status_label.setText("No animated attributes on selection")

    def on_bd_released(self):
        final_val = self.bd_slider.value()

        if self.bd_original_values:
            if final_val != 0:
                BlendEngine.apply_bd(final_val, self.bd_original_values)
            # Always set keyframes to lock in the blend
            self._auto_key_current_position()

        if self.bd_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.bd_undo_chunk_open = False
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
        if value == 50:
            self.status_label.setText("BE neutral")
            return
        count = BlendEngine.apply_be(value, self.be_original_values)
        if count:
            self.status_label.setText("Easing {} attribute{}".format(count, 's' if count != 1 else ''))
        elif self.be_original_values:
            self.status_label.setText("No attributes found")

    def on_be_pressed(self):
        self.be_slider.keyed_value = None
        self.be_slider.update()
        self.be_undo_chunk_open = True
        cmds.undoInfo(openChunk=True, chunkName="VertexBE")

        self.be_original_values = BlendEngine.cache_be()
        if not self.be_original_values:
            self.status_label.setText("Need 3+ keyframes for easing")

    def on_be_released(self):
        final_val = self.be_slider.value()

        if self.be_original_values:
            if final_val != 50:
                BlendEngine.apply_be(final_val, self.be_original_values)
            # Always set keyframes to lock in the blend
            self._auto_key_current_position()

        if self.be_undo_chunk_open:
            cmds.undoInfo(closeChunk=True)
            self.be_undo_chunk_open = False
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

    def _auto_key_current_position(self):
        """Set keyframes on all selected objects at current time to lock in the tween.

        Keys any keyable attribute that already has animation curves,
        supporting transforms, joints, and custom rig controls. The user's
        Maya autoKeyframe setting is intentionally NOT touched here — the
        tool's keying is orthogonal to Maya's autoKey preference.
        """
        _auto_key_selection()

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
        cmds.undoInfo(openChunk=True)

        # One-shot full query-and-apply (no drag, so no need for cache)
        TweenEngine.apply_tween(val)

        # Always key to lock in the position
        self._auto_key_current_position()

        cmds.undoInfo(closeChunk=True)

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
        # Propagate the new overshoot state to any open LT pop-out windows.
        for popout in list(SliderPopOut._open_windows):
            try:
                if popout.slider_type == 'LT':
                    popout.set_overshoot(checked)
            except RuntimeError:
                # Qt object was deleted out from under us
                pass
        # World slider always stays 0-100 (no overshoot)

    def _open_popout(self, slider_type):
        """Spawn a compact, stand-alone window containing a single slider.

        Pop-outs are parented to Maya's main window (not this dialog) so they
        remain usable even after the main Inbetweener window is closed.
        """
        overshoot = self.overshoot_checkbox.isChecked() if slider_type == 'LT' else False
        popout = SliderPopOut(slider_type, overshoot=overshoot, parent=None)
        # Position the pop-out near the top-right of the main window so the
        # two are easy to use side-by-side.
        main_geom = self.geometry()
        popout.move(main_geom.x() + main_geom.width() + 10, main_geom.y())
        popout.show()
        popout.raise_()
        popout.activateWindow()
        return popout

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
        if self.undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.world_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.bn_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.bd_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        if self.be_undo_chunk_open: cmds.undoInfo(closeChunk=True)
        super(VertexTweenerUI, self).closeEvent(event)

    def show_help_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Inbetweener v2.2 - Help")
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
            <p>Version 2.2.0 &mdash; Pipeline Tools</p>
        </div>

        <h2>Local Tweener (LT)</h2>
        <div class="section">
            <p>Classic tween machine: interpolates selected keys between their
            <b>surrounding boundary keys</b> on the same curve.</p>
            <ul>
                <li><span class="key">0%</span> = Previous boundary key value</li>
                <li><span class="key">50%</span> = Halfway between boundaries (linear)</li>
                <li><span class="key">100%</span> = Next boundary key value</li>
                <li><span class="key">Overshoot</span>: -50% to 150% for exaggerated motion</li>
            </ul>
            <p><b>Graph Editor mode:</b> Every selected key on a curve collapses toward
            the same boundary values — the key just before and the key just after the
            selection. At 50% the whole selected range collapses to the midpoint.</p>
            <p><b>Viewport mode:</b> Operates at the current scene time on every animated
            attribute of the selection.</p>
            <p><b>Quick Buttons:</b> 1/8, 1/4, 1/2, 3/4, 7/8 and 0, 1/3, 2/3, 1 for precise
            common breakdown positions.</p>
        </div>

        <h2>World Tweener (WT)</h2>
        <div class="section">
            <p>Like Local Tweener, but the interpolation is computed in <b>world space</b>
            using matrix lerp + quaternion slerp, then decomposed back to local channels
            so the keys land on a straight world-space path.</p>
            <ul>
                <li>Range: <span class="key">0%</span> to <span class="key">100%</span> (no overshoot)</li>
                <li>Ideal for maintaining world-space arcs on parented / constrained controls</li>
                <li>Works with transforms and joints</li>
            </ul>
            <p><b>Graph Editor mode:</b> Selected transform keys are rewritten between the
            same object's selection boundary matrices — no timeline scrubbing.</p>
            <p><b>When to use:</b> When local-space tweening produces incorrect arcs due
            to parent space changes between keys (IK/FK switching, space-matched rigs).</p>
        </div>

        <h2>Blend to Neighbor (BN)</h2>
        <div class="section">
            <p>The "spacing" slider: moves each selected key closer to or farther from
            its own <b>immediate left / right neighbor</b> on the curve. This changes
            how keys relate to their adjacent keys — it does not collapse the range.</p>
            <ul>
                <li><span class="key">&lt; 50</span>: Blend each key toward its <b>previous</b> neighbor</li>
                <li><span class="key">&gt; 50</span>: Blend each key toward its <b>next</b> neighbor</li>
                <li><span class="key">50</span>: No change (neutral)</li>
            </ul>
            <p><b>Use cases:</b> Tightening / loosening spacing, pulling timing toward
            holds, evening out breakdowns without changing the overall pose.</p>
        </div>

        <h2>Blend to Default (BD)</h2>
        <div class="section">
            <p>Blends each selected key toward the attribute's <b>rest pose</b> value.
            Every selected key slides independently toward its own default.</p>
            <ul>
                <li><span class="key">0</span>: Original values (no change)</li>
                <li><span class="key">100</span>: Default / rest pose</li>
            </ul>
            <p><b>Scan Default Pose:</b> Select your rig controls (or root) while in the
            default pose, then click &ldquo;Scan Default Pose&rdquo; to store accurate rest
            values. Without scanning, BD falls back to 0 for translate/rotate and 1 for scale.</p>
            <p><b>Use cases:</b> Zeroing out overshoot, resetting controls to neutral,
            reducing extreme poses.</p>
        </div>

        <h2>Blend to Ease (BE)</h2>
        <div class="section">
            <p>Reshapes the <b>selected key range</b> into a cubic ease curve between the
            selection boundary keys. Each selected key is remapped to its time-proportional
            position along the eased curve, so the range gets a smooth acceleration or
            deceleration shape rather than each key shifting uniformly.</p>
            <ul>
                <li><span class="key">&gt; 50</span>: Ease-in (slow start, accelerate — t&sup3;)</li>
                <li><span class="key">&lt; 50</span>: Ease-out (fast start, decelerate — 1-(1-t)&sup3;)</li>
                <li><span class="key">50</span>: No change (neutral)</li>
            </ul>
            <p><b>Selection:</b> Best used with 2+ keys selected in the Graph Editor so
            the slider has a range to reshape. Works on a single selected key too —
            that key gets reshaped between its immediate boundaries.</p>
        </div>

        <h2>Options</h2>
        <div class="section">
            <ul>
                <li><span class="key">Auto Keying</span>: All sliders automatically set keyframes
                on release. A green diamond tick marks the keyed position on the slider.
                Maya's own Auto Key preference is left untouched — the tool never toggles it.</li>
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
