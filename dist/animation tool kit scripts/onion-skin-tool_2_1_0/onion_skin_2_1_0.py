"""
Onion Skin v2.1.0 for Maya 2020+

A modern Python rewrite of the classic OnionSkin MEL tool by Syed Ali Ahsan (2007).
v2.1.0 adds keyframe-aware multi-plane ghosting: select an object, and the tool
finds its keyframes to capture 1-5 key-images before and after the current position.
Up to 10 stacked image planes, each with individual alpha control.

Original MEL script (v0.8.3):
    Author:  Syed Ali Ahsan  <yoda@cyber.net.pk>  (7 Feb 2007)
    Thanks to Mark Behm, Melt van der Spuy, Vincent Florio, Keith Lango,
    Herman Gonzalas, and Lord Ryan Santos.

Python adaptation (v2.1.0, 2026):  Rewritten for modern Maya.

Usage:
    import onion_skin_2_1_0
    onion_skin_2_1_0.launch()
"""

from __future__ import annotations
import os, glob
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtWidgets, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui
    from shiboken2 import wrapInstance

__version__ = "2.1.0"
_WIN = "onionSkinWorkspaceCtrl"
TEMP_PREFIX = "OnionSkinTemp"
TEMP_FOLDER = "onion_skin_temp"
MAX_LAYERS = 10

# Chroma-key: playblast against this color, then key it to transparent.
# Bright green chosen to contrast with most scene content.
CHROMA_COLOR = (0, 177, 64)      # RGB 0-255
CHROMA_TOLERANCE = 32            # per-channel distance

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_active_model_panel():
    p = cmds.getPanel(withFocus=True) or ""
    if cmds.getPanel(typeOf=p) == "modelPanel":
        return p
    for p in cmds.getPanel(visiblePanels=True) or []:
        if cmds.getPanel(typeOf=p) == "modelPanel":
            return p
    return None


def get_time_slider_range():
    s = mel.eval("$__tmp = $gPlayBackSlider")
    r = cmds.timeControl(s, query=True, rangeArray=True)
    return float(r[0]), float(r[1])


def _get_temp_dir():
    ws = cmds.workspace(query=True, fullName=True)
    rule = cmds.workspace(fileRuleEntry="images") or "images"
    d = os.path.join(ws, rule, TEMP_FOLDER).replace("\\", "/")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def _clean_temp_files():
    try:
        d = _get_temp_dir()
        for f in glob.glob(d + f"/{TEMP_PREFIX}*"):
            try:
                os.remove(f)
            except OSError:
                pass
    except Exception:
        pass


def _chroma_key_image(img_path, bg_rgb=CHROMA_COLOR, tol=CHROMA_TOLERANCE):
    """Replace pixels matching *bg_rgb* (within *tol*) with transparency.

    Uses numpy for speed if available, otherwise falls back to QImage
    pixel-by-pixel.  Saves the result as a 32-bit PNG beside the original
    and returns the new path.
    """
    QImage = QtGui.QImage
    QColor = QtGui.QColor

    img = QImage(img_path)
    if img.isNull():
        return img_path

    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    br, bg, bb = bg_rgb

    out_path = os.path.splitext(img_path)[0] + "_alpha.png"

    if _HAS_NUMPY:
        # ---- fast numpy path ------------------------------------------------
        ptr = img.bits()
        # PySide2 returns VoidPtr that needs setsize; PySide6 returns memoryview
        if hasattr(ptr, "setsize"):
            ptr.setsize(h * img.bytesPerLine())
        arr = np.frombuffer(ptr, dtype=np.uint8).copy()
        bpl = img.bytesPerLine()
        arr = arr.reshape(h, bpl)[:, :w * 4].reshape(h, w, 4)
        # Qt ARGB32 byte order is BGRA on little-endian
        b_ch = arr[:, :, 0].astype(np.int16)
        g_ch = arr[:, :, 1].astype(np.int16)
        r_ch = arr[:, :, 2].astype(np.int16)
        mask = ((np.abs(r_ch - br) < tol) &
                (np.abs(g_ch - bg) < tol) &
                (np.abs(b_ch - bb) < tol))
        arr[:, :, 3][mask] = 0  # set alpha to 0 for background pixels
        out_img = QImage(arr.data, w, h, w * 4, QImage.Format_ARGB32).copy()
        out_img.save(out_path, "PNG")
    else:
        # ---- slow fallback ---------------------------------------------------
        transparent = QColor(0, 0, 0, 0)
        for y in range(h):
            for x in range(w):
                c = img.pixelColor(x, y)
                if (abs(c.red() - br) < tol and
                        abs(c.green() - bg) < tol and
                        abs(c.blue() - bb) < tol):
                    img.setPixelColor(x, y, transparent)
        img.save(out_path, "PNG")

    return out_path


def _set_viewport_bg():
    """Set Maya viewport background to the chroma-key color.
    Returns a dict of original settings to pass to _restore_viewport_bg."""
    orig = {
        "bg": cmds.displayRGBColor("background", query=True),
        "bgTop": cmds.displayRGBColor("backgroundTop", query=True),
        "bgBot": cmds.displayRGBColor("backgroundBottom", query=True),
        "grad": cmds.displayPref(query=True, displayGradient=True),
    }
    r, g, b = CHROMA_COLOR[0] / 255.0, CHROMA_COLOR[1] / 255.0, CHROMA_COLOR[2] / 255.0
    cmds.displayPref(displayGradient=False)
    cmds.displayRGBColor("background", r, g, b)
    cmds.displayRGBColor("backgroundTop", r, g, b)
    cmds.displayRGBColor("backgroundBottom", r, g, b)
    return orig


def _restore_viewport_bg(orig):
    """Restore viewport background from dict returned by _set_viewport_bg."""
    if not orig:
        return
    cmds.displayRGBColor("background", *orig["bg"])
    cmds.displayRGBColor("backgroundTop", *orig["bgTop"])
    cmds.displayRGBColor("backgroundBottom", *orig["bgBot"])
    cmds.displayPref(displayGradient=orig["grad"])


def get_all_keyframe_times(obj, include_hierarchy=False):
    """Return a sorted list of unique keyframe times for *obj*.
    If *include_hierarchy* is True, also collect keys from all descendants."""
    nodes = [obj]
    if include_hierarchy:
        descendants = cmds.listRelatives(obj, allDescendents=True,
                                         fullPath=True) or []
        nodes.extend(descendants)

    all_times = set()
    for node in nodes:
        times = cmds.keyframe(node, query=True, timeChange=True) or []
        all_times.update(times)

    return sorted(all_times)


