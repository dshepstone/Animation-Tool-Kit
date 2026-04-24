"""Add/Remove Inbetweens Maya tool.

This utility offers a compact Maya Qt window that helps animators quickly
insert or remove blocks of empty time, or fan selected keys onto an even
spacing, all while preserving animation spacing. The interface exposes:

* **Target & Range** – operate on selected controls or every animated curve in
  the scene, optionally constrained to the highlighted or playback range.
* **Amount** – choose how many frames to insert or remove using the spin box or
  the large arrow buttons.
* **Key Spacing (Ripple)** – adjust selected keys to match a target spacing
  interval (0=consecutive frames, 2=every other frame, etc.) while rippling
  downstream keys.
* **Apply & Safety** – re-run the most recent insert/remove operation, wrapped
  in a single undo step, with an optional auto-close toggle.
* **Help footer** – contextual guidance describing each control and workflow.

Usage notes:
    Select controls or choose "All keyed in scene". Set Frames. Click ▲ to
    insert or ▼ to remove. Optionally enable "Use Time Range" to operate on the
    highlighted or playback range with ripple. Use "Key Spacing (Ripple)" after
    selecting keys in the time slider to adjust them to a target spacing interval
    (e.g., 0 for consecutive frames, 2 for every other frame).
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


class InsertRemoveFramesUI(QtWidgets.QDialog):
    WINDOW_TITLE = "Add/Remove Inbetweens"
    MIN_WIDTH = 340

    def __init__(self, parent: Optional[QtWidget] = None) -> None:
        super().__init__(parent or _maya_main_window())
        self.setObjectName("InsertRemoveFramesUI")
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowIcon(_tool_icon("add_Remove.png"))
        self.setWindowFlag(QtCore.Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

        self._build_ui()
        self._restore_settings()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Target & Range
        target_group = QtWidgets.QGroupBox("Target && Range", self)
        target_layout = QtWidgets.QVBoxLayout(target_group)
        target_layout.setSpacing(6)

        self.selected_radio = QtWidgets.QRadioButton("Selected objects", target_group)
        self.scene_radio = QtWidgets.QRadioButton("All keyed in scene", target_group)
        target_layout.addWidget(self.selected_radio)
        target_layout.addWidget(self.scene_radio)

        self.range_checkbox = QtWidgets.QCheckBox("Use Time Range", target_group)
        target_layout.addWidget(self.range_checkbox)

        target_helper = QtWidgets.QLabel(
            "Choose the animation scope for insert/remove operations. "
            "Selected objects limits edits to highlighted controls; All keyed in "
            "scene processes every animated curve. Enable Use Time Range to operate "
            "on the time slider selection (or playback range) and ripple keys after it.",
            target_group,
        )
        target_helper.setWordWrap(True)
        target_font = target_helper.font()
        target_font.setPointSizeF(target_font.pointSizeF() - 1)
        target_helper.setFont(target_font)
        target_layout.addWidget(target_helper)

        main_layout.addWidget(target_group)

        # Amount section
        amount_group = QtWidgets.QGroupBox("Insert / Remove Frames", self)
        amount_layout = QtWidgets.QVBoxLayout(amount_group)
        amount_layout.setSpacing(8)

        frames_layout = QtWidgets.QHBoxLayout()
        frames_layout.setSpacing(6)
        frames_label = QtWidgets.QLabel("Frames:", amount_group)
        self.frames_spinbox = QtWidgets.QSpinBox(amount_group)
        self.frames_spinbox.setRange(1, 1000)
        self.frames_spinbox.setValue(1)
        self.frames_spinbox.setKeyboardTracking(False)
        self.frames_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.PlusMinus)
        frames_layout.addWidget(frames_label)
        frames_layout.addWidget(self.frames_spinbox, 1)
        amount_layout.addLayout(frames_layout)

        arrows_layout = QtWidgets.QHBoxLayout()
        arrows_layout.setSpacing(10)
        self.insert_button = QtWidgets.QPushButton("▲ Insert Frames", amount_group)
        self.insert_button.setMinimumHeight(36)
        self.insert_button.setToolTip(
            "Insert blank frames: pushes keys forward from current time or selected range."
        )
        self.remove_button = QtWidgets.QPushButton("▼ Remove Frames", amount_group)
        self.remove_button.setMinimumHeight(36)
        self.remove_button.setToolTip(
            "Remove frames: pulls keys backward from current time or selected range."
        )
        arrows_layout.addWidget(self.insert_button, 1)
        arrows_layout.addWidget(self.remove_button, 1)
        amount_layout.addLayout(arrows_layout)

        helper_label = QtWidgets.QLabel(
            "Insert shifts keys forward to create empty frames. Remove shifts keys "
            "backward to close gaps. The action starts at the current time, or uses "
            "the highlighted time range when Use Time Range is enabled.",
            amount_group,
        )
        helper_label.setWordWrap(True)
        font = helper_label.font()
        font.setPointSizeF(font.pointSizeF() - 1)
        helper_label.setFont(font)
        amount_layout.addWidget(helper_label)

        main_layout.addWidget(amount_group)

        # Key Spacing section
        inbetween_group = QtWidgets.QGroupBox("Key Spacing (Ripple)", self)
        inbetween_layout = QtWidgets.QVBoxLayout(inbetween_group)
        inbetween_layout.setSpacing(8)

        inbetween_row = QtWidgets.QHBoxLayout()
        inbetween_row.setSpacing(6)
        inbetween_label = QtWidgets.QLabel("Spacing Amount:", inbetween_group)
        self.inbetween_spinbox = QtWidgets.QSpinBox(inbetween_group)
        self.inbetween_spinbox.setRange(0, 1000)
        self.inbetween_spinbox.setValue(2)
        self.inbetween_spinbox.setKeyboardTracking(False)
        self.inbetween_spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.PlusMinus)
        inbetween_row.addWidget(inbetween_label)
        inbetween_row.addWidget(self.inbetween_spinbox, 1)
        inbetween_layout.addLayout(inbetween_row)

        self.apply_spacing_button = QtWidgets.QPushButton(
            "Apply Spacing", inbetween_group
        )
        self.apply_spacing_button.setMinimumHeight(32)
        self.apply_spacing_button.setToolTip(
            "Adjust selected keys to match the target spacing interval."
        )
        inbetween_layout.addWidget(self.apply_spacing_button)

        inbetween_helper = QtWidgets.QLabel(
            "Select keys in the time slider first. Apply Spacing redistributes the "
            "selected keys to the target interval and ripples later keys on those "
            "curves (0=consecutive, 2=every other frame, etc.).",
            inbetween_group,
        )
        inbetween_helper.setWordWrap(True)
        helper_font = inbetween_helper.font()
        helper_font.setPointSizeF(helper_font.pointSizeF() - 1)
        inbetween_helper.setFont(helper_font)
        inbetween_layout.addWidget(inbetween_helper)

        main_layout.addWidget(inbetween_group)

        # Footer help
        footer_layout = QtWidgets.QHBoxLayout()
        footer_layout.addStretch(1)
        self.help_button = QtWidgets.QToolButton(self)
        self.help_button.setText("?")
        self.help_button.setToolTip("About this tool")
        footer_layout.addWidget(self.help_button)
        main_layout.addLayout(footer_layout)

        self._create_shortcuts()
        self._connect_signals()

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
        self.help_button.clicked.connect(self._show_help)
        self.selected_radio.toggled.connect(self._save_settings)
        self.scene_radio.toggled.connect(self._save_settings)
        self.range_checkbox.toggled.connect(self._save_settings)
        self.frames_spinbox.valueChanged.connect(self._save_settings)
        self.inbetween_spinbox.valueChanged.connect(self._save_settings)

    # ---------------------------------------------------------------- logic
    def _restore_settings(self) -> None:
        mode = _get_option_var_string("mode", "selected")
        if mode == "scene":
            self.scene_radio.setChecked(True)
        else:
            self.selected_radio.setChecked(True)
        self.range_checkbox.setChecked(_get_option_var_bool("use_range", False))
        self.frames_spinbox.setValue(_get_option_var_int("frames", 1))
        self.inbetween_spinbox.setValue(_get_option_var_int("inbetweens", 2))

    def _save_settings(self) -> None:
        _set_option_var_string("mode", "scene" if self.scene_radio.isChecked() else "selected")
        _set_option_var_bool("use_range", self.range_checkbox.isChecked())
        _set_option_var_int("frames", self.frames_spinbox.value())
        _set_option_var_int("inbetweens", self.inbetween_spinbox.value())

    def _on_arrow_clicked(self, direction: int) -> None:
        self._apply_shift(direction)

    def _apply_shift(self, direction: int) -> None:
        self.frames_spinbox.interpretText()
        self.frames_spinbox.clearFocus()
        frames = self.frames_spinbox.value()
        mode = "scene" if self.scene_radio.isChecked() else "selected"
        use_range = self.range_checkbox.isChecked()

        curves = gather_anim_curves(mode)
        if not curves:
            if mode == "selected":
                _show_headsup("<span style='color:#ffaf00'>No keyed objects selected.</span>")
            else:
                _show_headsup("<span style='color:#ffaf00'>No animation curves found.</span>")
            return

        delta = frames * direction

        try:
            changed = shift_keys(curves, delta, use_range)
        except Exception as exc:  # pragma: no cover - Maya specific
            cmds.warning(f"Insert/Remove Blank Frames failed: {exc}")
            return

        if not changed:
            _show_headsup("<span style='color:#ffaf00'>No keys in the chosen scope/range.</span>")
            return

        self._save_settings()

        action = "Inserted" if direction > 0 else "Removed"
        _show_headsup(f"<span style='color:#a0ff7a'>{action} {frames} frame(s).</span>")

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
            return

        if not valid:
            _show_headsup(
                "<span style='color:#ffaf00'>Select at least two keyed frames to space.</span>"
            )
            return

        if not changed:
            _show_headsup(
                "<span style='color:#a0ff7a'>No keys were spaced.</span>"
            )
            return

        _set_option_var_int("inbetweens", spacing_amount)
        interval_desc = "consecutive frames" if spacing_amount == 0 else f"interval of {spacing_amount}"
        _show_headsup(
            f"<span style='color:#a0ff7a'>Applied spacing: {interval_desc}.</span>"
        )

    def _show_help(self) -> None:
        message = (
            "<b>Insert</b> shifts keys forward, creating blank space. "
            "<b>Remove</b> shifts keys backward, collapsing space.<br><br>"
            "<u>Controls</u><br>"
            "&bull; <b>Selected objects</b> limits edits to the highlighted DAG nodes.<br>"
            "&bull; <b>All keyed in scene</b> processes every anim curve in the file.<br>"
            "&bull; <b>Use Time Range</b> uses the time-slider highlight or playback range "
            "and ripples keys that follow it.<br>"
            "&bull; <b>Frames</b> sets how many frames to insert or remove.<br>"
            "&bull; <b>Insert/Remove Frames</b> buttons perform the operation immediately.<br>"
            "&bull; <b>Key Spacing (Ripple)</b> adjusts selected keys to match a target "
            "spacing interval (0=consecutive, 2=every other frame, etc.) while "
            "rippling later keys on those curves.<br><br>"
            "Keyboard shortcuts: Ctrl/Cmd+Up = Insert, Ctrl/Cmd+Down = Remove."
        )
        QtWidgets.QMessageBox.information(self, "Add/Remove Inbetweens", message)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)


_window: Optional[InsertRemoveFramesUI] = None


def show() -> InsertRemoveFramesUI:
    """Display the Add/Remove Inbetweens window."""

    global _window
    if _window is None or not _window.isVisible():
        _window = InsertRemoveFramesUI()
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window


__all__ = [
    "InsertRemoveFramesUI",
    "gather_anim_curves",
    "get_time_range",
    "shift_keys",
    "ripple_spacing_on_selected_keys",
    "show",
]
