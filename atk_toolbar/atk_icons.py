"""ATK Icons — icon loading and QPainter-based icon generation.

Strategy
--------
1.  Try to load the tool's PNG from Maya's userBitmapsDir.
2.  If the PNG is missing or empty, draw a vector icon with QPainter.

All generated icons share a consistent visual language:
  • 32 × 32 px canvas (scalable)
  • Dark background (#2b2b2b) with a subtle rounded-rect border
  • Coloured accent line/symbol matching the tool's group colour
  • Thin white foreground strokes (2 px)
"""

import os
import math

import maya.cmds as cmds

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

# ---------------------------------------------------------------------------
# Colour palette — one accent colour per tool group
# ---------------------------------------------------------------------------
GROUP_COLORS = {
    "timing":   QtGui.QColor("#4FC3F7"),   # light blue
    "viewport": QtGui.QColor("#81C784"),   # green
    "rigging":  QtGui.QColor("#FFB74D"),   # orange
    "pipeline": QtGui.QColor("#CE93D8"),   # purple
    "settings": QtGui.QColor("#90A4AE"),   # steel grey
}

_BG_COLOR     = QtGui.QColor("#2b2b2b")
_BORDER_COLOR = QtGui.QColor("#484848")
_FG_COLOR     = QtGui.QColor("#e0e0e0")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_or_generate_icon(icon_file, icon_key, group="settings", size=32):
    """Return a QIcon for the given tool.

    Tries userBitmapsDir first; falls back to a generated vector icon.

    Parameters
    ----------
    icon_file : str
        Basename of the PNG (e.g. ``"temp-pivot.png"``).
    icon_key : str
        Key for the generated icon shape (e.g. ``"pivot"``).
    group : str
        Tool group name, determines accent colour.
    size : int
        Pixel size of the generated icon (PNG is loaded at its natural size).
    """
    # -- Try the PNG from userBitmapsDir first --------------------------------
    bitmaps_dir = cmds.internalVar(userBitmapsDir=True)
    png_path = os.path.join(bitmaps_dir, icon_file)
    if os.path.isfile(png_path):
        icon = QtGui.QIcon(png_path)
        if not icon.isNull():
            return icon

    # -- Fall back: generate from QPainter ------------------------------------
    return _generate_icon(icon_key, group, size)


def make_settings_icon(size=32):
    """Return a gear icon for the Settings button."""
    # Try to load the gearIcon.png from known locations
    icon_name = "gearIcon.png"
    pref_dir = cmds.internalVar(userPrefDir=True)
    search_paths = [
        os.path.join(pref_dir, "icons", icon_name),
        os.path.join(cmds.internalVar(userBitmapsDir=True), icon_name),
        os.path.join(os.path.dirname(__file__), "icons", icon_name),
    ]
    for path in search_paths:
        if os.path.isfile(path):
            icon = QtGui.QIcon(path)
            if not icon.isNull():
                return icon
    # Fall back to generated icon if PNG not found
    return _generate_icon("gear", "settings", size)


def make_warning_icon(size=32):
    """Return a warning ⚠ icon used when a tool is not installed."""
    return _generate_icon("warning", "settings", size)


# ---------------------------------------------------------------------------
# Internal — icon generation
# ---------------------------------------------------------------------------

def _generate_icon(icon_key, group, size):
    """Create a QIcon by painting onto a QPixmap."""
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

    accent = GROUP_COLORS.get(group, GROUP_COLORS["settings"])

    _draw_background(painter, size)
    _draw_symbol(painter, icon_key, accent, size)

    painter.end()
    return QtGui.QIcon(pixmap)


def _draw_background(painter, size):
    """Rounded-rect dark background with a subtle border."""
    r = size * 0.15
    rect = QtCore.QRectF(0.5, 0.5, size - 1, size - 1)

    painter.setBrush(QtGui.QBrush(_BG_COLOR))
    painter.setPen(QtGui.QPen(_BORDER_COLOR, 1.0))
    painter.drawRoundedRect(rect, r, r)


def _pen(color, width=1.8):
    p = QtGui.QPen(color, width)
    p.setCapStyle(QtCore.Qt.RoundCap)
    p.setJoinStyle(QtCore.Qt.RoundJoin)
    return p