# ---------------------------------------------------------------------------
# OnionLayer -- one image plane in the stack
# ---------------------------------------------------------------------------
class OnionLayer:
    """Represents a single onion-skin image plane."""

    BEFORE = "before"
    CURRENT = "current"
    AFTER = "after"

    def __init__(self, frame, role, xform, shape, img_path, key_index=None):
        self.frame = frame
        self.role = role
        self.xform = xform        # Maya transform node name (never renamed)
        self.shape = shape         # Maya imagePlane shape name (never renamed)
        self.img_path = img_path
        self.key_index = key_index

    def exists(self):
        if self.xform and self.shape:
            return cmds.objExists(self.xform) and cmds.objExists(self.shape)
        return False

    def get_alpha(self):
        if self.exists():
            return cmds.getAttr(f"{self.shape}.alphaGain")
        return 0.0

    def set_alpha(self, val):
        if self.exists():
            cmds.setAttr(f"{self.shape}.alphaGain", max(0.0, min(1.0, val)))

    def get_visible(self):
        if self.exists():
            return cmds.getAttr(f"{self.xform}.visibility")
        return False

    def set_visible(self, vis):
        if self.exists():
            cmds.setAttr(f"{self.xform}.visibility", int(bool(vis)))
            # Mark node dirty so viewport re-evaluates
            cmds.dgdirty(self.xform)

    def delete(self):
        if self.exists():
            cmds.delete(self.xform)
        self.xform = None
        self.shape = None

    def label(self):
        tag = {self.BEFORE: "before", self.CURRENT: "current",
               self.AFTER: "after"}.get(self.role, "")
        return f"Frame {int(self.frame)}  ({tag})"


