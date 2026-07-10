"""Shared visual theme for the Blue Pencil Flipbook Manager.

A single dark palette and Qt style sheet keeps the tool consistent with the
Animation Tool Kit look: charcoal panels, a Blue Pencil blue accent, rounded
controls, and clear hover / pressed / checked states.
"""

from __future__ import annotations

# --- Palette ----------------------------------------------------------------
BG = "#2b2f36"          # window background
PANEL = "#343941"       # group / card background
PANEL_ALT = "#3c424b"   # inputs, raised buttons
BORDER = "#22262c"      # separators / outlines
TEXT = "#e6e9ef"        # primary text
TEXT_DIM = "#9aa2ad"    # secondary text / labels
ACCENT = "#3d8bfd"      # Blue Pencil blue
ACCENT_HOVER = "#5b9dff"
ACCENT_PRESSED = "#2f6fd6"

# Default Blue Pencil stroke color (the classic light blue).
DRAW_DEFAULT = "#8fc2ff"

# Frame-type badge colors (shared by menus, badges, and legends).
KEY_COLOR = "#e0554e"
BREAKDOWN_COLOR = "#e0952b"
INBETWEEN_COLOR = "#3d8bfd"


STYLESHEET = """
QWidget {{
    background: {bg};
    color: {text};
    font-family: "Segoe UI", "Open Sans", sans-serif;
    font-size: 12px;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {bg};
    border: none;
}}

QLabel {{ background: transparent; }}
QLabel[role="sectionCaption"] {{ color: {dim}; font-size: 11px; }}

/* Menu bar ---------------------------------------------------------------- */
QMenuBar {{ background: {border}; color: {text}; padding: 2px; }}
QMenuBar::item {{ background: transparent; padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {accent}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}

/* Group boxes ------------------------------------------------------------- */
QGroupBox {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 10px 8px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 8px;
    color: {accent};
    background: transparent;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-size: 11px;
}}

/* Buttons ----------------------------------------------------------------- */
QPushButton {{
    background: {panel_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 16px;
}}
QPushButton:hover {{ background: #454b55; border-color: {accent}; }}
QPushButton:pressed {{ background: {accent_pressed}; }}
QPushButton:checked {{
    background: {accent};
    border-color: {accent_hover};
    color: white;
    font-weight: 600;
}}
QPushButton:disabled {{ color: {dim}; background: {panel}; }}

QPushButton[role="accent"] {{
    background: {accent};
    border-color: {accent_hover};
    color: white;
    font-weight: 600;
}}
QPushButton[role="accent"]:hover {{ background: {accent_hover}; }}
QPushButton[role="accent"]:pressed {{ background: {accent_pressed}; }}

/* Transport (round-ish) buttons */
QPushButton[role="transport"] {{ min-width: 30px; padding: 6px 8px; font-size: 14px; }}

/* Inputs ------------------------------------------------------------------ */
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {panel_alt};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 16px;
    selection-background-color: {accent};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {panel};
    border: 1px solid {border};
    selection-background-color: {accent};
    outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 14px; background: {panel}; border: none;
}}

/* Sliders ----------------------------------------------------------------- */
QSlider::groove:horizontal {{
    height: 4px; background: {border}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {text}; width: 14px; margin: -6px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {accent_hover}; }}

/* Check boxes ------------------------------------------------------------- */
QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {border}; background: {panel_alt};
}}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent_hover}; }}

/* Scrollbars -------------------------------------------------------------- */
QScrollBar:vertical {{ background: {bg}; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: {bg}; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: #4b525c; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Header + status bar ----------------------------------------------------- */
QWidget[role="header"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #3a4048, stop:1 {panel});
    border-radius: 8px;
    border: 1px solid {border};
}}
QLabel[role="title"] {{ font-size: 15px; font-weight: 700; color: {text}; }}
QLabel[role="subtitle"] {{ color: {dim}; font-size: 11px; }}
QLabel[role="status"] {{ color: {dim}; font-size: 11px; padding: 2px 4px; }}

/* Thumbnail cards --------------------------------------------------------- */
QFrame#ThumbnailCard {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#ThumbnailCard:hover {{ border-color: {accent}; }}
""".format(
    bg=BG,
    panel=PANEL,
    panel_alt=PANEL_ALT,
    border=BORDER,
    text=TEXT,
    dim=TEXT_DIM,
    accent=ACCENT,
    accent_hover=ACCENT_HOVER,
    accent_pressed=ACCENT_PRESSED,
)


def apply(widget):
    """Apply the shared theme to a top-level widget."""
    if widget is not None:
        widget.setStyleSheet(STYLESHEET)
