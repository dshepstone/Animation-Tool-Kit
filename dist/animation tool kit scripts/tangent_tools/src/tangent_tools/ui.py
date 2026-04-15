"""Tangent Tools — Qt window.

Builds a modern dockable-style panel that drives the operations in
:mod:`tangent_tools.core`.  The window is intentionally kept as a single
class so it's easy to follow and easy to theme.
"""
from __future__ import absolute_import, division, print_function

import os

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:                                     # Maya 2022-2024
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

import maya.OpenMayaUI as omui

from . import core


WINDOW_OBJECT_NAME = "TangentToolsPanel"
WINDOW_TITLE       = "Tangent Tools"


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLE_SHEET = """
QWidget#TangentToolsPanel {
    background-color: #2b2b2b;
    color: #dddddd;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 11px;
}
QLabel#SectionHeader {
    color: #f0c060;
    font-size: 11px;
    font-weight: bold;
    padding: 6px 2px 2px 2px;
    border-bottom: 1px solid #3f3f3f;
}
QLabel#HelperText {
    color: #9a9a9a;
    font-size: 10px;
    font-style: italic;
    padding: 0px 2px 4px 2px;
}
QPushButton {
    background-color: #3a3a3a;
    color: #eeeeee;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 20px;
}
QPushButton:hover      { background-color: #4a4a4a; border-color: #5a5a5a; }
QPushButton:pressed    { background-color: #2f2f2f; }
QPushButton:checked    { background-color: #5a7a9a; border-color: #6a8aaa; }
QPushButton#TangentBtn {
    background-color: #353535;
    border: 1px solid #505050;
    padding: 8px;
}
QPushButton#TangentBtn:hover {
    background-color: #454545;
    border-color: #f0c060;
}
QFrame#Card {
    background-color: #333333;
    border: 1px solid #3f3f3f;
    border-radius: 6px;
}
QToolTip {
    background-color: #1e1e1e;
    color: #f0f0f0;
    border: 1px solid #555555;
    padding: 4px;
}
"""


