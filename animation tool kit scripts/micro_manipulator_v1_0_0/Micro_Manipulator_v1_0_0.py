"""
╔══════════════════════════════════════════════════════════════╗
║     MICRO MANIPULATOR TOOL v1.0.0                            ║
║  Refined UI based on design annotations. Redundant tool      ║
║  buttons removed, tab highlighting enhanced, and smart       ║
║  gizmo toggling implemented.                                 ║
╚══════════════════════════════════════════════════════════════╝
"""

import maya.cmds as cmds
import maya.OpenMayaUI as omui
from PySide6 import QtWidgets, QtCore
from shiboken6 import wrapInstance

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

WINDOW_OBJECT = "microManipulatorWin"
WINDOW_TITLE  = "Micro Manipulator Tool v1.0.0"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None: return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)

# ──────────────────────────────────────────────────────────────────────────────
# Infinite Scrubber Widget
# ──────────────────────────────────────────────────────────────────────────────

class InfiniteScrubber(QtWidgets.QSlider):
    scrub_started = QtCore.Signal()
    scrub_moved = QtCore.Signal(float) 
    scrub_ended = QtCore.Signal()

    def __init__(self, parent=None):
        super(InfiniteScrubber, self).__init__(QtCore.Qt.Horizontal, parent)
        self.setRange(-1000, 1000)
        self.setValue(0)
        self.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.setTickInterval(250)
        
        self.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #222; height: 8px; background: #333; border-radius: 4px; }
            QSlider::handle:horizontal { background: #55aaff; border: 1px solid #111; width: 18px; margin: -5px 0; border-radius: 9px; }
            QSlider::handle:horizontal:pressed { background: #4CAF50; }
        """)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.scrub_started.emit()
        super(InfiniteScrubber, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super(InfiniteScrubber, self).mouseMoveEvent(event)
        if self.isSliderDown():
            self.scrub_moved.emit(float(self.value()))

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.scrub_ended.emit()
            self.blockSignals(True)
            self.setValue(0)
            self.blockSignals(False)
        super(InfiniteScrubber, self).mouseReleaseEvent(event)

# ──────────────────────────────────────────────────────────────────────────────
# Main UI & Logic Controller
# ──────────────────────────────────────────────────────────────────────────────

class FullConsoleUI(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(FullConsoleUI, self).__init__(parent or _maya_main_window())
        self.setObjectName(WINDOW_OBJECT)
        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setMinimumWidth(390)

        self.speed_pct = 5
        self._stored_states = []
        self._current_scrub_mode = None
        self._tool_job = None

        self._build()
        self._install_tool_watch()
        self.refresh_indicator()

    @property
    def speed_multiplier(self):
        return max(0.0001, self.speed_pct / 100.0)

    def _build(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12); root.setSpacing(12)

        # ── Viewport Gizmo Management (Simplified) ──
        tool_box = QtWidgets.QGroupBox("Viewport Gizmo")
        tool_lay = QtWidgets.QVBoxLayout(tool_box)
        tool_lay.setSpacing(6)

        self.toggle_gizmo_btn = QtWidgets.QPushButton("Hide Gizmo")
        self.toggle_gizmo_btn.setFixedHeight(34)
        f = self.toggle_gizmo_btn.font(); f.setBold(True); self.toggle_gizmo_btn.setFont(f)
        self.toggle_gizmo_btn.clicked.connect(self._on_toggle_gizmo)
        tool_lay.addWidget(self.toggle_gizmo_btn)

        root.addWidget(tool_box)

        # ── Speed Control ──
        speed_box = QtWidgets.QGroupBox("Micro Speed Reduction")
        sb_lay = QtWidgets.QVBoxLayout(speed_box)

        speed_row = QtWidgets.QHBoxLayout()
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(1, 100); self.slider.setValue(self.speed_pct)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow); self.slider.setTickInterval(10)
        
        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(1, 100); self.spin.setValue(self.speed_pct)
        self.spin.setSuffix(" %"); self.spin.setFixedWidth(70)
        
        self.slider.valueChanged.connect(self._on_speed_changed)
        self.spin.valueChanged.connect(self._on_speed_changed)
        
        speed_row.addWidget(self.slider, 1); speed_row.addWidget(self.spin, 0)
        sb_lay.addLayout(speed_row)

        preset_row = QtWidgets.QHBoxLayout()
        for pct in (1, 5, 10, 25, 50, 75): 
            btn = QtWidgets.QPushButton(f"{pct}%")
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _=False, p=pct: self._on_speed_changed(p))
            preset_row.addWidget(btn)
        sb_lay.addLayout(preset_row)
        root.addWidget(speed_box)

        # ── Tabbed Layout (Visually Highlighted) ──
        self.tabs = QtWidgets.QTabWidget()
        
        # New CSS to explicitly highlight the active tab and mute inactive ones
        self.tabs.setStyleSheet("""
            QTabBar::tab { 
                background: #333333; 
                color: #aaaaaa; 
                padding: 8px 25px; 
                border: 1px solid #222222;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected { 
                background: #4a4a4a; 
                color: #ffffff; 
                font-weight: bold;
                border-top: 2px solid #55aaff; /* Blue accent line */
            }
            QTabWidget::pane {
                border: 1px solid #222222;
                background: #4a4a4a;
                top: -1px;
            }
        """)
        
        # Build Translate, Rotate, Scale tabs
        self.tabs.addTab(self._build_scrubber_group("translate"), "Translate")
        self.tabs.addTab(self._build_scrubber_group("rotate"), "Rotate")
        self.tabs.addTab(self._build_scrubber_group("scale"), "Scale")
        
        # When user changes tabs, sync the viewport gizmo if it's currently visible
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        self.tabs.setCurrentIndex(1)
        root.addWidget(self.tabs)

        tip = QtWidgets.QLabel(
            "Select objects. Drag the Virtual Scrubbers to adjust smoothly.\n"
            "Undo (Ctrl+Z) will cleanly undo the entire drag action."
        )
        tip.setStyleSheet("color:#888;"); tip.setWordWrap(True)
        root.addWidget(tip)

    def _build_scrubber_group(self, mode):
        widget = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(widget)
        lay.setContentsMargins(10, 15, 10, 10)
        lay.setSpacing(15)

        colors = {"X": "#ff5555", "Y": "#55ff55", "Z": "#5555ff"}

        for axis in ("X", "Y", "Z"):
            row = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(f"{mode.capitalize()[:3]} {axis}")
            lbl.setFixedWidth(40)
            lbl.setStyleSheet(f"color: {colors[axis]}; font-weight: bold; font-size: 12px;")
            
            scrubber = InfiniteScrubber()
            scrubber.scrub_started.connect(lambda m=mode: self._on_scrub_start(m))
            scrubber.scrub_moved.connect(lambda val, a=axis, m=mode: self._on_scrub_move(m, a, val))
            scrubber.scrub_ended.connect(self._on_scrub_end)
            
            row.addWidget(lbl); row.addWidget(scrubber)
            lay.addLayout(row)
            
        lay.addStretch()
        return widget

    # ── Maya Tool Sync Logic ──
    
    def _on_toggle_gizmo(self):
        """Smart toggle: Switches between Select (hidden) and the tool matching the current tab."""
        ctx = (cmds.currentCtx() or "").lower()
        if "select" in ctx:
            # Gizmo is hidden, show it based on the active tab
            self._activate_tool_for_current_tab()
        else:
            # Gizmo is visible, hide it
            cmds.setToolTo("selectSuperContext")

    def _on_tab_changed(self, index):
        """If the gizmo is visible, automatically switch the Maya tool when the user changes tabs."""
        ctx = (cmds.currentCtx() or "").lower()
        if "select" not in ctx:
            self._activate_tool_for_current_tab()

    def _activate_tool_for_current_tab(self):
        idx = self.tabs.currentIndex()
        if idx == 0: cmds.setToolTo("moveSuperContext")
        elif idx == 1: cmds.setToolTo("rotateSuperContext")
        elif idx == 2: cmds.setToolTo("scaleSuperContext")

    def _install_tool_watch(self):
        try:
            self._tool_job = cmds.scriptJob(event=["ToolChanged", self.refresh_indicator], protected=False)
        except Exception:
            pass

    def refresh_indicator(self):
        try: current_ctx = (cmds.currentCtx() or "").lower()
        except Exception: current_ctx = ""
        
        is_hidden = "select" in current_ctx

        if is_hidden:
            self.toggle_gizmo_btn.setText("Show Gizmo")
            self.toggle_gizmo_btn.setStyleSheet("background-color: #55aaff; color: white; border: 1px solid #3388dd;")
        else:
            self.toggle_gizmo_btn.setText("Hide Gizmo")
            self.toggle_gizmo_btn.setStyleSheet("")

    def _on_speed_changed(self, val):
        self.speed_pct = val
        self.slider.blockSignals(True); self.slider.setValue(val); self.slider.blockSignals(False)
        self.spin.blockSignals(True); self.spin.setValue(val); self.spin.blockSignals(False)

    # ── Unified Scrubber Logic ──
    
    def _on_scrub_start(self, mode):
        sel = cmds.ls(selection=True, type="transform")
        if not sel: 
            return cmds.warning("[MicroManipulator] Please select an object first.")

        self._current_scrub_mode = mode
        cmds.undoInfo(openChunk=True, chunkName=f"Micro{mode.capitalize()}")
        
        self._stored_states = []
        for obj in sel:
            try:
                self._stored_states.append({
                    "obj": obj,
                    "X": cmds.getAttr(f"{obj}.{mode}X"),
                    "Y": cmds.getAttr(f"{obj}.{mode}Y"),
                    "Z": cmds.getAttr(f"{obj}.{mode}Z")
                })
            except Exception: continue

    def _on_scrub_move(self, mode, axis, raw_delta):
        if not self._stored_states or self._current_scrub_mode != mode: return

        if mode == "translate": sensitivity = 0.05
        elif mode == "rotate": sensitivity = 0.5
        elif mode == "scale": sensitivity = 0.005
        else: sensitivity = 0.1

        scaled_delta = raw_delta * sensitivity * self.speed_multiplier

        for state in self._stored_states:
            obj = state["obj"]
            base_val = state[axis] 
            
            try:
                if mode == "scale":
                    new_val = base_val * (1.0 + scaled_delta)
                else:
                    new_val = base_val + scaled_delta
                    
                cmds.setAttr(f"{obj}.{mode}{axis}", new_val)
            except Exception: pass 

    def _on_scrub_end(self):
        self._stored_states = []
        self._current_scrub_mode = None
        try: cmds.undoInfo(closeChunk=True)
        except Exception: pass

    def closeEvent(self, event):
        if self._tool_job is not None:
            try: cmds.scriptJob(kill=self._tool_job, force=True)
            except Exception: pass
        QtWidgets.QDialog.closeEvent(self, event)

def show():
    for w in QtWidgets.QApplication.allWidgets():
        if w.objectName() == WINDOW_OBJECT:
            try: w.close(); w.deleteLater()
            except Exception: pass
    ui = FullConsoleUI()
    ui.show()
    return ui

show()