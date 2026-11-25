# -*- coding: utf-8 -*-
"""
wire_shape_tool.py

Maya Wire Shape Tool
- Loads Comet's wireShape.mel (embedded) and exposes buttons to create its shapes.
- Adds a library of rig-ready controller shapes (COG, pole vector, IK foot,
  lollipop pins, gear switches, aim targets, ...) in pure Python, organised
  into categories.
- Joint Mode: builds controls on selected joints (one joint, or a whole chain
  as an FK parent-constraint chain or nested hierarchy) aligned to each
  joint's pivot and rotation axes, with a naming pattern such as
  FlagPole_#_CTRL, a Best Option shape per joint and per-joint shapes.
- Batch Rename tab: pattern rename (whole joint chains), search/replace and
  prefix/suffix.
- Includes an Offset Dummy builder: a null/gizmo control wrapped in any number
  of offset groups, plus a helper that wraps existing objects in matched
  offset groups.

Usage (Script Editor - Python):
    import wire_shape_tool
    wire_shape_tool.show()
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

import maya.cmds as cmds
import maya.mel as mel

# -----------------------------
# Embedded MEL (wireShape.mel)
# snaps.mel dependency removed - snapping is handled by Python
# -----------------------------
_MEL_SOURCE = r"""//----------------------------------------------------------------------------
// wireShape.mel - MEL Script (embedded, snap dependency removed)
//----------------------------------------------------------------------------

