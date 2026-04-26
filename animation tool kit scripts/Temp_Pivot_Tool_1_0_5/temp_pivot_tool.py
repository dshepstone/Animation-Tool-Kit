"""
Temp Pivot Tool for Autodesk Maya

A non-destructive, reusable temporary pivot system for animation.

TWO-NULL ARCHITECTURE (v7 - with pivot freezing):
  null_group_2: The POSITION ANCHOR - holds the pivot rig relative to control
  pivotOffsetGrp: Stores the offset from pivot positioning (created at Complete Setup)
  null_group_1: The TEMP PIVOT - animator-facing control with clean zeroed values

Hierarchy when ACTIVE (constraint ON):
    null_group_2 (aligned to control position)
      └ pivotOffsetGrp (baked pivot offset - translate only)
          └ null_group_1 (ANIMATOR PIVOT CTRL - rotatePivot=0, clean channels)
             └ [parentConstraint] → control

Workflow:
1. Select control, click "Create Pivot Locator" (Stage 1)
2. Tool automatically enters pivot adjust mode - move the pivot to desired position
3. Click "Complete Setup" (Stage 2) - freezes pivot offset, creates constraint
4. Rotate null_group_1 - control orbits around the custom pivot point (auto-keys applied)
5. Toggle OFF - anchor preserves position, constraint deleted, control free to move
6. Move control to new position
7. Toggle ON - anchor realigns to control, constraint recreated

Features:
- Pivot freezing: Offset group absorbs pivot position so animator sees clean 0 values
- Undo-safe: Major operations wrapped in undo chunks with undo/redo guard
- Auto-key: When you transform null_group_1, keyframes are automatically set on the control
- World-matrix alignment: Proper world-space alignment using full transformation matrix
- Robust selection: Works on shapes, namespaced nodes, props, locators
- Dockable UI: workspaceControl support for Maya 2017+
- Constraint validation: Warns if control has existing constraints

Author: David Shepstone
License: MIT
Version: 7.0.0

Upgrade notes from v6:
  - null_group_1 now has zeroed rotatePivot/scalePivot (pivot offset baked into pivotOffsetGrp)
  - New pivotOffsetGrp node tracked on settings as "pivotOffsetGrp"
  - UI uses workspaceControl for docking (falls back to window)
  - Undo chunks wrap all major operations
  - Selection resolves shape nodes to parent transforms automatically
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import maya.cmds as cmds
import maya.mel as mel

# -----------------------------
# Constants
# -----------------------------

WINDOW_NAME = "tempPivotToolWindow"
WORKSPACE_CONTROL_NAME = "TempPivotToolWorkspaceControl"
WINDOW_TITLE = "Temp Pivot Tool"
TOOL_PREFIX = "TMP"

# Node naming convention
NULL_GRP_1_SUFFIX = f"_{TOOL_PREFIX}_pivot"      # TEMP PIVOT - animator-facing control
NULL_GRP_2_SUFFIX = f"_{TOOL_PREFIX}_anchor"     # POSITION ANCHOR - holds pivot relative to control
OFFSET_GRP_SUFFIX = f"_{TOOL_PREFIX}_pivotOffset"  # Offset group - stores baked pivot offset
SETTINGS_SUFFIX = f"_{TOOL_PREFIX}_settings"
CONSTRAINT_SUFFIX = f"_{TOOL_PREFIX}_parentConstraint"

# Auto-key scriptJob storage (keyed by settings node name)
_auto_key_jobs: Dict[str, List[int]] = {}

# Undo guard - prevents auto-key from firing during undo/redo
_is_undoing: bool = False
_undo_guard_jobs: List[int] = []

# UI SelectionChanged scriptJob IDs — tracked so stale jobs from a previous
# _build_ui call can be killed before new ones are registered.  Without this,
# every rebuild accumulates extra jobs whose callbacks reference deleted widget
# paths and raise RuntimeError: Object '...' not found.
_ui_script_jobs: List[int] = []

# UI Colors
UI_COLORS = {
    "accent":       (0.25, 0.55, 0.85),   # Blue header accent
    "success":      (0.18, 0.68, 0.42),   # Green - ON / active
    "warning":      (0.90, 0.72, 0.20),   # Amber - toggle OFF prompt
    "error":        (0.82, 0.28, 0.28),   # Red - error / delete
    "stage1":       (0.85, 0.55, 0.15),   # Orange - Stage 1 / OFF state
    "stage2":       (0.25, 0.55, 0.85),   # Blue - Stage 2
    "on_state":     (0.18, 0.68, 0.42),   # Green - rig ON
    "off_state":    (0.40, 0.40, 0.43),   # Grey - rig OFF / READY
    "section_bg":   (0.20, 0.20, 0.22),   # Dark section header bg
    "detail_bg":    (0.18, 0.18, 0.20),   # Darker detail bg
    "pivot_label":  (0.45, 0.75, 1.00),   # Light blue - pivot node label
    "ctrl_label":   (0.75, 0.95, 0.65),   # Light green - control node label
}

# Tooltips
TOOLTIPS = {
    "create_pivot_btn": (
        "STAGE 1 — Create Pivot Locator\n\n"
        "1. Select a rig control in the viewport\n"
        "2. Click this button — a pivot null is created at the control\n"
        "3. Tool automatically enters pivot-adjust mode (like pressing D)\n"
        "4. Move the pivot marker to your desired rotation point\n"
        "5. Click 'Complete Setup' when the pivot is in position"
    ),
    "complete_setup_btn": (
        "STAGE 2 — Complete Setup\n\n"
        "1. Bakes the pivot position into an offset group\n"
        "2. Zeros out the pivot null channels (clean animator values)\n"
        "3. Creates parentConstraint: Pivot Null  →  Original Control\n"
        "4. Rotating the Pivot Null now orbits the control around your pivot\n"
        "5. Auto-key is enabled — keys set on control as you rotate"
    ),
    "toggle_btn": (
        "Toggle Pivot Rig ON / OFF\n\n"
        "Toggle OFF:\n"
        "  • Saves current anchor position\n"
        "  • Removes constraint (control is now free to move)\n"
        "  • Hides pivot rig nodes\n\n"
        "Toggle ON:\n"
        "  • Realigns anchor to control's current position\n"
        "  • Recreates the constraint\n"
        "  • Re-enables auto-key"
    ),
    "key_btn": (
        "Key Control — Set keyframe on the original control\n\n"
        "Keys translate and rotate channels on the control.\n"
        "Note: keys are also set automatically as you rotate the pivot null."
    ),
    "delete_btn": (
        "Delete Pivot Rig\n\n"
        "Permanently removes all temp pivot nodes:\n"
        "  • Pivot null, anchor, offset group, constraint, settings\n"
        "The original control is left untouched."
    ),
    "select_pivot_btn": (
        "Select Pivot Null\n\n"
        "Selects the temp pivot null (the node you rotate).\n"
        "Rotating this causes the control to orbit around the pivot point."
    ),
    "select_control_btn": (
        "Select Original Control\n\n"
        "Selects the original rig control being driven.\n"
        "Useful for inspecting values or manual keying."
    ),
}


# -----------------------------
# Undo Guard
# -----------------------------

def _on_undo_start():
    """Called when Maya begins an undo operation."""
    global _is_undoing
    _is_undoing = True


def _on_undo_end():
    """Called when Maya finishes an undo/redo operation."""
    global _is_undoing
    _is_undoing = False


def _setup_undo_guard():
    """Install global scriptJobs to detect undo/redo and set the guard flag."""
    global _undo_guard_jobs
    _teardown_undo_guard()

    job1 = cmds.scriptJob(event=["Undo", _on_undo_end], protected=True)
    job2 = cmds.scriptJob(event=["Redo", _on_undo_end], protected=True)
    # undoSuppress fires at the start of an undo chunk processing
    # We use timeChanged as a fallback reset since Maya doesn't have a direct "UndoStart" event
    _undo_guard_jobs = [job1, job2]


def _teardown_undo_guard():
    """Remove undo guard scriptJobs."""
    global _undo_guard_jobs
    for jid in _undo_guard_jobs:
        if cmds.scriptJob(exists=jid):
            cmds.scriptJob(kill=jid, force=True)
    _undo_guard_jobs = []


# -----------------------------
# Utility Functions
# -----------------------------

def _sanitize_name(name: str) -> str:
    """Create a safe prefix from a control name."""
    safe = name.split(":")[-1]
    safe = safe.replace("|", "_").replace(" ", "_")
    return safe


def _resolve_transform(node: str) -> str:
    """
    Resolve a node to its transform.

    If the user selected a shape node (nurbsCurve, locator, mesh, etc.),
    return the parent transform. Otherwise return the node itself.

    Handles:
    - nurbsCurve shapes
    - locator shapes
    - mesh shapes
    - any other shape node
    - namespaced nodes
    - full DAG paths
    """
    if not cmds.objExists(node):
        return node

    node_type = cmds.nodeType(node)

    # If it's a shape node, get the parent transform
    if cmds.objectType(node, isAType="shape"):
        parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
        if parents:
            return parents[0]

    return node


def _align_to_target_world_matrix(object_to_align: str, target: str) -> None:
    """
    Align object_to_align to target's world-space transform using world matrix.

    This method uses the full world transformation matrix to bypass rotation
    order issues and gimbal lock problems.

    Based on the MEL alignToFirstFixed() approach.
    """
    # Get target's world matrix (16 values)
    matrix = cmds.xform(target, q=True, ws=True, m=True)

    # Apply the full world matrix to the object
    # This bypasses rotation order issues
    cmds.xform(
        object_to_align, ws=True, m=[
            matrix[0], matrix[1], matrix[2], matrix[3],
            matrix[4], matrix[5], matrix[6], matrix[7],
            matrix[8], matrix[9], matrix[10], matrix[11],
            matrix[12], matrix[13], matrix[14], matrix[15]
        ]
    )


def _match_translation_world(source: str, target: str) -> None:
    """Match only world-space translation using xform."""
    pos = cmds.xform(target, q=True, ws=True, t=True)
    cmds.xform(source, ws=True, t=pos)


def _has_constraints(node: str) -> Tuple[bool, List[str]]:
    """
    Check if a node has any constraints affecting it.

    Uses both listRelatives and listConnections for robust detection.

    Returns:
        Tuple of (has_constraints, list_of_constraint_names)
    """
    constraint_types = [
        "parentConstraint", "pointConstraint", "orientConstraint",
        "scaleConstraint", "aimConstraint"
    ]

    found_constraints = []

    # Method 1: Check children for constraint nodes
    for ctype in constraint_types:
        constraints = cmds.listRelatives(node, type=ctype) or []
        found_constraints.extend(constraints)

    # Method 2: Check connections to translate/rotate attributes
    for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
        attr_path = f"{node}.{attr}"
        if cmds.objExists(attr_path):
            connections = cmds.listConnections(
                attr_path, source=True, destination=False, plugs=False, type="constraint"
            ) or []
            for conn_node in connections:
                if conn_node not in found_constraints:
                    found_constraints.append(conn_node)

    # Method 3: Use listConnections with type filter for broader detection
    for ctype in constraint_types:
        conns = cmds.listConnections(node, type=ctype, source=True, destination=False) or []
        for c in conns:
            if c not in found_constraints:
                found_constraints.append(c)

    return len(found_constraints) > 0, found_constraints


def _safe_set_attr(node: str, attr: str, value) -> bool:
    """Set an attribute safely, skipping if locked or non-existent."""
    attr_path = f"{node}.{attr}"
    if not cmds.objExists(attr_path):
        return False
    if cmds.getAttr(attr_path, lock=True):
        return False
    try:
        cmds.setAttr(attr_path, value)
        return True
    except RuntimeError:
        return False


def _safe_set_key(node: str, attr: str, time=None) -> bool:
    """Set a keyframe safely, skipping if locked or non-keyable."""
    attr_path = f"{node}.{attr}"
    if not cmds.objExists(attr_path):
        return False
    if cmds.getAttr(attr_path, lock=True):
        return False
    # Check if the attribute is keyable
    if not cmds.getAttr(attr_path, keyable=True):
        return False
    try:
        kwargs = {"attribute": attr}
        if time is not None:
            kwargs["time"] = time
        cmds.setKeyframe(node, **kwargs)
        return True
    except RuntimeError:
        return False


def _add_string_attr(node: str, attr: str, value: str = "") -> None:
    """Add a string attribute if it doesn't exist."""
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, dataType="string")
    cmds.setAttr(f"{node}.{attr}", value, type="string")


