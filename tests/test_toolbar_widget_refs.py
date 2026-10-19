"""Static guard: the toolbar must not keep wrappers of Maya-owned widgets.

shiboken cannot tell when Maya deletes a widget it owns (workspace switches,
deleteUI), so a wrapInstance() result stored in a module global dangles and
calling into it later locks up / crashes Maya (the ATK 1.1.11 regression).
"""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "atk_toolbar" / "atk_toolbar.py"


def _is_wrap_call(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "wrapInstance")


def stored_widget_globals(tree):
    """Return (function, global) pairs where a wrapInstance result is stored."""
    hits = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        declared = {n for g in ast.walk(fn) if isinstance(g, ast.Global) for n in g.names}
        wrapped = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and _is_wrap_call(node.value):
                wrapped.update(t.id for t in node.targets if isinstance(t, ast.Name))
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign):
                continue
            value_is_widget = _is_wrap_call(node.value) or (
                isinstance(node.value, ast.Name) and node.value.id in wrapped)
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in declared and value_is_widget:
                    hits.append((fn.name, target.id))
    return hits


class ToolbarWidgetRefTests(unittest.TestCase):
    def test_no_maya_widget_wrapper_stored_in_globals(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(stored_widget_globals(tree), [])

    def test_guard_detects_the_1_1_11_pattern(self):
        bad = ast.parse(
            "def f():\n"
            "    global _target\n"
            "    w = wrapInstance(1, object)\n"
            "    _target = w\n")
        self.assertEqual(stored_widget_globals(bad), [("f", "_target")])


if __name__ == "__main__":
    unittest.main()