# ---------------------------------------------------------------------------
# Core engine -- manages keyframe queries and multiple layers
# ---------------------------------------------------------------------------
class OnionSkinCore:

    def __init__(self):
        self.model_panel = None
        self.target_object = None      # the object whose keys we read
        self.include_hierarchy = True   # also scan child keys
        self.isolate_rig = False        # isolate the rig during capture
        self.layers = []               # list[OnionLayer]
        self.outline_mode = False
        self._viewport_state = {}
        self._cached_keys = []         # sorted keyframe times
        self._rig_top_node = None      # cached top node of the rig

    # -- Viewport ----------------------------------------------------------

    def select_viewport(self):
        p = get_active_model_panel()
        if p is None:
            cmds.confirmDialog(title="Onion Skin",
                               message="Click inside a 3-D viewport first.",
                               button=["OK"])
            return None
        self.model_panel = p
        return p

    def camera_for_panel(self):
        if not self.model_panel:
            return ""
        return cmds.modelPanel(self.model_panel, query=True, camera=True)

    # -- Object and keyframe scanning --------------------------------------

    def set_target_from_selection(self):
        """Grab the first selected object and scan its keyframes.
        Also walks up the DAG to find the rig's top node.
        Returns (object_name, key_count, rig_top_node) or (None, 0, None)."""
        sel = cmds.ls(selection=True, long=False) or []
        if not sel:
            cmds.confirmDialog(title="Onion Skin",
                               message="Select an object with keyframes first.",
                               button=["OK"])
            return None, 0, None
        self.target_object = sel[0]
        self._cached_keys = get_all_keyframe_times(
            self.target_object, self.include_hierarchy)
        top = self.find_rig_top_node()
        return self.target_object, len(self._cached_keys), top

    def rescan_keys(self):
        """Re-query keyframes on the current target object."""
        if not self.target_object:
            return 0
        if not cmds.objExists(self.target_object):
            self.target_object = None
            self._cached_keys = []
            return 0
        self._cached_keys = get_all_keyframe_times(
            self.target_object, self.include_hierarchy)
        return len(self._cached_keys)

    def get_keys_around_current(self, before_count, after_count,
                                include_current=False):
        """Find keyframe times around the current time.

        Returns a list of (frame, role) tuples:
          - up to *before_count* keys before current time
          - the current time IF *include_current* is True
            (regardless of whether it sits on a key)
          - up to *after_count* keys after current time
        Before/after frames are always actual keyframe times.
        """
        if not self._cached_keys:
            return []

        cur = cmds.currentTime(query=True)
        keys = self._cached_keys

        keys_before = [k for k in keys if k < cur]
        keys_after  = [k for k in keys if k > cur]
        on_key = any(abs(k - cur) < 0.001 for k in keys)

        # Take the N closest keys before (nearest to cur last, so slice end)
        chosen_before = keys_before[-before_count:] if before_count else []
        # Take the N closest keys after (nearest to cur first, so slice start)
        chosen_after = keys_after[:after_count] if after_count else []

        result = []
        for k in chosen_before:
            result.append((k, OnionLayer.BEFORE))
        # Include current frame if checkbox is on, or if it's on a key
        if include_current or on_key:
            result.append((cur, OnionLayer.CURRENT))
        for k in chosen_after:
            result.append((k, OnionLayer.AFTER))

        return result

    # -- Ghost creation ----------------------------------------------------

    def create_ghost_from_keys(self, before_count, after_count,
                               include_current=False):
        """Main entry: ghost N keys before + current + N keys after."""
        if not self.model_panel:
            cmds.warning("No viewport selected.")
            return "No viewport selected."
        if not self.target_object:
            cmds.warning("No target object set.")
            return "No target object. Select one first."

        self.rescan_keys()
        if not self._cached_keys:
            return f"No keyframes found on '{self.target_object}'."

        frames_and_roles = self.get_keys_around_current(
            before_count, after_count, include_current)
        if not frames_and_roles:
            return "No frames to capture."

        self._capture_layers(frames_and_roles)
        return None

    def create_single_frame(self):
        """Capture just the current frame (no keyframe lookup needed)."""
        if not self.model_panel:
            cmds.warning("No viewport selected.")
            return
        cur = cmds.currentTime(query=True)
        self._capture_layers([(cur, OnionLayer.CURRENT)])

    # -- Layer management --------------------------------------------------

    def delete_all(self):
        for layer in self.layers:
            layer.delete()
        self.layers.clear()
        _clean_temp_files()

    def delete_layer(self, index):
        if 0 <= index < len(self.layers):
            self.layers[index].delete()
            self.layers.pop(index)

    def refresh_all(self):
        """Re-capture all layers at their stored frames."""
        if not self.model_panel:
            return
        old_info = [(ly.frame, ly.role) for ly in self.layers]
        self.delete_all()
        if old_info:
            self._capture_layers(old_info)

    def set_all_visible(self, vis):
        for ly in self.layers:
            ly.set_visible(vis)

    def has_layers(self):
        self.layers = [ly for ly in self.layers if ly.exists()]
        return len(self.layers) > 0

    def toggle_fit_all(self):
        for ly in self.layers:
            if ly.exists():
                cur = cmds.getAttr(f"{ly.shape}.fit")
                cmds.setAttr(f"{ly.shape}.fit", 0 if cur == 1 else 1)

    # -- Frame nav ---------------------------------------------------------

    @staticmethod
    def step_forward():
        mel.eval("playButtonStepForward")

    @staticmethod
    def step_back():
        mel.eval("playButtonStepBackward")

    @staticmethod
    def next_key():
        cmds.currentTime(
            cmds.findKeyframe(timeSlider=True, which="next"), edit=True)

    @staticmethod
    def prev_key():
        cmds.currentTime(
            cmds.findKeyframe(timeSlider=True, which="previous"), edit=True)

    # -- Internal capture --------------------------------------------------

    def _capture_layers(self, frames_and_roles):
        """Delete existing layers, then capture new ones."""
        self.delete_all()

        if len(frames_and_roles) > MAX_LAYERS:
            frames_and_roles = frames_and_roles[:MAX_LAYERS]

        sel = cmds.ls(selection=True, flatten=True) or []
        orig_fmt = cmds.getAttr("defaultRenderGlobals.imageFormat")
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)  # PNG

        # Set green-screen background for chroma keying
        orig_bg = _set_viewport_bg()

        # Isolate rig if enabled
        did_isolate = False
        if self.isolate_rig and self._rig_top_node:
            did_isolate = self._enable_isolate()

        for idx, (frame, role) in enumerate(frames_and_roles):
            layer = self._snapshot_one(frame, role, idx)
            if layer:
                self.layers.append(layer)

        # Un-isolate before restoring anything else
        if did_isolate:
            self._disable_isolate()

        # Restore original background and image format
        _restore_viewport_bg(orig_bg)
        cmds.setAttr("defaultRenderGlobals.imageFormat", orig_fmt)

        # CRITICAL: Re-show all layers — they were hidden during capture
        for ly in self.layers:
            if ly.exists():
                ly.set_visible(True)

        # Restore time to the current-frame layer
        for ly in self.layers:
            if ly.role == OnionLayer.CURRENT:
                cmds.currentTime(ly.frame, edit=True)
                break

        if sel:
            cmds.select(sel, replace=True)

        if self.model_panel:
            cmds.modelEditor(self.model_panel, edit=True, imagePlane=True)
            mel.eval("refresh -f")

    def _snapshot_one(self, frame, role, stack_index):
        """Capture a single frame into a new image plane."""
        if not self.model_panel:
            return None

        cmds.setFocus(self.model_panel)

        if self.outline_mode:
            sel_for_toon = cmds.ls(selection=True, flatten=True) or []
            if not self._setup_toon(sel_for_toon):
                return None

        # Hide ALL existing onion layers during capture
        for ly in self.layers:
            if ly.exists():
                ly.set_visible(False)

        # Store selection, then clear it to remove selection highlighting
        sel = cmds.ls(selection=True, flatten=True) or []
        cmds.select(clear=True)

        # Move to the target frame so the scene poses correctly
        cmds.currentTime(frame, edit=True)

        # Store viewport display state, then hide everything except geo
        vp_state = self._query_viewport_display()
        sel_hilite = cmds.modelEditor(
            self.model_panel, query=True, selectionHiliteDisplay=True)

        cmds.modelEditor(self.model_panel, edit=True,
                         selectionHiliteDisplay=False,
                         nurbsCurves=False,
                         nurbsSurfaces=False,
                         controlVertices=False,
                         hulls=False,
                         grid=False,
                         hud=False,
                         manipulators=False,
                         locators=False,
                         joints=False,
                         ikHandles=False,
                         deformers=False,
                         dynamics=False,
                         fluids=False,
                         hairSystems=False,
                         follicles=False,
                         pivots=False,
                         handles=False,
                         dimensions=False,
                         strokes=False,
                         imagePlane=False)

        # Playblast as PNG against the green-screen background
        temp_dir = _get_temp_dir()
        out_base = f"{temp_dir}/{TEMP_PREFIX}_f{int(frame)}"
        cmds.playblast(
            format="image", compression="png",
            startTime=frame, endTime=frame,
            forceOverwrite=True, clearCache=True,
            filename=out_base, viewer=False,
            showOrnaments=False, percent=100,
            widthHeight=[960, 540])

        # Restore viewport display state
        self._restore_viewport_display(vp_state)
        cmds.modelEditor(self.model_panel, edit=True,
                         selectionHiliteDisplay=sel_hilite)

        # Restore selection
        if sel:
            cmds.select(sel, replace=True)

        # Find the raw playblast image
        img_file = self._find_image(temp_dir, frame, out_base)
        if img_file is None:
            cmds.warning(f"[OnionSkin] No image for frame {frame}")
            self._cleanup_toon()
            return None

        # Chroma-key: replace green background with transparency
        img_file = _chroma_key_image(img_file)
        print(f"[OnionSkin] Keyed image: {img_file}")

        # Create image plane
        xform, shape = self._create_plane()
        if not xform or not shape:
            cmds.warning("[OnionSkin] Failed to create plane.")
            self._cleanup_toon()
            return None

        # Configure
        cmds.setAttr(f"{shape}.imageName", img_file, type="string")
        cmds.setAttr(f"{shape}.useFrameExtension", 0)

        alpha = self._default_alpha(role, stack_index)
        cmds.setAttr(f"{shape}.alphaGain", alpha)

        depth = 1000 + stack_index
        cmds.setAttr(f"{shape}.depth", depth)
        cmds.setAttr(f"{xform}.visibility", 1)

        self._cleanup_toon()

        layer = OnionLayer(frame, role, xform, shape, img_file,
                           key_index=stack_index)
        print(f"[OnionSkin] Layer {stack_index}: frame={int(frame)}, "
              f"role={role}, alpha={alpha:.2f}, depth={depth}, "
              f"xform='{xform}', shape='{shape}'")
        return layer

    def _default_alpha(self, role, index):
        if role == OnionLayer.CURRENT:
            return 0.6
        return max(0.15, 0.50 - index * 0.07)

    def _find_image(self, temp_dir, frame, out_base):
        padded = str(int(frame)).zfill(4)
        for ext in ("png", "jpg", "jpeg"):
            candidate = f"{out_base}.{padded}.{ext}"
            if os.path.isfile(candidate):
                return candidate.replace("\\", "/")
        m = glob.glob(f"{out_base}*{padded}*")
        if m:
            return m[0].replace("\\", "/")
        m = sorted(glob.glob(f"{out_base}*"),
                   key=os.path.getmtime, reverse=True)
        if m:
            return m[0].replace("\\", "/")
        return None

    def _create_plane(self):
        """Create an image plane via MEL.
        NEVER renames nodes -- stores Maya's auto-generated names."""
        cam = cmds.modelPanel(self.model_panel, query=True, camera=True)
        cam_shapes = cmds.listRelatives(
            cam, shapes=True, type="camera") or []
        if not cam_shapes:
            return None, None
        cam_shape = cam_shapes[0]

        before = set(cmds.ls(type="imagePlane") or [])
        mel.eval(f'imagePlane -camera {cam_shape}')
        after = set(cmds.ls(type="imagePlane") or [])
        new_shapes = after - before

        if not new_shapes:
            cmds.warning("[OnionSkin] imagePlane not created.")
            return None, None

        shape = list(new_shapes)[0]
        parents = cmds.listRelatives(shape, parent=True) or []
        xform = parents[0] if parents else None

        cmds.setAttr(f"{shape}.depth", 1000)
        cmds.setAttr(f"{shape}.alphaGain", 0.5)
        cmds.setAttr(f"{shape}.useFrameExtension", 0)
        cmds.modelEditor(self.model_panel, edit=True, imagePlane=True)

        return xform, shape

    # -- Toon / Outline ----------------------------------------------------

    def _setup_toon(self, selection):
        if not selection:
            cmds.warning("Outline mode requires a mesh selection.")
            return False
        self._cleanup_toon()
        cmds.modelEditor(self.model_panel, edit=True, strokes=True)
        self._store_viewport_state()
        for obj in selection:
            nt = cmds.nodeType(obj)
            shape = obj
            if nt == "transform":
                ss = cmds.listRelatives(obj, shapes=True) or []
                if not ss:
                    continue
                shape = ss[0]
                nt = cmds.nodeType(shape)
            if nt == "nurbsCurve":
                continue
            if nt not in ("mesh", "nurbsSurface"):
                continue
            toon = cmds.createNode("pfxToon")
            ts = (cmds.listRelatives(toon, shapes=True) or [None])[0]
            if not ts:
                continue
            cmds.connectAttr(
                f"{shape}.worldMatrix[0]",
                f"{ts}.inputSurface[0].inputWorldMatrix")
            if nt == "mesh":
                cmds.connectAttr(
                    f"{obj}.outMesh", f"{ts}.inputSurface[0].surface")
            elif nt == "nurbsSurface":
                tess = cmds.createNode("nurbsTessellate")
                cmds.setAttr(f"{tess}.caching", True)
                cmds.connectAttr(f"{obj}.local", f"{tess}.inputSurface")
                cmds.connectAttr(
                    f"{tess}.outputPolygon",
                    f"{toon}.inputSurface[0].surface")
            cmds.setAttr(f"{toon}.borderLines", 1)
            cmds.setAttr(f"{toon}.displayPercent", 0.05)
            cmds.setAttr(f"{toon}.drawAsMesh", 0)
            cmds.setAttr(f"{toon}.creaseLines", 0)
        self._hide_all_viewport_types()
        return True

    def _store_viewport_state(self):
        p = self.model_panel
        flags = [
            "nurbsCurves", "nurbsSurfaces", "polymeshes", "subdivSurfaces",
            "planes", "lights", "joints", "ikHandles", "deformers",
            "dynamics", "fluids", "hairSystems", "follicles", "locators",
            "dimensions", "pivots", "handles", "textures"]
        self._viewport_state = {
            f: cmds.modelEditor(p, query=True, **{f: True}) for f in flags}

    def _hide_all_viewport_types(self):
        for f in self._viewport_state:
            cmds.modelEditor(self.model_panel, edit=True, **{f: False})

    def _restore_viewport_state(self):
        for f, v in self._viewport_state.items():
            cmds.modelEditor(self.model_panel, edit=True, **{f: v})

    # -- Viewport display snapshot for clean playblast ---------------------

    _DISPLAY_FLAGS = [
        "nurbsCurves", "nurbsSurfaces", "controlVertices", "hulls",
        "polymeshes", "subdivSurfaces", "planes", "lights", "cameras",
        "imagePlane", "joints", "ikHandles", "deformers", "dynamics",
        "fluids", "hairSystems", "follicles", "locators", "dimensions",
        "pivots", "handles", "textures", "strokes", "manipulators",
        "grid", "hud",
    ]

    def _query_viewport_display(self):
        """Snapshot all modelEditor display flags."""
        p = self.model_panel
        state = {}
        for f in self._DISPLAY_FLAGS:
            try:
                state[f] = cmds.modelEditor(p, query=True, **{f: True})
            except Exception:
                pass
        return state

    def _restore_viewport_display(self, state):
        """Restore modelEditor display flags from a snapshot dict."""
        for f, v in state.items():
            try:
                cmds.modelEditor(self.model_panel, edit=True, **{f: v})
            except Exception:
                pass

    # -- Rig isolation -----------------------------------------------------

    def find_rig_top_node(self):
        """Walk up the DAG from target_object to find the top group node.
        Returns the topmost transform (the rig root)."""
        if not self.target_object:
            return None
        if not cmds.objExists(self.target_object):
            return None

        node = self.target_object
        while True:
            parents = cmds.listRelatives(node, parent=True,
                                         fullPath=False) or []
            if not parents:
                break
            # Stop if we hit the world (no parent) or a non-transform
            parent = parents[0]
            if cmds.nodeType(parent) != "transform":
                break
            node = parent

        self._rig_top_node = node
        return node

    def get_rig_hierarchy(self):
        """Return the full list of DAG nodes under the rig top node."""
        if not self._rig_top_node:
            return []
        if not cmds.objExists(self._rig_top_node):
            return []
        descendants = cmds.listRelatives(
            self._rig_top_node, allDescendents=True,
            fullPath=True) or []
        return [self._rig_top_node] + descendants

    def _enable_isolate(self):
        """Isolate the rig hierarchy in the viewport."""
        if not self.model_panel or not self._rig_top_node:
            return False

        rig_nodes = self.get_rig_hierarchy()
        if not rig_nodes:
            return False

        # Turn on isolate-select mode on this panel
        panel = self.model_panel
        cmds.isolateSelect(panel, state=True)

        # Clear any existing isolate set, then add our rig
        cmds.isolateSelect(panel, removeSelected=True)
        cmds.select(rig_nodes, replace=True)
        cmds.isolateSelect(panel, addSelected=True)
        cmds.select(clear=True)

        mel.eval("refresh -f")
        return True

    def _disable_isolate(self):
        """Remove viewport isolation so the full scene is visible."""
        if not self.model_panel:
            return
        cmds.isolateSelect(self.model_panel, state=False)
        mel.eval("refresh -f")

    def _cleanup_toon(self):
        t = cmds.ls("pfxToon*") or []
        if t:
            cmds.delete(t)
            if self._viewport_state:
                self._restore_viewport_state()


