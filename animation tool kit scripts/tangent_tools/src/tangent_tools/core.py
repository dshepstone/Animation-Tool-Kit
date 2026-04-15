"""Tangent Tools — core Maya operations.

This module is a thin wrapper over ``maya.cmds`` that centralizes every
tangent/curve operation the UI needs to drive.

The implementations deliberately mirror how Maya's own Graph Editor
menus invoke the underlying commands (for example, ``keyTangent`` and
``setInfinity`` are called *without* naming any target, so Maya's normal
selection-context resolution handles the "selected keys in the Graph
Editor vs. selected object in the viewport" case for us).  Matching the
native menus keeps behaviour predictable across Maya versions.
"""
from __future__ import absolute_import, division, print_function

import maya.cmds as cmds
import maya.mel as mel


# ---------------------------------------------------------------------------
# Tangent type names
# ---------------------------------------------------------------------------

#: Maps the label shown in the UI to the ``keyTangent`` tangent type string.
#:
#: ``"spline"`` is the historic Maya "Auto Spline (Legacy)" tangent — that
#: is exactly what Maya's own menu item applies.
TANGENT_TYPES = {
    "auto_legacy": "spline",
    "linear":      "linear",
    "stepped":     "step",
}


# ---------------------------------------------------------------------------
# Graph Editor constants
# ---------------------------------------------------------------------------

GRAPH_EDITOR      = "graphEditor1GraphEd"
GRAPH_OUTLINER    = "graphEditor1OutlineEd"
GRAPH_FROM_OUTLR  = "graphEditor1FromOutliner"


def _graph_editor_exists():
    try:
        return bool(cmds.animCurveEditor(GRAPH_EDITOR, exists=True))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------

def _selected_anim_curves():
    """Return anim curves currently selected in the Graph Editor."""
    try:
        curves = cmds.keyframe(query=True, selected=True, name=True) or []
    except Exception:
        curves = []
    # Deduplicate while preserving order.
    seen = set()
    out = []
    for c in curves:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _selected_objects():
    """Return the current object/component selection."""
    return cmds.ls(selection=True, long=False) or []


def _graph_editor_selected_plugs():
    """Return plugs currently selected in the Graph Editor outliner.

    Maya exposes the Graph Editor's outliner selection through its
    ``selectionConnection`` — ``graphEditor1FromOutliner`` holds the
    plugs that are lit up in the outliner, e.g. ``pCube1.rotateY``.

    We filter the result to entries that actually look like plugs
    (contain a ``.``) so a plain object selection falls through to the
    object-level code paths.
    """
    try:
        items = cmds.selectionConnection(
            GRAPH_FROM_OUTLR, query=True, object=True
        ) or []
    except Exception:
        items = []
    return [p for p in items if isinstance(p, str) and "." in p]


# ---------------------------------------------------------------------------
# Tangent type operations
# ---------------------------------------------------------------------------

def set_tangent_type(kind):
    """Apply a tangent type to whatever Maya currently considers selected.

    We intentionally do NOT pass target objects to ``keyTangent``.  Maya's
    built-in menu items work the same way — the command resolves its own
    target from the active selection, which correctly handles selected
    keys in the Graph Editor, selected anim curves, and plain object
    selections in the viewport.
    """
    if kind not in TANGENT_TYPES:
        raise ValueError("Unknown tangent type: {0}".format(kind))

    tangent = TANGENT_TYPES[kind]

    try:
        if tangent == "step":
            # Step is only valid on the out-tangent side; Maya's own menu
            # leaves the in-tangent alone for stepped keys.
            cmds.keyTangent(edit=True, outTangentType="step")
        else:
            cmds.keyTangent(
                edit=True,
                inTangentType=tangent,
                outTangentType=tangent,
            )
    except Exception as exc:
        cmds.warning(
            "Tangent Tools: keyTangent failed ({0}). "
            "Select an object, a curve, or keys in the Graph Editor."
            .format(exc)
        )


def set_weighted(weighted):
    """Toggle weighted tangents on the targeted curves.

    Maya only allows switching weighted tangents on a *per-curve* basis.
    When the user only has keys selected we resolve their owning curves;
    otherwise we fall back to the selected objects and let ``keyTangent``
    walk their anim curves for us.
    """
    curves = _selected_anim_curves()
    if curves:
        targets = curves
    else:
        targets = _selected_objects()

    if not targets:
        cmds.warning("Tangent Tools: nothing selected.")
        return

    errors = 0
    for t in targets:
        try:
            cmds.keyTangent(t, edit=True, weightedTangents=bool(weighted))
        except Exception:
            errors += 1
    if errors:
        cmds.warning(
            "Tangent Tools: could not change weighted state on {0} "
            "target(s). Some curves may already be in the requested mode."
            .format(errors)
        )