def _draw_symbol(painter, icon_key, accent, size):
    """Dispatch to the appropriate drawing function."""
    s = size
    m = s * 0.18   # margin from edge
    painter.setPen(_pen(accent, s * 0.06))
    painter.setBrush(QtCore.Qt.NoBrush)

    dispatch = {
        "gear":    _draw_gear,
        "tween":   _draw_tween,
        "frames":  _draw_frames,
        "noise":   _draw_noise,
        "pivot":   _draw_pivot,
        "onion":   _draw_onion,
        "snap":    _draw_snap,
        "wire":    _draw_wire,
        "reset":   _draw_reset,
        "mirror":  _draw_mirror,
        "save":    _draw_save,
        "warning": _draw_warning,
    }

    fn = dispatch.get(icon_key, _draw_generic)
    fn(painter, accent, s, m)


# ── Individual symbol painters ──────────────────────────────────────────────

def _draw_gear(painter, accent, s, m):
    """8-tooth gear."""
    cx, cy = s / 2, s / 2
    outer_r = s * 0.36
    inner_r = s * 0.24
    hole_r  = s * 0.10
    teeth   = 8

    path = QtGui.QPainterPath()
    for i in range(teeth * 2):
        angle = math.radians(i * 360 / (teeth * 2))
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()

    painter.setPen(_pen(accent, s * 0.05))
    painter.setBrush(QtGui.QBrush(accent.darker(200)))
    painter.drawPath(path)

    # Centre hole
    painter.setBrush(QtGui.QBrush(_BG_COLOR))
    painter.setPen(_pen(accent, s * 0.04))
    painter.drawEllipse(QtCore.QPointF(cx, cy), hole_r, hole_r)


def _draw_tween(painter, accent, s, m):
    """Three vertical bars — left/right dimmed, centre highlighted."""
    bar_w = s * 0.13
    gap   = s * 0.07
    total = bar_w * 3 + gap * 2
    x0    = (s - total) / 2
    bar_h_side   = s * 0.45
    bar_h_center = s * 0.60
    cy = s / 2

    dim = accent.darker(180)

    for i, (bh, col) in enumerate([(bar_h_side, dim), (bar_h_center, accent), (bar_h_side, dim)]):
        x = x0 + i * (bar_w + gap)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QBrush(col))
        painter.drawRoundedRect(
            QtCore.QRectF(x, cy - bh / 2, bar_w, bh),
            bar_w * 0.3, bar_w * 0.3
        )


def _draw_frames(painter, accent, s, m):
    """Up arrow above, down arrow below — add/remove frames."""
    cx = s / 2
    aw = s * 0.30   # arrow width (half)
    ah = s * 0.22   # arrow height
    gap = s * 0.06
    shaft_w = s * 0.10

    painter.setPen(QtCore.Qt.NoPen)

    # Up arrow
    up_tip = s * 0.12
    up_base = up_tip + ah
    tri_up = QtGui.QPolygonF([
        QtCore.QPointF(cx, up_tip),
        QtCore.QPointF(cx - aw, up_base),
        QtCore.QPointF(cx + aw, up_base),
    ])
    painter.setBrush(QtGui.QBrush(accent))
    painter.drawPolygon(tri_up)
    # shaft
    painter.drawRect(QtCore.QRectF(cx - shaft_w / 2, up_base, shaft_w, s * 0.12))

    # Down arrow
    dn_tip = s * 0.88
    dn_base = dn_tip - ah
    tri_dn = QtGui.QPolygonF([
        QtCore.QPointF(cx, dn_tip),
        QtCore.QPointF(cx - aw, dn_base),
        QtCore.QPointF(cx + aw, dn_base),
    ])
    painter.setBrush(QtGui.QBrush(accent.darker(140)))
    painter.drawPolygon(tri_dn)
    painter.drawRect(QtCore.QRectF(cx - shaft_w / 2, dn_base - s * 0.12, shaft_w, s * 0.12))


def _draw_noise(painter, accent, s, m):
    """Jagged zigzag wave across the middle."""
    painter.setPen(_pen(accent, s * 0.07))
    painter.setBrush(QtCore.Qt.NoBrush)

    path = QtGui.QPainterPath()
    n = 6
    y_amp = s * 0.25
    cy = s / 2
    xs = [m + (s - 2 * m) * i / n for i in range(n + 1)]

    path.moveTo(xs[0], cy)
    for i, x in enumerate(xs[1:], 1):
        y = cy - y_amp if i % 2 == 1 else cy + y_amp
        path.lineTo(x, y)

    painter.drawPath(path)


def _draw_pivot(painter, accent, s, m):
    """Circle with crosshair + offset smaller dot representing a pivot."""
    cx, cy = s / 2, s / 2
    r = s * 0.28
    dot_r = s * 0.08
    offset = s * 0.22

    # Main circle
    painter.setPen(_pen(accent, s * 0.055))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)

    # Cross
    painter.drawLine(QtCore.QPointF(cx, cy - r), QtCore.QPointF(cx, cy + r))
    painter.drawLine(QtCore.QPointF(cx - r, cy), QtCore.QPointF(cx + r, cy))

    # Offset pivot dot
    painter.setBrush(QtGui.QBrush(accent))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawEllipse(QtCore.QPointF(cx + offset, cy - offset), dot_r, dot_r)