def _add_bool_attr(node: str, attr: str, value: bool = False) -> None:
    """Add a boolean attribute if it doesn't exist."""
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, attributeType="bool")
    cmds.setAttr(f"{node}.{attr}", value)


def _create_visual_null(name: str, color: Tuple[float, float, float], size: float = 1.0) -> str:
    """
    Create a null group with visual circle indicators.

    Args:
        name: Name for the null group
        color: RGB color tuple (0-1 range)
        size: Scale factor for the visual indicators

    Returns:
        The name of the created null group
    """
    # Create the null group
    null_grp = cmds.group(empty=True, name=name)
    base_name = null_grp

    # Add visual circles for each axis
    for axis, axis_color, normal in [
        ("X", (1, 0.3, 0.3), (1, 0, 0)),
        ("Y", (0.3, 1, 0.3), (0, 1, 0)),
        ("Z", (0.3, 0.5, 1), (0, 0, 1))
    ]:
        circle = cmds.circle(
            name=f"{base_name}_ring{axis}",
            normal=normal,
            radius=0.5 * size,
            degree=3,
            sections=24,
            constructionHistory=False
        )[0]
        circle_shape = cmds.listRelatives(circle, shapes=True)[0]
        cmds.setAttr(f"{circle_shape}.overrideEnabled", 1)
        cmds.setAttr(f"{circle_shape}.overrideRGBColors", 1)
        cmds.setAttr(f"{circle_shape}.overrideColorR", axis_color[0])
        cmds.setAttr(f"{circle_shape}.overrideColorG", axis_color[1])
        cmds.setAttr(f"{circle_shape}.overrideColorB", axis_color[2])
        cmds.parent(circle_shape, null_grp, shape=True, relative=True)
        cmds.delete(circle)

    # Add a center locator shape for selection clarity
    loc = cmds.spaceLocator(name=f"{base_name}_loc")[0]
    loc_shape = cmds.listRelatives(loc, shapes=True)[0]
    cmds.setAttr(f"{loc_shape}.overrideEnabled", 1)
    cmds.setAttr(f"{loc_shape}.overrideRGBColors", 1)
    cmds.setAttr(f"{loc_shape}.overrideColorR", color[0])
    cmds.setAttr(f"{loc_shape}.overrideColorG", color[1])
    cmds.setAttr(f"{loc_shape}.overrideColorB", color[2])
    cmds.setAttr(f"{loc_shape}.localScaleX", 0.3 * size)
    cmds.setAttr(f"{loc_shape}.localScaleY", 0.3 * size)
    cmds.setAttr(f"{loc_shape}.localScaleZ", 0.3 * size)
    cmds.parent(loc_shape, null_grp, shape=True, relative=True)
    cmds.delete(loc)

    # Defensive cleanup: remove any leftover ring/locator transforms that failed to parent.
    for pattern in (f"{base_name}_ring*", f"{base_name}_loc"):
        for node in cmds.ls(pattern, type="transform") or []:
            parent = cmds.listRelatives(node, parent=True) or []
            if not parent or parent[0] != null_grp:
                cmds.delete(node)

    return null_grp


def _set_null_color(null_grp: str, color: Tuple[float, float, float]) -> None:
    """Set the color of the locator shape in a null group."""
    shapes = cmds.listRelatives(null_grp, shapes=True) or []
    for shape in shapes:
        if cmds.nodeType(shape) == "locator":
            cmds.setAttr(f"{shape}.overrideColorR", color[0])
            cmds.setAttr(f"{shape}.overrideColorG", color[1])
            cmds.setAttr(f"{shape}.overrideColorB", color[2])


def _enter_pivot_adjust_mode(node: str) -> None:
    """
    Enter custom pivot editing mode with the translate tool active on the given node.

    This selects the node, activates the Move tool, and enters custom pivot editing
    mode (equivalent to pressing D or Insert key) so the user can immediately
    adjust the pivot position.

    See: https://help.autodesk.com/view/MAYAUL/2026/ENU/?guid=GUID-6BCE41D8-07CB-4A99-99CD-1D3986896157
    """
    # Ensure the node is selected
    cmds.select(node, replace=True)

    # Activate the Move tool and enter custom pivot editing mode
    # ctxEditMode is the MEL command equivalent to pressing D or Insert key
    mel.eval('MoveTool; ctxEditMode;')


# -----------------------------
# Rig Discovery Functions
# -----------------------------

def get_all_pivot_rigs() -> List[str]:
    """Find all temp pivot rigs in the scene by finding settings nodes."""
    settings_nodes = cmds.ls(f"*{SETTINGS_SUFFIX}", type="transform") or []
    return settings_nodes


def get_rig_for_control(control: str) -> Optional[str]:
    """Find the settings node for a given control, if one exists."""
    settings_nodes = get_all_pivot_rigs()
    for settings in settings_nodes:
        if cmds.attributeQuery("targetControl", node=settings, exists=True):
            target = cmds.getAttr(f"{settings}.targetControl")
            if target == control:
                return settings
    return None


def get_pending_pivot_for_control(control: str) -> Optional[str]:
    """Find a pending (stage 1) pivot null for a control."""
    # Look for null_group_1 that has a targetControl attr but no setupComplete=True yet
    pivot_nulls = cmds.ls(f"*{NULL_GRP_1_SUFFIX}", type="transform") or []
    for pivot in pivot_nulls:
        if cmds.attributeQuery("targetControl", node=pivot, exists=True):
            target = cmds.getAttr(f"{pivot}.targetControl")
            if target == control:
                # Check if setup is complete
                if cmds.attributeQuery("setupComplete", node=pivot, exists=True):
                    if not cmds.getAttr(f"{pivot}.setupComplete"):
                        return pivot
    return None


def _resolve_stored_name(name: Optional[str]) -> Optional[str]:
    """Resolve a stored node name that may have become a stale DAG path.

    If *name* is a full DAG path that no longer exists but the short
    (leaf) name does exist uniquely, return the short name so the rest
    of the code can still find it.
    """
    if not name:
        return None
    if cmds.objExists(name):
        return name
    # Try the short (leaf) name
    short = name.split("|")[-1]
    matches = cmds.ls(short, long=True) or []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Ambiguous — return first match (better than None)
        return matches[0]
    return None


def get_rig_nodes(settings_node: str) -> Dict[str, Optional[str]]:
    """Get all rig node names from a settings node.

    Stored names are resolved through ``_resolve_stored_name`` so that
    DAG-path changes caused by reparenting do not break look-ups.
    """
    result = {
        "settings": settings_node,
        "null_grp_1": None,  # Pivot (animator-facing control)
        "null_grp_2": None,  # Anchor (may not exist yet)
        "pivot_offset_grp": None,  # Offset group (created at complete_setup)
        "control": None,
        "constraint": None,
    }

    if not cmds.objExists(settings_node):
        return result

    if cmds.attributeQuery("nullGrp1", node=settings_node, exists=True):
        result["null_grp_1"] = _resolve_stored_name(
            cmds.getAttr(f"{settings_node}.nullGrp1") or None
        )
    if cmds.attributeQuery("nullGrp2", node=settings_node, exists=True):
        result["null_grp_2"] = _resolve_stored_name(
            cmds.getAttr(f"{settings_node}.nullGrp2") or None
        )
    if cmds.attributeQuery("pivotOffsetGrp", node=settings_node, exists=True):
        result["pivot_offset_grp"] = _resolve_stored_name(
            cmds.getAttr(f"{settings_node}.pivotOffsetGrp") or None
        )
    if cmds.attributeQuery("targetControl", node=settings_node, exists=True):
        result["control"] = _resolve_stored_name(
            cmds.getAttr(f"{settings_node}.targetControl") or None
        )
    if cmds.attributeQuery("constraintName", node=settings_node, exists=True):
        result["constraint"] = _resolve_stored_name(
            cmds.getAttr(f"{settings_node}.constraintName") or None
        )

    return result


def is_rig_active(settings_node: str) -> bool:
    """Check if a rig is currently active (constraint exists)."""
    if not cmds.objExists(settings_node):
        return False
    if cmds.attributeQuery("isActive", node=settings_node, exists=True):
        return cmds.getAttr(f"{settings_node}.isActive")
    return False


# =============================================================================
# STAGE 1: Create Pivot Null
# =============================================================================

