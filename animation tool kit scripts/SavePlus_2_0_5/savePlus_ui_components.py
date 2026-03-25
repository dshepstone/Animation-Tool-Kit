"""
SavePlus UI Components - Custom UI classes for the SavePlus tool
Part of the SavePlus toolset for Maya 2025
"""

import sys
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, 
                              QLabel, QDialog, QLineEdit, QHBoxLayout,
                              QCheckBox, QStyle, QSizePolicy, QPlainTextEdit)
from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

import savePlus_core

VERSION = savePlus_core.VERSION

class LogRedirector:
    """A class to redirect Maya's script output to a QTextEdit widget"""
    
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.orig_stdout = None
        self.orig_stderr = None
    
    def write(self, message):
        # Write to the text widget
        if self.text_widget:
            self.text_widget.append(message.rstrip())
            # Make sure to scroll to the bottom
            self.text_widget.verticalScrollBar().setValue(
                self.text_widget.verticalScrollBar().maximum()
            )
    
    def flush(self):
        pass
    
    def start_redirect(self):
        """Start redirecting stdout and stderr"""
        self.orig_stdout = sys.stdout
        self.orig_stderr = sys.stderr
        sys.stdout = self
        sys.stderr = self
    
    def stop_redirect(self):
        """Stop redirecting stdout and stderr"""
        if self.orig_stdout and self.orig_stderr:
            sys.stdout = self.orig_stdout
            sys.stderr = self.orig_stderr


class AboutDialog(QDialog):
    """About dialog for SavePlus"""
    
    def __init__(self, parent=None):
        super(AboutDialog, self).__init__(parent)
        
        self.setWindowTitle("About SavePlus")
        self.setMinimumWidth(300)
        self.setFixedSize(400, 250)
        
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("SavePlus")
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        title.setAlignment(Qt.AlignCenter)
        
        # Version
        version = QLabel(f"Version {VERSION}")
        version.setAlignment(Qt.AlignCenter)
        
        # Description
        desc = QLabel(
            "SavePlus provides a simple way to increment your save files.\n"
            "Based on the original MEL script by Neal Singleton."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        
        # Examples
        examples = QLabel(
            "Examples:\n"
            "filename.mb → filename02.mb\n"
            "filename5.mb → filename6.mb\n"
            "filename00002.mb → filename00003.mb\n"
            "scene45_99.mb → scene45_100.mb"
        )
        examples.setWordWrap(True)
        examples.setAlignment(Qt.AlignCenter)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        
        # Add widgets to layout
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addSpacing(10)
        layout.addWidget(desc)
        layout.addSpacing(10)
        layout.addWidget(examples)
        layout.addStretch()
        layout.addWidget(close_button)
        
        self.setLayout(layout)


class TimedWarningDialog(QDialog):
    """Warning dialog for save reminders"""
    
    def __init__(self, parent=None, first_time=False, interval=15):
        super(TimedWarningDialog, self).__init__(parent)
        
        self.setWindowTitle("Save Reminder")
        self.setMinimumWidth(350)
        self.disable_warnings = False
        
        layout = QVBoxLayout(self)
        
        # Warning icon and message
        message_layout = QHBoxLayout()
        
        icon_label = QLabel()
        icon_label.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(32, 32))
        
        if first_time:
            message_text = f"You've enabled save reminders. You'll be reminded to save every {interval} minute{'s' if interval != 1 else ''}."
        else:
            message_text = f"It's been {interval} minute{'s' if interval != 1 else ''} since your last save.\nWould you like to save your work now?"
        
        self.message = QLabel(message_text)
        self.message.setWordWrap(True)
        
        message_layout.addWidget(icon_label)
        message_layout.addWidget(self.message, 1)
        
        # Checkbox for disabling warnings (only shown for first-time saves)
        self.disable_checkbox = None
        if first_time:
            self.disable_checkbox = QCheckBox("Disable these reminders")
            self.disable_checkbox.setChecked(False)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        save_button = QPushButton("Save Now" if not first_time else "Got it")
        save_button.clicked.connect(self.accept)
        
        remind_later_button = None
        if not first_time:
            remind_later_button = QPushButton("Remind Me Later")
            remind_later_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        if remind_later_button:
            button_layout.addWidget(remind_later_button)
        
        # Add to main layout
        layout.addLayout(message_layout)
        if self.disable_checkbox:
            layout.addWidget(self.disable_checkbox)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def update_message(self, minutes):
        """Update message to show current interval"""
        if hasattr(self, 'first_time') and not self.first_time:
            message_text = f"It's been {minutes} minute{'s' if minutes != 1 else ''} since your last save.\nWould you like to save your work now?"
            self.message.setText(message_text)

    def get_disable_warnings(self):
        """Return whether warnings should be disabled"""
        if self.disable_checkbox:
            return self.disable_checkbox.isChecked()
        return False