global proc wireShape(string $what)
{
    string $s[]=`ls -sl`;
    string $c;
    string $new[] ;

    int $selcount = size($s);
    int $i;

    if ($selcount == 0)
        $selcount = 1;

    for ($i=0; $i < $selcount; ++$i)
    {
        switch ($what)
        {
        case "arrow":
            $c = `curve -d 1 -p 0 0.6724194 0.4034517 -p 0 0 0.4034517 -p 0 0 0.6724194 -p 0 -0.4034517 0 -p 0 0 -0.6724194 -p 0 0 -0.4034517 -p 0 0.6724194 -0.4034517 -p 0 0.6724194 0.4034517 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -n "arrow#"` ;
            break ;

        case "cross":
            $c = `curve -d 1 -p 1 0 -1 -p 2 0 -1 -p 2 0 1 -p 1 0 1 -p 1 0 2 -p -1 0 2 -p -1 0 1 -p -2 0 1 -p -2 0 -1 -p -1 0 -1 -p -1 0 -2 -p 1 0 -2 -p 1 0 -1 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 -n "cross#"`;
            break ;

        case "square":
            $c = `curve -d 1 -p -1 0 1 -p 1 0 1 -p 1 0 -1 -p -1 0 -1 -p -1 0 1 -k 0 -k 1 -k 2 -k 3 -k 4 -n "square#"`;
            break ;

        case "cube":
            $c = `curve -d 1 -p -0.5 0.5 0.5 -p 0.5 0.5 0.5 -p 0.5 0.5 -0.5 -p -0.5 0.5 -0.5 -p -0.5 0.5 0.5 -p -0.5 -0.5 0.5 -p -0.5 -0.5 -0.5 -p 0.5 -0.5 -0.5 -p 0.5 -0.5 0.5 -p -0.5 -0.5 0.5 -p 0.5 -0.5 0.5 -p 0.5 0.5 0.5 -p 0.5 0.5 -0.5 -p 0.5 -0.5 -0.5 -p -0.5 -0.5 -0.5 -p -0.5 0.5 -0.5 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 -k 13 -k 14 -k 15 -n "cube#"`;
            break ;

        case "orient":
            $c = `curve -d 3 -p 0.0959835 0.604001 -0.0987656 -p 0.500783 0.500458 -0.0987656 -p 0.751175 0.327886 -0.0987656 -p 0.751175 0.327886 -0.0987656 -p 0.751175 0.327886 -0.336638 -p 0.751175 0.327886 -0.336638 -p 1.001567 0 0 -p 1.001567 0 0 -p 0.751175 0.327886 0.336638 -p 0.751175 0.327886 0.336638 -p 0.751175 0.327886 0.0987656 -p 0.751175 0.327886 0.0987656 -p 0.500783 0.500458 0.0987656 -p 0.0959835 0.604001 0.0987656 -p 0.0959835 0.604001 0.0987656 -p 0.0959835 0.500458 0.500783 -p 0.0959835 0.327886 0.751175 -p 0.0959835 0.327886 0.751175 -p 0.336638 0.327886 0.751175 -p 0.336638 0.327886 0.751175 -p 0 0 1.001567 -p 0 0 1.001567 -p -0.336638 0.327886 0.751175 -p -0.336638 0.327886 0.751175 -p -0.0959835 0.327886 0.751175 -p -0.0959835 0.327886 0.751175 -p -0.0959835 0.500458 0.500783 -p -0.0959835 0.604001 0.0987656 -p -0.0959835 0.604001 0.0987656 -p -0.500783 0.500458 0.0987656 -p -0.751175 0.327886 0.0987656 -p -0.751175 0.327886 0.0987656 -p -0.751175 0.327886 0.336638 -p -0.751175 0.327886 0.336638 -p -1.001567 0 0 -p -1.001567 0 0 -p -0.751175 0.327886 -0.336638 -p -0.751175 0.327886 -0.336638 -p -0.751175 0.327886 -0.0987656 -p -0.751175 0.327886 -0.0987656 -p -0.500783 0.500458 -0.0987656 -p -0.0959835 0.604001 -0.0987656 -p -0.0959835 0.604001 -0.0987656 -p -0.0959835 0.500458 -0.500783 -p -0.0959835 0.327886 -0.751175 -p -0.0959835 0.327886 -0.751175 -p -0.336638 0.327886 -0.751175 -p -0.336638 0.327886 -0.751175 -p 0 0 -1.001567 -p 0 0 -1.001567 -p 0.336638 0.327886 -0.751175 -p 0.336638 0.327886 -0.751175 -p 0.0959835 0.327886 -0.751175 -p 0.0959835 0.327886 -0.751175 -p 0.0959835 0.500458 -0.500783 -p 0.0959835 0.604001 -0.0987656 -k 0 -k 0 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 -k 13 -k 14 -k 15 -k 16 -k 17 -k 18 -k 19 -k 20 -k 21 -k 22 -k 23 -k 24 -k 25 -k 26 -k 27 -k 28 -k 29 -k 30 -k 31 -k 32 -k 33 -k 34 -k 35 -k 36 -k 37 -k 38 -k 39 -k 40 -k 41 -k 42 -k 43 -k 44 -k 45 -k 46 -k 47 -k 48 -k 49 -k 50 -k 51 -k 52 -k 53 -k 53 -k 53 -n "orient#"` ;
            break ;

        case "circleY":
            {
            string $tc[] = `circle -c 0 0 0 -nr 0 1 0 -sw 360 -r 1 -d 3 -ut 0 -tol 0.01 -s 8 -ch 1`;
            $c=$tc[0];
            }
            break ;

        case "circleZ":
            {
            string $tc[] = `circle -c 0 0 0 -nr 0 0 1 -sw 360 -r 1 -d 3 -ut 0 -tol 0.01 -s 8 -ch 1` ;
            $c=$tc[0];
            }
            break ;

        case "circleX":
            {
            string $tc[] = `circle -c 0 0 0 -nr 1 0 0 -sw 360 -r 1 -d 3 -ut 0 -tol 0.01 -s 8 -ch 1`;
            $c=$tc[0];
            }
            break ;

        case "null":
        case "group":
        case "grp":
            $c = `group -em -n "grp#"`;
            break ;

        case "locator":
        case "loc":
            {
            string $tc[] = `spaceLocator -n "loc#"`;
            $c=$tc[0];
            }
            break ;

        case "bulb":
            $c = `curve -d 3 -p -0.139471 -0.798108 0 -p -0.139471 -0.798108 0 -p -0.139471 -0.798108 0 -p -0.299681 -0.672294 0 -p -0.299681 -0.672294 0 -p -0.299681 -0.672294 0 -p -0.121956 -0.578864 0 -p -0.121956 -0.578864 0 -p -0.121956 -0.578864 0 -p -0.285304 -0.51952 0 -p -0.285304 -0.51952 0 -p -0.0744873 -0.442806 0 -p -0.0744873 -0.442806 0 -p -0.287769 -0.373086 0 -p -0.287769 -0.373086 0 -p -0.100386 -0.296549 0 -p -0.100386 -0.296549 0 -p -0.264344 -0.205725 0 -p -0.264344 -0.205725 0 -p -0.262544 -0.0993145 0 -p -0.262544 -0.0993145 0 -p -0.167051 -0.0613459 0 -p -0.167051 -0.0613459 0 -p -0.167051 -0.0613459 0 -p -0.166024 0.0163458 0 -p -0.157394 0.232092 0 -p -0.367902 0.680843 0 -p -0.96336 1.224522 0 -p -1.006509 1.992577 0 -p -0.316123 2.613925 0 -p 0.561786 2.548479 0 -p 1.094888 2.001207 0 -p 1.051638 1.166965 0 -p 0.436419 0.66543 0 -p 0.13283 0.232092 0 -p 0.15009 0.0163458 0 -p 0.15073 -0.046628 0 -p 0.15073 -0.046628 0 -p 0.270326 -0.0955798 0 -p 0.270326 -0.0955798 0 -p 0.267815 -0.208156 0 -p 0.267815 -0.208156 0 -p 0.0884224 -0.291145 0 -p 0.0884224 -0.291145 0 -p 0.292477 -0.366091 0 -p 0.292477 -0.366091 0 -p 0.0946189 -0.439723 0 -p 0.0946189 -0.439723 0 -p 0.306664 -0.508968 0 -p 0.306664 -0.508968 0 -p 0.112488 -0.57513 0 -p 0.112488 -0.57513 0 -p 0.323789 -0.674644 0 -p 0.323789 -0.674644 0 -p 0.152097 -0.794645 0 -p 0.152097 -0.794645 0 -p 0.152097 -0.794645 0 -p 0.106716 -0.907397 0 -p 0.0103741 -1.003739 0 -p -0.0919896 -0.907397 0 -p -0.139471 -0.798108 0 -p -0.139471 -0.798108 0 -k 0 -k 0 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 -k 13 -k 14 -k 15 -k 16 -k 17 -k 18 -k 19 -k 20 -k 21 -k 22 -k 23 -k 24 -k 25 -k 26 -k 27 -k 28 -k 29 -k 30 -k 31 -k 32 -k 33 -k 34 -k 35 -k 36 -k 37 -k 38 -k 39 -k 40 -k 41 -k 42 -k 43 -k 44 -k 45 -k 46 -k 47 -k 48 -k 49 -k 50 -k 51 -k 52 -k 53 -k 54 -k 55 -k 56 -k 57 -k 58 -k 59 -k 59 -k 59 -n "bulb#"`;
            break ;

        case "sphere":
            $c = `curve -d 1 -p 0 3 0 -p 0 2 -2 -p 0 0 -3 -p 0 -2 -2 -p 0 -3 0 -p 0 -2 2 -p 0 0 3 -p 0 2 2 -p 0 3 0 -p 2 2 0 -p 3 0 0 -p 2 -2 0 -p 0 -3 0 -p -2 -2 0 -p -3 0 0 -p -2 2 0 -p 0 3 0 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -k 8 -k 9 -k 10 -k 11 -k 12 -k 13 -k 14 -k 15 -k 16 -n "sphere#"`;
            break ;

        case "plus":
            $c = `curve -d 1 -p 0 1 0 -p 0 -1 0 -p 0 0 0 -p -1 0 0 -p 1 0 0 -p 0 0 0 -p 0 0 1 -p 0 0 -1 -k 0 -k 1 -k 2 -k 3 -k 4 -k 5 -k 6 -k 7 -n "plus#"`;
            break ;

        case "joint":
        case "jnt":
            select -cl ;
            $c = `joint`;
            select -cl ;
            break ;

        } // end switch

        $new[size($new)] = $c ;

    } // end for

    select -r $new ;
}
"""
_MEL_PROC_NAME = "wireShape"

# -----------------------------
# Qt compatibility: PySide6 (Maya 2025+) with PySide2 fallback
# -----------------------------
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
    QT_VERSION = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance
    QT_VERSION = 2

# -----------------------------
# MEL loader / creator
# -----------------------------
def _mel_proc_exists(name: str) -> bool:
    try:
        return bool(mel.eval('exists "{0}"'.format(name)))
    except Exception:
        return False


def ensure_mel_loaded() -> None:
    """Load the embedded MEL proc if not already available."""
    if _mel_proc_exists(_MEL_PROC_NAME):
        return
    mel.eval(_MEL_SOURCE)


def _create_from_mel(key: str, rename_to: Optional[str] = None) -> List[str]:
    """Create a curve shape using wireShape.mel and return created transforms."""
    ensure_mel_loaded()
    before = set(cmds.ls(assemblies=True) or [])
    mel.eval('wireShape "{0}";'.format(key))
    sel = cmds.ls(sl=True, long=False) or []
    after = set(cmds.ls(assemblies=True) or [])
    created = [x for x in sel if x not in before] or list(after - before)
    if rename_to:
        # The MEL proc makes one shape per selected object; name them all
        # (Maya numbers the duplicates) instead of only the first.
        for i, node in enumerate(created):
            try:
                created[i] = cmds.rename(node, rename_to)
            except Exception:
                pass
    return created

# -----------------------------
# Python curve shape helpers
# -----------------------------
def _curve(points, degree=1, closed=False, name=None):
    """Create a curve with optional closing."""
    crv = cmds.curve(p=points, d=degree, name=name)
    if closed:
        try:
            cmds.closeCurve(crv, ch=False, preserveShape=True, replaceOriginal=True)
        except Exception:
            pass
    return crv


def _combine(transforms, name):
    """Parent the shape nodes of every transform after the first under the
    first transform, delete the emptied transforms, and rename the result.

    Lets multi-part controls (circle + arrows, ring + ticks, ...) behave as a
    single selectable curve object.
    """
    base = transforms[0]
    for extra in transforms[1:]:
        shapes = cmds.listRelatives(extra, shapes=True, fullPath=True) or []
        if shapes:
            cmds.parent(shapes, base, r=True, s=True)
        cmds.delete(extra)
    return cmds.rename(base, name)


def _arc_points(radius, start_deg, end_deg, step_deg=15.0, y=0.0):
    """Points along a circular arc in the XZ plane."""
    pts = []
    n = max(2, int(round(abs(end_deg - start_deg) / step_deg)) + 1)
    for i in range(n):
        ang = math.radians(start_deg + (end_deg - start_deg) * i / (n - 1))
        pts.append((math.cos(ang) * radius, y, math.sin(ang) * radius))
    return pts


# ── Primitive shapes ─────────────────────────────────────────────────────────

def create_four_way_arrow(name: str = "fourWayArrow_CTRL") -> str:
    """A simple 4-way arrow control (XY plane)."""
    s = 1.0
    ah = 0.35  # arrow head size
    w = 0.18   # stem half width

    pts = [
        # +X
        (w, 0, 0), (s-ah, 0, 0), (s-ah, w, 0), (s, 0, 0), (s-ah, -w, 0), (s-ah, 0, 0), (w, 0, 0),
        # +Y
        (0, w, 0), (0, s-ah, 0), (-w, s-ah, 0), (0, s, 0), (w, s-ah, 0), (0, s-ah, 0), (0, w, 0),
        # -X
        (-w, 0, 0), (-(s-ah), 0, 0), (-(s-ah), -w, 0), (-s, 0, 0), (-(s-ah), w, 0), (-(s-ah), 0, 0), (-w, 0, 0),
        # -Y
        (0, -w, 0), (0, -(s-ah), 0), (w, -(s-ah), 0), (0, -s, 0), (-w, -(s-ah), 0), (0, -(s-ah), 0), (0, -w, 0),
    ]
    return _curve(pts, degree=1, closed=False, name=name)


def create_diamond(name: str = "diamond_CTRL") -> str:
    s = 1.0
    pts = [(0, s, 0), (s, 0, 0), (0, -s, 0), (-s, 0, 0), (0, s, 0)]
    return _curve(pts, degree=1, closed=False, name=name)


def create_diamond_3d(name: str = "diamond3D_CTRL") -> str:
    """Octahedron — the classic pole-vector / space-switch diamond.

    Single stroke: an octahedron's vertices all have even degree, so an
    Eulerian circuit walks every edge exactly once.
    """
    t, b = (0, 1, 0), (0, -1, 0)
    a, c = (1, 0, 0), (0, 0, 1)
    e, d = (-1, 0, 0), (0, 0, -1)
    pts = [t, a, c, t, e, c, b, e, d, b, a, d, t]
    return _curve(pts, degree=1, closed=False, name=name)


def create_triangle(name: str = "triangle_CTRL") -> str:
    """Equilateral triangle flat in the XZ plane, pointing +Z."""
    r = 1.0
    pts = []
    for ang in (90, 210, 330, 90):
        rad = math.radians(ang)
        pts.append((math.cos(rad) * r, 0, math.sin(rad) * r))
    return _curve(pts, degree=1, closed=False, name=name)


def create_hexagon(name: str = "hexagon_CTRL") -> str:
    """Hexagon flat in the XZ plane."""
    pts = []
    for i in range(6):
        ang = math.radians(i * 60)
        pts.append((math.cos(ang), 0, math.sin(ang)))
    pts.append(pts[0])  # exact closure (avoids float drift at 360 degrees)
    return _curve(pts, degree=1, closed=False, name=name)


def create_star(name: str = "star_CTRL") -> str:
    outer = 1.0
    inner = 0.45
    pts = []
    for i in range(10):
        ang = math.radians(90 + i * 36)
        r = outer if i % 2 == 0 else inner
        pts.append((math.cos(ang) * r, math.sin(ang) * r, 0))
    pts.append(pts[0])
    return _curve(pts, degree=1, closed=False, name=name)


def create_pyramid(name: str = "pyramid_CTRL") -> str:
    s = 1.0
    base = [(-s, 0, -s), (s, 0, -s), (s, 0, s), (-s, 0, s), (-s, 0, -s)]
    apex = (0, s * 1.4, 0)
    pts = base + [apex, (s, 0, -s), apex, (s, 0, s), apex, (-s, 0, s), apex, (-s, 0, -s)]
    return _curve(pts, degree=1, closed=False, name=name)


def create_capsule(name: str = "capsule_CTRL") -> str:
    r = 0.5
    half = 1.0
    pts = []
    for i in range(0, 181, 15):
        ang = math.radians(i)
        pts.append((half + math.cos(ang) * r, 0, math.sin(ang) * r))
    for i in range(0, 181, 15):
        ang = math.radians(180 + i)
        pts.append((-half + math.cos(ang) * r, 0, math.sin(ang) * r))
    pts.append(pts[0])
    return _curve(pts, degree=1, closed=False, name=name)


def create_half_circle(name: str = "halfCircle_CTRL") -> str:
    """Half circle (arc + baseline) in the XZ plane — clavicle / brow control."""
    pts = _arc_points(1.0, 0, 180)
    pts.append(pts[0])  # baseline back to start
    return _curve(pts, degree=1, closed=False, name=name)


# ── Arrow shapes ─────────────────────────────────────────────────────────────

def create_circle_4arrow(name: str = "circleArrow4_CTRL") -> str:
    """Circle in the XZ plane with 4 outward arrows — typical COG / move control."""
    r      = 1.0    # circle radius
    ar     = 1.55   # arrow tip distance from origin
    ah     = 0.28   # arrowhead depth
    hw     = 0.20   # arrowhead half-width
    sw     = 0.07   # shaft half-width

    parts = [cmds.circle(nr=(0, 1, 0), r=r, s=20, ch=False)[0]]

    for angle in [0, 90, 180, 270]:
        rad  = math.radians(angle)
        dx   = round(math.cos(rad), 8)
        dz   = round(math.sin(rad), 8)
        px   = round(-math.sin(rad), 8)   # perpendicular in XZ
        pz   = round(math.cos(rad), 8)

        tip_x,  tip_z  = ar * dx,       ar * dz
        base_x, base_z = (ar-ah) * dx,  (ar-ah) * dz
        stem_x, stem_z = r * dx,        r * dz   # where shaft meets circle edge

        pts = [
            (tip_x,                        0, tip_z),
            (base_x + hw*px,               0, base_z + hw*pz),
            (base_x + sw*px,               0, base_z + sw*pz),
            (stem_x + sw*px,               0, stem_z + sw*pz),
            (stem_x - sw*px,               0, stem_z - sw*pz),
            (base_x - sw*px,               0, base_z - sw*pz),
            (base_x - hw*px,               0, base_z - hw*pz),
            (tip_x,                        0, tip_z),
        ]
        parts.append(cmds.curve(p=pts, d=1))

    return _combine(parts, name)


def create_double_arrow(name: str = "doubleArrow_CTRL") -> str:
    """A flat double-headed arrow along the X axis, lying in the XZ plane."""
    s  = 1.0   # half total length
    ah = 0.30  # arrowhead depth
    hw = 0.22  # arrowhead half-width
    sw = 0.08  # shaft half-width

    pts = [
        ( s,        0,  0.0),   # +X tip
        ( s-ah,     0,  hw),    # arrowhead shoulder right
        ( s-ah,     0,  sw),    # shaft corner
        (-(s-ah),   0,  sw),    # shaft other end
        (-(s-ah),   0,  hw),    # -X arrowhead shoulder right
        (-s,        0,  0.0),   # -X tip
        (-(s-ah),   0, -hw),    # -X arrowhead shoulder left
        (-(s-ah),   0, -sw),    # shaft corner
        ( s-ah,     0, -sw),    # shaft corner
        ( s-ah,     0, -hw),    # +X arrowhead shoulder left
        ( s,        0,  0.0),   # back to +X tip (close)
    ]
    return _curve(pts, degree=1, closed=False, name=name)


def _curved_arrow_points(r, start_deg, end_deg, ah=0.3, hw=0.16, sw=0.06):
    """Points for a flat curved arrow in the XZ plane.

    The arc sweeps from start to end; the arrowhead sits at the end angle,
    pointing along the direction of travel.
    """
    inner = _arc_points(r - sw, start_deg, end_deg)
    outer = _arc_points(r + sw, end_deg, start_deg)  # reversed for the return trip

    # Arrowhead at end_deg, pointing tangentially
    rad = math.radians(end_deg)
    cx, cz = math.cos(rad) * r, math.sin(rad) * r
    # Tangent direction (direction of increasing angle)
    sign = 1.0 if end_deg >= start_deg else -1.0
    tx, tz = -math.sin(rad) * sign, math.cos(rad) * sign
    # Radial direction (outward)
    rx, rz = math.cos(rad), math.sin(rad)

    head = [
        (cx + rx * sw,  0, cz + rz * sw),
        (cx + rx * hw,  0, cz + rz * hw),
        (cx + tx * ah,  0, cz + tz * ah),
        (cx - rx * hw,  0, cz - rz * hw),
        (cx - rx * sw,  0, cz - rz * sw),
    ]
    return inner + head + outer + [inner[0]]


def create_curved_arrow(name: str = "curvedArrow_CTRL") -> str:
    """A curved arrow (quarter-ish arc) flat in the XZ plane — head/neck rotate."""
    pts = _curved_arrow_points(1.0, 180, 45)
    return _curve(pts, degree=1, closed=False, name=name)


def create_spin_arrows(name: str = "spinArrows_CTRL") -> str:
    """Two opposing curved arrows in the XZ plane — classic spin / twist control."""
    a = cmds.curve(p=_curved_arrow_points(1.0, 150, 30), d=1)
    b = cmds.curve(p=_curved_arrow_points(1.0, 330, 210), d=1)
    return _combine([a, b], name)


# ── Rig control shapes ───────────────────────────────────────────────────────

def create_root_control(name: str = "root_CTRL") -> str:
    """Two concentric circles with four compass ticks — global / root control."""
    r_out, r_in = 1.3, 1.0
    parts = [
        cmds.circle(nr=(0, 1, 0), r=r_out, s=20, ch=False)[0],
        cmds.circle(nr=(0, 1, 0), r=r_in, s=20, ch=False)[0],
    ]
    for angle in (0, 90, 180, 270):
        rad = math.radians(angle)
        dx, dz = math.cos(rad), math.sin(rad)
        parts.append(cmds.curve(
            p=[(dx * r_in, 0, dz * r_in), (dx * r_out, 0, dz * r_out)], d=1))
    return _combine(parts, name)


def create_gear(name: str = "gear_CTRL") -> str:
    """Gear / cog outline in the XZ plane — settings and IK/FK switch control."""
    teeth = 8
    r_out, r_in, r_hole = 1.0, 0.78, 0.4
    step = 360.0 / teeth
    pts = []
    for i in range(teeth):
        a = i * step
        for frac, radius in ((0.05, r_in), (0.20, r_in), (0.30, r_out),
                             (0.70, r_out), (0.80, r_in), (0.95, r_in)):
            rad = math.radians(a + frac * step)
            pts.append((math.cos(rad) * radius, 0, math.sin(rad) * radius))
    pts.append(pts[0])
    gear = cmds.curve(p=pts, d=1)
    hole = cmds.circle(nr=(0, 1, 0), r=r_hole, s=16, ch=False)[0]
    return _combine([gear, hole], name)


def create_lollipop(name: str = "lollipop_CTRL") -> str:
    """Stick with a circle on top (XY plane) — FK pin / attribute holder."""
    stem_top = 1.0
    r = 0.35
    cy = stem_top + r
    pts = [(0, 0, 0), (0, stem_top, 0)]
    for i in range(0, 361, 30):
        ang = math.radians(270 - i)   # start at the bottom of the circle
        pts.append((math.cos(ang) * r, cy + math.sin(ang) * r, 0))
    return _curve(pts, degree=1, closed=False, name=name)


def create_pole_vector(name: str = "poleVector_CTRL") -> str:
    """Small 3D diamond with axis lines through the centre — IK pole vector."""
    s = 0.6
    t, b = (0, s, 0), (0, -s, 0)
    a, c = (s, 0, 0), (0, 0, s)
    e, d = (-s, 0, 0), (0, 0, -s)
    octa = cmds.curve(p=[t, a, c, t, e, c, b, e, d, b, a, d, t], d=1)
    ln = 1.0
    axes = cmds.curve(p=[
        (ln, 0, 0), (-ln, 0, 0), (0, 0, 0),
        (0, ln, 0), (0, -ln, 0), (0, 0, 0),
        (0, 0, ln), (0, 0, -ln),
    ], d=1)
    return _combine([octa, axes], name)


def create_foot(name: str = "foot_CTRL") -> str:
    """Footprint outline flat in the XZ plane, toes pointing +Z — IK foot."""
    pts = [
        (-0.32, 0, -0.90),   # heel back left
        ( 0.32, 0, -0.90),   # heel back right
        ( 0.42, 0, -0.55),
        ( 0.38, 0, -0.05),
        ( 0.48, 0,  0.40),   # ball, outer
        ( 0.42, 0,  0.80),
        ( 0.15, 0,  1.00),   # toes
        (-0.20, 0,  0.98),
        (-0.42, 0,  0.72),
        (-0.44, 0,  0.35),   # ball, inner
        (-0.34, 0, -0.10),
        (-0.40, 0, -0.55),
        (-0.32, 0, -0.90),   # close
    ]
    return _curve(pts, degree=1, closed=False, name=name)


def create_paddle(name: str = "paddle_CTRL") -> str:
    """Stick with a rounded paddle on top (XY plane) — hand / finger control."""
    stem_top = 0.8
    hw = 0.35        # paddle half width
    top = 1.8        # paddle top (before the rounded cap)
    pts = [(0, 0, 0), (0, stem_top, 0),
           (-hw, stem_top, 0), (-hw, top, 0)]
    for i in range(0, 181, 20):   # rounded cap, left to right
        ang = math.radians(180 - i)
        pts.append((math.cos(ang) * hw, top + math.sin(ang) * hw, 0))
    pts += [(hw, top, 0), (hw, stem_top, 0), (0, stem_top, 0)]
    return _curve(pts, degree=1, closed=False, name=name)


def create_eye_target(name: str = "eyeTarget_CTRL") -> str:
    """Circle with crosshair ticks facing +Z — eye / aim target control."""
    r = 1.0
    tick_in, tick_out = 0.65, 1.0
    parts = [cmds.circle(nr=(0, 0, 1), r=r, s=16, ch=False)[0]]
    for angle in (0, 90, 180, 270):
        rad = math.radians(angle)
        dx, dy = math.cos(rad), math.sin(rad)
        parts.append(cmds.curve(
            p=[(dx * tick_in, dy * tick_in, 0), (dx * tick_out, dy * tick_out, 0)], d=1))
    # small centre cross
    c = 0.12
    parts.append(cmds.curve(p=[(-c, 0, 0), (c, 0, 0), (0, 0, 0), (0, -c, 0), (0, c, 0)], d=1))
    return _combine(parts, name)


def create_flag(name: str = "flag_CTRL") -> str:
    """Pole with a triangular flag (XY plane) — marker / switch control."""
    pts = [
        (0, 0, 0), (0, 1.6, 0),          # pole
        (0.85, 1.35, 0), (0, 1.1, 0),    # flag triangle
        (0, 0, 0),                       # back down (retrace pole below flag)
    ]
    return _curve(pts, degree=1, closed=False, name=name)


# ── Offset dummy ─────────────────────────────────────────────────────────────

def create_offset_dummy(name: str = "dummy", offsets: int = 2):
    """Create a null/gizmo control wrapped in a chain of offset groups.

    Builds:   <name>_ZERO  >  <name>_OFS1 ... <name>_OFSn  >  <name>_CTRL

    The control is a locator-style gizmo (3D axis cross + circle) that renders
    clearly in the viewport but is a plain curve — safe to constrain, parent,
    or bake against.  The offset groups let animators zero the control, layer
    counter-animation, or use it as a clean parent space / null.

    Returns [zero_group, ctrl].
    """
    offsets = max(0, int(offsets))

    # Gizmo shape: 3D axis cross + circle in XZ
    ln = 0.6
    axes = cmds.curve(p=[
        (ln, 0, 0), (-ln, 0, 0), (0, 0, 0),
        (0, ln, 0), (0, -ln, 0), (0, 0, 0),
        (0, 0, ln), (0, 0, -ln),
    ], d=1)
    ring = cmds.circle(nr=(0, 1, 0), r=0.4, s=16, ch=False)[0]
    ctrl = _combine([axes, ring], name + "_CTRL")

    # Offset chain, innermost first: ZERO > OFS1 > ... > OFSn > CTRL
    top = ctrl
    for i in range(offsets, 0, -1):
        grp = cmds.group(top, name="{0}_OFS{1}".format(name, i))
        top = grp
    zero = cmds.group(top, name=name + "_ZERO")

    cmds.select(ctrl, replace=True)
    return [zero, ctrl]


def add_offset_groups(count: int = 1):
    """Wrap every selected object in ``count`` matched offset groups.

    Each group is created at the object's exact world transform and inserted
    directly above it, so the object's channel values are preserved and the
    new groups sit zeroed in between.  Returns the list of outermost groups.
    """
    count = max(1, int(count))
    sel = cmds.ls(selection=True, long=True) or []
    if not sel:
        cmds.warning("Wire Shapes: Select one or more objects to add offset groups.")
        return []
    # Track nodes by UUID: inserting a group changes the DAG path of the
    # wrapped object and of everything selected beneath it, so the paths
    # captured above go stale as soon as the first object is wrapped.
    sel_ids = cmds.ls(sel, uuid=True) or []
    outermost_ids = []
    for node_id in sel_ids:
        found = cmds.ls(node_id, long=True) or []
        if not found:
            continue
        node = found[0]
        short = node.split("|")[-1]
        target = node
        first_grp = None
        for i in range(1, count + 1):
            parent = cmds.listRelatives(target, parent=True, fullPath=True)
            grp = cmds.group(empty=True, name="{0}_OFS{1}".format(short, i))
            try:
                cmds.matchTransform(grp, target, position=True, rotation=True)
            except Exception:
                pos = cmds.xform(target, q=True, ws=True, t=True)
                rot = cmds.xform(target, q=True, ws=True, ro=True)
                cmds.xform(grp, ws=True, t=pos)
                cmds.xform(grp, ws=True, ro=rot)
            if parent:
                grp = cmds.parent(grp, parent[0])[0]
            grp = (cmds.ls(grp, long=True) or [grp])[0]
            target = cmds.parent(target, grp)[0]
            target = (cmds.ls(target, long=True) or [target])[0]
            if first_grp is None:
                first_grp = (cmds.ls(grp, uuid=True) or [None])[0]
        if first_grp:
            outermost_ids.append(first_grp)
    wrapped = cmds.ls(sel_ids, long=True) or []
    if wrapped:
        cmds.select(wrapped, replace=True)
    print("Wire Shapes: Added {0} offset group(s) to {1} object(s).".format(count, len(wrapped)))
    return cmds.ls(outermost_ids, long=True) or []


# ── Joint Mode ───────────────────────────────────────────────────────────────
#
# Builds controls that sit on joints with the joint's own rotation axes, so
# rotating a control X/Y/Z turns the joint about the same X/Y/Z.  The shape
# itself is turned (in its CVs, not its channels) so that it faces down the
# chain: a circle rings the bone whichever axis the chain is oriented along.

# The axis each shape "faces" when it is built at the origin (its normal for
# flat shapes, its up/length axis for 3D ones).  Joint Mode maps this axis
# onto the joint's chosen axis.  Shapes not listed face +Y.
SHAPE_FACING = {
    "circleX": (1, 0, 0),
    "circleY": (0, 1, 0),
    "circleZ": (0, 0, 1),
    "arrow": (1, 0, 0),           # MEL arrow lies in the YZ plane
    "diamond": (0, 0, 1),         # XY plane
    "star": (0, 0, 1),
    "fourWayArrow": (0, 0, 1),
    "lollipop": (0, 0, 1),
    "paddle": (0, 0, 1),
    "eyeTarget": (0, 0, 1),
    "flag": (0, 0, 1),
    "bulb": (0, 0, 1),
}

AXIS_VECTORS = {
    "+X": (1, 0, 0), "+Y": (0, 1, 0), "+Z": (0, 0, 1),
    "-X": (-1, 0, 0), "-Y": (0, -1, 0), "-Z": (0, 0, -1),
}

FACING_AUTO = "auto"      # face down the chain (the joint's aim axis)
FACING_KEEP = "keep"      # keep the shape as built, only orient it to the joint

CHAIN_BELOW = "below"     # each selected joint and every joint below it
CHAIN_RANGE = "range"     # from the first selected joint to the second

SIZE_RADIUS = "radius"
SIZE_BONE = "bone"
SIZE_FIXED = "fixed"

CONSTRAINT_NONE = "none"
CONSTRAINT_ORIENT = "orient"
CONSTRAINT_PARENT = "parent"
CONSTRAINT_POINT_ORIENT = "pointOrient"

# How the controls of a Multi-Joint chain are linked to each other.
HIER_NONE = "none"                  # independent controls
HIER_PARENT = "parent"              # nested: each group parented under the control above
HIER_CONSTRAINT = "constraint"      # flat: each group parent-constrained to the control above

BEST_SHAPE = "best"                 # pick the shape per joint (see best_shape_key)


@dataclass
class JointModeOptions:
    multi: bool = False                 # False: Single Joint, True: Multi-Joint chain
    chain: str = CHAIN_BELOW
    skip_end_joints: bool = True        # multi only: no control on joints without child joints
    facing: str = FACING_AUTO           # FACING_AUTO, FACING_KEEP or a key of AXIS_VECTORS
    size_mode: str = SIZE_RADIUS
    size: float = 2.0
    name_pattern: str = "{joint}_CTRL"
    start_number: int = 1
    zero_group: bool = True
    group_suffix: str = "GRP"
    hierarchy: str = HIER_CONSTRAINT    # multi only: HIER_NONE, HIER_PARENT or HIER_CONSTRAINT
    constraint: str = CONSTRAINT_NONE   # how each control drives its joint


def dominant_axis(vec):
    """Return the signed unit axis (x, y, z) closest to ``vec``, or None."""
    comps = [float(c) for c in vec]
    idx = max(range(3), key=lambda i: abs(comps[i]))
    if abs(comps[idx]) < 1e-9:
        return None
    axis = [0, 0, 0]
    axis[idx] = 1 if comps[idx] > 0 else -1
    return tuple(axis)


def axis_align_rotation(src, dst):
    """Euler rotation (degrees, any order) that turns unit axis src onto dst.

    Both must be signed unit axes such as (0, 1, 0) or (-1, 0, 0).  Every
    answer turns about a single axis, so the rotate order does not matter.
    """
    src = tuple(int(round(c)) for c in src)
    dst = tuple(int(round(c)) for c in dst)
    if src == dst:
        return (0.0, 0.0, 0.0)
    if src == tuple(-c for c in dst):
        # Half turn about any axis perpendicular to src.
        perp = (0, 0, 1) if src[2] == 0 else (1, 0, 0)
        return tuple(180.0 * c for c in perp)
    # Perpendicular unit axes: a quarter turn about src x dst.
    cross = (src[1] * dst[2] - src[2] * dst[1],
             src[2] * dst[0] - src[0] * dst[2],
             src[0] * dst[1] - src[1] * dst[0])
    return tuple(90.0 * c for c in cross)


def format_control_name(pattern, number, joint=""):
    """Build a control name from a naming pattern.

    ``#`` is replaced by the number, padded to the length of the run of
    hashes (``#`` -> 1, ``##`` -> 01).  ``{joint}`` is replaced by the
    joint's short name.  Characters Maya does not allow become ``_``.
    """
    pattern = (pattern or "").strip() or "{joint}_CTRL"
    short = joint.split("|")[-1].split(":")[-1]
    name = pattern.replace("{joint}", short)
    name = re.sub(r"#+", lambda m: str(int(number)).zfill(len(m.group(0))), name)
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not name or name[0].isdigit():
        name = "_" + name
    return name


def pattern_needs_number(pattern):
    """True when a pattern would give every control the same name."""
    pattern = (pattern or "").strip() or "{joint}_CTRL"
    return "#" not in pattern and "{joint}" not in pattern


def _matrix_without_scale(m):
    """Return a 4x4 (flat list) world matrix with its axes made unit length."""
    out = list(m)
    for row in range(3):
        v = out[row * 4: row * 4 + 3]
        length = math.sqrt(sum(c * c for c in v)) or 1.0
        for i in range(3):
            out[row * 4 + i] = v[i] / length
    return out


def _world_pos(node):
    return cmds.xform(node, q=True, ws=True, t=True)


def _child_joints(jnt):
    return cmds.listRelatives(jnt, children=True, type="joint", fullPath=True) or []


def _parent_joint(jnt):
    parent = cmds.listRelatives(jnt, parent=True, fullPath=True) or []
    if parent and cmds.nodeType(parent[0]) == "joint":
        return parent[0]
    return None


def _bone_vector(jnt):
    """World-space vector along the bone this joint drives.

    Towards the farthest child joint; for an end joint, the bone coming in
    from its parent.  None for a lone joint.
    """
    pos = _world_pos(jnt)
    best, best_len = None, 0.0
    for child in _child_joints(jnt):
        cpos = _world_pos(child)
        vec = [cpos[i] - pos[i] for i in range(3)]
        length = math.sqrt(sum(c * c for c in vec))
        if length > best_len:
            best, best_len = vec, length
    if best is not None and best_len > 1e-6:
        return best
    parent = _parent_joint(jnt)
    if parent:
        ppos = _world_pos(parent)
        vec = [pos[i] - ppos[i] for i in range(3)]
        if math.sqrt(sum(c * c for c in vec)) > 1e-6:
            return vec
    return None


def joint_aim_axis(jnt):
    """The joint's local axis that points down the chain, e.g. (1, 0, 0).

    Reads the joint's world orientation (rotate + jointOrient) and finds the
    local axis the bone runs along.  Returns (axis, alignment) where
    alignment is 1.0 when the bone lies exactly on that axis and lower when
    the joint is not oriented along its bone.  Falls back to +X, Maya's
    default aim axis, for a joint with no bone.
    """
    vec = _bone_vector(jnt)
    if vec is None:
        return (1, 0, 0), 1.0
    m = _matrix_without_scale(cmds.xform(jnt, q=True, ws=True, m=True))
    local = [sum(vec[i] * m[row * 4 + i] for i in range(3)) for row in range(3)]
    length = math.sqrt(sum(c * c for c in local)) or 1.0
    axis = dominant_axis(local) or (1, 0, 0)
    alignment = max(abs(c) for c in local) / length
    return axis, alignment


def _bone_length(jnt):
    vec = _bone_vector(jnt)
    if vec is None:
        return 1.0
    return math.sqrt(sum(c * c for c in vec)) or 1.0


def _sort_by_depth(joints):
    return sorted(joints, key=lambda j: j.count("|"))


def _descendant_joints(root):
    """root and every joint below it, depth first in outliner order."""
    out = [root]
    for child in _child_joints(root):
        out.extend(_descendant_joints(child))
    return out


def gather_joints(selection, multi, chain=CHAIN_BELOW, skip_end_joints=True):
    """Resolve the joints Joint Mode will build controls on, root first.

    Single Joint: every selected joint.  Multi-Joint, CHAIN_BELOW: each
    selected joint and all joints below it.  Multi-Joint, CHAIN_RANGE: the
    joints from the first selected joint down to the second.
    """
    joints = []
    for node in selection or []:
        found = cmds.ls(node, long=True, type="joint") or []
        for j in found:
            if j not in joints:
                joints.append(j)
    if not joints or not multi:
        return joints

    if chain == CHAIN_RANGE:
        if len(joints) < 2:
            raise ValueError("Start -> End needs two joints selected: "
                             "the start joint, then the end joint.")
        start, end = joints[0], joints[1]
        if not end.startswith(start + "|"):
            start, end = end, start
            if not end.startswith(start + "|"):
                raise ValueError("The two selected joints are not in the same chain.")
        result = []
        node = end
        while node and node != start:
            result.append(node)
            node = _parent_joint(node)
        result.append(start)
        result.reverse()
    else:
        result = []
        for root in _sort_by_depth(joints):
            for j in _descendant_joints(root):
                if j not in result:
                    result.append(j)

    if skip_end_joints:
        trimmed = [j for j in result if _child_joints(j)]
        result = trimmed or result
    return result


def _uuid(node):
    return (cmds.ls(node, uuid=True) or [None])[0]


def _node_path(uuid):
    found = cmds.ls(uuid, long=True) if uuid else None
    return found[0] if found else None


def _match_to_joint(node, jnt):
    """Put node on the joint's pivot with the joint's axes (no scale)."""
    try:
        cmds.setAttr(node + ".rotateOrder", cmds.getAttr(jnt + ".rotateOrder"))
    except Exception:
        pass
    m = _matrix_without_scale(cmds.xform(jnt, q=True, ws=True, m=True))
    cmds.xform(node, ws=True, m=m)
    try:
        cmds.setAttr(node + ".scale", 1, 1, 1, type="double3")
    except Exception:
        pass


def _bake_shape_transform(node, rotation, scale):
    """Turn and scale the shape in its CVs, leaving clean channels."""
    try:
        cmds.delete(node, constructionHistory=True)
    except Exception:
        pass
    cmds.xform(node, ws=False, t=(0, 0, 0), ro=rotation, s=(scale, scale, scale))
    if cmds.listRelatives(node, shapes=True, type="nurbsCurve"):
        cmds.makeIdentity(node, apply=True, t=True, r=True, s=True, n=0)
    else:
        cmds.xform(node, ro=(0, 0, 0), s=(1, 1, 1))
        for shape in cmds.listRelatives(node, shapes=True, type="locator", fullPath=True) or []:
            cmds.setAttr(shape + ".localScale", scale, scale, scale, type="double3")


# ── Best shape per joint ────────────────────────────────────────────────────

# (keywords, shape key).  A joint whose name contains one of the keywords as a
# word gets that shape; first match wins.
_BEST_SHAPE_RULES = (
    (("root", "world", "master", "global", "main"), "rootControl"),
    (("cog", "pelvis", "hips", "center", "centre"), "circleArrow4"),
    (("head",), "cube"),
    (("eye",), "sphere"),
    (("jaw",), "halfCircle"),
    (("clavicle", "clav", "collar", "scapula"), "halfCircle"),
    (("toe", "toes", "ball"), "halfCircle"),
    (("hand", "palm"), "square"),
    (("chest", "torso", "ribcage"), "cube"),
    (("prop", "weapon", "sword", "gun"), "cube"),
)
_BEST_DEFAULT = "circleY"           # FK ring around the bone (faces the chain)
_BEST_END = "diamond3D"             # tip joints with nothing below them


def _name_words(name):
    """Lower-case words of a node name: 'L_UpperArm2' -> ['l', 'upper', 'arm']."""
    short = name.split("|")[-1].split(":")[-1]
    short = re.sub(r"([a-z])([A-Z])", r"\1 \2", short)
    return re.findall(r"[a-z]+", short.lower())


def best_shape_key(jnt, has_children=True):
    """The recommended control shape key for a joint.

    Reads the joint's name (root, COG/pelvis, head, jaw, clavicle, hand,
    toe, ..., and _end / _tip / _nub for tip joints) and falls back to an FK ring for chain joints and a small 3D
    diamond for end joints.
    """
    words = _name_words(jnt)
    if any(w in ("end", "tip", "nub") for w in words):
        return _BEST_END
    for keywords, key in _BEST_SHAPE_RULES:
        for word in words:
            if any(word == k or (len(k) > 3 and word.startswith(k)) for k in keywords):
                return key
    return _BEST_DEFAULT if has_children else _BEST_END


def shape_defs_by_key():
    return {d.key: d for d in get_shape_defs()}


def resolve_joint_shapes(joints, shapes):
    """One ShapeDef per joint.

    ``shapes`` is a ShapeDef (used for every joint), BEST_SHAPE / None (best
    shape per joint), or a list matching ``joints`` whose items are any of
    those or a shape key.
    """
    defs = None

    def lookup(item, jnt):
        nonlocal defs
        if isinstance(item, ShapeDef):
            return item
        if defs is None:
            defs = shape_defs_by_key()
        if item in (None, BEST_SHAPE):
            key = best_shape_key(jnt, bool(_child_joints(jnt)))
            return defs.get(key) or defs[_BEST_DEFAULT]
        if item in defs:
            return defs[item]
        raise ValueError("unknown shape '{0}'".format(item))

    if isinstance(shapes, (list, tuple)):
        if len(shapes) != len(joints):
            raise ValueError("one shape per joint is needed")
        return [lookup(item, j) for item, j in zip(shapes, joints)]
    return [lookup(shapes, j) for j in joints]


def _existing_constraint(jnt, kind):
    """Name of a constraint of ``kind`` already driving the joint, or None."""
    try:
        found = cmds.listRelatives(jnt, children=True, type=kind, fullPath=True) or []
    except Exception:
        found = []
    return found[0] if found else None


def _constrain(driver, driven, kind, label):
    """Constrain driven to driver unless it already has that constraint.

    A second constraint call would add a target to the existing constraint
    and blend the old and new controls, so that case is skipped with a
    warning instead.
    """
    fns = {
        "parentConstraint": cmds.parentConstraint,
        "orientConstraint": cmds.orientConstraint,
        "pointConstraint": cmds.pointConstraint,
    }
    existing = _existing_constraint(driven, kind)
    if existing:
        cmds.warning(
            "Wire Shapes: '{0}' already has {1} '{2}'; not adding another target "
            "(it would blend the controls). Delete the old constraint to rebuild."
            .format(driven.split("|")[-1], label, existing.split("|")[-1]))
        return None
    try:
        return fns[kind](driver, driven, maintainOffset=True)
    except Exception as e:
        cmds.warning("Wire Shapes: Could not {0} '{1}': {2}".format(
            label, driven.split("|")[-1], e))
        return None


def create_joint_controls(shape_def, joints, options=None, sizes=None):
    """Create one control per joint, aligned to each joint.

    ``shape_def`` is a ShapeDef for every joint, BEST_SHAPE for the best
    shape per joint, or a list with one entry per joint (see
    ``resolve_joint_shapes``).  ``sizes`` optionally gives each joint its
    own size, read like ``JointModeOptions.size`` (a multiple of the joint
    radius or bone length, or units, per ``size_mode``).

    Each control is placed on the joint's pivot with the joint's rotation
    axes and rotate order, its shape turned to face the chain (see
    ``JointModeOptions.facing``), named from the naming pattern and, as
    chosen, zeroed under a group, linked to the control above it (nested or
    by parent constraint) and used to constrain its joint.  Returns a list
    of (joint, control, top_node).
    """
    opts = options or JointModeOptions()
    shapes = resolve_joint_shapes(joints, shape_def)
    if sizes is None:
        sizes = [opts.size] * len(joints)
    elif len(sizes) != len(joints):
        raise ValueError("one size per joint is needed")
    pattern = opts.name_pattern
    if len(joints) > 1 and pattern_needs_number(pattern):
        pattern = (pattern or "").strip() + "_#"
    hierarchy = opts.hierarchy if opts.multi else HIER_NONE
    # A constraint chain drives the zero groups; constraining the controls
    # themselves would lock their channels, so it always builds groups.
    zero_group = opts.zero_group or hierarchy == HIER_CONSTRAINT
    suffix = (opts.group_suffix or "GRP").strip("_ ") or "GRP"

    names = [format_control_name(pattern, opts.start_number + i, j)
             for i, j in enumerate(joints)]
    taken = [n for n in names if cmds.objExists(n)]
    if taken:
        cmds.warning(
            "Wire Shapes: {0} already exist{1} ({2}); Maya will number the new "
            "controls. Change the name or delete the old controls for clean names."
            .format(len(taken), "s" if len(taken) == 1 else "",
                    ", ".join(taken[:3]) + (", ..." if len(taken) > 3 else "")))

    results = []
    for i, jnt in enumerate(joints):
        shape = shapes[i]
        src_axis = SHAPE_FACING.get(shape.key, (0, 1, 0))
        aim, alignment = joint_aim_axis(jnt)
        if alignment < 0.9:
            cmds.warning(
                "Wire Shapes: '{0}' is not oriented along its bone; the control "
                "uses its closest axis. Orient the joints for a cleaner result."
                .format(jnt.split("|")[-1]))
        if opts.facing == FACING_KEEP:
            rotation = (0.0, 0.0, 0.0)
        elif opts.facing in AXIS_VECTORS:
            rotation = axis_align_rotation(src_axis, AXIS_VECTORS[opts.facing])
        else:
            rotation = axis_align_rotation(src_axis, aim)

        size = float(sizes[i])
        if opts.size_mode == SIZE_BONE:
            scale = _bone_length(jnt) * size
        elif opts.size_mode == SIZE_RADIUS:
            try:
                radius = float(cmds.getAttr(jnt + ".radius"))
            except Exception:
                radius = 1.0
            scale = (radius or 1.0) * size
        else:
            scale = size
        scale = max(scale, 1e-4)

        cmds.select(clear=True)
        created = shape.creator()
        if not created:
            raise RuntimeError("no object created for '{0}'".format(shape.label))
        ctrl = created[0]
        for extra in created[1:]:
            try:
                cmds.delete(extra)
            except Exception:
                pass

        # Track by UUID: renaming and parenting change names and DAG paths.
        ctrl_id = _uuid(ctrl)
        _bake_shape_transform(_node_path(ctrl_id), rotation, scale)
        cmds.rename(_node_path(ctrl_id), names[i])
        ctrl = _node_path(ctrl_id)
        _rename_shapes(ctrl)

        top_id = ctrl_id
        if zero_group:
            short = ctrl.split("|")[-1]
            grp = cmds.group(empty=True, world=True, name="{0}_{1}".format(short, suffix))
            top_id = _uuid(grp)
            grp = _node_path(top_id)
            _match_to_joint(grp, jnt)
            try:
                cmds.setAttr(ctrl + ".rotateOrder", cmds.getAttr(jnt + ".rotateOrder"))
            except Exception:
                pass
            # Relative parenting keeps the control's zeroed channels, so it
            # lands exactly on the group (and the joint) with nothing to clean.
            cmds.parent(ctrl, grp, relative=True)
        else:
            _match_to_joint(ctrl, jnt)
        results.append((jnt, ctrl_id, top_id))

    ids = [c for _, c, _ in results]
    top_ids = [t for _, _, t in results]
    _path = _node_path

    if hierarchy in (HIER_PARENT, HIER_CONSTRAINT) and len(results) > 1:
        joint_index = {jnt: i for i, (jnt, _, _) in enumerate(results)}
        for i, (jnt, _, _) in enumerate(results):
            parent = _parent_joint(jnt)
            while parent and parent not in joint_index:
                parent = _parent_joint(parent)
            if parent is None:
                continue
            parent_ctrl = _path(ids[joint_index[parent]])
            if hierarchy == HIER_PARENT:
                cmds.parent(_path(top_ids[i]), parent_ctrl)
            else:
                _constrain(parent_ctrl, _path(top_ids[i]), "parentConstraint",
                           "parent-constrain the group of")

    constraint_kinds = {
        CONSTRAINT_ORIENT: [("orientConstraint", "orient-constrain")],
        CONSTRAINT_PARENT: [("parentConstraint", "parent-constrain")],
        CONSTRAINT_POINT_ORIENT: [("pointConstraint", "point-constrain"),
                                  ("orientConstraint", "orient-constrain")],
    }.get(opts.constraint, [])
    for i, (jnt, _, _) in enumerate(results):
        for kind, label in constraint_kinds:
            _constrain(_path(ids[i]), jnt, kind, label)

    out = [(jnt, _path(ids[i]), _path(top_ids[i])) for i, (jnt, _, _) in enumerate(results)]
    cmds.select([c for _, c, _ in out if c], replace=True)
    return out


def _rename_shapes(node):
    """Name a transform's shapes <node>Shape, <node>Shape1, ..."""
    short = node.split("|")[-1]
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    for i, shape in enumerate(shapes):
        try:
            cmds.rename(shape, "{0}Shape{1}".format(short, i or ""))
        except Exception:
            pass


