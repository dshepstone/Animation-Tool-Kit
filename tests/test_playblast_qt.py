"""Real Qt process integration; Maya APIs remain mocked (no viewport claims)."""
import ast
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from test_playblast_reliability import SOURCE, NS

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    QtCore = None


@unittest.skipUnless(QtCore, 'Requires PySide6')
class QtProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        cls.ns = dict(NS, QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), cls.ns)

    def engine(self):
        p = self.ns['PBCPlayblast'].__new__(self.ns['PBCPlayblast'])
        QtCore.QObject.__init__(p)
        p.log_error = Mock()
        p.log_warning = Mock()
        p.log_output = Mock()
        p.initialize_ffmpeg_process()
        return p

    def test_real_process_success(self):
        # Wrapper adds FFmpeg arguments; exercise it with the actual executable.
        if not shutil.which('ffmpeg'):
            self.skipTest('ffmpeg unavailable')
        p = self.engine()
        self.assertTrue(p.execute_ffmpeg_command(shutil.which('ffmpeg'), ['-version']))

    def test_real_process_nonzero_exit(self):
        if not shutil.which('ffmpeg'):
            self.skipTest('ffmpeg unavailable')
        self.assertFalse(self.engine().execute_ffmpeg_command(shutil.which('ffmpeg'), ['-invalid-atk-option']))

    def test_real_process_cannot_start(self):
        self.assertFalse(self.engine().execute_ffmpeg_command('/not-an-atk-executable', []))

    def test_output_tab_checkbox_is_visible_on_own_row(self):
        widget_cls = self.ns['PBCPlayblastWidget']
        widget = widget_cls.__new__(widget_cls)
        QtWidgets.QWidget.__init__(widget)
        # Build the real output layout with real Qt controls, without Maya state.
        method = next(n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='PBCPlayblastWidget')
        method = next(n for n in method.body if isinstance(n,ast.FunctionDef) and n.name=='_build_output_tab')
        for node in ast.walk(method):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id=='self':
                name = node.attr
                if hasattr(widget,name):
                    continue
                if name.endswith(('_cb','CheckBox')):
                    control = QtWidgets.QCheckBox('Force overwrite existing output' if name=='force_overwrite_cb' else name)
                elif name.endswith(('SpinBox','_sb')):
                    control = QtWidgets.QSpinBox()
                elif name.endswith(('Button','_btn')):
                    control = QtWidgets.QPushButton(name)
                elif name.endswith(('ComboBox','_cmb')):
                    control = QtWidgets.QComboBox()
                elif name.endswith(('Label','_label')):
                    control = QtWidgets.QLabel(name)
                else:
                    control = QtWidgets.QLineEdit()
                setattr(widget,name,control)
        tab = widget._build_output_tab()
        tab.resize(700,700)
        tab.show()
        self.app.processEvents()
        self.assertTrue(widget.force_overwrite_cb.isVisible())
        self.assertFalse(widget.force_overwrite_cb.isChecked())
        self.assertIn('existing output',widget.force_overwrite_cb.text())
        self.assertGreater(widget.force_overwrite_cb.mapTo(tab,QtCore.QPoint()).y(),
                           widget.output_filename_le.mapTo(tab,QtCore.QPoint()).y())
        tab.close()


if __name__=='__main__':
    unittest.main()