class NoteInputDialog(QDialog):
    """Dialog for entering version notes"""
    
    def __init__(self, parent=None):
        super(NoteInputDialog, self).__init__(parent)
        
        self.setWindowTitle("Version Notes")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Explanation label
        help_label = QLabel("Enter notes for this version (optional):")
        
        # Text input
        self.text_edit = QPlainTextEdit()
        self.text_edit.setMinimumHeight(100)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        save_button = QPushButton("Save with Notes")
        save_button.clicked.connect(self.accept)
        
        skip_button = QPushButton("Skip Notes")
        skip_button.clicked.connect(self.reject)
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(save_button)
        buttons_layout.addWidget(skip_button)
        
        # Add to main layout
        layout.addWidget(help_label)
        layout.addWidget(self.text_edit)
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
    
    def get_notes(self):
        """Return the entered notes"""
        return self.text_edit.toPlainText()


class ZurbriggStyleCollapsibleHeader(QWidget):
    """Header widget for the collapsible frame in Zurbrigg style"""
    
    def __init__(self, title, parent=None):
        super(ZurbriggStyleCollapsibleHeader, self).__init__(parent)
        
        # Create layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 2, 5, 2)
        
        # Icon indicator (+ for collapsed, - for expanded)
        self.icon_label = QLabel("-")
        self.icon_label.setFixedWidth(15)
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        # Title with indicator color
        self.title_label = QLabel(title)
        bold_font = QFont()
        bold_font.setBold(True)
        self.title_label.setFont(bold_font)
        
        # Add widgets to layout
        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.title_label)
        self.layout.addStretch()
        
        # Set frame style and fixed height
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), palette.mid().color())
        self.setPalette(palette)
        
        self.setFixedHeight(26)
        
        # Default state is expanded
        self.is_expanded = True
    
    def update_state(self, is_expanded):
        """Update the icon based on the expanded state"""
        self.is_expanded = is_expanded
        self.icon_label.setText("-" if is_expanded else "+")
    
    def mousePressEvent(self, event):
        """Handle mouse press event to toggle collapse state"""
        if self.parent():
            self.parent().toggle_content()
        super(ZurbriggStyleCollapsibleHeader, self).mousePressEvent(event)

    def add_widget(self, widget):
        """Add a widget to the content layout"""
        self.content_layout.addWidget(widget)
        
        # Add a small spacer at the bottom for visual breathing room
        spacer = QWidget()
        spacer.setFixedHeight(5)
        self.content_layout.addWidget(spacer)