# ── Batch rename ─────────────────────────────────────────────────────────────

def expand_hierarchy(nodes):
    """Each node followed by its descendants of the same node type.

    Selecting the root of a joint chain gives the whole chain, root first;
    shapes and nodes of other types (constraints, controls) are left out.
    """
    out = []
    for node in nodes:
        kind = cmds.nodeType(node)
        stack = [node]
        while stack:
            current = stack.pop(0)
            if current not in out:
                out.append(current)
            kids = cmds.listRelatives(current, children=True, fullPath=True, type=kind) or []
            stack = kids + stack
    return out


def format_rename(pattern, number, old_name=""):
    """Name from a rename pattern: # numbers (## pads), {name} = old name."""
    short = old_name.split("|")[-1].split(":")[-1]
    pattern = (pattern or "").strip() or "{name}"
    name = pattern.replace("{name}", short)
    name = re.sub(r"#+", lambda m: str(int(number)).zfill(len(m.group(0))), name)
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not name or name[0].isdigit():
        name = "_" + name
    return name


def _apply_renames(nodes, new_names, rename_shapes=True):
    """Rename nodes (tracked by UUID) in two passes so names can swap."""
    ids = [_uuid(n) for n in nodes]
    pairs = [(i, n) for i, n in zip(ids, new_names) if i]
    for k, (uuid, _) in enumerate(pairs):
        cmds.rename(_node_path(uuid), "atkRenameTmp{0}_".format(k))
    result = []
    for uuid, name in pairs:
        cmds.rename(_node_path(uuid), name)
        path = _node_path(uuid)
        if rename_shapes and cmds.listRelatives(path, shapes=True):
            _rename_shapes(path)
        result.append(path)
    return result


