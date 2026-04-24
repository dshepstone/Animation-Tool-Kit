"""Add/Remove Inbetweens Maya tool.

A compact, dockable Maya tool that helps animators insert or remove blocks of
empty time, or fan selected keys onto an even spacing, all while preserving
animation spacing. The interface is hosted inside a Maya ``workspaceControl``
so it can float or be docked anywhere in the Maya UI, and features a top-level
menu bar exposing an HTML-based Help/How To window.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Type, TypeVar

from maya import cmds, mel  # type: ignore[import-not-found]  # pylint: disable=import-error
from maya import OpenMayaUI as omui  # type: ignore[import-not-found]  # pylint: disable=import-error

def _import_qt_modules() -> Tuple[object, object, object, object]:
    """Resolve the Qt bindings bundled with the current Maya session.

    Maya 2025+ ships with PySide6/shiboken6 while earlier releases expose
    PySide2/shiboken2. The helper tries a variety of permutations so the tool
    can run regardless of the active DCC version, returning the QtCore,
    QtGui, QtWidgets modules and the shiboken package used to wrap native
    pointers.
    """

    # Maya 2025+ ships PySide6 by default, but older versions still use
    # PySide2/shiboken2. Try PySide6 combinations first so environments without
    # PySide2 import cleanly.
    binding_attempts = (
        ("PySide6", "shiboken6"),
        ("PySide6", "shiboken2"),
        ("PySide2", "shiboken2"),
        ("PySide2", "shiboken6"),
    )

    last_error: Optional[Exception] = None
    for qt_mod_name, shiboken_name in binding_attempts:
        try:
            qt_mod = __import__(qt_mod_name, fromlist=["QtCore", "QtGui", "QtWidgets"])
            shiboken_mod = __import__(shiboken_name)
        except ImportError as exc:  # pragma: no cover - environment specific
            last_error = exc
            continue

        try:
            qt_core = getattr(qt_mod, "QtCore")
            qt_gui = getattr(qt_mod, "QtGui")
            qt_widgets = getattr(qt_mod, "QtWidgets")
        except AttributeError as exc:  # pragma: no cover - unexpected binding
            last_error = exc
            continue

        return qt_core, qt_gui, qt_widgets, shiboken_mod

    raise ImportError(
        "Insert / Remove Blank Frames requires PySide2/PySide6 with shiboken"
    ) from last_error


QtCore, QtGui, QtWidgets, _shiboken = _import_qt_modules()

QtWidget = TypeVar("QtWidget", bound=Any)

_QShortcut = getattr(QtGui, "QShortcut", None)
if _QShortcut is None:
    _QShortcut = getattr(QtWidgets, "QShortcut", None)
if _QShortcut is None:
    raise AttributeError("Qt bindings missing QShortcut class.")


def _wrap_instance(ptr: int, base: Type[QtWidget]) -> QtWidget:
    """Compatibly wrap an ``MQtUtil`` pointer using whichever shiboken is loaded."""

    return _shiboken.wrapInstance(int(ptr), base)


OPTION_PREFIX = "irft_option_"
ANIM_CURVE_TYPES = (
    "animCurveTL",
    "animCurveTA",
    "animCurveTT",
    "animCurveTU",
    "animCurveML",
    "animCurveMA",
    "animCurveMT",
    "animCurveMU",
)


def _maya_main_window() -> QtWidget:
    """Return Maya's main window wrapped as a Qt widget for parenting dialogs."""

    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        raise RuntimeError("Unable to locate Maya main window.")
    return _wrap_instance(int(ptr), QtWidgets.QWidget)


def _tool_icon(icon_name: str) -> "QtGui.QIcon":
    """Resolve a tool icon from Maya prefs or the packaged script folder."""

    candidate_paths = [
        os.path.join(cmds.internalVar(userBitmapsDir=True), icon_name),
        os.path.join(cmds.internalVar(userPrefDir=True), "icons", icon_name),
        os.path.join(os.path.dirname(__file__), icon_name),
    ]

    for icon_path in candidate_paths:
        if not os.path.exists(icon_path):
            continue
        icon = QtGui.QIcon(icon_path)
        if not icon.isNull():
            return icon
    return QtGui.QIcon()


def _option_var_name(key: str) -> str:
    return f"{OPTION_PREFIX}{key}"


