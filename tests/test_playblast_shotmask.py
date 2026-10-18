"""Regression checks for shot-mask texture failure/cleanup without Maya."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1]/'animation tool kit scripts/Playblast_Creator/playblast_creator.py'


class ShotMaskTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PlayblastCreatorShotMaskDrawOverride')
        method = next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='draw_image')
        self.manager=Mock()
        self.om=Mock()
        self.omr=Mock()
        self.omr.MRenderer.getTextureManager.return_value=self.manager
        ns={'om':self.om,'omr':self.omr}
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(SOURCE),'exec'),ns)
        self.draw=ns['draw_image']
        self.data=types.SimpleNamespace(parsed_fields=[{'image_path':'missing-logo.png'}],font_color=types.SimpleNamespace(a=1.0))

    def test_missing_texture_reports_path_without_attribute_error(self):
        self.manager.acquireTexture.return_value=None
        self.draw(None,Mock(),Mock(),self.data,0,None,(100,20))
        self.assertIn('missing-logo.png',self.om.MGlobal.displayError.call_args.args[0])
        self.manager.releaseTexture.assert_not_called()

    def test_texture_released_when_draw_raises(self):
        texture=Mock()
        self.manager.acquireTexture.return_value=texture
        drawer=Mock()
        drawer.setTexture.side_effect=RuntimeError('draw failure')
        with self.assertRaises(RuntimeError):
            self.draw(None,drawer,Mock(),self.data,0,None,(100,20))
        self.manager.releaseTexture.assert_called_once_with(texture)

    def test_absent_texture_manager_is_safe(self):
        self.omr.MRenderer.getTextureManager.return_value=None
        self.draw(None,Mock(),Mock(),self.data,0,None,(100,20))
        self.manager.acquireTexture.assert_not_called()


if __name__=='__main__':
    unittest.main()