def create_pivot_locator(control: str) -> Tuple[bool, str, Optional[str]]:
    """
    STAGE 1: Create the pivot null (null_group_1) for user pivot positioning.

    Process:
    1. Resolve shape nodes to transforms
    2. Create null_group_1
    3. Align to the selected control using world matrix
    4. Automatically enter pivot adjust mode with Move tool active
    5. User moves the pivot to desired position
    6. Then user clicks "Complete Setup" for Stage 2

    Args:
        control: The control to create a pivot for

    Returns:
        Tuple of (success, message, null_grp_1_name)
    """
    # Resolve shape to transform
    control = _resolve_transform(control)

    if not cmds.objExists(control):
        return False, f"Control '{control}' not found.", None

    # Ensure it's a transform node
    if cmds.nodeType(control) != "transform":
        return False, f"'{control}' is not a transform node.", None

    cmds.undoInfo(openChunk=True, chunkName="TMP_CreatePivotLocator")
    try:
        # Check if rig already exists for this control
        existing = get_rig_for_control(control)
        if existing:
            return False, f"Pivot rig already exists for '{control}'. Delete it first or use Toggle.", None

        # Check if pending pivot exists
        pending = get_pending_pivot_for_control(control)
        if pending:
            cmds.select(pending)
            return False, f"Pivot null already created. Adjust its pivot, then click 'Complete Setup'.", pending

        # Check for existing constraints on the control (could cause double offset)
        has_constraints, constraint_list = _has_constraints(control)
        if has_constraints:
            constraint_names = ", ".join(constraint_list[:3])  # Show first 3
            if len(constraint_list) > 3:
                constraint_names += f"... (+{len(constraint_list) - 3} more)"
            return False, f"Control '{control}' has existing constraints: {constraint_names}. This may cause double transforms.", None

        # Create safe prefix
        prefix = _sanitize_name(control)

        # =========================================================================
        # Create null_group_1 (the PIVOT - user will adjust its pivot point)
        # =========================================================================
        null_grp_1 = _create_visual_null(
            f"{prefix}{NULL_GRP_1_SUFFIX}",
            UI_COLORS["stage1"],  # Orange for Stage 1
            size=1.0
        )

        # Align null_grp_1 to the control's visual pivot (rotatePivot in world
        # space) rather than its local-origin world-matrix translation.
        # For controls inside a deep parent hierarchy the two differ: the world
        # matrix translation is the node's local-origin in world space, while
        # rotatePivot is where the animator's gizmo actually sits.  Using
        # rotatePivot ensures the temp pivot null appears at the correct centre
        # even for offset-group or namespaced controls.
        ctrl_pivot_ws = cmds.xform(control, q=True, ws=True, rotatePivot=True)
        ctrl_rot_ws   = cmds.xform(control, q=True, ws=True, ro=True)
        cmds.xform(null_grp_1, ws=True, t=ctrl_pivot_ws)
        cmds.xform(null_grp_1, ws=True, ro=ctrl_rot_ws)

        # Store target control reference on the null (for Stage 2)
        _add_string_attr(null_grp_1, "targetControl", control)
        _add_bool_attr(null_grp_1, "setupComplete", False)

        # Select the null and enter pivot adjust mode with translate tool
        # Use evalDeferred to ensure proper initialization timing
        cmds.evalDeferred(lambda: _enter_pivot_adjust_mode(null_grp_1))

        return True, f"Stage 1 complete. Move the PIVOT to your desired position, then click 'Complete Setup'.", null_grp_1
    finally:
        cmds.undoInfo(closeChunk=True)


# =============================================================================
# STAGE 2: Complete Setup (with pivot freezing)
# =============================================================================

def complete_setup(null_grp_1: str) -> Tuple[bool, str, Optional[str]]:
    """
    STAGE 2: Complete the pivot rig setup with pivot freezing.

    Process:
    1. Get the target control from null_group_1
    2. Read the rotatePivot offset the user created during pivot positioning
    3. Create pivotOffsetGrp to absorb the offset
    4. Re-parent null_group_1 under pivotOffsetGrp with zeroed pivots
    5. Create parentConstraint: null_group_1 → control (maintainOffset)
    6. Create settings node

    The resulting hierarchy:
        pivotOffsetGrp (at world position of the pivot point)
            └ null_group_1 (zeroed pivots, clean channels)
                └ [parentConstraint] → control

    Args:
        null_grp_1: The pivot null from Stage 1

    Returns:
        Tuple of (success, message, settings_node_name)
    """
    if not cmds.objExists(null_grp_1):
        return False, "Pivot null not found.", None

    # Get target control
    if not cmds.attributeQuery("targetControl", node=null_grp_1, exists=True):
        return False, "Pivot null is not valid (missing targetControl).", None

    control = cmds.getAttr(f"{null_grp_1}.targetControl")
    if not cmds.objExists(control):
        return False, f"Target control '{control}' not found.", None

    # Check if already complete
    if cmds.attributeQuery("setupComplete", node=null_grp_1, exists=True):
        if cmds.getAttr(f"{null_grp_1}.setupComplete"):
            return False, "Setup already complete for this pivot.", None

    cmds.undoInfo(openChunk=True, chunkName="TMP_CompleteSetup")
    try:
        # Exit pivot adjust mode if active
        try:
            mel.eval('ctxEditMode;')
        except Exception:
            pass
        # Switch to select tool to clean up any modal state
        try:
            mel.eval('SelectTool;')
        except Exception:
            pass

        prefix = _sanitize_name(control)

        # =====================================================================
        # PIVOT FREEZING: Convert pivot offset into offset group hierarchy
        # =====================================================================

        # 1. Read the rotatePivot that the user set during Stage 1
        pivot_ws = cmds.xform(null_grp_1, q=True, ws=True, rotatePivot=True)

        # 2. Read null_grp_1's current world matrix (its position at control)
        null_grp_1_world_matrix = cmds.xform(null_grp_1, q=True, ws=True, m=True)

        # 3. Create the pivotOffsetGrp
        offset_grp = cmds.group(
            empty=True,
            name=f"{prefix}{OFFSET_GRP_SUFFIX}"
        )

        # 4. Position pivotOffsetGrp at the world-space pivot point
        #    This group sits at the exact location where the user placed the pivot
        cmds.xform(offset_grp, ws=True, t=pivot_ws)

        # Copy the rotation from null_grp_1 so the offset group is oriented
        # to match the control's rotation (same as null_grp_1's initial orientation)
        null_rot = cmds.xform(null_grp_1, q=True, ws=True, ro=True)
        cmds.xform(offset_grp, ws=True, ro=null_rot)

        # 5. Re-parent null_grp_1 under the offset group
        #    IMPORTANT: After parenting, the DAG path changes.  Re-query by
        #    listing children of offset_grp to get the new valid name.
        cmds.parent(null_grp_1, offset_grp)
        # Re-resolve null_grp_1's name after reparenting (DAG path changed)
        children = cmds.listRelatives(offset_grp, children=True, type="transform", fullPath=True) or []
        for child in children:
            short = child.split("|")[-1]
            if NULL_GRP_1_SUFFIX in short:
                null_grp_1 = child
                break

        # 6. Zero out null_grp_1's local transforms and pivots
        #    The offset is now stored in pivotOffsetGrp's position
        for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
            _safe_set_attr(null_grp_1, attr, 0)

        # Hide scale channels — they are not used by the pivot control
        # and hiding them keeps the Channel Box clean for the animator.
        for attr in ["sx", "sy", "sz"]:
            attr_path = f"{null_grp_1}.{attr}"
            if cmds.objExists(attr_path) and not cmds.getAttr(attr_path, lock=True):
                cmds.setAttr(attr_path, keyable=False, channelBox=False)

        # Zero the pivots - this is the key freeze operation
        cmds.xform(null_grp_1, objectSpace=True, pivots=[0, 0, 0])

        # =====================================================================
        # Create parentConstraint: null_group_1 → control (maintainOffset=ON)
        # =====================================================================
        constraint_name = f"{prefix}{CONSTRAINT_SUFFIX}"
        if cmds.objExists(constraint_name):
            cmds.delete(constraint_name)

        constraint = cmds.parentConstraint(
            null_grp_1, control,
            maintainOffset=True,
            name=constraint_name
        )[0]

        # =====================================================================
        # Create settings node
        # =====================================================================
        settings_node = cmds.createNode("transform", name=f"{prefix}{SETTINGS_SUFFIX}")
        cmds.setAttr(f"{settings_node}.visibility", 0)

        # Store references — use SHORT names (no pipe prefix) so they remain
        # valid after future reparenting operations (toggle on/off).
        null_grp_1_short = null_grp_1.split("|")[-1]
        offset_grp_short = offset_grp.split("|")[-1]
        _add_string_attr(settings_node, "targetControl", control)
        _add_string_attr(settings_node, "nullGrp1", null_grp_1_short)
        _add_string_attr(settings_node, "nullGrp2", "")  # Created on first toggle OFF
        _add_string_attr(settings_node, "pivotOffsetGrp", offset_grp_short)
        _add_string_attr(settings_node, "constraintName", constraint)
        _add_bool_attr(settings_node, "isActive", True)

        # Parent settings under offset_grp for organization
        cmds.parent(settings_node, offset_grp)
        # Re-resolve settings_node after reparenting (DAG path changed)
        settings_node = _resolve_stored_name(settings_node.split("|")[-1])

        # Mark null_grp_1 setup as complete
        cmds.setAttr(f"{null_grp_1}.setupComplete", True)

        # Update null_grp_1 color to indicate active (green)
        _set_null_color(null_grp_1, UI_COLORS["success"])

        # Set up auto-key for transform changes
        _setup_undo_guard()
        setup_auto_key(settings_node)

        # Select null_grp_1 with the Rotate manipulator so the user can
        # start orbiting immediately.  Double-deferred ensures it sticks
        # after all UI refreshes and SelectionChanged scriptJobs settle.
        cmds.select(null_grp_1)
        cmds.setToolTo("RotateSuperContext")
        _deferred_node = null_grp_1  # capture for lambda
        cmds.evalDeferred(
            lambda n=_deferred_node: cmds.evalDeferred(
                lambda: (
                    cmds.select(n, replace=True),
                    cmds.setToolTo("RotateSuperContext"),
                ) if cmds.objExists(n) else None
            )
        )

        return True, f"Setup complete! Rotate pivot null to orbit '{control}' around custom pivot. Auto-key enabled.", settings_node
    finally:
        cmds.undoInfo(closeChunk=True)


# =============================================================================
# TOGGLE ON (Reactivate)
# =============================================================================

