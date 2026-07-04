# -*- coding: utf-8 -*-
"""
wire_shape_tool.py

Maya Wire Shape Tool
- Loads Comet's wireShape.mel (embedded) and exposes buttons to create its shapes.
- Adds a library of rig-ready controller shapes (COG, pole vector, IK foot,
  lollipop pins, gear switches, aim targets, ...) in pure Python, organised
  into categories.
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
    if rename_to and created:
        try:
            created[0] = cmds.rename(created[0], rename_to)
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

    outermost = []
    for node in sel:
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
            target = cmds.parent(target, grp)[0]
            if first_grp is None:
                first_grp = grp
        outermost.append(first_grp)

    cmds.select(sel, replace=True)
    print("Wire Shapes: Added {0} offset group(s) to {1} object(s).".format(count, len(sel)))
    return outermost


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
QSpinBox {
    background-color: #4a4a4a;
    color: #dddddd;
    border: 1px solid #666666;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    min-height: 22px;
}
QSpinBox:focus {
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
        self.dlg.setMinimumWidth(540)
        self.dlg.resize(560, 720)
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

        # Search
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search shapes...")
        self.search.setClearButtonEnabled(True)
        main.addWidget(self.search)
        main.addSpacing(12)

        # Scrollable body with category sections
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_frame_no_frame())
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        main.addWidget(scroll, 1)

        body = QtWidgets.QWidget()
        scroll.setWidget(body)
        self._body_layout = QtWidgets.QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 6, 0)
        self._body_layout.setSpacing(0)

        self._shape_defs = get_shape_defs()
        for category in CATEGORY_ORDER:
            defs = [d for d in self._shape_defs if d.category == category]
            if defs:
                self._add_section(category, defs)

        self._add_dummy_section()
        self._body_layout.addStretch()

        self.search.textChanged.connect(self._apply_filter)

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

    # ── Actions ──────────────────────────────────────────────────────────────

    def _snap_to_previous_selection(self, node, prev_sel):
        """Move node to the pivot of the last previously selected object."""
        if not (self.snap_cb.isChecked() and prev_sel):
            return
        try:
            src = prev_sel[-1]
            pos = cmds.xform(src, q=True, ws=True, rp=True)
            cmds.xform(node, ws=True, t=pos)
        except Exception:
            pass

    def _on_create(self, shape_def: ShapeDef):
        # Capture selection before creation for snap-to-selection
        prev_sel = cmds.ls(sl=True, long=True) or []

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


_UI_INSTANCE = None


def show():
    """Show the Wire Shapes UI."""
    global _UI_INSTANCE
    _UI_INSTANCE = WireShapeToolUI()
    _UI_INSTANCE.show()
    return _UI_INSTANCE