def batch_rename(nodes, pattern, start=1, step=1, hierarchy=False, rename_shapes=True):
    """Rename nodes in order from a pattern such as 'FlagPole_#_JNT'.

    ``hierarchy`` also renames every descendant of the same type, so
    selecting a chain's root joint renames the whole chain.  Returns the new
    long names.
    """
    shapes = set(cmds.ls(nodes, long=True, shapes=True) or [])
    nodes = [n for n in (cmds.ls(nodes, long=True) or []) if n not in shapes]
    if hierarchy:
        nodes = expand_hierarchy(nodes)
    if not nodes:
        return []
    if len(nodes) > 1 and "#" not in (pattern or "") and "{name}" not in (pattern or ""):
        pattern = (pattern or "").strip() + "_#"
    names = [format_rename(pattern, start + i * step, n) for i, n in enumerate(nodes)]
    return _apply_renames(nodes, names, rename_shapes)


def search_replace_names(nodes, search, replace="", hierarchy=False, rename_shapes=True):
    """Replace text in node names.  Returns the renamed nodes' long names."""
    if not search:
        return []
    nodes = cmds.ls(nodes, long=True) or []
    if hierarchy:
        nodes = expand_hierarchy(nodes)
    todo, names = [], []
    for n in nodes:
        short = n.split("|")[-1]
        new = format_rename(short.replace(search, replace), 0)
        if new != short:
            todo.append(n)
            names.append(new)
    return _apply_renames(todo, names, rename_shapes)


