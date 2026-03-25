"""
SavePlus Maya Import Helpers

Provides safe access to Maya modules when running inside Maya, and
fallback stubs when running in a standard Python environment.
"""

import importlib
import importlib.util


def _module_available(module_name):
    return importlib.util.find_spec(module_name) is not None


class _MissingMayaModule:
    def __init__(self, module_name):
        self._module_name = module_name

    def __getattr__(self, item):
        raise RuntimeError(
            f"Maya module '{self._module_name}' is not available. "
            "Run SavePlus inside Autodesk Maya."
        )


if _module_available("maya"):
    cmds = importlib.import_module("maya.cmds")
    mel = importlib.import_module("maya.mel")
else:
    cmds = _MissingMayaModule("maya.cmds")
    mel = _MissingMayaModule("maya.mel")

if _module_available("maya.app.general.mayaMixin"):
    MayaQWidgetDockableMixin = importlib.import_module(
        "maya.app.general.mayaMixin"
    ).MayaQWidgetDockableMixin
else:
    class MayaQWidgetDockableMixin:
        pass


def get_open_maya_ui():
    if _module_available("maya.OpenMayaUI"):
        return importlib.import_module("maya.OpenMayaUI")
    return None