def _get_option_var_bool(key: str, default: bool) -> bool:
    name = _option_var_name(key)
    if cmds.optionVar(exists=name):
        return bool(cmds.optionVar(q=name))
    cmds.optionVar(iv=(name, int(default)))
    return default


def _set_option_var_bool(key: str, value: bool) -> None:
    cmds.optionVar(iv=(_option_var_name(key), int(value)))


def _get_option_var_int(key: str, default: int) -> int:
    name = _option_var_name(key)
    if cmds.optionVar(exists=name):
        return int(cmds.optionVar(q=name))
    cmds.optionVar(iv=(name, int(default)))
    return default


def _set_option_var_int(key: str, value: int) -> None:
    cmds.optionVar(iv=(_option_var_name(key), int(value)))


def _get_option_var_string(key: str, default: str) -> str:
    name = _option_var_name(key)
    if cmds.optionVar(exists=name):
        return cmds.optionVar(q=name)
    cmds.optionVar(sv=(name, default))
    return default


def _set_option_var_string(key: str, value: str) -> None:
    cmds.optionVar(sv=(_option_var_name(key), value))


def _show_headsup(message: str) -> None:
    """Display a non-blocking feedback message, falling back to ``cmds.warning``."""
    try:
        cmds.inViewMessage(amg=message, pos="midCenter", fade=True)
    except RuntimeError:
        cmds.warning(message)


def _gather_anim_curves_selected() -> List[str]:
    """Collect anim curves connected to keyed attributes on the current selection."""
    selection = cmds.ls(selection=True) or []
    if not selection:
        return []

    curves: List[str] = []
    for node in selection:
        try:
            names = cmds.keyframe(node, query=True, name=True) or []
        except RuntimeError:
            names = []
        for curve in names:
            if curve and curve not in curves:
                curves.append(curve)
    return curves


def _gather_anim_curves_scene() -> List[str]:
    """Collect every anim curve node in the open scene, deduplicated."""
    curves: List[str] = []
    for curve_type in ANIM_CURVE_TYPES:
        curves.extend(cmds.ls(type=curve_type) or [])
    # Deduplicate while preserving order.
    seen = set()
    unique: List[str] = []
    for curve in curves:
        if curve not in seen:
            seen.add(curve)
            unique.append(curve)
    return unique


def gather_anim_curves(mode: str) -> List[str]:
    """Return animation curves for the requested scope.

    Args:
        mode: Either ``"selected"`` to target the current selection or
            ``"scene"`` to gather every animCurve in the file.

    Returns:
        A unique list of anim curve node names suitable for ``cmds.keyframe``.
    """

    if mode == "scene":
        return _gather_anim_curves_scene()
    return _gather_anim_curves_selected()


def get_time_range(use_range: bool) -> Tuple[float, float]:
    """Return the active time range used for shifting keys.

    When ``use_range`` is False the range collapses to the current time. When
    True the function honours the time-slider highlight if one exists, falling
    back to the playback range otherwise.
    """

    current = cmds.currentTime(query=True)
    if not use_range:
        return current, current

    range_start = cmds.playbackOptions(query=True, min=True)
    range_end = cmds.playbackOptions(query=True, max=True)
    try:
        slider = mel.eval("$tmp = $gPlayBackSlider")
        if cmds.timeControl(slider, query=True, rangeVisible=True):
            range_values = cmds.timeControl(slider, query=True, rangeArray=True)
            if range_values and len(range_values) == 2:
                range_start, range_end = range_values
    except Exception:
        pass

    if range_start > range_end:
        range_start, range_end = range_end, range_start
    return range_start, range_end


def _time_slider_range() -> Optional[Tuple[float, float]]:
    try:
        slider = mel.eval("$tmp = $gPlayBackSlider")
        if not cmds.timeControl(slider, query=True, rangeVisible=True):
            return None
        range_values = cmds.timeControl(slider, query=True, rangeArray=True)
    except RuntimeError:
        return None

    if not range_values or len(range_values) != 2:
        return None

    start, end = range_values
    if start > end:
        start, end = end, start
    return start, end


def _selected_key_times() -> List[float]:
    try:
        values = cmds.keyframe(query=True, selected=True, timeChange=True) or []
    except RuntimeError:
        return []
    return [float(value) for value in values]


def _as_time_set(times: Sequence[float]) -> Set[float]:
    return {round(time, 6) for time in times}