def _draw_onion(painter, accent, s, m):
    """Three overlapping circles with decreasing opacity."""
    cx, cy = s / 2, s / 2
    r = s * 0.22
    shift = s * 0.16

    for i, (dx, alpha) in enumerate([(-shift, 80), (0, 160), (shift, 80)]):
        col = QtGui.QColor(accent)
        col.setAlpha(alpha)
        painter.setPen(_pen(col, s * 0.055))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawEllipse(QtCore.QPointF(cx + dx, cy), r, r)


def _draw_snap(painter, accent, s, m):
    """Two overlapping circles with an arrow — snap/align symbol."""
    cx, cy = s / 2, s / 2
    r = s * 0.18
    offset = s * 0.16

    # Source circle (left)
    painter.setPen(_pen(accent.darker(160), s * 0.055))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawEllipse(QtCore.QPointF(cx - offset, cy), r, r)

    # Target circle (right)
    painter.setPen(_pen(accent, s * 0.055))
    painter.drawEllipse(QtCore.QPointF(cx + offset, cy), r, r)

    # Arrow from source to target
    arrow_y = cy
    arrow_x0 = cx - offset + r + s * 0.04
    arrow_x1 = cx + offset - r - s * 0.04
    painter.setPen(_pen(accent, s * 0.06))
    painter.drawLine(QtCore.QPointF(arrow_x0, arrow_y),
                     QtCore.QPointF(arrow_x1, arrow_y))

    # Arrowhead
    ah = s * 0.08
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QBrush(accent))
    arrow_head = QtGui.QPolygonF([
        QtCore.QPointF(arrow_x1, arrow_y),
        QtCore.QPointF(arrow_x1 - ah, arrow_y - ah * 0.7),
        QtCore.QPointF(arrow_x1 - ah, arrow_y + ah * 0.7),
    ])
    painter.drawPolygon(arrow_head)


def _draw_wire(painter, accent, s, m):
    """Star/asterisk-like polygon outline representing a rig control."""
    cx, cy = s / 2, s / 2
    outer_r = s * 0.36
    inner_r = s * 0.16
    points = 5
    path = QtGui.QPainterPath()

    for i in range(points * 2):
        angle = math.radians(i * 360 / (points * 2) - 90)
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()

    painter.setPen(_pen(accent, s * 0.055))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawPath(path)


def _draw_reset(painter, accent, s, m):
    """Circular arrow (↺) — reset / undo symbol."""
    cx, cy = s / 2, s / 2
    r = s * 0.29
    gap_angle = 70   # degrees of the circle that are open

    rect = QtCore.QRectF(cx - r, cy - r, r * 2, r * 2)
    painter.setPen(_pen(accent, s * 0.07))
    painter.setBrush(QtCore.Qt.NoBrush)
    # Arc going most of the way around (anticlockwise gap at top-right)
    painter.drawArc(rect, int((90 + gap_angle / 2) * 16), int((360 - gap_angle) * 16))

    # Arrowhead at the end of the arc
    end_angle = math.radians(90 - gap_angle / 2)
    ax = cx + r * math.cos(end_angle)
    ay = cy - r * math.sin(end_angle)
    aw = s * 0.12
    ah = s * 0.14
    # Rotate arrowhead tangent to the circle at that point
    tangent = end_angle + math.pi / 2
    tip_x = ax + aw * math.cos(tangent - 0.4)
    tip_y = ay - aw * math.sin(tangent - 0.4)

    arrow = QtGui.QPolygonF([
        QtCore.QPointF(ax, ay),
        QtCore.QPointF(ax - ah * math.cos(tangent + 0.9),
                       ay + ah * math.sin(tangent + 0.9)),
        QtCore.QPointF(tip_x, tip_y),
    ])
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QBrush(accent))
    painter.drawPolygon(arrow)


