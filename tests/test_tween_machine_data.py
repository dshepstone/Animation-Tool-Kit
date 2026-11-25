"""tweenMachine's scene data node is written as text Maya can store.

Under Python 3, ``ElementTree.tostring`` returns bytes by default, and Maya's
``setAttr(..., type="string")`` rejects them with "Error reading data element
number 1", so the Tween Machine button failed to open the window.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_maya  # noqa: E402

SCRIPT = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
          / "tweenMachine" / "python" / "tweenMachine.py")


class Scene(fake_maya.FakeScene):
    def __init__(self, nodes=None):
        super(Scene, self).__init__()
        self.nodes = dict(nodes or {})   # name -> {attr: value}
        self.set_calls = []

    def ls(self, *args, **kwargs):
        if args and isinstance(args[0], str):
            pattern = args[0]
            if pattern.endswith("*"):
                return [n for n in self.nodes if n.startswith(pattern[:-1])]
            return [n for n in self.nodes if n == pattern]
        return super(Scene, self).ls(*args, **kwargs)

    def about(self, **kwargs):
        return "2025"

    def optionVar(self, **kwargs):
        return False if "exists" in kwargs else None

    def createNode(self, node_type, name=None):
        self.nodes[name] = {}
        return name

    def addAttr(self, node, longName=None, **kwargs):
        self.nodes[node].setdefault(longName, "")

    def attributeQuery(self, attr, node=None, exists=False):
        return attr in self.nodes.get(node, {})

    def listRelatives(self, node, **kwargs):
        return None

    def getAttr(self, plug):
        node, attr = plug.split(".", 1)
        return self.nodes[node][attr]

    def setAttr(self, plug, value, **kwargs):
        if kwargs.get("type") == "string" and not isinstance(value, str):
            raise RuntimeError("setAttr: Error reading data element number 1: ")
        node, attr = plug.split(".", 1)
        if attr not in self.nodes[node]:
            raise RuntimeError("No object matches name: " + plug)
        self.nodes[node][attr] = value
        self.set_calls.append(plug)


class TweenMachineDataTest(unittest.TestCase):
    def _data(self, scene):
        saved = fake_maya.install(scene)
        try:
            module = fake_maya.load_tool(SCRIPT, scene, "atk_test_tweenMachine")
            return module.TMData()
        finally:
            fake_maya.restore(saved)

    def test_new_scene_writes_xml_text(self):
        scene = Scene()
        data = self._data(scene)
        stored = scene.nodes["tweenMachineData"]["data"]
        self.assertIsInstance(stored, str)
        self.assertTrue(stored.startswith("<tweenMachineData>"))
        self.assertEqual(data.node, "tweenMachineData")

    def test_existing_node_without_data_attr(self):
        scene = Scene({"tweenMachineData": {}})
        self._data(scene)
        self.assertIsInstance(scene.nodes["tweenMachineData"]["data"], str)

    def test_old_tmxml_node_is_read(self):
        xml = ('<tweenMachineData><buttons height="8" />'
               '<groups><group name="arms" index="0" /></groups>'
               '</tweenMachineData>')
        scene = Scene({"tmXML": {"data": xml}})
        data = self._data(scene)
        self.assertEqual([g.name for g in data.groups], ["arms"])
        self.assertIn('name="arms"', scene.nodes["tweenMachineData"]["data"])


if __name__ == "__main__":
    unittest.main()
