"""
SavePlus Main - Main UI class and functionality for the SavePlus tool
Part of the SavePlus toolset for Maya 2025
"""
import os
import time
import re
import traceback
import subprocess
import sys

import savePlus_maya
from savePlus_maya import cmds, mel

from PySide6.QtWidgets import (QPushButton, QVBoxLayout, QLabel, QLineEdit, 
                              QHBoxLayout, QCheckBox, QFileDialog, QMainWindow, 
                              QMenuBar, QStatusBar, QGridLayout, QFrame, QGroupBox, 
                              QComboBox, QStyle, QSizePolicy, QTextEdit, QSpinBox,
                              QMessageBox, QFormLayout, QScrollArea, QTabWidget, 
                              QListWidget, QListWidgetItem, QTableWidget, 
                              QTableWidgetItem, QHeaderView, QWidget, QDialog)
from PySide6 import QtCore
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from savePlus_maya import MayaQWidgetDockableMixin

import savePlus_core
import savePlus_ui_components

# Constants
VERSION = savePlus_core.VERSION
UNIQUE_IDENTIFIER = "SavePlus_v1_ToolButton"
TIMER_COUNT = 0  # Add this line to track timer firing count

def truncate_path(path, max_length=40):
    """
    Truncate a path for display by preserving the beginning and end
    while replacing the middle with ellipsis if too long.
    """
    if not path or len(path) <= max_length:
        return path
        
    # Keep the drive or network location part
    drive, remainder = os.path.splitdrive(path)
    
    # Separate the filename from the directory path
    directory, filename = os.path.split(remainder)
    
    # Calculate how much of the directory we can show
    # We want to show the beginning and end of the directory path
    available_length = max_length - len(drive) - len(filename) - 5  # 5 for "/.../"
    
    if available_length <= 0:
        # Path is too long, just show drive and filename
        return f"{drive}/.../{filename}"
    
    half_length = available_length // 2
    
    # Get the beginning and end of the directory path
    dir_start = directory[:half_length]
    dir_end = directory[-half_length:] if half_length > 0 else ""
    
    return f"{drive}{dir_start}/.../{dir_end}/{filename}"