# ---------------------------------------------------------------------------
# Custom layer-list item widget
# ---------------------------------------------------------------------------
class LayerItemWidget(QtWidgets.QWidget):

    alpha_changed = QtCore.Signal(int, float)
    delete_clicked = QtCore.Signal(int)
    vis_toggled = QtCore.Signal(int, bool)

    COLOR_BEFORE = "#5588cc"
    COLOR_CURRENT = "#66cc66"
    COLOR_AFTER = "#cc6655"

    def __init__(self, layer_index, layer, parent=None):
        super().__init__(parent)
        self._index = layer_index
        self._layer = layer
        self._build()

    def _build(self):
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        color = {
            OnionLayer.BEFORE: self.COLOR_BEFORE,
            OnionLayer.CURRENT: self.COLOR_CURRENT,
            OnionLayer.AFTER: self.COLOR_AFTER,
        }.get(self._layer.role, "#888")

        dot = QtWidgets.QLabel("\u25CF")
        dot.setStyleSheet(f"color:{color}; font-size:14px;")
        dot.setFixedWidth(18)
        dot.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(dot)

        self._vis_cb = QtWidgets.QCheckBox()
        self._vis_cb.setChecked(self._layer.get_visible())
        self._vis_cb.setToolTip("Toggle visibility")
        self._vis_cb.clicked.connect(self._on_vis)
        lay.addWidget(self._vis_cb)

        lbl = QtWidgets.QLabel(self._layer.label())
        lbl.setStyleSheet(f"color:{color}; font-weight:bold;")
        lbl.setMinimumWidth(120)
        lay.addWidget(lbl)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(int(self._layer.get_alpha() * 100))
        self._slider.setFixedWidth(100)
        self._slider.setToolTip("Opacity")
        self._slider.valueChanged.connect(self._on_alpha)
        lay.addWidget(self._slider)

        self._alpha_lbl = QtWidgets.QLabel(
            f"{int(self._layer.get_alpha() * 100)}%")
        self._alpha_lbl.setFixedWidth(36)
        self._alpha_lbl.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lay.addWidget(self._alpha_lbl)

        btn_del = QtWidgets.QPushButton("\u2715")
        btn_del.setFixedSize(22, 22)
        btn_del.setToolTip("Delete this layer")
        btn_del.clicked.connect(
            lambda: self.delete_clicked.emit(self._index))
        lay.addWidget(btn_del)

    def _on_alpha(self, val):
        self._alpha_lbl.setText(f"{val}%")
        self.alpha_changed.emit(self._index, val / 100.0)

    def _on_vis(self):
        self.vis_toggled.emit(self._index, self._vis_cb.isChecked())