def _has_keys_in_range(curves: Sequence[str], start: float, end: float) -> bool:
    for curve in curves:
        try:
            keys = cmds.keyframe(curve, query=True, time=(start, end)) or []
        except RuntimeError:
            continue
        if keys:
            return True
    return False


def _mel_shift(curves: Sequence[str], start: float, end: Optional[float], delta: int) -> None:
    time_range = f"{start}:{end}" if end is not None else f"{start}:"
    curve_args = " ".join(f"\"{curve}\"" for curve in curves)
    mel.eval(
        f"keyframe -edit -relative -timeChange {delta} -time \"{time_range}\" -option over {curve_args};"
    )


def shift_keys(curves: Sequence[str], delta: int, use_range: bool) -> bool:
    """Shift keys on curves by ``delta`` frames respecting the chosen range.

    The function wraps all edits inside a single undo chunk, honours the
    selected/current time logic, and performs a ripple shift when a time range
    is supplied so downstream keys maintain spacing. It uses Maya's keyframe
    edit command to apply the shift from the time slider.
    """

    if not curves:
        return False
    if delta == 0:
        return False

    current = cmds.currentTime(query=True)

    cmds.undoInfo(openChunk=True)
    any_shifted = False
    try:
        if use_range:
            start, end = get_time_range(True)
            if _has_keys_in_range(curves, start, end):
                _mel_shift(curves, start, end, delta)
                any_shifted = True
            ripple_start = end + 0.001
            if _has_keys_in_range(curves, ripple_start, 1000000):
                _mel_shift(curves, ripple_start, None, delta)
                any_shifted = True
        else:
            insert_at = current + 1
            if _has_keys_in_range(curves, insert_at, 1000000):
                _mel_shift(curves, insert_at, None, delta)
                any_shifted = True
    finally:
        cmds.undoInfo(closeChunk=True)

    return any_shifted


def ripple_spacing_on_selected_keys(
    amount: int,
    direction: int,
) -> Tuple[bool, bool]:
    """Set the spacing between highlighted keys to a target value.

    Args:
        amount: Target spacing interval between keys. 0 means consecutive frames,
                2 means keys at frames 1, 3, 5, 7 (interval of 2), etc.
        direction: Kept for backward compatibility, but ignored in current implementation.

    Returns:
        Tuple of (valid, changed) where valid indicates the operation was valid
        and changed indicates whether any keys were actually modified.
    """

    if amount < 0:
        raise ValueError("Spacing amount must be zero or greater.")

    slider_range = _time_slider_range()
    selection = cmds.ls(selection=True) or []
    curve_candidates = []

    for node in selection:
        try:
            names = cmds.keyframe(node, query=True, name=True) or []
            curve_candidates.extend(names)
        except RuntimeError:
            continue

    filtered_curves = [
        curve
        for curve in set(curve_candidates)
        if cmds.objExists(curve) and cmds.nodeType(curve) in ANIM_CURVE_TYPES
    ]
    if not filtered_curves:
        return False, False

    # Determine the interval between keys based on spacing amount
    # spacing=0 means consecutive frames (interval=1)
    # spacing=n (n>0) means interval=n
    interval = max(amount, 1)

    changed = False
    cmds.undoInfo(openChunk=True)
    try:
        for curve in filtered_curves:
            times = (
                cmds.keyframe(curve, query=True, time=slider_range)
                if slider_range
                else cmds.keyframe(curve, query=True, selected=True)
            )
            if not times or len(times) < 2:
                continue

            times = sorted(set(times))

            # Keep first key fixed (anchor point)
            # For each subsequent key, calculate where it should be based on target spacing
            previous_expected_time = times[0]

            for index in range(1, len(times)):
                current_key_time = times[index]
                expected_time = previous_expected_time + interval
                delta = expected_time - current_key_time

                if delta != 0:
                    # Move this key and all downstream keys by delta
                    cmds.keyframe(
                        curve,
                        edit=True,
                        time=(current_key_time, 1000000),
                        relative=True,
                        timeChange=delta,
                    )
                    changed = True
                    # Update times list to reflect the change for subsequent iterations
                    for j in range(index, len(times)):
                        times[j] += delta

                previous_expected_time = expected_time
    finally:
        cmds.undoInfo(closeChunk=True)

    return True, changed


WORKSPACE_CONTROL_NAME = "InsertRemoveFramesWorkspaceControl"
# ``workspaceControl -uiScript`` is evaluated in the same language context
# that created the control. We register it from Python via ``cmds``, so the
# script runs as Python — no ``python("...")`` MEL wrapper.
WORKSPACE_CONTROL_UI_SCRIPT = (
    "import insert_remove_frames_tool as irft; "
    "irft._restore_workspace_control()"
)