def toggle_on(settings_node: str) -> Tuple[bool, str]:
    """
    Reactivate the temp pivot system.

    Process:
    1. Realign null_group_2 to control's current world position/rotation
    2. Move pivotOffsetGrp under null_group_2
    3. Reset null_group_1's LOCAL transforms to zero
    4. Recreate parentConstraint: null_group_1 → control (maintainOffset)
    5. Show visibility

    Args:
        settings_node: The settings node for this rig

    Returns:
        Tuple of (success, message)
    """
    if not cmds.objExists(settings_node):
        return False, "Settings node not found."

    if is_rig_active(settings_node):
        return False, "Rig is already active."

    nodes = get_rig_nodes(settings_node)
    control = nodes["control"]
    null_grp_1 = nodes["null_grp_1"]
    null_grp_2 = nodes["null_grp_2"]
    offset_grp = nodes["pivot_offset_grp"]

    if not control or not cmds.objExists(control):
        return False, f"Control '{control}' not found."
    if not null_grp_1 or not cmds.objExists(null_grp_1):
        return False, "Pivot null (null_group_1) not found."
    if not null_grp_2 or not cmds.objExists(null_grp_2):
        return False, "Anchor null (null_group_2) not found. Cannot toggle ON."

    cmds.undoInfo(openChunk=True, chunkName="TMP_ToggleOn")
    try:
        # =====================================================================
        # Realign null_group_2 to control's current world position/rotation
        # =====================================================================
        _align_to_target_world_matrix(null_grp_2, control)

        # =====================================================================
        # Handle v7 (with offset group) or v6 (without) hierarchy
        # =====================================================================
        if offset_grp and cmds.objExists(offset_grp):
            # v7 architecture - ensure offset_grp is under null_grp_2
            current_parent = cmds.listRelatives(offset_grp, parent=True)
            if not current_parent or current_parent[0] != null_grp_2:
                cmds.parent(offset_grp, null_grp_2)
            # Re-resolve names after reparenting (DAG paths changed)
            offset_grp = _resolve_stored_name(offset_grp.split("|")[-1])
            null_grp_1 = _resolve_stored_name(null_grp_1.split("|")[-1])

            # ---------------------------------------------------------------
            # Orientation fix: sync offset_grp's world rotation to the
            # control's current world rotation.  This zeroes offset_grp's
            # local rotation relative to null_grp_2 so that null_grp_1
            # inherits the control's CURRENT orientation rather than a stale
            # rotation baked in from a previous toggle cycle.
            #
            # Root cause: on the FIRST toggle-OFF, offset_grp is reparented
            # from world-level (where it has R_original) under null_grp_2
            # (which is at R_control_now).  Maya preserves its world rotation,
            # so local_rot = inverse(R_control_now) * R_original — potentially
            # non-zero.  That residual persists and adds a twist to null_grp_1
            # on every subsequent toggle-ON.
            #
            # Changing only the world rotation of offset_grp does NOT affect
            # its world POSITION (translate and rotate are independent), so
            # the pivot point stays in the correct place.
            # ---------------------------------------------------------------
            ctrl_world_rot = cmds.xform(control, q=True, ws=True, ro=True)
            cmds.xform(offset_grp, ws=True, ro=ctrl_world_rot)

            # Reset null_grp_1 local transforms (offset is in the offset group)
            for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
                _safe_set_attr(null_grp_1, attr, 0)
        else:
            # v6 compatibility - null_grp_1 directly under null_grp_2
            current_parent = cmds.listRelatives(null_grp_1, parent=True)
            if not current_parent or current_parent[0] != null_grp_2:
                cmds.parent(null_grp_1, null_grp_2)
            # Re-resolve after reparenting
            null_grp_1 = _resolve_stored_name(null_grp_1.split("|")[-1])

            for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
                _safe_set_attr(null_grp_1, attr, 0)

        # =====================================================================
        # Recreate parentConstraint: null_group_1 → control
        # =====================================================================
        prefix = _sanitize_name(control)
        constraint_name = f"{prefix}{CONSTRAINT_SUFFIX}"

        if cmds.objExists(constraint_name):
            cmds.delete(constraint_name)

        constraint = cmds.parentConstraint(
            null_grp_1, control,
            maintainOffset=True,
            name=constraint_name
        )[0]

        # Update settings
        cmds.setAttr(f"{settings_node}.constraintName", constraint, type="string")
        cmds.setAttr(f"{settings_node}.isActive", True)

        # =====================================================================
        # Show visibility
        # =====================================================================
        if null_grp_2 and cmds.objExists(null_grp_2):
            cmds.setAttr(f"{null_grp_2}.visibility", 1)
        if offset_grp and cmds.objExists(offset_grp):
            cmds.setAttr(f"{offset_grp}.visibility", 1)

        # Update null_grp_1 color to active (green)
        _set_null_color(null_grp_1, UI_COLORS["success"])

        # Set up auto-key for transform changes
        _setup_undo_guard()
        setup_auto_key(settings_node)

        # Select null_grp_1
        cmds.select(null_grp_1)

        return True, f"Pivot ON. Rotate pivot null to orbit '{control}'. Auto-key enabled."
    finally:
        cmds.undoInfo(closeChunk=True)


# =============================================================================
# TOGGLE OFF (Deactivate)
# =============================================================================

def toggle_off(settings_node: str) -> Tuple[bool, str]:
    """
    Deactivate the temp pivot system.

    Process:
    1. Clean up auto-key scriptJobs
    2. Create null_group_2 if it doesn't exist (first toggle OFF)
    3. Align null_group_2 to control's current position
    4. Parent offset group (or null_group_1) under null_group_2
    5. Delete the constraint
    6. Hide visibility

    Args:
        settings_node: The settings node for this rig

    Returns:
        Tuple of (success, message)
    """
    if not cmds.objExists(settings_node):
        return False, "Settings node not found."

    if not is_rig_active(settings_node):
        return False, "Rig is not active."

    nodes = get_rig_nodes(settings_node)
    control = nodes["control"]
    constraint = nodes["constraint"]
    null_grp_1 = nodes["null_grp_1"]
    null_grp_2 = nodes["null_grp_2"]
    offset_grp = nodes["pivot_offset_grp"]

    if not control or not cmds.objExists(control):
        return False, f"Control '{control}' not found."
    if not null_grp_1 or not cmds.objExists(null_grp_1):
        return False, "Pivot null (null_group_1) not found."

    cmds.undoInfo(openChunk=True, chunkName="TMP_ToggleOff")
    try:
        # =====================================================================
        # Clean up auto-key scriptJobs
        # =====================================================================
        cleanup_auto_key(settings_node)

        # =====================================================================
        # Delete the constraint FIRST (before creating/moving anchor)
        # =====================================================================
        if constraint and cmds.objExists(constraint):
            cmds.delete(constraint)

        # Also clean any other constraints from this tool
        constraints = cmds.listRelatives(control, type="parentConstraint") or []
        for c in constraints:
            if CONSTRAINT_SUFFIX in c or TOOL_PREFIX in c:
                cmds.delete(c)

        prefix = _sanitize_name(control)

        # =====================================================================
        # Create null_group_2 if it doesn't exist (first toggle OFF)
        # =====================================================================
        if not null_grp_2 or not cmds.objExists(null_grp_2):
            null_grp_2 = _create_visual_null(
                f"{prefix}{NULL_GRP_2_SUFFIX}",
                UI_COLORS["stage2"],  # Blue for anchor
                size=1.2  # Slightly larger to distinguish
            )
            # Store reference in settings
            cmds.setAttr(f"{settings_node}.nullGrp2", null_grp_2, type="string")

        # =====================================================================
        # Align null_group_2 to control's current world position/rotation
        # =====================================================================
        _align_to_target_world_matrix(null_grp_2, control)

        # =====================================================================
        # Parent hierarchy under null_group_2
        # =====================================================================
        if offset_grp and cmds.objExists(offset_grp):
            # v7: parent offset_grp under null_grp_2
            current_parent = cmds.listRelatives(offset_grp, parent=True)
            if not current_parent or current_parent[0] != null_grp_2:
                cmds.parent(offset_grp, null_grp_2)
            # Re-resolve names after reparenting (DAG paths changed)
            offset_grp = _resolve_stored_name(offset_grp.split("|")[-1])
            null_grp_1 = _resolve_stored_name(null_grp_1.split("|")[-1])
        else:
            # v6 compatibility: parent null_grp_1 directly under null_grp_2
            current_parent = cmds.listRelatives(null_grp_1, parent=True)
            if not current_parent or current_parent[0] != null_grp_2:
                cmds.parent(null_grp_1, null_grp_2)
            # Re-resolve after reparenting
            null_grp_1 = _resolve_stored_name(null_grp_1.split("|")[-1])

        # =====================================================================
        # Reset null_group_1 local transforms
        # =====================================================================
        for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
            _safe_set_attr(null_grp_1, attr, 0)

        # Clear constraint reference and set inactive
        cmds.setAttr(f"{settings_node}.constraintName", "", type="string")
        cmds.setAttr(f"{settings_node}.isActive", False)

        # =====================================================================
        # Hide visibility
        # =====================================================================
        cmds.setAttr(f"{null_grp_2}.visibility", 0)

        # Update null_grp_1 color to inactive (orange)
        _set_null_color(null_grp_1, UI_COLORS["stage1"])

        # Select the control now being manipulated
        cmds.select(control, replace=True)

        return True, f"Pivot OFF. '{control}' is now free to move. Key if needed."
    finally:
        cmds.undoInfo(closeChunk=True)


# =============================================================================
# TOGGLE (Smart)
# =============================================================================

def toggle_pivot(settings_node: str) -> Tuple[bool, str, bool]:
    """Smart toggle - ON if OFF, OFF if ON."""
    if not cmds.objExists(settings_node):
        return False, "Settings node not found.", False

    if is_rig_active(settings_node):
        success, msg = toggle_off(settings_node)
        return success, msg, False
    else:
        success, msg = toggle_on(settings_node)
        return success, msg, True


# =============================================================================
# KEY CONTROL
# =============================================================================

def key_control(settings_node: str) -> Tuple[bool, str]:
    """Set keyframes on the control's translate and rotate, skipping locked/non-keyable attrs."""
    if not cmds.objExists(settings_node):
        return False, "Settings node not found."

    nodes = get_rig_nodes(settings_node)
    control = nodes["control"]

    if not control or not cmds.objExists(control):
        return False, f"Control '{control}' not found."

    current_time = cmds.currentTime(query=True)
    keyed_attrs = []

    for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
        if _safe_set_key(control, attr, time=current_time):
            keyed_attrs.append(attr)

    if keyed_attrs:
        return True, f"Keyed {len(keyed_attrs)} attrs on '{control}' at frame {current_time}."
    else:
        return False, f"Could not key any attributes on '{control}' (locked or non-keyable)."


