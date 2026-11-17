"""Static checks that the toolbar registry, the installer and the tool sources agree.

Nothing here needs Maya or Qt: the registry and the tool modules are read with
``ast`` and the installer is read as text.  It catches the failures that only
show up on an artist's machine: a registry entry pointing at a function that
was renamed, a tool the installer forgot to copy, or a module that opens its
window as a side effect of being imported.
"""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "animation tool kit scripts"
INSTALLER = ROOT / "install_atk_toolbar.mel"
LOADER = ROOT / "atk_toolbar" / "atk_loader.py"

# Where each registry module lives in the source tree.  Packages point at the
# folder that the installer copies into the Maya scripts directory.
PACKAGE_ROOTS = {
    "tangent_tools": TOOLS / "tangent_tools" / "src",
    "time_bookmarks": TOOLS / "Bookmarks" / "src",
    "blue_pencil_flipbook": TOOLS / "Blue-Pencil-Flipbook-Manager",
    "atk_overlap": TOOLS / "Overlap",
    "studiolibrary": TOOLS / "studiolibrary-2.21.1" / "src",
}


def load_registry():
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "TOOL_REGISTRY" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("TOOL_REGISTRY not found in atk_loader.py")


def installer_paths():
    """Tool-relative file paths the installer copies (single files and icons).

    Paths written relative to the installer folder are made tool-relative;
    the optional ``icon/`` fallbacks (not shipped in the release ZIP) are
    left out.
    """
    text = INSTALLER.read_text(encoding="utf-8")
    prefix = TOOLS.name + "/"
    paths = set()
    for found in re.findall(r'"([\w\- .]+/[\w\- ./]+\.(?:py|png))"', text):
        if found.startswith("icon/"):
            continue
        paths.add(found[len(prefix):] if found.startswith(prefix) else found)
    return sorted(paths)


def module_source(module):
    """Return the source file for a registry module name."""
    parts = module.split(".")
    if parts[0] in PACKAGE_ROOTS:
        base = PACKAGE_ROOTS[parts[0]].joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        return base / "__init__.py"
    matches = [p for p in TOOLS.rglob(parts[0] + ".py") if "studiolibrary" not in p.parts]
    if not matches:
        raise AssertionError("No source file found for module '%s'" % module)
    return matches[0]


def defined_names(path):
    """Top-level names of a module, plus ``Class.method`` for its classes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        names.add("%s.%s" % (node.name, item.name))
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names, tree


def registry_functions(tool):
    names = [tool["launch_fn"]]
    names += [tool[key] for key in ("quick_fn", "startup_fn") if key in tool]
    names += [entry[1] for entry in tool.get("context_actions", []) if entry]
    names += [entry[2] for entry in tool.get("palette_colors", [])]
    return names


class RegistryIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_version_strings_agree(self):
        package = (ROOT / "atk_toolbar" / "__init__.py").read_text(encoding="utf-8")
        toolbar = (ROOT / "atk_toolbar" / "atk_toolbar.py").read_text(encoding="utf-8")
        version = re.search(r'__version__ = "([\d.]+)"', package).group(1)
        self.assertEqual(re.search(r'^VERSION\s*=\s*"([\d.]+)"', toolbar, re.M).group(1), version)
        self.assertTrue((ROOT / ("Animation_Tool_Kit_v%s_Release_Notes.md" % version)).is_file(),
                        "no release notes for %s" % version)

    def test_ids_are_unique_and_groups_known(self):
        ids = [tool["id"] for tool in self.registry]
        self.assertEqual(len(ids), len(set(ids)))
        for tool in self.registry:
            self.assertIn(tool["group"], ("timing", "viewport", "rigging", "pipeline"))

    def test_every_registry_function_exists_in_its_module(self):
        for tool in self.registry:
            if tool["id"] == "studio_library":
                continue  # third-party package: 'main' is re-exported, not defined
            names, _tree = defined_names(module_source(tool["module"]))
            for function in registry_functions(tool):
                self.assertIn(function, names, "%s: '%s' is not defined in %s" % (
                    tool["id"], function, tool["module"]))

    def test_importing_a_tool_does_not_open_its_window(self):
        launchers = {"show", "launch", "main", "run", "show_ui", "show_dialog", "start"}
        for tool in self.registry:
            if tool["id"] in ("studio_library", "tween_machine"):
                continue
            _names, tree = defined_names(module_source(tool["module"]))
            for node in tree.body:
                call = node.value if isinstance(node, ast.Expr) else None
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                    self.assertNotIn(call.func.id, launchers, (
                        "%s calls %s() at import time; the toolbar imports the "
                        "module and then launches it, so the window is built "
                        "twice" % (tool["module"], call.func.id)))

    def test_installer_only_copies_files_that_exist(self):
        paths = installer_paths()
        self.assertGreater(len(paths), 30)
        for relative in paths:
            self.assertTrue((TOOLS / relative).is_file(),
                            "installer copies a missing file: %s" % relative)

    def test_installer_copies_every_single_file_tool(self):
        copied = {Path(p).name for p in installer_paths()}
        for tool in self.registry:
            root = tool["module"].split(".")[0]
            if root in PACKAGE_ROOTS or tool["id"] == "playblast_creator":
                continue
            self.assertIn(root + ".py", copied,
                          "installer does not copy %s.py" % root)
            for extra in tool.get("extra_modules", []):
                if extra.split(".")[0] not in PACKAGE_ROOTS and "studio" not in extra \
                        and extra != "mutils":
                    self.assertIn(extra + ".py", copied,
                                  "installer does not copy %s.py" % extra)

    def test_package_tools_are_copied_by_the_installer(self):
        text = INSTALLER.read_text(encoding="utf-8")
        for name, base in PACKAGE_ROOTS.items():
            self.assertTrue((base / name).is_dir(), "missing package folder %s" % name)
            self.assertIn(name, text, "installer never mentions package %s" % name)


if __name__ == "__main__":
    unittest.main()
