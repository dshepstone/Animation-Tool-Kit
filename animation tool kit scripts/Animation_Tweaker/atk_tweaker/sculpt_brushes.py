"""Maya's mesh sculpting brushes, grouped for the Animation Tweaker brush shelf.

The brushes are Maya's own tools, started through their runtime commands, and
the icons are the ones Maya ships in its Qt resources. Nothing here builds UI.
Picking a brush while a tweak sculpt is open selects the sculpt copy first, so
the brush always lands on the copy rather than on the animated mesh.
"""
from maya import cmds, mel

from . import engine

# (id, label, runtime command, Maya resource icon, tip)
SHAPE_BRUSHES = (
    ("sculpt", "Sculpt", "SetMeshSculptTool", "Sculpt.png", "Push the surface out along its normal (Ctrl: in)"),
    ("smooth", "Smooth", "SetMeshSmoothTool", "Smooth.png", "Even out bumps and dents"),
    ("relax", "Relax", "SetMeshRelaxTool", "Relax.png", "Even out the vertex spacing, keeping the shape"),
    ("grab", "Grab", "SetMeshGrabTool", "Grab.png", "Drag an area of the surface around"),
    ("pinch", "Pinch", "SetMeshPinchTool", "Pinch.png", "Pull vertices together into a crease"),
    ("flatten", "Flatten", "SetMeshFlattenTool", "Flatten.png", "Flatten the surface onto a plane"),
    ("bulge", "Bulge", "SetMeshBulgeTool", "Bulge.png", "Swell the surface outwards"),
    ("amplify", "Amplify", "SetMeshAmplifyTool", "Amplify.png", "Exaggerate the existing surface detail"),
    ("smear", "Smear", "SetMeshSmearTool", "Smear.png", "Slide vertices along the surface"),
)
DETAIL_BRUSHES = (
    ("foamy", "Foamy", "SetMeshFoamyTool", "Foamy.png", "Soft, build-up sculpting"),
    ("wax", "Wax", "SetMeshWaxTool", "Wax.png", "Add volume like wax"),
    ("scrape", "Scrape", "SetMeshScrapeTool", "Scrape.png", "Shave down high points"),
    ("fill", "Fill", "SetMeshFillTool", "Fill.png", "Fill in low points"),
    ("knife", "Knife", "SetMeshKnifeTool", "Knife.png", "Cut fine creases"),
    ("spray", "Spray", "SetMeshSprayTool", "Spray.png", "Spray a stamp in random spots"),
    ("repeat", "Repeat", "SetMeshRepeatTool", "Repeat.png", "Repeat a stamp along the stroke"),
    ("imprint", "Imprint", "SetMeshImprintTool", "Imprint.png", "Press a stamp into the surface"),
)
MASK_BRUSHES = (
    ("freeze", "Freeze", "SetMeshFreezeTool", "Freeze.png", "Paint areas that other brushes must not move"),
)
# (id, label, runtime command, icon, tip) for one-shot actions next to the brushes.
MASK_ACTIONS = (
    ("invert_freeze", "Invert", "SculptMeshInvertFreeze", "", "Invert the frozen area"),
    ("unfreeze_all", "Clear", "SculptMeshUnfreezeAll", "", "Unfreeze the whole mesh"),
)
GROUPS = (("Shape", SHAPE_BRUSHES), ("Detail", DETAIL_BRUSHES), ("Mask", MASK_BRUSHES))
ALL_BRUSHES = SHAPE_BRUSHES + DETAIL_BRUSHES + MASK_BRUSHES
LAST_BRUSH_VAR = "atkTweakerLastBrush"
DEFAULT_BRUSH = "grab"


def brush(brush_id):
    for entry in ALL_BRUSHES:
        if entry[0] == brush_id:
            return entry
    raise ValueError("Unknown brush %r" % brush_id)


def _target_sculpt(mesh=None):
    """The open sculpt copy for ``mesh`` (or the only open one), else None."""
    if mesh:
        try:
            sculpt, _record = engine.session_for(mesh)
        except Exception:
            sculpt = None
        if sculpt:
            return sculpt
    sessions = engine.active_sessions()
    return next(iter(sessions)) if len(sessions) == 1 else None


def activate(brush_id, mesh=None):
    """Start a Maya sculpt brush. Returns the sculpt copy it will paint on (or None)."""
    _id, _label, command, _icon, _tip = brush(brush_id)
    sculpt = _target_sculpt(mesh)
    if sculpt:
        cmds.select(sculpt, replace=True)
    mel.eval(command)
    cmds.optionVar(stringValue=(LAST_BRUSH_VAR, brush_id))
    return sculpt


def run_action(action_id):
    for entry in MASK_ACTIONS:
        if entry[0] == action_id:
            mel.eval(entry[2])
            return
    raise ValueError("Unknown sculpt action %r" % action_id)


def last_brush():
    if cmds.optionVar(exists=LAST_BRUSH_VAR):
        value = cmds.optionVar(query=LAST_BRUSH_VAR)
        if any(entry[0] == value for entry in ALL_BRUSHES):
            return value
    return DEFAULT_BRUSH


SCULPT_CONTEXT = "sculptMeshCacheContext"
# Maya's Tool Settings sliders run 0-100; their fields accept up to 100000.
SLIDER_MAX = 100.0
FIELD_MAX = 100000.0
_SETTING_SLIDERS = {"size": "sculptMeshFalloffSize_FSG", "strength": "sculptMeshFalloffStrength_FSG"}


def brush_ready():
    """True once Maya's sculpt context exists (a sculpt brush was used this session)."""
    try:
        return bool(cmds.sculptMeshCacheCtx(SCULPT_CONTEXT, exists=True))
    except Exception:
        return False


def brush_values():
    """(size, strength) of the current sculpt brush, or None before any brush was picked."""
    if not brush_ready():
        return None
    return (cmds.sculptMeshCacheCtx(SCULPT_CONTEXT, query=True, size=True),
            cmds.sculptMeshCacheCtx(SCULPT_CONTEXT, query=True, strength=True))


def _set_value(flag, value):
    if not brush_ready():
        raise ValueError("Pick a sculpt brush first")
    value = max(0.0, min(FIELD_MAX, float(value)))
    cmds.sculptMeshCacheCtx(SCULPT_CONTEXT, edit=True, **{flag: value})
    # Keep Maya's Tool Settings window in step when it is open.
    slider = _SETTING_SLIDERS[flag]
    if cmds.floatSliderGrp(slider, exists=True):
        cmds.floatSliderGrp(slider, edit=True, value=value)
    return value


def set_brush_size(value):
    """Brush radius for the current brush (Maya keeps one per brush unless the size is pinned)."""
    return _set_value("size", value)


def set_brush_strength(value):
    """How strongly the current brush moves the surface."""
    return _set_value("strength", value)


def show_settings():
    """Open the Tool Settings for the current sculpt brush."""
    mel.eval("ShowMeshSculptToolOptions")


def exit_brush():
    """Back to the Select tool."""
    cmds.setToolTo("selectSuperContext")


def symmetry_enabled():
    return bool(cmds.symmetricModelling(query=True, symmetry=True))


def set_symmetry(enabled, axis="x"):
    """Object-space symmetry for the sculpt brushes."""
    if enabled:
        cmds.symmetricModelling(symmetry=True, about="object", axis=axis)
    else:
        cmds.symmetricModelling(symmetry=False)