# ---------------------------------------------------------------------------
# Pre / Post Infinity
# ---------------------------------------------------------------------------

#: Infinity modes accepted by ``cmds.setInfinity``.
INFINITY_MODES = (
    "constant",
    "linear",
    "cycle",
    "cycleRelative",
    "oscillate",
)


def set_infinity(mode, pre=True, post=True):
    """Set pre and/or post infinity on the current selection.

    Matches the Graph Editor menu items, which issue commands like
    ``setInfinity -poi cycle;`` without naming any object.  We also use
    the short flag names (``pri`` / ``poi``) because Maya's Python
    binding for ``setInfinity`` does not always accept the long forms.
    """
    if mode not in INFINITY_MODES:
        raise ValueError("Unknown infinity mode: {0}".format(mode))

    if not (pre or post):
        return

    kwargs = {}
    if pre:
        kwargs["pri"] = mode
    if post:
        kwargs["poi"] = mode

    try:
        cmds.setInfinity(**kwargs)
    except Exception as exc:
        cmds.warning(
            "Tangent Tools: setInfinity failed ({0}). "
            "Make sure a curve or object with animation is selected."
            .format(exc)
        )


# ---------------------------------------------------------------------------
# Graph Editor — Show / Isolate toggles
# ---------------------------------------------------------------------------

def toggle_show_selected_curves_only(enabled):
    """Toggle the Graph Editor's *Show > Selected Type(s)* filter.

    Mirrors Maya's built-in Show menu, which calls the ``filterUI``
    procs:

    * ``filterUIFilterSelection`` — build an item filter from the
      currently-selected channels and apply it to the outliner.
    * ``filterUIClearFilter`` — drop the filter again.

    These procs ship with every modern Maya, unlike the older
    ``showSelectedAnimCurves`` / ``showAllAnimCurves`` helpers which are
    not present in some Maya 2022+ installations.
    """
    if not _graph_editor_exists():
        cmds.warning("Tangent Tools: Graph Editor is not open.")
        return

    if enabled:
        # The second arg of filterUIFilterSelection is the menu it
        # should refresh after building the filter; passing an empty
        # string skips the refresh and is harmless.
        try:
            mel.eval(
                'filterUIFilterSelection "{0}" "";'.format(GRAPH_OUTLINER)
            )
            return
        except Exception as exc:
            primary_exc = exc
        # Fall back to the older showSelectedAnimCurves proc if the
        # filterUI variant isn't available on this Maya.
        try:
            mel.eval(
                'showSelectedAnimCurves "{0}";'.format(GRAPH_OUTLINER)
            )
            return
        except Exception:
            pass
        cmds.warning(
            "Tangent Tools: could not enable Show Selected Type(s) "
            "({0})".format(primary_exc)
        )
    else:
        try:
            mel.eval(
                'filterUIClearFilter "{0}";'.format(GRAPH_OUTLINER)
            )
        except Exception as exc:
            cmds.warning(
                "Tangent Tools: could not clear filter ({0})".format(exc)
            )


def show_all_curves():
    """Clear any Graph Editor outliner filter and show every channel."""
    if not _graph_editor_exists():
        cmds.warning("Tangent Tools: Graph Editor is not open.")
        return

    try:
        mel.eval('filterUIClearFilter "{0}";'.format(GRAPH_OUTLINER))
    except Exception as exc:
        cmds.warning(
            "Tangent Tools: could not clear filter ({0})".format(exc)
        )


def toggle_isolate_curves(enabled):
    """Toggle the Graph Editor's *Curves > Isolate Curve Display*.

    The menu item is implemented through the ``isolateAnimCurve`` MEL
    proc which takes a boolean plus the outliner/graph editor names.
    We try a few argument orderings because Maya has shipped slightly
    different signatures across versions, and finally fall back to a
    direct ``animCurveEditor -displayInfinities`` toggle as a last
    resort.
    """
    if not _graph_editor_exists():
        cmds.warning("Tangent Tools: Graph Editor is not open.")
        return

    state = "true" if enabled else "false"
    attempts = (
        'isolateAnimCurve {state} "{outliner}" "{editor}";',
        'isolateAnimCurve {state} "{from_outliner}" "{editor}";',
        'isolateAnimCurve("{from_outliner}", "{editor}", {state});',
    )
    last_exc = None
    for tmpl in attempts:
        try:
            mel.eval(tmpl.format(
                state=state,
                outliner=GRAPH_OUTLINER,
                from_outliner=GRAPH_FROM_OUTLR,
                editor=GRAPH_EDITOR,
            ))
            return
        except Exception as exc:
            last_exc = exc
            continue
    cmds.warning(
        "Tangent Tools: could not toggle Isolate Curve Display "
        "({0}). Select one or more curves in the Graph Editor first."
        .format(last_exc)
    )


# ---------------------------------------------------------------------------
# Buffer curves
# ---------------------------------------------------------------------------