# ---------------------------------------------------------------------------
# Preset button
# ---------------------------------------------------------------------------
class PresetButton(QtWidgets.QPushButton):

    def __init__(self, before, after, label, parent=None):
        super().__init__(parent)
        self.before = before
        self.after = after
        self.setToolTip(f"{before} key(s) before + current + {after} key(s) after")
        self.setFixedSize(48, 40)
        self.setText(label)
        self.setStyleSheet("""
            QPushButton {
                background: #3a3a3a; border: 1px solid #555;
                border-radius: 4px; color: #ccc; font-size: 11px;
            }
            QPushButton:hover { background: #4a4a4a; border-color: #77a; }
            QPushButton:pressed { background: #555; }
        """)


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
class OnionSkinUI(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("onionSkinWidget")
        self.setWindowTitle(f"Onion Skin v{__version__}")
        self.setMinimumWidth(380)
        self.core = OnionSkinCore()
        self._build_ui()
        self._refresh_state()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ---- Menu bar ----
        mb = QtWidgets.QMenuBar(self)
        root.setMenuBar(mb)
        fm = mb.addMenu("File")
        fm.addAction("Delete All Ghosts", self._on_delete_all)
        fm.addAction("Clean Temp Files", self._on_clean_temp)
        fm.addSeparator()
        fm.addAction("Close", self.close)
        om = mb.addMenu("Options")
        self._outline_action = om.addAction("Outline Mode")
        self._outline_action.setCheckable(True)
        self._outline_action.toggled.connect(self._on_outline_toggled)
        om.addAction("Toggle Fit / Fix Offset", self._on_fix_offset)
        hm = mb.addMenu("Help")
        hm.addAction("About...", self._on_about)
        hm.addAction("How to Use...", self._on_help)

        # ---- Viewport ----
        vg = QtWidgets.QGroupBox("Viewport")
        vl = QtWidgets.QHBoxLayout(vg)
        self._vp_label = QtWidgets.QLabel("No viewport selected")
        self._vp_label.setStyleSheet("color:#aaa;")
        vl.addWidget(self._vp_label, stretch=1)
        btn_vp = QtWidgets.QPushButton("Select Viewport")
        btn_vp.setToolTip("Click a 3-D viewport, then press this.")
        btn_vp.clicked.connect(self._on_select_viewport)
        vl.addWidget(btn_vp)
        root.addWidget(vg)

        # ---- Target Object ----
        og = QtWidgets.QGroupBox("Target Object")
        ol = QtWidgets.QVBoxLayout(og)

        obj_row = QtWidgets.QHBoxLayout()
        self._obj_label = QtWidgets.QLabel("No object selected")
        self._obj_label.setStyleSheet("color:#aaa;")
        obj_row.addWidget(self._obj_label, stretch=1)
        btn_obj = QtWidgets.QPushButton("Set from Selection")
        btn_obj.setToolTip(
            "Select an animated object in the viewport, then click this.")
        btn_obj.clicked.connect(self._on_set_object)
        obj_row.addWidget(btn_obj)
        ol.addLayout(obj_row)

        self._key_info = QtWidgets.QLabel("")
        self._key_info.setStyleSheet("color:#888; font-size:11px;")
        ol.addWidget(self._key_info)

        self._hier_cb = QtWidgets.QCheckBox("Include Hierarchy")
        self._hier_cb.setChecked(True)
        self._hier_cb.setToolTip(
            "Also scan keyframes on child objects (joints, controls, etc.)")
        self._hier_cb.stateChanged.connect(self._on_hier_changed)
        ol.addWidget(self._hier_cb)

        self._isolate_cb = QtWidgets.QCheckBox("Isolate Rig During Capture")
        self._isolate_cb.setChecked(False)
        self._isolate_cb.setToolTip(
            "Find the top node of the selected rig and isolate it in the\n"
            "viewport before capturing. Un-isolates after capture completes.\n"
            "Useful for removing other rigs/objects from the ghost images.")
        self._isolate_cb.clicked.connect(self._on_isolate_changed)
        ol.addWidget(self._isolate_cb)

        self._rig_info = QtWidgets.QLabel("")
        self._rig_info.setStyleSheet("color:#888; font-size:11px;")
        ol.addWidget(self._rig_info)

        root.addWidget(og)

        # ---- Ghost Settings ----
        gg = QtWidgets.QGroupBox("Ghost Settings")
        gl = QtWidgets.QVBoxLayout(gg)

        # Single-frame capture (no key lookup)
        self._btn_single = QtWidgets.QPushButton(
            "Ghost Current Frame Only")
        self._btn_single.setMinimumHeight(28)
        self._btn_single.setEnabled(False)
        self._btn_single.setToolTip("Capture current frame (no key lookup).")
        self._btn_single.clicked.connect(self._on_single_frame)
        gl.addWidget(self._btn_single)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color:#444;")
        gl.addWidget(sep)

        # Keyframe-based presets
        kp_label = QtWidgets.QLabel("Ghost by Keyframes:")
        kp_label.setStyleSheet("color:#ccc; font-weight:bold;")
        gl.addWidget(kp_label)

        preset_row = QtWidgets.QHBoxLayout()
        self._preset_buttons = []
        for n in range(1, 6):
            btn = PresetButton(n, n, f"{n}k")
            btn.setEnabled(False)
            btn.clicked.connect(
                lambda checked=False, b=n, a=n: self._on_preset(b, a))
            preset_row.addWidget(btn)
            self._preset_buttons.append(btn)
        gl.addLayout(preset_row)

        # Dot diagram
        self._dot_label = QtWidgets.QLabel("")
        self._dot_label.setAlignment(QtCore.Qt.AlignCenter)
        self._dot_label.setStyleSheet("font-size:16px;")
        gl.addWidget(self._dot_label)

        # Custom before/after
        cust_row = QtWidgets.QHBoxLayout()
        cust_row.addWidget(QtWidgets.QLabel("Custom:"))

        self._spin_before = QtWidgets.QSpinBox()
        self._spin_before.setRange(0, 5)
        self._spin_before.setValue(1)
        self._spin_before.setPrefix("Before: ")
        self._spin_before.setToolTip("Keys before current time")
        self._spin_before.setFixedWidth(90)
        self._spin_before.valueChanged.connect(self._update_dot_diagram)
        cust_row.addWidget(self._spin_before)

        self._spin_after = QtWidgets.QSpinBox()
        self._spin_after.setRange(0, 5)
        self._spin_after.setValue(1)
        self._spin_after.setPrefix("After: ")
        self._spin_after.setToolTip("Keys after current time")
        self._spin_after.setFixedWidth(90)
        self._spin_after.valueChanged.connect(self._update_dot_diagram)
        cust_row.addWidget(self._spin_after)

        self._btn_custom = QtWidgets.QPushButton("Go")
        self._btn_custom.setFixedWidth(40)
        self._btn_custom.setEnabled(False)
        self._btn_custom.clicked.connect(self._on_custom_preset)
        cust_row.addWidget(self._btn_custom)
        cust_row.addStretch()
        gl.addLayout(cust_row)

        # Include current frame toggle
        self._include_cur_cb = QtWidgets.QCheckBox("Include Current Frame")
        self._include_cur_cb.setChecked(False)
        self._include_cur_cb.setToolTip(
            "Also capture the current frame even if it's not on a keyframe.")
        self._include_cur_cb.clicked.connect(self._update_dot_diagram)
        gl.addWidget(self._include_cur_cb)

        root.addWidget(gg)

        # ---- Ghosted Layers ----
        lg = QtWidgets.QGroupBox("Ghosted Layers")
        ll = QtWidgets.QVBoxLayout(lg)

        legend = QtWidgets.QHBoxLayout()
        for color, text in [
            (LayerItemWidget.COLOR_BEFORE, "Before"),
            (LayerItemWidget.COLOR_CURRENT, "Current"),
            (LayerItemWidget.COLOR_AFTER, "After"),
        ]:
            d = QtWidgets.QLabel(f"\u25CF {text}")
            d.setStyleSheet(f"color:{color}; font-size:11px;")
            legend.addWidget(d)
        legend.addStretch()
        ll.addLayout(legend)

        self._layer_scroll = QtWidgets.QScrollArea()
        self._layer_scroll.setWidgetResizable(True)
        self._layer_scroll.setMinimumHeight(120)
        self._layer_scroll.setMaximumHeight(280)
        self._layer_container = QtWidgets.QWidget()
        self._layer_layout = QtWidgets.QVBoxLayout(self._layer_container)
        self._layer_layout.setContentsMargins(2, 2, 2, 2)
        self._layer_layout.setSpacing(1)
        self._layer_layout.addStretch()
        self._layer_scroll.setWidget(self._layer_container)
        ll.addWidget(self._layer_scroll)

        bulk_row = QtWidgets.QHBoxLayout()
        self._btn_show_all = QtWidgets.QPushButton("Show All")
        self._btn_show_all.setEnabled(False)
        self._btn_show_all.clicked.connect(
            lambda: self._set_all_visible(True))
        bulk_row.addWidget(self._btn_show_all)
        self._btn_hide_all = QtWidgets.QPushButton("Hide All")
        self._btn_hide_all.setEnabled(False)
        self._btn_hide_all.clicked.connect(
            lambda: self._set_all_visible(False))
        bulk_row.addWidget(self._btn_hide_all)
        self._btn_delete_all = QtWidgets.QPushButton("Delete All")
        self._btn_delete_all.setEnabled(False)
        self._btn_delete_all.clicked.connect(self._on_delete_all)
        bulk_row.addWidget(self._btn_delete_all)
        ll.addLayout(bulk_row)

        root.addWidget(lg)

        # ---- Display Options ----
        dg = QtWidgets.QGroupBox("Display Options")
        dl = QtWidgets.QVBoxLayout(dg)

        near_row = QtWidgets.QHBoxLayout()
        near_row.addWidget(QtWidgets.QLabel("Near Opacity:"))
        self._near_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._near_slider.setRange(0, 100)
        self._near_slider.setValue(50)
        self._near_slider.valueChanged.connect(self._on_near_opacity)
        near_row.addWidget(self._near_slider, stretch=1)
        self._near_lbl = QtWidgets.QLabel("50%")
        self._near_lbl.setFixedWidth(36)
        near_row.addWidget(self._near_lbl)
        dl.addLayout(near_row)

        far_row = QtWidgets.QHBoxLayout()
        far_row.addWidget(QtWidgets.QLabel("Far Opacity:"))
        self._far_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._far_slider.setRange(0, 100)
        self._far_slider.setValue(15)
        self._far_slider.valueChanged.connect(self._on_far_opacity)
        far_row.addWidget(self._far_slider, stretch=1)
        self._far_lbl = QtWidgets.QLabel("15%")
        self._far_lbl.setFixedWidth(36)
        far_row.addWidget(self._far_lbl)
        dl.addLayout(far_row)

        fix_row = QtWidgets.QHBoxLayout()
        self._btn_refresh = QtWidgets.QPushButton("Refresh All")
        self._btn_refresh.setEnabled(False)
        self._btn_refresh.clicked.connect(self._on_refresh)
        fix_row.addWidget(self._btn_refresh)
        self._btn_fix = QtWidgets.QPushButton("Fix Offset")
        self._btn_fix.setEnabled(False)
        self._btn_fix.clicked.connect(self._on_fix_offset)
        fix_row.addWidget(self._btn_fix)
        dl.addLayout(fix_row)

        root.addWidget(dg)

        # ---- Frame Navigation ----
        ng = QtWidgets.QGroupBox("Frame Navigation")
        nl = QtWidgets.QHBoxLayout(ng)
        for lb, tip, sl in [
            ("\u25C0", "Step back", self.core.step_back),
            ("\u23EE", "Prev key", self.core.prev_key),
            ("\u23ED", "Next key", self.core.next_key),
            ("\u25B6", "Step fwd", self.core.step_forward),
        ]:
            b = QtWidgets.QPushButton(lb)
            b.setToolTip(tip)
            b.setFixedWidth(48)
            b.clicked.connect(sl)
            nl.addWidget(b)
        root.addWidget(ng)

        # Status
        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(self._status)
        root.addStretch()

        self._update_dot_diagram()

    # -- Dot diagram -------------------------------------------------------

    def _update_dot_diagram(self, *args):
        b = self._spin_before.value()
        a = self._spin_after.value()
        inc_cur = self._include_cur_cb.isChecked()
        before_dots = " ".join(
            [f'<span style="color:#5588cc;">\u25CB</span>'] * b)
        current_dot = '<span style="color:#66cc66;">\u25CF</span>'
        after_dots = " ".join(
            [f'<span style="color:#cc6655;">\u25CB</span>'] * a)
        parts = []
        if before_dots:
            parts.append(before_dots)
        if inc_cur:
            parts.append(current_dot)
        if after_dots:
            parts.append(after_dots)
        self._dot_label.setText("  ".join(parts))

    # -- Slots -------------------------------------------------------------

    def _on_select_viewport(self):
        p = self.core.select_viewport()
        if p:
            self._vp_label.setText(
                f"{self.core.camera_for_panel()}  ({p})")
            self._vp_label.setStyleSheet("color:#ddd;")
            self._btn_single.setEnabled(True)
            self._update_preset_enabled()
            self._status.setText("Viewport locked.")

    def _on_set_object(self):
        obj, count, top_node = self.core.set_target_from_selection()
        if obj:
            self._obj_label.setText(obj)
            self._obj_label.setStyleSheet("color:#ddd; font-weight:bold;")
            if count > 0:
                self._key_info.setText(
                    f"{count} keyframe{'s' if count != 1 else ''} found")
                self._key_info.setStyleSheet("color:#8c8; font-size:11px;")
            else:
                self._key_info.setText("No keyframes found on this object")
                self._key_info.setStyleSheet("color:#c88; font-size:11px;")
            # Show rig top node info
            if top_node:
                self._rig_info.setText(f"Rig top node: {top_node}")
                self._rig_info.setStyleSheet("color:#aac; font-size:11px;")
            else:
                self._rig_info.setText("")
            self._update_preset_enabled()
            self._status.setText(f"Target: {obj}  ({count} keys)")

    def _on_isolate_changed(self):
        self.core.isolate_rig = self._isolate_cb.isChecked()
        if self.core.isolate_rig and self.core._rig_top_node:
            self._status.setText(
                f"Isolate ON — rig root: {self.core._rig_top_node}")
        else:
            self._status.setText("Isolate OFF")

    def _on_hier_changed(self, state):
        self.core.include_hierarchy = (state == QtCore.Qt.Checked)
        if self.core.target_object:
            count = self.core.rescan_keys()
            hier_txt = "+ hierarchy" if self.core.include_hierarchy else "object only"
            self._key_info.setText(
                f"{count} keyframe{'s' if count != 1 else ''} found  ({hier_txt})")
            if count > 0:
                self._key_info.setStyleSheet("color:#8c8; font-size:11px;")
            else:
                self._key_info.setStyleSheet("color:#c88; font-size:11px;")
            self._update_preset_enabled()

    def _update_preset_enabled(self):
        ready = (self.core.model_panel is not None
                 and self.core.target_object is not None
                 and len(self.core._cached_keys) > 0)
        for btn in self._preset_buttons:
            btn.setEnabled(ready)
        self._btn_custom.setEnabled(ready)

    def _on_single_frame(self):
        self._status.setText("Capturing current frame...")
        QtWidgets.QApplication.processEvents()
        self.core.create_single_frame()
        self._rebuild_layer_list()
        self._refresh_state()
        self._status.setText("Captured 1 frame.")

    def _on_preset(self, before, after):
        inc_cur = self._include_cur_cb.isChecked()
        self._status.setText(
            f"Finding {before} keys before + {after} keys after...")
        QtWidgets.QApplication.processEvents()

        err = self.core.create_ghost_from_keys(before, after, inc_cur)
        if err:
            self._status.setText(err)
            return

        self._apply_opacity_gradient()
        self._rebuild_layer_list()
        self._refresh_state()

        n = len(self.core.layers)
        frames_str = ", ".join(
            str(int(ly.frame)) for ly in self.core.layers)
        self._status.setText(
            f"{n} layer{'s' if n != 1 else ''} at keys: {frames_str}")

    def _on_custom_preset(self):
        b = self._spin_before.value()
        a = self._spin_after.value()
        self._on_preset(b, a)

    def _on_delete_all(self):
        self.core.delete_all()
        self._rebuild_layer_list()
        self._refresh_state()
        self._status.setText("All ghosts deleted.")

    def _on_clean_temp(self):
        _clean_temp_files()
        self._status.setText("Temp files cleaned.")

    def _on_refresh(self):
        self._status.setText("Refreshing...")
        QtWidgets.QApplication.processEvents()
        self.core.refresh_all()
        self._apply_opacity_gradient()
        self._rebuild_layer_list()
        self._refresh_state()
        self._status.setText("Refreshed all layers.")

    def _on_fix_offset(self):
        self.core.toggle_fit_all()
        self._status.setText("Fit toggled on all layers.")

    def _on_outline_toggled(self, checked):
        self.core.outline_mode = checked
        self._status.setText(f"Outline {'ON' if checked else 'OFF'}")

    def _set_all_visible(self, vis):
        self.core.set_all_visible(vis)
        if self.core.model_panel:
            cmds.modelEditor(
                self.core.model_panel, edit=True, imagePlane=False)
            cmds.modelEditor(
                self.core.model_panel, edit=True, imagePlane=True)
            cmds.refresh(force=True)
        self._rebuild_layer_list()
        self._status.setText("All " + ("shown." if vis else "hidden."))

    def _on_layer_alpha(self, index, alpha):
        if 0 <= index < len(self.core.layers):
            self.core.layers[index].set_alpha(alpha)

    def _on_layer_delete(self, index):
        self.core.delete_layer(index)
        self._rebuild_layer_list()
        self._refresh_state()
        self._status.setText("Layer deleted.")

    def _on_layer_vis(self, index, vis):
        if 0 <= index < len(self.core.layers):
            self.core.layers[index].set_visible(vis)
            # Cycle imagePlane display off/on to force Maya to redraw
            if self.core.model_panel:
                cmds.modelEditor(
                    self.core.model_panel, edit=True, imagePlane=False)
                cmds.modelEditor(
                    self.core.model_panel, edit=True, imagePlane=True)
                cmds.refresh(force=True)

    def _on_near_opacity(self, val):
        self._near_lbl.setText(f"{val}%")
        self._apply_opacity_gradient()

    def _on_far_opacity(self, val):
        self._far_lbl.setText(f"{val}%")
        self._apply_opacity_gradient()

    # -- Opacity gradient --------------------------------------------------

    def _apply_opacity_gradient(self):
        layers = self.core.layers
        if not layers:
            return
        near = self._near_slider.value() / 100.0
        far = self._far_slider.value() / 100.0

        cur_idx = None
        for i, ly in enumerate(layers):
            if ly.role == OnionLayer.CURRENT:
                cur_idx = i
                break

        if cur_idx is None:
            for ly in layers:
                ly.set_alpha(near)
            self._rebuild_layer_list()
            return

        max_dist = max(cur_idx, len(layers) - 1 - cur_idx, 1)

        for i, ly in enumerate(layers):
            dist = abs(i - cur_idx)
            if dist == 0:
                ly.set_alpha(near)
            else:
                t = dist / max_dist
                alpha = near + (far - near) * t
                ly.set_alpha(max(0.0, min(1.0, alpha)))

        self._rebuild_layer_list()

    # -- Layer list --------------------------------------------------------

    def _rebuild_layer_list(self):
        while self._layer_layout.count() > 0:
            item = self._layer_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for i, layer in enumerate(self.core.layers):
            if not layer.exists():
                continue
            row = LayerItemWidget(i, layer)
            row.alpha_changed.connect(self._on_layer_alpha)
            row.delete_clicked.connect(self._on_layer_delete)
            row.vis_toggled.connect(self._on_layer_vis)
            self._layer_layout.addWidget(row)

        self._layer_layout.addStretch()

    def _refresh_state(self):
        has = self.core.has_layers()
        self._btn_refresh.setEnabled(has)
        self._btn_delete_all.setEnabled(has)
        self._btn_show_all.setEnabled(has)
        self._btn_hide_all.setEnabled(has)
        self._btn_fix.setEnabled(has)

    # -- About / Help ------------------------------------------------------

    def _on_about(self):
        QtWidgets.QMessageBox.about(
            self, f"Onion Skin v{__version__}",
            f"<h3>Onion Skin v{__version__}</h3>"
            "<p>Keyframe-aware multi-plane ghosting for Maya.</p><hr>"
            "<p><b>Original MEL (v0.8.3, 2007):</b><br>"
            "Syed Ali Ahsan &lt;yoda@cyber.net.pk&gt;</p>"
            "<p><b>Python v2.1.0 (2026):</b> Keyframe-based ghosting, "
            "per-layer alpha, up to 10 stacked planes.</p>")

    def _on_help(self):
        QtWidgets.QMessageBox.information(
            self, "How to Use",
            "<h3>Quick Start</h3><ol>"
            "<li>Click a 3-D viewport \u2192 <b>Select Viewport</b>.</li>"
            "<li>Select an animated object \u2192 "
            "<b>Set from Selection</b>.</li>"
            "<li>Click a <b>preset</b> (1k\u20135k) to ghost that many "
            "keyframes before and after the current time.</li></ol>"
            "<h3>How Keyframe Ghosting Works</h3>"
            "<p>The tool reads all keyframes on your selected object "
            "(and its hierarchy if checked). When you pick <b>2k</b>, "
            "it finds the 2 nearest keyframes before the current time "
            "and the 2 nearest after, then playblasts a snapshot at "
            "each of those keyframe times.</p>"
            "<p>The result is an image plane for each key pose, stacked "
            "in the viewport with adjustable opacity.</p>"
            "<h3>Presets</h3>"
            "<p><b>1k</b> = 1 key before + current + 1 key after<br>"
            "<b>2k</b> = 2 keys before + current + 2 keys after<br>"
            "...up to <b>5k</b> (5+1+5 = 11, capped at 10 layers).</p>"
            "<p>Use <b>Custom</b> for asymmetric counts.</p>"
            "<h3>Layer List</h3>"
            "<p><span style='color:#5588cc'>\u25CF Blue</span> = before, "
            "<span style='color:#66cc66'>\u25CF Green</span> = current, "
            "<span style='color:#cc6655'>\u25CF Red</span> = after.<br>"
            "Each layer: visibility toggle, opacity slider, delete.</p>"
            "<h3>Display Options</h3>"
            "<p><b>Near/Far Opacity</b> auto-fades layers by distance.<br>"
            "<b>Fix Offset</b> toggles fit mode on all planes.</p>")


# ---------------------------------------------------------------------------
def launch():
    if cmds.workspaceControl(_WIN, exists=True):
        cmds.deleteUI(_WIN)
    cmds.workspaceControl(
        _WIN, label=f"Onion Skin v{__version__}",
        floating=True, initialWidth=440, initialHeight=700,
        minimumWidth=380, retain=False)
    ptr = omui.MQtUtil.findControl(_WIN)
    if ptr:
        w = wrapInstance(int(ptr), QtWidgets.QWidget)
        ui = OnionSkinUI(w)
        lay = w.layout()
        if lay is None:
            lay = QtWidgets.QVBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(ui)