def prefix_suffix_names(nodes, prefix="", suffix="", hierarchy=False, rename_shapes=True):
    """Add a prefix and/or suffix to node names."""
    if not (prefix or suffix):
        return []
    nodes = cmds.ls(nodes, long=True) or []
    if hierarchy:
        nodes = expand_hierarchy(nodes)
    names = [format_rename(prefix + n.split("|")[-1] + suffix, 0) for n in nodes]
    return _apply_renames(nodes, names, rename_shapes)


# -----------------------------
# Registry
# -----------------------------
@dataclass(frozen=True)
class ShapeDef:
    key: str
    label: str
    creator: Callable[[], List[str]]
    icon_candidates: List[str]
    tooltip: str
    category: str


CATEGORY_ORDER = ["Primitives", "Arrows & Direction", "Rig Controls", "Utility"]


def _mel_creator(key: str, default_name: str) -> Callable[[], List[str]]:
    return lambda: _create_from_mel(key, rename_to=default_name)


def _py_creator(fn: Callable[[], str]) -> Callable[[], List[str]]:
    return lambda: [fn()]


def _parse_mel_cases() -> List[str]:
    return re.findall(r'case\s+\"([^\"]+)\"\s*:', _MEL_SOURCE)


def get_shape_defs() -> List[ShapeDef]:
    mel_cases = set(_parse_mel_cases())

    def mel_def(key, label, default_name, icons, tooltip, category):
        if key not in mel_cases:
            return None
        return ShapeDef(key, label, _mel_creator(key, default_name),
                        icons, tooltip, category)

    def py_def(key, label, fn, icons, tooltip, category):
        return ShapeDef(key, label, _py_creator(fn), icons, tooltip, category)

    rot = [":/rotateTool.png", ":/rotateManip.png", ":/menuIcon.xpm"]
    mov = [":/moveTool.png", ":/moveManip.png", ":/menuIcon.xpm"]

    defs = [
        # ── Primitives ──────────────────────────────────────────────────────
        mel_def("circleX", "Circle X", "circleX_CTRL", rot,
                "Circle facing the X axis - FK limbs, twist controls.", "Primitives"),
        mel_def("circleY", "Circle Y", "circleY_CTRL", rot,
                "Circle facing the Y axis - COG, hips, spine FK.", "Primitives"),
        mel_def("circleZ", "Circle Z", "circleZ_CTRL", rot,
                "Circle facing the Z axis - face and camera-facing controls.", "Primitives"),
        mel_def("square", "Square", "square_CTRL",
                [":/polyPlane.png", ":/polyCube.png", ":/menuIcon.xpm"],
                "Flat square - secondary body controls, panels.", "Primitives"),
        mel_def("cube", "Cube", "cube_CTRL", [":/polyCube.png", ":/menuIcon.xpm"],
                "Wire cube - chest, hips, prop and space-switch controls.", "Primitives"),
        mel_def("sphere", "Sphere", "sphere_CTRL", [":/polySphere.png", ":/menuIcon.xpm"],
                "Wire sphere - head, eye and free-floating controls.", "Primitives"),
        py_def("diamond", "Diamond", lambda: create_diamond("diamond_CTRL"),
               [":/polyCone.png", ":/polyPlane.png", ":/menuIcon.xpm"],
               "Flat diamond - small accents and secondary controls.", "Primitives"),
        py_def("diamond3D", "Diamond 3D", lambda: create_diamond_3d("diamond3D_CTRL"),
               [":/polyCone.png", ":/polySphere.png", ":/menuIcon.xpm"],
               "Octahedron - pole vectors, space switches, pivot markers.", "Primitives"),
        py_def("triangle", "Triangle", lambda: create_triangle("triangle_CTRL"),
               [":/polyCone.png", ":/menuIcon.xpm"],
               "Flat triangle - direction hints and simple switches.", "Primitives"),
        py_def("hexagon", "Hexagon", lambda: create_hexagon("hexagon_CTRL"),
               [":/polyPlane.png", ":/menuIcon.xpm"],
               "Flat hexagon - alternative to circles for utility controls.", "Primitives"),
        py_def("star", "Star", lambda: create_star("star_CTRL"),
               [":/polySphere.png", ":/menuIcon.xpm"],
               "Flat star - stand-out selector or special control.", "Primitives"),
        py_def("pyramid", "Pyramid", lambda: create_pyramid("pyramid_CTRL"),
               [":/polyPyramid.png", ":/polyCone.png", ":/menuIcon.xpm"],
               "Pyramid outline - direction / up-vector markers.", "Primitives"),
        py_def("capsule", "Capsule", lambda: create_capsule("capsule_CTRL"),
               [":/polyCylinder.png", ":/polySphere.png", ":/menuIcon.xpm"],
               "Flat capsule (XZ) - limb sections and sliders.", "Primitives"),
        py_def("halfCircle", "Half Circle", lambda: create_half_circle("halfCircle_CTRL"),
               rot, "Half circle - clavicles, brows and fan controls.", "Primitives"),
        mel_def("plus", "Plus", "plus_CTRL", [":/add.png", ":/plus.png", ":/menuIcon.xpm"],
                "3D plus / axis cross - small pivot markers.", "Primitives"),
        mel_def("cross", "Cross", "cross_CTRL",
                [":/close.png", ":/constraint.png", ":/menuIcon.xpm"],
                "Flat chunky cross - roll and secondary controls.", "Primitives"),

        # ── Arrows & Direction ──────────────────────────────────────────────
        mel_def("arrow", "Arrow", "arrow_CTRL", mov,
                "Flat single arrow - direction / aim indicator.", "Arrows & Direction"),
        py_def("doubleArrow", "Double Arrow", lambda: create_double_arrow("doubleArrow_CTRL"),
               mov, "Double-headed arrow (XZ) - sliders and 1-axis controls.",
               "Arrows & Direction"),
        py_def("fourWayArrow", "4-Way Arrow", lambda: create_four_way_arrow("fourWayArrow_CTRL"),
               mov, "4-way arrow (XY) - screen-space or 2-axis controls.",
               "Arrows & Direction"),
        py_def("circleArrow4", "Circle 4-Arrow", lambda: create_circle_4arrow("circleArrow4_CTRL"),
               mov, "Circle with 4 outward arrows (XZ) - COG / master mover.",
               "Arrows & Direction"),
        py_def("curvedArrow", "Curved Arrow", lambda: create_curved_arrow("curvedArrow_CTRL"),
               rot, "Curved arrow (XZ) - single-direction rotate control.",
               "Arrows & Direction"),
        py_def("spinArrows", "Spin Arrows", lambda: create_spin_arrows("spinArrows_CTRL"),
               rot, "Two opposing curved arrows (XZ) - spin / twist control.",
               "Arrows & Direction"),
        mel_def("orient", "Orient", "orient_CTRL",
                [":/orientConstraint.png", ":/aimConstraint.png", ":/menuIcon.xpm"],
                "Comet orient shape - rotate-in-any-direction control.",
                "Arrows & Direction"),

        # ── Rig Controls ────────────────────────────────────────────────────
        py_def("rootControl", "Root", lambda: create_root_control("root_CTRL"),
               mov, "Concentric circles with compass ticks - global / root control.",
               "Rig Controls"),
        py_def("gear", "Gear", lambda: create_gear("gear_CTRL"),
               [":/advancedSettings.png", ":/gear.png", ":/menuIcon.xpm"],
               "Gear outline - settings, IK/FK switch and utility controls.",
               "Rig Controls"),
        py_def("poleVector", "Pole Vector", lambda: create_pole_vector("poleVector_CTRL"),
               [":/polyCone.png", ":/menuIcon.xpm"],
               "Small 3D diamond with axis lines - IK pole vector.", "Rig Controls"),
        py_def("lollipop", "Lollipop", lambda: create_lollipop("lollipop_CTRL"),
               [":/joint.png", ":/kinJoint.png", ":/menuIcon.xpm"],
               "Stick with circle (XY) - FK pins that stay clear of the mesh.",
               "Rig Controls"),
        py_def("paddle", "Paddle", lambda: create_paddle("paddle_CTRL"),
               [":/joint.png", ":/menuIcon.xpm"],
               "Stick with rounded paddle (XY) - hand and finger controls.",
               "Rig Controls"),
        py_def("foot", "Foot", lambda: create_foot("foot_CTRL"),
               [":/kinHandle.png", ":/ikHandle.png", ":/menuIcon.xpm"],
               "Footprint outline (XZ, toes +Z) - IK foot control.", "Rig Controls"),
        py_def("eyeTarget", "Eye Target", lambda: create_eye_target("eyeTarget_CTRL"),
               [":/aimConstraint.png", ":/menuIcon.xpm"],
               "Circle with crosshair (faces +Z) - eye / aim target.", "Rig Controls"),
        py_def("flag", "Flag", lambda: create_flag("flag_CTRL"),
               [":/flag.png", ":/menuIcon.xpm"],
               "Pole with triangular flag (XY) - markers and switches.", "Rig Controls"),

        # ── Utility ─────────────────────────────────────────────────────────
        mel_def("null", "Null", "null_CTRL",
                [":/locator.png", ":/out_group.png", ":/menuIcon.xpm"],
                "Empty transform (no shape).", "Utility"),
        mel_def("group", "Group", "group_CTRL",
                [":/out_group.png", ":/group.png", ":/menuIcon.xpm"],
                "Empty group transform.", "Utility"),
        mel_def("locator", "Locator", "locator_CTRL", [":/locator.png", ":/menuIcon.xpm"],
                "Space locator.", "Utility"),
        mel_def("joint", "Joint", "joint_CTRL", [":/joint.png", ":/kinJoint.png", ":/menuIcon.xpm"],
                "Single joint at the origin.", "Utility"),
        mel_def("bulb", "Bulb", "bulb_CTRL",
                [":/lightPoint.png", ":/lightAmbient.png", ":/menuIcon.xpm"],
                "Light bulb outline - light or 'idea' control.", "Utility"),
    ]
    return [d for d in defs if d is not None]

# -----------------------------
# UI helpers
# -----------------------------
def _maya_main_window():
    """Return Maya's main window as a Qt widget for proper parenting."""
    try:
        import maya.OpenMayaUI as omui
        ptr = omui.MQtUtil.mainWindow()
        return wrapInstance(int(ptr), QtWidgets.QWidget)
    except Exception:
        return None


def _load_icon(candidates: List[str]) -> QtGui.QIcon:
    """Return the first icon that loads successfully, or a null icon."""
    for path in candidates:
        icon = QtGui.QIcon(path)
        if not icon.isNull():
            return icon
    return QtGui.QIcon()


# Qt6 / Qt5 enum compatibility helpers
def _tool_button_text_under_icon():
    if QT_VERSION == 6:
        return QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon
    return QtCore.Qt.ToolButtonTextUnderIcon


def _frame_no_frame():
    if QT_VERSION == 6:
        return QtWidgets.QFrame.Shape.NoFrame
    return QtWidgets.QFrame.NoFrame


# -----------------------------
# Stylesheet — matches the ATK toolbar / Reset Tool design language
# -----------------------------
_STYLESHEET = """
QDialog {
    background-color: #3c3c3c;
    color: #cccccc;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: #333333;
    width: 10px;
    margin: 0;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #5a5a5a;
    min-height: 24px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background: #6d6d6d;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QLabel {
    color: #cccccc;
    background: transparent;
}
QLabel#lbl_title {
    font-size: 14px;
    font-weight: bold;
    color: #ffffff;
}
QLabel#lbl_subtitle {
    font-size: 11px;
    color: #999999;
}
QLabel#lbl_section {
    font-size: 9px;
    font-weight: bold;
    color: #777777;
    letter-spacing: 1px;
}
QLabel#lbl_desc {
    font-size: 10px;
    color: #848484;
    padding-left: 2px;
}
QFrame#separator {
    background-color: #525252;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QLineEdit {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}
QLineEdit:focus {
    border-color: #2e6da4;
}
QCheckBox {
    color: #cccccc;
    font-size: 11px;
    spacing: 6px;
}
QTabWidget::pane {
    border: none;
    border-top: 1px solid #525252;
}
QTabBar::tab {
    background: #444444;
    color: #bbbbbb;
    border: 1px solid #555555;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 16px;
    margin-right: 2px;
    font-size: 11px;
}
QTabBar::tab:selected {
    background: #2e6da4;
    color: #ffffff;
    border-color: #4088c0;
}
QTabBar::tab:hover:!selected {
    background: #505050;
}
QTableWidget {
    background-color: #3a3a3a;
    alternate-background-color: #404040;
    color: #dddddd;
    gridline-color: #4a4a4a;
    border: 1px solid #555555;
    border-radius: 4px;
    font-size: 11px;
    selection-background-color: #2e6da4;
}
QHeaderView::section {
    background-color: #474747;
    color: #bbbbbb;
    border: none;
    border-right: 1px solid #555555;
    padding: 4px 6px;
    font-size: 10px;
}
QPushButton:checked {
    background-color: #2e6da4;
    border-color: #4088c0;
    color: #ffffff;
}
QPushButton:disabled {
    color: #6a6a6a;
    background-color: #474747;
}
QFrame#joint_panel {
    background-color: #353535;
    border: 1px solid #525252;
    border-radius: 4px;
}
QCheckBox#cb_joint_mode {
    font-size: 12px;
    font-weight: bold;
    color: #ffffff;
}
QRadioButton {
    color: #cccccc;
    font-size: 11px;
    spacing: 4px;
}
QRadioButton:disabled, QCheckBox:disabled, QLabel:disabled {
    color: #6a6a6a;
}
QComboBox {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    min-height: 22px;
}
QComboBox:disabled {
    color: #777777;
}
QComboBox QAbstractItemView {
    background-color: #4a4a4a;
    color: #dddddd;
    selection-background-color: #2e6da4;
}
QSpinBox, QDoubleSpinBox {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 22px;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #2e6da4;
}
QToolButton {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #5c5c5c;
    border-radius: 4px;
    padding: 8px;
    font-size: 11px;
}
QToolButton:hover {
    background-color: #585858;
    border-color: #888888;
    color: #ffffff;
}
QToolButton:pressed {
    background-color: #3a3a3a;
    border-color: #555555;
}
QPushButton {
    background-color: #555555;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 7px 14px;
    font-size: 12px;
    min-height: 30px;
}
QPushButton:hover {
    background-color: #636363;
    border-color: #888888;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #444444;
    border-color: #555555;
}
QPushButton#btn_primary {
    background-color: #2e6da4;
    color: #ffffff;
    border: 1px solid #4088c0;
    font-weight: bold;
}
QPushButton#btn_primary:hover {
    background-color: #3a7ec0;
    border-color: #5599d4;
}
QPushButton#btn_primary:pressed {
    background-color: #205080;
    border-color: #2e6da4;
}
"""