def toggle_show_buffer_curves(enabled):
    """Pure on/off toggle for buffer curve display.

    Mirrors the Graph Editor's *View > Show Buffer Curves* menu item.
    No snapshot is taken here — use :func:`create_buffer_curves` for
    that — this function only controls whether existing buffer curves
    are drawn.

    We update both ``animCurveEditor -showBufferCurves`` and the
    ``graphEditorShowBufferCurves`` option var that Maya consults on
    refresh, otherwise the state flips back as soon as the Graph
    Editor redraws.
    """
    if not _graph_editor_exists():
        cmds.warning("Tangent Tools: Graph Editor is not open.")
        return

    # First, mirror Maya's own Script Editor output for
    # View > Show Buffer Curves as closely as possible.
    desired = bool(enabled)
    mel_state = "true" if desired else "false"
    primary_exc = None
    applied = False
    try:
        mel.eval(
            "animCurveEditor -edit -showBufferCurves {0} {1}; "
            "optionVar -iv graphEditorShowBufferCurves {0};".format(
                mel_state, GRAPH_EDITOR
            )
        )
        applied = True
    except Exception as exc:
        primary_exc = exc

    if not applied:
        try:
            cmds.animCurveEditor(
                GRAPH_EDITOR, edit=True, showBufferCurves=desired
            )
            cmds.optionVar(
                intValue=("graphEditorShowBufferCurves", 1 if desired else 0)
            )
            applied = True
        except Exception as exc:
            primary_exc = exc

    if not applied:
        mel_attempts = (
            # Some Maya builds route through this proc.
            "performShowBufferCurves {0} {1};".format(
                1 if desired else 0, GRAPH_EDITOR
            ),
            # Keep a final legacy fallback.
            "doBufferGraphEditor {0} {1} {2};".format(
                1 if desired else 0, GRAPH_EDITOR, GRAPH_OUTLINER
            ),
        )
        for cmd in mel_attempts:
            try:
                mel.eval(cmd)
                mel.eval(
                    "optionVar -iv graphEditorShowBufferCurves {0};".format(
                        mel_state
                    )
                )
                applied = True
                break
            except Exception as exc:
                primary_exc = exc

    if not applied:
        cmds.warning(
            "Tangent Tools: could not toggle buffer curve display "
            "({0})".format(primary_exc)
        )


def show_buffer_curves():
    """Show buffer curves in the Graph Editor."""
    toggle_show_buffer_curves(True)


def hide_buffer_curves():
    """Hide buffer curves in the Graph Editor."""
    toggle_show_buffer_curves(False)


def create_buffer_curves():
    """Snapshot the current selection as buffer curves.

    Runs the documented command::

        bufferCurve -animation keys -overwrite true
    """
    try:
        cmds.bufferCurve(animation="keys", overwrite=True)
        print("// Tangent Tools: buffer curve snapshot created")
    except Exception as exc:
        cmds.warning(
            "Tangent Tools: bufferCurve snapshot failed ({0}). "
            "Select an object or keys in the Graph Editor first."
            .format(exc)
        )


def use_referenced_buffer_curve():
    """Set the buffer curve to the referenced anim curve.

    Runs ``bufferCurve -useReferencedCurve``, which makes the buffer
    curve equal to the animation curve stored in the reference file.
    Useful when comparing against the original referenced animation
    after local edits.
    """
    try:
        cmds.bufferCurve(useReferencedCurve=True)
        print("// Tangent Tools: buffer curve set to referenced anim curve")
    except Exception as exc:
        cmds.warning(
            "Tangent Tools: bufferCurve -useReferencedCurve failed "
            "({0}). Make sure a referenced anim curve is selected."
            .format(exc)
        )


def swap_buffer_curves():
    """Swap the live curve with its buffer snapshot.

    Runs ``bufferCurve -animation keys -swap``, which exchanges the
    current animation with the buffer curve — a fast way to A/B
    between the original and an edit.
    """
    try:
        cmds.bufferCurve(animation="keys", swap=True)
        print("// Tangent Tools: buffer curve swapped")
    except Exception as exc:
        cmds.warning(
            "Tangent Tools: bufferCurve swap failed ({0}). "
            "Select an object or keys in the Graph Editor first."
            .format(exc)
        )


# ---------------------------------------------------------------------------
# Mute / Unmute
# ---------------------------------------------------------------------------

def _muted_plugs_for(obj):
    """Return plugs on *obj* that currently have a mute node connected."""
    plugs = []
    mute_nodes = cmds.listConnections(obj, type="mute") or []
    for node in mute_nodes:
        driven = cmds.listConnections(
            node + ".output", plugs=True, source=False, destination=True
        ) or []
        plugs.extend(driven)
    return plugs