MODERN_STYLE = """
QWidget#InsertRemoveFramesUI {
    background: palette(window);
}
QFrame#Card {
    background: palette(base);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
}
QLabel#SectionTitle {
    font-weight: 600;
    letter-spacing: 0.3px;
    color: palette(bright-text);
    padding: 0px;
}
QLabel#SectionHint {
    color: rgba(200, 200, 200, 160);
}
QPushButton#PrimaryAction {
    background: #4a6fa5;
    color: white;
    border: 1px solid #365684;
    border-radius: 4px;
    padding: 6px 10px;
    font-weight: 600;
}
QPushButton#PrimaryAction:hover { background: #5a82bc; }
QPushButton#PrimaryAction:pressed { background: #3d5d8c; }
QPushButton#DangerAction {
    background: #a5533a;
    color: white;
    border: 1px solid #7d3e2c;
    border-radius: 4px;
    padding: 6px 10px;
    font-weight: 600;
}
QPushButton#DangerAction:hover { background: #bd6349; }
QPushButton#DangerAction:pressed { background: #8a432e; }
QPushButton#AccentAction {
    background: #3d8b6a;
    color: white;
    border: 1px solid #2d6750;
    border-radius: 4px;
    padding: 6px 10px;
    font-weight: 600;
}
QPushButton#AccentAction:hover { background: #4ba57f; }
QPushButton#AccentAction:pressed { background: #306e54; }
QToolButton#SegmentButton {
    padding: 4px 10px;
    border: 1px solid rgba(255,255,255,35);
    background: palette(button);
}
QToolButton#SegmentButton:checked {
    background: #4a6fa5;
    color: white;
    border: 1px solid #365684;
}
QSpinBox { padding: 3px 4px; }
"""