class ZurbriggStyleCollapsibleFrame(QWidget):
    """
    A collapsible frame widget that maintains fixed position in layouts,
    similar to how the Zurbrigg Advanced Playblast UI works.
    """
    
    # Define a signal that will be emitted when content is toggled
    toggled = QtCore.Signal()
    
    def __init__(self, title, parent=None, collapsed=True):
        super(ZurbriggStyleCollapsibleFrame, self).__init__(parent)
        
        # Store the current state
        self.collapsed = collapsed
        
        # Main layout for the frame
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(1)
        
        # Create header
        self.header = ZurbriggStyleCollapsibleHeader(title, self)
        
        # Create content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)
        
        # Set initial visibility based on collapsed state
        self.content_widget.setVisible(not collapsed)
        self.header.update_state(not collapsed)
        
        # Add widgets to main layout
        self.main_layout.addWidget(self.header)
        self.main_layout.addWidget(self.content_widget)
        
        # Ensure fixed position even when collapsed
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    
    def toggle_content(self):
        """Toggle the visibility of the content"""
        self.collapsed = not self.collapsed
        
        # Update the header state
        self.header.update_state(not self.collapsed)
        
        # Toggle visibility
        self.content_widget.setVisible(not self.collapsed)
        
        # Set size hint to force layout update
        if not self.collapsed:
            # When expanding, allow natural size
            self.content_widget.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        else:
            # When collapsing, set minimum height to zero
            self.content_widget.setMaximumHeight(0)
        
        # Emit toggled signal to notify parent of state change
        self.toggled.emit()
    
    def add_widget(self, widget):
        """Add a widget to the content layout"""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout):
        """Add a layout to the content layout"""
        self.content_layout.addLayout(layout)

    def sizeHint(self):
        """Return a size hint that reflects the collapsed state"""
        size = super(ZurbriggStyleCollapsibleFrame, self).sizeHint()
        if self.collapsed:
            size.setHeight(self.header.height())
        return size
        
    def is_collapsed(self):
        """Return the current collapsed state"""
        return self.collapsed
        
    def set_collapsed(self, collapsed):
        """Set the collapsed state directly"""
        if self.collapsed != collapsed:
            self.toggle_content()


