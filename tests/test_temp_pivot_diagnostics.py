"""Temp Pivot failure reporting, checked against a tiny fake scene (no Maya).

Covers the reasons a control could not take a temp pivot without telling
the user: joints rejected as "not a transform", locked or driven channels,
existing constraints, component and rig-node selections, and rig name
clashes between characters with the same control names.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_maya  # noqa: E402

SCRIPT = (Path(__file__).resolve().parents[1] / "animation tool kit scripts"
          / "Temp_Pivot_Tool_1_0_5" / "temp_pivot_tool.py")

TRANSFORM_TYPES = {"transform", "joint", "ikHandle"}
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


class Scene(object):
    """Just enough of maya.cmds for the Temp Pivot checks."""

    def __init__(self):
        self.nodes = {}       # name -> {"type", "locked", "inputs", "attrs", "parent"}
        self.selection = []
        self.dialogs = []
        self.warnings = []
        self.deleted = []

    def add(self, name, node_type="transform", parent=None, **attrs):
        self.nodes[name] = {"type": node_type, "locked": set(), "inputs": {},
                            "attrs": dict(attrs), "parent": parent,
                            "matrix": list(IDENTITY)}
        return name

    # -- maya.cmds ---------------------------------------------------------
    def objExists(self, path):
        node, _, attr = path.partition(".")
        if node not in self.nodes:
            return False
        if not attr:
            return True
        base = attr.split("[")[0]
        return (base in ("tx", "ty", "tz", "rx", "ry", "rz", "t", "r",
                         "rotateOrder", "visibility")
                or base in self.nodes[node]["attrs"])

    def nodeType(self, node):
        return self.nodes[node.split(".")[0]]["type"]

    def objectType(self, node, isAType=None):
        node_type = self.nodes[node]["type"]
        if isAType == "transform":
            return node_type in TRANSFORM_TYPES
        if isAType == "shape":
            return node_type in ("mesh", "nurbsCurve", "locator")
        return node_type

    def ls(self, *args, **kwargs):
        if kwargs.get("selection") or kwargs.get("sl"):
            return list(self.selection)
        names = []
        for arg in args:
            names.extend(arg if isinstance(arg, (list, tuple)) else [arg])
        out = []
        for name in names:
            if kwargs.get("objectsOnly") and "." in name:
                name = name.split(".")[0]
            if "*" in name:
                import fnmatch
                out.extend(n for n in self.nodes if fnmatch.fnmatch(n, name))
            elif name in self.nodes:
                out.append(name)
        if "type" in kwargs:
            out = [n for n in out if self.nodes[n]["type"] in
                   ((kwargs["type"],) if isinstance(kwargs["type"], str) else kwargs["type"])
                   or (kwargs["type"] == "transform" and self.nodes[n]["type"] in TRANSFORM_TYPES)]
        return out

    def listRelatives(self, node, **kwargs):
        if kwargs.get("parent"):
            parent = self.nodes[node]["parent"]
            return [parent] if parent else []
        wanted = kwargs.get("type")
        return [n for n, d in self.nodes.items()
                if d["parent"] == node and (wanted is None or d["type"] == wanted)]

    def listConnections(self, target, **kwargs):
        node, _, attr = target.partition(".")
        if node not in self.nodes:
            return []
        if kwargs.get("destination", True) and not kwargs.get("source", True):
            # outputs: which nodes does this node drive?
            return [n for n, d in self.nodes.items()
                    if any(src == node for src in d["inputs"].values())]
        inputs = self.nodes[node]["inputs"]
        if attr in ("t", "r"):
            # Like Maya: a compound query also returns its children's inputs.
            sources = [v for k, v in inputs.items() if k == attr or (len(k) == 2 and k[0] == attr)]
        else:
            sources = [inputs[attr]] if attr in inputs else ([] if attr else list(inputs.values()))
        wanted = kwargs.get("type")
        if wanted:
            sources = [s for s in sources
                       if self.nodes[s]["type"] == wanted
                       or (wanted == "constraint" and self.nodes[s]["type"].endswith("Constraint"))]
        return sources

    def getAttr(self, path, **kwargs):
        node, _, attr = path.partition(".")
        if kwargs.get("lock"):
            return attr in self.nodes[node]["locked"]
        if kwargs.get("keyable"):
            return True
        return self.nodes[node]["attrs"].get(attr, 0)

    def attributeQuery(self, attr, node=None, exists=False):
        return attr in self.nodes.get(node, {"attrs": {}})["attrs"]

    def xform(self, node, **kwargs):
        if kwargs.get("q") and kwargs.get("m"):
            return list(self.nodes[node]["matrix"])
        if kwargs.get("q"):
            return [0.0, 0.0, 0.0]
        return None

    def connectionInfo(self, plug, **kwargs):
        node, _, attr = plug.partition(".")
        source = self.nodes[node]["inputs"].get(attr)
        if kwargs.get("isExactDestination"):
            return source is not None
        if kwargs.get("sourceFromDestination"):
            return f"{source}.output" if source else ""
        return None

    def setAttr(self, path, value, **kwargs):
        node, _, attr = path.partition(".")
        if node in self.nodes:
            self.nodes[node]["attrs"][attr] = value

    def about(self, **kwargs):
        return False

    def confirmDialog(self, **kwargs):
        self.dialogs.append(kwargs)
        return "OK"

    def warning(self, message):
        self.warnings.append(message)

    def select(self, *args, **kwargs):
        self.selection = list(args[0]) if args and isinstance(args[0], list) else list(args)

    def delete(self, node):
        self.deleted.append(node)
        self.nodes.pop(node, None)

    def undoInfo(self, **kwargs):
        return None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


def load(scene):
    return fake_maya.load_tool(SCRIPT, scene, name="atk_test_temp_pivot")


class DiagnoseControlTest(unittest.TestCase):
    def setUp(self):
        self.scene = Scene()
        self.tool = load(self.scene)
        self.tool.cmds = self.scene

    def test_clean_control_has_no_problems(self):
        self.scene.add("hand_ctrl")
        self.assertEqual(self.tool.diagnose_control("hand_ctrl"), [])

    def test_joint_controls_are_accepted(self):
        """Joints used to fail the nodeType == 'transform' check silently."""
        self.scene.add("fk_elbow_jnt", "joint")
        self.assertTrue(self.tool._is_transform("fk_elbow_jnt"))
        self.assertEqual(self.tool.diagnose_control("fk_elbow_jnt"), [])

    def test_non_transform_is_explained(self):
        self.scene.add("lambert2", "lambert")
        problems = self.tool.diagnose_control("lambert2")
        self.assertEqual(len(problems), 1)
        self.assertIn("lambert", problems[0])
        self.assertIn("not a transform", problems[0])

    def test_existing_constraint_is_reported(self):
        self.scene.add("hand_ctrl")
        self.scene.add("hand_ctrl_orientConstraint1", "orientConstraint", parent="hand_ctrl")
        self.scene.nodes["hand_ctrl"]["inputs"]["rx"] = "hand_ctrl_orientConstraint1"
        problems = self.tool.diagnose_control("hand_ctrl")
        self.assertTrue(any("hand_ctrl_orientConstraint1" in p for p in problems), problems)

    def test_child_constraint_driving_another_node_is_ignored(self):
        self.scene.add("hand_ctrl")
        self.scene.add("other_node")
        self.scene.add("parked_pointConstraint1", "pointConstraint", parent="hand_ctrl")
        self.scene.nodes["other_node"]["inputs"]["tx"] = "parked_pointConstraint1"
        self.assertEqual(self.tool.diagnose_control("hand_ctrl"), [])

    def test_fully_locked_control_is_reported(self):
        self.scene.add("hand_ctrl")
        self.scene.nodes["hand_ctrl"]["locked"].update(
            {"tx", "ty", "tz", "rx", "ry", "rz"})
        problems = self.tool.diagnose_control("hand_ctrl")
        self.assertTrue(any("None of the translate or rotate" in p for p in problems), problems)

    def test_partly_locked_control_is_allowed_with_skips(self):
        self.scene.add("hand_ctrl")
        self.scene.nodes["hand_ctrl"]["locked"].update({"tx", "ty", "tz"})
        self.assertEqual(self.tool.diagnose_control("hand_ctrl"), [])
        kwargs = self.tool._constraint_kwargs("hand_ctrl")
        self.assertEqual(kwargs, {"skipTranslate": ["x", "y", "z"]})

    def test_driven_channels_are_skipped_but_keys_are_fine(self):
        self.scene.add("hand_ctrl")
        self.scene.add("hand_ctrl_rotateX", "animCurveTA")
        self.scene.add("hand_expr", "expression")
        self.scene.add("hand_sdk", "animCurveUA")
        node = self.scene.nodes["hand_ctrl"]
        node["inputs"].update({"rx": "hand_ctrl_rotateX", "ry": "hand_expr", "rz": "hand_sdk"})
        report = self.tool.get_channel_report("hand_ctrl")
        self.assertEqual(report["skip_rotate"], ["y", "z"])
        self.assertTrue(any("expression" in p for p in report["problems"]))
        self.assertTrue(any("set driven key" in p for p in report["problems"]))

    def test_one_driven_axis_does_not_block_its_siblings(self):
        self.scene.add("hand_ctrl")
        self.scene.add("hand_expr", "expression")
        self.scene.nodes["hand_ctrl"]["inputs"]["tx"] = "hand_expr"
        report = self.tool.get_channel_report("hand_ctrl")
        self.assertEqual(report["skip_translate"], ["x"])
        self.assertEqual(report["skip_rotate"], [])

    def test_connected_compound_blocks_all_three_axes(self):
        self.scene.add("hand_ctrl")
        self.scene.add("hand_mult", "multiplyDivide")
        self.scene.nodes["hand_ctrl"]["inputs"]["r"] = "hand_mult"
        report = self.tool.get_channel_report("hand_ctrl")
        self.assertEqual(report["skip_rotate"], ["x", "y", "z"])

    def test_zero_scale_is_reported(self):
        self.scene.add("hand_ctrl")
        self.scene.nodes["hand_ctrl"]["matrix"] = [0, 0, 0, 0] + IDENTITY[4:]
        problems = self.tool.diagnose_control("hand_ctrl")
        self.assertTrue(any("scale of zero" in p for p in problems), problems)


class FailureReportTest(unittest.TestCase):
    def setUp(self):
        self.scene = Scene()
        self.tool = load(self.scene)
        self.tool.cmds = self.scene

    def test_create_pops_up_a_report_instead_of_failing_silently(self):
        self.scene.add("hand_ctrl")
        self.scene.add("hand_ctrl_parentConstraint1", "parentConstraint", parent="hand_ctrl")
        self.scene.nodes["hand_ctrl"]["inputs"]["tx"] = "hand_ctrl_parentConstraint1"
        ok, message, node = self.tool.create_pivot_locator("hand_ctrl")
        self.assertFalse(ok)
        self.assertIsNone(node)
        self.assertEqual(len(self.scene.dialogs), 1)
        self.assertIn("hand_ctrl_parentConstraint1", self.scene.dialogs[0]["message"])
        self.assertTrue(self.scene.warnings)

    def test_report_can_be_suppressed_for_scripts(self):
        self.scene.add("lambert2", "lambert")
        ok, message, _ = self.tool.create_pivot_locator("lambert2", report=False)
        self.assertFalse(ok)
        self.assertIn("not a transform", message)
        self.assertEqual(self.scene.dialogs, [])

    def test_unexpected_error_is_reported_and_cleaned_up(self):
        self.scene.add("hand_ctrl")

        def broken_null(name, color, size=1.0):
            self.scene.add(name)
            raise RuntimeError("simulated Maya failure")

        self.tool._create_visual_null = broken_null
        ok, message, _ = self.tool.create_pivot_locator("hand_ctrl")
        self.assertFalse(ok)
        self.assertIn("simulated Maya failure", message)
        self.assertEqual(len(self.scene.dialogs), 1)

    def test_failed_setup_leaves_the_pivot_pending(self):
        """A failure after setupComplete was set must not block a retry."""
        pivot = self.scene.add("hand_ctrl_TMP_pivot", setupComplete=True,
                               settingsNode="hand_ctrl_TMP_settings",
                               targetControl="hand_ctrl")
        self.scene.add("hand_ctrl_TMP_settings")
        self.tool._rollback_setup(pivot, [], list(IDENTITY), [0, 0, 0],
                                  ["hand_ctrl_TMP_settings"], "hand_ctrl")
        self.assertFalse(self.scene.nodes[pivot]["attrs"]["setupComplete"])
        self.assertEqual(self.scene.nodes[pivot]["attrs"]["settingsNode"], "")
        self.assertNotIn("hand_ctrl_TMP_settings", self.scene.nodes)
        self.assertEqual(self.tool.find_rig_context([pivot]), ("pending", pivot))

    def test_empty_selection_is_explained(self):
        self.scene.selection = []
        reasons = self.tool._explain_selection()
        self.assertIn("Nothing is selected", reasons[0])

    def test_material_selection_is_explained(self):
        self.scene.add("lambert2", "lambert")
        self.scene.selection = ["lambert2"]
        reasons = self.tool._explain_selection()
        self.assertTrue(any("lambert" in r for r in reasons), reasons)


class NamingTest(unittest.TestCase):
    def setUp(self):
        self.scene = Scene()
        self.tool = load(self.scene)
        self.tool.cmds = self.scene

    def test_prefix_is_unique_across_characters(self):
        """Two characters with the same control name used to share one prefix,
        so building the second rig deleted the first rig's constraint."""
        self.scene.add("A:hand_ctrl")
        self.scene.add("B:hand_ctrl")
        first = self.tool._unique_prefix("A:hand_ctrl")
        self.scene.add(first + self.tool.NULL_GRP_1_SUFFIX)
        second = self.tool._unique_prefix("B:hand_ctrl")
        self.assertNotEqual(first, second)

    def test_rig_nodes_are_recognised_by_suffix_only(self):
        """A control merely containing 'TMP' is not a rig node any more."""
        self.assertFalse(self.tool._is_rig_node("TMP_hand_ctrl"))
        self.assertTrue(self.tool._is_rig_node("hand_ctrl_TMP_pivot"))
        self.assertTrue(self.tool._is_rig_node("hand_ctrl_TMP_anchor1"))

    def test_list_rows_parse(self):
        pivot, control = self.tool._parse_list_entry(" [ON]   a_TMP_pivot  →  A:hand")
        self.assertEqual((pivot, control), ("a_TMP_pivot", "A:hand"))


if __name__ == "__main__":
    unittest.main()
