"""A small in-memory stand-in for the parts of maya.cmds the ATK tests need.

``FakeScene`` holds anim curves as ``{curve: {time: value}}`` plus the plug
each curve drives, and answers the handful of ``keyframe`` / ``cutKey`` /
``snapKey`` calls the tools make.  ``load_tool`` imports a tool module with
this fake installed as ``maya.cmds``.
"""
import importlib.util
import sys
import types


class FakeScene(object):
    def __init__(self):
        self.curves = {}        # curve -> {time: value}
        self.plugs = {}         # curve -> "node.attr"
        self.types = {}         # curve -> node type
        self.locked = set()
        self.referenced = set()
        self.tangents = {}      # curve -> {"in": [...], "out": [...]} angles
        self.selection = []
        self.selected_keys = {}  # curve -> [times]
        self.current_time = 1.0
        self.playback = (1.0, 24.0)
        self.undo_depth = 0
        self.max_undo_depth = 0
        self.filtered = []
        self.warnings = []
        self.auto_key = False

    # -- scene building ---------------------------------------------------
    def add_curve(self, node, attr, keys, curve_type="animCurveTL"):
        curve = "%s_%s" % (node.split("|")[-1], attr)
        self.curves[curve] = dict(keys)
        self.plugs[curve] = "%s.%s" % (node, attr)
        self.types[curve] = curve_type
        return curve

    def curves_of(self, node):
        return [c for c in self.curves if self.plugs[c].split(".")[0] == node]

    def times(self, curve):
        return sorted(self.curves[curve])

    # -- maya.cmds --------------------------------------------------------
    def ls(self, *args, **kwargs):
        if kwargs.get("selection") or kwargs.get("sl"):
            return list(self.selection)
        if "type" in kwargs:
            wanted = kwargs["type"]
            wanted = (wanted,) if isinstance(wanted, str) else tuple(wanted)
            return [c for c in self.curves if self.types[c] in wanted]
        return list(args[0]) if args and isinstance(args[0], (list, tuple)) else list(args)

    def nodeType(self, node):
        return self.types.get(node, "transform")

    def objExists(self, node):
        return node in self.curves or node in self.selection

    def lockNode(self, node, **kwargs):
        return [node in self.locked]

    def referenceQuery(self, node, **kwargs):
        return node in self.referenced

    def listConnections(self, plug, **kwargs):
        curve = plug.split(".")[0]
        return [self.plugs[curve]] if curve in self.plugs else []

    def currentTime(self, *args, **kwargs):
        return self.current_time

    def playbackOptions(self, **kwargs):
        if kwargs.get("min") or kwargs.get("minTime"):
            return self.playback[0]
        return self.playback[1]

    def autoKeyframe(self, **kwargs):
        return self.auto_key

    def undoInfo(self, **kwargs):
        if kwargs.get("openChunk"):
            self.undo_depth += 1
            self.max_undo_depth = max(self.max_undo_depth, self.undo_depth)
        if kwargs.get("closeChunk"):
            self.undo_depth -= 1

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message)

    def inViewMessage(self, **kwargs):
        return None

    def _resolve(self, args):
        """Return the curves a keyframe-style command addresses."""
        if not args:
            return list(self.curves)
        target = args[0]
        if target in self.curves:
            return [target]
        return self.curves_of(target)

    def keyframe(self, *args, **kwargs):
        query = kwargs.get("query") or kwargs.get("q")
        selected = kwargs.get("selected") or kwargs.get("sl")
        curves = self._resolve(args)
        if query:
            if kwargs.get("name"):
                if selected:
                    return [c for c in curves if self.selected_keys.get(c)]
                attrs = kwargs.get("attribute")
                if attrs:
                    return [c for c in curves if self.plugs[c].split(".")[1] in attrs]
                return curves
            out = []
            for curve in curves:
                times = self.times(curve)
                if selected:
                    times = [t for t in times if t in self.selected_keys.get(curve, [])]
                if "time" in kwargs:
                    start, end = kwargs["time"]
                    times = [t for t in times if start <= t <= end]
                if kwargs.get("valueChange") or kwargs.get("vc"):
                    out.extend(self.curves[curve][t] for t in times)
                elif kwargs.get("indexValue") or kwargs.get("iv"):
                    all_times = self.times(curve)
                    out.extend(all_times.index(t) for t in times)
                elif kwargs.get("keyframeCount"):
                    out.append(len(times))
                else:
                    out.extend(times)
            if kwargs.get("keyframeCount"):
                return sum(out)
            return out
        # edit: relative time shift
        delta = kwargs.get("timeChange")
        for curve in curves:
            times = self.times(curve)
            if "index" in kwargs:
                moving = [times[i] for i, _ in kwargs["index"]]
            elif "time" in kwargs:
                start, end = kwargs["time"]
                moving = [t for t in times if start <= t <= end]
            else:
                moving = times
            values = {t: self.curves[curve].pop(t) for t in moving}
            for t, value in values.items():
                self.curves[curve][t + delta] = value
        return None

    def keyTangent(self, curve, **kwargs):
        count = len(self.curves[curve])
        angles = self.tangents.get(curve, {})
        side = "in" if kwargs.get("inAngle") else "out"
        return list(angles.get(side, [0.0] * count))

    def cutKey(self, curve, **kwargs):
        for start, end in kwargs.get("time", []):
            for t in [t for t in self.curves[curve] if start <= t <= end]:
                del self.curves[curve][t]

    def snapKey(self, curve, **kwargs):
        self.curves[curve] = {float(round(t)): v for t, v in self.curves[curve].items()}

    def filterCurve(self, curves):
        self.filtered.append(sorted(curves))

    def delete(self, node):
        if node in self.referenced:
            raise RuntimeError("referenced")
        self.curves.pop(node)

    def setAttr(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


def install(scene):
    """Put ``scene`` in sys.modules as maya.cmds; returns the previous modules."""
    names = ("maya", "maya.cmds", "maya.mel", "maya.OpenMayaUI")
    saved = {name: sys.modules.get(name) for name in names}
    maya = types.ModuleType("maya")
    mel = types.ModuleType("maya.mel")
    mel.eval = lambda *args, **kwargs: ""
    omui = types.ModuleType("maya.OpenMayaUI")
    omui.MQtUtil = types.SimpleNamespace(mainWindow=lambda: None,
                                         findControl=lambda *a: None)
    maya.cmds, maya.mel, maya.OpenMayaUI = scene, mel, omui
    sys.modules.update({"maya": maya, "maya.cmds": scene, "maya.mel": mel,
                        "maya.OpenMayaUI": omui})
    return saved


def restore(saved):
    for name, module in saved.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_tool(path, scene, name=None):
    """Import the tool at ``path`` against ``scene``; returns the module."""
    saved = install(scene)
    try:
        spec = importlib.util.spec_from_file_location(name or ("atk_test_" + path.stem), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        restore(saved)