def _maya_main_window():
    """Return Maya's main window as a ``QWidget``."""
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def _icons_dir():
    """Resolve the repo-level ``tangent_icons`` directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    # src/tangent_tools/ui.py → <repo>/tangent_icons
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    return os.path.join(repo_root, "tangent_icons")


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

class TangentToolsWindow(QtWidgets.QWidget):
    """Main Tangent Tools panel."""

    def __init__(self, parent=None):
        super(TangentToolsWindow, self).__init__(parent or _maya_main_window())
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setStyleSheet(STYLE_SHEET)
        self.setMinimumWidth(320)

        self._build_ui()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(self._build_tangent_section())
        root.addWidget(self._build_weighted_section())
        root.addWidget(self._build_infinity_section())
        root.addWidget(self._build_display_section())
        root.addStretch(1)

    # ------------------------------------------------------------------
    # Tangent types
    # ------------------------------------------------------------------

    def _build_tangent_section(self):
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(4)

        layout.addWidget(self._section_header("Tangent Type"))
        layout.addWidget(self._helper(
            "Apply a tangent type to the selected controllers, objects "
            "or to the keys/curves currently selected in the Graph Editor."
        ))

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(self._make_tangent_button(
            "Auto Spline\n(Legacy)", "AutoSpline.png", "auto_legacy",
            "Auto Spline (Legacy) — Maya's classic spline tangent. "
            "Applies to selected objects, curves or individual keys."
        ))
        row.addWidget(self._make_tangent_button(
            "Linear", "Linear.png", "linear",
            "Linear tangents — straight-line interpolation between keys. "
            "Applies to selected objects, curves or individual keys."
        ))
        row.addWidget(self._make_tangent_button(
            "Stepped", "stepped.png", "stepped",
            "Stepped tangents — hold each value until the next key. "
            "Applies to selected objects, curves or individual keys."
        ))

        layout.addLayout(row)
        return card

    def _make_tangent_button(self, label, icon_file, kind, tooltip):
        btn = QtWidgets.QPushButton(label)
        btn.setObjectName("TangentBtn")
        btn.setToolTip(tooltip)
        btn.setMinimumHeight(70)
        btn.setCursor(QtCore.Qt.PointingHandCursor)

        icon_path = os.path.join(_icons_dir(), icon_file)
        if os.path.exists(icon_path):
            btn.setIcon(QtGui.QIcon(icon_path))
            btn.setIconSize(QtCore.QSize(32, 32))

        btn.clicked.connect(lambda: core.set_tangent_type(kind))
        return btn

    # ------------------------------------------------------------------
    # Weighted tangents
    # ------------------------------------------------------------------

    def _build_weighted_section(self):
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(4)

        layout.addWidget(self._section_header("Weighted Tangents"))
        layout.addWidget(self._helper(
            "Convert curves between weighted and non-weighted tangents. "
            "Weighted tangents let you drag tangent length for finer "
            "control; non-weighted keeps handles at a fixed length."
        ))

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        to_non = QtWidgets.QPushButton("Non-Weighted")
        to_non.setToolTip(
            "Convert the selected curves' tangents to non-weighted. "
            "Works on objects, curves and keys selected in the Graph Editor."
        )
        to_non.clicked.connect(lambda: core.set_weighted(False))

        to_wgt = QtWidgets.QPushButton("Weighted")
        to_wgt.setToolTip(
            "Convert the selected curves' tangents to weighted. "
            "Works on objects, curves and keys selected in the Graph Editor."
        )
        to_wgt.clicked.connect(lambda: core.set_weighted(True))

        row.addWidget(to_non)
        row.addWidget(to_wgt)
        layout.addLayout(row)
        return card

    # ------------------------------------------------------------------
    # Pre/Post Infinity
    # ------------------------------------------------------------------

    def _build_infinity_section(self):
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        layout.addWidget(self._section_header("Pre / Post Infinity"))
        layout.addWidget(self._helper(
            "Control how a curve behaves before its first key and after "
            "its last. Choose a mode, then click Pre, Post or Both."
        ))

        # (Display label, internal mode passed to cmds.setInfinity).  Order
        # matches Maya's own pre/post infinity menu.
        self._infinity_modes = [
            ("Cycle",            "cycle"),
            ("Cycle with Offset", "cycleRelative"),
            ("Oscillate",        "oscillate"),
            ("Linear",           "linear"),
            ("Constant",         "constant"),
        ]
        self._infinity_combo = QtWidgets.QComboBox()
        for label, _mode in self._infinity_modes:
            self._infinity_combo.addItem(label)
        self._infinity_combo.setToolTip(
            "Infinity mode to apply:\n"
            "  Cycle             — repeat the curve\n"
            "  Cycle with Offset — repeat with the value offset preserved\n"
            "  Oscillate         — mirror the curve back and forth\n"
            "  Linear            — extrapolate linearly using the end tangent\n"
            "  Constant          — hold the boundary value"
        )
        layout.addWidget(self._infinity_combo)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        pre_btn = QtWidgets.QPushButton("Pre")
        pre_btn.setToolTip("Apply the selected infinity mode to the PRE side only.")
        pre_btn.clicked.connect(lambda: self._apply_infinity(pre=True, post=False))

        post_btn = QtWidgets.QPushButton("Post")
        post_btn.setToolTip("Apply the selected infinity mode to the POST side only.")
        post_btn.clicked.connect(lambda: self._apply_infinity(pre=False, post=True))

        both_btn = QtWidgets.QPushButton("Both")
        both_btn.setToolTip("Apply the selected infinity mode to both PRE and POST sides.")
        both_btn.clicked.connect(lambda: self._apply_infinity(pre=True, post=True))

        row.addWidget(pre_btn)
        row.addWidget(post_btn)
        row.addWidget(both_btn)
        layout.addLayout(row)
        return card

    def _apply_infinity(self, pre, post):
        idx = self._infinity_combo.currentIndex()
        if idx < 0 or idx >= len(self._infinity_modes):
            return
        _label, mode = self._infinity_modes[idx]
        core.set_infinity(mode, pre=pre, post=post)

    # ------------------------------------------------------------------
    # Display / curve behaviour
    # ------------------------------------------------------------------

    def _build_display_section(self):
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        layout.addWidget(self._section_header("Curve Display"))
        layout.addWidget(self._helper(
            "Quality-of-life controls for the Graph Editor, including "
            "visibility filters, isolate, mute, and buffer-curve tools."
        ))

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        # Row 0 — display toggles
        self._show_selected_btn = QtWidgets.QPushButton("Show Selected Type(s)")
        self._show_selected_btn.setToolTip(
            "Apply the Graph Editor's Show > Selected Type(s) filter "
            "using the current selection."
        )
        self._show_selected_btn.clicked.connect(
            lambda: core.toggle_show_selected_curves_only(True)
        )

        self._show_all_btn = QtWidgets.QPushButton("Show All")
        self._show_all_btn.setToolTip(
            "Clear Graph Editor channel filters and restore all curves."
        )
        self._show_all_btn.clicked.connect(core.show_all_curves)

        self._isolate_btn = QtWidgets.QPushButton("Isolate Curves")
        self._isolate_btn.setCheckable(True)
        self._isolate_btn.setToolTip(
            "Toggle Curves > Isolate Curve Display. When ON, only the "
            "curves currently selected in the Graph Editor are visible; "
            "click again to restore the full view."
        )
        self._isolate_btn.toggled.connect(core.toggle_isolate_curves)

        grid.addWidget(self._show_selected_btn, 0, 0)
        grid.addWidget(self._show_all_btn,      0, 1)
        grid.addWidget(self._isolate_btn,       1, 0, 1, 2)

        # Row 2 — mute
        mute_btn = QtWidgets.QPushButton("Mute")
        mute_btn.setToolTip(
            "Mute every keyable channel on the selection (or the plugs "
            "driven by the selected curves). Muted channels ignore their "
            "animation while you scrub."
        )
        mute_btn.clicked.connect(core.mute_channels)

        unmute_btn = QtWidgets.QPushButton("Un-Mute")
        unmute_btn.setToolTip("Remove mute nodes from the selection so "
                              "animation plays back again.")
        unmute_btn.clicked.connect(core.unmute_channels)

        grid.addWidget(mute_btn,   2, 0)
        grid.addWidget(unmute_btn, 2, 1)

        # Row 3 — explicit Show/Hide Buffer Curves actions.
        self._show_buffer_btn = QtWidgets.QPushButton("Show Buffer Curves")
        self._show_buffer_btn.setToolTip(
            "Show existing buffer curves in the Graph Editor. "
            "Use Create Buffer Curves below to generate them."
        )
        self._show_buffer_btn.clicked.connect(core.show_buffer_curves)

        self._hide_buffer_btn = QtWidgets.QPushButton("Hide Buffer Curves")
        self._hide_buffer_btn.setToolTip(
            "Hide buffer curves in the Graph Editor while preserving them."
        )
        self._hide_buffer_btn.clicked.connect(core.hide_buffer_curves)

        # Row 4 — Create Buffer Curves (full width action button).
        create_buf_btn = QtWidgets.QPushButton("Create Buffer Curves")
        create_buf_btn.setToolTip(
            "Snapshot the current animation as buffer curves. Runs "
            "bufferCurve -animation keys -overwrite true on the "
            "selected object / keys."
        )
        create_buf_btn.clicked.connect(core.create_buffer_curves)

        # Row 5 — Use Referenced Curve | Swap Buffer Curves.
        use_ref_btn = QtWidgets.QPushButton("Use Referenced Curve")
        use_ref_btn.setToolTip(
            "Set the buffer curve to the referenced anim curve. Runs "
            "bufferCurve -useReferencedCurve — useful for comparing "
            "local edits against the original referenced animation."
        )
        use_ref_btn.clicked.connect(core.use_referenced_buffer_curve)

        swap_buf_btn = QtWidgets.QPushButton("Swap Buffer Curves")
        swap_buf_btn.setToolTip(
            "Swap the live curve with its buffer snapshot. Runs "
            "bufferCurve -animation keys -swap — a fast A/B compare "
            "between the original and the edit."
        )
        swap_buf_btn.clicked.connect(core.swap_buffer_curves)

        grid.addWidget(self._show_buffer_btn, 3, 0)
        grid.addWidget(self._hide_buffer_btn, 3, 1)
        grid.addWidget(create_buf_btn,        4, 0, 1, 2)
        grid.addWidget(use_ref_btn,           5, 0)
        grid.addWidget(swap_buf_btn,          5, 1)

        layout.addLayout(grid)
        return card

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _section_header(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("SectionHeader")
        return lbl

    def _helper(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("HelperText")
        lbl.setWordWrap(True)
        return lbl