# -----------------------------
# UI
# -----------------------------
class WireShapeToolUI:
    OBJECT_NAME = "WireShapeToolUI"

    # keywords that keep the Offset Dummy section visible while searching
    _DUMMY_KEYWORDS = ("dummy", "offset", "null", "zero", "gizmo", "ofs")

    def __init__(self):
        # Close any existing instance
        for w in QtWidgets.QApplication.allWidgets():
            if getattr(w, "objectName", lambda: "")() == self.OBJECT_NAME:
                try:
                    w.close()
                except Exception:
                    pass

        parent = _maya_main_window()
        self.dlg = QtWidgets.QDialog(parent)
        self.dlg.setObjectName(self.OBJECT_NAME)
        self.dlg.setWindowTitle("Wire Shapes")
        self.dlg.setMinimumWidth(560)
        self.dlg.resize(600, 880)
        self.dlg.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.dlg.setStyleSheet(_STYLESHEET)

        self._sections = []   # (container_widget, [buttons])

        main = QtWidgets.QVBoxLayout(self.dlg)
        main.setContentsMargins(16, 14, 16, 16)
        main.setSpacing(0)

        # Header
        header = QtWidgets.QHBoxLayout()
        head_col = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("Wire Shapes")
        title.setObjectName("lbl_title")
        subtitle = QtWidgets.QLabel(
            "Create curve controls for rigging. Click a shape to create it; "
            "with Snap enabled, new controls land on the selected object."
        )
        subtitle.setObjectName("lbl_subtitle")
        subtitle.setWordWrap(True)
        head_col.addWidget(title)
        head_col.addSpacing(4)
        head_col.addWidget(subtitle)
        header.addLayout(head_col, 1)

        self.snap_cb = QtWidgets.QCheckBox("Snap to Selection")
        self.snap_cb.setChecked(True)
        self.snap_cb.setToolTip(
            "If something is selected, move the created control to the selection pivot."
        )
        header.addWidget(self.snap_cb, 0, QtCore.Qt.AlignTop)
        main.addLayout(header)
        main.addSpacing(12)

        self.tabs = QtWidgets.QTabWidget()
        main.addWidget(self.tabs, 1)

        # ── Shapes tab ──────────────────────────────────────────────────────
        shapes_tab = QtWidgets.QWidget()
        shapes_layout = QtWidgets.QVBoxLayout(shapes_tab)
        shapes_layout.setContentsMargins(0, 10, 0, 0)
        shapes_layout.setSpacing(0)
        self.tabs.addTab(shapes_tab, "Shapes")

        # Search
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search shapes...")
        self.search.setClearButtonEnabled(True)
        shapes_layout.addWidget(self.search)
        shapes_layout.addSpacing(10)

        self._shape_defs = get_shape_defs()
        self._defs_by_key = {d.key: d for d in self._shape_defs}

        # Scrollable body: Joint Mode panel, then the shape sections
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_frame_no_frame())
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        shapes_layout.addWidget(scroll, 1)

        body = QtWidgets.QWidget()
        scroll.setWidget(body)
        self._body_layout = QtWidgets.QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 6, 0)
        self._body_layout.setSpacing(0)

        self._build_joint_mode_panel(self._body_layout)
        self._body_layout.addSpacing(12)
        self._add_best_section()
        for category in CATEGORY_ORDER:
            defs = [d for d in self._shape_defs if d.category == category]
            if defs:
                self._add_section(category, defs)

        self._add_dummy_section()
        self._body_layout.addStretch()

        self.search.textChanged.connect(self._apply_filter)

        # ── Batch Rename tab ────────────────────────────────────────────────
        self._build_rename_tab()
        self._update_joint_mode_ui()

        # Footer
        main.addSpacing(10)
        sep = QtWidgets.QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        main.addWidget(sep)
        main.addSpacing(10)

        footer = QtWidgets.QHBoxLayout()
        tip = QtWidgets.QLabel(
            "Tip: Click a button to create a curve control. Default names end with _CTRL."
        )
        tip.setObjectName("lbl_desc")
        footer.addWidget(tip)
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.dlg.close)
        footer.addWidget(close_btn)
        main.addLayout(footer)

    # ── Joint Mode panel ─────────────────────────────────────────────────────

    def _build_joint_mode_panel(self, main):
        frame = QtWidgets.QFrame()
        frame.setObjectName("joint_panel")
        frame.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        outer = QtWidgets.QVBoxLayout(frame)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        head = QtWidgets.QHBoxLayout()
        self.joint_mode_cb = QtWidgets.QCheckBox("Joint Mode")
        self.joint_mode_cb.setObjectName("cb_joint_mode")
        self.joint_mode_cb.setToolTip(
            "Build controls on the selected joints: each control sits on the joint's\n"
            "pivot with the joint's rotation axes, and its shape faces down the chain."
        )
        head.addWidget(self.joint_mode_cb)
        head.addStretch(1)
        self.single_rb = QtWidgets.QRadioButton("Single Joint")
        self.single_rb.setToolTip("One control on each selected joint.")
        self.multi_rb = QtWidgets.QRadioButton("Multi-Joint Chain")
        self.multi_rb.setToolTip(
            "Walk the chain from the selection and build a control on every joint,\n"
            "set up as an FK hierarchy."
        )
        self.single_rb.setChecked(True)
        head.addWidget(self.single_rb)
        head.addWidget(self.multi_rb)
        outer.addLayout(head)

        self._joint_body = QtWidgets.QWidget()
        form = QtWidgets.QGridLayout(self._joint_body)
        form.setContentsMargins(0, 4, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        row = 0

        def label(text):
            lbl = QtWidgets.QLabel(text)
            lbl.setObjectName("lbl_subtitle")
            return lbl

        # Naming
        form.addWidget(label("Name:"), row, 0)
        self.name_edit = QtWidgets.QLineEdit("{joint}_CTRL")
        self.name_edit.setPlaceholderText("e.g. FlagPole_#_CTRL")
        self.name_edit.setToolTip(
            "Controller naming pattern.\n"
            "  #        the control's number (## pads to 01, ### to 001)\n"
            "  {joint}  the joint's name\n"
            "Example: FlagPole_#_CTRL gives FlagPole_1_CTRL, FlagPole_2_CTRL, ..."
        )
        form.addWidget(self.name_edit, row, 1)
        form.addWidget(label("Start #:"), row, 2)
        self.start_spin = QtWidgets.QSpinBox()
        self.start_spin.setRange(0, 9999)
        self.start_spin.setValue(1)
        self.start_spin.setToolTip("Number given to the first control in the chain.")
        form.addWidget(self.start_spin, row, 3)
        row += 1
        self.name_preview = QtWidgets.QLabel()
        self.name_preview.setObjectName("lbl_desc")
        form.addWidget(self.name_preview, row, 1, 1, 3)
        row += 1

        # Facing / axis
        form.addWidget(label("Shape faces:"), row, 0)
        self.facing_combo = QtWidgets.QComboBox()
        self.facing_combo.addItem("Down the chain (auto)", FACING_AUTO)
        for key in ("+X", "+Y", "+Z", "-X", "-Y", "-Z"):
            self.facing_combo.addItem("Joint " + key, key)
        self.facing_combo.addItem("Keep shape as built", FACING_KEEP)
        self.facing_combo.setToolTip(
            "Which of the joint's local axes the shape faces.\n"
            "Auto reads each joint's orientation and faces the axis that points\n"
            "to the next joint, so circles ring the bone. The control's own\n"
            "rotation axes always match the joint's."
        )
        form.addWidget(self.facing_combo, row, 1)

        form.addWidget(label("Size:"), row, 2)
        size_row = QtWidgets.QHBoxLayout()
        self.size_spin = QtWidgets.QDoubleSpinBox()
        self.size_spin.setRange(0.01, 1000.0)
        self.size_spin.setDecimals(2)
        self.size_spin.setSingleStep(0.25)
        self.size_spin.setValue(2.0)
        self.size_spin.setMaximumWidth(72)
        self.size_combo = QtWidgets.QComboBox()
        self.size_combo.addItem("x Radius", SIZE_RADIUS)
        self.size_combo.addItem("x Bone", SIZE_BONE)
        self.size_combo.addItem("units", SIZE_FIXED)
        self.size_combo.setToolTip(
            "Control size: a multiple of each joint's radius, a multiple of its\n"
            "bone length, or a fixed size in scene units.")
        size_row.addWidget(self.size_spin)
        size_row.addWidget(self.size_combo)
        form.addLayout(size_row, row, 3)
        row += 1

        # Setup
        self.zero_cb = QtWidgets.QCheckBox("Zero group")
        self.zero_cb.setChecked(True)
        self.zero_cb.setToolTip(
            "Put each control under a group matched to the joint, so the\n"
            "control's translate and rotate channels start at zero.\n"
            "Always on for a parent-constraint chain."
        )
        self.group_suffix_edit = QtWidgets.QLineEdit("GRP")
        self.group_suffix_edit.setToolTip("Suffix for the zero group: <control>_GRP")
        self.group_suffix_edit.setMaximumWidth(90)
        form.addWidget(label("Setup:"), row, 0)
        zero_row = QtWidgets.QHBoxLayout()
        zero_row.addWidget(self.zero_cb)
        zero_row.addWidget(self.group_suffix_edit)
        zero_row.addStretch(1)
        form.addLayout(zero_row, row, 1)
        form.addWidget(label("Drive joints:"), row, 2)
        self.constraint_combo = QtWidgets.QComboBox()
        self.constraint_combo.addItem("No constraint", CONSTRAINT_NONE)
        self.constraint_combo.addItem("Parent constraint", CONSTRAINT_PARENT)
        self.constraint_combo.addItem("Orient constraint", CONSTRAINT_ORIENT)
        self.constraint_combo.addItem("Point + Orient", CONSTRAINT_POINT_ORIENT)
        self.constraint_combo.setToolTip(
            "Constrain each joint to its new control (control drives joint).\n"
            "Nothing is parented: the joints stay where they are in the outliner.\n"
            "A joint that already has that constraint is skipped with a warning.")
        form.addWidget(self.constraint_combo, row, 3)
        row += 1

        # Multi-joint options
        form.addWidget(label("Chain:"), row, 0)
        self.chain_combo = QtWidgets.QComboBox()
        self.chain_combo.addItem("Selected joint + all below", CHAIN_BELOW)
        self.chain_combo.addItem("Start -> End (select 2 joints)", CHAIN_RANGE)
        self.chain_combo.setToolTip(
            "Selected + below: every joint under each selected joint.\n"
            "Start -> End: select the first joint, then the last joint."
        )
        form.addWidget(self.chain_combo, row, 1)
        self.skip_end_cb = QtWidgets.QCheckBox("Skip end joints")
        self.skip_end_cb.setChecked(True)
        self.skip_end_cb.setToolTip("No control on the last joint of a chain (it has nothing to rotate).")
        form.addWidget(self.skip_end_cb, row, 2, 1, 2)
        row += 1

        form.addWidget(label("Link controls:"), row, 0)
        self.link_combo = QtWidgets.QComboBox()
        self.link_combo.addItem("Parent-constraint chain (FK)", HIER_CONSTRAINT)
        self.link_combo.addItem("Nested hierarchy (FK)", HIER_PARENT)
        self.link_combo.addItem("Not linked", HIER_NONE)
        self.link_combo.setToolTip(
            "How each control follows the control above it:\n"
            "  Parent-constraint chain - every <control>_GRP stays flat in the\n"
            "      outliner and is parent-constrained to the control above.\n"
            "  Nested hierarchy - each <control>_GRP is parented under the\n"
            "      control above.\n"
            "  Not linked - independent controls.")
        form.addWidget(self.link_combo, row, 1)
        self.per_joint_btn = QtWidgets.QPushButton("Per-joint shapes...")
        self.per_joint_btn.setCheckable(True)
        self.per_joint_btn.setToolTip(
            "List the chain's joints and pick a different shape for each one.")
        form.addWidget(self.per_joint_btn, row, 2, 1, 2)
        row += 1

        self._per_joint_box = self._build_per_joint_box()
        form.addWidget(self._per_joint_box, row, 0, 1, 4)
        self._multi_widgets = [self.chain_combo, self.skip_end_cb, self.link_combo,
                               self.per_joint_btn]
        form.setColumnStretch(1, 3)
        form.setColumnStretch(3, 2)

        outer.addWidget(self._joint_body)
        main.addWidget(frame)

        self.joint_mode_cb.toggled.connect(self._update_joint_mode_ui)
        self.multi_rb.toggled.connect(self._update_joint_mode_ui)
        self.per_joint_btn.toggled.connect(self._update_joint_mode_ui)
        self.per_joint_btn.toggled.connect(lambda on: on and self._auto_load_joint_list())
        self.multi_rb.toggled.connect(lambda on: on and self._auto_load_joint_list())
        self.joint_mode_cb.toggled.connect(lambda on: on and self._auto_load_joint_list())
        self.size_spin.valueChanged.connect(self._on_global_size_changed)
        self.link_combo.currentIndexChanged.connect(self._update_joint_mode_ui)
        self.zero_cb.toggled.connect(self._update_joint_mode_ui)
        self.name_edit.textChanged.connect(self._update_name_preview)
        self.start_spin.valueChanged.connect(self._update_name_preview)
        self._update_name_preview()

    # ── Per-joint shape list ─────────────────────────────────────────────────

    def _build_per_joint_box(self):
        self._filling_list = False   # True while the code (not the user) fills rows
        self._list_edited = False    # the user changed a shape or size in the list
        box = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(box)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)

        hint = QtWidgets.QLabel(
            "The list follows your joint selection until you edit it. Pick a "
            "shape and size per joint (or select rows and click a shape below), "
            "then Build Controls.")
        hint.setObjectName("lbl_desc")
        hint.setWordWrap(True)
        v.addWidget(hint)

        buttons = QtWidgets.QHBoxLayout()
        load = QtWidgets.QPushButton("Load Selection")
        load.setToolTip("Fill the list with the joints the chain options select.\n"
                        "Shapes and sizes already set for a joint are kept.")
        load.clicked.connect(self._on_load_joint_list)
        best = QtWidgets.QPushButton("All: Best Option")
        best.setToolTip("Set every row to the recommended shape for its joint.")
        best.clicked.connect(lambda: self._assign_rows(BEST_SHAPE, all_rows=True))
        all_size = QtWidgets.QPushButton("All: Size")
        all_size.setToolTip("Set every row's size to the Size above.")
        all_size.clicked.connect(self._reset_row_sizes)
        clear = QtWidgets.QPushButton("Clear")
        clear.clicked.connect(self._clear_joint_list)
        for b in (load, best, all_size, clear):
            buttons.addWidget(b)
        buttons.addStretch(1)
        v.addLayout(buttons)

        self.joint_table = QtWidgets.QTableWidget(0, 4)
        self.joint_table.setHorizontalHeaderLabels(["Joint", "Shape", "Size", "Control name"])
        self.joint_table.horizontalHeaderItem(2).setToolTip(
            "Each control's size, read like the Size above (x Radius, x Bone or\n"
            "units). With several rows selected, editing one sets them all.")
        self.joint_table.verticalHeader().setVisible(False)
        self.joint_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.joint_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        header = self.joint_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(2, 78)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.joint_table.setMinimumHeight(150)
        self.joint_table.setMaximumHeight(190)
        v.addWidget(self.joint_table)

        self.build_list_btn = QtWidgets.QPushButton("Build Controls")
        self.build_list_btn.setObjectName("btn_primary")
        self.build_list_btn.setToolTip("Build one control per listed joint with its chosen shape.")
        self.build_list_btn.clicked.connect(self._on_build_joint_list)
        v.addWidget(self.build_list_btn)
        return box

    def _shape_combo(self, value=BEST_SHAPE):
        combo = QtWidgets.QComboBox()
        combo.addItem("Best option", BEST_SHAPE)
        for d in self._shape_defs:
            combo.addItem(d.label, d.key)
        idx = combo.findData(value.key if isinstance(value, ShapeDef) else value)
        combo.setCurrentIndex(max(idx, 0))
        combo.currentIndexChanged.connect(self._on_row_shape_changed)
        return combo

    def _size_spin(self, value):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(0.01, 1000.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.25)
        spin.setValue(value)
        spin.setProperty("edited", False)
        spin.setStyleSheet("QDoubleSpinBox { padding: 1px 4px; min-height: 18px; }")
        spin.valueChanged.connect(lambda v, sp=spin: self._on_row_size_changed(sp, v))
        return spin

    def _on_row_shape_changed(self, *_):
        if not self._filling_list:
            self._list_edited = True
        self._refresh_joint_table_names()

    def _on_row_size_changed(self, spin, value):
        if self._filling_list:
            return
        self._list_edited = True
        spin.setProperty("edited", True)
        # Editing one of several selected rows sets them all.
        rows = {i.row() for i in self.joint_table.selectionModel().selectedRows()}
        if len(rows) > 1 and any(self.joint_table.cellWidget(r, 2) is spin for r in rows):
            self._filling_list = True
            try:
                for r in rows:
                    other = self.joint_table.cellWidget(r, 2)
                    other.setValue(value)
                    other.setProperty("edited", True)
            finally:
                self._filling_list = False

    def _on_global_size_changed(self, value):
        """Rows that were not given their own size follow the Size field."""
        if not hasattr(self, "joint_table"):
            return
        self._filling_list = True
        try:
            for r in range(self.joint_table.rowCount()):
                spin = self.joint_table.cellWidget(r, 2)
                if not spin.property("edited"):
                    spin.setValue(value)
        finally:
            self._filling_list = False

    def _reset_row_sizes(self):
        self._filling_list = True
        try:
            for r in range(self.joint_table.rowCount()):
                spin = self.joint_table.cellWidget(r, 2)
                spin.setValue(self.size_spin.value())
                spin.setProperty("edited", False)
        finally:
            self._filling_list = False

    def _clear_joint_list(self):
        self.joint_table.setRowCount(0)
        self._list_edited = False

    def _on_load_joint_list(self, quiet=False):
        """Fill the list from the selection; keeps each joint's shape and size.

        ``quiet`` (automatic loads) leaves the list alone, without warnings,
        when the selection holds no joints.
        """
        opts = self._joint_mode_options()
        sel = cmds.ls(sl=True, long=True) or []
        try:
            joints = gather_joints(sel, True, opts.chain, opts.skip_end_joints)
        except ValueError as e:
            if not quiet:
                cmds.warning("Wire Shapes: {0}".format(e))
            return False
        if not joints:
            if not quiet:
                cmds.warning("Wire Shapes: Select the joint(s) of a chain first.")
            return False
        previous = {}
        for r in range(self.joint_table.rowCount()):
            jnt = self.joint_table.item(r, 0).data(QtCore.Qt.UserRole)
            spin = self.joint_table.cellWidget(r, 2)
            previous[jnt] = (self.joint_table.cellWidget(r, 1).currentData(),
                             spin.value(), spin.property("edited"))
        self._filling_list = True
        try:
            self.joint_table.setRowCount(0)
            for jnt in joints:
                key, size, edited = previous.get(jnt, (BEST_SHAPE, self.size_spin.value(), False))
                r = self.joint_table.rowCount()
                self.joint_table.insertRow(r)
                item = QtWidgets.QTableWidgetItem(jnt.split("|")[-1])
                item.setData(QtCore.Qt.UserRole, jnt)
                item.setToolTip(jnt)
                self.joint_table.setItem(r, 0, item)
                self.joint_table.setCellWidget(r, 1, self._shape_combo(key))
                spin = self._size_spin(size)
                spin.setProperty("edited", edited)
                self.joint_table.setCellWidget(r, 2, spin)
                self.joint_table.setItem(r, 3, QtWidgets.QTableWidgetItem(""))
        finally:
            self._filling_list = False
        if not quiet:
            self._list_edited = False
        self._refresh_joint_table_names()
        return True

    def _auto_load_joint_list(self, *_):
        """Pre-load the selection while the list is open and not hand-edited."""
        try:
            if not (self._per_joint_active() and self.dlg.isVisible()):
                return
            if self._list_edited and self.joint_table.rowCount():
                return
            self._on_load_joint_list(quiet=True)
        except RuntimeError:
            pass        # window already deleted

    def _start_selection_job(self):
        global _SELECTION_JOB
        _kill_selection_job()
        try:
            _SELECTION_JOB = cmds.scriptJob(event=["SelectionChanged", _on_selection_changed])
        except Exception:
            _SELECTION_JOB = None

    def _joint_table_rows(self):
        """[(joint, shape key, size)] in list order."""
        rows = []
        for r in range(self.joint_table.rowCount()):
            jnt = self.joint_table.item(r, 0).data(QtCore.Qt.UserRole)
            rows.append((jnt, self.joint_table.cellWidget(r, 1).currentData(),
                         self.joint_table.cellWidget(r, 2).value()))
        return rows

    def _refresh_joint_table_names(self, *_):
        if not hasattr(self, "joint_table"):
            return
        rows = self._joint_table_rows()
        pattern = self.name_edit.text()
        if len(rows) > 1 and pattern_needs_number(pattern):
            pattern = pattern.strip() + "_#"
        for r, (jnt, key, _size) in enumerate(rows):
            combo = self.joint_table.cellWidget(r, 1)
            try:
                best = self._defs_by_key.get(best_shape_key(jnt, bool(_child_joints(jnt))))
            except Exception:
                best = None
            combo.setItemText(0, "Best: " + (best.label if best else "Circle Y"))
            name = format_control_name(pattern, self.start_spin.value() + r, jnt)
            self.joint_table.item(r, 3).setText(name)

    def _assign_rows(self, key, all_rows=False):
        """Give the selected rows (or every row) of the joint list a shape."""
        rows = range(self.joint_table.rowCount()) if all_rows else sorted(
            {i.row() for i in self.joint_table.selectionModel().selectedRows()})
        for r in rows:
            combo = self.joint_table.cellWidget(r, 1)
            combo.setCurrentIndex(max(combo.findData(key), 0))
        self._refresh_joint_table_names()
        return len(rows)

    def _per_joint_active(self):
        return (self.joint_mode_cb.isChecked() and self.multi_rb.isChecked()
                and self.per_joint_btn.isChecked())

    def _on_build_joint_list(self):
        rows = self._joint_table_rows()
        if not rows:
            cmds.warning("Wire Shapes: Load the joints first (Load Joints from Selection).")
            return
        missing = [j for j, _, _ in rows if not cmds.objExists(j)]
        if missing:
            cmds.warning("Wire Shapes: Some listed joints no longer exist; load the joints again.")
            return
        self._build_on_joints([j for j, _, _ in rows], [k for _, k, _ in rows], "per-joint",
                              sizes=[sz for _, _, sz in rows])

    def _update_joint_mode_ui(self, *_):
        if not hasattr(self, "_best_container"):
            return          # still building the window
        on = self.joint_mode_cb.isChecked()
        self._joint_body.setVisible(on)
        self.single_rb.setEnabled(on)
        self.multi_rb.setEnabled(on)
        self.snap_cb.setEnabled(not on)
        multi = self.multi_rb.isChecked()
        for w in self._multi_widgets:
            w.setEnabled(multi)
        self._per_joint_box.setVisible(multi and self.per_joint_btn.isChecked())
        chain = multi and self.link_combo.currentData() == HIER_CONSTRAINT
        self.group_suffix_edit.setEnabled(self.zero_cb.isChecked() or chain)
        self._apply_filter(self.search.text())

    def _update_name_preview(self, *_):
        pattern = self.name_edit.text()
        if pattern_needs_number(pattern):
            pattern = pattern.strip() + "_#"
        start = self.start_spin.value()
        names = [format_control_name(pattern, start + i, "joint{0}".format(i + 1))
                 for i in range(3)]
        self.name_preview.setText("Preview: " + ", ".join(names) + ", ...")
        self._refresh_joint_table_names()

    def _joint_mode_options(self):
        return JointModeOptions(
            multi=self.multi_rb.isChecked(),
            chain=self.chain_combo.currentData(),
            skip_end_joints=self.skip_end_cb.isChecked(),
            facing=self.facing_combo.currentData(),
            size_mode=self.size_combo.currentData(),
            size=self.size_spin.value(),
            name_pattern=self.name_edit.text(),
            start_number=self.start_spin.value(),
            zero_group=self.zero_cb.isChecked(),
            group_suffix=self.group_suffix_edit.text(),
            hierarchy=self.link_combo.currentData(),
            constraint=self.constraint_combo.currentData(),
        )

    def _on_create_joint_mode(self, shape):
        """Build ``shape`` (a ShapeDef or BEST_SHAPE) on the selected joints."""
        if self._per_joint_active() and self.joint_table.rowCount():
            key = shape.key if isinstance(shape, ShapeDef) else shape
            if self._assign_rows(key):
                self._list_edited = True
                return
            cmds.warning("Wire Shapes: Select rows in the per-joint list to assign "
                         "this shape, or click Build Controls.")
            return
        opts = self._joint_mode_options()
        sel = cmds.ls(sl=True, long=True) or []
        try:
            joints = gather_joints(sel, opts.multi, opts.chain, opts.skip_end_joints)
        except ValueError as e:
            cmds.warning("Wire Shapes: {0}".format(e))
            return
        if not joints:
            cmds.warning("Wire Shapes: Joint Mode is on - select one or more joints.")
            return
        label = shape.label if isinstance(shape, ShapeDef) else "Best option"
        self._build_on_joints(joints, shape, label)

    def _build_on_joints(self, joints, shapes, label, sizes=None):
        opts = self._joint_mode_options()
        cmds.undoInfo(openChunk=True, chunkName="WireShapesJointMode")
        try:
            built = create_joint_controls(shapes, joints, opts, sizes=sizes)
        except Exception as e:
            cmds.warning("Wire Shapes: Failed to create '{0}' controls on joints: {1}".format(
                label, e))
            return
        finally:
            cmds.undoInfo(closeChunk=True)
        print("Wire Shapes: Created {0} '{1}' control(s) on joints.".format(len(built), label))

    # ── Best for Joints section ──────────────────────────────────────────────

    _BEST_KEYS = ("circleY", "square", "hexagon", "cube", "sphere",
                  "halfCircle", "lollipop", "spinArrows", "diamond3D", "circleArrow4",
                  "rootControl")

    def _add_best_section(self):
        container = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._section_label("Best for Joints"))
        v.addSpacing(8)

        self.best_btn = QtWidgets.QPushButton("Best Option  -  pick the right shape per joint")
        self.best_btn.setObjectName("btn_primary")
        self.best_btn.setToolTip(
            "Builds the recommended control on each joint:\n"
            "  root / world / master -> Root     COG / pelvis / hips -> Circle 4-Arrow\n"
            "  head / chest -> Cube              eye -> Sphere\n"
            "  jaw / clavicle / toe -> Half Circle   hand / palm -> Square\n"
            "  any other chain joint -> FK ring (Circle)   end joint -> Diamond 3D")
        self.best_btn.clicked.connect(lambda: self._on_create_joint_mode(BEST_SHAPE))
        v.addWidget(self.best_btn)
        v.addSpacing(8)

        grid_host = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        labels = {"circleY": "FK Ring", "circleArrow4": "COG"}
        buttons = []
        defs = [self._defs_by_key[k] for k in self._BEST_KEYS if k in self._defs_by_key]
        for i, d in enumerate(defs):
            btn = QtWidgets.QToolButton()
            btn.setToolButtonStyle(_tool_button_text_under_icon())
            btn.setText(labels.get(d.key, d.label))
            btn.setIcon(_load_icon(d.icon_candidates))
            btn.setIconSize(QtCore.QSize(24, 24))
            btn.setMinimumSize(90, 62)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            btn.setToolTip(d.tooltip)
            btn.setProperty("shape_key", d.key)
            btn.clicked.connect(lambda _=False, dd=d: self._on_create(dd))
            grid.addWidget(btn, i // 4, i % 4)
            buttons.append(btn)
        for cidx in range(4):
            grid.setColumnStretch(cidx, 1)
        v.addWidget(grid_host)
        v.addSpacing(14)
        sep = QtWidgets.QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        v.addWidget(sep)
        v.addSpacing(12)

        self._body_layout.addWidget(container)
        self._best_container = container
        self._best_buttons = buttons

    # ── Batch Rename tab ─────────────────────────────────────────────────────

    def _build_rename_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        v.setContentsMargins(0, 12, 0, 0)
        v.setSpacing(6)
        self.tabs.addTab(tab, "Batch Rename")

        desc = QtWidgets.QLabel(
            "Rename the selected objects in selection order. Tick 'Include "
            "children' and select a chain's root joint to rename the whole chain.")
        desc.setObjectName("lbl_desc")
        desc.setWordWrap(True)
        v.addWidget(desc)
        v.addSpacing(6)

        def label(text):
            lbl = QtWidgets.QLabel(text)
            lbl.setObjectName("lbl_subtitle")
            return lbl

        v.addWidget(self._section_label("Rename"))
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(label("Name:"), 0, 0)
        self.rn_pattern = QtWidgets.QLineEdit()
        self.rn_pattern.setPlaceholderText("e.g. FlagPole_#_JNT")
        self.rn_pattern.setToolTip(
            "  #       the number (## pads to 01, ### to 001)\n"
            "  {name}  the object's current name\n"
            "FlagPole_#_JNT gives FlagPole_1_JNT, FlagPole_2_JNT, ...")
        grid.addWidget(self.rn_pattern, 0, 1, 1, 3)
        grid.addWidget(label("Start #:"), 1, 0)
        self.rn_start = QtWidgets.QSpinBox()
        self.rn_start.setRange(0, 99999)
        self.rn_start.setValue(1)
        grid.addWidget(self.rn_start, 1, 1)
        grid.addWidget(label("Step:"), 1, 2)
        self.rn_step = QtWidgets.QSpinBox()
        self.rn_step.setRange(1, 1000)
        self.rn_step.setValue(1)
        grid.addWidget(self.rn_step, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        v.addLayout(grid)
        self.rn_preview = QtWidgets.QLabel()
        self.rn_preview.setObjectName("lbl_desc")
        v.addWidget(self.rn_preview)

        opts_row = QtWidgets.QHBoxLayout()
        self.rn_children = QtWidgets.QCheckBox("Include children (same type)")
        self.rn_children.setToolTip(
            "Also rename every descendant of the same type as each selected\n"
            "object - select a root joint to rename the whole joint chain.")
        self.rn_shapes = QtWidgets.QCheckBox("Rename shapes to match")
        self.rn_shapes.setChecked(True)
        opts_row.addWidget(self.rn_children)
        opts_row.addWidget(self.rn_shapes)
        opts_row.addStretch(1)
        v.addLayout(opts_row)
        btn = QtWidgets.QPushButton("Rename Selected")
        btn.setObjectName("btn_primary")
        btn.clicked.connect(self._on_batch_rename)
        v.addWidget(btn)
        v.addSpacing(12)

        v.addWidget(self._section_label("Search and Replace"))
        sr = QtWidgets.QHBoxLayout()
        self.rn_search = QtWidgets.QLineEdit()
        self.rn_search.setPlaceholderText("Search")
        self.rn_replace = QtWidgets.QLineEdit()
        self.rn_replace.setPlaceholderText("Replace with")
        sr_btn = QtWidgets.QPushButton("Replace")
        sr_btn.clicked.connect(self._on_search_replace)
        sr.addWidget(self.rn_search)
        sr.addWidget(self.rn_replace)
        sr.addWidget(sr_btn)
        v.addLayout(sr)
        v.addSpacing(12)

        v.addWidget(self._section_label("Prefix / Suffix"))
        ps = QtWidgets.QHBoxLayout()
        self.rn_prefix = QtWidgets.QLineEdit()
        self.rn_prefix.setPlaceholderText("Prefix, e.g. L_")
        self.rn_suffix = QtWidgets.QLineEdit()
        self.rn_suffix.setPlaceholderText("Suffix, e.g. _JNT")
        ps_btn = QtWidgets.QPushButton("Add")
        ps_btn.clicked.connect(self._on_prefix_suffix)
        ps.addWidget(self.rn_prefix)
        ps.addWidget(self.rn_suffix)
        ps.addWidget(ps_btn)
        v.addLayout(ps)
        v.addStretch(1)

        self.rn_pattern.textChanged.connect(self._update_rename_preview)
        self.rn_start.valueChanged.connect(self._update_rename_preview)
        self.rn_step.valueChanged.connect(self._update_rename_preview)
        self._update_rename_preview()

    def _update_rename_preview(self, *_):
        pattern = self.rn_pattern.text().strip()
        if not pattern:
            self.rn_preview.setText("Preview: type a name pattern.")
            return
        if "#" not in pattern and "{name}" not in pattern:
            pattern += "_#"
        start, step = self.rn_start.value(), self.rn_step.value()
        names = [format_rename(pattern, start + i * step, "joint{0}".format(i + 1))
                 for i in range(3)]
        self.rn_preview.setText("Preview: " + ", ".join(names) + ", ...")

    def _run_rename(self, label, fn):
        sel = cmds.ls(sl=True, long=True) or []
        if not sel:
            cmds.warning("Wire Shapes: Select the objects to rename.")
            return
        cmds.undoInfo(openChunk=True, chunkName="WireShapesRename")
        try:
            renamed = fn(sel)
        except Exception as e:
            cmds.warning("Wire Shapes: {0} failed: {1}".format(label, e))
            return
        finally:
            cmds.undoInfo(closeChunk=True)
        if renamed:
            cmds.select(renamed, replace=True)
        print("Wire Shapes: {0}: renamed {1} object(s).".format(label, len(renamed)))

    def _on_batch_rename(self):
        pattern = self.rn_pattern.text().strip()
        if not pattern:
            cmds.warning("Wire Shapes: Type a name pattern such as FlagPole_#_JNT.")
            return
        self._run_rename("Rename", lambda sel: batch_rename(
            sel, pattern, self.rn_start.value(), self.rn_step.value(),
            self.rn_children.isChecked(), self.rn_shapes.isChecked()))

    def _on_search_replace(self):
        if not self.rn_search.text():
            cmds.warning("Wire Shapes: Type the text to search for.")
            return
        self._run_rename("Search and Replace", lambda sel: search_replace_names(
            sel, self.rn_search.text(), self.rn_replace.text(),
            self.rn_children.isChecked(), self.rn_shapes.isChecked()))

    def _on_prefix_suffix(self):
        if not (self.rn_prefix.text() or self.rn_suffix.text()):
            cmds.warning("Wire Shapes: Type a prefix or a suffix.")
            return
        self._run_rename("Prefix / Suffix", lambda sel: prefix_suffix_names(
            sel, self.rn_prefix.text(), self.rn_suffix.text(),
            self.rn_children.isChecked(), self.rn_shapes.isChecked()))

    # ── Section builders ─────────────────────────────────────────────────────

    def _section_label(self, text):
        lbl = QtWidgets.QLabel(text.upper())
        lbl.setObjectName("lbl_section")
        return lbl

    def _add_section(self, category: str, defs: List[ShapeDef]):
        container = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(self._section_label(category))
        v.addSpacing(8)

        grid_host = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        buttons = []
        cols = 4
        for i, d in enumerate(defs):
            btn = QtWidgets.QToolButton()
            btn.setToolButtonStyle(_tool_button_text_under_icon())
            btn.setText(d.label)
            btn.setIcon(_load_icon(d.icon_candidates))
            btn.setIconSize(QtCore.QSize(28, 28))
            btn.setMinimumSize(114, 76)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            btn.setToolTip(d.tooltip)
            btn.setProperty("shape_key", d.key)
            btn.clicked.connect(lambda _=False, dd=d: self._on_create(dd))
            grid.addWidget(btn, i // cols, i % cols)
            buttons.append(btn)
        # keep incomplete last rows left-aligned at even widths
        for cidx in range(cols):
            grid.setColumnStretch(cidx, 1)

        v.addWidget(grid_host)
        v.addSpacing(14)

        sep = QtWidgets.QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        v.addWidget(sep)
        v.addSpacing(12)

        self._body_layout.addWidget(container)
        self._sections.append((container, buttons))

    def _add_dummy_section(self):
        container = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(self._section_label("Offset Dummy"))
        v.addSpacing(8)

        desc = QtWidgets.QLabel(
            "A locator-style gizmo control wrapped in offset groups "
            "(name_ZERO > name_OFS1... > name_CTRL). Use it as a clean null, "
            "a constraint target, or a layered offset for counter-animation."
        )
        desc.setObjectName("lbl_desc")
        desc.setWordWrap(True)
        v.addWidget(desc)
        v.addSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        lbl = QtWidgets.QLabel("Offset groups:")
        lbl.setObjectName("lbl_subtitle")
        row.addWidget(lbl)

        self.offset_spin = QtWidgets.QSpinBox()
        self.offset_spin.setRange(0, 5)
        self.offset_spin.setValue(2)
        self.offset_spin.setToolTip(
            "How many offset groups to build between the ZERO group and the control."
        )
        row.addWidget(self.offset_spin)
        row.addStretch(1)
        v.addLayout(row)
        v.addSpacing(8)

        btn_dummy = QtWidgets.QPushButton("Create Offset Dummy")
        btn_dummy.setObjectName("btn_primary")
        btn_dummy.setToolTip(
            "Create the dummy gizmo wrapped in the chosen number of offset groups.\n"
            "With Snap enabled it is placed at the selected object's pivot."
        )
        btn_dummy.clicked.connect(self._on_create_dummy)
        v.addWidget(btn_dummy)
        v.addSpacing(6)

        btn_wrap = QtWidgets.QPushButton("Wrap Selection in Offset Groups")
        btn_wrap.setToolTip(
            "Insert the chosen number of matched offset groups directly above\n"
            "each selected object. Channel values are preserved."
        )
        btn_wrap.clicked.connect(self._on_wrap_selection)
        v.addWidget(btn_wrap)
        v.addSpacing(14)

        self._body_layout.addWidget(container)
        self._dummy_container = container

    # ── Filtering ────────────────────────────────────────────────────────────

    def _apply_filter(self, text: str):
        if not hasattr(self, "_dummy_container"):
            return          # still building the window
        text = (text or "").strip().lower()

        for container, buttons in self._sections:
            any_visible = False
            for btn in buttons:
                label = (btn.text() or "").lower()
                key = (btn.property("shape_key") or "").lower()
                visible = (text == "") or (text in label) or (text in key)
                btn.setVisible(visible)
                any_visible = any_visible or visible
            container.setVisible(any_visible)

        dummy_visible = (text == "") or any(text in k for k in self._DUMMY_KEYWORDS)
        self._dummy_container.setVisible(dummy_visible)

        joint_mode = self.joint_mode_cb.isChecked()
        any_best = False
        for btn in self._best_buttons:
            label = (btn.text() or "").lower()
            key = (btn.property("shape_key") or "").lower()
            visible = (text == "") or (text in label) or (text in key)
            btn.setVisible(visible)
            any_best = any_best or visible
        any_best = any_best or text == "" or text in "best option"
        self._best_container.setVisible(joint_mode and any_best)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _snap_to_previous_selection(self, node, prev_sel, index=-1):
        """Move node to the pivot of a previously selected object (last by default)."""
        if not (self.snap_cb.isChecked() and prev_sel):
            return
        try:
            src = prev_sel[index]
            pos = cmds.xform(src, q=True, ws=True, rp=True)
            cmds.xform(node, ws=True, t=pos)
        except Exception:
            pass

    def _on_create(self, shape_def: ShapeDef):
        if self.joint_mode_cb.isChecked():
            self._on_create_joint_mode(shape_def)
            return
        # Capture selection before creation for snap-to-selection
        prev_sel = cmds.ls(sl=True, long=True) or []
        # The classic MEL shapes build one copy per selected object so each
        # can snap to its own target. With Snap off that only stacks
        # duplicates at the origin, so create a single shape instead.
        if prev_sel and not self.snap_cb.isChecked():
            cmds.select(clear=True)
        try:
            created = shape_def.creator()
        except Exception as e:
            cmds.warning(
                "Wire Shapes: Failed to create '{0}': {1}".format(shape_def.label, e)
            )
            return

        if not created:
            cmds.warning(
                "Wire Shapes: No object created for '{0}'.".format(shape_def.label)
            )
            return

        cmds.select(created, replace=True)
        if len(created) > 1 and len(created) == len(prev_sel):
            # One shape per selected object: snap each to its own target.
            for i, node in enumerate(created):
                self._snap_to_previous_selection(node, prev_sel, i)
        else:
            self._snap_to_previous_selection(created[0], prev_sel)

        try:
            cmds.xform(created, centerPivots=True)
        except Exception:
            pass

    def _on_create_dummy(self):
        prev_sel = cmds.ls(sl=True, long=True) or []
        try:
            zero, ctrl = create_offset_dummy("dummy", offsets=self.offset_spin.value())
        except Exception as e:
            cmds.warning("Wire Shapes: Failed to create offset dummy: {0}".format(e))
            return
        # Move the whole chain via the ZERO group so the control stays zeroed
        self._snap_to_previous_selection(zero, prev_sel)
        cmds.select(ctrl, replace=True)

    def _on_wrap_selection(self):
        try:
            add_offset_groups(self.offset_spin.value() or 1)
        except Exception as e:
            cmds.warning("Wire Shapes: Failed to add offset groups: {0}".format(e))

    def show(self):
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
        self._start_selection_job()
        job = _SELECTION_JOB
        self.dlg.finished.connect(lambda *_: _kill_selection_job(job))
        self.dlg.destroyed.connect(lambda *_: _kill_selection_job(job))
        self._auto_load_joint_list()


_UI_INSTANCE = None
_SELECTION_JOB = None


def _on_selection_changed():
    """SelectionChanged scriptJob: keep the per-joint list on the selection."""
    ui = _UI_INSTANCE
    if ui is None:
        _kill_selection_job()
        return
    ui._auto_load_joint_list()


def _kill_selection_job(only=None):
    """Kill the selection scriptJob (only if it is ``only``, when given)."""
    global _SELECTION_JOB
    if only is not None and only != _SELECTION_JOB:
        return          # an older window closing: its job is already gone
    job, _SELECTION_JOB = _SELECTION_JOB, None
    if job is None:
        return
    try:
        if cmds.scriptJob(exists=job):
            cmds.scriptJob(kill=job, force=True)
    except Exception:
        pass


def shutdown():
    """Release the selection scriptJob and close the window.

    Called by the ATK toolbar before Reload Scripts and when Maya quits.
    """
    global _UI_INSTANCE
    _kill_selection_job()
    ui, _UI_INSTANCE = _UI_INSTANCE, None
    if ui is not None:
        try:
            ui.dlg.close()
        except RuntimeError:
            pass


def show():
    """Show the Wire Shapes UI."""
    global _UI_INSTANCE
    _UI_INSTANCE = WireShapeToolUI()
    _UI_INSTANCE.show()
    return _UI_INSTANCE