def _draw_save(painter, accent, s, m):
    """Floppy-disk silhouette with a small + badge."""
    x0, y0 = m, m
    w = s - 2 * m
    h = s - 2 * m
    notch = w * 0.25
    corner = w * 0.10

    # Floppy body
    path = QtGui.QPainterPath()
    path.moveTo(x0, y0 + notch)
    path.lineTo(x0, y0 + h - corner)
    path.quadTo(x0, y0 + h, x0 + corner, y0 + h)
    path.lineTo(x0 + w - corner, y0 + h)
    path.quadTo(x0 + w, y0 + h, x0 + w, y0 + h - corner)
    path.lineTo(x0 + w, y0)
    path.lineTo(x0 + notch, y0)
    path.closeSubpath()

    painter.setPen(_pen(accent, s * 0.055))
    painter.setBrush(QtGui.QBrush(accent.darker(220)))
    painter.drawPath(path)

    # Label area (lower portion)
    label_h = h * 0.38
    painter.setBrush(QtGui.QBrush(accent.darker(160)))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawRect(QtCore.QRectF(x0 + w * 0.10, y0 + h - label_h, w * 0.80, label_h * 0.85))

    # Top slot (shutter)
    shutter_w = w * 0.45
    shutter_h = h * 0.22
    painter.setBrush(QtGui.QBrush(accent.darker(180)))
    painter.drawRect(QtCore.QRectF(x0 + w * 0.30, y0, shutter_w, shutter_h))

    # + badge (bottom-right)
    bx = x0 + w * 0.72
    by = y0 + h * 0.68
    br = s * 0.12
    painter.setBrush(QtGui.QBrush(accent))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawEllipse(QtCore.QPointF(bx, by), br, br)
    pw = s * 0.055
    painter.setPen(_pen(_BG_COLOR, pw))
    painter.drawLine(QtCore.QPointF(bx - br * 0.6, by), QtCore.QPointF(bx + br * 0.6, by))
    painter.drawLine(QtCore.QPointF(bx, by - br * 0.6), QtCore.QPointF(bx, by + br * 0.6))


def _draw_mirror(painter, accent, s, m):
    """Two mirrored arrows around a vertical center line."""
    cx = s / 2.0

    painter.setPen(_pen(accent, s * 0.05))
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawLine(QtCore.QPointF(cx, m), QtCore.QPointF(cx, s - m))

    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(QtGui.QBrush(accent))

    left = QtGui.QPolygonF([
        QtCore.QPointF(cx - s * 0.08, s * 0.30),
        QtCore.QPointF(cx - s * 0.30, s * 0.30),
        QtCore.QPointF(cx - s * 0.22, s * 0.20),
        QtCore.QPointF(cx - s * 0.40, s * 0.38),
        QtCore.QPointF(cx - s * 0.22, s * 0.56),
        QtCore.QPointF(cx - s * 0.30, s * 0.46),
        QtCore.QPointF(cx - s * 0.08, s * 0.46),
    ])
    right = QtGui.QPolygonF([
        QtCore.QPointF(cx + s * 0.08, s * 0.54),
        QtCore.QPointF(cx + s * 0.30, s * 0.54),
        QtCore.QPointF(cx + s * 0.22, s * 0.64),
        QtCore.QPointF(cx + s * 0.40, s * 0.46),
        QtCore.QPointF(cx + s * 0.22, s * 0.28),
        QtCore.QPointF(cx + s * 0.30, s * 0.38),
        QtCore.QPointF(cx + s * 0.08, s * 0.38),
    ])
    painter.drawPolygon(left)
    painter.drawPolygon(right)


def _draw_warning(painter, accent, s, m):
    """Warning triangle ⚠."""
    cx = s / 2
    tip_y = m + s * 0.05
    base_y = s - m
    bw = s * 0.38

    tri = QtGui.QPolygonF([
        QtCore.QPointF(cx, tip_y),
        QtCore.QPointF(cx - bw, base_y),
        QtCore.QPointF(cx + bw, base_y),
    ])
    painter.setPen(_pen(QtGui.QColor("#FFB74D"), s * 0.055))
    painter.setBrush(QtGui.QBrush(QtGui.QColor("#FFB74D").darker(220)))
    painter.drawPolygon(tri)

    # Exclamation mark
    painter.setPen(_pen(QtGui.QColor("#FFB74D"), s * 0.08))
    mid_x = cx
    painter.drawLine(QtCore.QPointF(mid_x, tip_y + s * 0.20),
                     QtCore.QPointF(mid_x, base_y - s * 0.18))
    painter.setBrush(QtGui.QBrush(QtGui.QColor("#FFB74D")))
    painter.setPen(QtCore.Qt.NoPen)
    dot_r = s * 0.06
    painter.drawEllipse(QtCore.QPointF(mid_x, base_y - s * 0.10), dot_r, dot_r)


def _draw_generic(painter, accent, s, m):
    """Fallback: simple filled circle."""
    cx, cy = s / 2, s / 2
    r = s * 0.28
    painter.setPen(_pen(accent, s * 0.06))
    painter.setBrush(QtGui.QBrush(accent.darker(200)))
    painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)