class InsertRemoveFramesUI(QtWidgets.QWidget):
    """Modern, compact UI for the Add/Remove Inbetweens tool.

    Designed to sit inside a Maya ``workspaceControl`` so it can float freely
    or be docked alongside any other Maya panel. All verbose guidance has been
    moved out of the panel itself and into a Help menu that opens an HTML
    How To window, keeping the tool window tight and unobtrusive.
    """

    WINDOW_TITLE = "Add/Remove Inbetweens"
    MIN_WIDTH = 280

    def __init__(self, parent: Optional[QtWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("InsertRemoveFramesUI")
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowIcon(_tool_icon("add_Remove.png"))
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setStyleSheet(MODERN_STYLE)
        self._help_dialog: Optional[QtWidgets.QDialog] = None

        self._build_ui()
        self._restore_settings()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_menu_bar(main_layout)

        content = QtWidgets.QWidget(self)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(8, 6, 8, 8)
        content_layout.setSpacing(8)

        content_layout.addWidget(self._build_target_card())
        content_layout.addWidget(self._build_frames_card())
        content_layout.addWidget(self._build_spacing_card())

        self.status_label = QtWidgets.QLabel("", content)
        self.status_label.setObjectName("SectionHint")
        status_font = self.status_label.font()
        status_font.setPointSizeF(status_font.pointSizeF() - 1)
        self.status_label.setFont(status_font)
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        content_layout.addWidget(self.status_label)

        content_layout.addStretch(1)

        main_layout.addWidget(content)

        self._create_shortcuts()
        self._connect_signals()

    def _build_menu_bar(self, main_layout: QtWidgets.QVBoxLayout) -> None:
        self.menu_bar = QtWidgets.QMenuBar(self)
        self.menu_bar.setNativeMenuBar(False)

        edit_menu = self.menu_bar.addMenu("Tools")
        self.reset_action = edit_menu.addAction("Reset to Defaults")

        help_menu = self.menu_bar.addMenu("Help")
        self.how_to_action = help_menu.addAction("How To...")
        self.shortcuts_action = help_menu.addAction("Keyboard Shortcuts")
        help_menu.addSeparator()
        self.about_action = help_menu.addAction("About")

        main_layout.setMenuBar(self.menu_bar)

    def _build_card(self, title: str) -> Tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
        card = QtWidgets.QFrame(self)
        card.setObjectName("Card")
        card.setFrameShape(QtWidgets.QFrame.StyledPanel)

        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 8)
        card_layout.setSpacing(6)

        title_label = QtWidgets.QLabel(title, card)
        title_label.setObjectName("SectionTitle")
        card_layout.addWidget(title_label)
        return card, card_layout

    def _build_target_card(self) -> QtWidgets.QFrame:
        card, layout = self._build_card("Scope")

        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setSpacing(0)
        self.mode_group = QtWidgets.QButtonGroup(card)
        self.mode_group.setExclusive(True)

        self.selected_button = QtWidgets.QToolButton(card)
        self.selected_button.setObjectName("SegmentButton")
        self.selected_button.setText("Selected")
        self.selected_button.setCheckable(True)
        self.selected_button.setToolTip("Operate on anim curves of selected objects.")
        self.selected_button.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )

        self.scene_button = QtWidgets.QToolButton(card)
        self.scene_button.setObjectName("SegmentButton")
        self.scene_button.setText("All Keyed")
        self.scene_button.setCheckable(True)
        self.scene_button.setToolTip("Operate on every animated curve in the scene.")
        self.scene_button.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )

        self.mode_group.addButton(self.selected_button, 0)
        self.mode_group.addButton(self.scene_button, 1)
        mode_row.addWidget(self.selected_button)
        mode_row.addWidget(self.scene_button)
        layout.addLayout(mode_row)

        self.range_checkbox = QtWidgets.QCheckBox("Use Time Range (ripple)", card)
        self.range_checkbox.setToolTip(
            "Operate on the time-slider highlight (or playback range) and\n"
            "ripple later keys so spacing is preserved."
        )
        layout.addWidget(self.range_checkbox)

        return card

    def _build_frames_card(self) -> QtWidgets.QFrame:
        card, layout = self._build_card("Insert / Remove Frames")

        frames_row = QtWidgets.QHBoxLayout()
        frames_row.setSpacing(6)
        frames_label = QtWidgets.QLabel("Frames", card)
        self.frames_spinbox = QtWidgets.QSpinBox(card)
        self.frames_spinbox.setRange(1, 1000)
        self.frames_spinbox.setValue(1)
        self.frames_spinbox.setKeyboardTracking(False)
        self.frames_spinbox.setAlignment(QtCore.Qt.AlignRight)
        self.frames_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.PlusMinus)
        frames_row.addWidget(frames_label)
        frames_row.addWidget(self.frames_spinbox, 1)
        layout.addLayout(frames_row)

        buttons_row = QtWidgets.QHBoxLayout()
        buttons_row.setSpacing(6)
        self.remove_button = QtWidgets.QPushButton("▼  Remove", card)
        self.remove_button.setObjectName("DangerAction")
        self.remove_button.setMinimumHeight(30)
        self.remove_button.setToolTip(
            "Shift keys backward (Ctrl/Cmd+↓)."
        )
        self.insert_button = QtWidgets.QPushButton("▲  Insert", card)
        self.insert_button.setObjectName("PrimaryAction")
        self.insert_button.setMinimumHeight(30)
        self.insert_button.setToolTip(
            "Shift keys forward to create blank frames (Ctrl/Cmd+↑)."
        )
        buttons_row.addWidget(self.remove_button, 1)
        buttons_row.addWidget(self.insert_button, 1)
        layout.addLayout(buttons_row)

        return card

    def _build_spacing_card(self) -> QtWidgets.QFrame:
        card, layout = self._build_card("Key Spacing (Ripple)")

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(QtWidgets.QLabel("Spacing", card))

        self.inbetween_spinbox = QtWidgets.QSpinBox(card)
        self.inbetween_spinbox.setRange(0, 1000)
        self.inbetween_spinbox.setValue(2)
        self.inbetween_spinbox.setKeyboardTracking(False)
        self.inbetween_spinbox.setAlignment(QtCore.Qt.AlignRight)
        self.inbetween_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.PlusMinus)
        self.inbetween_spinbox.setToolTip(
            "0 = consecutive frames, 2 = every other frame, etc."
        )
        row.addWidget(self.inbetween_spinbox, 1)

        self.apply_spacing_button = QtWidgets.QPushButton("Apply", card)
        self.apply_spacing_button.setObjectName("AccentAction")
        self.apply_spacing_button.setMinimumHeight(26)
        self.apply_spacing_button.setToolTip(
            "Redistribute selected keys to match the target spacing interval."
        )
        row.addWidget(self.apply_spacing_button)
        layout.addLayout(row)

        return card

    def _create_shortcuts(self) -> None:
        for sequence, direction in (("Ctrl+Up", 1), ("Meta+Up", 1), ("Ctrl+Down", -1), ("Meta+Down", -1)):
            shortcut = _QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.activated.connect(lambda _checked=False, d=direction: self._on_arrow_clicked(d))

    def _connect_signals(self) -> None:
        self.insert_button.clicked.connect(lambda: self._on_arrow_clicked(1))
        self.remove_button.clicked.connect(lambda: self._on_arrow_clicked(-1))
        self.apply_spacing_button.clicked.connect(
            lambda: self._on_ripple_spacing_clicked(1)
        )
        self.how_to_action.triggered.connect(self._show_how_to)
        self.shortcuts_action.triggered.connect(self._show_shortcuts)
        self.about_action.triggered.connect(self._show_about)
        self.reset_action.triggered.connect(self._reset_defaults)
        self.mode_group.buttonToggled.connect(lambda *_: self._save_settings())
        self.range_checkbox.toggled.connect(self._save_settings)
        self.frames_spinbox.valueChanged.connect(self._save_settings)
        self.inbetween_spinbox.valueChanged.connect(self._save_settings)

    # ------------------------------------------------------------- helpers
    def _is_scene_mode(self) -> bool:
        return self.scene_button.isChecked()

    # ---------------------------------------------------------------- logic
    def _restore_settings(self) -> None:
        mode = _get_option_var_string("mode", "selected")
        if mode == "scene":
            self.scene_button.setChecked(True)
        else:
            self.selected_button.setChecked(True)
        self.range_checkbox.setChecked(_get_option_var_bool("use_range", False))
        self.frames_spinbox.setValue(_get_option_var_int("frames", 1))
        self.inbetween_spinbox.setValue(_get_option_var_int("inbetweens", 2))

    def _save_settings(self) -> None:
        _set_option_var_string("mode", "scene" if self._is_scene_mode() else "selected")
        _set_option_var_bool("use_range", self.range_checkbox.isChecked())
        _set_option_var_int("frames", self.frames_spinbox.value())
        _set_option_var_int("inbetweens", self.inbetween_spinbox.value())

    def _reset_defaults(self) -> None:
        self.selected_button.setChecked(True)
        self.range_checkbox.setChecked(False)
        self.frames_spinbox.setValue(1)
        self.inbetween_spinbox.setValue(2)
        self._save_settings()
        self._set_status("Defaults restored.", ok=True)

    def _set_status(self, message: str, ok: bool = True) -> None:
        color = "#a0ff7a" if ok else "#ffaf00"
        self.status_label.setText(
            f"<span style='color:{color}'>{message}</span>"
        )

    def _on_arrow_clicked(self, direction: int) -> None:
        self._apply_shift(direction)

    def _apply_shift(self, direction: int) -> None:
        self.frames_spinbox.interpretText()
        self.frames_spinbox.clearFocus()
        frames = self.frames_spinbox.value()
        mode = "scene" if self._is_scene_mode() else "selected"
        use_range = self.range_checkbox.isChecked()

        curves = gather_anim_curves(mode)
        if not curves:
            warning = (
                "No keyed objects selected."
                if mode == "selected"
                else "No animation curves found."
            )
            _show_headsup(f"<span style='color:#ffaf00'>{warning}</span>")
            self._set_status(warning, ok=False)
            return

        delta = frames * direction

        try:
            changed = shift_keys(curves, delta, use_range)
        except Exception as exc:  # pragma: no cover - Maya specific
            cmds.warning(f"Insert/Remove Blank Frames failed: {exc}")
            self._set_status(f"Error: {exc}", ok=False)
            return

        if not changed:
            warning = "No keys in the chosen scope/range."
            _show_headsup(f"<span style='color:#ffaf00'>{warning}</span>")
            self._set_status(warning, ok=False)
            return

        self._save_settings()

        action = "Inserted" if direction > 0 else "Removed"
        message = f"{action} {frames} frame(s)."
        _show_headsup(f"<span style='color:#a0ff7a'>{message}</span>")
        self._set_status(message, ok=True)

    def _on_ripple_spacing_clicked(self, direction: int) -> None:
        self.inbetween_spinbox.interpretText()
        self.inbetween_spinbox.clearFocus()
        spacing_amount = self.inbetween_spinbox.value()

        try:
            valid, changed = ripple_spacing_on_selected_keys(
                spacing_amount,
                direction,
            )
        except Exception as exc:  # pragma: no cover - Maya specific
            cmds.warning(f"Key Spacing failed: {exc}")
            self._set_status(f"Error: {exc}", ok=False)
            return

        if not valid:
            warning = "Select at least two keyed frames to space."
            _show_headsup(f"<span style='color:#ffaf00'>{warning}</span>")
            self._set_status(warning, ok=False)
            return

        if not changed:
            note = "No keys needed spacing."
            _show_headsup(f"<span style='color:#a0ff7a'>{note}</span>")
            self._set_status(note, ok=True)
            return

        _set_option_var_int("inbetweens", spacing_amount)
        interval_desc = (
            "consecutive frames" if spacing_amount == 0 else f"interval of {spacing_amount}"
        )
        message = f"Applied spacing: {interval_desc}."
        _show_headsup(f"<span style='color:#a0ff7a'>{message}</span>")
        self._set_status(message, ok=True)

    # ------------------------------------------------------------- help UI
    def _show_how_to(self) -> None:
        self._open_help_dialog("How To", _HOW_TO_HTML)

    def _show_shortcuts(self) -> None:
        self._open_help_dialog("Keyboard Shortcuts", _SHORTCUTS_HTML)

    def _show_about(self) -> None:
        self._open_help_dialog("About", _ABOUT_HTML)

    def _open_help_dialog(self, title: str, html: str) -> None:
        if self._help_dialog is None:
            self._help_dialog = _HelpDialog(self)
        self._help_dialog.set_content(title, html)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    # ------------------------------------------------------------------ qt
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._save_settings()
        if self._help_dialog is not None:
            self._help_dialog.close()
        super().closeEvent(event)