class EnlargedNotesViewerDialog(QDialog):
    """Dialog for viewing notes in a larger, more readable window"""

    def __init__(self, parent=None, filename="", notes="", file_path="", editable=True):
        super(EnlargedNotesViewerDialog, self).__init__(parent)

        self.file_path = file_path
        self.notes_modified = False

        self.setWindowTitle(f"Notes - {filename}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # File info header
        info_layout = QVBoxLayout()

        filename_label = QLabel(f"<b>File:</b> {filename}")
        filename_label.setStyleSheet("font-size: 12px; color: #CCCCCC;")
        info_layout.addWidget(filename_label)

        if file_path:
            path_label = QLabel(f"<b>Path:</b> {file_path}")
            path_label.setStyleSheet("font-size: 10px; color: #888888;")
            path_label.setWordWrap(True)
            info_layout.addWidget(path_label)

        layout.addLayout(info_layout)

        # Separator
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #444444;")
        layout.addWidget(separator)

        # Notes header
        notes_header = QLabel("Version Notes:")
        notes_header.setStyleSheet("font-weight: bold; color: #CCCCCC; font-size: 12px;")
        layout.addWidget(notes_header)

        # Notes text area
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlainText(notes)
        self.notes_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #2A2A2A;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 10px;
                font-size: 12px;
                line-height: 1.5;
            }
        """)
        if not editable:
            self.notes_edit.setReadOnly(True)
        else:
            self.notes_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.notes_edit)

        # Helper text
        if editable:
            helper_text = QLabel("Edit notes above and click 'Save Notes' to update.")
            helper_text.setStyleSheet("color: #666666; font-size: 10px; font-style: italic;")
            layout.addWidget(helper_text)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        if editable:
            save_button = QPushButton("Save Notes")
            save_button.setToolTip("Save changes to the notes")
            save_button.clicked.connect(self.accept)
            buttons_layout.addWidget(save_button)

        close_button = QPushButton("Close")
        close_button.setToolTip("Close this window")
        close_button.clicked.connect(self.reject)
        buttons_layout.addWidget(close_button)

        layout.addLayout(buttons_layout)

    def _on_text_changed(self):
        """Track when text has been modified"""
        self.notes_modified = True

    def get_notes(self):
        """Return the current notes text"""
        return self.notes_edit.toPlainText()

    def has_changes(self):
        """Check if notes have been modified"""
        return self.notes_modified


class ProjectScenesBrowserDialog(QDialog):
    """Dialog for browsing and opening scenes from the project's scenes folder"""

    def __init__(self, parent=None, project_path="", version_history=None):
        super(ProjectScenesBrowserDialog, self).__init__(parent)

        self.project_path = project_path
        self.version_history = version_history
        self.scenes_path = ""

        self.setWindowTitle("Project Scenes Browser")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        self.resize(900, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header with project info
        header_layout = QHBoxLayout()

        project_label = QLabel(f"<b>Project:</b> {project_path}")
        project_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
        project_label.setWordWrap(True)
        header_layout.addWidget(project_label, 1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Refresh the file list")
        refresh_btn.clicked.connect(self.refresh_file_list)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Helper text
        helper_text = QLabel("Browse and open Maya scene files from your project's scenes folder. Double-click to open a file.")
        helper_text.setStyleSheet("color: #888888; font-size: 10px; font-style: italic;")
        layout.addWidget(helper_text)

        # Main content area with splitter
        from PySide6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side - File list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        files_label = QLabel("Scene Files:")
        files_label.setStyleSheet("font-weight: bold; color: #CCCCCC;")
        left_layout.addWidget(files_label)

        from PySide6.QtWidgets import QListWidget
        self.files_list = QListWidget()
        self.files_list.setAlternatingRowColors(True)
        self.files_list.setStyleSheet("""
            QListWidget {
                background-color: #2A2A2A;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #3A5A8A;
            }
            QListWidget::item:hover {
                background-color: #3A3A3A;
            }
        """)
        self.files_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.files_list.itemDoubleClicked.connect(self._on_double_click)
        left_layout.addWidget(self.files_list)

        splitter.addWidget(left_widget)

        # Right side - File info and notes
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        info_label = QLabel("File Information:")
        info_label.setStyleSheet("font-weight: bold; color: #CCCCCC;")
        right_layout.addWidget(info_label)

        # File details
        self.file_info_label = QLabel("Select a file to view details")
        self.file_info_label.setStyleSheet("color: #888888; padding: 10px; background-color: #2A2A2A; border-radius: 4px;")
        self.file_info_label.setWordWrap(True)
        self.file_info_label.setMinimumHeight(80)
        right_layout.addWidget(self.file_info_label)

        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet("font-weight: bold; color: #CCCCCC;")
        right_layout.addWidget(notes_label)

        self.notes_display = QPlainTextEdit()
        self.notes_display.setReadOnly(True)
        self.notes_display.setPlaceholderText("No notes available for this file")
        self.notes_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #2A2A2A;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 10px;
            }
        """)
        right_layout.addWidget(self.notes_display)

        # View full notes button
        view_notes_btn = QPushButton("View Notes in Full Window")
        view_notes_btn.setToolTip("Open notes in a larger, easier to read window")
        view_notes_btn.clicked.connect(self._view_full_notes)
        right_layout.addWidget(view_notes_btn)

        splitter.addWidget(right_widget)
        splitter.setSizes([400, 400])

        layout.addWidget(splitter)

        # Bottom buttons
        buttons_layout = QHBoxLayout()

        open_folder_btn = QPushButton("Open Scenes Folder")
        open_folder_btn.setToolTip("Open the scenes folder in file explorer")
        open_folder_btn.clicked.connect(self._open_scenes_folder)
        buttons_layout.addWidget(open_folder_btn)

        buttons_layout.addStretch()

        open_btn = QPushButton("Open Selected")
        open_btn.setToolTip("Open the selected scene file in Maya")
        open_btn.clicked.connect(self._open_selected)
        buttons_layout.addWidget(open_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(close_btn)

        layout.addLayout(buttons_layout)

        # Store selected file path
        self.selected_file_path = ""

        # Populate the file list
        self.refresh_file_list()

    def refresh_file_list(self):
        """Refresh the list of scene files"""
        import os

        self.files_list.clear()
        self.selected_file_path = ""

        if not self.project_path:
            return

        # Find scenes directory
        self.scenes_path = os.path.join(self.project_path, "scenes")

        if not os.path.exists(self.scenes_path):
            from PySide6.QtWidgets import QListWidgetItem
            item = QListWidgetItem("No scenes folder found")
            item.setData(Qt.UserRole, "")
            self.files_list.addItem(item)
            return

        # Get all Maya files
        maya_files = []
        for root, dirs, files in os.walk(self.scenes_path):
            for file in files:
                if file.lower().endswith(('.ma', '.mb')):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.scenes_path)
                    # Get file modification time
                    mod_time = os.path.getmtime(full_path)
                    maya_files.append((rel_path, full_path, mod_time))

        # Sort by modification time (newest first)
        maya_files.sort(key=lambda x: x[2], reverse=True)

        # Add to list
        from PySide6.QtWidgets import QListWidgetItem
        from datetime import datetime

        for rel_path, full_path, mod_time in maya_files:
            mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
            item = QListWidgetItem(f"{rel_path}  [{mod_date}]")
            item.setData(Qt.UserRole, full_path)
            item.setToolTip(full_path)
            self.files_list.addItem(item)

        if not maya_files:
            item = QListWidgetItem("No Maya scene files found")
            item.setData(Qt.UserRole, "")
            self.files_list.addItem(item)

    def _on_selection_changed(self):
        """Handle file selection change"""
        import os
        from datetime import datetime

        selected_items = self.files_list.selectedItems()
        if not selected_items:
            self.selected_file_path = ""
            self.file_info_label.setText("Select a file to view details")
            self.notes_display.setPlainText("")
            return

        file_path = selected_items[0].data(Qt.UserRole)
        if not file_path or not os.path.exists(file_path):
            self.selected_file_path = ""
            self.file_info_label.setText("File not found")
            self.notes_display.setPlainText("")
            return

        self.selected_file_path = file_path

        # Get file info
        stat = os.stat(file_path)
        size_mb = stat.st_size / (1024 * 1024)
        mod_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        info_text = f"""<b>Filename:</b> {os.path.basename(file_path)}<br>
<b>Size:</b> {size_mb:.2f} MB<br>
<b>Modified:</b> {mod_time}<br>
<b>Path:</b> {file_path}"""

        self.file_info_label.setText(info_text)

        # Get notes from version history
        notes = ""
        if self.version_history:
            versions = self.version_history.get_versions_for_file(file_path)
            for version in versions:
                if os.path.normpath(version.get('path', '')) == os.path.normpath(file_path):
                    notes = version.get('notes', '')
                    break

        self.notes_display.setPlainText(notes if notes else "")

    def _on_double_click(self, item):
        """Handle double-click on file item"""
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.selected_file_path = file_path
            self.accept()

    def _open_selected(self):
        """Open the selected file"""
        if self.selected_file_path:
            self.accept()

    def _view_full_notes(self):
        """View notes in enlarged dialog"""
        import os

        if not self.selected_file_path:
            return

        notes = self.notes_display.toPlainText()
        filename = os.path.basename(self.selected_file_path)

        dialog = EnlargedNotesViewerDialog(
            self,
            filename=filename,
            notes=notes,
            file_path=self.selected_file_path,
            editable=False
        )
        dialog.exec()

    def _open_scenes_folder(self):
        """Open scenes folder in file explorer"""
        import subprocess
        import sys
        import os

        if not self.scenes_path or not os.path.exists(self.scenes_path):
            return

        try:
            if sys.platform == 'win32':
                os.startfile(self.scenes_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.scenes_path])
            else:
                subprocess.Popen(['xdg-open', self.scenes_path])
        except Exception as e:
            print(f"Error opening folder: {e}")

    def get_selected_file(self):
        """Return the selected file path"""
        return self.selected_file_path
