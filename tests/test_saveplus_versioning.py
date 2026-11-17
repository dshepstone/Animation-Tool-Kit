"""SavePlus version increments against a fake Maya file command (no Maya needed)."""
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest

TOOL_DIR = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
            / "SavePlus_2_0_5")


class FakeCmds(object):
    """Just enough of maya.cmds for save_plus_proc: file / workspace."""

    def __init__(self):
        self.scene = ""

    def file(self, *args, **kwargs):
        if kwargs.get("query"):
            return self.scene
        if "rename" in kwargs:
            self.scene = kwargs["rename"]
            return self.scene
        if kwargs.get("save"):
            Path(self.scene).write_text("// fake scene\n")
            return self.scene
        return None

    def workspace(self, *args, **kwargs):
        return ""

    def __getattr__(self, name):
        return lambda *a, **k: None


def _load_core(fake):
    maya_shim = types.ModuleType("savePlus_maya")
    maya_shim.cmds = fake
    maya_shim.mel = None
    saved = {name: sys.modules.get(name) for name in ("savePlus_maya", "savePlus_core")}
    sys.modules["savePlus_maya"] = maya_shim
    sys.modules.pop("savePlus_core", None)
    sys.path.insert(0, str(TOOL_DIR))
    try:
        return importlib.import_module("savePlus_core")
    finally:
        sys.path.remove(str(TOOL_DIR))
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class SavePlusVersioningTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeCmds()
        self.core = _load_core(self.fake)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _save_next(self, name):
        path = Path(self.tmp.name) / name
        path.write_text("// fake scene\n")
        self.fake.scene = str(path).replace("\\", "/")
        ok, message, new_path = self.core.save_plus_proc(self.fake.scene)
        self.assertTrue(ok, message)
        return Path(new_path).name

    def test_simple_trailing_number(self):
        self.assertEqual(self._save_next("myScene_v001.ma"), "myScene_v002.ma")

    def test_no_number_appends_02(self):
        self.assertEqual(self._save_next("myScene.ma"), "myScene02.ma")

    def test_name_with_two_numbers_keeps_its_start(self):
        # Used to be saved as "_anim_v004.ma" (everything before the last
        # non-digit run was dropped).
        self.assertEqual(self._save_next("shot010_anim_v003.ma"), "shot010_anim_v004.ma")
        self.assertEqual(self._save_next("sc01_sh02_v09.mb"), "sc01_sh02_v10.mb")

    def test_rollover_keeps_padding_with_project_prefix(self):
        # Used to become "A01_anim_v0010.ma" (099 was read as 09 + 9).
        self.assertEqual(self._save_next("A01_anim_v009.ma"), "A01_anim_v010.ma")
        self.assertEqual(self._save_next("A01_shot_099.ma"), "A01_shot_100.ma")

    def test_assignment_pattern(self):
        self.assertEqual(self._save_next("Smith_John_blocking_01.ma"),
                         "Smith_John_blocking_02.ma")
        self.assertEqual(self._save_next("A03_Smith_John_wip_122.ma"),
                         "A03_Smith_John_wip_123.ma")

    def test_existing_next_version_is_skipped(self):
        (Path(self.tmp.name) / "shot010_anim_v004.ma").write_text("taken\n")
        self.assertEqual(self._save_next("shot010_anim_v003.ma"), "shot010_anim_v005.ma")

    def test_every_press_versions_up(self):
        """Save Plus is pressed over and over: each press must make the next file."""
        cases = {
            "myScene.ma": ["myScene02.ma", "myScene03.ma", "myScene04.ma"],
            "myScene_v001.ma": ["myScene_v002.ma", "myScene_v003.ma", "myScene_v004.ma"],
            "shot010_anim_v008.ma": ["shot010_anim_v009.ma", "shot010_anim_v010.ma",
                                     "shot010_anim_v011.ma"],
            "A01_anim_v098.ma": ["A01_anim_v099.ma", "A01_anim_v100.ma", "A01_anim_v101.ma"],
            "Smith_John_blocking_09.ma": ["Smith_John_blocking_10.ma",
                                          "Smith_John_blocking_11.ma",
                                          "Smith_John_blocking_12.ma"],
            "sc01_sh02.mb": ["sc01_sh03.mb", "sc01_sh04.mb", "sc01_sh05.mb"],
        }
        for start, expected in cases.items():
            path = Path(self.tmp.name) / start
            path.write_text("// fake scene\n")
            self.fake.scene = str(path).replace("\\", "/")
            saved = []
            for _press in expected:
                # Exactly what the button and the quick-save shelf button do:
                # hand the current scene to save_plus_proc.
                ok, message, new_path = self.core.save_plus_proc(self.fake.scene)
                self.assertTrue(ok, message)
                self.assertEqual(self.fake.scene, new_path)   # Maya now has the new file open
                self.assertTrue(Path(new_path).is_file())      # and it was written
                saved.append(Path(new_path).name)
            self.assertEqual(saved, expected, start)
            self.assertTrue(path.is_file(), "the original file must be left in place")

    def test_compute_next_version_path(self):
        nxt = self.core.compute_next_version_path("/p/A03_Smith_John_blocking_wip_122.ma")
        self.assertTrue(nxt.endswith("A03_Smith_John_blocking_wip_123.ma"))


if __name__ == "__main__":
    unittest.main()