# =============================================================================
# AUTO-KEY MANAGEMENT
# =============================================================================

def _create_auto_key_callback(settings_node: str):
    """Create a callback function for auto-keying that captures the settings node.

    Undo is suppressed (``stateWithoutFlush=False``) so that the
    setKeyframe call does NOT create a separate undo entry.  This lets
    the user undo a single rotation in one step instead of having to
    undo twice (once for the key, once for the rotation).
    """
    def auto_key_callback():
        # Guard: skip if we are in an undo/redo operation
        global _is_undoing
        if _is_undoing:
            return

        # Only key if the rig is still active
        if cmds.objExists(settings_node) and is_rig_active(settings_node):
            # Suppress undo so the keyframe merges with the user's
            # manipulation command rather than creating a second entry.
            cmds.undoInfo(stateWithoutFlush=False)
            try:
                key_control(settings_node)
            finally:
                cmds.undoInfo(stateWithoutFlush=True)
    return auto_key_callback


def setup_auto_key(settings_node: str) -> None:
    """Set up scriptJobs to auto-key the control when null_group_1 is transformed."""
    global _auto_key_jobs

    # Clean up any existing jobs for this rig
    cleanup_auto_key(settings_node)

    if not cmds.objExists(settings_node):
        return

    nodes = get_rig_nodes(settings_node)
    null_grp_1 = nodes["null_grp_1"]

    if not null_grp_1 or not cmds.objExists(null_grp_1):
        return

    # Create callback function
    callback = _create_auto_key_callback(settings_node)

    # Set up scriptJobs for BOTH translation AND rotation attribute changes
    job_ids = []
    for attr in ["tx", "ty", "tz", "rx", "ry", "rz"]:
        attr_path = f"{null_grp_1}.{attr}"
        if cmds.objExists(attr_path):
            job_id = cmds.scriptJob(
                attributeChange=[attr_path, callback],
                killWithScene=True
            )
            job_ids.append(job_id)

    _auto_key_jobs[settings_node] = job_ids


def cleanup_auto_key(settings_node: str) -> None:
    """Remove auto-key scriptJobs for a rig."""
    global _auto_key_jobs

    if settings_node in _auto_key_jobs:
        for job_id in _auto_key_jobs[settings_node]:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        del _auto_key_jobs[settings_node]


# =============================================================================
# DELETE RIG
# =============================================================================

def delete_pivot_rig(settings_node: str) -> Tuple[bool, str]:
    """Delete the pivot rig completely."""
    if not cmds.objExists(settings_node):
        return False, "Settings node not found."

    nodes = get_rig_nodes(settings_node)
    control = nodes["control"]

    cmds.undoInfo(openChunk=True, chunkName="TMP_DeletePivotRig")
    try:
        # Clean up auto-key scriptJobs (in case they exist)
        cleanup_auto_key(settings_node)

        # Toggle off first
        if is_rig_active(settings_node):
            toggle_off(settings_node)

        # Delete null_group_2 (which parents everything else in v7)
        null_grp_2 = nodes["null_grp_2"]
        if null_grp_2 and cmds.objExists(null_grp_2):
            cmds.delete(null_grp_2)

        # Delete offset group if it wasn't parented under null_group_2
        offset_grp = nodes["pivot_offset_grp"]
        if offset_grp and cmds.objExists(offset_grp):
            cmds.delete(offset_grp)

        # Delete null_group_1 if it wasn't parented under null_group_2 or offset_grp
        null_grp_1 = nodes["null_grp_1"]
        if null_grp_1 and cmds.objExists(null_grp_1):
            cmds.delete(null_grp_1)

        # Clean up orphaned settings node
        if cmds.objExists(settings_node):
            cmds.delete(settings_node)

        # Remove any remaining constraints
        if control and cmds.objExists(control):
            constraints = cmds.listRelatives(control, type="parentConstraint") or []
            for c in constraints:
                if CONSTRAINT_SUFFIX in c or TOOL_PREFIX in c:
                    cmds.delete(c)

        return True, f"Deleted pivot rig for '{control}'."
    finally:
        cmds.undoInfo(closeChunk=True)


def delete_pending_pivot(null_grp_1: str) -> Tuple[bool, str]:
    """Delete a pending (Stage 1) pivot null."""
    if not cmds.objExists(null_grp_1):
        return False, "Pivot null not found."

    control = ""
    if cmds.attributeQuery("targetControl", node=null_grp_1, exists=True):
        control = cmds.getAttr(f"{null_grp_1}.targetControl")

    cmds.undoInfo(openChunk=True, chunkName="TMP_DeletePending")
    try:
        cmds.delete(null_grp_1)
        return True, f"Deleted pending pivot null for '{control}'."
    finally:
        cmds.undoInfo(closeChunk=True)


# =============================================================================
# UI IMPLEMENTATION (Dockable with workspaceControl)
# =============================================================================