class SavePlusUI(MayaQWidgetDockableMixin, QMainWindow):
    """SavePlus UI Class - Modern interface with menus and log display"""
    
    # Option variables for saving settings
    OPT_VAR_ASSIGNMENT_LETTER = "SavePlusAssignmentLetter"
    OPT_VAR_ASSIGNMENT_NUMBER = "SavePlusAssignmentNumber"
    OPT_VAR_LAST_NAME = "SavePlusLastName"
    OPT_VAR_FIRST_NAME = "SavePlusFirstName"
    OPT_VAR_VERSION_TYPE = "SavePlusVersionType"
    OPT_VAR_VERSION_NUMBER = "SavePlusVersionNumber"
    OPT_VAR_ENABLE_TIMED_WARNING = "SavePlusEnableTimedWarning"
    OPT_VAR_PIPELINE_STAGE = "SavePlusPipelineStage"  # New option var for pipeline stage
    
    # Option variables for saving preferences
    OPT_VAR_DEFAULT_FILETYPE = "SavePlusDefaultFiletype"
    OPT_VAR_AUTO_SAVE_INTERVAL = "SavePlusAutoSaveInterval"
    OPT_VAR_DEFAULT_SAVE_PATH = "SavePlusDefaultSavePath"
    OPT_VAR_PROJECT_PATH = "SavePlusProjectPath"
    OPT_VAR_FILE_EXPANDED = "SavePlusFileExpanded"
    OPT_VAR_NAME_EXPANDED = "SavePlusNameExpanded"
    OPT_VAR_LOG_EXPANDED = "SavePlusLogExpanded"
    OPT_VAR_RESPECT_PROJECT = "SavePlusRespectProject"
    OPT_VAR_PROJECT_PREFIX_LETTER = "SavePlusProjectPrefixLetter"
    OPT_VAR_PROJECT_PREFIX_NUMBER = "SavePlusProjectPrefixNumber"
    OPT_VAR_PROJECT_NAME = "SavePlusProjectName"
    OPT_VAR_PROJECT_ROOT_PATH = "SavePlusProjectRootPath"
    OPT_VAR_PROJECT_SET_PATH = "SavePlusProjectSetPath"

    # New option variables
    OPT_VAR_ENABLE_AUTO_BACKUP = "SavePlusEnableAutoBackup"
    OPT_VAR_BACKUP_INTERVAL = "SavePlusBackupInterval"
    OPT_VAR_ADD_VERSION_NOTES = "SavePlusAddVersionNotes"

    # Additional preference option variables
    OPT_VAR_CLEAR_QUICK_NOTE = "SavePlusClearQuickNote"
    OPT_VAR_ENABLE_SAVE_SOUND = "SavePlusEnableSaveSound"
    OPT_VAR_MAX_HISTORY_ENTRIES = "SavePlusMaxHistoryEntries"
    OPT_VAR_BACKUP_LOCATION = "SavePlusBackupLocation"
    OPT_VAR_MAX_BACKUPS = "SavePlusMaxBackups"
    OPT_VAR_SHOW_SAVE_CONFIRMATION = "SavePlusShowSaveConfirmation"
    OPT_VAR_AUTO_INCREMENT_VERSION = "SavePlusAutoIncrementVersion"
    OPT_VAR_COMPACT_NAME = "SavePlusCompactName"

    # Stage abbreviations used for compact filenames
    STAGE_ABBREVIATIONS = {
        "layout": "lay",
        "planning": "pln",
        "blocking": "blk",
        "blocking plus": "blk+",
        "spline": "spln",
        "polish": "pls",
        "lighting": "lgt",
        "final": "fnl",
    }
    STATUS_ABBREVIATIONS = {
        "wip": "w",
        "final": "f",
    }
    
    def __init__(self, parent=None):
        try:
            super(SavePlusUI, self).__init__(parent)
            savePlus_core.debug_print("Initializing SavePlus UI")
            
            # Set window properties
            self.setWindowTitle("SavePlus")
            self.setMinimumWidth(550)
            self.setMinimumHeight(200)
            
            # Set application-wide tooltip style
            self.setStyleSheet("""
                QToolTip {
                    background-color: #2A2A2A;
                    color: white;
                    border: 1px solid #3A3A3A;
                    border-radius: 3px;
                    padding: 3px;
                    font-size: 11px;
                }
            """)

            # Flag to control auto-resize behavior
            self.auto_resize_enabled = True
            
            # Directory selected with browse button
            self.selected_directory = None
            
            # Initialize version history manager
            self.version_history = savePlus_core.VersionHistoryModel()
            
            # Create a central widget
            central_widget = QWidget()
            central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setCentralWidget(central_widget)
            
            # Create main layout
            main_layout = QVBoxLayout(central_widget)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(0)

            # Allow manual resizing and show a size grip in the corner
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            # --- CREATE BASIC UI FIRST --- 
            
            # Create menu bar (basic UI component)
            self.create_menu_bar()
            
            # Create status bar (basic UI component)
            self.status_bar = QStatusBar()
            self.status_bar.setSizeGripEnabled(True)
            self.setStatusBar(self.status_bar)
            
            # --- CREATE HEADER ABOVE TABS ---
            
            # Create a modern header
            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(10, 5, 10, 5)
            
           # Minimal title in tab header
            title_layout = QHBoxLayout()
            title_layout.setContentsMargins(5, 2, 5, 2)

            # Version label only in small text
            version_label = QLabel(f"SavePlus v{VERSION}")
            version_label.setStyleSheet("color: #7f8c8d; font-size: 9px;")
            version_label.setAlignment(Qt.AlignRight)

            title_layout.addStretch()
            title_layout.addWidget(version_label)

            main_layout.addLayout(title_layout)
            
            # --- CREATE TABS ---
            
            # Create tab widget
            self.tab_widget = QTabWidget()
            
            # Create SavePlus Tab
            self.saveplus_tab = QWidget()
            self.saveplus_layout = QVBoxLayout(self.saveplus_tab)
            self.saveplus_layout.setContentsMargins(8, 8, 8, 8)
            self.saveplus_layout.setSpacing(8)

            # Create Project Tab
            self.project_tab = QWidget()
            self.project_layout = QVBoxLayout(self.project_tab)
            self.project_layout.setContentsMargins(8, 8, 8, 8)
            self.project_layout.setSpacing(10)
            
            # Create History Tab
            self.history_tab = QWidget()
            self.history_layout = QVBoxLayout(self.history_tab)
            self.history_layout.setContentsMargins(8, 8, 8, 8)
            self.history_layout.setSpacing(8)
            
            # Create Preferences Tab
            self.preferences_tab = QWidget()
            self.preferences_layout = QVBoxLayout(self.preferences_tab)
            self.preferences_layout.setContentsMargins(8, 8, 8, 8)
            self.preferences_layout.setSpacing(10)
            
            # Add tabs to tab widget - Project tab is first for project management workflow
            self.tab_widget.addTab(self.project_tab, "Project")
            self.tab_widget.addTab(self.saveplus_tab, "SavePlus")
            self.tab_widget.addTab(self.history_tab, "History")
            self.tab_widget.addTab(self.preferences_tab, "Preferences")

            self.project_tab_index = self.tab_widget.indexOf(self.project_tab)
            self.history_tab_index = self.tab_widget.indexOf(self.history_tab)
            self.saveplus_tab_index = self.tab_widget.indexOf(self.saveplus_tab)
            
            # Add tab widget to main layout
            main_layout.addWidget(self.tab_widget)
            
            # --- SAVEPLUS TAB CONTENT ---
            
            # Create container widget for scrollable content
            self.container_widget = QWidget()
            # Set a fixed policy to ensure elements stay at the top
            self.container_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

            self.container_layout = QVBoxLayout(self.container_widget)
            self.container_layout.setContentsMargins(0, 0, 0, 0)
            self.container_layout.setSpacing(15)  # Increased spacing between sections
            self.container_layout.setAlignment(Qt.AlignTop)  # Keep elements aligned at the top

            # Create save buttons at the TOP of interface
            buttons_layout = QHBoxLayout()
            buttons_layout.setContentsMargins(0, 10, 0, 10)  # Add some vertical padding

            # Style buttons with consistent, modern appearance
            button_style = """
            QPushButton {
                border-radius: 4px;
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                                stop: 0 #3a3a3a, stop: 1 #2a2a2a);
                border: 1px solid #444444;
                padding: 6px 12px;
                min-height: 30px;
                color: #ffffff;  /* White text for maximum contrast */
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                                stop: 0 #4a4a4a, stop: 1 #3a3a3a);
                color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                                stop: 0 #2a2a2a, stop: 1 #3a3a3a);
                color: #ffffff;
            }
            """

            # Create buttons with keyboard shortcut indicators
            save_button = QPushButton("Save Plus (Ctrl+S)")
            save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
            save_button.setMinimumHeight(40)
            save_button.setStyleSheet(button_style)
            save_button.clicked.connect(self.save_plus)
            save_button.setToolTip("Increment the version number and save.\n\nExample: scene_v01.ma → scene_v02.ma\n\nAny quick note entered below will be attached to this version.")

            save_new_button = QPushButton("Save As New (Ctrl+Shift+S)")
            save_new_button.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
            save_new_button.setMinimumHeight(40)
            save_new_button.setStyleSheet(button_style)
            save_new_button.clicked.connect(self.save_as_new)
            save_new_button.setToolTip("Save with the exact filename shown above.\n\nUseful for starting a new file or saving to a specific name without incrementing.")

            # New backup button
            backup_button = QPushButton("Create Backup (Ctrl+B)")
            backup_button.setIcon(self.style().standardIcon(QStyle.SP_DriveFDIcon))
            backup_button.setMinimumHeight(40)
            backup_button.setStyleSheet(button_style)
            backup_button.clicked.connect(self.create_backup)
            backup_button.setToolTip("Save a versioned backup copy of the current file.\n\nExample: scene_122.ma → scene_123.ma\n\nUseful before making major changes.")

            buttons_layout.addWidget(save_button)
            buttons_layout.addWidget(save_new_button)
            buttons_layout.addWidget(backup_button)

            # Add top save buttons to container layout
            self.container_layout.addLayout(buttons_layout)

            # Button help text — concise one-liner per button
            button_help = QLabel(
                "<table style='border-spacing:0; color:#999999; font-size:10px;'>"
                "<tr>"
                  "<td style='padding:2px 8px 2px 2px; white-space:nowrap;'>"
                    "<span style='color:#CCCCCC; font-weight:bold;'>Save Plus</span>"
                  "</td>"
                  "<td style='padding:2px 0;'>"
                    "Increments the version number and saves a new copy. "
                    "Your previous version is kept."
                  "</td>"
                "</tr>"
                "<tr>"
                  "<td style='padding:2px 8px 2px 2px; white-space:nowrap;'>"
                    "<span style='color:#CCCCCC; font-weight:bold;'>Save As New</span>"
                  "</td>"
                  "<td style='padding:2px 0;'>"
                    "Saves with the exact filename shown — no increment. "
                    "Use this to start a new file or lock in a specific name."
                  "</td>"
                "</tr>"
                "<tr>"
                  "<td style='padding:2px 8px 2px 2px; white-space:nowrap;'>"
                    "<span style='color:#CCCCCC; font-weight:bold;'>Create Backup</span>"
                  "</td>"
                  "<td style='padding:2px 0;'>"
                    "Saves a separate backup copy without changing your current file. "
                    "Run this before making large changes."
                  "</td>"
                "</tr>"
                "</table>"
            )
            button_help.setWordWrap(True)
            button_help.setContentsMargins(2, 2, 2, 2)
            self.container_layout.addWidget(button_help)

            # Last save indicator and status
            last_save_layout = QHBoxLayout()
            last_save_layout.setContentsMargins(4, 2, 4, 2)

            last_save_container = QFrame()
            last_save_container.setStyleSheet("background-color: rgba(0, 0, 0, 0.2); border-radius: 3px;")
            last_save_container.setLayout(last_save_layout)

            self.last_save_indicator = QLabel("●")
            self.last_save_indicator.setStyleSheet("color: #4CAF50; font-size: 18px;")
            self.last_save_indicator.setFixedWidth(20)

            self.last_save_status = QLabel("Last saved: N/A")
            self.last_save_status.setStyleSheet("color: #ffffff; font-size: 10px;")

            last_save_layout.addWidget(self.last_save_indicator)
            last_save_layout.addWidget(self.last_save_status)
            last_save_layout.addStretch()

            self.container_layout.addWidget(last_save_container)

            # Quick Note input - placed right under buttons for easy access
            quick_note_layout = QHBoxLayout()
            quick_note_layout.setContentsMargins(0, 8, 0, 8)
            quick_note_layout.setSpacing(8)

            quick_note_label = QLabel("Quick Note:")
            quick_note_label.setStyleSheet("color: #CCCCCC; font-weight: bold; font-size: 11px;")
            quick_note_label.setFixedWidth(75)
            quick_note_layout.addWidget(quick_note_label)

            self.quick_note_input = QLineEdit()
            self.quick_note_input.setPlaceholderText("Optional: Add a note before saving...")
            self.quick_note_input.setStyleSheet("""
                QLineEdit {
                    background-color: #2A2A2A;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 6px 10px;
                    color: #FFFFFF;
                    font-size: 11px;
                }
                QLineEdit:focus {
                    border: 1px solid #0066CC;
                }
            """)
            self.quick_note_input.setToolTip("Type a note here before clicking 'Save Plus'.\n\nThis note will be attached to the saved version for future reference.\n\nLeave empty if no note is needed - this is optional.")
            quick_note_layout.addWidget(self.quick_note_input)

            self.container_layout.addLayout(quick_note_layout)

            # Add a subtle separator between buttons and sections
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Sunken)
            separator.setStyleSheet("background-color: #444444; max-height: 1px;")
            self.container_layout.addWidget(separator)
            self.container_layout.addSpacing(10)  # Add space after separator

            # Create Name Generator section (expanded by default - placed high for easy access)
            self.name_gen_section = savePlus_ui_components.ZurbriggStyleCollapsibleFrame("Name Generator", collapsed=False)
            self.name_gen_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Create name generator content
            name_gen = QWidget()
            name_gen_layout = QFormLayout(name_gen)
            name_gen_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

            # Assignment letter and number
            assignment_layout = QHBoxLayout()

            # Assignment letter selection
            self.assignment_letter_combo = QComboBox()
            self.assignment_letter_combo.addItems(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
            saved_letter = self.load_option_var(self.OPT_VAR_ASSIGNMENT_LETTER, "A")
            index = self.assignment_letter_combo.findText(saved_letter)
            if index >= 0:
                self.assignment_letter_combo.setCurrentIndex(index)
            self.assignment_letter_combo.setFixedWidth(50)
            self.assignment_letter_combo.setToolTip("Assignment/Project letter identifier (e.g., A, B, J)")

            # Assignment number selection
            self.assignment_spinbox = QSpinBox()
            self.assignment_spinbox.setRange(1, 99)
            self.assignment_spinbox.setValue(self.load_option_var(self.OPT_VAR_ASSIGNMENT_NUMBER, 1))
            self.assignment_spinbox.setFixedWidth(50)
            self.assignment_spinbox.setToolTip("Assignment/Project number (e.g., 01, 02)")

            assignment_layout.addWidget(self.assignment_letter_combo)
            assignment_layout.addWidget(self.assignment_spinbox)
            assignment_layout.addStretch()

            # Last name
            self.lastname_input = QLineEdit()
            self.lastname_input.setPlaceholderText("Last Name")
            self.lastname_input.setText(self.load_option_var(self.OPT_VAR_LAST_NAME, ""))
            self.lastname_input.setFixedWidth(200)
            self.lastname_input.setToolTip("Your last name for the filename")

            # First name
            self.firstname_input = QLineEdit()
            self.firstname_input.setPlaceholderText("First Name")
            self.firstname_input.setText(self.load_option_var(self.OPT_VAR_FIRST_NAME, ""))
            self.firstname_input.setFixedWidth(200)
            self.firstname_input.setToolTip("Your first name for the filename")

            # Pipeline stage dropdown
            pipeline_stage_layout = QHBoxLayout()
            self.pipeline_stage_label = QLabel("Pipeline Stage:")

            # Create the pipeline stage dropdown
            self.pipeline_stage_combo = QComboBox()
            self.pipeline_stage_combo.addItems([
                "Layout",
                "Planning",
                "Blocking",
                "Blocking Plus",
                "Spline",
                "Polish",
                "Lighting",
                "Final"
            ])
            saved_stage = self.load_option_var(self.OPT_VAR_PIPELINE_STAGE, "Blocking")
            index = self.pipeline_stage_combo.findText(saved_stage)
            if index >= 0:
                self.pipeline_stage_combo.setCurrentIndex(index)
            self.pipeline_stage_combo.setFixedWidth(120)

            # Status dropdown (WIP or Final)
            self.version_status_combo = QComboBox()
            self.version_status_combo.addItems(["wip", "final"])
            saved_type = self.load_option_var(self.OPT_VAR_VERSION_TYPE, "wip")
            index = self.version_status_combo.findText(saved_type)
            if index >= 0:
                self.version_status_combo.setCurrentIndex(index)
            self.version_status_combo.setFixedWidth(80)

            self.pipeline_stage_combo.setItemData(0, "Camera angles, character and prop placement, and shot timing established", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(1, "Performance planning using reference footage and thumbnail sketches", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(2, "Key storytelling poses blocked in stepped mode with rough timing", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(3, "Primary and secondary breakdowns added; refined timing, spacing, and arcs", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(4, "Converted to spline; cleaned interpolation, arcs, and spacing", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(5, "Final polish: facial animation, overlap, follow-through, and subtle details", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(6, "Lighting pass: establishing mood, depth, and render look", Qt.ToolTipRole)
            self.pipeline_stage_combo.setItemData(7, "Shot approved: animation and visuals are final and ready for comp or submission", Qt.ToolTipRole)

            # Add both dropdowns to the layout
            pipeline_stage_layout.addWidget(self.pipeline_stage_combo)
            pipeline_stage_layout.addWidget(self.version_status_combo)
            pipeline_stage_layout.addStretch()

            # Version number
            version_number_layout = QHBoxLayout()
            self.version_number_spinbox = QSpinBox()
            self.version_number_spinbox.setRange(1, 99)
            self.version_number_spinbox.setValue(self.load_option_var(self.OPT_VAR_VERSION_NUMBER, 1))
            self.version_number_spinbox.setFixedWidth(50)
            self.version_number_spinbox.setToolTip("Starting version number")
            version_number_layout.addWidget(self.version_number_spinbox)
            version_number_layout.addStretch()

            # Preview label
            self.filename_preview = QLabel("No filename")
            self.filename_preview.setStyleSheet("color: #0066CC; font-weight: bold;")

            # Generate and Reset buttons
            name_gen_buttons_layout = QHBoxLayout()
            generate_button = QPushButton("Generate Filename")
            generate_button.clicked.connect(self.generate_filename)
            generate_button.setToolTip("Create a filename based on the settings above and apply it to the Filename field")

            reset_button = QPushButton("Reset")
            reset_button.clicked.connect(self.reset_name_generator)
            reset_button.setToolTip("Reset all Name Generator fields to defaults")

            name_gen_buttons_layout.addStretch()
            name_gen_buttons_layout.addWidget(generate_button)
            name_gen_buttons_layout.addWidget(reset_button)

            # Add all to form layout
            # Compact name checkbox
            self.compact_name_checkbox = QCheckBox("Compact Name")
            self.compact_name_checkbox.setChecked(bool(self.load_option_var(self.OPT_VAR_COMPACT_NAME, 0)))
            self.compact_name_checkbox.setToolTip(
                "Generate a shorter filename using abbreviations:\n"
                "  \u2022 First name \u2192 initial only  (John \u2192 J)\n"
                "  \u2022 Stage \u2192 abbreviation  (blocking \u2192 blk,  blocking plus \u2192 blk+)\n"
                "  \u2022 Status \u2192 single letter  (wip \u2192 w,  final \u2192 f)\n\n"
                "Recommended when syncing to cloud storage or Windows systems\n"
                "with long folder paths.\n\n"
                "Max filename lengths by platform:\n"
                "  Windows:      255 chars (full path capped at 260)\n"
                "  macOS/Linux:  255 bytes\n"
                "  Google Drive: 255 chars\n"
                "  OneDrive:     255 chars\n"
                "  Dropbox:      260-char total path\n\n"
                "Safe target: keep filenames under 64 characters."
            )
            compact_checkbox_row = QHBoxLayout()
            compact_checkbox_row.addWidget(self.compact_name_checkbox)
            compact_checkbox_row.addStretch()

            # Live compact preview label (always shows what the compact name would look like)
            self.compact_filename_preview = QLabel("\u2014")
            self.compact_filename_preview.setStyleSheet("color: #5599CC; font-style: italic;")

            name_gen_layout.addRow("Assignment:", assignment_layout)
            name_gen_layout.addRow("Last Name:", self.lastname_input)
            name_gen_layout.addRow("First Name:", self.firstname_input)
            name_gen_layout.addRow("Stage:", pipeline_stage_layout)
            name_gen_layout.addRow("Version:", version_number_layout)
            name_gen_layout.addRow("Preview:", self.filename_preview)
            name_gen_layout.addRow("", compact_checkbox_row)
            name_gen_layout.addRow("Compact:", self.compact_filename_preview)
            name_gen_layout.addRow("", name_gen_buttons_layout)

            self.name_gen_section.add_widget(name_gen)
            self.container_layout.addWidget(self.name_gen_section)

            # Add name_gen_section toggled signal connection
            self.name_gen_section.toggled.connect(self.adjust_window_size)

            # Connect all name generator inputs to the live compact preview
            for signal in [
                self.assignment_letter_combo.currentIndexChanged,
                self.assignment_spinbox.valueChanged,
                self.pipeline_stage_combo.currentIndexChanged,
                self.version_status_combo.currentIndexChanged,
                self.version_number_spinbox.valueChanged,
            ]:
                signal.connect(self._update_compact_preview)
            self.lastname_input.textChanged.connect(self._update_compact_preview)
            self.firstname_input.textChanged.connect(self._update_compact_preview)

            # Trigger initial compact preview population
            self._update_compact_preview()

            # Create File Options section (collapsed by default - advanced settings)
            self.file_options_section = savePlus_ui_components.ZurbriggStyleCollapsibleFrame("File Options", collapsed=True)
            self.file_options_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Create file options content
            file_options = QWidget()
            file_layout = QVBoxLayout(file_options)
            file_layout.setSpacing(10)  # Increased spacing between elements

            # Add filename input field - improved layout
            filename_section = QWidget()
            filename_layout = QVBoxLayout(filename_section)
            filename_layout.setContentsMargins(0, 0, 0, 0)
            filename_layout.setSpacing(5)

            filename_label = QLabel("Filename:")
            filename_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
            filename_layout.addWidget(filename_label)

            filename_input_layout = QHBoxLayout()
            filename_input_layout.setSpacing(6)  # Tighter spacing between elements

            self.filename_input = QLineEdit()
            self.filename_input.setMinimumWidth(250)
            self.filename_input.textChanged.connect(self.update_version_preview)
            self.filename_input.setStyleSheet("padding: 6px;")
            self.filename_input.home(False)  # Ensure text starts from beginning
            self.filename_input.setToolTip("Enter the filename for your scene.\n\nThe version number will be automatically incremented when using 'Save Plus'.\n\nExample: my_scene_v01 will become my_scene_v02")
            self.current_full_path = ""  # Store full path separately from display name

            # Get current file name if available
            current_file = cmds.file(query=True, sceneName=True)
            if current_file:
                self.filename_input.setText(os.path.basename(current_file))

            filename_input_layout.addWidget(self.filename_input)

            # Create a button group for path options with improved styling
            browse_button = QPushButton("Browse")
            browse_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
            browse_button.clicked.connect(self.browse_file)
            browse_button.setStyleSheet("padding: 6px;")
            browse_button.setToolTip("Browse for a directory to save to")

            reference_path_button = QPushButton("Reference")
            reference_path_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogToParent))
            reference_path_button.clicked.connect(self.use_reference_path)
            reference_path_button.setStyleSheet("padding: 6px;")
            reference_path_button.setToolTip("Use path from selected reference")

            filename_input_layout.addWidget(browse_button)
            filename_input_layout.addWidget(reference_path_button)

            filename_layout.addLayout(filename_input_layout)
            file_layout.addWidget(filename_section)

            # Add save location display with folder open button - NEW FEATURE
            save_location_section = QWidget()
            save_location_layout = QVBoxLayout(save_location_section)
            save_location_layout.setContentsMargins(0, 0, 0, 0)
            save_location_layout.setSpacing(5)

            save_location_label = QLabel("Save Location:")
            save_location_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
            save_location_layout.addWidget(save_location_label)

            save_location_display_layout = QHBoxLayout()
            save_location_display_layout.setSpacing(6)

            # Create a QFrame with horizontal layout to contain the path text and folder button
            save_path_frame = QFrame()
            save_path_frame.setFrameShape(QFrame.StyledPanel)
            save_path_frame.setFrameShadow(QFrame.Sunken)
            save_path_frame.setStyleSheet("""
                QFrame {
                    background-color: #2A2A2A;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px;
                }
            """)
            save_path_layout = QHBoxLayout(save_path_frame)
            save_path_layout.setContentsMargins(6, 2, 6, 2)
            save_path_layout.setSpacing(3)

            self.save_location_label = QLabel()
            self.save_location_label.setStyleSheet("color: #0066CC; background-color: transparent; padding: 0;")
            save_path_layout.addWidget(self.save_location_label, 1)  # Give label stretch priority

            # Add folder open button that opens the current directory
            folder_open_button = QPushButton()
            folder_open_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
            folder_open_button.setToolTip("Open folder in file explorer")
            folder_open_button.setFixedSize(28, 28)  # Slightly larger button for better clickability
            folder_open_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(60, 60, 60, 0.5); 
                    border: 1px solid rgba(80, 80, 80, 0.5);
                    border-radius: 4px;
                    padding: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(80, 80, 80, 0.8);
                    border: 1px solid rgba(100, 100, 100, 0.8);
                }
                QPushButton:pressed {
                    background-color: rgba(100, 100, 100, 1.0);
                }
            """)

            # Explicitly create a lambda function for the connection
            folder_open_button.clicked.connect(lambda: self.open_current_directory())
            save_path_layout.addWidget(folder_open_button)
            # Add explicit debug print after connecting
            print("Folder button created and connected to open_current_directory method")

            save_location_display_layout.addWidget(save_path_frame)

            # Add project reset button with improved styling
            self.reset_project_button = QPushButton()
            self.reset_project_button.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
            self.reset_project_button.setToolTip("Reset Project Display")
            self.reset_project_button.clicked.connect(self.direct_reset_project_display)
            self.reset_project_button.setStyleSheet("padding: 6px;")
            save_location_display_layout.addWidget(self.reset_project_button)

            save_location_layout.addLayout(save_location_display_layout)
            file_layout.addWidget(save_location_section)

            # Add version preview with improved styling
            version_preview_section = QWidget()
            version_preview_layout = QVBoxLayout(version_preview_section)
            version_preview_layout.setContentsMargins(0, 0, 0, 0)
            version_preview_layout.setSpacing(5)

            version_preview_label = QLabel("Next version:")
            version_preview_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
            version_preview_layout.addWidget(version_preview_label)

            version_preview_display = QHBoxLayout()
            version_preview_display.setSpacing(6)

            self.version_preview_icon = QLabel("→")
            self.version_preview_icon.setStyleSheet("color: #0066CC; font-weight: bold; font-size: 14px;")

            self.version_preview_text = QLabel("N/A")
            self.version_preview_text.setStyleSheet("color: #0066CC; font-weight: bold;")

            version_preview_display.addWidget(self.version_preview_icon)
            version_preview_display.addWidget(self.version_preview_text)
            version_preview_display.addStretch()

            version_preview_layout.addLayout(version_preview_display)
            file_layout.addWidget(version_preview_section)

            # Add file type selector with improved styling
            file_type_section = QWidget()
            file_type_layout = QVBoxLayout(file_type_section)
            file_type_layout.setContentsMargins(0, 0, 0, 0)
            file_type_layout.setSpacing(5)

            file_type_label = QLabel("File Type:")
            file_type_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
            file_type_layout.addWidget(file_type_label)

            self.filetype_combo = QComboBox()
            self.filetype_combo.addItems(["Maya ASCII (.ma)", "Maya Binary (.mb)"])
            self.filetype_combo.setFixedWidth(180)
            self.filetype_combo.setStyleSheet("padding: 6px;")
            self.filetype_combo.currentIndexChanged.connect(self.update_filename_preview)
            self.filetype_combo.currentIndexChanged.connect(self.update_version_preview)
            self.filetype_combo.currentIndexChanged.connect(self._update_compact_preview)
            self.filetype_combo.setToolTip("Choose the file format for saving:\n\n• Maya ASCII (.ma): Human-readable, larger file size, good for version control\n• Maya Binary (.mb): Smaller file size, faster to save/load")
            file_type_layout.addWidget(self.filetype_combo)
            file_layout.addWidget(file_type_section)

            # Add checkboxes with improved styling
            checkbox_section = QWidget()
            checkbox_layout = QVBoxLayout(checkbox_section)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setSpacing(8)

            # Add option to use the current directory
            self.use_current_dir = QCheckBox("Use current directory")
            self.use_current_dir.setChecked(True)
            self.use_current_dir.setStyleSheet("padding: 2px;")
            self.use_current_dir.toggled.connect(self.update_save_location_display)
            self.use_current_dir.setToolTip("When checked, saves will go to the same folder as the currently open file.\n\nUncheck to use a custom directory selected with the Browse button.")
            checkbox_layout.addWidget(self.use_current_dir)

            # Add option to respect project structure
            self.respect_project_structure = QCheckBox("Respect Maya project structure")
            self.respect_project_structure.setChecked(self.load_option_var(self.OPT_VAR_RESPECT_PROJECT, True))
            self.respect_project_structure.setToolTip("Save files in Maya project structure when active")
            self.respect_project_structure.setStyleSheet("padding: 2px;")
            self.respect_project_structure.stateChanged.connect(self.update_save_location_display)
            checkbox_layout.addWidget(self.respect_project_structure)

            file_layout.addWidget(checkbox_section)

            # Project status indicator
            project_status_section = QWidget()
            project_status_layout = QVBoxLayout(project_status_section)
            project_status_layout.setContentsMargins(0, 5, 0, 0)
            project_status_layout.setSpacing(5)

            project_label = QLabel("Project:")
            project_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
            project_status_layout.addWidget(project_label)

            self.project_status_label = QLabel("Project: Not detected")
            self.project_status_label.setStyleSheet("color: #666666; padding: 4px;")
            project_status_layout.addWidget(self.project_status_label)

            file_layout.addWidget(project_status_section)

            # Create layout for save reminder controls with improved styling
            reminder_section = QWidget()
            reminder_layout = QVBoxLayout(reminder_section)
            reminder_layout.setContentsMargins(0, 5, 0, 0)
            reminder_layout.setSpacing(5)

            reminder_label = QLabel("Reminders:")
            reminder_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
            reminder_layout.addWidget(reminder_label)

            save_reminder_layout = QHBoxLayout()
            save_reminder_layout.setContentsMargins(0, 0, 0, 0)
            save_reminder_layout.setSpacing(8)

            # Add timed save reminder checkbox with updated label
            self.enable_timed_warning = QCheckBox("Enable save reminder every")
            self.enable_timed_warning.setChecked(False)  # Explicitly set to False by default
            self.enable_timed_warning.stateChanged.connect(self.toggle_timed_warning)
            self.enable_timed_warning.setStyleSheet("padding: 2px;")
            self.enable_timed_warning.setToolTip("Get a reminder to save your work at regular intervals.\n\nThe status indicator will change color:\n• Green: Recently saved\n• Yellow: Getting close to reminder time\n• Red: Time to save!")
            save_reminder_layout.addWidget(self.enable_timed_warning)

            # Add spinner for reminder interval
            self.reminder_interval_spinbox = QSpinBox()
            self.reminder_interval_spinbox.setRange(1, 60)
            self.reminder_interval_spinbox.setValue(15)  # Default to 15 minutes
            self.reminder_interval_spinbox.setSuffix(" minutes")
            self.reminder_interval_spinbox.setFixedWidth(100)
            self.reminder_interval_spinbox.setStyleSheet("padding: 4px;")
            self.reminder_interval_spinbox.valueChanged.connect(self.update_reminder_interval)
            save_reminder_layout.addWidget(self.reminder_interval_spinbox)
            save_reminder_layout.addStretch()

            reminder_layout.addLayout(save_reminder_layout)

            # Add version notes option
            self.add_version_notes = QCheckBox("Add version notes when saving")
            self.add_version_notes.setChecked(self.load_option_var(self.OPT_VAR_ADD_VERSION_NOTES, False))
            self.add_version_notes.setToolTip("When enabled, you'll be prompted to add notes when saving.\n\nNotes help you remember what changes were made in each version.\n\nYou can also use the Quick Note field above for faster note entry.")
            self.add_version_notes.setStyleSheet("padding: 2px;")
            reminder_layout.addWidget(self.add_version_notes)

            file_layout.addWidget(reminder_section)
            
            self.file_options_section.add_widget(file_options)
            self.container_layout.addWidget(self.file_options_section)
            
            # Add file_options_section toggled signal connection
            self.file_options_section.toggled.connect(self.adjust_window_size)

            # Create Log section (collapsed by default)
            self.log_section = savePlus_ui_components.ZurbriggStyleCollapsibleFrame("Log Output", collapsed=True)
            self.log_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            # Create log content
            log_content = QWidget()
            log_layout = QVBoxLayout(log_content)
            
            # Create log text display with fixed height
            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.setLineWrapMode(QTextEdit.NoWrap)
            self.log_text.setFixedHeight(150)  # Fixed height for log
            
            # Log controls
            log_controls = QHBoxLayout()
            
            # Add log to script editor option
            self.log_to_script_editor_cb = QCheckBox("Log to Script Editor")
            self.log_to_script_editor_cb.setChecked(True)
            
            self.clear_log_button = QPushButton("Clear Log")
            self.clear_log_button.clicked.connect(self.clear_log)
            
            log_controls.addWidget(self.log_to_script_editor_cb)
            log_controls.addStretch()
            log_controls.addWidget(self.clear_log_button)
            
            log_layout.addWidget(self.log_text)
            log_layout.addLayout(log_controls)
            
            self.log_section.add_widget(log_content)
            self.container_layout.addWidget(self.log_section)
            
            # Add log_section toggled signal connection
            self.log_section.toggled.connect(self.adjust_window_size)
            
            # Add spacing at the bottom
            self.container_layout.addSpacing(20)
            
            # Create scroll area
            self.scroll_area = QScrollArea()
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setWidget(self.container_widget)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            # Add scroll area to saveplus layout
            self.saveplus_layout.addWidget(self.scroll_area)
            
            # --- PROJECT TAB CONTENT ---

            # Create scroll area so project tab content is accessible when docked
            project_scroll = QScrollArea()
            project_scroll.setWidgetResizable(True)
            project_scroll.setFrameShape(QFrame.NoFrame)
            project_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            project_container = QWidget()
            project_container_layout = QVBoxLayout(project_container)
            project_container_layout.setContentsMargins(0, 0, 0, 0)
            project_container_layout.setSpacing(10)

            # Current project status
            current_project_group = QGroupBox("Current Project")
            current_project_layout = QVBoxLayout(current_project_group)
            
            self.project_tab_status_label = QLabel("Project: Not detected")
            self.project_tab_status_label.setStyleSheet("color: #666666; padding: 4px;")
            current_project_layout.addWidget(self.project_tab_status_label)
            
            project_status_controls = QHBoxLayout()
            refresh_project_button = QPushButton("Refresh")
            refresh_project_button.clicked.connect(self.update_project_tracking)
            maya_project_window_button = QPushButton("Maya Project Window...")
            maya_project_window_button.setToolTip("Open Maya's standard project setup window")
            maya_project_window_button.clicked.connect(self.open_maya_project_window)
            open_project_folder_button = QPushButton("Open Folder")
            open_project_folder_button.setToolTip("Open current project folder in file browser")
            open_project_folder_button.clicked.connect(self.open_current_project_folder)
            project_status_controls.addWidget(maya_project_window_button)
            project_status_controls.addWidget(open_project_folder_button)
            project_status_controls.addStretch()
            project_status_controls.addWidget(refresh_project_button)
            current_project_layout.addLayout(project_status_controls)

            # Project scenes browser
            project_scenes_group = QGroupBox("Project Scenes")
            project_scenes_layout = QVBoxLayout(project_scenes_group)

            project_scenes_helper = QLabel("Select a scene from the project's scenes folder and open it.")
            project_scenes_helper.setStyleSheet("color: #666666; font-size: 9px; font-style: italic; padding: 2px;")
            project_scenes_layout.addWidget(project_scenes_helper)

            self.project_scenes_list = QListWidget()
            self.project_scenes_list.setAlternatingRowColors(True)
            self.project_scenes_list.setToolTip("Scenes in the current project's scenes folder")
            self.project_scenes_list.itemSelectionChanged.connect(self.update_project_scenes_controls)
            self.project_scenes_list.itemDoubleClicked.connect(self.open_selected_project_scene)
            project_scenes_layout.addWidget(self.project_scenes_list)

            project_scenes_controls = QHBoxLayout()
            refresh_project_scenes_button = QPushButton("Refresh List")
            refresh_project_scenes_button.setToolTip("Refresh the scenes list from the project's scenes folder")
            refresh_project_scenes_button.clicked.connect(lambda: self.refresh_project_scenes_list(force=True))

            open_project_scenes_browser_button = QPushButton("Open Browser")
            open_project_scenes_browser_button.setToolTip("Open the full scenes browser with file details and notes")
            open_project_scenes_browser_button.clicked.connect(self.open_project_browser)

            self.project_scenes_open_button = QPushButton("Open Selected")
            self.project_scenes_open_button.setToolTip("Open the selected scene in Maya")
            self.project_scenes_open_button.setEnabled(False)
            self.project_scenes_open_button.clicked.connect(self.open_selected_project_scene)

            project_scenes_controls.addWidget(refresh_project_scenes_button)
            project_scenes_controls.addWidget(open_project_scenes_browser_button)
            project_scenes_controls.addStretch()
            project_scenes_controls.addWidget(self.project_scenes_open_button)
            project_scenes_layout.addLayout(project_scenes_controls)

            self.project_scenes_last_path = None

            # Set existing project
            existing_project_group = QGroupBox("Set Existing Project")
            existing_project_layout = QFormLayout(existing_project_group)
            
            existing_project_path_layout = QHBoxLayout()
            self.project_set_path_input = QLineEdit()
            self.project_set_path_input.setPlaceholderText("Select an existing Maya project folder")
            self.project_set_path_input.setText(self.load_option_var(self.OPT_VAR_PROJECT_SET_PATH, ""))
            browse_existing_button = QPushButton("Browse...")
            browse_existing_button.setFixedWidth(80)
            browse_existing_button.clicked.connect(self.browse_existing_project_directory)
            existing_project_path_layout.addWidget(self.project_set_path_input)
            existing_project_path_layout.addWidget(browse_existing_button)
            
            existing_project_layout.addRow("Project Path:", existing_project_path_layout)

            set_project_button = QPushButton("Set Project")
            set_project_button.clicked.connect(self.set_existing_project)
            existing_project_layout.addRow("", set_project_button)

            # Rename project
            rename_project_group = QGroupBox("Rename Project")
            rename_project_layout = QFormLayout(rename_project_group)

            self.rename_project_new_name = QLineEdit()
            self.rename_project_new_name.setPlaceholderText("New project folder name")
            rename_project_layout.addRow("New Name:", self.rename_project_new_name)

            rename_buttons_layout = QHBoxLayout()
            rename_project_button = QPushButton("Rename Project Folder")
            rename_project_button.setToolTip("Rename the current project's folder")
            rename_project_button.clicked.connect(self.rename_current_project)
            rename_buttons_layout.addWidget(rename_project_button)
            rename_buttons_layout.addStretch()
            rename_project_layout.addRow("", rename_buttons_layout)

            # Create new project
            create_project_group = QGroupBox("Create New Project")
            create_project_layout = QFormLayout(create_project_group)
            
            project_prefix_layout = QHBoxLayout()
            self.project_prefix_letter_combo = QComboBox()
            self.project_prefix_letter_combo.addItems(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
            saved_prefix_letter = self.load_option_var(self.OPT_VAR_PROJECT_PREFIX_LETTER, "A")
            prefix_index = self.project_prefix_letter_combo.findText(saved_prefix_letter)
            if prefix_index >= 0:
                self.project_prefix_letter_combo.setCurrentIndex(prefix_index)
            self.project_prefix_letter_combo.setFixedWidth(50)
            
            self.project_prefix_number_spinbox = QSpinBox()
            self.project_prefix_number_spinbox.setRange(1, 99)
            self.project_prefix_number_spinbox.setValue(self.load_option_var(self.OPT_VAR_PROJECT_PREFIX_NUMBER, 1))
            self.project_prefix_number_spinbox.setFixedWidth(60)
            
            project_prefix_layout.addWidget(self.project_prefix_letter_combo)
            project_prefix_layout.addWidget(self.project_prefix_number_spinbox)
            project_prefix_layout.addStretch()
            
            self.project_name_input = QLineEdit()
            self.project_name_input.setPlaceholderText("Project name (e.g. HeroShot)")
            self.project_name_input.setText(self.load_option_var(self.OPT_VAR_PROJECT_NAME, ""))
            
            project_root_layout = QHBoxLayout()
            self.project_root_path_input = QLineEdit()
            self.project_root_path_input.setPlaceholderText("Root directory for the new project")
            self.project_root_path_input.setText(self.load_option_var(self.OPT_VAR_PROJECT_ROOT_PATH, ""))
            browse_root_button = QPushButton("Browse...")
            browse_root_button.setFixedWidth(80)
            browse_root_button.clicked.connect(self.browse_project_root_directory)
            project_root_layout.addWidget(self.project_root_path_input)
            project_root_layout.addWidget(browse_root_button)
            
            self.project_name_preview = QLabel("Project name preview: ")
            self.project_name_preview.setStyleSheet("color: #0066CC; font-weight: bold;")
            
            create_project_button = QPushButton("Create Project")
            create_project_button.clicked.connect(self.create_project)
            
            create_project_layout.addRow("Project Prefix:", project_prefix_layout)
            create_project_layout.addRow("Project Name:", self.project_name_input)
            create_project_layout.addRow("Project Root:", project_root_layout)
            create_project_layout.addRow("", self.project_name_preview)
            create_project_layout.addRow("", create_project_button)
            
            project_container_layout.addWidget(current_project_group)
            project_container_layout.addWidget(project_scenes_group)
            project_container_layout.addWidget(existing_project_group)
            project_container_layout.addWidget(rename_project_group)
            project_container_layout.addWidget(create_project_group)
            project_container_layout.addStretch()

            project_scroll.setWidget(project_container)
            self.project_layout.addWidget(project_scroll)
            
            self.project_prefix_letter_combo.currentIndexChanged.connect(self.update_project_name_preview)
            self.project_prefix_number_spinbox.valueChanged.connect(self.update_project_name_preview)
            self.project_name_input.textChanged.connect(self.update_project_name_preview)
            self.project_root_path_input.textChanged.connect(self.update_project_name_preview)
            self.update_project_name_preview()
            
            # --- HISTORY TAB CONTENT ---

            # Create scroll area so history tab content is accessible when docked
            history_scroll = QScrollArea()
            history_scroll.setWidgetResizable(True)
            history_scroll.setFrameShape(QFrame.NoFrame)
            history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            history_container = QWidget()
            history_container_layout = QVBoxLayout(history_container)
            history_container_layout.setContentsMargins(0, 0, 0, 0)
            history_container_layout.setSpacing(8)

            # Create Recent Files group at the top of History tab
            recent_files_group = QGroupBox("Recent Files")
            recent_files_layout = QVBoxLayout(recent_files_group)

            # Helper text for recent files
            recent_helper = QLabel("Double-click a file to open it. Hover over entries to see full path and notes.")
            recent_helper.setStyleSheet("color: #666666; font-size: 9px; font-style: italic; padding: 2px;")
            recent_files_layout.addWidget(recent_helper)

            # Recent files list
            self.recent_files_list = QListWidget()
            self.recent_files_list.setAlternatingRowColors(True)
            self.recent_files_list.setMaximumHeight(150)
            self.recent_files_list.itemDoubleClicked.connect(self.open_recent_file)
            self.populate_recent_files()
            
            # Recent files controls
            recent_controls_layout = QHBoxLayout()

            refresh_button = QPushButton("Refresh")
            refresh_button.setToolTip("Refresh the recent files list")
            refresh_button.clicked.connect(self.populate_recent_files)

            clear_recent_button = QPushButton("Clear Recent")
            clear_recent_button.setToolTip("Clear only the recent files list (keeps version history)")
            clear_recent_button.clicked.connect(self.clear_recent_files)

            open_button = QPushButton("Open Selected")
            open_button.setToolTip("Open the selected file in Maya")
            open_button.clicked.connect(self.open_selected_file)

            recent_controls_layout.addWidget(refresh_button)
            recent_controls_layout.addWidget(clear_recent_button)
            recent_controls_layout.addStretch()
            recent_controls_layout.addWidget(open_button)

            recent_files_layout.addWidget(self.recent_files_list)
            recent_files_layout.addLayout(recent_controls_layout)
            
            # Create a table for version history
            version_history_group = QGroupBox("Version History")
            version_history_layout = QVBoxLayout(version_history_group)

            # Helper text for version history
            history_helper = QLabel("Shows all saved versions of the current file. Select a row and click 'View Notes' to see or edit notes in a larger window.")
            history_helper.setStyleSheet("color: #666666; font-size: 9px; font-style: italic; padding: 2px;")
            version_history_layout.addWidget(history_helper)

            self.history_table = QTableWidget()
            self.history_table.setColumnCount(4)
            self.history_table.setHorizontalHeaderLabels(["Filename", "Date", "Path", "Notes"])
            self.history_table.setAlternatingRowColors(True)
            self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)  # Make read-only
            self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
            self.history_table.setSelectionMode(QTableWidget.SingleSelection)
            self.history_table.itemDoubleClicked.connect(self.open_history_file_double_click)
            
            # Adjust column widths
            header = self.history_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            
            # History controls
            history_controls = QHBoxLayout()

            refresh_history_button = QPushButton("Refresh")
            refresh_history_button.setToolTip("Refresh the version history table")
            refresh_history_button.clicked.connect(self.populate_history)

            clear_history_button = QPushButton("Clear History")
            clear_history_button.setToolTip("Clear all version history data (cannot be undone)")
            clear_history_button.clicked.connect(self.clear_history)

            # Project Browser button - shows all files in project scenes folder
            browse_project_button = QPushButton("Browse Project")
            browse_project_button.setToolTip("Browse all scene files in the project's scenes folder")
            browse_project_button.clicked.connect(self.open_project_browser)

            open_history_button = QPushButton("Open Selected")
            open_history_button.setToolTip("Open the selected version in Maya")
            open_history_button.clicked.connect(self.open_selected_history_file)

            view_notes_button = QPushButton("View Notes")
            view_notes_button.setToolTip("View or edit notes for the selected version in a larger window")
            view_notes_button.clicked.connect(self.view_history_notes)

            export_history_button = QPushButton("Export History")
            export_history_button.setToolTip("Export version history to a text file for backup or review")
            export_history_button.clicked.connect(self.export_history)

            history_controls.addWidget(refresh_history_button)
            history_controls.addWidget(clear_history_button)
            history_controls.addWidget(browse_project_button)
            history_controls.addStretch()
            history_controls.addWidget(view_notes_button)
            history_controls.addWidget(open_history_button)
            history_controls.addWidget(export_history_button)
            
            # Add to version history layout
            version_history_layout.addWidget(self.history_table)
            version_history_layout.addLayout(history_controls)
            
            # Add both sections to history container, then add scroll area to tab
            history_container_layout.addWidget(recent_files_group)
            history_container_layout.addWidget(version_history_group)

            history_scroll.setWidget(history_container)
            self.history_layout.addWidget(history_scroll)
            
            # --- PREFERENCES TAB CONTENT ---

            # Create a scroll area for preferences
            pref_scroll = QScrollArea()
            pref_scroll.setWidgetResizable(True)
            pref_scroll.setFrameShape(QFrame.NoFrame)
            pref_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            pref_container = QWidget()
            pref_container_layout = QVBoxLayout(pref_container)
            pref_container_layout.setContentsMargins(5, 5, 5, 5)
            pref_container_layout.setSpacing(15)

            # Helper function to create description labels
            def create_help_label(text):
                help_label = QLabel(text)
                help_label.setStyleSheet("color: #888888; font-size: 10px; padding-left: 20px; padding-bottom: 8px;")
                help_label.setWordWrap(True)
                return help_label

            # Helper function to create section headers
            def create_section_header(text):
                header = QLabel(text)
                header.setStyleSheet("""
                    font-size: 12px;
                    font-weight: bold;
                    color: #CCCCCC;
                    padding: 8px 0px 4px 0px;
                    border-bottom: 1px solid #444444;
                """)
                return header

            # ============================================================
            # SAVING BEHAVIOR SECTION
            # ============================================================
            saving_group = QGroupBox("Saving Behavior")
            saving_group.setToolTip("Configure how SavePlus handles file saving operations")
            saving_layout = QVBoxLayout(saving_group)
            saving_layout.setSpacing(2)

            # Default file type preference
            filetype_layout = QHBoxLayout()
            filetype_label = QLabel("Default File Type:")
            filetype_label.setFixedWidth(150)
            filetype_label.setToolTip("The file format used when saving new files")
            self.pref_default_filetype = QComboBox()
            self.pref_default_filetype.addItems(["Maya ASCII (.ma)", "Maya Binary (.mb)"])
            self.pref_default_filetype.setToolTip("Maya ASCII (.ma): Human-readable, larger file size, better for version control\nMaya Binary (.mb): Smaller file size, faster to save/load")
            filetype_layout.addWidget(filetype_label)
            filetype_layout.addWidget(self.pref_default_filetype)
            filetype_layout.addStretch()
            saving_layout.addLayout(filetype_layout)
            saving_layout.addWidget(create_help_label("Maya ASCII is recommended for projects using version control. Binary files are smaller and faster."))

            # Auto-increment version
            self.pref_auto_increment = QCheckBox("Auto-increment version number on Save Plus")
            self.pref_auto_increment.setChecked(True)
            self.pref_auto_increment.setToolTip("Automatically increase the version number (v01 → v02) when using Save Plus")
            saving_layout.addWidget(self.pref_auto_increment)
            saving_layout.addWidget(create_help_label("When enabled, clicking 'Save Plus' will automatically increment the version number in your filename."))

            # Show save confirmation
            self.pref_show_confirmation = QCheckBox("Show confirmation dialog after saving")
            self.pref_show_confirmation.setChecked(False)
            self.pref_show_confirmation.setToolTip("Display a confirmation message after each successful save")
            saving_layout.addWidget(self.pref_show_confirmation)
            saving_layout.addWidget(create_help_label("Enable this to see a popup confirmation after each save operation."))

            pref_container_layout.addWidget(saving_group)

            # ============================================================
            # SAVE REMINDERS SECTION
            # ============================================================
            reminders_group = QGroupBox("Save Reminders")
            reminders_group.setToolTip("Configure automatic save reminder notifications")
            reminders_layout = QVBoxLayout(reminders_group)
            reminders_layout.setSpacing(2)

            # Auto-save interval
            interval_layout = QHBoxLayout()
            interval_label = QLabel("Reminder Interval:")
            interval_label.setFixedWidth(150)
            interval_label.setToolTip("How often to show a save reminder when working")
            self.pref_auto_save_interval = QSpinBox()
            self.pref_auto_save_interval.setRange(1, 60)
            self.pref_auto_save_interval.setValue(15)
            self.pref_auto_save_interval.setSuffix(" minutes")
            self.pref_auto_save_interval.setToolTip("Time between save reminders (1-60 minutes)")
            self.pref_auto_save_interval.setFixedWidth(100)
            interval_layout.addWidget(interval_label)
            interval_layout.addWidget(self.pref_auto_save_interval)
            interval_layout.addStretch()
            reminders_layout.addLayout(interval_layout)
            reminders_layout.addWidget(create_help_label("When save reminders are enabled, you'll be notified after this amount of time passes without saving."))

            # Enable save sound
            self.pref_enable_sound = QCheckBox("Play sound with save reminders")
            self.pref_enable_sound.setChecked(False)
            self.pref_enable_sound.setToolTip("Play an audio notification when a save reminder appears")
            reminders_layout.addWidget(self.pref_enable_sound)
            reminders_layout.addWidget(create_help_label("Enable this to hear an audio alert when it's time to save your work."))

            pref_container_layout.addWidget(reminders_group)

            # ============================================================
            # AUTOMATIC BACKUP SECTION
            # ============================================================
            backup_group = QGroupBox("Automatic Backups")
            backup_group.setToolTip("Configure automatic backup creation")
            backup_layout = QVBoxLayout(backup_group)
            backup_layout.setSpacing(2)

            # Enable auto-backup
            self.pref_enable_auto_backup = QCheckBox("Enable automatic backups")
            self.pref_enable_auto_backup.setChecked(self.load_option_var(self.OPT_VAR_ENABLE_AUTO_BACKUP, False))
            self.pref_enable_auto_backup.setToolTip("Automatically version up and save a backup copy of your scene at regular intervals")
            backup_layout.addWidget(self.pref_enable_auto_backup)
            backup_layout.addWidget(create_help_label("When enabled, SavePlus will automatically create backup copies of your scene at the specified interval."))

            # Backup interval
            backup_interval_layout = QHBoxLayout()
            backup_interval_label = QLabel("Backup Interval:")
            backup_interval_label.setFixedWidth(150)
            backup_interval_label.setToolTip("How often to create automatic backups")
            self.pref_backup_interval = QSpinBox()
            self.pref_backup_interval.setRange(5, 120)
            self.pref_backup_interval.setValue(self.load_option_var(self.OPT_VAR_BACKUP_INTERVAL, 30))
            self.pref_backup_interval.setSuffix(" minutes")
            self.pref_backup_interval.setToolTip("Time between automatic backups (5-120 minutes)")
            self.pref_backup_interval.setFixedWidth(100)
            backup_interval_layout.addWidget(backup_interval_label)
            backup_interval_layout.addWidget(self.pref_backup_interval)
            backup_interval_layout.addStretch()
            backup_layout.addLayout(backup_interval_layout)
            backup_layout.addWidget(create_help_label("Backups are saved by versioning up the existing filename (e.g. scene_122.ma → scene_123.ma)."))

            # Max backups to keep
            max_backup_layout = QHBoxLayout()
            max_backup_label = QLabel("Maximum Backups:")
            max_backup_label.setFixedWidth(150)
            max_backup_label.setToolTip("Maximum number of backup files to keep per scene")
            self.pref_max_backups = QSpinBox()
            self.pref_max_backups.setRange(1, 50)
            self.pref_max_backups.setValue(self.load_option_var(self.OPT_VAR_MAX_BACKUPS, 10))
            self.pref_max_backups.setToolTip("Older backups will be automatically deleted when this limit is reached (1-50)")
            self.pref_max_backups.setFixedWidth(100)
            max_backup_layout.addWidget(max_backup_label)
            max_backup_layout.addWidget(self.pref_max_backups)
            max_backup_layout.addStretch()
            backup_layout.addLayout(max_backup_layout)
            backup_layout.addWidget(create_help_label("Old backups are automatically deleted when this limit is exceeded. Set to 0 to keep all backups."))

            # Custom backup location
            backup_path_layout = QHBoxLayout()
            backup_path_label = QLabel("Backup Location:")
            backup_path_label.setFixedWidth(150)
            backup_path_label.setToolTip("Custom folder for storing backup files (leave empty to use scene folder)")
            self.pref_backup_location = QLineEdit()
            self.pref_backup_location.setPlaceholderText("Leave empty to save backups with scene file")
            self.pref_backup_location.setToolTip("Optional: Specify a custom folder for all backup files")
            backup_browse = QPushButton("Browse...")
            backup_browse.setFixedWidth(80)
            backup_browse.clicked.connect(self.browse_backup_location)
            backup_path_layout.addWidget(backup_path_label)
            backup_path_layout.addWidget(self.pref_backup_location)
            backup_path_layout.addWidget(backup_browse)
            backup_layout.addLayout(backup_path_layout)
            backup_layout.addWidget(create_help_label("If left empty, backups are created in the same folder as the original scene file."))

            pref_container_layout.addWidget(backup_group)

            # ============================================================
            # VERSION NOTES SECTION
            # ============================================================
            notes_group = QGroupBox("Version Notes")
            notes_group.setToolTip("Configure version notes and quick note behavior")
            notes_layout = QVBoxLayout(notes_group)
            notes_layout.setSpacing(2)

            # Clear quick note after save
            self.pref_clear_quick_note = QCheckBox("Clear quick note field after saving")
            self.pref_clear_quick_note.setChecked(self.load_option_var(self.OPT_VAR_CLEAR_QUICK_NOTE, True))
            self.pref_clear_quick_note.setToolTip("Automatically clear the quick note input field after a successful save")
            notes_layout.addWidget(self.pref_clear_quick_note)
            notes_layout.addWidget(create_help_label("When enabled, the quick note field will be cleared after each save so you can enter a fresh note."))

            # Max history entries
            history_layout = QHBoxLayout()
            history_label = QLabel("Max History Entries:")
            history_label.setFixedWidth(150)
            history_label.setToolTip("Maximum number of version history entries to display")
            self.pref_max_history = QSpinBox()
            self.pref_max_history.setRange(10, 500)
            self.pref_max_history.setValue(self.load_option_var(self.OPT_VAR_MAX_HISTORY_ENTRIES, 100))
            self.pref_max_history.setToolTip("Number of previous versions to show in the History tab (10-500)")
            self.pref_max_history.setFixedWidth(100)
            history_layout.addWidget(history_label)
            history_layout.addWidget(self.pref_max_history)
            history_layout.addStretch()
            notes_layout.addLayout(history_layout)
            notes_layout.addWidget(create_help_label("Controls how many version entries are displayed in the History tab. Higher values may slow down loading."))

            pref_container_layout.addWidget(notes_group)

            # ============================================================
            # FILE PATHS SECTION
            # ============================================================
            paths_group = QGroupBox("File Paths")
            paths_group.setToolTip("Configure default directories for saving files")
            paths_layout = QVBoxLayout(paths_group)
            paths_layout.setSpacing(2)

            # Default save location
            default_path_layout = QHBoxLayout()
            default_path_label = QLabel("Default Save Location:")
            default_path_label.setFixedWidth(150)
            default_path_label.setToolTip("The default directory used when saving new files")
            self.pref_default_path = QLineEdit()
            self.pref_default_path.setPlaceholderText("Default directory for saving files")
            self.pref_default_path.setToolTip("Files will be saved to this directory by default when no project is set")
            browse_default_button = QPushButton("Browse...")
            browse_default_button.setFixedWidth(80)
            browse_default_button.clicked.connect(self.browse_default_save_location)
            default_path_layout.addWidget(default_path_label)
            default_path_layout.addWidget(self.pref_default_path)
            default_path_layout.addWidget(browse_default_button)
            paths_layout.addLayout(default_path_layout)
            paths_layout.addWidget(create_help_label("This path is used when saving a new file and no Maya project is set."))

            # Project directory
            project_path_layout = QHBoxLayout()
            project_path_label = QLabel("Project Directory:")
            project_path_label.setFixedWidth(150)
            project_path_label.setToolTip("The Maya project directory")
            self.pref_project_path = QLineEdit()
            self.pref_project_path.setPlaceholderText("Maya project directory")
            self.pref_project_path.setToolTip("When 'Respect Project Structure' is enabled, files are saved relative to this project")
            project_browse = QPushButton("Browse...")
            project_browse.setFixedWidth(80)
            project_browse.clicked.connect(self.browse_project_directory)
            project_path_layout.addWidget(project_path_label)
            project_path_layout.addWidget(self.pref_project_path)
            project_path_layout.addWidget(project_browse)
            paths_layout.addLayout(project_path_layout)
            paths_layout.addWidget(create_help_label("The Maya project directory. Use the Project tab to manage and switch projects."))

            pref_container_layout.addWidget(paths_group)

            # ============================================================
            # USER INTERFACE SECTION
            # ============================================================
            ui_group = QGroupBox("User Interface")
            ui_group.setToolTip("Configure SavePlus interface behavior and default states")
            ui_layout = QVBoxLayout(ui_group)
            ui_layout.setSpacing(2)

            ui_layout.addWidget(create_section_header("Default Section States"))
            ui_layout.addWidget(create_help_label("Choose which sections should be expanded when SavePlus opens:"))

            # Default sections expanded
            self.pref_file_expanded = QCheckBox("File Options section expanded by default")
            self.pref_file_expanded.setChecked(True)
            self.pref_file_expanded.setToolTip("Show the File Options section expanded when SavePlus opens")
            ui_layout.addWidget(self.pref_file_expanded)

            self.pref_name_expanded = QCheckBox("Name Generator section expanded by default")
            self.pref_name_expanded.setChecked(True)
            self.pref_name_expanded.setToolTip("Show the Name Generator section expanded when SavePlus opens")
            ui_layout.addWidget(self.pref_name_expanded)

            self.pref_log_expanded = QCheckBox("Log Output section expanded by default")
            self.pref_log_expanded.setChecked(False)
            self.pref_log_expanded.setToolTip("Show the Log Output section expanded when SavePlus opens")
            ui_layout.addWidget(self.pref_log_expanded)

            ui_layout.addWidget(create_help_label("Collapsed sections help keep the interface compact. Click the section header to expand/collapse."))

            pref_container_layout.addWidget(ui_group)

            # ============================================================
            # ABOUT SECTION
            # ============================================================
            about_group = QGroupBox("About SavePlus")
            about_group.setToolTip("Information about SavePlus")
            about_layout = QVBoxLayout(about_group)

            version_label = QLabel("Version: 2.0.4")
            version_label.setStyleSheet("color: #AAAAAA; font-size: 11px;")
            about_layout.addWidget(version_label)

            about_text = QLabel("SavePlus is a comprehensive file versioning and project management tool for Maya.\n\nFeatures include automatic version incrementing, save reminders, automatic backups, version notes, project management, and more.")
            about_text.setStyleSheet("color: #888888; font-size: 10px;")
            about_text.setWordWrap(True)
            about_layout.addWidget(about_text)

            pref_container_layout.addWidget(about_group)

            # Add spacer at the bottom
            pref_container_layout.addStretch()

            # Set the container as the scroll area widget
            pref_scroll.setWidget(pref_container)
            self.preferences_layout.addWidget(pref_scroll)

            # Add "Apply Settings" and "Reset to Defaults" buttons
            button_layout = QHBoxLayout()

            reset_button = QPushButton("Reset to Defaults")
            reset_button.setFixedWidth(120)
            reset_button.setToolTip("Reset all preferences to their default values")
            reset_button.clicked.connect(self.reset_preferences_to_defaults)

            apply_button = QPushButton("Apply Settings")
            apply_button.setFixedWidth(120)
            apply_button.setToolTip("Save all preference changes")
            apply_button.clicked.connect(self.save_preferences)
            apply_button.setStyleSheet("""
                QPushButton {
                    background-color: #0066CC;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0077DD;
                }
            """)

            button_layout.addWidget(reset_button)
            button_layout.addStretch()
            button_layout.addWidget(apply_button)

            self.preferences_layout.addLayout(button_layout)
            
            # Update filename preview initially
            self.update_filename_preview()
            self.update_version_preview()
            
            # Setup log redirector
            self.log_redirector = savePlus_ui_components.LogRedirector(self.log_text)
            self.log_redirector.start_redirect()
            
            # Initialize project tracking
            self.project_directory = savePlus_core.get_maya_project_directory()
            self.update_project_display()
            self.refresh_project_scenes_list(force=True)

            # Connect to Maya's workspaceChanged event to update when project changes
            self.workspace_change_callback = None
            try:
                self.workspace_change_callback = cmds.scriptJob(
                    event=["workspaceChanged", self.on_workspace_changed],
                    protected=True
                )
                print(f"[SavePlus Debug] Connected to workspace change event")
            except Exception as e:
                print(f"[SavePlus Debug] Could not connect to workspace change event: {e}")

            # Log initialization message
            print("SavePlus UI initialized successfully")
            
           # Setup timer for save reminders - MAKE SURE THIS IS IN __init__
            self.timer_job_id = None  # Initialize scriptJob ID
            self.last_save_time = time.time()
            self.last_timer_check = time.time()
            self.save_timer = QTimer()  # Create without parent for Maya compatibility
            self.save_timer.setTimerType(QtCore.Qt.CoarseTimer)  # More reliable timer type
            self.save_timer.timeout.connect(self.check_save_time)
            print("[SavePlus Debug] Qt timer created (not started)")

            # Enable this timer in Maya's event loop - KEEP THIS IMPORTANT CODE
            if hasattr(self, 'save_timer'):
                omui = savePlus_maya.get_open_maya_ui()
                if omui:
                    print("[SavePlus Debug] Connected timer to Maya's event loop")
                else:
                    print("[SavePlus Debug] Using standard Qt timer (Maya UI unavailable)")

            # Load timer preference without triggering stateChanged
            timer_enabled = self.load_option_var(self.OPT_VAR_ENABLE_TIMED_WARNING, False)
            print(f"[SavePlus Debug] Loaded timer preference: enabled={timer_enabled}")

            # Set checkbox state without triggering signals
            self.enable_timed_warning.blockSignals(True)
            self.enable_timed_warning.setChecked(timer_enabled)
            self.enable_timed_warning.blockSignals(False)

            # Schedule timer setup if enabled in preferences (delay to ensure UI is ready)
            if timer_enabled:
                print("[SavePlus Debug] Timer enabled in preferences, scheduling activation")
                QtCore.QTimer.singleShot(1000, self.setup_timer)
            else:
                print("[SavePlus Debug] Timer disabled in preferences")

            # Setup timer for auto-backup
            self.last_backup_time = time.time()
            self.backup_timer = QTimer(self)
            self.backup_timer.timeout.connect(self.check_backup_time)

            # Flag to track first-time save
            self.is_first_save = not current_file

            if self.pref_enable_auto_backup.isChecked():
                self.backup_timer.start(60000)  # Check every minute

            # Connect tab changed signal to update history
            self.tab_widget.currentChanged.connect(self.on_tab_changed)

            # Load preferences
            self.load_preferences()

            # Schedule initial window sizing after UI is fully constructed
            QtCore.QTimer.singleShot(200, self.adjust_window_size)

            # Initial population of history
            self.populate_history()

            # Initialize the timer system after UI is loaded
            QtCore.QTimer.singleShot(2000, self.bootstrap_timer)

            # Force multiple initial timer checks to verify operation
            if self.enable_timed_warning.isChecked():
                print("\n" + "#"*70)
                print("## STARTING TIMER VERIFICATION SEQUENCE")
                print("#"*70 + "\n")
                
                # Reset the counter
                if not hasattr(SavePlusUI, 'TIMER_COUNT'):
                    SavePlusUI.TIMER_COUNT = 0
                SavePlusUI.TIMER_COUNT = 0
                
                # Simulate last save being 4 minutes ago for immediate testing
                print("[SavePlus Debug] Setting up timer for immediate testing")
                self.last_save_time = time.time() - (4 * 60)
                
                # Schedule multiple checks at different intervals
                QtCore.QTimer.singleShot(1000, lambda: print("\n[VERIFY] Scheduling initial timer check #1"))
                QtCore.QTimer.singleShot(1500, self.check_save_time)
                
                QtCore.QTimer.singleShot(6000, lambda: print("\n[VERIFY] Scheduling initial timer check #2"))
                QtCore.QTimer.singleShot(6500, self.check_save_time)
                
                QtCore.QTimer.singleShot(11000, lambda: print("\n[VERIFY] Scheduling initial timer check #3"))
                QtCore.QTimer.singleShot(11500, self.check_save_time)
                
                # Force UI update
                QtCore.QTimer.singleShot(16000, lambda: print("[SavePlus Debug] Timer verification sequence complete"))
                
                # Setup a more robust timer initialization
                self.save_timer = QTimer()
                self.save_timer.setTimerType(QtCore.Qt.CoarseTimer)
                self.save_timer.timeout.connect(self.check_save_time)
                print("[DEBUG] Qt timer created with proper signal connection")

                # Set up file monitoring
                self.setup_file_monitoring()

                # Load the timer state from preferences without triggering toggle
                timer_enabled = self.load_option_var(self.OPT_VAR_ENABLE_TIMED_WARNING, False)
                if timer_enabled:
                    print("[DEBUG] Timer should be enabled from preferences")
                    # Block signals to prevent immediate toggle
                    self.enable_timed_warning.blockSignals(True)
                    self.enable_timed_warning.setChecked(True)
                    self.enable_timed_warning.blockSignals(False)
                    # Start timer after a delay
                    QtCore.QTimer.singleShot(1000, lambda: self.toggle_timed_warning(2))

                # Check if we're starting with a new file and reset UI appropriately
                if not cmds.file(query=True, sceneName=True):
                    print("[SavePlus Debug] Starting with a new file - initializing UI accordingly")
                    # Use a slight delay to ensure UI is fully initialized
                    QtCore.QTimer.singleShot(100, self.reset_for_new_file)

                # Force check for new file on startup with slight delay to ensure UI is ready
                QtCore.QTimer.singleShot(500, self.force_reset_project_display)

                # Create a periodic check for new files
                self.new_file_timer = QTimer()
                self.new_file_timer.setInterval(1000)  # Check every second
                self.new_file_timer.timeout.connect(lambda: self.force_reset_project_display() 
                                                if not cmds.file(query=True, sceneName=True) else None)
                self.new_file_timer.start()

        except Exception as e:
            error_message = f"Error initializing SavePlus UI: {str(e)}"
            print(error_message)
            traceback.print_exc()
            cmds.confirmDialog(title="SavePlus Error", 
                            message=f"Error loading SavePlus: {str(e)}\n\nCheck script editor for details.", 
                            button=["OK"], defaultButton="OK")

    def update_filename_display(self, full_path):
        """Update the filename input to show only the basename while storing the full path"""
        self.current_full_path = full_path
        basename = os.path.basename(full_path) if full_path else ""
        self.filename_input.setText(basename)
        self.filename_input.setToolTip(full_path)  # Show full path on hover
        self.update_filename_preview()
        self.update_version_preview()

    def update_reminder_interval(self, value):
        """Update the save reminder interval"""
        # Save the new interval to preferences
        cmds.optionVar(iv=(self.OPT_VAR_AUTO_SAVE_INTERVAL, value))
        
        # Update the value in the preferences tab to keep them in sync
        if hasattr(self, 'pref_auto_save_interval'):
            self.pref_auto_save_interval.setValue(value)
        
        print(f"Save reminder interval updated to {value} minutes")

    def closeEvent(self, event):
        """Handle clean up when window is closed"""
        savePlus_core.debug_print("Closing SavePlus UI")
        try:
            # Stop redirecting output
            if hasattr(self, 'log_redirector') and self.log_redirector:
                self.log_redirector.stop_redirect()
            
            # Stop Qt timer
            if hasattr(self, 'save_timer') and self.save_timer.isActive():
                self.save_timer.stop()
                print("[DEBUG] Stopped Qt timer during close")
                
            # Kill any active scriptJobs
            if hasattr(self, 'timer_job_id') and self.timer_job_id is not None:
                try:
                    cmds.scriptJob(kill=self.timer_job_id)
                    print(f"[DEBUG] Killed timer scriptJob during close: {self.timer_job_id}")
                    self.timer_job_id = None
                except Exception as e:
                    print(f"[DEBUG] Error killing scriptJob during close: {e}")
            
            # Kill file open job
            if hasattr(self, 'file_open_job') and self.file_open_job is not None:
                try:
                    cmds.scriptJob(kill=self.file_open_job)
                    print(f"[DEBUG] Killed file open scriptJob during close")
                except Exception as e:
                    print(f"[DEBUG] Error killing file open scriptJob: {e}")
            
            # Kill new scene job
            if hasattr(self, 'new_scene_job') and self.new_scene_job is not None:
                try:
                    cmds.scriptJob(kill=self.new_scene_job)
                    print(f"[DEBUG] Killed new scene scriptJob during close")
                except Exception as e:
                    print(f"[DEBUG] Error killing new scene scriptJob: {e}")
            
            # Stop backup timer
            if hasattr(self, 'backup_timer') and self.backup_timer:
                self.backup_timer.stop()
            
            # Disable auto resize to prevent errors during shutdown
            self.auto_resize_enabled = False
        except Exception as e:
            savePlus_core.debug_print(f"Error during close: {e}")
        
        super(SavePlusUI, self).closeEvent(event)
    
    def create_menu_bar(self):
        """Create the menu bar with all menu items"""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        save_plus_action = QAction("Save Plus", self)
        save_plus_action.setShortcut("Ctrl+S")
        save_plus_action.triggered.connect(self.save_plus)
        file_menu.addAction(save_plus_action)
        
        save_as_action = QAction("Save As New", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_as_new)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        backup_action = QAction("Create Backup", self)
        backup_action.setShortcut("Ctrl+B")
        backup_action.triggered.connect(self.create_backup)
        file_menu.addAction(backup_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("Export Version History", self)
        export_action.triggered.connect(self.export_history)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Edit menu
        edit_menu = menu_bar.addMenu("Edit")
        
        reset_project_display_action = QAction("Reset Project Display", self)
        reset_project_display_action.triggered.connect(self.force_reset_project_display)
        edit_menu.addAction(reset_project_display_action)

        prefs_action = QAction("Preferences", self)
        prefs_action.triggered.connect(self.show_preferences)
        edit_menu.addAction(prefs_action)
        
        # Help menu
        self.create_help_menu(menu_bar)
    
    def create_help_menu(self, menu_bar):
        """
        Create a help menu that links only to currently available pages on mayasaveplus.com
        """
        import webbrowser
        
        # Create Help menu
        help_menu = menu_bar.addMenu("Help")
        
        # Documentation
        documentation_action = QAction("Documentation", self)
        documentation_action.triggered.connect(lambda: webbrowser.open("https://mayasaveplus.com/documentation.html"))
        help_menu.addAction(documentation_action)
        
        # Features
        features_action = QAction("Features", self)
        features_action.triggered.connect(lambda: webbrowser.open("https://mayasaveplus.com/features.html"))
        help_menu.addAction(features_action)
        
        # Changelog
        changelog_action = QAction("Changelog", self)
        changelog_action.triggered.connect(lambda: webbrowser.open("https://mayasaveplus.com/changelog.html"))
        help_menu.addAction(changelog_action)
        
        help_menu.addSeparator()
        
        # Downloads - for updates
        download_action = QAction("Check for Updates", self)
        download_action.triggered.connect(lambda: webbrowser.open("https://mayasaveplus.com/download.html"))
        help_menu.addAction(download_action)
        
        help_menu.addSeparator()
        
        # Support submenu - with email only for now
        support_menu = help_menu.addMenu("Support")
        
        # Email support
        email_support_action = QAction("Email Support", self)
        email_support_action.triggered.connect(lambda: webbrowser.open("mailto:support@mayasaveplus.com?subject=SavePlus%20Support%20Request"))
        support_menu.addAction(email_support_action)
        
        help_menu.addSeparator()
        
        # Visit website (homepage)
        website_action = QAction("Visit SavePlus Website", self)
        website_action.triggered.connect(lambda: webbrowser.open("https://mayasaveplus.com/index.html"))
        help_menu.addAction(website_action)
        
        # Built-in documentation viewer
        builtin_docs_action = QAction("Show Offline Documentation...", self)
        builtin_docs_action.triggered.connect(self.show_offline_documentation)
        help_menu.addAction(builtin_docs_action)
        
        # Keyboard shortcuts reference
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        # About SavePlus
        about_action = QAction("About SavePlus", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        return help_menu

    def check_for_updates(self):
        """Check for updates to SavePlus"""
        import webbrowser
        
        # Current version from the tool
        current_version = VERSION
        
        # Show checking dialog
        cmds.confirmDialog(
            title="Check for Updates",
            message=f"Current version: {current_version}\n\nChecking for updates requires an internet connection and will open your web browser.",
            button=["Check Now", "Cancel"],
            defaultButton="Check Now",
            cancelButton="Cancel",
            dismissString="Cancel"
        )
        
        # Open the updates page on the custom domain
        webbrowser.open("https://www.mayasaveplus.com/updates")
        
        self.status_bar.showMessage("Checking for updates...", 3000)

    def show_offline_documentation(self):
        """Display offline documentation in a dialog window"""
        try:
            import os
            from PySide6.QtCore import QUrl
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWidgets import QDialog, QVBoxLayout
            
            # Find the documentation HTML file path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            doc_path = os.path.join(script_dir, "docs", "documentation.html")
            
            # Fallback if not found
            if not os.path.exists(doc_path):
                # Check in parent directory
                doc_path = os.path.join(os.path.dirname(script_dir), "documentation.html")
                
                if not os.path.exists(doc_path):
                    self.status_bar.showMessage("Documentation file not found", 5000)
                    print(f"Documentation file not found at {doc_path}")
                    
                    # Ask if they want to open online docs instead
                    response = cmds.confirmDialog(
                        title="Documentation Not Found",
                        message="Local documentation file could not be found.\nWould you like to open the online documentation instead?",
                        button=["Yes", "No"],
                        defaultButton="Yes",
                        cancelButton="No"
                    )
                    
                    if response == "Yes":
                        import webbrowser
                        webbrowser.open("https://mayasaveplus.com/documentation.html")
                    
                    return
            
            try:
                # Create documentation viewer dialog
                doc_dialog = QDialog(self)
                doc_dialog.setWindowTitle("SavePlus Documentation")
                doc_dialog.resize(900, 700)
                
                layout = QVBoxLayout(doc_dialog)
                
                # Create web view
                web_view = QWebEngineView()
                web_view.load(QUrl.fromLocalFile(doc_path))
                
                layout.addWidget(web_view)
                doc_dialog.setLayout(layout)
                
                doc_dialog.exec()
            except ImportError:
                # If QtWebEngineWidgets is not available, open in external browser
                import webbrowser
                webbrowser.open(f"file://{doc_path}")
                
        except Exception as e:
            self.status_bar.showMessage(f"Error showing documentation: {e}", 5000)
            print(f"Error showing documentation: {e}")
            import traceback
            traceback.print_exc()

    def show_shortcuts(self):
        """Display a dialog with keyboard shortcuts"""
        shortcuts = [
            ("Ctrl+S", "Save Plus - Increment the current file"),
            ("Ctrl+Shift+S", "Save As New - Save with a new name"),
            ("Ctrl+B", "Create Backup - Save a versioned backup copy"),
        ]
        
        # Create message with shortcuts
        message = "SavePlus Keyboard Shortcuts:\n\n"
        for key, desc in shortcuts:
            message += f"{key:<15} - {desc}\n"
        
        # Show dialog
        cmds.confirmDialog(
            title="Keyboard Shortcuts",
            message=message,
            button=["OK"],
            defaultButton="OK"
        )

    def clear_log(self):
        """Clear the log display"""
        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.clear()
    
    def browse_file(self):
        """Open file browser to select save location directory"""
        print("Opening file browser for save location directory...")
        
        # Determine the starting directory for the browser
        default_path = ""
        
        # Check if we should use project directory
        if hasattr(self, 'respect_project_structure') and self.respect_project_structure.isChecked() and self.project_directory:
            default_path = self.project_directory
            print(f"Using project directory as starting point: {default_path}")
        # Then check if we should use current file directory
        elif self.use_current_dir.isChecked():
            current_file = cmds.file(query=True, sceneName=True)
            if current_file:
                default_path = os.path.dirname(current_file)
                print(f"Using current file directory as starting point: {default_path}")
        # Fall back to default path from preferences if available
        elif hasattr(self, 'pref_default_path') and self.pref_default_path.text():
            default_path = self.pref_default_path.text()
            print(f"Using default path from preferences: {default_path}")
        
        directory = QFileDialog.getExistingDirectory(
            self, "Select Save Location Directory", default_path
        )
        
        if directory:
            # Store the directory path but keep the current filename
            current_filename = os.path.basename(self.filename_input.text())
            
            # If we have a filename, combine with the new directory
            if current_filename:
                new_path = os.path.join(directory, current_filename)
                self.update_filename_display(new_path)
                self.filename_input.setText(os.path.basename(new_path))
                self.filename_input.setToolTip(new_path)  # Show full path on hover
                print(f"Selected directory: {directory}")
                print(f"Updated path: {new_path}")
            else:
                # If no filename set yet, just remember the directory for later
                self.selected_directory = directory
                print(f"Selected directory: {directory}")
                self.status_bar.showMessage(f"Directory set to: {directory}", 5000)
            
            # Check if selected directory is in a Maya project
            for proj_path in [self.project_directory, cmds.workspace(q=True, rd=True)]:
                if proj_path and directory.startswith(proj_path):
                    print(f"[SavePlus Debug] Selected directory is within project: {proj_path}")
                    # Ensure project display is updated
                    self.update_project_tracking()
                    break

            # Uncheck the "use current directory" option since we've specified a custom one
            self.use_current_dir.setChecked(False)
            
            self.update_filename_preview()
            
            # Update save location display
            self.update_save_location_display()

    def update_save_location_display(self):
        """Update the display of the current save location"""
        if hasattr(self, 'save_location_label'):
            # Use the new get_save_directory method to determine save location
            save_dir = self.get_save_directory()

            # Display truncated path but set full path as tooltip
            truncated_path = truncate_path(save_dir, 40)  # Adjust max_length as needed
            self.save_location_label.setText(truncated_path)
            self.save_location_label.setToolTip(f"Full path: {save_dir}\n\nClick the folder icon to open this location.")

            # Update style based on whether it's a project path - use dark background for consistency
            if self.project_directory and savePlus_core.is_path_in_project(save_dir, self.project_directory):
                # Green text for project paths with dark background
                self.save_location_label.setStyleSheet("color: #4CAF50; font-size: 10px; background-color: transparent; padding: 3px; border-radius: 2px;")
            else:
                # Blue text for non-project paths with dark background
                self.save_location_label.setStyleSheet("color: #0066CC; font-size: 10px; background-color: transparent; padding: 3px; border-radius: 2px;")

    def browse_default_save_location(self):
        """Open file browser to select default save location directory"""
        print("Opening file browser for default save location...")
        current_path = self.pref_default_path.text()
        directory = QFileDialog.getExistingDirectory(
            self, "Select Default Save Location", current_path
        )
        
        if directory:
            self.pref_default_path.setText(directory)
            print(f"Default save location set to: {directory}")
            self.status_bar.showMessage(f"Default save location set to: {directory}", 5000)
    
    def browse_project_directory(self):
        """Open file browser to select project directory"""
        print("Opening file browser for project directory...")
        current_path = self.pref_project_path.text()
        directory = QFileDialog.getExistingDirectory(
            self, "Select Project Directory", current_path
        )

        if directory:
            self.pref_project_path.setText(directory)
            print(f"Project directory set to: {directory}")
            self.status_bar.showMessage(f"Project directory set to: {directory}", 5000)

    def browse_backup_location(self):
        """Open file browser to select custom backup location directory"""
        print("Opening file browser for backup location...")
        current_path = self.pref_backup_location.text()
        if not current_path:
            current_path = self.pref_default_path.text()
        directory = QFileDialog.getExistingDirectory(
            self, "Select Backup Location", current_path
        )

        if directory:
            self.pref_backup_location.setText(directory)
            print(f"Backup location set to: {directory}")
            self.status_bar.showMessage(f"Backup location set to: {directory}", 5000)

    def reset_preferences_to_defaults(self):
        """Reset all preferences to their default values"""
        reply = cmds.confirmDialog(
            title="Reset Preferences",
            message="Are you sure you want to reset all preferences to their default values?\n\nThis cannot be undone.",
            button=["Reset", "Cancel"],
            defaultButton="Cancel",
            cancelButton="Cancel",
            dismissString="Cancel"
        )

        if reply == "Reset":
            # Reset saving behavior
            self.pref_default_filetype.setCurrentIndex(0)  # Maya ASCII
            self.pref_auto_increment.setChecked(True)
            self.pref_show_confirmation.setChecked(False)

            # Reset save reminders
            self.pref_auto_save_interval.setValue(15)
            self.pref_enable_sound.setChecked(False)

            # Reset automatic backups
            self.pref_enable_auto_backup.setChecked(False)
            self.pref_backup_interval.setValue(30)
            self.pref_max_backups.setValue(10)
            self.pref_backup_location.setText("")

            # Reset version notes
            self.pref_clear_quick_note.setChecked(True)
            self.pref_max_history.setValue(100)

            # Reset file paths (keep as-is or clear)
            # self.pref_default_path.setText("")
            # self.pref_project_path.setText("")

            # Reset UI preferences
            self.pref_file_expanded.setChecked(True)
            self.pref_name_expanded.setChecked(True)
            self.pref_log_expanded.setChecked(False)

            print("Preferences reset to defaults")
            self.status_bar.showMessage("Preferences reset to default values. Click 'Apply Settings' to save.", 5000)

    def browse_existing_project_directory(self):
        """Open file browser to select an existing project directory"""
        current_path = self.project_set_path_input.text()
        directory = QFileDialog.getExistingDirectory(
            self, "Select Existing Project Directory", current_path
        )
        
        if directory:
            self.project_set_path_input.setText(directory)
            cmds.optionVar(sv=(self.OPT_VAR_PROJECT_SET_PATH, directory))
            self.status_bar.showMessage(f"Existing project path set to: {directory}", 5000)

    def browse_project_root_directory(self):
        """Open file browser to select the root directory for new projects"""
        current_path = self.project_root_path_input.text()
        directory = QFileDialog.getExistingDirectory(
            self, "Select Project Root Directory", current_path
        )
        
        if directory:
            self.project_root_path_input.setText(directory)
            cmds.optionVar(sv=(self.OPT_VAR_PROJECT_ROOT_PATH, directory))
            self.status_bar.showMessage(f"Project root set to: {directory}", 5000)

    def sanitize_project_component(self, value):
        """Sanitize project name components for consistent naming"""
        cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', value.strip())
        cleaned = re.sub(r'_+', '_', cleaned)
        return cleaned.strip("_")

    def build_project_directory_name(self):
        """Build a project directory name from the current inputs"""
        prefix_letter = self.project_prefix_letter_combo.currentText()
        prefix_number = str(self.project_prefix_number_spinbox.value()).zfill(2)
        project_name = self.sanitize_project_component(self.project_name_input.text())
        
        prefix = f"{prefix_letter}{prefix_number}"
        if project_name:
            return f"{prefix}_{project_name}"
        return prefix

    def update_project_name_preview(self):
        """Update the project name preview label"""
        project_name = self.build_project_directory_name()
        self.project_name_preview.setText(f"Project name preview: {project_name}")

    def set_existing_project(self):
        """Set Maya's current project based on the provided path"""
        project_path = self.project_set_path_input.text().strip()
        if not project_path:
            QMessageBox.warning(self, "Missing Project Path", "Please select a project directory.")
            return
        
        self.set_project_from_path(project_path)

    def set_project_from_path(self, project_path):
        """Set the Maya project and update UI tracking"""
        if not os.path.isdir(project_path):
            QMessageBox.warning(self, "Invalid Project Path", "The selected project directory does not exist.")
            return
        
        normalized_path = savePlus_core.normalize_path(project_path)
        try:
            mel.eval(f'setProject "{normalized_path}"')
        except Exception as e:
            savePlus_core.debug_print(f"Error setting project via MEL: {e}")
            try:
                cmds.workspace(directory=normalized_path, openWorkspace=True)
            except Exception as e2:
                QMessageBox.critical(self, "Project Set Failed", f"Unable to set the project: {e2}")
                return
        
        self.project_set_path_input.setText(normalized_path)
        cmds.optionVar(sv=(self.OPT_VAR_PROJECT_SET_PATH, normalized_path))
        
        if hasattr(self, 'pref_project_path'):
            self.pref_project_path.setText(normalized_path)
            cmds.optionVar(sv=(self.OPT_VAR_PROJECT_PATH, normalized_path))
        
        self.project_directory = savePlus_core.get_maya_project_directory()
        self.update_project_display()
        self.refresh_project_scenes_list(force=True)
        self.status_bar.showMessage(f"Project set to: {normalized_path}", 5000)

    def create_project(self):
        """Create a new project on disk and set it in Maya"""
        project_root = self.project_root_path_input.text().strip()
        if not project_root:
            QMessageBox.warning(self, "Missing Project Root", "Please choose a project root directory.")
            return
        
        project_dir_name = self.build_project_directory_name()
        if not project_dir_name:
            QMessageBox.warning(self, "Missing Project Name", "Please provide a project name.")
            return
        
        project_path = os.path.join(project_root, project_dir_name)
        
        if os.path.exists(project_path):
            confirm = QMessageBox.question(
                self,
                "Project Exists",
                "This project folder already exists. Set it as the current project?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return
        else:
            if not savePlus_core.create_project_structure(project_path):
                QMessageBox.critical(self, "Project Creation Failed", "Unable to create the project structure.")
                return
        
        cmds.optionVar(sv=(self.OPT_VAR_PROJECT_PREFIX_LETTER, self.project_prefix_letter_combo.currentText()))
        cmds.optionVar(iv=(self.OPT_VAR_PROJECT_PREFIX_NUMBER, self.project_prefix_number_spinbox.value()))
        cmds.optionVar(sv=(self.OPT_VAR_PROJECT_NAME, self.project_name_input.text()))
        cmds.optionVar(sv=(self.OPT_VAR_PROJECT_ROOT_PATH, project_root))
        
        self.set_project_from_path(project_path)

    def open_maya_project_window(self):
        """Open Maya's standard project setup window"""
        try:
            mel.eval('projectWindow')
            self.status_bar.showMessage("Maya Project Window opened", 3000)
        except Exception as e:
            savePlus_core.debug_print(f"Error opening project window: {e}")
            QMessageBox.warning(self, "Error", f"Could not open Maya project window: {e}")

    def open_current_project_folder(self):
        """Open the current project folder in the system file browser"""
        try:
            project_dir = savePlus_core.get_maya_project_directory()
            if project_dir and os.path.isdir(project_dir):
                if sys.platform == 'win32':
                    os.startfile(project_dir)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', project_dir])
                else:
                    subprocess.Popen(['xdg-open', project_dir])
                self.status_bar.showMessage(f"Opened: {project_dir}", 3000)
            else:
                QMessageBox.warning(self, "No Project", "No valid project directory is currently set.")
        except Exception as e:
            savePlus_core.debug_print(f"Error opening project folder: {e}")
            QMessageBox.warning(self, "Error", f"Could not open project folder: {e}")

    def rename_current_project(self):
        """Rename the current project folder"""
        import shutil

        new_name = self.rename_project_new_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Missing Name", "Please enter a new project name.")
            return

        # Sanitize the name
        new_name = self.sanitize_project_component(new_name)
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "The project name contains only invalid characters.")
            return

        project_dir = savePlus_core.get_maya_project_directory()
        if not project_dir:
            QMessageBox.warning(self, "No Project", "No valid project directory is currently set.")
            return

        # Strip trailing slashes to ensure os.path.basename works correctly
        project_dir = project_dir.rstrip('/\\')

        if not os.path.isdir(project_dir):
            QMessageBox.warning(self, "No Project", f"Project directory does not exist:\n{project_dir}")
            return

        parent_dir = os.path.dirname(project_dir)
        old_name = os.path.basename(project_dir)
        new_path = os.path.join(parent_dir, new_name)

        # Debug output
        print(f"[SavePlus] Rename project:")
        print(f"  Old path: {project_dir}")
        print(f"  Old name: {old_name}")
        print(f"  New path: {new_path}")
        print(f"  New name: {new_name}")

        if not old_name:
            QMessageBox.warning(self, "Error", "Could not determine current project folder name.")
            return

        if old_name == new_name:
            QMessageBox.information(self, "No Change", "The new name is the same as the current name.")
            return

        if os.path.exists(new_path):
            QMessageBox.warning(self, "Folder Exists", f"A folder named '{new_name}' already exists in:\n{parent_dir}")
            return

        # Confirm the rename
        confirm = QMessageBox.question(
            self,
            "Confirm Rename",
            f"Rename project folder from:\n'{old_name}'\nto:\n'{new_name}'?\n\nThis will close the current scene.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            # Check for unsaved changes
            if cmds.file(query=True, modified=True):
                save_result = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "Save changes before renaming?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes
                )
                if save_result == QMessageBox.Cancel:
                    return
                elif save_result == QMessageBox.Yes:
                    cmds.file(save=True)

            # Create a new empty scene to release all file locks
            print("[SavePlus] Creating new scene to release file locks...")
            cmds.file(new=True, force=True)

            # Clear Maya's workspace cache by setting to parent directory first
            print("[SavePlus] Clearing Maya workspace cache...")
            try:
                mel.eval(f'setProject "{savePlus_core.normalize_path(parent_dir)}"')
            except Exception as e:
                print(f"[SavePlus] Warning clearing workspace: {e}")

            # Small delay to ensure Maya releases handles
            import time as time_module
            time_module.sleep(0.3)

            # Rename the folder using shutil.move for better cross-platform support
            print(f"[SavePlus] Moving folder...")
            shutil.move(project_dir, new_path)
            print(f"[SavePlus] Folder renamed successfully to: {new_path}")

            # Set the renamed folder as the new project using MEL
            normalized_new_path = savePlus_core.normalize_path(new_path)
            print(f"[SavePlus] Setting new project via MEL: {normalized_new_path}")
            mel.eval(f'setProject "{normalized_new_path}"')

            # Verify the project was set correctly
            new_project = savePlus_core.get_maya_project_directory()
            if new_project:
                new_project = new_project.rstrip('/\\')
            print(f"[SavePlus] Verified current project: {new_project}")

            # Update UI
            self.rename_project_new_name.clear()
            self.project_directory = savePlus_core.get_maya_project_directory()
            self.update_project_display()
            self.status_bar.showMessage(f"Project renamed to: {new_name}", 5000)

            QMessageBox.information(self, "Success", f"Project folder renamed to:\n{new_name}")

        except PermissionError as e:
            print(f"[SavePlus] Permission error: {e}")
            QMessageBox.critical(self, "Permission Denied",
                f"Could not rename project folder.\nFiles may still be in use.\n\nError: {e}")
        except Exception as e:
            print(f"[SavePlus] Error renaming project: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Rename Failed", f"Could not rename project folder:\n{e}")

    def save_plus(self):
        """Execute the save plus operation with the specified filename"""
        print("Starting Save Plus operation...")
        # Reset the save timer immediately when save is attempted
        self.last_save_time = time.time()
        filename = self.filename_input.text()
        
        if not filename:
            message = "Error: Please enter a filename"
            self.status_bar.showMessage(message, 5000)
            print(message)
            return
        
        # Handle the file path
        current_file_path = cmds.file(query=True, sceneName=True)
        
        # Check if this is a first save
        is_first_save = not current_file_path
        
        # Determine the appropriate save directory
        save_directory = self.get_save_directory()
        
        # If a path is provided in the filename, only override it if we're explicitly
        # using current directory or project structure
        if os.path.dirname(filename) and (self.use_current_dir.isChecked() or 
                                        (hasattr(self, 'respect_project_structure') and 
                                        self.respect_project_structure.isChecked())):
            # Extract just the basename
            filename = os.path.basename(filename)
        
        # Combine directory and filename
        if not os.path.dirname(filename):
            filename = os.path.join(save_directory, filename)
            
        print(f"Using directory: {save_directory}")
        
        # Apply selected file extension
        base_name, ext = os.path.splitext(filename)
        if not ext or (ext.lower() not in ['.ma', '.mb']):
            # Extension based on dropdown (.ma is first)
            ext = '.ma' if self.filetype_combo.currentIndex() == 0 else '.mb'
            filename = base_name + ext
            print(f"Applied file extension: {ext}")
        
        print(f"Attempting to save as: {filename}")

        # Get version notes - ALWAYS check quick note first, regardless of checkbox
        version_notes = ""
        if hasattr(self, 'quick_note_input') and self.quick_note_input.text().strip():
            version_notes = self.quick_note_input.text().strip()
            # Check preference before clearing
            should_clear = self.load_option_var(self.OPT_VAR_CLEAR_QUICK_NOTE, True)
            if should_clear:
                self.quick_note_input.clear()  # Clear after using
            print(f"Quick note captured: {version_notes}")
        elif self.add_version_notes.isChecked():
            # Only show dialog if no quick note was provided AND checkbox is checked
            notes_dialog = savePlus_ui_components.NoteInputDialog(self)
            if notes_dialog.exec() == QDialog.Accepted:
                version_notes = notes_dialog.get_notes()
                print("Version notes added via dialog")
            else:
                print("Skipped version notes dialog")

        # Perform the save operation with project awareness
        respect_project = hasattr(self, 'respect_project_structure') and self.respect_project_structure.isChecked()
        result, message, new_file_path = savePlus_core.save_plus_proc(filename, respect_project)
        self.status_bar.showMessage(message, 5000)
        print(message)

        # Update the filename field with the new filename if successful
        if result:
            new_filename = cmds.file(query=True, sceneName=True)
            if new_filename:
                # Add these lines to maintain the directory for next saves
                new_directory = os.path.dirname(new_filename)
                self.selected_directory = new_directory
                print(f"Updated selected directory to: {new_directory}")
                
                self.filename_input.setText(os.path.basename(new_filename))
                print(f"Updated filename to: {os.path.basename(new_filename)}")
                self.update_filename_preview()
                
                # Update version history
                self.version_history.add_version(new_file_path, version_notes)
                self.populate_recent_files()

                # Update last save status
                self.last_save_indicator.setStyleSheet("color: #4CAF50; font-size: 18px;")  # Green
                self.last_save_indicator.setToolTip("Recent save - you're up to date")
                save_time = time.strftime("%H:%M:%S", time.localtime())
                self.last_save_status.setText(f"Last saved: {save_time}")
                self.update_version_preview()

                # Reset the backup timer
                self.last_backup_time = time.time()
                
                # If this was a first-time save and warnings are enabled, show first-time warning
                if is_first_save and self.enable_timed_warning.isChecked():
                    self.show_first_time_warning()
    
    def save_as_new(self):
        """Save the file with the specified name without incrementing"""
        print("Starting Save As New operation...")
        # Reset the save timer immediately when save is attempted
        self.last_save_time = time.time()
        filename = self.filename_input.text()
        
        if not filename:
            message = "Error: Please enter a filename"
            self.status_bar.showMessage(message, 5000)
            print(message)
            return
        
        # Handle the file path
        current_file_path = cmds.file(query=True, sceneName=True)
        
        # Check if this is a first save
        is_first_save = not current_file_path
        
        # If only a filename is provided (no path)
        if not os.path.dirname(filename):
            if self.selected_directory and not self.use_current_dir.isChecked():
                # Use the directory selected via Browse button
                filename = os.path.join(self.selected_directory, filename)
                print(f"Using selected directory: {self.selected_directory}")
            elif current_file_path and self.use_current_dir.isChecked():
                # Use current file's directory
                current_dir = os.path.dirname(current_file_path)
                filename = os.path.join(current_dir, filename)
                print(f"Using current directory: {current_dir}")
        
        # Apply selected file extension
        base_name, ext = os.path.splitext(filename)
        if not ext or (ext.lower() not in ['.ma', '.mb']):
            # Extension based on dropdown (.ma is first)
            ext = '.ma' if self.filetype_combo.currentIndex() == 0 else '.mb'
            filename = base_name + ext
            print(f"Applied file extension: {ext}")
        
        print(f"Attempting to save as: {filename}")
        
        # Check if file exists - MODIFIED to give user options
        if os.path.exists(filename):
            msgBox = QMessageBox(self)
            msgBox.setWindowTitle("File Exists")
            msgBox.setText(f"The file {os.path.basename(filename)} already exists.\nWhat would you like to do?")

            overwriteButton = msgBox.addButton("Overwrite", QMessageBox.ActionRole)
            newNameButton = msgBox.addButton("Use New Name", QMessageBox.ActionRole)
            cancelButton = msgBox.addButton("Cancel", QMessageBox.RejectRole)

            msgBox.setDefaultButton(cancelButton)  # Set Cancel as default
            msgBox.exec()

            clickedButton = msgBox.clickedButton()

            if clickedButton == overwriteButton:
                choice = 0  # Maintain original choice values
            elif clickedButton == newNameButton:
                choice = 1
            else:
                choice = 2
            
            if choice == 0:  # Overwrite
                print(f"Overwriting existing file: {filename}")
                # Continue with save operation
            elif choice == 1:  # Use New Name
                # Generate a new unique filename
                base_dir = os.path.dirname(filename)
                base_name, ext = os.path.splitext(os.path.basename(filename))
                
                # Try to find a unique name by adding a number
                counter = 1
                new_filename = os.path.join(base_dir, f"{base_name}_{counter}{ext}")
                while os.path.exists(new_filename):
                    counter += 1
                    new_filename = os.path.join(base_dir, f"{base_name}_{counter}{ext}")
                
                filename = new_filename
                print(f"Using new unique filename: {filename}")
            else:  # Cancel
                message = "Save operation cancelled"
                self.status_bar.showMessage(message, 5000)
                print(message)
                return
        
        # Get version notes - ALWAYS check quick note first, regardless of checkbox
        version_notes = ""
        if hasattr(self, 'quick_note_input') and self.quick_note_input.text().strip():
            version_notes = self.quick_note_input.text().strip()
            # Check preference before clearing
            should_clear = self.load_option_var(self.OPT_VAR_CLEAR_QUICK_NOTE, True)
            if should_clear:
                self.quick_note_input.clear()  # Clear after using
            print(f"Quick note captured: {version_notes}")
        elif self.add_version_notes.isChecked():
            # Only show dialog if no quick note was provided AND checkbox is checked
            notes_dialog = savePlus_ui_components.NoteInputDialog(self)
            if notes_dialog.exec() == QDialog.Accepted:
                version_notes = notes_dialog.get_notes()
                print("Version notes added via dialog")
            else:
                print("Skipped version notes dialog")

        # Make sure directory exists
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            try:
                print(f"Creating directory: {directory}")
                os.makedirs(directory)
            except OSError as e:
                message = f"Error: Could not create directory {directory}: {e}"
                self.status_bar.showMessage(message, 5000)
                print(message)
                return
        
        # Save the file
        try:
            cmds.file(rename=filename)
            
            # Explicitly specify the file type based on extension for proper saving
            if filename.lower().endswith('.ma'):
                cmds.file(save=True, type='mayaAscii')
            elif filename.lower().endswith('.mb'):
                cmds.file(save=True, type='mayaBinary')
            else:
                # Default to Maya ASCII if extension is unknown
                cmds.file(save=True, type='mayaAscii')
                
            message = f"{os.path.basename(filename)} saved successfully"
            self.status_bar.showMessage(message, 5000)
            print(message)
            
            # Update version history
            self.version_history.add_version(filename, version_notes)
            self.populate_recent_files()
                      
            # Update last save status
            self.last_save_indicator.setStyleSheet("color: #4CAF50; font-size: 18px;")  # Green
            self.last_save_indicator.setToolTip("Recent save - you're up to date")
            save_time = time.strftime("%H:%M:%S", time.localtime())
            self.last_save_status.setText(f"Last saved: {save_time}")
            self.update_version_preview()

            # Reset the backup timer
            self.last_backup_time = time.time()
            
            # If this was a first-time save and warnings are enabled, show first-time warning
            if is_first_save and self.enable_timed_warning.isChecked():
                self.show_first_time_warning()
        except Exception as e:
            message = f"Error saving file: {e}"
            self.status_bar.showMessage(message, 5000)
            print(message)
    
    def create_backup(self):
        """Create a backup copy of the current file"""
        print("Creating backup...")
        
        # Check if file is saved
        current_file = cmds.file(query=True, sceneName=True)
        if not current_file:
            message = "Error: File must be saved at least once before creating a backup"
            self.status_bar.showMessage(message, 5000)
            print(message)
            return
        
        # Create backup
        success, message, backup_path = savePlus_core.create_backup(current_file)
        self.status_bar.showMessage(message, 5000)
        
        if success:
            # Add to history
            self.version_history.add_version(backup_path, "Automatic backup")
            self.populate_recent_files()
        
        return success
    
    def populate_recent_files(self):
        """Populate the recent files list"""
        try:
            self.recent_files_list.clear()
            
            recent_versions = self.version_history.get_recent_versions(20)
            
            for version in recent_versions:
                # Create list item with filename and date
                filename = version.get('filename', 'Unknown')
                date = version.get('date', '')
                
                item = QListWidgetItem(f"{filename} - {date}")
                item.setData(Qt.UserRole, version.get('path', ''))
                
                # Set tooltip to show path and notes
                tooltip = f"Path: {version.get('path', '')}"
                notes = version.get('notes', '').strip()
                if notes:
                    tooltip += f"\nNotes: {notes}"
                item.setToolTip(tooltip)
                
                self.recent_files_list.addItem(item)
        except Exception as e:
            savePlus_core.debug_print(f"Error populating recent files: {e}")
    
    def open_recent_file(self, item):
        """Open a file from the recent files list"""
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            self.open_maya_file(file_path)
    
    def open_selected_file(self):
        """Open the selected file from the recent files list"""
        selected_items = self.recent_files_list.selectedItems()
        if selected_items:
            file_path = selected_items[0].data(Qt.UserRole)
            if file_path and os.path.exists(file_path):
                self.open_maya_file(file_path)
            else:
                message = f"File not found: {file_path}"
                self.status_bar.showMessage(message, 5000)
                print(message)
    
    def open_maya_file(self, file_path):
        """Open a Maya file"""
        # Check for unsaved changes
        if cmds.file(query=True, modified=True):
            result = cmds.confirmDialog(
                title='Unsaved Changes',
                message='Save changes to the current file?',
                button=['Save', 'Don\'t Save', 'Cancel'],
                defaultButton='Save',
                cancelButton='Cancel',
                dismissString='Cancel'
            )
            
            if result == 'Cancel':
                return
            elif result == 'Save':
                cmds.file(save=True)
        
        # Find this section in the open_maya_file method, around line 880
        try:
            cmds.file(file_path, open=True, force=True)
            message = f"Opened: {os.path.basename(file_path)}"
            self.status_bar.showMessage(message, 5000)
            print(message)
            
            # Update the filename input
            self.filename_input.setText(os.path.basename(file_path))
            self.filename_input.setToolTip(file_path)  # Show full path on hover
            self.update_filename_preview()
            
            # Add these new lines to update the save location display
            self.selected_directory = os.path.dirname(file_path)
            self.update_save_location_display()
            
        except Exception as e:
            message = f"Error opening file: {e}"
            self.status_bar.showMessage(message, 5000)
            print(message)
    
    def populate_history(self):
        """Populate the history table with version history"""
        try:
            self.history_table.setRowCount(0)  # Clear table
            
            # Get current file path
            current_file = cmds.file(query=True, sceneName=True)
            
            if current_file:
                versions = self.version_history.get_versions_for_file(current_file)
                
                for idx, version in enumerate(versions):
                    self.history_table.insertRow(idx)
                    
                    # Filename
                    filename_item = QTableWidgetItem(version.get('filename', 'Unknown'))
                    self.history_table.setItem(idx, 0, filename_item)
                    
                    # Date
                    date_item = QTableWidgetItem(version.get('date', ''))
                    self.history_table.setItem(idx, 1, date_item)
                    
                    # Path
                    path_item = QTableWidgetItem(version.get('path', ''))
                    self.history_table.setItem(idx, 2, path_item)
                    
                    # Notes
                    notes = version.get('notes', '').strip()
                    notes_item = QTableWidgetItem(notes)
                    self.history_table.setItem(idx, 3, notes_item)
            else:
                print("No current file to show history for")
                
        except Exception as e:
            savePlus_core.debug_print(f"Error populating history: {e}")
    
    def open_selected_history_file(self):
        """Open the selected file from the history table"""
        selected_rows = self.history_table.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            file_path = self.history_table.item(row, 2).text()

            if file_path and os.path.exists(file_path):
                self.open_maya_file(file_path)
            else:
                message = f"File not found: {file_path}"
                self.status_bar.showMessage(message, 5000)
                print(message)

    def open_history_file_double_click(self, item):
        """Open file when double-clicking on history table row"""
        row = item.row()
        file_path = self.history_table.item(row, 2).text()

        if file_path and os.path.exists(file_path):
            self.open_maya_file(file_path)
        else:
            message = f"File not found: {file_path}"
            self.status_bar.showMessage(message, 5000)
            print(message)

    def view_history_notes(self):
        """View or edit notes for the selected history entry in an enlarged window"""
        selected_rows = self.history_table.selectedItems()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a version from the history table.")
            return

        row = selected_rows[0].row()
        file_path = self.history_table.item(row, 2).text()
        filename = self.history_table.item(row, 0).text()
        current_notes = self.history_table.item(row, 3).text()

        # Use the new EnlargedNotesViewerDialog for better readability
        dialog = savePlus_ui_components.EnlargedNotesViewerDialog(
            self,
            filename=filename,
            notes=current_notes,
            file_path=file_path,
            editable=True
        )

        if dialog.exec() == QDialog.Accepted:
            new_notes = dialog.get_notes().strip()
            # Update the notes in the version history
            if self.version_history.update_notes(file_path, new_notes):
                self.history_table.item(row, 3).setText(new_notes)
                self.status_bar.showMessage("Notes updated successfully", 3000)
            else:
                QMessageBox.warning(self, "Error", "Could not update notes.")

    def export_history(self):
        """Export version history to a text file"""
        # Get save location
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Version History", "", "Text Files (*.txt)"
        )
        
        if file_path:
            # Add extension if not provided
            if not file_path.lower().endswith('.txt'):
                file_path += '.txt'
            
            if self.version_history.export_history(file_path):
                message = f"History exported to: {file_path}"
                self.status_bar.showMessage(message, 5000)
                print(message)
            else:
                message = "Error exporting history"
                self.status_bar.showMessage(message, 5000)
                print(message)

    def clear_history(self):
        """Clear version history data"""
        confirm = QMessageBox.question(
            self,
            "Clear History",
            "This will remove all version history entries. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return

        if self.version_history.clear_history():
            self.populate_history()
            self.populate_recent_files()
            self.status_bar.showMessage("History cleared", 5000)
        else:
            self.status_bar.showMessage("Failed to clear history", 5000)

    def clear_recent_files(self):
        """Clear only the recent files list (not all history data)"""
        confirm = QMessageBox.question(
            self,
            "Clear Recent Files",
            "This will clear the recent files list display.\n\nNote: This does not delete the actual history data, "
            "just refreshes the recent files view.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return

        self.recent_files_list.clear()
        self.status_bar.showMessage("Recent files list cleared", 3000)

    def open_project_browser(self):
        """Open the Project Scenes Browser dialog to browse all scenes in the project"""
        # Get current project path
        project_path = self.project_directory or savePlus_core.get_maya_project_directory()

        if not project_path:
            QMessageBox.warning(
                self,
                "No Project",
                "No Maya project is currently set.\n\n"
                "Please set a project using the Project tab or Maya's File > Set Project menu."
            )
            return

        # Open the Project Browser dialog
        dialog = savePlus_ui_components.ProjectScenesBrowserDialog(
            self,
            project_path=project_path,
            version_history=self.version_history
        )

        if dialog.exec() == QDialog.Accepted:
            selected_file = dialog.get_selected_file()
            if selected_file and os.path.exists(selected_file):
                self.open_maya_file(selected_file)

    def update_project_scenes_controls(self):
        """Enable or disable project scenes controls based on selection"""
        if not hasattr(self, "project_scenes_open_button"):
            return

        selected_items = self.project_scenes_list.selectedItems() if hasattr(self, "project_scenes_list") else []
        has_valid_selection = False
        if selected_items:
            file_path = selected_items[0].data(Qt.UserRole)
            has_valid_selection = bool(file_path and os.path.exists(file_path))

        self.project_scenes_open_button.setEnabled(has_valid_selection)

    def refresh_project_scenes_list(self, force=False):
        """Refresh the project scenes list from the current project's scenes folder"""
        if not hasattr(self, "project_scenes_list"):
            return

        project_path = self.project_directory or savePlus_core.get_maya_project_directory()

        if not force and project_path == self.project_scenes_last_path:
            return

        self.project_scenes_last_path = project_path
        self.project_scenes_list.clear()
        self.project_scenes_open_button.setEnabled(False)

        if not project_path:
            item = QListWidgetItem("Set a project to view scenes")
            item.setData(Qt.UserRole, "")
            self.project_scenes_list.addItem(item)
            return

        scenes_path = os.path.join(project_path, "scenes")
        if not os.path.exists(scenes_path):
            item = QListWidgetItem("No scenes folder found")
            item.setData(Qt.UserRole, "")
            self.project_scenes_list.addItem(item)
            return

        maya_files = []
        for root, _, files in os.walk(scenes_path):
            for file_name in files:
                if file_name.lower().endswith(('.ma', '.mb')):
                    full_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(full_path, scenes_path)
                    mod_time = os.path.getmtime(full_path)
                    maya_files.append((rel_path, full_path, mod_time))

        maya_files.sort(key=lambda item: item[2], reverse=True)

        if not maya_files:
            item = QListWidgetItem("No Maya scene files found")
            item.setData(Qt.UserRole, "")
            self.project_scenes_list.addItem(item)
            return

        from datetime import datetime

        for rel_path, full_path, mod_time in maya_files:
            mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{rel_path}  [{mod_date}]")
            item.setData(Qt.UserRole, full_path)
            item.setToolTip(full_path)
            self.project_scenes_list.addItem(item)

    def open_selected_project_scene(self):
        """Open the selected scene from the project scenes list"""
        if not hasattr(self, "project_scenes_list"):
            return

        selected_items = self.project_scenes_list.selectedItems()
        if not selected_items:
            return

        file_path = selected_items[0].data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            self.open_maya_file(file_path)
    
    def on_tab_changed(self, index):
        """Handle tab changed event"""
        if index == self.project_tab_index:  # Project tab
            self.update_project_tracking()
        elif index == self.history_tab_index:  # History tab
            self.populate_history()
            self.populate_recent_files()
    
    def show_preferences(self):
        """Show the preferences tab"""
        if hasattr(self, 'tab_widget'):
            self.tab_widget.setCurrentWidget(self.preferences_tab)
    
    def show_about(self):
        """Show the about dialog"""
        about_dialog = savePlus_ui_components.AboutDialog(self)
        
        # Add project recognition information to the description
        if hasattr(about_dialog, 'desc'):
            project_info = "\n\nProject Recognition: SavePlus automatically recognizes Maya projects and can maintain project structure."
            about_dialog.desc.setText(about_dialog.desc.text() + project_info)
        
        about_dialog.exec()
    
    def show_first_time_warning(self):
        """Show the first-time save warning dialog"""
        # Get the current interval setting
        reminder_interval = self.reminder_interval_spinbox.value()
        
        warning_dialog = savePlus_ui_components.TimedWarningDialog(
            self, 
            first_time=True,
            interval=reminder_interval
        )
        result = warning_dialog.exec()
        
        # If user chose to disable warnings
        if warning_dialog.get_disable_warnings():
            self.enable_timed_warning.setChecked(False)
    
    def _build_compact_filename(self):
        """Return the compact filename string based on current name generator inputs."""
        assignment_letter = self.assignment_letter_combo.currentText()
        assignment_num = str(self.assignment_spinbox.value()).zfill(2)
        last_name = self.lastname_input.text().strip()
        first_name = self.firstname_input.text().strip()
        pipeline_stage = self.pipeline_stage_combo.currentText().lower()
        version_status = self.version_status_combo.currentText().lower()
        version_num = str(self.version_number_spinbox.value()).zfill(2)

        first_initial = first_name[0].upper() if first_name else ""
        stage_abbr = self.STAGE_ABBREVIATIONS.get(pipeline_stage, pipeline_stage[:4])
        status_abbr = self.STATUS_ABBREVIATIONS.get(version_status, version_status[0])

        parts = [f"{assignment_letter}{assignment_num}"]
        if last_name:
            parts.append(last_name)
        if first_initial:
            parts.append(first_initial)
        parts.append(stage_abbr)
        parts.append(status_abbr)
        parts.append(version_num)
        return "_".join(parts)

    def _update_compact_preview(self):
        """Refresh the compact filename preview label."""
        if not hasattr(self, 'compact_filename_preview'):
            return
        last_name = self.lastname_input.text().strip()
        first_name = self.firstname_input.text().strip()
        if last_name or first_name:
            filetype_idx = self.filetype_combo.currentIndex() if hasattr(self, 'filetype_combo') else 0
            ext = '.ma' if filetype_idx == 0 else '.mb'
            self.compact_filename_preview.setText(self._build_compact_filename() + ext)
        else:
            self.compact_filename_preview.setText("\u2014")

    def generate_filename(self):
        """Generate a filename based on the name generator inputs"""
        assignment_letter = self.assignment_letter_combo.currentText()
        assignment_num = str(self.assignment_spinbox.value()).zfill(2)
        last_name = self.lastname_input.text()
        first_name = self.firstname_input.text()
        
        # Get pipeline stage and status
        pipeline_stage = self.pipeline_stage_combo.currentText().lower()
        version_status = self.version_status_combo.currentText()
        
        # Combine stage and status for the version type
        version_type = f"{pipeline_stage}_{version_status}"
        
        version_num = str(self.version_number_spinbox.value()).zfill(2)
        
        if not last_name or not first_name:
            QMessageBox.warning(self, "Missing Information",
                            "Please enter both Last Name and First Name")
            return

        # Build filename — compact or full depending on checkbox
        use_compact = hasattr(self, 'compact_name_checkbox') and self.compact_name_checkbox.isChecked()
        if use_compact:
            new_filename = self._build_compact_filename()
        else:
            # Format: X##_LastName_FirstName_stage_status_## (where X is the assignment letter)
            # Example: J02_Smith_John_layout_wip_01
            new_filename = f"{assignment_letter}{assignment_num}_{last_name}_{first_name}_{version_type}_{version_num}"
        
        # Update the filename input - using the update_filename_display method to properly handle the path
        if hasattr(self, 'update_filename_display') and callable(self.update_filename_display):
            # If we have a directory selected, use it
            if self.selected_directory:
                full_path = os.path.join(self.selected_directory, new_filename)
                self.update_filename_display(full_path)
            else:
                # Just update the filename without path
                self.filename_input.setText(new_filename)
        else:
            # Fallback if update_filename_display is not available
            self.filename_input.setText(new_filename)
        
        # Update preview
        self.update_filename_preview()
        
        # Save settings
        self.save_name_generator_settings()
        
        print(f"Generated filename: {new_filename}")
        print(f"Project identifier: {assignment_letter}{assignment_num}_")
        print(f"Last Name: {last_name}")
        print(f"First Name: {first_name}")
        print(f"Version Type: {version_type}")
        print(f"Version Number: {version_num}")
    
    def reset_name_generator(self):
        """Reset name generator fields to defaults"""
        self.assignment_letter_combo.setCurrentIndex(0)  # Reset to 'A'
        self.assignment_spinbox.setValue(1)
        self.lastname_input.setText("")
        self.firstname_input.setText("")
        
        # Reset pipeline stage and status
        self.pipeline_stage_combo.setCurrentIndex(2)  # Default to Blocking
        self.version_status_combo.setCurrentIndex(0)  # Default to WIP
        
        self.version_number_spinbox.setValue(1)
        if hasattr(self, 'compact_name_checkbox'):
            self.compact_name_checkbox.setChecked(False)

        # Update preview
        self.update_filename_preview()
        self._update_compact_preview()

        # Save settings
        self.save_name_generator_settings()

        print("Name generator reset to defaults")
    
    def update_filename_preview(self):
        """Update the filename preview label"""
        if hasattr(self, 'filename_input') and hasattr(self, 'filename_preview'):
            base_name = self.filename_input.text()
            if base_name:
                # Extension based on dropdown (.ma is first)
                ext = '.ma' if self.filetype_combo.currentIndex() == 0 else '.mb'
                self.filename_preview.setText(f"{base_name}{ext}")
            else:
                self.filename_preview.setText("No filename")
    
    def toggle_timed_warning(self, state):
        """Toggle the timed warning feature using Maya's scriptJob system"""
        print(f"\n[DEBUG] toggle_timed_warning called with state: {state}")
        print(f"[DEBUG] State type: {type(state)}, Qt.Checked value: {Qt.Checked}")
        
        try:
            # Use direct integer comparison - 2 is checked, 0 is unchecked
            if state == 2 or state is True or state == Qt.Checked:
                print("\n" + "="*70)
                print("               TIMER ENABLED - USING MAYA SCRIPTJOB")
                print("="*70 + "\n")
                
                # Set last save time to current time
                self.last_save_time = time.time()
                
                # Remove any existing scriptJob
                if hasattr(self, 'timer_job_id') and self.timer_job_id is not None:
                    try:
                        cmds.scriptJob(kill=self.timer_job_id)
                        print(f"[DEBUG] Removed existing timer scriptJob: {self.timer_job_id}")
                    except Exception as e:
                        print(f"[DEBUG] Error removing timer scriptJob: {e}")
                
                # Use directly scheduled Qt timer instead of scriptJob
                # This is simpler and more reliable across Maya versions
                if hasattr(self, 'save_timer'):
                    self.save_timer.stop()  # Stop if already running
                    self.save_timer.setInterval(5000)  # 5 seconds
                    self.save_timer.start()
                    print("[DEBUG] Started Qt timer with 5-second interval")
                    print(f"[DEBUG] Timer active status: {self.save_timer.isActive()}")
                
                # Save the setting
                cmds.optionVar(iv=(self.OPT_VAR_ENABLE_TIMED_WARNING, 1))
                
            else:
                print("\n" + "="*70)
                print("               TIMER DISABLED - STOPPING TIMER")
                print("="*70 + "\n")
                
                # Stop Qt timer
                if hasattr(self, 'save_timer') and self.save_timer.isActive():
                    self.save_timer.stop()
                    print("[DEBUG] Stopped Qt timer")
                
                # Kill the scriptJob if it exists (just to be thorough)
                if hasattr(self, 'timer_job_id') and self.timer_job_id is not None:
                    try:
                        cmds.scriptJob(kill=self.timer_job_id)
                        print(f"[DEBUG] Killed timer scriptJob: {self.timer_job_id}")
                        self.timer_job_id = None
                    except Exception as e:
                        print(f"[DEBUG] Error killing scriptJob: {e}")
                        self.timer_job_id = None
                
                # Save the setting
                cmds.optionVar(iv=(self.OPT_VAR_ENABLE_TIMED_WARNING, 0))
                
        except Exception as e:
            print(f"[ERROR] Timer toggle failed: {str(e)}")
            traceback.print_exc()
    
    def check_save_time(self):
        """Check if enough time has passed to show a save reminder"""
        try:
            # Increment and display counter - VERY VISIBLE logging
            if not hasattr(SavePlusUI, 'TIMER_COUNT'):
                SavePlusUI.TIMER_COUNT = 0
            
            SavePlusUI.TIMER_COUNT += 1
            print("\n" + "*"*70)
            print(f"*** TIMER CHECK #{SavePlusUI.TIMER_COUNT} at {time.strftime('%H:%M:%S')} ***")
            print("*"*70 + "\n")
            
            # Get current time and calculate elapsed time
            current_time = time.time()
            elapsed_minutes = (current_time - self.last_save_time) / 60
            
            # CRITICAL FIX: Get interval BEFORE using it
            reminder_interval = self.reminder_interval_spinbox.value()
            
            # Detailed debug information
            print(f"[Timer Status] Last save: {time.strftime('%H:%M:%S', time.localtime(self.last_save_time))}")
            print(f"[Timer Status] Elapsed time: {elapsed_minutes:.2f} minutes")
            print(f"[Timer Status] Reminder threshold: {reminder_interval} minutes")
            print(f"[Timer Status] Timer interval: {self.save_timer.interval()/1000} seconds")
            print(f"[Timer Status] Timer active: {self.save_timer.isActive()}")
            
            # Update indicator color based on time since last save
            if elapsed_minutes >= reminder_interval:
                # Red - Time to save
                self.last_save_indicator.setStyleSheet("color: #F44336; font-size: 18px;")
                self.last_save_indicator.setToolTip("Save recommended - it's been a while")
                print("[Timer Status] Indicator: RED (save needed)")
            elif elapsed_minutes >= reminder_interval * 0.7:
                # Yellow - Getting close to reminder time
                self.last_save_indicator.setStyleSheet("color: #FFC107; font-size: 18px;")
                self.last_save_indicator.setToolTip("Consider saving soon")
                print("[Timer Status] Indicator: YELLOW (getting close)")
            else:
                # Green - Recent save
                self.last_save_indicator.setStyleSheet("color: #4CAF50; font-size: 18px;")
                self.last_save_indicator.setToolTip("Recent save - you're up to date")
                print("[Timer Status] Indicator: GREEN (recently saved)")
            
            # Show warning if enough time has passed
            if elapsed_minutes >= reminder_interval:
                print("\n" + "!"*70)
                print(f"!!! TIME TO SHOW REMINDER DIALOG !!! (Elapsed: {elapsed_minutes:.2f} min > Threshold: {reminder_interval} min)")
                print("!"*70 + "\n")
                
                # Create and show the dialog
                warning_dialog = savePlus_ui_components.TimedWarningDialog(self, first_time=False, interval=int(elapsed_minutes))
                
                # Force dialog to stay on top
                warning_dialog.setWindowFlags(warning_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
                
                # Show the dialog and get response
                print("[Dialog] Showing save reminder dialog...")
                result = warning_dialog.exec()
                
                if result == QDialog.Accepted:
                    # User clicked "Save Now" - Ask which save method to use
                    print("[Dialog] User chose to save now")
                    msgBox = QMessageBox(self)
                    msgBox.setWindowTitle("Save Method")
                    msgBox.setText("How would you like to save your file?")

                    savePlusButton = msgBox.addButton("Save Plus (Increment)", QMessageBox.ActionRole)
                    saveAsNewButton = msgBox.addButton("Save As New", QMessageBox.ActionRole)
                    cancelButton = msgBox.addButton("Cancel", QMessageBox.RejectRole)

                    msgBox.setDefaultButton(savePlusButton)  # Default to Save Plus
                    msgBox.exec()

                    clickedButton = msgBox.clickedButton()

                    if clickedButton == savePlusButton:
                        print("[Dialog] User chose Save Plus (increment)")
                        self.save_plus()
                    elif clickedButton == saveAsNewButton:
                        print("[Dialog] User chose Save As New")
                        self.save_as_new()
                    else:
                        print("[Dialog] User cancelled save operation")
                else:
                    # User clicked "Remind Me Later"
                    print("[Dialog] User chose to be reminded later")
                    # Reset timer to remind again in 2 minutes
                    self.last_save_time = current_time - ((reminder_interval - 2) * 60)
                    print(f"[Timer Status] Last save time adjusted to remind again in 2 minutes")
            else:
                print(f"[Timer Status] Not time for reminder yet. Will remind in {reminder_interval - elapsed_minutes:.2f} minutes")
            
            # End of timer check
            print("\n" + "-"*70)
            print(f"--- TIMER CHECK #{SavePlusUI.TIMER_COUNT} COMPLETED ---")
            print("-"*70 + "\n")
            
        except Exception as e:
            # Comprehensive error reporting
            print("\n" + "X"*70)
            print("XXX ERROR IN TIMER CHECK XXX")
            print("X"*70)
            print(f"Error message: {str(e)}")
            print("Stack trace:")
            traceback.print_exc()
            print("X"*70 + "\n")

    def setup_timer(self):
        """Set up the save reminder timer based on current preferences"""
        try:
            if self.enable_timed_warning.isChecked():
                print("[DEBUG] Setting up timer via scriptJob")
                self.toggle_timed_warning(Qt.Checked)
            else:
                print("[DEBUG] Timer setup skipped (not enabled)")
        except Exception as e:
            print(f"[ERROR] Timer setup failed: {str(e)}")
            traceback.print_exc()

    def check_backup_time(self):
        """Check if enough time has passed to create an auto-backup"""
        if not self.pref_enable_auto_backup.isChecked():
            return
            
        current_time = time.time()
        backup_interval = self.pref_backup_interval.value()
        elapsed_minutes = (current_time - self.last_backup_time) / 60
        
        # Create backup if it's been at least as long as the backup interval
        if elapsed_minutes >= backup_interval:
            # Only backup if file is saved and modified
            current_file = cmds.file(query=True, sceneName=True)
            if current_file and cmds.file(query=True, modified=True):
                print(f"Auto-backup triggered after {elapsed_minutes:.1f} minutes")
                if self.create_backup():
                    self.last_backup_time = current_time
    
    def load_option_var(self, name, default_value):
        """Load an option variable with a default value"""
        return savePlus_core.load_option_var(name, default_value)
        
    def adjust_window_size(self):
        """Adjust window size based on content"""
        if not self.auto_resize_enabled:
            return
            
        try:
            # Process events to ensure container widget is properly laid out
            QtCore.QCoreApplication.processEvents()
            
            # Get actual heights of sections instead of fixed estimates
            total_height = 0
            
            # Use actual heights of widgets
            if hasattr(self, 'file_options_section'):
                if not self.file_options_section.is_collapsed():
                    total_height += self.file_options_section.sizeHint().height()
                else:
                    total_height += self.file_options_section.header.height()
                    
            if hasattr(self, 'name_gen_section'):
                if not self.name_gen_section.is_collapsed():
                    total_height += self.name_gen_section.sizeHint().height()
                else:
                    total_height += self.name_gen_section.header.height()
            
            # Add height for save buttons
            total_height += 60  # Buttons with padding
            
            if hasattr(self, 'log_section'):
                if not self.log_section.is_collapsed():
                    total_height += self.log_section.sizeHint().height()
                else:
                    total_height += self.log_section.header.height()
            
            # Add spacing between sections
            total_height += self.container_layout.spacing() * 4  # Account for section spacing
            
            # Add bottom padding
            total_height += 20
            
            # Force the container widget to update its layout
            self.container_widget.updateGeometry()
            
            # Process events to apply resize immediately
            QtCore.QCoreApplication.processEvents()
        except Exception as e:
            savePlus_core.debug_print(f"Error during window resize: {e}")
            # Disable auto-resize if we encounter problems
            self.auto_resize_enabled = False
    
    def save_name_generator_settings(self):
        """Save name generator settings to option variables"""
        try:
            cmds.optionVar(sv=(self.OPT_VAR_ASSIGNMENT_LETTER, self.assignment_letter_combo.currentText()))
            cmds.optionVar(iv=(self.OPT_VAR_ASSIGNMENT_NUMBER, self.assignment_spinbox.value()))
            cmds.optionVar(sv=(self.OPT_VAR_LAST_NAME, self.lastname_input.text()))
            cmds.optionVar(sv=(self.OPT_VAR_FIRST_NAME, self.firstname_input.text()))
            
            # Save pipeline stage
            cmds.optionVar(sv=(self.OPT_VAR_PIPELINE_STAGE, self.pipeline_stage_combo.currentText()))
            
            # Save version status
            cmds.optionVar(sv=(self.OPT_VAR_VERSION_TYPE, self.version_status_combo.currentText()))
            
            cmds.optionVar(iv=(self.OPT_VAR_VERSION_NUMBER, self.version_number_spinbox.value()))
            if hasattr(self, 'compact_name_checkbox'):
                cmds.optionVar(iv=(self.OPT_VAR_COMPACT_NAME, int(self.compact_name_checkbox.isChecked())))
        except Exception as e:
            savePlus_core.debug_print(f"Error saving name generator settings: {e}")
    
    def save_preferences(self):
        """Save all preference settings"""
        try:
            # === SAVING BEHAVIOR ===
            # Save file type preference
            file_type_index = self.pref_default_filetype.currentIndex()
            cmds.optionVar(iv=(self.OPT_VAR_DEFAULT_FILETYPE, file_type_index))

            # Save auto-increment setting
            if hasattr(self, 'pref_auto_increment'):
                cmds.optionVar(iv=(self.OPT_VAR_AUTO_INCREMENT_VERSION, int(self.pref_auto_increment.isChecked())))

            # Save show confirmation setting
            if hasattr(self, 'pref_show_confirmation'):
                cmds.optionVar(iv=(self.OPT_VAR_SHOW_SAVE_CONFIRMATION, int(self.pref_show_confirmation.isChecked())))

            # === SAVE REMINDERS ===
            # Save auto-save interval
            auto_save_interval = self.pref_auto_save_interval.value()
            cmds.optionVar(iv=(self.OPT_VAR_AUTO_SAVE_INTERVAL, auto_save_interval))

            # Sync the reminder interval with the main tab spinner
            if hasattr(self, 'reminder_interval_spinbox'):
                self.reminder_interval_spinbox.setValue(auto_save_interval)

            # Save sound preference
            if hasattr(self, 'pref_enable_sound'):
                cmds.optionVar(iv=(self.OPT_VAR_ENABLE_SAVE_SOUND, int(self.pref_enable_sound.isChecked())))

            # === AUTOMATIC BACKUPS ===
            # Save auto-backup settings
            cmds.optionVar(iv=(self.OPT_VAR_ENABLE_AUTO_BACKUP, int(self.pref_enable_auto_backup.isChecked())))
            cmds.optionVar(iv=(self.OPT_VAR_BACKUP_INTERVAL, self.pref_backup_interval.value()))

            # Save max backups setting
            if hasattr(self, 'pref_max_backups'):
                cmds.optionVar(iv=(self.OPT_VAR_MAX_BACKUPS, self.pref_max_backups.value()))

            # Save backup location
            if hasattr(self, 'pref_backup_location'):
                cmds.optionVar(sv=(self.OPT_VAR_BACKUP_LOCATION, self.pref_backup_location.text()))

            # === VERSION NOTES ===
            # Save clear quick note setting
            if hasattr(self, 'pref_clear_quick_note'):
                cmds.optionVar(iv=(self.OPT_VAR_CLEAR_QUICK_NOTE, int(self.pref_clear_quick_note.isChecked())))

            # Save max history entries
            if hasattr(self, 'pref_max_history'):
                cmds.optionVar(iv=(self.OPT_VAR_MAX_HISTORY_ENTRIES, self.pref_max_history.value()))

            # Save add version notes (from main tab)
            cmds.optionVar(iv=(self.OPT_VAR_ADD_VERSION_NOTES, int(self.add_version_notes.isChecked())))

            # === FILE PATHS ===
            # Save path preferences
            default_path = self.pref_default_path.text()
            cmds.optionVar(sv=(self.OPT_VAR_DEFAULT_SAVE_PATH, default_path))

            project_path = self.pref_project_path.text()
            cmds.optionVar(sv=(self.OPT_VAR_PROJECT_PATH, project_path))

            # Save respect project setting
            cmds.optionVar(iv=(self.OPT_VAR_RESPECT_PROJECT, int(self.respect_project_structure.isChecked())))

            # === UI PREFERENCES ===
            # Save UI preferences
            cmds.optionVar(iv=(self.OPT_VAR_FILE_EXPANDED, int(self.pref_file_expanded.isChecked())))
            cmds.optionVar(iv=(self.OPT_VAR_NAME_EXPANDED, int(self.pref_name_expanded.isChecked())))
            cmds.optionVar(iv=(self.OPT_VAR_LOG_EXPANDED, int(self.pref_log_expanded.isChecked())))

            # Update backup timer based on new settings
            if self.pref_enable_auto_backup.isChecked():
                if not self.backup_timer.isActive():
                    self.backup_timer.start(60000)
            else:
                if self.backup_timer.isActive():
                    self.backup_timer.stop()

            # Apply UI settings immediately
            self.apply_ui_settings()

            print("Preferences saved successfully")
            self.status_bar.showMessage("Preferences saved successfully", 5000)
        except Exception as e:
            error_message = f"Error saving preferences: {e}"
            print(error_message)
            traceback.print_exc()
            self.status_bar.showMessage(error_message, 5000)

        # Update save location display to reflect new preferences
        self.update_save_location_display()
    
    def load_preferences(self):
        """Load preference settings"""
        try:
            # === SAVING BEHAVIOR ===
            # Load file type preference
            if cmds.optionVar(exists=self.OPT_VAR_DEFAULT_FILETYPE):
                file_type_index = cmds.optionVar(q=self.OPT_VAR_DEFAULT_FILETYPE)
                self.pref_default_filetype.setCurrentIndex(file_type_index)

            # Load auto-increment setting
            if hasattr(self, 'pref_auto_increment'):
                if cmds.optionVar(exists=self.OPT_VAR_AUTO_INCREMENT_VERSION):
                    self.pref_auto_increment.setChecked(bool(cmds.optionVar(q=self.OPT_VAR_AUTO_INCREMENT_VERSION)))

            # Load show confirmation setting
            if hasattr(self, 'pref_show_confirmation'):
                if cmds.optionVar(exists=self.OPT_VAR_SHOW_SAVE_CONFIRMATION):
                    self.pref_show_confirmation.setChecked(bool(cmds.optionVar(q=self.OPT_VAR_SHOW_SAVE_CONFIRMATION)))

            # === SAVE REMINDERS ===
            # Load auto-save interval
            if cmds.optionVar(exists=self.OPT_VAR_AUTO_SAVE_INTERVAL):
                auto_save_interval = cmds.optionVar(q=self.OPT_VAR_AUTO_SAVE_INTERVAL)
                self.pref_auto_save_interval.setValue(auto_save_interval)

            # Load sound preference
            if hasattr(self, 'pref_enable_sound'):
                if cmds.optionVar(exists=self.OPT_VAR_ENABLE_SAVE_SOUND):
                    self.pref_enable_sound.setChecked(bool(cmds.optionVar(q=self.OPT_VAR_ENABLE_SAVE_SOUND)))

            # === AUTOMATIC BACKUPS ===
            # Load auto-backup settings
            if cmds.optionVar(exists=self.OPT_VAR_ENABLE_AUTO_BACKUP):
                enable_auto_backup = bool(cmds.optionVar(q=self.OPT_VAR_ENABLE_AUTO_BACKUP))
                self.pref_enable_auto_backup.setChecked(enable_auto_backup)

            if cmds.optionVar(exists=self.OPT_VAR_BACKUP_INTERVAL):
                backup_interval = cmds.optionVar(q=self.OPT_VAR_BACKUP_INTERVAL)
                self.pref_backup_interval.setValue(backup_interval)

            # Load max backups setting
            if hasattr(self, 'pref_max_backups'):
                if cmds.optionVar(exists=self.OPT_VAR_MAX_BACKUPS):
                    self.pref_max_backups.setValue(cmds.optionVar(q=self.OPT_VAR_MAX_BACKUPS))

            # Load backup location
            if hasattr(self, 'pref_backup_location'):
                if cmds.optionVar(exists=self.OPT_VAR_BACKUP_LOCATION):
                    self.pref_backup_location.setText(cmds.optionVar(q=self.OPT_VAR_BACKUP_LOCATION))

            # === VERSION NOTES ===
            # Load clear quick note setting
            if hasattr(self, 'pref_clear_quick_note'):
                if cmds.optionVar(exists=self.OPT_VAR_CLEAR_QUICK_NOTE):
                    self.pref_clear_quick_note.setChecked(bool(cmds.optionVar(q=self.OPT_VAR_CLEAR_QUICK_NOTE)))

            # Load max history entries
            if hasattr(self, 'pref_max_history'):
                if cmds.optionVar(exists=self.OPT_VAR_MAX_HISTORY_ENTRIES):
                    self.pref_max_history.setValue(cmds.optionVar(q=self.OPT_VAR_MAX_HISTORY_ENTRIES))

            # Load add version notes setting
            if cmds.optionVar(exists=self.OPT_VAR_ADD_VERSION_NOTES):
                add_version_notes = bool(cmds.optionVar(q=self.OPT_VAR_ADD_VERSION_NOTES))
                self.add_version_notes.setChecked(add_version_notes)

            # === FILE PATHS ===
            # Load path preferences
            if cmds.optionVar(exists=self.OPT_VAR_DEFAULT_SAVE_PATH):
                default_path = cmds.optionVar(q=self.OPT_VAR_DEFAULT_SAVE_PATH)
                self.pref_default_path.setText(default_path)

            if cmds.optionVar(exists=self.OPT_VAR_PROJECT_PATH):
                project_path = cmds.optionVar(q=self.OPT_VAR_PROJECT_PATH)
                self.pref_project_path.setText(project_path)

            # Load respect project setting
            if cmds.optionVar(exists=self.OPT_VAR_RESPECT_PROJECT):
                respect_project = bool(cmds.optionVar(q=self.OPT_VAR_RESPECT_PROJECT))
                if hasattr(self, 'respect_project_structure'):
                    self.respect_project_structure.setChecked(respect_project)

            # === UI PREFERENCES ===
            # Load UI preferences
            if cmds.optionVar(exists=self.OPT_VAR_FILE_EXPANDED):
                file_expanded = bool(cmds.optionVar(q=self.OPT_VAR_FILE_EXPANDED))
                self.pref_file_expanded.setChecked(file_expanded)

            if cmds.optionVar(exists=self.OPT_VAR_NAME_EXPANDED):
                name_expanded = bool(cmds.optionVar(q=self.OPT_VAR_NAME_EXPANDED))
                self.pref_name_expanded.setChecked(name_expanded)

            if cmds.optionVar(exists=self.OPT_VAR_LOG_EXPANDED):
                log_expanded = bool(cmds.optionVar(q=self.OPT_VAR_LOG_EXPANDED))
                self.pref_log_expanded.setChecked(log_expanded)

            # Load timed warning preference
            if cmds.optionVar(exists=self.OPT_VAR_ENABLE_TIMED_WARNING):
                enable_timed_warning = bool(cmds.optionVar(q=self.OPT_VAR_ENABLE_TIMED_WARNING))
                print(f"[DEBUG] Loading timed warning preference: {enable_timed_warning}")

                # Only update if different to avoid triggering the stateChanged signal
                if self.enable_timed_warning.isChecked() != enable_timed_warning:
                    self.enable_timed_warning.blockSignals(True)
                    self.enable_timed_warning.setChecked(enable_timed_warning)
                    self.enable_timed_warning.blockSignals(False)

            # Apply UI settings
            self.apply_ui_settings()
        except Exception as e:
            savePlus_core.debug_print(f"Error loading preferences: {e}")
            traceback.print_exc()

        # Initialize save location based on default path
        if cmds.optionVar(exists=self.OPT_VAR_DEFAULT_SAVE_PATH):
            default_path = cmds.optionVar(q=self.OPT_VAR_DEFAULT_SAVE_PATH)
            
            # If the filename input is empty and no current file is open,
            # use the default path
            current_file = cmds.file(query=True, sceneName=True)
            if not current_file and not self.filename_input.text():
                self.selected_directory = default_path
                # Add a placeholder text to show the path
                self.filename_input.setPlaceholderText("untitled.ma")
                
        # Update save location display
        self.update_save_location_display()

    def use_reference_path(self):
        """Extract path from selected referenced node and use it for saving"""
        print("Attempting to use reference path from selection...")
        
        # Get the current selection
        selection = cmds.ls(selection=True)
        
        if not selection:
            self.status_bar.showMessage("No objects selected. Please select a referenced object.", 5000)
            print("No selection found")
            return
        
        # Check if selection is referenced
        reference_nodes = []
        for obj in selection:
            if cmds.referenceQuery(obj, isNodeReferenced=True):
                reference_nodes.append(obj)
        
        if not reference_nodes:
            self.status_bar.showMessage("Selected objects are not references. Please select a referenced object.", 5000)
            print("No referenced objects in selection")
            return
        
        # Get the reference file path
        try:
            # Get the reference node for the first referenced object
            reference_node = cmds.referenceQuery(reference_nodes[0], referenceNode=True)
            
            # Get the file path for this reference
            reference_file = cmds.referenceQuery(reference_node, filename=True)
            print(f"Reference file: {reference_file}")
            
            # Correct way to handle nested references
            # In Maya, when you get a filename from referenceQuery, it already gives
            # the resolved path, so we don't need additional parent handling
            
            # Extract the directory path
            reference_dir = os.path.dirname(reference_file)
            print(f"Using reference directory: {reference_dir}")
            
            # Set this as our new directory
            self.selected_directory = reference_dir
            
            # Update UI
            self.use_current_dir.setChecked(False)
            self.update_save_location_display()
            
            # Check if this path is in a Maya project
            for proj_path in [self.project_directory, cmds.workspace(q=True, rd=True)]:
                if proj_path and reference_dir.startswith(proj_path):
                    print(f"[SavePlus Debug] Reference path is within project: {proj_path}")
                    # Ensure project display is updated
                    self.update_project_tracking()
                    break

            # Extract character/asset name from reference for filename suggestion
            ref_basename = os.path.basename(reference_file)
            asset_name = os.path.splitext(ref_basename)[0]
            
            # Remove common prefixes or namespaces from the asset name if needed
            if '_' in asset_name:
                # Usually character names are after prefixes like "chr_" or "prop_"
                parts = asset_name.split('_')
                if len(parts) > 1 and parts[0].lower() in ['chr', 'prop', 'env', 'rig']:
                    asset_name = '_'.join(parts[1:])  # Remove the prefix
            
            # Ask if user wants to use this name for the file
            if cmds.confirmDialog(
                title='Use Asset Name',
                message=f'Do you want to use "{asset_name}" in your filename?',
                button=['Yes', 'No'],
                defaultButton='Yes',
                cancelButton='No'
            ) == 'Yes':
                # Get current scene file base name or create a new one
                current_file = cmds.file(query=True, sceneName=True)
                if current_file:
                    current_basename = os.path.basename(current_file)
                    # Insert asset name into filename if not already there
                    if asset_name not in current_basename:
                        name_parts = os.path.splitext(current_basename)
                        new_basename = f"{name_parts[0]}_{asset_name}{name_parts[1]}"
                        self.filename_input.setText(new_basename)
                        print(f"Updated filename to include asset name: {new_basename}")
                else:
                    # Suggest a new filename with asset name
                    suggested_name = f"shot_{asset_name}_v001.ma"
                    self.filename_input.setText(suggested_name)
                    self.filename_input.setToolTip(new_path)  # Show full path on hover
                    print(f"Created new suggested filename: {suggested_name}")
                
                self.update_filename_preview()
            
            # Update the filename input if needed (only if we didn't set it from asset name)
            if not self.filename_input.text():
                current_filename = os.path.basename(cmds.file(query=True, sceneName=True) or "untitled.ma")
                new_path = os.path.join(reference_dir, current_filename)
                self.filename_input.setText(os.path.basename(new_path))
                self.filename_input.setToolTip(new_path)  # Show full path on hover
                self.update_filename_preview()
            
            message = f"Save location set to referenced character path: {reference_dir}"
            self.status_bar.showMessage(message, 5000)
            print(message)
            
        except Exception as e:
            message = f"Error getting reference path: {e}"
            self.status_bar.showMessage(message, 5000)
            print(message)
            traceback.print_exc()

    def update_version_preview(self):
        """Update the version preview to show what the next save will be"""
        try:
            filename = self.filename_input.text()
            if not filename:
                self.version_preview_text.setText("N/A")
                return
                
            # Get the base name and extension
            base_name, ext = os.path.splitext(filename)
            if not ext or (ext.lower() not in ['.ma', '.mb']):
                # Use extension from dropdown
                ext = '.ma' if self.filetype_combo.currentIndex() == 0 else '.mb'
            
            # Find the trailing number pattern
            match = re.search(r'(\D*)(\d+)(\D*)$', base_name)
            
            if match:
                # If a number is found
                prefix = match.group(1)
                number = match.group(2)
                suffix = match.group(3)
                
                # Increment the number, preserving leading zeros
                new_number = str(int(number) + 1).zfill(len(number))
                new_base_name = prefix + new_number + suffix
                new_filename = new_base_name + ext
                
                # Show original → new
                self.version_preview_text.setText(f"{os.path.basename(filename)} → {new_filename}")
            else:
                # If no number is found, add "02" to the end
                new_base_name = base_name + "02"
                new_filename = new_base_name + ext
                self.version_preview_text.setText(f"{os.path.basename(filename)} → {new_filename}")
        except Exception as e:
            savePlus_core.debug_print(f"Error updating version preview: {e}")
            self.version_preview_text.setText("Error")

    def force_timer_test(self):
        """Force the timer to run for testing purposes"""
        print("\n" + "#"*70)
        print("#     FORCED TIMER TEST - BYPASSING NORMAL ACTIVATION     #")
        print("#"*70 + "\n")
        
        try:
            # Create a brand new timer to avoid any issues with existing one
            test_timer = QTimer()
            test_timer.setTimerType(QtCore.Qt.CoarseTimer)
            
            # Set up a test function to run
            def test_check():
                print(f"[TEST] Direct timer check at {time.strftime('%H:%M:%S')}")
                self.check_save_time()  # Call the regular check method
            
            # Connect and start
            test_timer.timeout.connect(test_check)
            test_timer.start(5000)  # 5 second interval
            
            print(f"[TEST] Direct test timer created and started")
            print(f"[TEST] Timer active: {test_timer.isActive()}")
            
            # Force immediate checks
            test_check()  # Run immediately
            
            # Return the timer so it doesn't get garbage collected
            return test_timer
        
        except Exception as e:
            print(f"[ERROR] Force timer test failed: {str(e)}")
            traceback.print_exc()
            return None

    def check_save_time_maya(self):
        """Maya scriptJob handler for timeChange events"""
        try:
            current_time = time.time()
            
            # Initialize if needed
            if not hasattr(self, 'last_timer_check'):
                self.last_timer_check = 0
                print("[DEBUG] Initialized last_timer_check")
                
            # Only check every 5 seconds to avoid too frequent checks
            time_since_check = current_time - self.last_timer_check
            if time_since_check < 5:
                return
                
            # Update last check time
            self.last_timer_check = current_time
            print(f"[DEBUG] Maya timeChange timer check at {time.strftime('%H:%M:%S')}")
            
            # Call the regular check method
            self.check_save_time()
        except Exception as e:
            print(f"[ERROR] Timer check failed in scriptJob: {str(e)}")
            traceback.print_exc()

    def closeEvent(self, event):
        """Handle clean up when window is closed"""
        savePlus_core.debug_print("Closing SavePlus UI")
        try:
            # Stop redirecting output
            if hasattr(self, 'log_redirector') and self.log_redirector:
                self.log_redirector.stop_redirect()
            
            # Stop Qt timer
            if hasattr(self, 'save_timer') and self.save_timer.isActive():
                self.save_timer.stop()
                print("[DEBUG] Stopped Qt timer during close")
                
            # Kill any active scriptJobs
            if hasattr(self, 'timer_job_id') and self.timer_job_id is not None:
                try:
                    cmds.scriptJob(kill=self.timer_job_id)
                    print(f"[DEBUG] Killed timer scriptJob during close: {self.timer_job_id}")
                    self.timer_job_id = None
                except Exception as e:
                    print(f"[DEBUG] Error killing scriptJob during close: {e}")
            
            # Stop backup timer
            if hasattr(self, 'backup_timer') and self.backup_timer:
                self.backup_timer.stop()
            
            if hasattr(self, 'new_file_timer') and self.new_file_timer.isActive():
                self.new_file_timer.stop()
                print("[DEBUG] Stopped new file check timer during close")

            # Disable auto resize to prevent errors during shutdown
            self.auto_resize_enabled = False
        except Exception as e:
            savePlus_core.debug_print(f"Error during close: {e}")
        
        super(SavePlusUI, self).closeEvent(event)

    def bootstrap_timer(self):
        """Safely establish the timer after all UI components are ready"""
        print("\n[DEBUG] ========= BOOTSTRAP TIMER STARTING =========")
        
        # Initialize timer attributes
        if not hasattr(self, 'timer_job_id'):
            self.timer_job_id = None
        
        # Get current preference state
        timer_enabled = self.enable_timed_warning.isChecked()
        print(f"[DEBUG] Current timer checkbox state: {timer_enabled}")
        
        # Only enable the timer if checked
        if timer_enabled:
            print("[DEBUG] Timer is enabled, setting up...")
            self.toggle_timed_warning(Qt.Checked)
        else:
            print("[DEBUG] Timer is disabled, no action needed")
        
        print("[DEBUG] ========= BOOTSTRAP COMPLETE =========\n")

    def on_workspace_changed(self):
        """Handler for Maya workspace changes"""
        try:
            print(f"[SavePlus Debug] Workspace change detected")
            
            # Call our new comprehensive update method
            self.update_project_tracking()
            
            # If "Respect project structure" is enabled, update the save location
            if hasattr(self, 'respect_project_structure') and self.respect_project_structure.isChecked():
                # If we have a valid project directory, use it for saving
                if self.project_directory:
                    scenes_dir = os.path.join(self.project_directory, "scenes")
                    if not os.path.exists(scenes_dir):
                        try:
                            os.makedirs(scenes_dir)
                        except Exception as e:
                            print(f"[SavePlus Debug] Could not create scenes directory: {e}")
                    
                    print(f"[SavePlus Debug] Setting save directory to project scenes: {scenes_dir}")
                    self.selected_directory = scenes_dir
                
                # Update the UI
                self.update_save_location_display()
        except Exception as e:
            print(f"[SavePlus Debug] Error handling workspace change: {e}")

    def get_project_status_labels(self):
        """Return all project status labels that need updates"""
        labels = []
        if hasattr(self, 'project_status_label'):
            labels.append(self.project_status_label)
        if hasattr(self, 'project_tab_status_label'):
            labels.append(self.project_tab_status_label)
        return labels

    def set_project_status(self, text, tooltip=None, style=None):
        """Set project status text across all status labels"""
        for label in self.get_project_status_labels():
            label.setText(text)
            if tooltip is not None:
                label.setToolTip(tooltip)
            if style is not None:
                label.setStyleSheet(style)

    def update_project_display(self):
        """Update UI elements to reflect current project"""
        print("[SavePlus Debug] update_project_display called")
        
        if not self.get_project_status_labels():
            print("[SavePlus Debug] No project status labels found")
            return
            
        if self.project_directory:
            truncated_path = truncate_path(self.project_directory, 40)
            self.set_project_status(
                f"Project: {truncated_path}",
                tooltip=self.project_directory,
                style="color: #4CAF50;"
            )  # Green for active project
            print(f"[SavePlus Debug] Project display updated to: {truncated_path}")
        else:
            # Show different text based on whether we're respecting project structure
            if self.respect_project_structure.isChecked():
                # Maya workspace should be used, but no project is active
                workspace = cmds.workspace(query=True, rootDirectory=True)
                if workspace:
                    truncated_path = truncate_path(workspace, 40)
                    self.set_project_status(
                        f"Project: {truncated_path}",
                        tooltip=workspace,
                        style="color: #4CAF50;"
                    )  # Green for active project
                    print(f"[SavePlus Debug] Project display set to workspace: {truncated_path}")
                else:
                    self.set_project_status("No project active", tooltip="No project active", style="color: #F44336;")
                    print("[SavePlus Debug] No workspace found, showing 'No project active'")
            else:
                # We're not respecting project structure, show preference path
                if hasattr(self, 'pref_default_path') and self.pref_default_path.text():
                    default_path = truncate_path(self.pref_default_path.text(), 40)
                    self.set_project_status(
                        f"Using default path: {default_path}",
                        tooltip=self.pref_default_path.text(),
                        style="color: #F39C12;"
                    )  # Orange for preference path
                    print(f"[SavePlus Debug] Project display set to default path: {default_path}")
                else:
                    self.set_project_status("No default path set", tooltip="No default path set", style="color: #F44336;")
                    print("[SavePlus Debug] No default path set, showing warning message")

    def get_save_directory(self):
        """Determine the appropriate directory for saving files based on settings"""
        # IMPORTANT: Check for project structure respect first
        if hasattr(self, 'respect_project_structure') and self.respect_project_structure.isChecked() and self.project_directory:
            # Always use project's scenes directory when this option is enabled
            scenes_dir = os.path.join(self.project_directory, "scenes")
            if not os.path.exists(scenes_dir):
                try:
                    os.makedirs(scenes_dir)
                except Exception as e:
                    print(f"[SavePlus Debug] Could not create scenes directory: {e}")
            return scenes_dir
        
        # Then handle other cases
        current_file_path = cmds.file(query=True, sceneName=True)
        
        if current_file_path and self.use_current_dir.isChecked():
            # Use directory of current file
            return os.path.dirname(current_file_path)
        
        if self.selected_directory:
            # Use explicitly selected directory
            return self.selected_directory
        
        if current_file_path:
            # Fallback to current file's directory
            return os.path.dirname(current_file_path)
        
        # Ultimate fallback - Maya's default scenes directory
        workspace = cmds.workspace(query=True, directory=True)
        return os.path.join(workspace, "scenes")

    def open_current_directory(self):
        """Open the current save directory in the system file explorer"""
        import sys
        import os
        import subprocess
        import traceback

        print("\n" + "="*50)
        print("FOLDER OPEN BUTTON CLICKED!")
        print("="*50)
        
        try:
            # Get the current save directory
            save_dir = self.get_save_directory()
            print(f"Attempting to open directory: {save_dir}")
            
            if not os.path.exists(save_dir):
                print(f"Directory does not exist: {save_dir}")
                self.status_bar.showMessage(f"Directory not found: {save_dir}", 5000)
                return
                    
            # Open directory using the appropriate command for the OS
            if sys.platform == 'win32':
                print(f"Using Windows explorer command for path: {save_dir}")
                
                # Method 1: Use os.startfile which properly handles paths with spaces
                try:
                    os.startfile(save_dir)
                    print(f"Opened directory using os.startfile")
                except Exception as startfile_error:
                    print(f"os.startfile failed: {startfile_error}")
                    
                    # Method 2: Ensure the path is properly quoted for Windows Explorer
                    try:
                        # Normalize path to use backslashes for Windows
                        win_path = os.path.normpath(save_dir)
                        # Use string with quotes around the path
                        subprocess.Popen(f'explorer "{win_path}"', shell=True)
                        print(f"Opened directory using shell=True with quoted path")
                    except Exception as shell_error:
                        print(f"Shell command failed: {shell_error}")
                        
                        # Method 3: Last resort - pass as a list but with proper formatting
                        normalized_path = save_dir.replace('/', '\\')
                        subprocess.Popen(['explorer', normalized_path])
                        print(f"Tried last resort method")
                    
            elif sys.platform == 'darwin':  # macOS
                print(f"Using macOS open command for path: {save_dir}")
                subprocess.Popen(['open', save_dir])
            else:  # Linux
                print(f"Using Linux xdg-open command for path: {save_dir}")
                subprocess.Popen(['xdg-open', save_dir])
                    
            print(f"Successfully opened directory: {save_dir}")
            self.status_bar.showMessage(f"Opened folder: {save_dir}", 3000)
            
        except Exception as e:
            error_message = f"Error opening directory: {e}"
            print(error_message)
            traceback.print_exc()  # Print detailed error information
            
            # Show error in the status bar if available
            if hasattr(self, 'status_bar'):
                self.status_bar.showMessage(error_message, 5000)

    def setup_file_monitoring(self):
        """Set up monitoring for file open and new scene events"""
        try:
            # Debug the file create/open event triggers
            self.debug_scriptJob = cmds.scriptJob(
                event=["idle", lambda: self.debug_path_issue() if not cmds.file(query=True, sceneName=True) else None],
                runOnce=True
            )
            print(f"[SavePlus Debug] Set up one-time debug script job")
            
            # Monitor for file open events
            self.file_open_job = cmds.scriptJob(
                event=["SceneOpened", self.on_file_opened],
                protected=True
            )
            print(f"[SavePlus Debug] Connected to scene opened event")
            
            # Also monitor for new scene events
            self.new_scene_job = cmds.scriptJob(
                event=["NewSceneOpened", self.on_file_opened],
                protected=True
            )
            print(f"[SavePlus Debug] Connected to new scene event")
            
        except Exception as e:
            print(f"[SavePlus Debug] Could not connect to file monitoring events: {e}")
            traceback.print_exc()
                
        except Exception as e:
            print(f"[SavePlus Debug] Could not connect to file monitoring events: {e}")

    def on_file_opened(self):
        """Handle file open events"""
        try:
            print("[SavePlus Debug] on_file_opened triggered")
            
            # Get new file path
            current_file = cmds.file(query=True, sceneName=True)
            
            # Check if this is a new, unsaved file
            is_new_file = not current_file
            
            if is_new_file:
                print("[SavePlus Debug] New file detected - calling reset_for_new_file")
                self.reset_for_new_file()
            else:
                print(f"[SavePlus Debug] File opened: {current_file}")
                
                # Update UI with new file
                self.filename_input.setText(os.path.basename(current_file))
                self.filename_input.setToolTip(current_file)
                
                # Update directory tracking
                self.selected_directory = os.path.dirname(current_file)
                
                # Automatically check "Use current directory"
                self.use_current_dir.setChecked(True)
                
                # Check if project has changed and update project tracking
                self.update_project_tracking()
                
                # Update save location display
                self.update_save_location_display()
            
            # Update history tab if it's visible
            if self.tab_widget.currentIndex() == self.history_tab_index:  # History tab
                self.populate_history()
        except Exception as e:
            print(f"[SavePlus Debug] Error handling file open: {e}")
            traceback.print_exc()

    def update_project_tracking(self):
        """Update project tracking when files or workspaces change"""
        try:
            # Get current Maya project
            current_project = savePlus_core.get_maya_project_directory()
            
            # If project has changed, update it
            if current_project != self.project_directory:
                print(f"[SavePlus Debug] Project changed from {self.project_directory} to {current_project}")
                self.project_directory = current_project
                
                # Update UI to reflect project change
                self.update_project_display()
                self.refresh_project_scenes_list(force=True)
                
                # If no project is active but we have a default path in preferences, use that
                if not self.project_directory and hasattr(self, 'pref_default_path') and self.pref_default_path.text():
                    default_path = self.pref_default_path.text()
                    print(f"[SavePlus Debug] No project active, using default path: {default_path}")
                    
                    # Only update if we're respecting project structure
                    if hasattr(self, 'respect_project_structure') and self.respect_project_structure.isChecked():
                        self.selected_directory = default_path
            
            # Also update save location display to reflect any changes
            self.update_save_location_display()
        except Exception as e:
            print(f"[SavePlus Debug] Error updating project tracking: {e}")

    def debug_path_issue(self):
        """Debug function to print current project paths and settings"""
        print("\n" + "="*80)
        print("DEBUGGING PROJECT PATH ISSUE")
        print("="*80)
        
        print(f"Current file: {cmds.file(query=True, sceneName=True) or 'NONE (new file)'}")
        print(f"Maya workspace: {cmds.workspace(query=True, rootDirectory=True) or 'NONE'}")
        print(f"self.project_directory: {self.project_directory or 'NONE'}")
        print(f"self.selected_directory: {self.selected_directory or 'NONE'}")
        print(f"Default path from prefs: {self.pref_default_path.text() if hasattr(self, 'pref_default_path') else 'NONE'}")
        print(f"'Use current directory' checked: {self.use_current_dir.isChecked()}")
        print(f"'Respect project structure' checked: {self.respect_project_structure.isChecked()}")
        
        print("-"*80)
        print("FIXING PROJECT PATH DISPLAY")
        print("-"*80)
        
        # Force reset project path for new files
        if not cmds.file(query=True, sceneName=True):
            print("Detected new file - resetting project path display")
            
            # Clear the stored project directory for new files if not respecting project structure
            if not self.respect_project_structure.isChecked():
                self.project_directory = None
                print("Cleared project_directory (not respecting project structure)")
            
            # Set the proper selected directory
            if hasattr(self, 'pref_default_path') and self.pref_default_path.text():
                self.selected_directory = self.pref_default_path.text()
                print(f"Set selected_directory to preference default: {self.selected_directory}")
            else:
                # Fall back to Maya's default scenes directory
                workspace = cmds.workspace(query=True, directory=True)
                scenes_dir = os.path.join(workspace, "scenes")
                self.selected_directory = scenes_dir
                print(f"Set selected_directory to Maya default: {self.selected_directory}")
            
            # Update the project display
            self.update_project_display()
            
            # Update the save location display
            self.update_save_location_display()
            
            print("Project display updated")
        
        print("="*80)
        return True  # Return true so this can be called from scriptJob if needed

    def reset_for_new_file(self):
        """Reset UI for new, unsaved files"""
        print("[SavePlus Debug] reset_for_new_file called")
        
        # Check if this is actually a new file
        if cmds.file(query=True, sceneName=True):
            print("[SavePlus Debug] Not a new file, skipping reset")
            return
        
        print("[SavePlus Debug] CONFIRMED NEW FILE - Resetting display")
        
        # Reset UI filename
        self.filename_input.setText("untitled.ma")
        
        # Handle the directory based on settings
        if self.respect_project_structure.isChecked():
            # If respecting project structure, use the current Maya workspace
            workspace_dir = cmds.workspace(query=True, rootDirectory=True)
            scenes_dir = os.path.join(workspace_dir, "scenes")
            self.selected_directory = scenes_dir
            self.project_directory = workspace_dir
            print(f"[SavePlus Debug] Using workspace scenes directory: {scenes_dir}")
        else:
            # If not respecting project structure, use the default path from preferences
            if hasattr(self, 'pref_default_path') and self.pref_default_path.text():
                default_path = self.pref_default_path.text()
                self.selected_directory = default_path
                # Clear the project directory to show "no project active"
                self.project_directory = None
                print(f"[SavePlus Debug] Using preference default path: {default_path}")
            else:
                # Fall back to Maya's default scenes directory
                workspace = cmds.workspace(query=True, directory=True)
                scenes_dir = os.path.join(workspace, "scenes")
                self.selected_directory = scenes_dir
                self.project_directory = None
                print(f"[SavePlus Debug] Using Maya default scenes directory: {scenes_dir}")
        
        # Update the UI displays
        self.update_project_display()
        self.update_save_location_display()
        print("[SavePlus Debug] Reset for new file completed")

    def force_reset_project_display(self):
        """Force reset project display for new files - ignores Maya's workspace"""
        try:
            print("[SavePlus Debug] FORCE RESET of project display called")
            
            # Only proceed if this is a new file
            if cmds.file(query=True, sceneName=True):
                print("[SavePlus Debug] Not a new file, skipping force reset")
                return False
                
            print("[SavePlus Debug] New file confirmed - forcing project reset")
            
            # Forcibly update project display regardless of Maya's workspace
            if not self.respect_project_structure.isChecked():
                # If not respecting project structure, force clear project path
                self.project_directory = None
                self.set_project_status(
                    "No project active",
                    tooltip="No project is active for this new file",
                    style="color: #F44336;"
                )  # Red
                
                # Set selected directory to preference default if available
                if hasattr(self, 'pref_default_path') and self.pref_default_path.text():
                    self.selected_directory = self.pref_default_path.text()
                else:
                    # Default to Maya scenes directory
                    workspace = cmds.workspace(query=True, directory=True)
                    self.selected_directory = os.path.join(workspace, "scenes")
            else:
                # If respecting project structure, show current workspace but make it clear it's for a new file
                workspace = cmds.workspace(query=True, rootDirectory=True)
                if workspace:
                    self.project_directory = workspace
                    truncated_path = truncate_path(workspace, 40)
                    self.set_project_status(
                        f"Project (new file): {truncated_path}",
                        tooltip=f"Using workspace for new file: {workspace}",
                        style="color: #FFA500;"
                    )  # Orange
                    
                    # Set selected directory to workspace scenes folder
                    self.selected_directory = os.path.join(workspace, "scenes")
                else:
                    # No workspace set
                    self.project_directory = None
                    self.set_project_status(
                        "No project active",
                        tooltip="No project is active for this new file",
                        style="color: #F44336;"
                    )  # Red
                    
                    # Default to Maya scenes directory
                    workspace = cmds.workspace(query=True, directory=True)
                    self.selected_directory = os.path.join(workspace, "scenes")
            
            # Update filename to default
            self.filename_input.setText("untitled.ma")
            
            # Force update save location display
            self.update_save_location_display()
            
            print("[SavePlus Debug] Force reset of project display completed")
            return True
        except Exception as e:
            print(f"[SavePlus Debug] Error in force_reset_project_display: {e}")
            traceback.print_exc()
            return False

    def direct_reset_project_display(self):
        """Directly manipulate the project display label regardless of Maya's state"""
        print("[SavePlus] Performing direct reset of project display")
        
        # Get reference to the project label
        if not self.get_project_status_labels():
            print("[SavePlus] No project label found to reset")
            return
        
        # Force text change regardless of internal state
        self.set_project_status(
            "No active project (manually reset)",
            tooltip="Project display was manually reset",
            style="color: #888888; font-style: italic;"
        )
        
        # If we want to preserve some internal state consistency
        self.project_directory = None
        
        # Update save location
        if hasattr(self, 'pref_default_path') and self.pref_default_path.text():
            self.selected_directory = self.pref_default_path.text()
        else:
            # Default to Maya's default scenes folder
            workspace = cmds.workspace(query=True, directory=True)
            self.selected_directory = os.path.join(workspace, "scenes")
        
        # Update the save location display
        self.update_save_location_display()
        
        print("[SavePlus] Direct reset of project display completed")

    def apply_ui_settings(self):
        """Apply UI settings from preferences"""
        try:
            # Set collapsed state of sections based on preferences
            file_expanded = self.pref_file_expanded.isChecked()
            name_expanded = self.pref_name_expanded.isChecked()
            log_expanded = self.pref_log_expanded.isChecked()
            
            # Only change state if different from current state to avoid unnecessary toggling
            if self.file_options_section.is_collapsed() == file_expanded:
                self.file_options_section.toggle_content()
                
            if self.name_gen_section.is_collapsed() == name_expanded:
                self.name_gen_section.toggle_content()
                
            if self.log_section.is_collapsed() == log_expanded:
                self.log_section.toggle_content()
            
            # Adjust window size to reflect changes
            self.adjust_window_size()
        except Exception as e:
            savePlus_core.debug_print(f"Error applying UI settings: {e}")