class _HelpDialog(QtWidgets.QDialog):
    """HTML Help window with a sidebar of sections."""

    def __init__(self, parent: Optional[QtWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add/Remove Inbetweens — Help")
        self.setMinimumSize(520, 420)
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.section_list = QtWidgets.QListWidget(self)
        self.section_list.setFixedWidth(140)
        self.section_list.addItem("How To")
        self.section_list.addItem("Keyboard Shortcuts")
        self.section_list.addItem("About")

        self.text_view = QtWidgets.QTextBrowser(self)
        self.text_view.setOpenExternalLinks(True)

        layout.addWidget(self.section_list)
        layout.addWidget(self.text_view, 1)

        self.section_list.currentRowChanged.connect(self._on_section_changed)

    def _on_section_changed(self, row: int) -> None:
        if row == 0:
            self.text_view.setHtml(_HOW_TO_HTML)
        elif row == 1:
            self.text_view.setHtml(_SHORTCUTS_HTML)
        elif row == 2:
            self.text_view.setHtml(_ABOUT_HTML)

    def set_content(self, title: str, html: str) -> None:
        self.setWindowTitle(f"Add/Remove Inbetweens — {title}")
        mapping = {"How To": 0, "Keyboard Shortcuts": 1, "About": 2}
        row = mapping.get(title, 0)
        self.section_list.blockSignals(True)
        self.section_list.setCurrentRow(row)
        self.section_list.blockSignals(False)
        self.text_view.setHtml(html)


_HOW_TO_HTML = """
<html><body style="font-family: sans-serif; line-height: 1.5;">
<h2 style="margin-top:0;">How To Use</h2>
<p>The <b>Add/Remove Inbetweens</b> tool lets you insert or remove blocks of
empty time and redistribute keys onto an even spacing &mdash; without losing
tangents or breaking the shape of your curves.</p>

<h3>1. Insert or Remove Frames</h3>
<ol>
  <li>Pick a <b>Scope</b>:
    <ul>
      <li><b>Selected</b> &mdash; only anim curves on the selected controls.</li>
      <li><b>All Keyed</b> &mdash; every animated curve in the scene.</li>
    </ul>
  </li>
  <li>Optionally enable <b>Use Time Range (ripple)</b> to operate on the
      highlighted time-slider range (or playback range) and ripple later keys
      so downstream spacing is preserved.</li>
  <li>Enter the number of <b>Frames</b>.</li>
  <li>Click <b style="color:#5a82bc;">&#9650; Insert</b> to push keys forward
      or <b style="color:#bd6349;">&#9660; Remove</b> to pull them back.</li>
</ol>

<h3>2. Key Spacing (Ripple)</h3>
<ol>
  <li>Select the frames you want to re-space in Maya&rsquo;s time slider.</li>
  <li>Set <b>Spacing</b>:
    <ul>
      <li><code>0</code> &mdash; keys on consecutive frames.</li>
      <li><code>2</code> &mdash; every other frame.</li>
      <li><code>n</code> &mdash; interval of <code>n</code> frames between keys.</li>
    </ul>
  </li>
  <li>Click <b style="color:#4ba57f;">Apply</b>. Later keys on the same curves
      ripple to preserve timing.</li>
</ol>

<h3>Tips</h3>
<ul>
  <li>Every operation is a single undo step (<code>Ctrl/Cmd+Z</code>).</li>
  <li>Tangents and curve shapes are preserved; locked channels are skipped.</li>
  <li>The panel can be docked into Maya&rsquo;s interface &mdash; drag the
      title bar onto any dock area.</li>
</ul>
</body></html>
"""

_SHORTCUTS_HTML = """
<html><body style="font-family: sans-serif; line-height: 1.6;">
<h2 style="margin-top:0;">Keyboard Shortcuts</h2>
<table cellpadding="6" style="border-collapse:collapse;">
  <tr><td><b>Ctrl + &#8593;</b> &nbsp;/&nbsp; <b>Cmd + &#8593;</b></td>
      <td>Insert frames</td></tr>
  <tr><td><b>Ctrl + &#8595;</b> &nbsp;/&nbsp; <b>Cmd + &#8595;</b></td>
      <td>Remove frames</td></tr>
  <tr><td><b>Ctrl + Z</b> &nbsp;/&nbsp; <b>Cmd + Z</b></td>
      <td>Undo the last insert / remove / spacing operation</td></tr>
</table>
<p>All shortcuts work whenever the tool window or any of its widgets have
keyboard focus.</p>
</body></html>
"""

_ABOUT_HTML = """
<html><body style="font-family: sans-serif; line-height: 1.5;">
<h2 style="margin-top:0;">About</h2>
<p><b>Add/Remove Inbetweens</b> &mdash; a compact, dockable Maya tool that
helps animators retime shots by inserting blank frames, removing frames,
or fanning keys onto an even spacing.</p>
<p>Created by <b>David Shepstone</b>.</p>
<p>Compatible with Maya 2020 &ndash; 2026+, on Windows, macOS and Linux.</p>
</body></html>
"""


def _restore_workspace_control() -> None:
    """Rebuild the UI inside the existing workspaceControl on session restore."""

    global _window
    _window = InsertRemoveFramesUI()

    workspace_ptr = omui.MQtUtil.findControl(WORKSPACE_CONTROL_NAME)
    if workspace_ptr is None:
        return

    workspace_widget = _wrap_instance(int(workspace_ptr), QtWidgets.QWidget)
    layout = workspace_widget.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(workspace_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
    layout.addWidget(_window)


_window: Optional[InsertRemoveFramesUI] = None


def show() -> InsertRemoveFramesUI:
    """Display the Add/Remove Inbetweens window inside a Maya workspaceControl.

    Using ``workspaceControl`` means the panel can be freely floated, docked,
    tabbed with other panels, and is automatically restored by Maya on the
    next session via the registered ``uiScript``. Any existing control (even
    a broken/empty one left over from a prior failed load) is deleted first
    to guarantee the UI always rebuilds cleanly.
    """

    if cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
        try:
            cmds.deleteUI(WORKSPACE_CONTROL_NAME, control=True)
        except RuntimeError:
            pass

    cmds.workspaceControl(
        WORKSPACE_CONTROL_NAME,
        label=InsertRemoveFramesUI.WINDOW_TITLE,
        retain=False,
        floating=True,
        initialWidth=320,
        initialHeight=380,
        minimumWidth=InsertRemoveFramesUI.MIN_WIDTH,
        uiScript=WORKSPACE_CONTROL_UI_SCRIPT,
    )

    # Defensive fallback: if Maya somehow didn't run the uiScript (rare, but
    # can happen if the module was renamed), build the UI manually.
    if _window is None:
        _restore_workspace_control()

    return _window  # type: ignore[return-value]


__all__ = [
    "InsertRemoveFramesUI",
    "gather_anim_curves",
    "get_time_range",
    "shift_keys",
    "ripple_spacing_on_selected_keys",
    "show",
]