def _build_ui(parent_layout: str) -> None:
    """
    Build the tool UI inside the given parent layout.

    This is separated from show() so the same UI can be placed inside
    either a workspaceControl or a plain window.

    Any existing children are removed first so the function is
    idempotent — safe to call from both show() and the uiScript
    callback without producing duplicates.
    """
    # Kill any SelectionChanged scriptJobs registered by a previous _build_ui
    # call.  They are parented to the workspaceControl (not to its children),
    # so they survive child deletion and would keep firing with stale widget
    # path closures, causing RuntimeError: Object '...' not found.
    global _ui_script_jobs
    for _jid in _ui_script_jobs:
        try:
            if cmds.scriptJob(exists=_jid):
                cmds.scriptJob(kill=_jid, force=True)
        except Exception:
            pass
    _ui_script_jobs = []

    cmds.setParent(parent_layout)
    existing = cmds.layout(parent_layout, query=True, childArray=True) or []
    for child in existing:
        try:
            cmds.deleteUI(child)
        except RuntimeError:
            pass

    # ==========================================
    # ROOT FORM (anchors header / body / footer)
    # ==========================================

    main_form = cmds.formLayout(numberOfDivisions=100)

    # ------------------------------------------
    # HEADER (top strip)
    # ------------------------------------------

    header = cmds.rowLayout(
        numberOfColumns=3,
        adjustableColumn=2,
        columnWidth3=(6, 10, 110),
        columnAttach3=("both", "both", "right"),
        height=48
    )
    cmds.canvas(width=4, height=44, rgbValue=UI_COLORS["accent"])
    cmds.columnLayout(adjustableColumn=True, rowSpacing=0)
    cmds.text(
        label="  Temp Pivot Tool",
        font="boldLabelFont",
        align="left",
        height=24
    )
    cmds.text(
        label="  Non-destructive pivot system for animation",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.setParent("..")
    cmds.text(
        label="v7  ",
        align="right",
        font="smallBoldLabelFont"
    )
    cmds.setParent("..")  # header rowLayout

    # ------------------------------------------
    # FOOTER (bottom strip - log + close)
    # ------------------------------------------

    footer = cmds.formLayout(numberOfDivisions=100, height=120)

    log_frame = cmds.frameLayout(
        label="  Output Log",
        collapsable=True,
        collapse=True,
        marginWidth=4,
        marginHeight=4
    )
    log_field = cmds.scrollField(
        height=72,
        editable=False,
        wordWrap=True,
        font="smallPlainLabelFont",
        text="Ready. Select a control and click 'Create Pivot Locator'."
    )
    cmds.setParent("..")  # log_frame

    close_btn = cmds.button(
        label="Close Tool",
        width=110,
        height=28,
        backgroundColor=(0.42, 0.42, 0.42),
        annotation="Close the Temp Pivot Tool window."
    )

    cmds.formLayout(
        footer, edit=True,
        attachForm=[
            (log_frame, "left", 6),
            (log_frame, "top", 4),
            (log_frame, "bottom", 4),
            (close_btn, "right", 8),
            (close_btn, "bottom", 6),
        ],
        attachControl=[(log_frame, "right", 6, close_btn)],
        attachNone=[(close_btn, "top")]
    )
    cmds.setParent("..")  # footer

    # ------------------------------------------
    # BODY - paneLayout: sidebar + tabs
    # ------------------------------------------

    body = cmds.paneLayout(
        configuration="vertical2",
        paneSize=[(1, 32, 100), (2, 68, 100)]
    )

    # ============== LEFT SIDEBAR ===============
    sidebar = cmds.columnLayout(
        adjustableColumn=True,
        rowSpacing=4,
        columnAttach=("both", 8)
    )

    cmds.separator(height=6, style="none")

    # State badge - large and prominent
    state_indicator = cmds.button(
        label="READY",
        height=44,
        backgroundColor=UI_COLORS["off_state"],
        enable=False
    )

    selection_text = cmds.text(
        label="  Select a rig control to begin",
        align="left",
        font="smallPlainLabelFont",
        height=22,
        wordWrap=True
    )

    cmds.separator(height=8, style="in")

    # Temp Pivot Null detail row
    cmds.rowLayout(
        numberOfColumns=2,
        adjustableColumn=2,
        columnWidth2=(6, 10),
        columnAttach2=("both", "both"),
        columnOffset2=(0, 4)
    )
    cmds.canvas(width=4, height=38, rgbValue=UI_COLORS["pivot_label"])
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.text(
        label="TEMP PIVOT NULL",
        align="left",
        font="smallBoldLabelFont",
        height=16
    )
    pivot_detail_text = cmds.text(
        label="—",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.setParent("..")
    cmds.setParent("..")  # piv_row

    # Original Control detail row
    cmds.rowLayout(
        numberOfColumns=2,
        adjustableColumn=2,
        columnWidth2=(6, 10),
        columnAttach2=("both", "both"),
        columnOffset2=(0, 4)
    )
    cmds.canvas(width=4, height=38, rgbValue=UI_COLORS["ctrl_label"])
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.text(
        label="ORIGINAL CONTROL",
        align="left",
        font="smallBoldLabelFont",
        height=16
    )
    control_detail_text = cmds.text(
        label="—",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.setParent("..")
    cmds.setParent("..")  # ctl_row

    cmds.separator(height=10, style="in")

    cmds.text(
        label="QUICK ACTIONS",
        align="left",
        font="smallBoldLabelFont",
        height=18
    )

    toggle_btn = cmds.button(
        label="Toggle ON / OFF",
        height=36,
        backgroundColor=UI_COLORS["success"],
        annotation=TOOLTIPS["toggle_btn"]
    )

    key_btn = cmds.button(
        label="Key Control",
        height=28,
        annotation=TOOLTIPS["key_btn"]
    )

    cmds.separator(height=6, style="none")

    cmds.text(
        label="NAVIGATE",
        align="left",
        font="smallBoldLabelFont",
        height=16
    )

    cmds.rowLayout(
        numberOfColumns=2,
        adjustableColumn=1,
        columnWidth2=(1, 1),
        columnAttach2=("both", "both"),
        columnOffset2=(0, 4)
    )
    select_pivot_btn = cmds.button(
        label="Pivot Null",
        height=26,
        annotation=TOOLTIPS["select_pivot_btn"]
    )
    select_control_btn = cmds.button(
        label="Control",
        height=26,
        annotation=TOOLTIPS["select_control_btn"]
    )
    cmds.setParent("..")  # nav_row

    cmds.separator(height=10, style="in")

    delete_btn = cmds.button(
        label="Delete Pivot Rig",
        height=28,
        backgroundColor=UI_COLORS["error"],
        annotation=TOOLTIPS["delete_btn"]
    )

    cmds.separator(height=6, style="none")

    cmds.setParent("..")  # sidebar columnLayout

    # ============== RIGHT TAB AREA ===============
    tabs = cmds.tabLayout(
        innerMarginWidth=8,
        innerMarginHeight=8,
        tabsVisible=True
    )

    # ------ TAB 1: WORKFLOW ------
    tab_workflow = cmds.formLayout(numberOfDivisions=100)

    stage1_frame = cmds.frameLayout(
        label="  STAGE 1  —  Create Pivot Locator",
        collapsable=False,
        marginWidth=8,
        marginHeight=8
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(
        label="Select a rig control in the viewport.",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.text(
        label="Pivot-adjust mode activates automatically —",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.text(
        label="move the locator to your desired pivot point.",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.separator(height=4, style="none")
    create_pivot_btn = cmds.button(
        label="Create Pivot Locator",
        height=42,
        backgroundColor=UI_COLORS["stage1"],
        annotation=TOOLTIPS["create_pivot_btn"]
    )
    cmds.setParent("..")
    cmds.setParent("..")  # stage1_frame

    stage2_frame = cmds.frameLayout(
        label="  STAGE 2  —  Complete Setup",
        collapsable=False,
        marginWidth=8,
        marginHeight=8
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(
        label="After positioning the pivot, click below.",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.text(
        label="Bakes the offset and creates the constraint.",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.text(
        label="Auto-key captures animation as you rotate.",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )
    cmds.separator(height=4, style="none")
    complete_setup_btn = cmds.button(
        label="Complete Setup",
        height=42,
        backgroundColor=UI_COLORS["stage2"],
        annotation=TOOLTIPS["complete_setup_btn"]
    )
    cmds.setParent("..")
    cmds.setParent("..")  # stage2_frame

    guide_frame = cmds.frameLayout(
        label="  WORKFLOW GUIDE",
        collapsable=True,
        collapse=False,
        marginWidth=8,
        marginHeight=8
    )
    cmds.rowColumnLayout(
        numberOfColumns=2,
        columnWidth=[(1, 220), (2, 220)],
        columnSpacing=[(1, 0), (2, 12)],
        rowSpacing=[(1, 4)]
    )

    _steps = [
        ("1", "Select a rig control", UI_COLORS["stage1"]),
        ("2", "Click  Create Pivot Locator", UI_COLORS["stage1"]),
        ("3", "Move pivot  (D key / Insert)", (0.55, 0.55, 0.58)),
        ("4", "Click  Complete Setup", UI_COLORS["stage2"]),
        ("5", "Rotate pivot null to animate", UI_COLORS["success"]),
        ("6", "Toggle OFF when done", UI_COLORS["off_state"]),
    ]
    for _num, _txt, _col in _steps:
        cmds.rowLayout(
            numberOfColumns=2,
            adjustableColumn=2,
            columnWidth2=(22, 1),
            columnAttach2=("both", "both"),
            columnOffset2=(0, 4)
        )
        cmds.text(
            label=_num,
            align="center",
            width=22,
            height=22,
            font="smallBoldLabelFont",
            backgroundColor=_col
        )
        cmds.text(
            label=f"  {_txt}",
            align="left",
            height=22,
            font="smallPlainLabelFont"
        )
        cmds.setParent("..")  # rowLayout (cell)
    cmds.setParent("..")  # rowColumnLayout
    cmds.setParent("..")  # guide_frame

    cmds.formLayout(
        tab_workflow, edit=True,
        attachForm=[
            (stage1_frame, "top", 4),
            (stage1_frame, "left", 4),
            (stage2_frame, "top", 4),
            (stage2_frame, "right", 4),
            (guide_frame, "left", 4),
            (guide_frame, "right", 4),
            (guide_frame, "bottom", 4),
        ],
        attachPosition=[
            (stage1_frame, "right", 4, 50),
            (stage2_frame, "left", 4, 50),
        ],
        attachControl=[
            (guide_frame, "top", 8, stage1_frame),
        ],
        attachNone=[
            (stage1_frame, "bottom"),
            (stage2_frame, "bottom"),
        ]
    )
    cmds.setParent("..")  # tab_workflow

    # ------ TAB 2: ACTIVE RIGS ------
    tab_rigs = cmds.formLayout(numberOfDivisions=100)

    list_header = cmds.rowLayout(
        numberOfColumns=2,
        adjustableColumn=2,
        columnWidth2=(60, 10),
        columnAttach2=("both", "both"),
        columnOffset2=(0, 0),
        height=22
    )
    cmds.text(
        label=" Status",
        align="left",
        width=60,
        height=22,
        font="smallBoldLabelFont",
        backgroundColor=UI_COLORS["section_bg"]
    )
    cmds.text(
        label="  Temp Pivot Null   →   Original Control",
        align="left",
        height=22,
        font="smallBoldLabelFont",
        backgroundColor=UI_COLORS["section_bg"]
    )
    cmds.setParent("..")  # list_header

    rig_list = cmds.textScrollList(
        allowMultiSelection=False,
        font="fixedWidthFont"
    )

    list_btns = cmds.rowLayout(
        numberOfColumns=3,
        adjustableColumn=2,
        columnWidth3=(90, 10, 110),
        columnAttach3=("both", "both", "both"),
        columnOffset3=(0, 6, 6),
        height=30
    )
    refresh_btn = cmds.button(label="Refresh", height=28)
    toggle_list_btn = cmds.button(
        label="Toggle Selected",
        height=28,
        backgroundColor=UI_COLORS["success"]
    )
    delete_list_btn = cmds.button(
        label="Delete Selected",
        height=28,
        backgroundColor=UI_COLORS["error"]
    )
    cmds.setParent("..")  # list_btns

    list_help = cmds.text(
        label="  Click a row to select pivot in viewport.   Double-click to toggle.",
        align="left",
        font="smallPlainLabelFont",
        height=18
    )

    cmds.formLayout(
        tab_rigs, edit=True,
        attachForm=[
            (list_header, "top", 4),
            (list_header, "left", 4),
            (list_header, "right", 4),
            (rig_list, "left", 4),
            (rig_list, "right", 4),
            (list_btns, "left", 4),
            (list_btns, "right", 4),
            (list_help, "left", 4),
            (list_help, "right", 4),
            (list_help, "bottom", 4),
        ],
        attachControl=[
            (rig_list, "top", 0, list_header),
            (rig_list, "bottom", 6, list_btns),
            (list_btns, "bottom", 4, list_help),
        ]
    )
    cmds.setParent("..")  # tab_rigs

    # ------ TAB 3: HELP & TIPS ------
    tab_help = cmds.scrollLayout(
        childResizable=True,
        horizontalScrollBarThickness=0
    )
    cmds.columnLayout(
        adjustableColumn=True,
        rowSpacing=8,
        columnAttach=("both", 6)
    )

    cmds.separator(height=4, style="none")
    cmds.text(
        label="HOW IT WORKS",
        align="left",
        font="boldLabelFont",
        height=20
    )
    cmds.text(
        label="The Temp Pivot Tool builds a non-destructive two-null rig "
              "around any control so you can rotate around a custom pivot "
              "without breaking the original animation channels.",
        align="left",
        font="smallPlainLabelFont",
        wordWrap=True,
        height=48
    )

    cmds.separator(height=4, style="in")

    cmds.text(
        label="HIERARCHY (when active)",
        align="left",
        font="boldLabelFont",
        height=20
    )
    cmds.text(
        label=(
            "  null_group_2     POSITION ANCHOR\n"
            "    └ pivotOffsetGrp     baked offset (translate)\n"
            "        └ null_group_1     ANIMATOR PIVOT  (clean 0,0,0)\n"
            "            └ [parentConstraint]  →  control"
        ),
        align="left",
        font="fixedWidthFont",
        height=72
    )

    cmds.separator(height=4, style="in")

    cmds.text(
        label="TIPS",
        align="left",
        font="boldLabelFont",
        height=20
    )
    _tips = [
        "Press D (or Insert) while the pivot null is selected to nudge "
        "the pivot location at any time before Stage 2.",
        "Toggling OFF preserves the anchor position — you can move the "
        "control freely, then Toggle ON to re-link the rig.",
        "Auto-key fires on the original control whenever the pivot null "
        "is rotated, so animation is captured live.",
        "Use the Active Rigs tab to manage multiple temp pivots in the "
        "same scene — single click selects, double-click toggles.",
    ]
    for _tip in _tips:
        cmds.rowLayout(
            numberOfColumns=2,
            adjustableColumn=2,
            columnWidth2=(14, 10),
            columnAttach2=("both", "both"),
            columnOffset2=(0, 4)
        )
        cmds.text(
            label="▸",
            align="left",
            width=14,
            font="smallBoldLabelFont"
        )
        cmds.text(
            label=_tip,
            align="left",
            font="smallPlainLabelFont",
            wordWrap=True
        )
        cmds.setParent("..")

    cmds.separator(height=4, style="in")

    cmds.text(
        label="  Temp Pivot Tool  v7.0.0   •   David Shepstone   •   MIT License",
        align="center",
        font="smallPlainLabelFont",
        height=20
    )
    cmds.separator(height=8, style="none")

    cmds.setParent("..")  # help columnLayout
    cmds.setParent("..")  # tab_help scrollLayout

    cmds.tabLayout(
        tabs, edit=True,
        tabLabel=[
            (tab_workflow, "Workflow"),
            (tab_rigs, "Active Rigs"),
            (tab_help, "Help & Tips"),
        ]
    )
    cmds.setParent("..")  # tabs

    cmds.setParent("..")  # body paneLayout

    # ------------------------------------------
    # Anchor everything to the root form
    # ------------------------------------------

    cmds.formLayout(
        main_form, edit=True,
        attachForm=[
            (header, "left", 6),
            (header, "top", 6),
            (header, "right", 6),
            (body, "left", 0),
            (body, "right", 0),
            (footer, "left", 0),
            (footer, "right", 0),
            (footer, "bottom", 0),
        ],
        attachControl=[
            (body, "top", 4, header),
            (body, "bottom", 2, footer),
        ]
    )

    # ==========================================
    # CALLBACKS
    # ==========================================

    # Flag to prevent list refresh during programmatic selection from the list
    _skip_list_refresh = [False]

    def log_message(message: str, msg_type: str = "info") -> None:
        prefix_map = {"warning": "[!] ", "error": "[X] ", "success": "[OK] ", "info": ""}
        prefix = prefix_map.get(msg_type, "")
        current = cmds.scrollField(log_field, query=True, text=True) or ""
        new_text = f"{prefix}{message}"
        if current and not current.startswith("Ready."):
            new_text = f"{current}\n{new_text}"
        cmds.scrollField(log_field, edit=True, text=new_text)
        cmds.scrollField(log_field, edit=True, insertionPosition=len(new_text))

    def refresh_rig_list(preserve_selection: bool = True) -> None:
        """Refresh the rig list, optionally preserving the current selection."""
        if _skip_list_refresh[0]:
            return

        # Save current selection — items use format: "[ON]  pivot  →  control"
        selected_control = None
        if preserve_selection:
            selected_items = cmds.textScrollList(rig_list, query=True, selectItem=True) or []
            if selected_items:
                raw = selected_items[0]
                parts = raw.split("\u2192")
                if len(parts) >= 2:
                    selected_control = parts[1].strip()
                else:
                    selected_control = raw.split("[")[0].strip()

        cmds.textScrollList(rig_list, edit=True, removeAll=True)
        rigs = get_all_pivot_rigs()
        for settings_node in sorted(rigs):
            nodes = get_rig_nodes(settings_node)
            control = nodes.get("control") or "?"
            pivot_null = nodes.get("null_grp_1") or "?"
            control_short = control.split("|")[-1]
            pivot_short = pivot_null.split("|")[-1]
            active = is_rig_active(settings_node)
            status_tag = " [ON] " if active else " [OFF]"
            # Padded so the arrow column lines up
            entry = f"{status_tag}  {pivot_short}  \u2192  {control_short}"
            cmds.textScrollList(rig_list, edit=True, append=entry)

        if selected_control:
            all_items = cmds.textScrollList(rig_list, query=True, allItems=True) or []
            for item in all_items:
                if selected_control in item:
                    cmds.textScrollList(rig_list, edit=True, selectItem=item)
                    break

    def _resolve_selection() -> List[str]:
        """Get the current selection resolved to transforms."""
        raw_sel = cmds.ls(selection=True, long=True) or []
        resolved = []
        for item in raw_sel:
            resolved_node = _resolve_transform(item)
            if cmds.objExists(resolved_node) and cmds.nodeType(resolved_node) == "transform":
                resolved.append(resolved_node)
        return resolved

    def update_status() -> None:
        sel = _resolve_selection()
        selected_settings = None
        pending_pivot = None

        for item in sel:
            short_name = item.split("|")[-1]

            if NULL_GRP_1_SUFFIX in short_name:
                if cmds.attributeQuery("setupComplete", node=item, exists=True):
                    if cmds.getAttr(f"{item}.setupComplete"):
                        prefix = short_name.replace(NULL_GRP_1_SUFFIX, "")
                        possible_settings = f"{prefix}{SETTINGS_SUFFIX}"
                        if cmds.objExists(possible_settings):
                            selected_settings = possible_settings
                    else:
                        pending_pivot = item
                break
            if NULL_GRP_2_SUFFIX in short_name:
                prefix = short_name.replace(NULL_GRP_2_SUFFIX, "")
                possible_settings = f"{prefix}{SETTINGS_SUFFIX}"
                if cmds.objExists(possible_settings):
                    selected_settings = possible_settings
                break
            if OFFSET_GRP_SUFFIX in short_name:
                prefix = short_name.replace(OFFSET_GRP_SUFFIX, "")
                possible_settings = f"{prefix}{SETTINGS_SUFFIX}"
                if cmds.objExists(possible_settings):
                    selected_settings = possible_settings
                break
            rig = get_rig_for_control(item)
            if rig:
                selected_settings = rig
                break
            short = item.split("|")[-1]
            rig = get_rig_for_control(short)
            if rig:
                selected_settings = rig
                break
            pending = get_pending_pivot_for_control(item)
            if pending:
                pending_pivot = pending

        if selected_settings:
            nodes = get_rig_nodes(selected_settings)
            control = nodes.get("control") or "?"
            pivot_null = nodes.get("null_grp_1") or "?"
            control_short = control.split("|")[-1]
            pivot_short = pivot_null.split("|")[-1]
            active = is_rig_active(selected_settings)

            cmds.text(
                selection_text,
                edit=True,
                label=f"  Pivot rig active — rotate pivot null to animate"
            )
            cmds.text(pivot_detail_text, edit=True, label=f"  {pivot_short}")
            cmds.text(control_detail_text, edit=True, label=f"  {control_short}")

            if active:
                cmds.button(
                    state_indicator, edit=True,
                    label="ON",
                    backgroundColor=UI_COLORS["success"]
                )
                cmds.button(
                    toggle_btn, edit=True,
                    label="Toggle OFF  (free control)",
                    backgroundColor=UI_COLORS["warning"]
                )
            else:
                cmds.button(
                    state_indicator, edit=True,
                    label="OFF",
                    backgroundColor=UI_COLORS["off_state"]
                )
                cmds.button(
                    toggle_btn, edit=True,
                    label="Toggle ON  (activate pivot)",
                    backgroundColor=UI_COLORS["success"]
                )

        elif pending_pivot:
            pivot_short = pending_pivot.split("|")[-1]
            cmds.text(
                selection_text,
                edit=True,
                label="  Stage 1 complete — move pivot, then click Complete Setup"
            )
            cmds.text(pivot_detail_text, edit=True, label=f"  {pivot_short}  (pending)")
            if cmds.attributeQuery("targetControl", node=pending_pivot, exists=True):
                ctrl_name = cmds.getAttr(f"{pending_pivot}.targetControl")
                cmds.text(control_detail_text, edit=True, label=f"  {ctrl_name}")
            else:
                cmds.text(control_detail_text, edit=True, label="  —")
            cmds.button(
                state_indicator, edit=True,
                label="STAGE 1",
                backgroundColor=UI_COLORS["stage1"]
            )
            cmds.button(
                toggle_btn, edit=True,
                label="Toggle ON / OFF",
                backgroundColor=UI_COLORS["success"]
            )

        elif sel:
            display_name = sel[0].split("|")[-1]
            cmds.text(selection_text, edit=True, label=f"  Selected: {display_name}")
            cmds.text(pivot_detail_text, edit=True, label="  —")
            cmds.text(control_detail_text, edit=True, label="  —")
            cmds.button(
                state_indicator, edit=True,
                label="READY",
                backgroundColor=UI_COLORS["off_state"]
            )
            cmds.button(
                toggle_btn, edit=True,
                label="Toggle ON / OFF",
                backgroundColor=UI_COLORS["success"]
            )

        else:
            cmds.text(selection_text, edit=True, label="  Select a rig control to begin")
            cmds.text(pivot_detail_text, edit=True, label="  —")
            cmds.text(control_detail_text, edit=True, label="  —")
            cmds.button(
                state_indicator, edit=True,
                label="READY",
                backgroundColor=UI_COLORS["off_state"]
            )
            cmds.button(
                toggle_btn, edit=True,
                label="Toggle ON / OFF",
                backgroundColor=UI_COLORS["success"]
            )

    def get_current_context():
        """Get current rig settings or pending pivot."""
        sel = _resolve_selection()

        for item in sel:
            short_name = item.split("|")[-1]

            if NULL_GRP_1_SUFFIX in short_name:
                if cmds.attributeQuery("setupComplete", node=item, exists=True):
                    if cmds.getAttr(f"{item}.setupComplete"):
                        prefix = short_name.replace(NULL_GRP_1_SUFFIX, "")
                        possible_settings = f"{prefix}{SETTINGS_SUFFIX}"
                        if cmds.objExists(possible_settings):
                            return ("rig", possible_settings)
                    else:
                        return ("pending", item)
            if NULL_GRP_2_SUFFIX in short_name:
                prefix = short_name.replace(NULL_GRP_2_SUFFIX, "")
                possible_settings = f"{prefix}{SETTINGS_SUFFIX}"
                if cmds.objExists(possible_settings):
                    return ("rig", possible_settings)
            if OFFSET_GRP_SUFFIX in short_name:
                prefix = short_name.replace(OFFSET_GRP_SUFFIX, "")
                possible_settings = f"{prefix}{SETTINGS_SUFFIX}"
                if cmds.objExists(possible_settings):
                    return ("rig", possible_settings)

            rig = get_rig_for_control(item)
            if rig:
                return ("rig", rig)
            short = item.split("|")[-1]
            rig = get_rig_for_control(short)
            if rig:
                return ("rig", rig)

            pending = get_pending_pivot_for_control(item)
            if pending:
                return ("pending", pending)

        return (None, None)

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------

    def on_create_pivot(*args):
        cmds.refresh(force=True)
        sel = _resolve_selection()
        controls = [s for s in sel if TOOL_PREFIX not in s.split("|")[-1]]

        if not controls:
            log_message("Select a control first.", "warning")
            return

        control = controls[0]
        short = control.split("|")[-1]
        if len(cmds.ls(short)) == 1:
            control = short

        success, msg, pivot = create_pivot_locator(control)
        log_message(msg, "success" if success else "warning")
        cmds.evalDeferred(refresh_rig_list)
        cmds.evalDeferred(update_status)

    def _deferred_select_pivot(node_name: str) -> None:
        """Select the pivot null via double-deferred to survive UI refreshes."""
        def _inner():
            if cmds.objExists(node_name):
                cmds.select(node_name, replace=True)
                cmds.setToolTo("RotateSuperContext")
        cmds.evalDeferred(lambda: cmds.evalDeferred(_inner))

    def on_complete_setup(*args):
        ctx_type, ctx_node = get_current_context()
        pivot_to_select = None

        if ctx_type == "pending":
            success, msg, settings = complete_setup(ctx_node)
            log_message(msg, "success" if success else "error")
            if success and settings:
                nodes = get_rig_nodes(settings)
                pivot_to_select = nodes["null_grp_1"]
        elif ctx_type == "rig":
            log_message("Setup already complete. Use Toggle to activate.", "warning")
        else:
            sel = _resolve_selection()
            found = False
            for item in sel:
                short = item.split("|")[-1]
                pending = get_pending_pivot_for_control(item)
                if not pending:
                    pending = get_pending_pivot_for_control(short)
                if pending:
                    success, msg, settings = complete_setup(pending)
                    log_message(msg, "success" if success else "error")
                    if success and settings:
                        nodes = get_rig_nodes(settings)
                        pivot_to_select = nodes["null_grp_1"]
                    found = True
                    break
            if not found:
                log_message("No pending pivot null found. Create one first.", "warning")

        refresh_rig_list()
        update_status()
        if pivot_to_select and cmds.objExists(pivot_to_select):
            _deferred_select_pivot(pivot_to_select)

    def on_toggle(*args):
        ctx_type, ctx_node = get_current_context()
        if ctx_type == "rig":
            success, msg, is_active = toggle_pivot(ctx_node)
            log_message(msg, "success" if success else "error")
        elif ctx_type == "pending":
            log_message("Complete setup first before toggling.", "warning")
        else:
            log_message("No pivot rig found. Create and complete setup first.", "warning")
        refresh_rig_list()
        update_status()

    def on_key(*args):
        ctx_type, ctx_node = get_current_context()
        if ctx_type == "rig":
            success, msg = key_control(ctx_node)
            log_message(msg, "success" if success else "error")
        else:
            log_message("No active pivot rig found.", "warning")

    def on_delete(*args):
        ctx_type, ctx_node = get_current_context()
        if ctx_type == "rig":
            success, msg = delete_pivot_rig(ctx_node)
            log_message(msg, "success" if success else "error")
        elif ctx_type == "pending":
            success, msg = delete_pending_pivot(ctx_node)
            log_message(msg, "success" if success else "error")
        else:
            log_message("No pivot rig found.", "warning")
        refresh_rig_list()
        update_status()

    def on_select_pivot(*args):
        ctx_type, ctx_node = get_current_context()
        if ctx_type == "rig":
            nodes = get_rig_nodes(ctx_node)
            pivot = nodes["null_grp_1"]
            if pivot and cmds.objExists(pivot):
                cmds.select(pivot)
                log_message(f"Selected pivot null: {pivot}", "info")
        elif ctx_type == "pending":
            cmds.select(ctx_node)
            log_message(f"Selected: {ctx_node}", "info")
        else:
            log_message("No pivot null found.", "warning")

    def on_select_control(*args):
        ctx_type, ctx_node = get_current_context()
        if ctx_type == "rig":
            nodes = get_rig_nodes(ctx_node)
            control = nodes["control"]
            if control and cmds.objExists(control):
                cmds.select(control)
                log_message(f"Selected control: {control}", "info")
        elif ctx_type == "pending":
            if cmds.attributeQuery("targetControl", node=ctx_node, exists=True):
                control = cmds.getAttr(f"{ctx_node}.targetControl")
                if cmds.objExists(control):
                    cmds.select(control)
                    log_message(f"Selected control: {control}", "info")
        else:
            log_message("No control found.", "warning")

    def on_list_select(*args):
        """Handle rig list selection — select pivot null in viewport."""
        selected_items = cmds.textScrollList(rig_list, query=True, selectItem=True) or []
        if selected_items:
            raw = selected_items[0]
            # Format: " [ON]  pivot_name  →  control_name"
            parts = raw.split("\u2192")
            if len(parts) >= 2:
                control_name = parts[1].strip()
            else:
                # Fallback for unexpected format
                control_name = raw.split("[")[0].strip() if "[" in raw else raw.strip()
            settings = get_rig_for_control(control_name)
            if settings:
                nodes = get_rig_nodes(settings)
                pivot = nodes["null_grp_1"]
                if pivot and cmds.objExists(pivot):
                    _skip_list_refresh[0] = True
                    try:
                        cmds.select(pivot)
                    finally:
                        cmds.evalDeferred(lambda: _skip_list_refresh.__setitem__(0, False))
        update_status()

    def on_list_toggle(*args):
        selected_items = cmds.textScrollList(rig_list, query=True, selectItem=True) or []
        if not selected_items:
            log_message("Select a rig from the list first.", "warning")
            return
        raw = selected_items[0]
        parts = raw.split("\u2192")
        control_name = parts[1].strip() if len(parts) >= 2 else raw.split("[")[0].strip()
        settings = get_rig_for_control(control_name)
        if settings:
            success, msg, is_active = toggle_pivot(settings)
            log_message(msg, "success" if success else "error")
            refresh_rig_list()
            update_status()

    def on_list_delete(*args):
        selected_items = cmds.textScrollList(rig_list, query=True, selectItem=True) or []
        if not selected_items:
            log_message("Select a rig from the list to delete.", "warning")
            return
        raw = selected_items[0]
        parts = raw.split("\u2192")
        control_name = parts[1].strip() if len(parts) >= 2 else raw.split("[")[0].strip()
        settings = get_rig_for_control(control_name)
        if settings:
            success, msg = delete_pivot_rig(settings)
            log_message(msg, "success" if success else "error")
            refresh_rig_list(preserve_selection=False)
            update_status()

    def on_close(*args):
        """Close the tool window / workspace control."""
        if (hasattr(cmds, "workspaceControl")
                and cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True)):
            cmds.deleteUI(WORKSPACE_CONTROL_NAME)
        elif cmds.window(WINDOW_NAME, exists=True):
            cmds.deleteUI(WINDOW_NAME)

    # ------------------------------------------------------------------
    # Connect callbacks
    # ------------------------------------------------------------------

    cmds.button(create_pivot_btn, edit=True, command=on_create_pivot)
    cmds.button(complete_setup_btn, edit=True, command=on_complete_setup)
    cmds.button(toggle_btn, edit=True, command=on_toggle)
    cmds.button(key_btn, edit=True, command=on_key)
    cmds.button(delete_btn, edit=True, command=on_delete)
    cmds.button(select_pivot_btn, edit=True, command=on_select_pivot)
    cmds.button(select_control_btn, edit=True, command=on_select_control)
    cmds.button(toggle_list_btn, edit=True, command=on_list_toggle)
    cmds.button(delete_list_btn, edit=True, command=on_list_delete)
    cmds.button(refresh_btn, edit=True, command=lambda *_: refresh_rig_list())
    cmds.button(close_btn, edit=True, command=on_close)

    cmds.textScrollList(rig_list, edit=True, selectCommand=on_list_select)
    cmds.textScrollList(rig_list, edit=True, doubleClickCommand=on_list_toggle)

    # Parent scriptJobs to the top-level UI element so they are
    # automatically killed when the panel / window is closed.
    if (hasattr(cmds, "workspaceControl")
            and cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True)):
        script_parent = WORKSPACE_CONTROL_NAME
    elif cmds.window(WINDOW_NAME, exists=True):
        script_parent = WINDOW_NAME
    else:
        script_parent = parent_layout

    _ui_script_jobs.append(
        cmds.scriptJob(event=["SelectionChanged", update_status], parent=script_parent)
    )
    _ui_script_jobs.append(
        cmds.scriptJob(event=["SelectionChanged", refresh_rig_list], parent=script_parent)
    )

    # Initialize
    refresh_rig_list()
    update_status()


def _rebuild_workspace_ui() -> None:
    """Rebuild the tool UI inside an existing workspaceControl.

    Called by Maya's ``uiScript`` mechanism whenever the workspace
    control is restored (e.g. after Maya restart or re-dock).
    """
    _setup_undo_guard()
    _build_ui(WORKSPACE_CONTROL_NAME)


def show() -> None:
    """
    Show the Temp Pivot Tool.

    Uses workspaceControl (Maya 2017+) so the tool can be docked, but
    launches as a **floating window** on first open.  If the user has
    previously docked it, re-running the script will restore and focus
    the existing panel instead of creating a duplicate.

    Falls back to a regular floating window if workspaceControl is
    unavailable (Maya < 2017).
    """
    # Install the undo guard
    _setup_undo_guard()

    # ------------------------------------------------------------------
    # Try workspaceControl (dockable) first
    # ------------------------------------------------------------------
    use_workspace = hasattr(cmds, "workspaceControl")

    if use_workspace:
        # Always delete and recreate so the UI is fully rebuilt.
        # This guarantees the Close button (and everything else) is
        # present whether the panel is floating or docked.
        if cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
            cmds.deleteUI(WORKSPACE_CONTROL_NAME)

        # Also clean up any leftover window with the old name
        if cmds.window(WINDOW_NAME, exists=True):
            cmds.deleteUI(WINDOW_NAME)

        # Create the workspace control — starts **floating** (not docked).
        # The user can dock it manually if desired; Maya remembers the
        # position on subsequent launches thanks to retain=True.
        #
        # uiScript is the command Maya calls to rebuild the UI contents
        # whenever the retained workspace control is restored (e.g.
        # after a Maya restart).  Without this, a retained workspace
        # control comes back as an empty shell with no buttons.
        cmds.workspaceControl(
            WORKSPACE_CONTROL_NAME,
            label=WINDOW_TITLE,
            retain=True,
            floating=True,
            initialWidth=780,
            initialHeight=560,
            minimumWidth=620,
            uiScript="import temp_pivot_tool; temp_pivot_tool._rebuild_workspace_ui()",
        )

        # Build the UI inside the workspace control.  _build_ui()
        # clears existing children first, so even if Maya's uiScript
        # already fired we won't get duplicates.
        _build_ui(WORKSPACE_CONTROL_NAME)

        # Raise / show
        cmds.workspaceControl(
            WORKSPACE_CONTROL_NAME, edit=True,
            visible=True,
        )
        return

    # ------------------------------------------------------------------
    # Fallback: plain floating window (Maya < 2017)
    # ------------------------------------------------------------------
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    window = cmds.window(
        WINDOW_NAME,
        title=WINDOW_TITLE,
        sizeable=True,
        minimizeButton=True,
        maximizeButton=False,
        width=780,
        height=560
    )

    _build_ui(window)

    cmds.showWindow(window)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    show()
