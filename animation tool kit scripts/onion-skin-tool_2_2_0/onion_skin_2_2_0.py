"""
Onion Skin v2.2.0 for Maya 2020+

A modern Python rewrite of the classic OnionSkin MEL tool by Syed Ali Ahsan (2007).
Keyframe-aware multi-plane ghosting: select an object, and the tool finds its
keyframes to capture 1-5 key-images before and after the current position.
Up to 10 stacked image planes, each with individual alpha control.

v2.2.0 changes:
    - Ghost planes are tagged in the scene, so Delete All performs a full
      scene sweep and never leaves orphaned image planes behind — even after
      the UI was closed, the scene was reopened, or Maya crashed mid-capture.
    - Leftover ghosts from a previous session are adopted into the layer
      list when the tool launches, so they stay visible AND deletable.
    - Capture is crash-safe: viewport background, image format, isolate
      mode, current time, selection, and layer visibility are always
      restored even if the playblast fails.
    - Fixed: timeline no longer jumps to the last captured key after a
      capture without a "current" layer.
    - Fixed: "Include Hierarchy" checkbox was ignored under PySide6
      (Maya 2025+) due to an enum comparison bug.
    - Fixed: outline mode created no toon lines (wrong node wiring) and
      hid strokes during the playblast.
    - Fixed: cleanup no longer deletes user-created pfxToon nodes — only
      the ones this tool created.
    - When the layer cap is hit, the keys furthest from the current time
      are dropped instead of blindly truncating the "after" keys.
    - UI: viewport is auto-detected on launch, per-frame progress feedback,
      color-coded status messages, smoother opacity-gradient updates, and
      a busy guard so capture can't be re-triggered mid-run.
    - Fixed: ghost planes were parked at depth 1000, so any set/environment
      geometry around the camera (walls, cycloramas) occluded them and they
      never appeared in shot cameras.  Planes now sit just past the camera's
      near clip plane and draw as a screen overlay at any scene scale.
    - New: optional Background Geo set — include chosen set/prop geometry
      in isolated ghost captures for spatial context, with a viewport
      hide/show toggle.
    - Preset buttons renamed from "1k".."5k" to "±1 Key".."±5 Keys".
    - Fixed: ghost size mismatched the live character.  The plane's stock
      fit modes map the image to the camera's film gate (e.g. aspect 1.5)
      while the playblast renders through the resolution gate (16:9); the
      plane is now pinned "To Size" to the exact resolution-gate rectangle
      computed from the camera's film fit, aperture, and overscan.
      "Fix Offset" is now "Re-Align Planes" and re-applies this fit.
    - UI: all options live in a vertical scroll area (menu bar and status
      bar stay pinned), so the window no longer needs to be full-height.
      The window opens compact with an always-visible scroll bar.
    - Fixed: "Include Current Frame" is respected — parking the playhead
      on a keyframe no longer forces a current-frame capture.
    - New: "Flip Ghosts" Prev/Next buttons cycle through the ghost
      planes one at a time (Show All restores them).
    - The target rig, background geo, and capture toggles are saved into
      the scene (fileInfo) and restored when the window reopens — and can
      be replaced any time with 'Set from Selection' / 'Add Selected'.

Original MEL script (v0.8.3):
    Author:  Syed Ali Ahsan  <yoda@cyber.net.pk>  (7 Feb 2007)
    Thanks to Mark Behm, Melt van der Spuy, Vincent Florio, Keith Lango,
    Herman Gonzalas, and Lord Ryan Santos.

Usage:
    import onion_skin_2_2_0
    onion_skin_2_2_0.launch()
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

__version__ = "2.2.0"
_WIN = "onionSkinWorkspaceCtrl"
TEMP_PREFIX = "OnionSkinTemp"
TEMP_FOLDER = "onion_skin_temp"
MAX_LAYERS = 10

# Playblast capture resolution (also drives the plane-fit math below)
CAPTURE_W = 960
CAPTURE_H = 540

# Every image plane this tool creates carries this string attribute so a
# scene sweep can always find and remove them, even across sessions.
TAG_ATTR = "onionSkinGhost"

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


def _find_tagged_planes():
    """Return every imagePlane shape in the scene created by this tool."""
    found = []
    for shape in cmds.ls(type="imagePlane") or []:
        try:
            if cmds.attributeQuery(TAG_ATTR, node=shape, exists=True):
                found.append(shape)
        except Exception:
            pass
    return found


def _tag_plane(shape, frame, role):
    """Mark an imagePlane shape as an onion-skin ghost."""
    if not cmds.attributeQuery(TAG_ATTR, node=shape, exists=True):
        cmds.addAttr(shape, longName=TAG_ATTR, dataType="string")
    cmds.setAttr(f"{shape}.{TAG_ATTR}", f"{frame}|{role}", type="string")


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
        arr = np.ascontiguousarray(arr)
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

    @classmethod
    def from_tagged_shape(cls, shape):
        """Rebuild a layer from a tagged imagePlane left in the scene."""
        parents = cmds.listRelatives(shape, parent=True) or []
        xform = parents[0] if parents else None
        tag = ""
        try:
            tag = cmds.getAttr(f"{shape}.{TAG_ATTR}") or ""
        except Exception:
            pass
        parts = tag.split("|")
        try:
            frame = float(parts[0])
        except (ValueError, IndexError):
            frame = 0.0
        role = parts[1] if len(parts) > 1 else cls.BEFORE
        if role not in (cls.BEFORE, cls.CURRENT, cls.AFTER):
            role = cls.BEFORE
        img = ""
        try:
            img = cmds.getAttr(f"{shape}.imageName") or ""
        except Exception:
            pass
        return cls(frame, role, xform, shape, img)

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
        # Delete the transform first (removes the shape with it), but fall
        # back to the shape so a half-broken layer never leaves nodes behind.
        for node in (self.xform, self.shape):
            if node and cmds.objExists(node):
                try:
                    cmds.delete(node)
                except Exception:
                    pass
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
        self._toon_nodes = []          # toon helper nodes created by us
        self.background_nodes = []     # user-chosen set/background geo
        self.include_background = True  # add bg geo to the isolate capture

    # -- Viewport ----------------------------------------------------------

    def select_viewport(self, silent=False):
        p = get_active_model_panel()
        if p is None:
            if not silent:
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

    def camera_shape_for_panel(self):
        """Return the camera SHAPE node for the locked panel, or None."""
        if not self.model_panel:
            return None
        cam = cmds.modelPanel(self.model_panel, query=True, camera=True)
        if not cam:
            return None
        if cmds.nodeType(cam) == "camera":
            return cam
        shapes = cmds.listRelatives(cam, shapes=True, type="camera") or []
        return shapes[0] if shapes else None

    def _plane_depth(self, stack_index):
        """Depth for a ghost plane, just past the camera's near clip plane.

        Image planes are depth-tested 3D quads: a large fixed depth (the
        old 1000) parks them behind any set/environment geometry that
        surrounds the camera, making them invisible.  Sitting right after
        the near clip plane makes them draw as a screen overlay in front
        of everything, blended by their alpha, at any scene scale.
        """
        near = 0.1
        cam_shape = self.camera_shape_for_panel()
        if cam_shape:
            try:
                near = cmds.getAttr(f"{cam_shape}.nearClipPlane")
            except Exception:
                pass
        base = max(near * 1.1, 0.001)
        return base + stack_index * base * 0.02

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
        self.save_prefs()
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

        # Take the N closest keys before (nearest to cur last, so slice end)
        chosen_before = keys_before[-before_count:] if before_count else []
        # Take the N closest keys after (nearest to cur first, so slice start)
        chosen_after = keys_after[:after_count] if after_count else []

        result = []
        for k in chosen_before:
            result.append((k, OnionLayer.BEFORE))
        # Include the current frame ONLY when the checkbox asks for it —
        # sitting on a keyframe must not override the user's choice.
        if include_current:
            result.append((cur, OnionLayer.CURRENT))
        for k in chosen_after:
            result.append((k, OnionLayer.AFTER))

        return result

    # -- Ghost creation ----------------------------------------------------

    def create_ghost_from_keys(self, before_count, after_count,
                               include_current=False, progress_cb=None):
        """Main entry: ghost N keys before + current + N keys after.
        Returns an error string, or None on success."""
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

        self._capture_layers(frames_and_roles, progress_cb)
        return None

    def create_single_frame(self, progress_cb=None):
        """Capture just the current frame (no keyframe lookup needed).
        Returns an error string, or None on success."""
        if not self.model_panel:
            cmds.warning("No viewport selected.")
            return "No viewport selected."
        cur = cmds.currentTime(query=True)
        self._capture_layers([(cur, OnionLayer.CURRENT)], progress_cb)
        return None

    # -- Layer management --------------------------------------------------

    def delete_all(self):
        """Delete every ghost plane: tracked layers AND a scene-wide sweep
        of tagged planes, so nothing is ever left behind (e.g. ghosts from
        a previous session or an interrupted capture)."""
        for layer in self.layers:
            layer.delete()
        self.layers = []
        for shape in _find_tagged_planes():
            parents = cmds.listRelatives(shape, parent=True,
                                         fullPath=True) or []
            try:
                cmds.delete(parents[0] if parents else shape)
            except Exception:
                pass
        _clean_temp_files()

    def adopt_existing(self):
        """Pick up tagged ghost planes left in the scene by a previous
        session so they show in the layer list and remain deletable.
        Returns the number of adopted layers."""
        known = {ly.shape for ly in self.layers if ly.shape}
        adopted = 0
        for shape in _find_tagged_planes():
            if shape in known:
                continue
            layer = OnionLayer.from_tagged_shape(shape)
            if layer.exists():
                self.layers.append(layer)
                adopted += 1
        if adopted:
            self.layers.sort(key=lambda ly: ly.frame)
            # Ghosts made by older builds sit at depth 1000+ (occluded by
            # set geometry) and use gate-based fit modes (wrong scale) —
            # pull them into the overlay range and re-pin their fit.
            if self.model_panel:
                self.realign_all()
        return adopted

    # -- Background geometry ------------------------------------------------

    def set_background_from_selection(self):
        """Store the current selection as background/set geometry to be
        included in isolated captures.  Returns the node count."""
        sel = cmds.ls(selection=True, long=True) or []
        self.background_nodes = sel
        self.save_prefs()
        return len(sel)

    def clear_background(self):
        self.background_nodes = []
        self.save_prefs()

    def existing_background_nodes(self):
        return [n for n in self.background_nodes if cmds.objExists(n)]

    def toggle_background_visibility(self):
        """Flip visibility on the stored background nodes.
        Returns the new state (True = shown), or None if nothing is set."""
        nodes = self.existing_background_nodes()
        if not nodes:
            return None
        any_visible = False
        for n in nodes:
            try:
                if cmds.getAttr(f"{n}.visibility"):
                    any_visible = True
                    break
            except Exception:
                pass
        new_state = not any_visible
        for n in nodes:
            try:
                cmds.setAttr(f"{n}.visibility", int(new_state))
            except Exception:
                pass
        return new_state

    # -- Session persistence (stored in the scene file) ----------------------

    def save_prefs(self):
        """Persist target/background choices into the scene via fileInfo
        so reopening the window (or the scene) restores the setup."""
        try:
            cmds.fileInfo("onionSkinTarget", self.target_object or "")
            cmds.fileInfo("onionSkinBackground",
                          ";".join(self.background_nodes))
            cmds.fileInfo("onionSkinIncludeBg",
                          "1" if self.include_background else "0")
            cmds.fileInfo("onionSkinIsolate",
                          "1" if self.isolate_rig else "0")
            cmds.fileInfo("onionSkinIncludeHier",
                          "1" if self.include_hierarchy else "0")
        except Exception:
            pass

    def load_prefs(self):
        """Restore the setup saved by save_prefs.  Returns True if a
        still-existing target object was restored."""
        def _get(key):
            try:
                v = cmds.fileInfo(key, query=True)
                return v[0] if v else ""
            except Exception:
                return ""

        val = _get("onionSkinIncludeHier")
        if val:
            self.include_hierarchy = (val == "1")
        val = _get("onionSkinIsolate")
        if val:
            self.isolate_rig = (val == "1")
        val = _get("onionSkinIncludeBg")
        if val:
            self.include_background = (val == "1")

        bg = _get("onionSkinBackground")
        if bg:
            self.background_nodes = [
                n for n in bg.split(";") if n and cmds.objExists(n)]

        tgt = _get("onionSkinTarget")
        if tgt and cmds.objExists(tgt):
            self.target_object = tgt
            self._cached_keys = get_all_keyframe_times(
                tgt, self.include_hierarchy)
            self.find_rig_top_node()
            return True
        return False

    def delete_layer(self, index):
        if 0 <= index < len(self.layers):
            self.layers[index].delete()
            self.layers.pop(index)

    def refresh_all(self, progress_cb=None):
        """Re-capture all layers at their stored frames."""
        if not self.model_panel:
            return
        old_info = [(ly.frame, ly.role) for ly in self.layers]
        self.delete_all()
        if old_info:
            self._capture_layers(old_info, progress_cb)

    def set_all_visible(self, vis):
        for ly in self.layers:
            ly.set_visible(vis)

    def solo_layer(self, index):
        """Show only the layer at *index*, hiding all the others."""
        for i, ly in enumerate(self.layers):
            ly.set_visible(i == index)

    def has_layers(self):
        self.layers = [ly for ly in self.layers if ly.exists()]
        return len(self.layers) > 0

    def _apply_plane_fit(self, shape):
        """Pin the plane to the exact film-plane rectangle the playblast
        rendered, so the ghost lines up 1:1 with the live view.

        The camera's film gate (e.g. 1.417 x 0.945, aspect 1.5) rarely
        matches the capture aspect (16:9).  The stock image-plane fit
        modes map the image to the film gate, which is a different
        rectangle than the resolution gate the playblast rendered from,
        scaling the ghost character up or down.  Instead we compute the
        resolution-gate rectangle in aperture units from the camera's
        film fit and lock the plane to it with fit mode "To Size".
        """
        cam_shape = self.camera_shape_for_panel()
        if not cam_shape:
            return
        try:
            h_ap = cmds.getAttr(f"{cam_shape}.horizontalFilmAperture")
            v_ap = cmds.getAttr(f"{cam_shape}.verticalFilmAperture")
            film_fit = cmds.getAttr(f"{cam_shape}.filmFit")
        except Exception:
            return
        try:
            overscan = cmds.getAttr(f"{cam_shape}.overscan") or 1.0
        except Exception:
            overscan = 1.0

        img_aspect = float(CAPTURE_W) / float(CAPTURE_H)
        film_aspect = h_ap / v_ap
        width_matched = (h_ap, h_ap / img_aspect)
        height_matched = (v_ap * img_aspect, v_ap)

        if film_fit == 1:    # Horizontal
            w, h = width_matched
        elif film_fit == 2:  # Vertical
            w, h = height_matched
        elif film_fit == 3:  # Overscan
            w, h = height_matched if img_aspect > film_aspect \
                else width_matched
        else:                # Fill (default)
            w, h = width_matched if img_aspect > film_aspect \
                else height_matched

        w *= overscan
        h *= overscan
        try:
            cmds.setAttr(f"{shape}.fit", 4)  # To Size
            cmds.setAttr(f"{shape}.sizeX", w)
            cmds.setAttr(f"{shape}.sizeY", h)
            cmds.setAttr(f"{shape}.offsetX", 0)
            cmds.setAttr(f"{shape}.offsetY", 0)
        except Exception:
            pass

    def realign_all(self):
        """Re-apply the gate-aligned fit and overlay depth to every
        layer.  Returns the number of planes touched."""
        n = 0
        for idx, ly in enumerate(self.layers):
            if ly.exists():
                self._apply_plane_fit(ly.shape)
                try:
                    cmds.setAttr(f"{ly.shape}.depth", self._plane_depth(idx))
                except Exception:
                    pass
                n += 1
        return n

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

    def _capture_layers(self, frames_and_roles, progress_cb=None):
        """Delete existing layers, then capture new ones.

        Everything that mutates global state (background color, image
        format, isolate mode, current time, selection) is restored in a
        finally block so a failed playblast can't corrupt the session.
        """
        self.delete_all()

        if len(frames_and_roles) > MAX_LAYERS:
            # Keep the keys closest to the current time, then restore
            # chronological order.
            cur = cmds.currentTime(query=True)
            frames_and_roles = sorted(
                frames_and_roles,
                key=lambda fr: abs(fr[0] - cur))[:MAX_LAYERS]
            frames_and_roles.sort(key=lambda fr: fr[0])

        sel = cmds.ls(selection=True, flatten=True) or []
        orig_time = cmds.currentTime(query=True)
        orig_fmt = cmds.getAttr("defaultRenderGlobals.imageFormat")
        cmds.setAttr("defaultRenderGlobals.imageFormat", 32)  # PNG

        # Set green-screen background for chroma keying
        orig_bg = _set_viewport_bg()

        did_isolate = False
        try:
            # Isolate rig if enabled
            if self.isolate_rig and self._rig_top_node:
                did_isolate = self._enable_isolate()

            total = len(frames_and_roles)
            for idx, (frame, role) in enumerate(frames_and_roles):
                if progress_cb:
                    progress_cb(idx, total, frame)
                layer = self._snapshot_one(frame, role, idx)
                if layer:
                    self.layers.append(layer)
        finally:
            # Un-isolate before restoring anything else
            if did_isolate:
                self._disable_isolate()

            # Restore original background and image format
            _restore_viewport_bg(orig_bg)
            cmds.setAttr("defaultRenderGlobals.imageFormat", orig_fmt)

            # Re-show all layers — they were hidden during capture
            for ly in self.layers:
                if ly.exists():
                    ly.set_visible(True)

            # Always return the playhead to where the user left it
            cmds.currentTime(orig_time, edit=True)

            if sel:
                try:
                    cmds.select(sel, replace=True)
                except Exception:
                    pass

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

        try:
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
                             strokes=self.outline_mode,
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
                widthHeight=[CAPTURE_W, CAPTURE_H])
        finally:
            # Restore viewport display state
            self._restore_viewport_display(vp_state)
            cmds.modelEditor(self.model_panel, edit=True,
                             selectionHiliteDisplay=sel_hilite)
            # Restore selection
            if sel:
                try:
                    cmds.select(sel, replace=True)
                except Exception:
                    pass

        # Find the raw playblast image
        img_file = self._find_image(temp_dir, frame, out_base)
        if img_file is None:
            cmds.warning(f"[OnionSkin] No image for frame {frame}")
            self._cleanup_toon()
            return None

        # Chroma-key: replace green background with transparency
        img_file = _chroma_key_image(img_file)

        # Create image plane
        xform, shape = self._create_plane()
        if not xform or not shape:
            cmds.warning("[OnionSkin] Failed to create plane.")
            self._cleanup_toon()
            return None

        # Configure and tag so a scene sweep can always find this plane
        cmds.setAttr(f"{shape}.imageName", img_file, type="string")
        cmds.setAttr(f"{shape}.useFrameExtension", 0)
        self._apply_plane_fit(shape)
        _tag_plane(shape, frame, role)

        alpha = self._default_alpha(role, stack_index)
        cmds.setAttr(f"{shape}.alphaGain", alpha)

        depth = self._plane_depth(stack_index)
        cmds.setAttr(f"{shape}.depth", depth)
        cmds.setAttr(f"{xform}.visibility", 1)

        self._cleanup_toon()

        return OnionLayer(frame, role, xform, shape, img_file,
                          key_index=stack_index)

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
        """Create an image plane attached to the panel's camera.
        NEVER renames nodes -- stores Maya's auto-generated names."""
        cam_shape = self.camera_shape_for_panel()
        if not cam_shape:
            return None, None

        try:
            xform, shape = cmds.imagePlane(camera=cam_shape)
        except Exception:
            cmds.warning("[OnionSkin] imagePlane not created.")
            return None, None

        cmds.setAttr(f"{shape}.depth", self._plane_depth(0))
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
            if nt not in ("mesh", "nurbsSurface"):
                continue
            # createNode on a shape type returns the shape and auto-creates
            # a parent transform; track the transform for cleanup.
            node = cmds.createNode("pfxToon")
            if cmds.nodeType(node) == "pfxToon":
                toon_shape = node
                parents = cmds.listRelatives(node, parent=True) or [node]
                toon_xform = parents[0]
            else:
                toon_xform = node
                ss = cmds.listRelatives(node, shapes=True) or [None]
                toon_shape = ss[0]
            if not toon_shape:
                continue
            self._toon_nodes.append(toon_xform)
            cmds.connectAttr(
                f"{shape}.worldMatrix[0]",
                f"{toon_shape}.inputSurface[0].inputWorldMatrix")
            if nt == "mesh":
                cmds.connectAttr(
                    f"{shape}.outMesh",
                    f"{toon_shape}.inputSurface[0].surface")
            elif nt == "nurbsSurface":
                tess = cmds.createNode("nurbsTessellate")
                cmds.setAttr(f"{tess}.caching", True)
                cmds.connectAttr(f"{shape}.local", f"{tess}.inputSurface")
                cmds.connectAttr(
                    f"{tess}.outputPolygon",
                    f"{toon_shape}.inputSurface[0].surface")
                self._toon_nodes.append(tess)
            cmds.setAttr(f"{toon_shape}.borderLines", 1)
            cmds.setAttr(f"{toon_shape}.displayPercent", 0.05)
            cmds.setAttr(f"{toon_shape}.drawAsMesh", 0)
            cmds.setAttr(f"{toon_shape}.creaseLines", 0)
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
        """Isolate the rig hierarchy (plus optional background geo)
        in the viewport."""
        if not self.model_panel or not self._rig_top_node:
            return False

        iso_nodes = self.get_rig_hierarchy()
        if not iso_nodes:
            return False

        # Optionally include the user-chosen background/set geometry so
        # the ghost images keep spatial context (floor, props, walls).
        if self.include_background:
            for bg in self.existing_background_nodes():
                iso_nodes.append(bg)
                iso_nodes.extend(cmds.listRelatives(
                    bg, allDescendents=True, fullPath=True) or [])

        # Turn on isolate-select mode on this panel
        panel = self.model_panel
        cmds.isolateSelect(panel, state=True)

        # Clear any existing isolate set, then add our nodes
        cmds.isolateSelect(panel, removeSelected=True)
        cmds.select(iso_nodes, replace=True)
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
        """Delete only the toon nodes this tool created."""
        stale = [n for n in self._toon_nodes if cmds.objExists(n)]
        if stale:
            try:
                cmds.delete(stale)
            except Exception:
                pass
            if self._viewport_state:
                self._restore_viewport_state()
        self._toon_nodes = []


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

        dot = QtWidgets.QLabel("●")
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

        btn_del = QtWidgets.QPushButton("✕")
        btn_del.setFixedSize(22, 22)
        btn_del.setToolTip("Delete this layer")
        btn_del.clicked.connect(
            lambda: self.delete_clicked.emit(self._index))
        lay.addWidget(btn_del)

    def sync_from_layer(self):
        """Refresh slider/label/checkbox from the Maya node without
        re-emitting signals (used by the opacity-gradient sliders)."""
        a = int(self._layer.get_alpha() * 100)
        self._slider.blockSignals(True)
        self._slider.setValue(a)
        self._slider.blockSignals(False)
        self._alpha_lbl.setText(f"{a}%")
        self._vis_cb.blockSignals(True)
        self._vis_cb.setChecked(bool(self._layer.get_visible()))
        self._vis_cb.blockSignals(False)

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
        self.setToolTip(
            f"Ghost the {before} nearest key(s) before and the {after} "
            "nearest key(s) after the current time")
        self.setFixedHeight(40)
        self.setMinimumWidth(56)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)
        self.setText(label)
        self.setStyleSheet("""
            QPushButton {
                background: #3a3a3a; border: 1px solid #555;
                border-radius: 4px; color: #ccc; font-size: 11px;
            }
            QPushButton:hover { background: #4a4a4a; border-color: #77a; }
            QPushButton:pressed { background: #555; }
            QPushButton:disabled { color: #666; border-color: #3a3a3a; }
        """)


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------
class OnionSkinUI(QtWidgets.QWidget):

    _STATUS_COLORS = {
        "info": "#999",
        "ok":   "#8c8",
        "warn": "#cc8",
        "err":  "#c88",
        "busy": "#8ac",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("onionSkinWidget")
        self.setWindowTitle(f"Onion Skin v{__version__}")
        self.setMinimumWidth(380)
        self.core = OnionSkinCore()
        self._capturing = False
        self._layer_items = []
        self._solo_index = None
        self._build_ui()
        self._startup()

    def sizeHint(self):
        # Keep the default window compact — the scroll area supplies
        # access to everything below the fold.  Without this the floating
        # workspace control sizes itself to the full content height and
        # the scroll bar never engages.
        return QtCore.QSize(440, 560)

    def _startup(self):
        """Auto-detect a viewport and adopt any ghosts left in the scene
        by a previous session, so the tool is usable with zero clicks."""
        panel = self.core.select_viewport(silent=True)
        if panel:
            self._vp_label.setText(
                f"{self.core.camera_for_panel()}  ({panel})")
            self._vp_label.setStyleSheet("color:#ddd;")
            self._btn_single.setEnabled(True)

        restored = self._restore_session()
        adopted = self.core.adopt_existing()
        self._rebuild_layer_list()
        self._refresh_state()

        if adopted:
            self._set_status(
                f"Recovered {adopted} ghost layer"
                f"{'s' if adopted != 1 else ''} from the scene.", "warn")
        elif restored:
            self._set_status(
                "Restored target and background settings from the scene.",
                "info")
        elif panel:
            self._set_status(
                "Viewport detected. Select an animated object, then press "
                "'Set from Selection'.", "info")
        else:
            self._set_status(
                "Click inside a 3-D viewport, then press "
                "'Select Viewport'.", "info")

    def _restore_session(self):
        """Reload the target rig, background geo, and toggles saved in
        the scene so reopening the window doesn't lose the setup.
        Returns True if anything was restored."""
        restored_target = self.core.load_prefs()

        for cb, state in (
                (self._hier_cb, self.core.include_hierarchy),
                (self._isolate_cb, self.core.isolate_rig),
                (self._bg_include_cb, self.core.include_background)):
            cb.blockSignals(True)
            cb.setChecked(bool(state))
            cb.blockSignals(False)

        if restored_target:
            obj = self.core.target_object
            count = len(self.core._cached_keys)
            self._obj_label.setText(obj)
            self._obj_label.setStyleSheet("color:#ddd; font-weight:bold;")
            self._key_info.setText(
                f"{count} keyframe{'s' if count != 1 else ''} found")
            self._key_info.setStyleSheet(
                "color:#8c8; font-size:11px;" if count
                else "color:#c88; font-size:11px;")
            if self.core._rig_top_node:
                self._rig_info.setText(
                    f"Rig top node: {self.core._rig_top_node}")
                self._rig_info.setStyleSheet("color:#aac; font-size:11px;")
            self._update_preset_enabled()

        if self.core.existing_background_nodes():
            self._update_bg_label()

        return restored_target or bool(self.core.background_nodes)

    def _build_ui(self):
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold; color: #ccc;
                border: 1px solid #4a4a4a; border-radius: 6px;
                margin-top: 8px; padding-top: 6px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 8px; padding: 0 4px;
            }
        """)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Menu bar (pinned above the scroll area) ----
        mb = QtWidgets.QMenuBar(self)
        outer.setMenuBar(mb)
        fm = mb.addMenu("File")
        fm.addAction("Delete All Ghosts", self._on_delete_all)
        fm.addAction("Clean Temp Files", self._on_clean_temp)
        fm.addSeparator()
        fm.addAction("Close", self.close)
        om = mb.addMenu("Options")
        self._outline_action = om.addAction("Outline Mode")
        self._outline_action.setCheckable(True)
        self._outline_action.toggled.connect(self._on_outline_toggled)
        om.addAction("Re-Align Image Planes", self._on_fix_offset)
        hm = mb.addMenu("Help")
        hm.addAction("About...", self._on_about)
        hm.addAction("How to Use...", self._on_help)

        # ---- Scrollable content ----
        # All option groups live inside a scroll area so the window can
        # be kept short without hiding controls.
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOn)
        self._scroll.setMinimumHeight(240)
        content = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(content)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ---- Viewport ----
        vg = QtWidgets.QGroupBox("Step 1 — Viewport")
        vl = QtWidgets.QHBoxLayout(vg)
        self._vp_label = QtWidgets.QLabel("No viewport selected")
        self._vp_label.setStyleSheet("color:#aaa;")
        vl.addWidget(self._vp_label, stretch=1)
        btn_vp = QtWidgets.QPushButton("Select Viewport")
        btn_vp.setToolTip("Click a 3-D viewport, then press this.\n"
                          "(Auto-detected at launch when possible.)")
        btn_vp.clicked.connect(self._on_select_viewport)
        vl.addWidget(btn_vp)
        root.addWidget(vg)

        # ---- Target Object ----
        og = QtWidgets.QGroupBox("Step 2 — Target Object")
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
        self._hier_cb.toggled.connect(self._on_hier_changed)
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

        # ---- Background Geometry ----
        bg = QtWidgets.QGroupBox("Background Geo  (optional)")
        bl = QtWidgets.QVBoxLayout(bg)

        bg_row = QtWidgets.QHBoxLayout()
        self._bg_label = QtWidgets.QLabel("None set")
        self._bg_label.setStyleSheet("color:#aaa;")
        bg_row.addWidget(self._bg_label, stretch=1)
        btn_bg_add = QtWidgets.QPushButton("Add Selected")
        btn_bg_add.setToolTip(
            "Select set/prop geometry (floor, bed, walls...) and click "
            "this.\nIt will be included in isolated ghost captures for "
            "spatial context.")
        btn_bg_add.clicked.connect(self._on_bg_add)
        bg_row.addWidget(btn_bg_add)
        btn_bg_clear = QtWidgets.QPushButton("Clear")
        btn_bg_clear.setFixedWidth(50)
        btn_bg_clear.clicked.connect(self._on_bg_clear)
        bg_row.addWidget(btn_bg_clear)
        bl.addLayout(bg_row)

        bg_row2 = QtWidgets.QHBoxLayout()
        self._bg_include_cb = QtWidgets.QCheckBox("Include in Ghost Capture")
        self._bg_include_cb.setChecked(True)
        self._bg_include_cb.setToolTip(
            "When 'Isolate Rig During Capture' is on, also keep this\n"
            "background geometry visible in the captured ghost images.")
        self._bg_include_cb.toggled.connect(self._on_bg_include_changed)
        bg_row2.addWidget(self._bg_include_cb, stretch=1)
        self._btn_bg_vis = QtWidgets.QPushButton("Hide / Show in Viewport")
        self._btn_bg_vis.setEnabled(False)
        self._btn_bg_vis.setToolTip(
            "Toggle the visibility of the background geometry in the\n"
            "viewport so the ghosts read more clearly.")
        self._btn_bg_vis.clicked.connect(self._on_bg_toggle_vis)
        bg_row2.addWidget(self._btn_bg_vis)
        bl.addLayout(bg_row2)

        root.addWidget(bg)

        # ---- Ghost Settings ----
        gg = QtWidgets.QGroupBox("Step 3 — Ghost")
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
        kp_label = QtWidgets.QLabel(
            "Ghost by Keyframes  (keys before + after current time):")
        kp_label.setStyleSheet("color:#ccc; font-weight:bold;")
        gl.addWidget(kp_label)

        preset_row = QtWidgets.QHBoxLayout()
        self._preset_buttons = []
        for n in range(1, 6):
            btn = PresetButton(n, n,
                               f"±{n} Key" if n == 1 else f"±{n} Keys")
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
            d = QtWidgets.QLabel(f"● {text}")
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

        self._empty_hint = QtWidgets.QLabel(
            "No ghosts yet — capture some with Step 3 above.")
        self._empty_hint.setStyleSheet("color:#777; font-size:11px;")
        self._empty_hint.setAlignment(QtCore.Qt.AlignCenter)
        ll.addWidget(self._empty_hint)

        flip_row = QtWidgets.QHBoxLayout()
        flip_lbl = QtWidgets.QLabel("Flip Ghosts:")
        flip_lbl.setStyleSheet("color:#ccc;")
        flip_row.addWidget(flip_lbl)
        self._btn_ghost_prev = QtWidgets.QPushButton("◀ Prev")
        self._btn_ghost_prev.setEnabled(False)
        self._btn_ghost_prev.setToolTip(
            "Show only the previous ghost plane (wraps around).\n"
            "Use Show All to bring every ghost back.")
        self._btn_ghost_prev.clicked.connect(
            lambda: self._on_flip_ghost(-1))
        flip_row.addWidget(self._btn_ghost_prev)
        self._btn_ghost_next = QtWidgets.QPushButton("Next ▶")
        self._btn_ghost_next.setEnabled(False)
        self._btn_ghost_next.setToolTip(
            "Show only the next ghost plane (wraps around).\n"
            "Use Show All to bring every ghost back.")
        self._btn_ghost_next.clicked.connect(
            lambda: self._on_flip_ghost(1))
        flip_row.addWidget(self._btn_ghost_next)
        flip_row.addStretch()
        ll.addLayout(flip_row)

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
        self._btn_delete_all.setToolTip(
            "Remove every ghost image plane from the scene,\n"
            "including any left over from previous sessions.")
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
        self._btn_refresh.setToolTip(
            "Re-capture every layer at its stored frame.")
        self._btn_refresh.clicked.connect(self._on_refresh)
        fix_row.addWidget(self._btn_refresh)
        self._btn_fix = QtWidgets.QPushButton("Re-Align Planes")
        self._btn_fix.setEnabled(False)
        self._btn_fix.setToolTip(
            "Re-pin every ghost plane to the camera's rendered gate\n"
            "(fixes size/position drift after camera setting changes).")
        self._btn_fix.clicked.connect(self._on_fix_offset)
        fix_row.addWidget(self._btn_fix)
        dl.addLayout(fix_row)

        root.addWidget(dg)

        # ---- Frame Navigation ----
        ng = QtWidgets.QGroupBox("Frame Navigation")
        nl = QtWidgets.QHBoxLayout(ng)
        for lb, tip, sl in [
            ("◀", "Step back", self.core.step_back),
            ("⏮", "Prev key", self.core.prev_key),
            ("⏭", "Next key", self.core.next_key),
            ("▶", "Step fwd", self.core.step_forward),
        ]:
            b = QtWidgets.QPushButton(lb)
            b.setToolTip(tip)
            b.setFixedWidth(48)
            b.clicked.connect(sl)
            nl.addWidget(b)
        root.addWidget(ng)

        root.addStretch()
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll, stretch=1)

        # ---- Status bar (pinned below the scroll area) ----
        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet(
            "color:#888; font-size:11px; padding:4px 8px;")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        self._update_dot_diagram()

    # -- Status / busy helpers ----------------------------------------------

    def _set_status(self, msg, kind="info"):
        color = self._STATUS_COLORS.get(kind, "#888")
        self._status.setStyleSheet(
            f"color:{color}; font-size:11px; padding:4px 8px;")
        self._status.setText(msg)

    def _on_capture_progress(self, idx, total, frame):
        self._set_status(
            f"Capturing frame {int(frame)}  ({idx + 1}/{total})...", "busy")
        QtWidgets.QApplication.processEvents()

    def _begin_capture(self):
        """Guard against re-entrant capture; returns False if already busy."""
        if self._capturing:
            return False
        self._capturing = True
        self._set_capture_buttons_enabled(False)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        return True

    def _end_capture(self):
        self._capturing = False
        QtWidgets.QApplication.restoreOverrideCursor()
        self._set_capture_buttons_enabled(True)
        self._update_preset_enabled()

    def _set_capture_buttons_enabled(self, on):
        self._btn_single.setEnabled(on and self.core.model_panel is not None)
        self._btn_refresh.setEnabled(on and bool(self.core.layers))
        for btn in self._preset_buttons:
            btn.setEnabled(on)
        self._btn_custom.setEnabled(on)

    # -- Dot diagram -------------------------------------------------------

    def _update_dot_diagram(self, *args):
        b = self._spin_before.value()
        a = self._spin_after.value()
        inc_cur = self._include_cur_cb.isChecked()
        before_dots = " ".join(
            ['<span style="color:#5588cc;">○</span>'] * b)
        current_dot = '<span style="color:#66cc66;">●</span>'
        after_dots = " ".join(
            ['<span style="color:#cc6655;">○</span>'] * a)
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
            self._set_status("Viewport locked.", "ok")

    def _on_set_object(self):
        # Auto-grab a viewport too, so this works as a one-click step.
        if not self.core.model_panel:
            p = self.core.select_viewport(silent=True)
            if p:
                self._vp_label.setText(
                    f"{self.core.camera_for_panel()}  ({p})")
                self._vp_label.setStyleSheet("color:#ddd;")
                self._btn_single.setEnabled(True)

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
            if count > 0:
                self._set_status(
                    f"Target: {obj}  ({count} keys). Pick a preset to "
                    "ghost.", "ok")
            else:
                self._set_status(
                    f"Target: {obj} has no keyframes — only 'Ghost Current "
                    "Frame Only' will work.", "warn")

    def _update_bg_label(self):
        nodes = self.core.existing_background_nodes()
        if not nodes:
            self._bg_label.setText("None set")
            self._bg_label.setStyleSheet("color:#aaa;")
            self._btn_bg_vis.setEnabled(False)
            return
        names = [n.split("|")[-1] for n in nodes]
        shown = ", ".join(names[:3])
        if len(nodes) > 3:
            shown += f" (+{len(nodes) - 3} more)"
        self._bg_label.setText(shown)
        self._bg_label.setStyleSheet("color:#ddd;")
        self._btn_bg_vis.setEnabled(True)

    def _on_bg_add(self):
        count = self.core.set_background_from_selection()
        if count:
            self._update_bg_label()
            self._set_status(
                f"Background geo set ({count} node"
                f"{'s' if count != 1 else ''}). It will appear in "
                "isolated ghost captures.", "ok")
        else:
            self._set_status(
                "Nothing selected — select set/prop geometry first.", "warn")

    def _on_bg_clear(self):
        # Re-show the geo before forgetting it so nothing stays hidden
        if self.core.existing_background_nodes():
            for n in self.core.existing_background_nodes():
                try:
                    cmds.setAttr(f"{n}.visibility", 1)
                except Exception:
                    pass
        self.core.clear_background()
        self._update_bg_label()
        self._set_status("Background geo cleared.", "ok")

    def _on_bg_include_changed(self, checked):
        self.core.include_background = bool(checked)
        self.core.save_prefs()
        self._set_status(
            "Background geo will {}be included in isolated captures."
            .format("" if checked else "NOT "), "info")

    def _on_bg_toggle_vis(self):
        state = self.core.toggle_background_visibility()
        if state is None:
            self._set_status("No background geo set.", "warn")
        else:
            self._set_status(
                "Background geo " + ("shown." if state else "hidden."), "ok")

    def _on_isolate_changed(self):
        self.core.isolate_rig = self._isolate_cb.isChecked()
        self.core.save_prefs()
        if self.core.isolate_rig and self.core._rig_top_node:
            self._set_status(
                f"Isolate ON — rig root: {self.core._rig_top_node}", "info")
        else:
            self._set_status("Isolate OFF", "info")

    def _on_hier_changed(self, checked):
        self.core.include_hierarchy = bool(checked)
        self.core.save_prefs()
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
        ready = (not self._capturing
                 and self.core.model_panel is not None
                 and self.core.target_object is not None
                 and len(self.core._cached_keys) > 0)
        for btn in self._preset_buttons:
            btn.setEnabled(ready)
        self._btn_custom.setEnabled(ready)

    def _on_single_frame(self):
        if not self._begin_capture():
            return
        try:
            err = self.core.create_single_frame(self._on_capture_progress)
        finally:
            self._end_capture()
        self._rebuild_layer_list()
        self._refresh_state()
        if err:
            self._set_status(err, "err")
        else:
            self._set_status("Captured 1 frame.", "ok")

    def _on_preset(self, before, after):
        if not self._begin_capture():
            return
        inc_cur = self._include_cur_cb.isChecked()
        try:
            err = self.core.create_ghost_from_keys(
                before, after, inc_cur, self._on_capture_progress)
        finally:
            self._end_capture()

        if err:
            self._set_status(err, "err")
            self._rebuild_layer_list()
            self._refresh_state()
            return

        self._apply_opacity_gradient(rebuild=False)
        self._rebuild_layer_list()
        self._refresh_state()

        n = len(self.core.layers)
        frames_str = ", ".join(
            str(int(ly.frame)) for ly in self.core.layers)
        self._set_status(
            f"{n} layer{'s' if n != 1 else ''} at keys: {frames_str}", "ok")

    def _on_custom_preset(self):
        b = self._spin_before.value()
        a = self._spin_after.value()
        if b == 0 and a == 0 and not self._include_cur_cb.isChecked():
            self._set_status(
                "Nothing to capture — set Before/After above 0 or enable "
                "'Include Current Frame'.", "warn")
            return
        self._on_preset(b, a)

    def _on_delete_all(self):
        self.core.delete_all()
        self._rebuild_layer_list()
        self._refresh_state()
        self._set_status("All ghosts deleted (scene swept clean).", "ok")

    def _on_clean_temp(self):
        _clean_temp_files()
        self._set_status("Temp files cleaned.", "ok")

    def _on_refresh(self):
        if not self._begin_capture():
            return
        try:
            self.core.refresh_all(self._on_capture_progress)
        finally:
            self._end_capture()
        self._apply_opacity_gradient(rebuild=False)
        self._rebuild_layer_list()
        self._refresh_state()
        self._set_status("Refreshed all layers.", "ok")

    def _on_fix_offset(self):
        n = self.core.realign_all()
        self._set_status(
            f"Re-aligned {n} plane{'s' if n != 1 else ''} to the "
            "camera's rendered gate.", "ok")

    def _on_outline_toggled(self, checked):
        self.core.outline_mode = checked
        self._set_status(f"Outline {'ON' if checked else 'OFF'}", "info")

    def _force_viewport_refresh(self):
        """Cycle imagePlane display off/on to force Maya to redraw."""
        if self.core.model_panel:
            cmds.modelEditor(
                self.core.model_panel, edit=True, imagePlane=False)
            cmds.modelEditor(
                self.core.model_panel, edit=True, imagePlane=True)
            cmds.refresh(force=True)

    def _set_all_visible(self, vis):
        self._solo_index = None
        self.core.set_all_visible(vis)
        self._force_viewport_refresh()
        for item in self._layer_items:
            item.sync_from_layer()
        self._set_status("All " + ("shown." if vis else "hidden."), "ok")

    def _on_flip_ghost(self, step):
        layers = self.core.layers
        if not layers:
            return
        if self._solo_index is None or self._solo_index >= len(layers):
            self._solo_index = 0 if step > 0 else len(layers) - 1
        else:
            self._solo_index = (self._solo_index + step) % len(layers)
        self.core.solo_layer(self._solo_index)
        self._force_viewport_refresh()
        for item in self._layer_items:
            item.sync_from_layer()
        ly = layers[self._solo_index]
        self._set_status(
            f"Ghost {self._solo_index + 1}/{len(layers)}:  {ly.label()}",
            "info")

    def _on_layer_alpha(self, index, alpha):
        if 0 <= index < len(self.core.layers):
            self.core.layers[index].set_alpha(alpha)

    def _on_layer_delete(self, index):
        self.core.delete_layer(index)
        self._rebuild_layer_list()
        self._refresh_state()
        self._set_status("Layer deleted.", "ok")

    def _on_layer_vis(self, index, vis):
        if 0 <= index < len(self.core.layers):
            self.core.layers[index].set_visible(vis)
            self._force_viewport_refresh()

    def _on_near_opacity(self, val):
        self._near_lbl.setText(f"{val}%")
        self._apply_opacity_gradient()

    def _on_far_opacity(self, val):
        self._far_lbl.setText(f"{val}%")
        self._apply_opacity_gradient()

    # -- Opacity gradient --------------------------------------------------

    def _apply_opacity_gradient(self, rebuild=False):
        """Fade layers by their distance from the current-frame layer.
        Updates existing list rows in place so slider drags stay smooth."""
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
        else:
            max_dist = max(cur_idx, len(layers) - 1 - cur_idx, 1)
            for i, ly in enumerate(layers):
                dist = abs(i - cur_idx)
                if dist == 0:
                    ly.set_alpha(near)
                else:
                    t = dist / max_dist
                    alpha = near + (far - near) * t
                    ly.set_alpha(max(0.0, min(1.0, alpha)))

        if rebuild:
            self._rebuild_layer_list()
        else:
            for item in self._layer_items:
                item.sync_from_layer()

    # -- Layer list --------------------------------------------------------

    def _rebuild_layer_list(self):
        self._solo_index = None
        while self._layer_layout.count() > 0:
            item = self._layer_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._layer_items = []

        for i, layer in enumerate(self.core.layers):
            if not layer.exists():
                continue
            row = LayerItemWidget(i, layer)
            row.alpha_changed.connect(self._on_layer_alpha)
            row.delete_clicked.connect(self._on_layer_delete)
            row.vis_toggled.connect(self._on_layer_vis)
            self._layer_layout.addWidget(row)
            self._layer_items.append(row)

        self._layer_layout.addStretch()
        self._empty_hint.setVisible(not self._layer_items)

    def _refresh_state(self):
        has = self.core.has_layers()
        self._btn_refresh.setEnabled(has and not self._capturing)
        self._btn_delete_all.setEnabled(has)
        self._btn_show_all.setEnabled(has)
        self._btn_hide_all.setEnabled(has)
        self._btn_fix.setEnabled(has)
        self._btn_ghost_prev.setEnabled(has)
        self._btn_ghost_next.setEnabled(has)

    # -- About / Help ------------------------------------------------------

    def _on_about(self):
        QtWidgets.QMessageBox.about(
            self, f"Onion Skin v{__version__}",
            f"<h3>Onion Skin v{__version__}</h3>"
            "<p>Keyframe-aware multi-plane ghosting for Maya.</p><hr>"
            "<p><b>Original MEL (v0.8.3, 2007):</b><br>"
            "Syed Ali Ahsan &lt;yoda@cyber.net.pk&gt;</p>"
            f"<p><b>Python v{__version__} (2026):</b> Keyframe-based "
            "ghosting, per-layer alpha, up to 10 stacked planes, "
            "scene-safe cleanup that never leaves orphaned planes.</p>")

    def _on_help(self):
        QtWidgets.QMessageBox.information(
            self, "How to Use",
            "<h3>Quick Start</h3><ol>"
            "<li>Click a 3-D viewport → <b>Select Viewport</b> "
            "(auto-detected at launch when possible).</li>"
            "<li>Select an animated object → "
            "<b>Set from Selection</b>.</li>"
            "<li>Click a <b>preset</b> (±1 to ±5 Keys) to ghost that many "
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
            "<p><b>±1 Key</b> = 1 key before + 1 key after the current "
            "time<br>"
            "<b>±2 Keys</b> = 2 keys before + 2 keys after<br>"
            "...up to <b>±5 Keys</b> (capped at 10 layers — the keys "
            "furthest from the current time are dropped).</p>"
            "<p>Use <b>Custom</b> for asymmetric counts and "
            "<b>Include Current Frame</b> to also ghost the pose at the "
            "playhead.</p>"
            "<h3>Background Geo</h3>"
            "<p>Select set/prop geometry and press <b>Add Selected</b>. "
            "When 'Isolate Rig During Capture' is on, that geometry is "
            "kept in the captured images for spatial context. "
            "<b>Hide / Show in Viewport</b> toggles it in the live view "
            "so ghosts read clearly.</p>"
            "<h3>Layer List</h3>"
            "<p><span style='color:#5588cc'>● Blue</span> = before, "
            "<span style='color:#66cc66'>● Green</span> = current, "
            "<span style='color:#cc6655'>● Red</span> = after.<br>"
            "Each layer: visibility toggle, opacity slider, delete.<br>"
            "<b>Flip Ghosts</b> shows one plane at a time (Prev/Next, "
            "wraps around); <b>Show All</b> brings every ghost back.</p>"
            "<h3>Session Memory</h3>"
            "<p>The target rig, background geo, and capture toggles are "
            "saved with the scene and restored when the window reopens. "
            "Replace them any time with <b>Set from Selection</b> / "
            "<b>Add Selected</b>.</p>"
            "<h3>Display Options</h3>"
            "<p><b>Near/Far Opacity</b> auto-fades layers by distance.<br>"
            "<b>Re-Align Planes</b> re-pins every ghost to the camera's "
            "rendered gate if the size or position drifts (e.g. after "
            "changing camera settings).</p>"
            "<h3>Cleanup</h3>"
            "<p><b>Delete All</b> removes every ghost image plane from "
            "the scene — including any left over from a previous "
            "session or an interrupted capture. Leftover ghosts are also "
            "adopted back into the layer list when the tool launches.</p>")


# ---------------------------------------------------------------------------
def launch():
    if cmds.workspaceControl(_WIN, exists=True):
        cmds.deleteUI(_WIN)
    cmds.workspaceControl(
        _WIN, label=f"Onion Skin v{__version__}",
        floating=True, initialWidth=440, initialHeight=560,
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
