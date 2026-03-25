# -*- coding: utf-8 -*-
"""
wire_shape_tool.py

Maya Wire Shape Tool
- Loads Comet's wireShape.mel (embedded) and exposes buttons to create its shapes.
- Adds extra common curve shapes (e.g., 4-way arrow) in pure Python.

Usage (Script Editor - Python):
    import wire_shape_tool
    wire_shape_tool.show()
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional

import maya.cmds as cmds
import maya.mel as mel

# -----------------------------
# Embedded MEL (wireShape.mel)
# snaps.mel dependency removed — snapping is handled by Python
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
# Qt compatibility: PySide6 (Maya 2026+) with PySide2 fallback
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


def create_star(name: str = "star_CTRL") -> str:
    import math
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
    import math
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

def create_circle_4arrow(name: str = "circleArrow4_CTRL") -> str:
    """Circle in the XZ plane with 4 outward arrows — typical translate/move control."""
    import math

    r      = 1.0    # circle radius
    ar     = 1.55   # arrow tip distance from origin
    ah     = 0.28   # arrowhead depth
    hw     = 0.20   # arrowhead half-width
    sw     = 0.07   # shaft half-width

    # Circle in XZ plane (normal Y)
    import maya.cmds as _cmds
    ctrl = _cmds.circle(nr=(0, 1, 0), r=r, s=20, ch=False)[0]

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
        arrow_crv = _cmds.curve(p=pts, d=1)
        shapes = _cmds.listRelatives(arrow_crv, shapes=True, fullPath=True)
        _cmds.parent(shapes, ctrl, r=True, s=True)
        _cmds.delete(arrow_crv)

    return _cmds.rename(ctrl, name)


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
    category: str  # "MEL" or "Extra"


def _mel_creator(key: str, default_name: str) -> Callable[[], List[str]]:
    return lambda: _create_from_mel(key, rename_to=default_name)


def _py_creator(fn: Callable[[], str]) -> Callable[[], List[str]]:
    return lambda: [fn()]


def _parse_mel_cases() -> List[str]:
    return re.findall(r'case\s+\"([^\"]+)\"\s*:', _MEL_SOURCE)


def get_shape_defs() -> List[ShapeDef]:
    mel_cases = set(_parse_mel_cases())

    primary = [
        ("arrow", "Arrow", "arrow_CTRL"),
        ("cross", "Cross", "cross_CTRL"),
        ("square", "Square", "square_CTRL"),
        ("cube", "Cube", "cube_CTRL"),
        ("orient", "Orient", "orient_CTRL"),
        ("circleX", "Circle X", "circleX_CTRL"),
        ("circleY", "Circle Y", "circleY_CTRL"),
        ("circleZ", "Circle Z", "circleZ_CTRL"),
        ("null", "Null", "null_CTRL"),
        ("group", "Group", "group_CTRL"),
        ("locator", "Locator", "locator_CTRL"),
        ("bulb", "Bulb", "bulb_CTRL"),
        ("sphere", "Sphere", "sphere_CTRL"),
        ("plus", "Plus", "plus_CTRL"),
        ("joint", "Joint", "joint_CTRL"),
    ]

    mel_icons = {
        "Arrow": [":/moveTool.png", ":/moveManip.png", ":/moveUV.png", ":/menuIcon.xpm"],
        "Cross": [":/close.png", ":/constraint.png", ":/menuIcon.xpm"],
        "Square": [":/polyPlane.png", ":/polyCube.png", ":/menuIcon.xpm"],
        "Cube": [":/polyCube.png", ":/menuIcon.xpm"],
        "Orient": [":/orientConstraint.png", ":/aimConstraint.png", ":/menuIcon.xpm"],
        "Circle X": [":/rotateTool.png", ":/rotateManip.png", ":/menuIcon.xpm"],
        "Circle Y": [":/rotateTool.png", ":/rotateManip.png", ":/menuIcon.xpm"],
        "Circle Z": [":/rotateTool.png", ":/rotateManip.png", ":/menuIcon.xpm"],
        "Null": [":/locator.png", ":/out_group.png", ":/menuIcon.xpm"],
        "Group": [":/out_group.png", ":/group.png", ":/menuIcon.xpm"],
        "Locator": [":/locator.png", ":/menuIcon.xpm"],
        "Bulb": [":/lightPoint.png", ":/lightAmbient.png", ":/menuIcon.xpm"],
        "Sphere": [":/polySphere.png", ":/menuIcon.xpm"],
        "Plus": [":/add.png", ":/plus.png", ":/menuIcon.xpm"],
        "Joint": [":/joint.png", ":/kinJoint.png", ":/menuIcon.xpm"],
    }

    defs: List[ShapeDef] = []
    for key, label, default_name in primary:
        if key not in mel_cases:
            continue
        defs.append(
            ShapeDef(
                key=key,
                label=label,
                creator=_mel_creator(key, default_name),
                icon_candidates=mel_icons.get(label, [":/menuIcon.xpm"]),
                tooltip="Create wireShape: {0}".format(key),
                category="MEL",
            )
        )

    extras = [
        ShapeDef("fourWayArrow", "4-Way Arrow", _py_creator(lambda: create_four_way_arrow("fourWayArrow_CTRL")),
                 [":/moveTool.png", ":/moveManip.png", ":/menuIcon.xpm"], "Create 4-way arrow (XY).", "Extra"),
        ShapeDef("circleArrow4", "Circle 4-Arrow", _py_creator(lambda: create_circle_4arrow("circleArrow4_CTRL")),
                 [":/moveTool.png", ":/moveManip.png", ":/menuIcon.xpm"], "Create circle with 4 outward arrows (XZ plane, translate control).", "Extra"),
        ShapeDef("doubleArrow", "Double Arrow", _py_creator(lambda: create_double_arrow("doubleArrow_CTRL")),
                 [":/moveTool.png", ":/moveManip.png", ":/menuIcon.xpm"], "Create double-headed arrow flat on XZ plane.", "Extra"),
        ShapeDef("diamond", "Diamond", _py_creator(lambda: create_diamond("diamond_CTRL")),
                 [":/polyCone.png", ":/polyPlane.png", ":/menuIcon.xpm"], "Create diamond (2D).", "Extra"),
        ShapeDef("star", "Star", _py_creator(lambda: create_star("star_CTRL")),
                 [":/polySphere.png", ":/menuIcon.xpm"], "Create star (2D).", "Extra"),
        ShapeDef("pyramid", "Pyramid", _py_creator(lambda: create_pyramid("pyramid_CTRL")),
                 [":/polyPyramid.png", ":/polyCone.png", ":/menuIcon.xpm"], "Create pyramid outline.", "Extra"),
        ShapeDef("capsule", "Capsule", _py_creator(lambda: create_capsule("capsule_CTRL")),
                 [":/polyCylinder.png", ":/polySphere.png", ":/menuIcon.xpm"], "Create capsule (2D in XZ).", "Extra"),
    ]
    defs.extend(extras)
    return defs

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


def _window_context_help_button():
    if QT_VERSION == 6:
        return QtCore.Qt.WindowType.WindowContextHelpButtonHint
    return QtCore.Qt.WindowContextHelpButtonHint

# -----------------------------
# UI
# -----------------------------
class WireShapeToolUI:
    OBJECT_NAME = "WireShapeToolUI"

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
        self.dlg.setWindowFlags(
            self.dlg.windowFlags() ^ _window_context_help_button()
        )

        # Subtle modern style (dark)
        self.dlg.setStyleSheet("""
            QDialog { background: #2b2b2b; }
            QLabel { color: #d8d8d8; }
            QLineEdit {
                padding: 7px 10px;
                border-radius: 10px;
                border: 1px solid #3a3a3a;
                background: #1f1f1f;
                color: #eaeaea;
            }
            QToolButton {
                border-radius: 14px;
                border: 1px solid #3a3a3a;
                background: #262626;
                padding: 10px;
            }
            QToolButton:hover {
                border: 1px solid #5a5a5a;
                background: #303030;
            }
            QToolButton:pressed {
                background: #1f1f1f;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                border-radius: 12px;
                top: -1px;
            }
            QTabBar::tab {
                padding: 8px 14px;
                border: 1px solid #3a3a3a;
                border-bottom: none;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                background: #242424;
                margin-right: 4px;
                color: #d8d8d8;
            }
            QTabBar::tab:selected {
                background: #2b2b2b;
            }
            QCheckBox { color: #d8d8d8; }
            QPushButton {
                padding: 7px 14px;
                border-radius: 10px;
                border: 1px solid #3a3a3a;
                background: #262626;
                color: #eaeaea;
            }
            QPushButton:hover {
                border: 1px solid #5a5a5a;
                background: #303030;
            }
        """)

        main = QtWidgets.QVBoxLayout(self.dlg)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        # Header
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Create Control Shapes")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch(1)

        self.snap_cb = QtWidgets.QCheckBox("Snap to Selection")
        self.snap_cb.setChecked(True)
        self.snap_cb.setToolTip(
            "If something is selected, move the created control to the selection pivot."
        )
        header.addWidget(self.snap_cb)
        main.addLayout(header)

        # Search
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search shapes…")
        main.addWidget(self.search)

        # Tabs
        self.tabs = QtWidgets.QTabWidget()
        main.addWidget(self.tabs, 1)

        self._shape_defs = get_shape_defs()
        self._mel_defs = [d for d in self._shape_defs if d.category == "MEL"]
        self._extra_defs = [d for d in self._shape_defs if d.category == "Extra"]

        self._mel_grid = self._make_tab("MEL Shapes", self._mel_defs)
        self._extra_grid = self._make_tab("Extra Shapes", self._extra_defs)

        self.search.textChanged.connect(self._apply_filter)

        # Footer
        footer = QtWidgets.QHBoxLayout()
        tip = QtWidgets.QLabel(
            "Tip: Click a button to create a curve control. Default names end with _CTRL."
        )
        tip.setStyleSheet("font-size: 12px; color: #bdbdbd;")
        footer.addWidget(tip)
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.dlg.close)
        footer.addWidget(close_btn)
        main.addLayout(footer)

    def _make_tab(self, title: str, defs: List[ShapeDef]):
        page = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(10, 10, 10, 10)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_frame_no_frame())
        v.addWidget(scroll)

        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)

        grid = QtWidgets.QGridLayout(inner)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        cols = 4
        for i, d in enumerate(defs):
            btn = QtWidgets.QToolButton()
            btn.setToolButtonStyle(_tool_button_text_under_icon())
            btn.setText(d.label)
            btn.setIcon(_load_icon(d.icon_candidates))
            btn.setIconSize(QtCore.QSize(34, 34))
            btn.setMinimumSize(120, 92)
            btn.setToolTip(d.tooltip)
            btn.setProperty("shape_key", d.key)
            btn.clicked.connect(lambda _=False, dd=d: self._on_create(dd))
            grid.addWidget(btn, i // cols, i % cols)

        self.tabs.addTab(page, title)
        return grid

    def _apply_filter(self, text: str):
        text = (text or "").strip().lower()

        def _filter_grid(grid):
            for i in range(grid.count()):
                item = grid.itemAt(i)
                if item is None:
                    continue
                w = item.widget()
                if not w:
                    continue
                label = (w.text() or "").lower()
                key = (w.property("shape_key") or "").lower()
                w.setVisible((text == "") or (text in label) or (text in key))

        _filter_grid(self._mel_grid)
        _filter_grid(self._extra_grid)

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

        # Snap: move created[0] to pivot of previous selection's last item
        if self.snap_cb.isChecked() and prev_sel:
            try:
                target = created[0]
                src = prev_sel[-1]
                pos = cmds.xform(src, q=True, ws=True, rp=True)
                cmds.xform(target, ws=True, t=pos)
            except Exception:
                pass

        try:
            cmds.xform(created, centerPivots=True)
        except Exception:
            pass

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