def _keyable_plugs_for(obj):
    """Return leaf keyable unlocked plugs on *obj*."""
    attrs = cmds.listAttr(obj, keyable=True, unlocked=True) or []
    plugs = []
    for a in attrs:
        plug = "{0}.{1}".format(obj, a)
        if cmds.objExists(plug):
            plugs.append(plug)
    return plugs


def _mute_targets(prefer_muted=False):
    """Resolve plugs to target for mute/unmute operations.

    When ``prefer_muted`` is ``True`` (unmute path) we only include plugs
    that actually have a mute node attached, so we never send spurious
    ``-disable -force`` calls to unrelated channels.
    """
    # 1. Graph Editor curve selection always wins.
    curves = _selected_anim_curves()
    if curves:
        plugs = []
        for c in curves:
            conns = cmds.listConnections(
                c + ".output", plugs=True, source=False, destination=True
            ) or []
            plugs.extend(conns)
        if plugs:
            return plugs

    objects = _selected_objects()
    if not objects:
        return []

    # 2. Channel Box attribute selection (if any) wins over everything else.
    try:
        selected_attrs = cmds.channelBox(
            "mainChannelBox",
            query=True,
            selectedMainAttributes=True,
        ) or []
    except Exception:
        selected_attrs = []

    plugs = []
    if selected_attrs:
        for obj in objects:
            for attr in selected_attrs:
                plug = "{0}.{1}".format(obj, attr)
                if cmds.objExists(plug):
                    plugs.append(plug)
        if plugs:
            if prefer_muted:
                return [p for p in plugs if _is_muted(p)]
            return plugs

    # 3. Fall back to the full set of keyable unlocked channels.
    for obj in objects:
        if prefer_muted:
            plugs.extend(_muted_plugs_for(obj))
        else:
            plugs.extend(_keyable_plugs_for(obj))
    return plugs


def _is_muted(plug):
    """Return ``True`` when *plug* has a mute node connected."""
    try:
        return bool(cmds.listConnections(plug, type="mute"))
    except Exception:
        return False


def mute_channels():
    """Mute channels based on the active selection.

    Priority order:

    1. If the user has individual channels highlighted in the Graph
       Editor outliner, only those plugs are muted.
    2. Otherwise we fall back to the broader resolution handled by
       ``_mute_targets`` (channel box selection, full object).
    """
    # 1. Graph Editor outliner plug selection wins.
    plugs = _graph_editor_selected_plugs()
    if plugs:
        muted = 0
        for plug in plugs:
            try:
                cmds.mute(plug)
                muted += 1
            except Exception:
                pass
        if not muted:
            cmds.warning("Tangent Tools: no channels were muted.")
        return

    # 2. Fallback — existing object / channel box path.
    plugs = _mute_targets(prefer_muted=False)
    if not plugs:
        cmds.warning("Tangent Tools: nothing to mute.")
        return

    muted = 0
    for plug in plugs:
        try:
            cmds.mute(plug)
            muted += 1
        except Exception:
            pass
    if not muted:
        cmds.warning("Tangent Tools: no channels were muted.")


def unmute_channels():
    """Unmute channels based on the active selection.

    Priority order mirrors :func:`mute_channels`:

    1. Plugs selected in the Graph Editor outliner are unmuted
       individually — calling ``cmds.mute(plug, disable=True)`` on a
       per-plug basis so only the channels the user highlighted are
       affected.
    2. Otherwise the whole-object form from the Maya docs example is
       used: ``cmds.mute(obj, disable=True)`` drops every mute node on
       every muted attribute of each object in the selection.
    """
    # 1. Graph Editor outliner plug selection wins.
    plugs = _graph_editor_selected_plugs()
    if plugs:
        unmuted = 0
        for plug in plugs:
            try:
                cmds.mute(plug, disable=True)
                unmuted += 1
            except Exception:
                pass
        if unmuted == 0:
            cmds.warning(
                "Tangent Tools: no muted channels found on the "
                "selection."
            )
        return

    # 2. Resolve owning objects from the regular selection + any
    #    curves selected in the Graph Editor.
    objects = set()
    for obj in _selected_objects():
        objects.add(obj)
    for curve in _selected_anim_curves():
        try:
            driven = cmds.listConnections(
                curve + ".output",
                plugs=True,
                source=False,
                destination=True,
            ) or []
        except Exception:
            driven = []
        for plug in driven:
            objects.add(plug.split(".")[0])

    if not objects:
        cmds.warning("Tangent Tools: nothing selected.")
        return

    unmuted = 0
    for obj in objects:
        try:
            cmds.mute(obj, disable=True)
            unmuted += 1
        except Exception:
            pass

    if unmuted == 0:
        cmds.warning(
            "Tangent Tools: no muted channels found on the selection."
        )
    else:
        print(
            "// Tangent Tools: unmuted channels on {0} object(s)"
            .format(unmuted)
        )
