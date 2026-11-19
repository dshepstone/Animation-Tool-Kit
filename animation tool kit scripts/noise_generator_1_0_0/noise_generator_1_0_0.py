"""
Curve Noise Generator - Maya Animation Curve Tool
===================================================
Floating Maya tool window for animation curve manipulation:
  - Bake on 1's / 2's / 3's / 4's
  - Noise slider: alternating zigzag on selected keys
      Positive = +/- zigzag pattern
      Negative = random noise pattern
      Optional taper checkbox to diminish across selection
  - Noise Build slider: gradually growing noise for flat/static curves
      Positive = building zigzag wave (0 at edges, full in middle)
      Negative = building random noise (0 at edges, full in middle)
      First and last selected keys stay at original value.
  - Scale slider: scale selected key values up or down
      Positive = amplify values away from baseline
      Negative = compress values toward baseline
      First and last selected keys stay at original value.
  - Ease slider: taper selected keys toward the neighboring unselected key
      Positive = ease-out (taper toward the next key after selection)
      Negative = ease-in  (taper toward the previous key before selection)
  - Ease Both slider: combined ease-in + ease-out
      Positive = amplify / overshoot (push away from baseline)
      Negative = settle / dampen (pull both ends toward neighbors)
  - Channel filter checkboxes (TX TY TZ RX RY RZ) to restrict
    which curves bake / noise / ease operate on.

Sliders snap back to centre on release.  Cache is released after
each operation so the next drag starts fresh.  Each slider also has
a value field: type an exact amount and press Enter to apply it as
a single undoable operation.

Author : Claude (Anthropic)
Requires: Autodesk Maya 2020+ (PySide2 or PySide6)
Usage  :
    import noise_generator_1_0_0
    noise_generator_1_0_0.launch()

Version history:
    1.2.0 - Bake fills between the two selected keys without touching them
            and only bakes curves with selected keys. "Select inbetweens
            after bake" selects just the new inbetweens.
            New PIN NOISE slider: noise on the inbetweens with "Pin start
            key" / "Pin end key" checkboxes that fade the noise into the
            unselected start/end keys (which never move).
            New EASE IN / EASE OUT sliders: re-time the selected keys with
            a slow (right) or fast (left) start / finish between the
            unselected start/end keys.
    1.1.0 - Qt UI rebuilt to match the Inbetweener tool's slider styling
            (pill track, accent ticks, labeled handle, live readout).
            Value fields now actually apply the effect (previously they
            only moved the slider thumb).  Channel filter now resolves
            the driven attribute from downstream connections only.
            Window sized to fit all sliders without a forced scrollbar.
    1.0.0 - Initial release (maya.cmds workspaceControl UI).
"""

from __future__ import division, print_function
import math
import random
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui

VERSION = "1.2.0"
TITLE = "Curve Noise Generator"

# Legacy maya.cmds UI names (deleted on launch if a 1.0.0 window remains)
_LEGACY_WIN = "cng_win"
_LEGACY_WORKSPACE = "cng_workspaceControl"

DEF_MIN  = -10.0
DEF_MAX  =  10.0
ABS_MIN  =   0.1
ABS_MAX  = 150.0


# ============================================================================
# QT COMPATIBILITY LAYER (matches the Inbetweener tool)
# ============================================================================

def _import_qt_modules():
    """Resolve the Qt bindings bundled with the current Maya session."""
    binding_attempts = (
        ("PySide6", "shiboken6"),
        ("PySide6", "shiboken2"),
        ("PySide2", "shiboken2"),
        ("PySide2", "shiboken6"),
    )

    last_error = None
    for qt_mod_name, shiboken_name in binding_attempts:
        try:
            qt_mod = __import__(qt_mod_name, fromlist=["QtCore", "QtGui", "QtWidgets"])
            shiboken_mod = __import__(shiboken_name)
        except ImportError as exc:
            last_error = exc
            continue

        try:
            qt_core = getattr(qt_mod, "QtCore")
            qt_gui = getattr(qt_mod, "QtGui")
            qt_widgets = getattr(qt_mod, "QtWidgets")
        except AttributeError as exc:
            last_error = exc
            continue

        return qt_core, qt_gui, qt_widgets, shiboken_mod

    raise ImportError(
        "Curve Noise Generator requires PySide2/PySide6 with shiboken"
        " (last error: {})".format(last_error))


QtCore, QtGui, QtWidgets, shiboken = _import_qt_modules()


# ===================================================================
#  Channel filter helpers
# ===================================================================

def _get_curve_attr(crv):
    """Return the attribute name an anim curve drives (e.g. 'translateX')."""
    conns = cmds.listConnections(crv + ".output", plugs=True,
                                 source=False, destination=True) or []
    if not conns:
        return ""
    plug = conns[0]
    if "." in plug:
        return plug.split(".")[-1]
    return ""


def _filter_curves(curves, allowed):
    """Filter a list of anim-curve names, keeping only those whose
    output attribute is in *allowed*.  If allowed is None, keep all."""
    if allowed is None:
        return list(curves)
    out = []
    for crv in curves:
        a = _get_curve_attr(crv)
        if a in allowed:
            out.append(crv)
    return out


# ===================================================================
#  Key cache
# ===================================================================
class KeyCache(object):
    """Snapshot of selected keys for non-destructive editing."""

    def __init__(self):
        self.clear()

    def clear(self):
        self.curves  = []
        self.indices = {}
        self.times   = {}
        self.values  = {}
        self.nkeys   = 0
        self.ncurves = 0
        self.rsigns  = {}
        self.ramps   = {}
        self.prev_key = {}
        self.next_key = {}
        self.prev_time = {}
        self.next_time = {}
        self.prev_index = {}
        self.next_index = {}

    def capture(self, attr_filter=None):
        self.clear()

        ge = cmds.keyframe(q=True, name=True, selected=True) or []
        if ge:
            if attr_filter is not None:
                ge = _filter_curves(ge, attr_filter)
            for crv in ge:
                ix = cmds.keyframe(crv, q=True, indexValue=True, selected=True) or []
                if not ix:
                    continue
                ix = [int(i) for i in ix]
                tt = cmds.keyframe(crv, q=True, timeChange=True, selected=True) or []
                vv = cmds.keyframe(crv, q=True, valueChange=True, selected=True) or []
                if len(tt) != len(ix) or len(vv) != len(ix):
                    continue
                self.curves.append(crv)
                self.indices[crv] = ix
                self.times[crv]   = list(tt)
                self.values[crv]  = list(vv)
                self.nkeys += len(ix)
            if self.curves:
                self.ncurves = len(self.curves)
                self._gen_random()
                return True

        sel = cmds.ls(sl=True) or []
        if not sel:
            return False
        ac = set()
        for o in sel:
            ac.update(cmds.keyframe(o, q=True, name=True) or [])
        if not ac:
            return False

        if attr_filter is not None:
            ac = set(_filter_curves(sorted(ac), attr_filter))

        tr = _tl_range()
        for crv in sorted(ac):
            ix = cmds.keyframe(crv, q=True, indexValue=True,
                               time=(tr[0], tr[1])) or []
            if not ix:
                continue
            ix = [int(i) for i in ix]
            tt = cmds.keyframe(crv, q=True, timeChange=True,
                               time=(tr[0], tr[1])) or []
            vv = cmds.keyframe(crv, q=True, valueChange=True,
                               time=(tr[0], tr[1])) or []
            if len(tt) != len(ix) or len(vv) != len(ix):
                continue
            self.curves.append(crv)
            self.indices[crv] = ix
            self.times[crv]   = list(tt)
            self.values[crv]  = list(vv)
            self.nkeys += len(ix)

        self.ncurves = len(self.curves)
        if self.nkeys:
            self._gen_random()
        return self.nkeys > 0

    def _gen_random(self):
        rng = random.Random()
        self.rsigns = {}
        self.ramps  = {}
        for crv in self.curves:
            n = len(self.indices[crv])
            self.rsigns[crv] = [1.0 if rng.random() > 0.5 else -1.0 for _ in range(n)]
            self.ramps[crv]  = [rng.uniform(0.3, 1.0) for _ in range(n)]
        self._find_neighbors()

    def _find_neighbors(self):
        self.prev_key = {}
        self.next_key = {}
        self.prev_time = {}
        self.next_time = {}
        self.prev_index = {}
        self.next_index = {}
        for crv in self.curves:
            sel_indices = self.indices[crv]
            first_idx = sel_indices[0]
            last_idx  = sel_indices[-1]

            if first_idx > 0:
                prev_idx = first_idx - 1
                v = cmds.keyframe(crv, q=True, index=(prev_idx, prev_idx),
                                  valueChange=True)
                t = cmds.keyframe(crv, q=True, index=(prev_idx, prev_idx),
                                  timeChange=True)
                if v and t:
                    self.prev_key[crv] = v[0]
                    self.prev_time[crv] = t[0]
                    self.prev_index[crv] = prev_idx

            next_idx = last_idx + 1
            v = cmds.keyframe(crv, q=True, index=(next_idx, next_idx),
                              valueChange=True)
            t = cmds.keyframe(crv, q=True, index=(next_idx, next_idx),
                              timeChange=True)
            if v and t:
                self.next_key[crv] = v[0]
                self.next_time[crv] = t[0]
                self.next_index[crv] = next_idx

    def ok(self):
        return self.nkeys > 0


# ===================================================================
#  Helpers
# ===================================================================

def _tl_range():
    sl = mel.eval('$__tmp = $gPlayBackSlider')
    hl = cmds.timeControl(sl, q=True, rangeArray=True)
    if hl and len(hl) >= 2:
        s, e = float(hl[0]), float(hl[1])
        if (e - s) > 1.0:
            return (s, e - 1.0)
    return (cmds.playbackOptions(q=True, minTime=True),
            cmds.playbackOptions(q=True, maxTime=True))

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ===================================================================
#  Bake
# ===================================================================

_EPS = 1e-3


def _bake_targets(allowed):
    """Return {curve: (start_time, end_time)} to bake.

    Graph Editor keys selected: bake only the curves that have selected
    keys, each between its own first and last selected key (normally the
    two keys you picked).  Nothing selected in the Graph Editor: bake
    every curve of the selected objects over the timeline range.
    """
    ranges = {}
    ge = cmds.keyframe(q=True, name=True, selected=True) or []
    if ge:
        for crv in _filter_curves(ge, allowed):
            tt = cmds.keyframe(crv, q=True, selected=True, timeChange=True) or []
            if tt:
                ranges[crv] = (float(min(tt)), float(max(tt)))
        return ranges

    ac = set()
    for o in cmds.ls(sl=True) or []:
        ac.update(cmds.keyframe(o, q=True, name=True) or [])
    tr = _tl_range()
    for crv in _filter_curves(sorted(ac), allowed):
        ranges[crv] = (float(tr[0]), float(tr[1]))
    return ranges


def bake(interval, allowed=None, preselect=False, quiet=False):
    """Fill the range between two keys with inbetweens every *interval*
    frames, sampled from the current curve.

    The keys at both ends of the range are kept exactly as they are
    (value and time) - only the keys strictly between them are replaced.
    New inbetweens are marked as breakdowns.

    *allowed* is an optional set of attribute names (e.g. {'translateX'})
    used to restrict which curves are baked; None means all curves.

    *preselect*: when True, only the new inbetweens are selected in the
    Graph Editor afterwards (the two end keys are left unselected), ready
    for Pin Noise / Ease In / Ease Out.
    """
    if not cmds.ls(sl=True) and not cmds.keyframe(q=True, name=True,
                                                   selected=True):
        cmds.warning("CNG: Nothing selected."); return
    targets = _bake_targets(allowed)
    if not targets:
        cmds.warning("CNG: No curves to bake (check the channel boxes)."); return

    baked = []
    cmds.undoInfo(openChunk=True, chunkName="Bake on {}'s".format(interval))
    try:
        for crv in sorted(targets):
            st, et = targets[crv]
            if et - st <= _EPS:
                continue

            frames = []
            f = st + interval
            while f < et - _EPS:
                frames.append(f)
                f += interval

            def _ev(t):
                v = cmds.keyframe(crv, q=True, time=(t, t), eval=True,
                                  valueChange=True)
                return v[0] if v else None

            # Sample everything before touching the curve
            samples = [(fr, _ev(fr)) for fr in frames]
            ends = [(st, _ev(st)), (et, _ev(et))]

            # Range ends must be keys (timeline-range bakes); existing
            # end keys are never touched.
            for bt, bv in ends:
                if bv is not None and not cmds.keyframe(
                        crv, q=True, time=(bt, bt), timeChange=True):
                    cmds.setKeyframe(crv, time=bt, value=bv)

            cmds.cutKey(crv, time=(st + _EPS, et - _EPS), clear=True)
            for fr, v in samples:
                if v is not None:
                    cmds.setKeyframe(crv, time=fr, value=v)

            # Inbetweens get auto tangents.  The start/end keys keep their
            # tangents, except a stepped side facing the inbetweens (from
            # blocking), which would hold the value and pop.
            for fr, _v in samples:
                cmds.keyTangent(crv, time=(fr, fr), itt="auto", ott="auto")
            for bt, flag in ((st, "ott"), (et, "itt")):
                try:
                    cur = cmds.keyTangent(crv, q=True, time=(bt, bt),
                                          **{flag: True}) or []
                    if cur and cur[0] in ("step", "stepnext"):
                        cmds.keyTangent(crv, time=(bt, bt), **{flag: "auto"})
                except Exception:
                    pass
            for fr, _v in samples:
                cmds.keyframe(crv, time=(fr, fr), tickDrawSpecial=True)
                cmds.keyframe(crv, time=(fr, fr), breakdown=True)
            for bt in (st, et):
                try:
                    cmds.keyframe(crv, time=(bt, bt), tickDrawSpecial=False)
                    cmds.keyframe(crv, time=(bt, bt), breakdown=False)
                except Exception:
                    pass
            baked.append((crv, st, et))

        if not baked:
            cmds.warning("CNG: Nothing to bake - select two keys with a gap.")
            return []
        if len(baked) == 1:
            msg = "<hl>Baked on {}'s</hl>  ({:g}-{:g})".format(
                interval, baked[0][1], baked[0][2])
        else:
            msg = "<hl>Baked on {}'s</hl>  ({} curves)".format(
                interval, len(baked))
        if preselect:
            n_sel = _select_inbetweens(baked)
            msg += "  - {} inbetween(s) selected".format(n_sel)
        if not quiet:
            cmds.inViewMessage(amg=msg, pos="midCenter", fade=True)
        return baked
    except Exception as e:
        cmds.warning("Bake error: {}".format(e))
        return []
    finally:
        cmds.undoInfo(closeChunk=True)


def _select_inbetweens(baked):
    """Select only the keys strictly between each baked range's end keys.
    Returns the number of keys selected."""
    cmds.selectKey(clear=True)
    count = 0
    for crv, st, et in baked:
        if et - st <= 2 * _EPS:
            continue
        try:
            cmds.selectKey(crv, add=True, keyframe=True,
                           time=(st + _EPS, et - _EPS))
        except Exception:
            continue
        count += len(cmds.keyframe(crv, q=True, selected=True,
                                   indexValue=True) or [])
    return count


# ===================================================================
#  Noise -- direct value offset
# ===================================================================

def apply_noise(cache, slider_val, taper=False):
    """
    Apply noise to keys. The slider value IS the offset amount
    in the attribute's own units -- drag to 5 and keys move +/-5.

    Positive: strict alternating zigzag  +, -, +, -
    Negative: random pattern with varying amplitudes

    If taper=True, amplitude diminishes across the selection:
      positive slider -> big at start, small at end
      negative slider -> small at start, big at end
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    mag = abs(slider_val)

    for crv in cache.curves:
        orig = cache.values[crv]
        idxs = cache.indices[crv]
        n    = len(idxs)

        for i, idx in enumerate(idxs):
            # Taper factor (1.0 = full, 0.0 = none)
            if taper and n > 1:
                t = i / float(n - 1)
                if slider_val > 0:
                    tf = math.sqrt(1.0 - t)   # big start, small end
                else:
                    tf = math.sqrt(t)          # small start, big end
            else:
                tf = 1.0

            if slider_val > 0:
                # Strict alternating zigzag
                sign = 1.0 if (i % 2 == 0) else -1.0
                offset = sign * mag * tf
            else:
                # Random noise
                rs = cache.rsigns.get(crv, [1.0] * n)
                ra = cache.ramps.get(crv,  [1.0] * n)
                offset = rs[i] * ra[i] * mag * tf

            cmds.keyframe(crv, index=(idx, idx),
                          valueChange=orig[i] + offset, absolute=True)


def _write_base(cache):
    for crv in cache.curves:
        for i, idx in enumerate(cache.indices[crv]):
            cmds.keyframe(crv, index=(idx, idx),
                          valueChange=cache.values[crv][i], absolute=True)


# ===================================================================
#  Noise Build -- gradually growing noise, edges pinned
# ===================================================================

def apply_noise_build(cache, slider_val):
    """
    Noise that builds up gradually from zero at the first and last
    selected keys to full amplitude in the middle.  Designed for
    static / flat curves where you want noise to grow organically.

    Positive: building zigzag wave  +, -, +, -
    Negative: building random noise

    The envelope is sin(pi * t) so both the first and last selected
    keys stay at their original value and the peak amplitude is in
    the centre of the selection.
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    mag = abs(slider_val)

    for crv in cache.curves:
        orig = cache.values[crv]
        idxs = cache.indices[crv]
        n    = len(idxs)

        for i, idx in enumerate(idxs):
            # Pin first and last keys
            if i == 0 or i == n - 1:
                cmds.keyframe(crv, index=(idx, idx),
                              valueChange=orig[i], absolute=True)
                continue

            # Envelope: 0 at edges, 1 in the middle
            if n > 2:
                t = i / float(n - 1)
                envelope = math.sin(math.pi * t)
            else:
                envelope = 1.0

            if slider_val > 0:
                sign = 1.0 if (i % 2 == 0) else -1.0
                offset = sign * mag * envelope
            else:
                rs = cache.rsigns.get(crv, [1.0] * n)
                ra = cache.ramps.get(crv,  [1.0] * n)
                offset = rs[i] * ra[i] * mag * envelope

            cmds.keyframe(crv, index=(idx, idx),
                          valueChange=orig[i] + offset, absolute=True)


# ===================================================================
#  Scale -- scale key values up or down, edges pinned
# ===================================================================

def apply_scale(cache, slider_val, smin, smax, both_sides=False):
    """
    Scale the value of each selected key up or down relative to the
    baseline (linear interpolation between the first and last
    selected key values).

    First and last selected keys always stay at their original value.

    Positive slider: amplify -- push values away from baseline.
        factor goes from 1.0 (no change) up to 3.0 at full slider.
    Negative slider: compress -- pull values toward baseline.
        factor goes from 1.0 (no change) down to 0.0 at full slider.

    both_sides: when True, the scale factor is shaped by a bell
        envelope (sin(pi*t)) so the effect tapers at both the start
        and end of the selection, peaking in the middle.  When False,
        the scale factor is applied uniformly to all interior keys.
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    rng = abs(smin) if slider_val < 0 else abs(smax)
    normalized = abs(slider_val) / max(rng, 0.001)
    normalized = _clamp(normalized, 0.0, 1.0)

    if slider_val > 0:
        factor = 1.0 + normalized * 2.0   # 1.0 -> 3.0
    else:
        factor = 1.0 - normalized          # 1.0 -> 0.0

    for crv in cache.curves:
        vv  = cache.values[crv]
        idx = cache.indices[crv]
        n   = len(vv)

        if n < 2:
            continue

        # Baseline: lerp between first and last selected key
        first_v = vv[0]
        last_v  = vv[-1]

        for i, ix in enumerate(idx):
            # Pin first and last keys
            if i == 0 or i == n - 1:
                cmds.keyframe(crv, index=(ix, ix),
                              valueChange=vv[i], absolute=True)
                continue

            t = i / float(n - 1)
            baseline = first_v + (last_v - first_v) * t
            deviation = vv[i] - baseline

            if both_sides:
                # Bell envelope: 0 at edges, 1 in the middle
                env = math.sin(math.pi * t)
                # Blend between no-scale (1.0) at edges and full factor in middle
                local_factor = 1.0 + (factor - 1.0) * env
            else:
                local_factor = factor

            new_v = baseline + deviation * local_factor

            cmds.keyframe(crv, index=(ix, ix),
                          valueChange=new_v, absolute=True)


# ===================================================================
#  Ease
# ===================================================================

def apply_ease(cache, slider_val, smin, smax):
    """
    Pull selected keys toward the neighbor key value, shaped by the
    classic power-curve ease envelope.

    Positive slider -> ease-out : target = NEXT neighbor key.
    Negative slider -> ease-in  : target = PREVIOUS neighbor key.
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    rng = abs(smin) if slider_val < 0 else abs(smax)
    normalized = abs(slider_val) / max(rng, 0.001)
    normalized = _clamp(normalized, 0.0, 1.0)

    strength = 0.25 + normalized * 3.0

    for crv in cache.curves:
        vv  = cache.values[crv]
        idx = cache.indices[crv]
        tt  = cache.times[crv]
        n   = len(vv)

        if n < 1:
            continue

        has_prev = crv in cache.prev_key
        has_next = crv in cache.next_key

        if has_prev:
            prev_val = cache.prev_key[crv]
            prev_t   = cache.prev_time[crv]
        else:
            prev_val = vv[0]
            prev_t   = tt[0]

        if has_next:
            next_val = cache.next_key[crv]
            next_t   = cache.next_time[crv]
        else:
            next_val = vv[-1]
            next_t   = tt[-1]

        time_range = next_t - prev_t

        if time_range <= 0.0:
            for i, ix in enumerate(idx):
                cmds.keyframe(crv, index=(ix, ix),
                              valueChange=vv[i], absolute=True)
            continue

        if slider_val > 0:
            target = next_val
        else:
            target = prev_val

        for i, ix in enumerate(idx):
            t = (tt[i] - prev_t) / time_range
            t = _clamp(t, 0.0, 1.0)

            if slider_val > 0:
                envelope = 1.0 - pow(abs(1.0 - t), strength)
            else:
                envelope = 1.0 - pow(t, strength)

            pull = envelope * pow(normalized, 0.8)
            pull = pow(pull, 0.7)
            pull = pull + (1.0 - pull) * pow(envelope, 60.0) * normalized

            new_v = vv[i] + (target - vv[i]) * pull

            cmds.keyframe(crv, index=(ix, ix),
                          valueChange=new_v, absolute=True)


# ===================================================================
#  Ease Both (combined ease-in + ease-out)
# ===================================================================

def apply_ease_both(cache, slider_val, smin, smax):
    """
    NEGATIVE (settle / dampen): pull both ends toward neighbors.
    POSITIVE (amplify / overshoot): push away from baseline.
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    rng = abs(smin) if slider_val < 0 else abs(smax)
    normalized = abs(slider_val) / max(rng, 0.001)
    normalized = _clamp(normalized, 0.0, 1.0)

    strength = 0.25 + normalized * 3.0

    for crv in cache.curves:
        vv  = cache.values[crv]
        idx = cache.indices[crv]
        tt  = cache.times[crv]
        n   = len(vv)

        if n < 1:
            continue

        has_prev = crv in cache.prev_key
        has_next = crv in cache.next_key

        if has_prev:
            prev_val = cache.prev_key[crv]
            prev_t   = cache.prev_time[crv]
        else:
            prev_val = vv[0]
            prev_t   = tt[0]

        if has_next:
            next_val = cache.next_key[crv]
            next_t   = cache.next_time[crv]
        else:
            next_val = vv[-1]
            next_t   = tt[-1]

        time_range = next_t - prev_t

        if time_range <= 0.0:
            for i, ix in enumerate(idx):
                cmds.keyframe(crv, index=(ix, ix),
                              valueChange=vv[i], absolute=True)
            continue

        for i, ix in enumerate(idx):
            t = (tt[i] - prev_t) / time_range
            t = _clamp(t, 0.0, 1.0)

            if slider_val < 0:
                env_in  = pow(abs(1.0 - t), strength)
                env_out = pow(t, strength)

                pull_in  = env_in  * pow(normalized, 0.8)
                pull_in  = pow(pull_in, 0.7)
                pull_in  = pull_in + (1.0 - pull_in) * pow(env_in, 60.0) * normalized

                pull_out = env_out * pow(normalized, 0.8)
                pull_out = pow(pull_out, 0.7)
                pull_out = pull_out + (1.0 - pull_out) * pow(env_out, 60.0) * normalized

                new_v = vv[i] + (prev_val - vv[i]) * pull_in \
                               + (next_val - vv[i]) * pull_out

            else:
                baseline = prev_val + (next_val - prev_val) * t
                deviation = vv[i] - baseline
                bell = math.sin(math.pi * t)
                bell = pow(bell, max(0.3, 1.0 - normalized * 0.7))
                amp = bell * normalized * 3.0
                new_v = vv[i] + deviation * amp

            cmds.keyframe(crv, index=(ix, ix),
                          valueChange=new_v, absolute=True)


# ===================================================================
#  Pin Noise -- noise on the inbetweens, start and/or end key pinned
# ===================================================================

def _pin_envelope(u, pin_start, pin_end, decay=False):
    """Noise envelope from the start key (u = 0) to the end key (u = 1).
    A pinned end fades the noise to zero there.

    decay: impact-style falloff - full strength at the start, dying away
    quickly and reaching zero at the end key.  Pin start then only adds a
    very short fade-in so the first frame does not pop.
    """
    if decay:
        env = pow(1.0 - u, 2.5)
        if pin_start:
            env *= math.sin(0.5 * math.pi * min(1.0, u / 0.12))
        return env
    if pin_start and pin_end:
        return math.sin(math.pi * u)
    if pin_start:
        return math.sin(0.5 * math.pi * u)
    if pin_end:
        return math.sin(0.5 * math.pi * (1.0 - u))
    return 1.0


def _anchored_track(cache, crv):
    """Times/values of the selected keys with the unselected key just
    before and just after the selection added as fixed anchors.

    Returns (times, values, first) where *first* is the position of the
    first selected key in the returned lists (1 if a previous key was
    added, else 0).  With only inbetweens selected, the anchors are the
    two original keys the inbetweens were baked between.
    """
    tt = list(cache.times[crv])
    vv = list(cache.values[crv])
    first = 0
    if crv in cache.prev_key:
        tt.insert(0, cache.prev_time[crv])
        vv.insert(0, cache.prev_key[crv])
        first = 1
    if crv in cache.next_key:
        tt.append(cache.next_time[crv])
        vv.append(cache.next_key[crv])
    return tt, vv, first


def apply_pin_noise(cache, slider_val, pin_start=True, pin_end=True,
                    decay=False):
    """
    Noise on the selected inbetweens.  The slider value is the offset in
    the attribute's own units (like NOISE).

    Positive: alternating zigzag  +, -, +, -
    Negative: random noise

    Only the selected keys are ever written, so the unselected start and
    end keys (the two keys the inbetweens were baked between) never move.

    pin_start: noise fades in from the start key (zero at the start key).
    pin_end:   noise fades out into the end key (zero at the end key).
    Neither:   full-strength noise on every selected key.

    If nothing comes before/after the selection on a curve, the first/last
    selected key acts as the start/end key and is held when pinned.
    The fade is based on key time, so it stays even on 1's, 2's, etc.
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    mag = abs(slider_val)

    for crv in cache.curves:
        orig = cache.values[crv]
        idxs = cache.indices[crv]
        n    = len(idxs)
        at, _av, first = _anchored_track(cache, crv)
        a0, a1 = at[0], at[-1]
        span = a1 - a0

        for i, idx in enumerate(idxs):
            u = (cache.times[crv][i] - a0) / span if span > 0.0 else 0.5
            u = _clamp(u, 0.0, 1.0)
            # Selected key that is itself the anchor (nothing beyond it)
            held = ((pin_start and first == 0 and i == 0) or
                    ((pin_end or decay) and len(at) == first + n
                     and i == n - 1))
            if held:
                cmds.keyframe(crv, index=(idx, idx),
                              valueChange=orig[i], absolute=True)
                continue

            env = _pin_envelope(u, pin_start, pin_end, decay)

            if slider_val > 0:
                sign = 1.0 if (i % 2 == 0) else -1.0
                offset = sign * mag * env
            else:
                rs = cache.rsigns.get(crv, [1.0] * n)
                ra = cache.ramps.get(crv,  [1.0] * n)
                offset = rs[i] * ra[i] * mag * env

            cmds.keyframe(crv, index=(idx, idx),
                          valueChange=orig[i] + offset, absolute=True)


# Tangent types whose angle Maya recomputes from the neighbouring keys.
_NEIGHBOUR_TANGENTS = ("auto", "spline", "clamped", "plateau", "linear",
                       "autoMix", "autoEase", "autoCustom")


def snapshot_anchors(cache):
    """Record the value and tangents of the unselected start/end keys so
    restore_anchors() can hold them exactly while a slider is dragged."""
    snap = []
    for crv in cache.curves:
        for idx_map in (cache.prev_index, cache.next_index):
            if crv not in idx_map:
                continue
            i = idx_map[crv]
            try:
                t = cmds.keyframe(crv, q=True, index=(i, i), timeChange=True)
                v = cmds.keyframe(crv, q=True, index=(i, i), valueChange=True)
                ang = cmds.keyTangent(crv, q=True, index=(i, i),
                                      inAngle=True, outAngle=True)
            except Exception:
                continue
            if t and v:
                snap.append((crv, i, t[0], v[0], ang))
    return snap


def restore_anchors(snap):
    """Put the start/end keys back exactly as snapshot_anchors() found
    them (only touches a key whose value actually changed)."""
    for crv, i, t, v, ang in snap:
        try:
            cur = cmds.keyframe(crv, q=True, time=(t, t), valueChange=True)
            if cur and abs(cur[0] - v) > 1e-9:
                cmds.keyframe(crv, time=(t, t), valueChange=v, absolute=True)
        except Exception:
            pass


def describe_anchors(cache):
    """One line per curve for the Script Editor: what is being edited and
    which keys are held."""
    out = []
    for crv in cache.curves:
        tt = cache.times[crv]
        s = cache.prev_time.get(crv)
        e = cache.next_time.get(crv)
        out.append("{}: {} key(s) {:g}-{:g}, start key {}, end key {}".format(
            crv, len(tt), tt[0], tt[-1],
            "{:g}".format(s) if s is not None else "(none)",
            "{:g}".format(e) if e is not None else "(none)"))
    return out


def lock_anchor_tangents(cache):
    """Freeze the tangents of the unselected start/end keys (the keys just
    before and after the selection).

    Auto/spline/clamped/linear tangents are recalculated from neighbouring
    keys, so moving the inbetweens would swing the start/end key tangents
    and bend the curve through and beyond them.  Switching them to "fixed"
    keeps their current angle.  Call inside the slider's undo chunk.
    """
    for crv in cache.curves:
        for idx_map in (cache.prev_index, cache.next_index):
            if crv not in idx_map:
                continue
            i = idx_map[crv]
            for flag in ("itt", "ott"):
                try:
                    cur = cmds.keyTangent(crv, q=True, index=(i, i),
                                          **{flag: True}) or []
                    if cur and cur[0] in _NEIGHBOUR_TANGENTS:
                        cmds.keyTangent(crv, index=(i, i), **{flag: "fixed"})
                except Exception:
                    pass


# ===================================================================
#  Ease In / Ease Out -- retime the selected values with an ease curve
# ===================================================================

def _sample_linear(tt, vv, t):
    """Piecewise-linear sample of the cached (time, value) keys at t."""
    if t <= tt[0]:
        return vv[0]
    if t >= tt[-1]:
        return vv[-1]
    for i in range(1, len(tt)):
        if t <= tt[i]:
            t0, t1 = tt[i - 1], tt[i]
            if t1 <= t0:
                return vv[i]
            f = (t - t0) / (t1 - t0)
            return vv[i - 1] + (vv[i] - vv[i - 1]) * f
    return vv[-1]


def apply_ease_in_out(cache, slider_val, smin, smax, side):
    """
    Re-time the motion across the selected keys with an ease curve.  Each
    key takes the value the original motion had at an eased time, so the
    shape (including any noise) is kept but its spacing changes.

    The ease runs from the start key to the end key (the unselected keys
    just before and after the selection), which never move.  If nothing
    comes before/after the selection, the first/last selected key is used
    and stays put.

    side == "in"  (EASE IN):  right = slow start (eases out of the start
                              key), left = fast start.
    side == "out" (EASE OUT): right = slow finish (eases into the end
                              key), left = fast finish.
    """
    if not cache.ok():
        return
    if slider_val == 0.0:
        _write_base(cache)
        return

    rng = abs(smin) if slider_val < 0 else abs(smax)
    normalized = _clamp(abs(slider_val) / max(rng, 0.001), 0.0, 1.0)

    power = 1.0 + normalized * 3.0      # 1 -> 4
    if slider_val < 0:
        power = 1.0 / power             # 1 -> 0.25 (opposite ease)

    for crv in cache.curves:
        idx = cache.indices[crv]
        tt  = cache.times[crv]
        at, av, _first = _anchored_track(cache, crv)
        if len(at) < 3:
            continue
        t0, t1 = at[0], at[-1]
        span = t1 - t0
        if span <= 0.0:
            continue

        for i, ix in enumerate(idx):
            u = _clamp((tt[i] - t0) / span, 0.0, 1.0)
            if side == "in":
                w = pow(u, power)
            else:
                w = 1.0 - pow(1.0 - u, power)
            new_v = _sample_linear(at, av, t0 + w * span)
            cmds.keyframe(crv, index=(ix, ix),
                          valueChange=new_v, absolute=True)


# ===================================================================
#  Presets -- one-click recipes built from Bake + Ease + Pin Noise
# ===================================================================

# name, bake interval, pattern (+1 zigzag / -1 random), amount factor,
# pin start, pin end, decay, ease (side, slider value) or None, description
PRESETS = (
    ("Camera Shake", 1, -1, 1.0, True, True, False, None,
     "Random jitter on 1's that fades in from the start key and out into "
     "the end key. Use on the camera's rotate X / Y (and Z)."),
    ("Handheld", 3, -1, 0.6, True, True, False, None,
     "Slower, softer random drift on 3's for a handheld camera feel."),
    ("Impact Hit", 1, 1, 1.0, True, False, True, None,
     "A hard hit: strong rattle right after the start key that dies away "
     "into the end key."),
    ("Skid to Stop", 1, 1, 0.5, False, False, True, ("out", 6.0),
     "Slows into the end key (Ease Out) with chatter that dies away as it "
     "stops. Use on the travel channel, plus rotate for a wobble."),
    ("Settle Wobble", 2, 1, 1.0, False, False, True, ("out", 3.0),
     "Back-and-forth wobble on 2's that settles into the end key."),
    ("Rumble Build", 1, -1, 1.0, True, False, False, None,
     "Shake that grows from nothing at the start key to full strength at "
     "the end key (earthquake, engine starting)."),
)


def run_preset(preset, amount, allowed=None):
    """Bake the gap between the selected keys, ease it and add pinned
    noise in one undoable step.  The selected start/end keys never move.

    *amount* is the noise size in the attribute's own units.
    """
    (name, interval, pattern, factor, pin_start, pin_end, decay,
     ease, _desc) = preset
    cmds.undoInfo(openChunk=True, chunkName="CNG Preset: " + name)
    try:
        baked = bake(interval, allowed, preselect=True, quiet=True)
        if not baked:
            return False
        if not cmds.keyframe(q=True, name=True, selected=True):
            cmds.warning("CNG: The gap between the keys is too short for "
                         "{}'s.".format(interval))
            return False
        cache = KeyCache()
        if not cache.capture(attr_filter=allowed):
            return False
        snap = snapshot_anchors(cache)
        lock_anchor_tangents(cache)
        if ease:
            side, val = ease
            apply_ease_in_out(cache, val, DEF_MIN, DEF_MAX, side)
            cache.capture(attr_filter=allowed)
        apply_pin_noise(cache, pattern * abs(amount) * factor,
                        pin_start=pin_start, pin_end=pin_end, decay=decay)
        restore_anchors(snap)
        cmds.inViewMessage(
            amg="<hl>{}</hl>  ({} curve(s), amount {:g})".format(
                name, cache.ncurves, abs(amount) * factor),
            pos="midCenter", fade=True)
        return True
    except Exception as e:
        cmds.warning("CNG preset error: {}".format(e))
        return False
    finally:
        cmds.undoInfo(closeChunk=True)


# ===================================================================
#  Restore
# ===================================================================

def restore_captured(cache):
    if not cache.ok(): return
    cmds.undoInfo(openChunk=True, chunkName="CNG Restore")
    try:    _write_base(cache)
    finally: cmds.undoInfo(closeChunk=True)


# ============================================================================
# CUSTOM SLIDER UI (styled to match the Inbetweener tool)
# ============================================================================

class NoiseTickedSlider(QtWidgets.QSlider):
    """Fully custom-drawn slider: dark pill track, square accent ticks with
    larger square end caps, a centre-zero diamond marker, and a dark rounded
    box at the handle showing the slider's short label (NZ/NB/SC/ES/EB) in
    the slider's accent color.

    Works in float units: the underlying int slider is scaled by SCALE so
    drags map smoothly onto the user's min/max range.
    """

    SCALE = 100.0

    _TRACK_H = 12.0      # pill track height
    _TICK_INSET = 9.0    # keep end caps inside the pill's rounded corners
    _HANDLE_W = 36.0
    _HANDLE_H = 22.0

    def __init__(self, label_text, accent_hex, parent=None):
        super(NoiseTickedSlider, self).__init__(QtCore.Qt.Horizontal, parent)
        self.label_text = label_text
        self._accent_hex = accent_hex
        self._groove_drag = False  # True while dragging after a groove click
        self.setTickPosition(QtWidgets.QSlider.NoTicks)
        self.setTracking(True)
        self.setMinimumHeight(40)
        self.set_float_range(DEF_MIN, DEF_MAX)
        self.setValue(0)

    # ------------------------------------------------------------------
    # Float value mapping
    # ------------------------------------------------------------------
    def float_value(self):
        return self.value() / self.SCALE

    def set_float_range(self, lo, hi):
        self.setRange(int(round(lo * self.SCALE)), int(round(hi * self.SCALE)))

    def snap_to_zero(self):
        self.blockSignals(True)
        self.setValue(0)
        self.blockSignals(False)
        self.update()

    # ------------------------------------------------------------------
    # Geometry helpers shared by painting and mouse handling
    # ------------------------------------------------------------------
    def _accent_color(self):
        return QtGui.QColor(self._accent_hex)

    def _groove_metrics(self):
        """Return (groove_rect, inset, usable_span) for value<->x mapping."""
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self)
        span = max(1.0, groove.width() - 2 * self._TICK_INSET)
        return groove, self._TICK_INSET, span

    def _x_for_value(self, val):
        groove, inset, span = self._groove_metrics()
        s_min, s_max = self.minimum(), self.maximum()
        s_range = float(s_max - s_min) or 1.0
        return groove.left() + inset + ((val - s_min) / s_range) * span

    def _value_at(self, pos):
        """Map a mouse position to a slider value along the tick span."""
        groove, inset, span = self._groove_metrics()
        s_min, s_max = self.minimum(), self.maximum()
        frac = (pos.x() - groove.left() - inset) / span
        frac = min(max(frac, 0.0), 1.0)
        return int(round(s_min + frac * (s_max - s_min)))

    def _handle_box_rect(self):
        """Rect of the visible label-box handle at the current value."""
        groove, _, _ = self._groove_metrics()
        cy = groove.center().y()
        x = self._x_for_value(self.value())
        box_x = min(max(x - self._HANDLE_W / 2.0, 2.0),
                    self.width() - self._HANDLE_W - 2.0)
        return QtCore.QRectF(box_x, cy - self._HANDLE_H / 2.0,
                             self._HANDLE_W, self._HANDLE_H)

    # ------------------------------------------------------------------
    # Mouse handling — every press runs a full press/drag/release session
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        # Any left press starts a normal drag session (sliderPressed ->
        # cache, valueChanged -> apply, sliderReleased -> commit) instead
        # of Qt's default page-step jump, which changes values WITHOUT
        # ever firing sliderPressed/sliderReleased — i.e. outside any
        # undo chunk and without snapping back afterwards.
        if event.button() == QtCore.Qt.LeftButton:
            self._groove_drag = True
            self.setSliderDown(True)              # emits sliderPressed first
            if not self._handle_box_rect().contains(QtCore.QPointF(event.pos())):
                # Click on the track: jump the handle to the click position.
                # Clicks on the visible handle box grab it without jumping.
                self.setSliderPosition(self._value_at(event.pos()))
            self.update()
            event.accept()
            return
        super(NoiseTickedSlider, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._groove_drag:
            self.setSliderPosition(self._value_at(event.pos()))
            event.accept()
            return
        super(NoiseTickedSlider, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._groove_drag and event.button() == QtCore.Qt.LeftButton:
            self._groove_drag = False
            self.setSliderDown(False)             # emits sliderReleased
            self.update()
            event.accept()
            return
        super(NoiseTickedSlider, self).mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        # Deliberately does NOT call the base paintEvent: the native groove
        # and handle are replaced entirely by the custom look below.
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        groove, inset, span = self._groove_metrics()
        s_min, s_max = self.minimum(), self.maximum()
        s_range = float(s_max - s_min) or 1.0
        cy = groove.center().y()

        accent = self._accent_color()
        dim = QtGui.QColor(accent)
        dim.setAlpha(180)

        # --- Track: dark rounded pill ---
        track = QtCore.QRectF(groove.left(), cy - self._TRACK_H / 2.0,
                              groove.width(), self._TRACK_H)
        painter.setPen(QtGui.QPen(QtGui.QColor(34, 34, 34), 1))
        painter.setBrush(QtGui.QColor(46, 46, 46))
        painter.drawRoundedRect(track, self._TRACK_H / 2.0, self._TRACK_H / 2.0)

        # --- Square ticks every 10%, larger square caps at both ends ---
        painter.setPen(QtCore.Qt.NoPen)
        for i in range(11):
            frac = i / 10.0
            x = groove.left() + inset + frac * span
            is_end = i in (0, 10)
            size = 8.0 if is_end else (5.0 if i == 5 else 4.0)
            color = QtGui.QColor(accent) if is_end else QtGui.QColor(dim)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QtCore.QRectF(x - size / 2.0, cy - size / 2.0, size, size),
                1.5, 1.5)

        # --- Zero-position marker (accent diamond, where the slider rests) ---
        if s_min < 0 < s_max:
            zx = groove.left() + inset + ((0 - s_min) / s_range) * span
            painter.setBrush(QtGui.QColor(accent))
            painter.setPen(QtGui.QPen(QtGui.QColor(accent).darker(160), 1))
            diamond = QtGui.QPolygonF([
                QtCore.QPointF(zx, cy - 7),
                QtCore.QPointF(zx + 5, cy),
                QtCore.QPointF(zx, cy + 7),
                QtCore.QPointF(zx - 5, cy),
            ])
            painter.drawPolygon(diamond)

        # --- Handle: rounded box with the slider label ---
        # Idle: dark box with the label in the accent color.
        # While dragging: box fills with the accent color (dark label) so the
        # active slider reads at a glance.
        dragging = self.isSliderDown()
        box_rect = self._handle_box_rect()
        if dragging:
            painter.setPen(QtGui.QPen(QtGui.QColor(accent).darker(150), 1.2))
            painter.setBrush(accent)
            label_color = QtGui.QColor(34, 34, 34)
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor(110, 110, 110), 1.2))
            painter.setBrush(QtGui.QColor(58, 58, 58))
            label_color = accent
        painter.drawRoundedRect(box_rect, 5, 5)

        font = QtGui.QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        if self.label_text:
            painter.setPen(QtGui.QPen(label_color))
            painter.drawText(box_rect, QtCore.Qt.AlignCenter, self.label_text)

        # --- Live value readout while dragging ---
        # Shows the current value inside the track (right end, or left end
        # when the handle is over it). Disappears again on release.
        if dragging:
            txt = "{:+.1f}".format(self.float_value())
            fm = QtGui.QFontMetricsF(font)
            try:
                text_w = fm.horizontalAdvance(txt)
            except AttributeError:
                text_w = fm.width(txt)
            pad = 12.0
            tx = track.right() - pad - text_w
            if box_rect.right() >= tx - 8.0:
                tx = track.left() + pad
            text_rect = QtCore.QRectF(tx, cy - fm.height() / 2.0,
                                      text_w, fm.height())
            # Mask the ticks behind the readout so the number stays legible
            mask = text_rect.adjusted(-5, -2, 5, 2)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(46, 46, 46))
            painter.drawRoundedRect(mask, 3, 3)
            painter.setPen(QtGui.QPen(QtGui.QColor(175, 175, 175)))
            painter.drawText(text_rect, QtCore.Qt.AlignCenter, txt)

        painter.end()


# ============================================================================
# MAIN WINDOW
# ============================================================================

# Slider definitions: key -> (title, short label, accent color, descriptor)
SLIDER_DEFS = (
    ("noise", "NOISE", "NZ", "#6BB5FF",
     "Drag right for an alternating +/- zigzag, left for random noise. "
     "The value is the offset in the attribute's own units."),
    ("noise_build", "NOISE BUILD", "NB", "#C49BD6",
     "Noise that grows from zero at the selection edges to full amplitude "
     "in the middle. First and last selected keys stay pinned."),
    ("pin_noise", "PIN NOISE", "PN", "#FF8A8A",
     "Noise on the selected inbetweens. Right = zigzag, left = random. The "
     "start/end keys never move; checked pins fade the noise into them."),
    ("scale", "SCALE", "SC", "#FFD700",
     "Right amplifies values away from the first/last-key baseline, left "
     "compresses toward it. Edges stay pinned."),
    ("ease", "EASE", "ES", "#7EC8A0",
     "Right eases out toward the next key after the selection, left eases "
     "in toward the previous key before it."),
    ("ease_both", "EASE BOTH", "EB", "#E8A87C",
     "Right amplifies/overshoots away from the baseline, left settles both "
     "ends toward their neighbor keys."),
    ("ease_in", "EASE IN", "EI", "#8FD3C8",
     "Re-times the selected inbetweens. Right = slow start (ease out of the "
     "start key), left = fast start. Start/end keys never move."),
    ("ease_out", "EASE OUT", "EO", "#9FB8E8",
     "Re-times the selected inbetweens. Right = slow finish (ease into the "
     "end key), left = fast finish. Start/end keys never move."),
)

_UNDO_NAMES = {
    "noise":       "CNG Noise",
    "noise_build": "CNG Noise Build",
    "pin_noise":   "CNG Pin Noise",
    "ease_in":     "CNG Ease In",
    "ease_out":    "CNG Ease Out",
    "scale":       "CNG Scale",
    "ease":        "CNG Ease",
    "ease_both":   "CNG Ease Both",
}


# Tabs: (title, tooltip, workflow hint, group keys in order)
TAB_LAYOUT = (
    ("Inbetweens",
     "Bake inbetweens between two keys, add pinned noise, then ease",
     u"Select two keys  →  Bake  →  Pin Noise  →  Ease In / Out",
     ("bake", "pin_noise", "ease_in", "ease_out")),
    ("Presets",
     "One-click skid, shake and impact recipes",
     "Select the start and end key, set Amount, click a preset. It bakes, "
     "eases and adds noise in one undo - the two keys never move.",
     ("presets",)),
    ("Noise",
     "Noise and building noise on the selected keys",
     "",
     ("noise", "noise_build")),
    ("Shape",
     "Scale and ease the selected keys against their neighbours",
     "",
     ("scale", "ease", "ease_both")),
)

_TAB_OPTVAR = "cngLastTab"

# Sliders whose unselected start/end keys are held exactly
_ANCHORED_KEYS = ("pin_noise", "ease_in", "ease_out")


class CurveNoiseGenUI(QtWidgets.QDialog):
    """Curve Noise Generator main window, styled to match the Inbetweener."""

    instance = None

    @classmethod
    def display(cls):
        if cls.instance is not None:
            try:
                if not shiboken.isValid(cls.instance):
                    cls.instance = None
            except RuntimeError:
                cls.instance = None

        if cls.instance is None:
            cls.instance = CurveNoiseGenUI()

        cls.instance.show()
        cls.instance.raise_()
        cls.instance.activateWindow()
        return cls.instance

    def __init__(self, parent=None):
        _delete_legacy_ui()

        if parent is None:
            ptr = omui.MQtUtil.mainWindow()
            parent = shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
        super(CurveNoiseGenUI, self).__init__(parent)

        self.setWindowTitle("{} v{}".format(TITLE, VERSION))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setMinimumWidth(380)

        self.cache = KeyCache()
        self._undo_open = False
        self._session_active = False
        self._sliders = {}        # key -> NoiseTickedSlider
        self._value_spins = {}    # key -> QDoubleSpinBox
        self._min_spins = {}      # key -> QDoubleSpinBox
        self._max_spins = {}      # key -> QDoubleSpinBox
        self._channel_boxes = {}  # attr name -> QCheckBox
        self._anchor_snap = []    # start/end keys held by the inbetween sliders

        self._build_ui()

        # Size the window so every slider group is visible without
        # scrolling, clamped to the available screen height.
        # Height = everything outside the tabs + the tallest tab page, so
        # no tab needs to scroll on a normal screen.
        tallest = max(p.sizeHint().height() for p in self._tab_pages)
        lay = self.layout()
        m = lay.contentsMargins()
        fixed_h = (self._channels_frame.sizeHint().height()
                   + self._tabs.tabBar().sizeHint().height()
                   + self._status_label.sizeHint().height()
                   + m.top() + m.bottom() + 2 * lay.spacing() + 8)
        hint = QtCore.QSize(440, fixed_h + tallest)
        screen = None
        try:
            screen = self.screen()
        except AttributeError:
            pass
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        avail_h = screen.availableGeometry().height() if screen else 1000
        self.resize(440, min(hint.height(), avail_h - 80))

    # =================================================================
    #  UI construction
    # =================================================================
    def _build_ui(self):
        self.setStyleSheet("""
            QDialog { background: #3c3c3c; }
            QLabel { color: #ccc; background: transparent; border: none; }
            QPushButton {
                background: #4a4a4a; color: #ddd; border: 1px solid #666;
                border-radius: 3px; padding: 4px 8px; font-size: 11px;
            }
            QPushButton:hover { background: #5a5a5a; border-color: #888; }
            QPushButton:pressed { background: #333; }
            QPushButton#bakeButton {
                background: #46566a; border-color: #5d7188; font-weight: bold;
            }
            QPushButton#bakeButton:hover { background: #546882; }
            QPushButton#bakeButton:pressed { background: #38465a; }
            QCheckBox { color: #ccc; font-size: 11px; spacing: 4px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            QDoubleSpinBox {
                background: #2b2b2b; color: #ddd; border: 1px solid #555;
                border-radius: 3px; padding: 1px 2px; font-size: 11px;
            }
            QDoubleSpinBox:focus { border-color: #888; }
            QScrollArea { background: transparent; border: none; }
            QTabWidget::pane {
                border: 1px solid #555; border-radius: 4px; top: -1px;
                background: #3c3c3c;
            }
            QTabBar::tab {
                background: #333; color: #999; border: 1px solid #555;
                border-bottom: none; padding: 6px 16px; margin-right: 2px;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
                font-size: 11px; font-weight: bold;
            }
            QTabBar::tab:selected { background: #3c3c3c; color: #eee;
                                    border-color: #777; }
            QTabBar::tab:hover:!selected { background: #444; color: #ccc; }
        """)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ---- CHANNELS (shared by every tab) ---------------------------
        self._channels_frame = self._build_channels_group()
        outer.addWidget(self._channels_frame)

        # ---- TABS -----------------------------------------------------
        defs = dict((d[0], d) for d in SLIDER_DEFS)
        self._tabs = QtWidgets.QTabWidget()
        self._tabs.tabBar().setExpanding(True)
        self._tab_pages = []
        for tab_title, tip, hint_text, keys in TAB_LAYOUT:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            page = QtWidgets.QWidget()
            page.setStyleSheet("background: #3c3c3c;")
            col = QtWidgets.QVBoxLayout(page)
            col.setContentsMargins(6, 6, 6, 6)
            col.setSpacing(6)
            if hint_text:
                col.addWidget(self._make_workflow_hint(hint_text))
            for key in keys:
                if key == "bake":
                    col.addWidget(self._build_bake_group())
                elif key == "presets":
                    col.addWidget(self._build_presets_group())
                else:
                    _k, title, short, accent, desc = defs[key]
                    col.addWidget(self._build_slider_group(
                        key, title, short, accent, desc))
            col.addStretch()
            scroll.setWidget(page)
            idx = self._tabs.addTab(scroll, tab_title)
            self._tabs.setTabToolTip(idx, tip)
            self._tab_pages.append(page)
        outer.addWidget(self._tabs, 1)

        try:
            last = int(cmds.optionVar(q=_TAB_OPTVAR)) \
                if cmds.optionVar(exists=_TAB_OPTVAR) else 0
        except Exception:
            last = 0
        if 0 <= last < self._tabs.count():
            self._tabs.setCurrentIndex(last)
        self._tabs.currentChanged.connect(
            lambda i: cmds.optionVar(intValue=(_TAB_OPTVAR, int(i))))

        # ---- Status hint ----------------------------------------------
        status = QtWidgets.QLabel(
            "Select Graph Editor keys (or objects + timeline range), "
            "then drag a slider. Sliders snap back on release."
        )
        status.setWordWrap(True)
        status.setAlignment(QtCore.Qt.AlignCenter)
        status.setStyleSheet(
            "color: #999; font-size: 10px; padding: 3px 6px;"
            " background: #333; border: 1px solid #444; border-radius: 3px;"
        )
        self._status_label = status
        outer.addWidget(status)

    def _make_workflow_hint(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: #bbb; font-size: 10px; padding: 4px 6px;"
            " background: #343a40; border: 1px solid #4a525a;"
            " border-radius: 3px;"
        )
        return lbl

    def _make_group_frame(self, title, color):
        """Create a styled group frame with a colored header label,
        matching the Inbetweener's group boxes."""
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #3a3a3a; border: 1px solid #555;"
            " border-radius: 4px; }"
        )
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4)

        header = QtWidgets.QLabel(title)
        header.setStyleSheet(
            "QLabel {{ color: {c}; font-weight: bold; font-size: 11px;"
            " background: transparent; border: none; padding: 2px 0; }}".format(c=color)
        )
        header_row.addWidget(header)
        header_row.addStretch()

        layout.addLayout(header_row)
        return frame, layout, header_row

    def _make_descriptor(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(
            "color: #999; font-size: 9px; background: transparent;"
            " border: none; padding: 0 2px;"
        )
        lbl.setWordWrap(True)
        return lbl

    def _build_channels_group(self):
        frame, layout, header_row = self._make_group_frame(
            "CHANNELS", "#5285A6")

        hint = QtWidgets.QLabel("none checked = all")
        hint.setStyleSheet("color: #888; font-size: 9px; background:"
                           " transparent; border: none;")
        header_row.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(10)
        for label, attr in (("TX", "translateX"), ("TY", "translateY"),
                            ("TZ", "translateZ"), ("RX", "rotateX"),
                            ("RY", "rotateY"),    ("RZ", "rotateZ")):
            cb = QtWidgets.QCheckBox(label)
            cb.setToolTip("Restrict operations to {}".format(attr))
            self._channel_boxes[attr] = cb
            row.addWidget(cb)
        row.addStretch()
        layout.addLayout(row)
        return frame

    def _build_bake_group(self):
        frame, layout, _ = self._make_group_frame("BAKE", "#5285A6")
        layout.addWidget(self._make_descriptor(
            "Select two keys and fill between them on 1's, 2's, 3's or 4's. "
            "The two keys stay put; new inbetweens are marked as breakdowns."
        ))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        for n in (1, 2, 3, 4):
            btn = QtWidgets.QPushButton("{}'s".format(n))
            btn.setObjectName("bakeButton")
            btn.setFixedHeight(24)
            btn.setToolTip("Bake selected curves on {}'s".format(n))
            btn.clicked.connect(lambda _=False, i=n: self._bake(i))
            row.addWidget(btn)
        layout.addLayout(row)

        opt_row = QtWidgets.QHBoxLayout()
        opt_row.setSpacing(10)
        self.bake_preselect_cb = QtWidgets.QCheckBox(
            "Select inbetweens after bake")
        self.bake_preselect_cb.setChecked(True)
        self.bake_preselect_cb.setToolTip(
            "After baking, select only the new inbetweens in the Graph Editor "
            "(the two keys you baked between stay unselected) so you can drag "
            "Pin Noise / Ease In / Ease Out straight away")
        opt_row.addWidget(self.bake_preselect_cb)
        opt_row.addStretch()
        layout.addLayout(opt_row)
        return frame

    def _build_presets_group(self):
        frame, layout, header_row = self._make_group_frame(
            "PRESETS", "#E0B85A")

        lbl = QtWidgets.QLabel("Amount")
        lbl.setStyleSheet("color: #888; font-size: 9px; background:"
                          " transparent; border: none;")
        header_row.addWidget(lbl)
        self.preset_amount = QtWidgets.QDoubleSpinBox()
        self.preset_amount.setDecimals(2)
        self.preset_amount.setRange(0.01, 1000.0)
        self.preset_amount.setValue(1.0)
        self.preset_amount.setSingleStep(0.25)
        self.preset_amount.setFixedWidth(64)
        self.preset_amount.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.NoButtons)
        self.preset_amount.setToolTip(
            "Noise size in the attribute's units: degrees for rotate, scene "
            "units for translate. Try 0.5-2 for a camera, more for big moves.")
        header_row.addWidget(self.preset_amount)

        for preset in PRESETS:
            name, interval, _p, _f, _ps, _pe, _d, _e, desc = preset
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            btn = QtWidgets.QPushButton(name)
            btn.setObjectName("bakeButton")
            btn.setFixedSize(112, 26)
            btn.setToolTip(desc)
            btn.clicked.connect(
                lambda _=False, p=preset: self._run_preset(p))
            row.addWidget(btn, 0, QtCore.Qt.AlignTop)
            d = self._make_descriptor(
                u"{}  •  on {}'s".format(desc, interval))
            row.addWidget(d, 1)
            layout.addLayout(row)
        return frame

    def _run_preset(self, preset):
        if self._session_active:
            return
        run_preset(preset, self.preset_amount.value(),
                   allowed=self._checked_attrs())

    def _build_slider_group(self, key, title, short, accent, desc):
        frame, layout, header_row = self._make_group_frame(title, accent)

        # Min / Max range fields live in the header row to save height
        for text, attr_key, lo, hi, dv in (
                ("Min", "min", -ABS_MAX, -ABS_MIN, DEF_MIN),
                ("Max", "max",  ABS_MIN,  ABS_MAX, DEF_MAX)):
            lbl = QtWidgets.QLabel(text)
            lbl.setStyleSheet("color: #888; font-size: 9px; background:"
                              " transparent; border: none;")
            header_row.addWidget(lbl)
            spin = QtWidgets.QDoubleSpinBox()
            spin.setDecimals(1)
            spin.setRange(lo, hi)
            spin.setValue(dv)
            spin.setSingleStep(1.0)
            spin.setFixedWidth(58)
            spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            spin.setToolTip("{} slider range".format(text))
            spin.editingFinished.connect(
                lambda k=key: self._on_range_changed(k))
            if attr_key == "min":
                self._min_spins[key] = spin
            else:
                self._max_spins[key] = spin
            header_row.addWidget(spin)

        layout.addWidget(self._make_descriptor(desc))

        # Value field + slider row
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)

        vspin = QtWidgets.QDoubleSpinBox()
        vspin.setDecimals(1)
        vspin.setRange(DEF_MIN, DEF_MAX)
        vspin.setValue(0.0)
        vspin.setSingleStep(0.5)
        vspin.setFixedWidth(58)
        vspin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        vspin.setKeyboardTracking(False)
        vspin.setToolTip("Type an exact value and press Enter to apply it")
        vspin.editingFinished.connect(lambda k=key: self._on_spin_commit(k))
        self._value_spins[key] = vspin
        row.addWidget(vspin)

        slider = NoiseTickedSlider(short, accent)
        slider.sliderPressed.connect(lambda k=key: self._on_press(k))
        slider.valueChanged.connect(lambda _v, k=key: self._on_change(k))
        slider.sliderReleased.connect(lambda k=key: self._on_release(k))
        self._sliders[key] = slider
        row.addWidget(slider)

        layout.addLayout(row)

        # Per-slider option checkboxes
        if key == "noise":
            self.noise_taper_cb = QtWidgets.QCheckBox("Taper noise")
            self.noise_taper_cb.setToolTip(
                "Diminish the noise amplitude across the selection")
            layout.addWidget(self.noise_taper_cb)
        elif key == "pin_noise":
            pin_row = QtWidgets.QHBoxLayout()
            pin_row.setSpacing(10)
            self.pin_start_cb = QtWidgets.QCheckBox("Pin start key")
            self.pin_start_cb.setChecked(True)
            self.pin_start_cb.setToolTip(
                "Fade the noise in from the start key (the key before the "
                "selection), so there is no pop at the start")
            self.pin_end_cb = QtWidgets.QCheckBox("Pin end key")
            self.pin_end_cb.setChecked(True)
            self.pin_end_cb.setToolTip(
                "Fade the noise out into the end key (the key after the "
                "selection), so there is no pop at the end")
            self.pin_decay_cb = QtWidgets.QCheckBox("Decay")
            self.pin_decay_cb.setToolTip(
                "Impact-style falloff: full noise at the start, dying away "
                "into the end key (skids, hits, settles)")
            self.pin_decay_cb.toggled.connect(
                lambda on: self.pin_end_cb.setEnabled(not on))
            pin_row.addWidget(self.pin_start_cb)
            pin_row.addWidget(self.pin_end_cb)
            pin_row.addWidget(self.pin_decay_cb)
            pin_row.addStretch()
            layout.addLayout(pin_row)
        elif key == "scale":
            self.scale_both_cb = QtWidgets.QCheckBox("Scale both sides")
            self.scale_both_cb.setToolTip(
                "Shape the scale with a bell envelope so it tapers at both "
                "ends of the selection")
            layout.addWidget(self.scale_both_cb)

        return frame

    # =================================================================
    #  Channel filter / bake
    # =================================================================
    def _checked_attrs(self):
        """Return the set of Maya attr names enabled by the channel
        checkboxes.  If NONE are checked, return None -> 'all curves'."""
        active = set(attr for attr, cb in self._channel_boxes.items()
                     if cb.isChecked())
        return active or None

    def _bake(self, interval):
        bake(interval, allowed=self._checked_attrs(),
             preselect=self.bake_preselect_cb.isChecked())

    # =================================================================
    #  Undo helpers
    # =================================================================
    def _begin_undo(self, name):
        if not self._undo_open:
            cmds.undoInfo(openChunk=True, chunkName=name)
            self._undo_open = True

    def _end_undo(self):
        if self._undo_open:
            self._undo_open = False
            try:
                cmds.undoInfo(closeChunk=True)
            except RuntimeError:
                pass

    # =================================================================
    #  Slider session: press -> capture, drag -> apply, release -> commit
    # =================================================================
    def _apply(self, key, value):
        self._apply_effect(key, value)
        if key in _ANCHORED_KEYS:
            restore_anchors(self._anchor_snap)

    def _apply_effect(self, key, value):
        if key == "noise":
            apply_noise(self.cache, value,
                        taper=self.noise_taper_cb.isChecked())
        elif key == "noise_build":
            apply_noise_build(self.cache, value)
        elif key == "pin_noise":
            apply_pin_noise(self.cache, value,
                            pin_start=self.pin_start_cb.isChecked(),
                            pin_end=self.pin_end_cb.isChecked(),
                            decay=self.pin_decay_cb.isChecked())
        elif key in ("ease_in", "ease_out"):
            apply_ease_in_out(self.cache, value,
                              self._min_spins[key].value(),
                              self._max_spins[key].value(),
                              side="in" if key == "ease_in" else "out")
        elif key == "scale":
            apply_scale(self.cache, value,
                        self._min_spins[key].value(),
                        self._max_spins[key].value(),
                        both_sides=self.scale_both_cb.isChecked())
        elif key == "ease":
            apply_ease(self.cache, value,
                       self._min_spins[key].value(),
                       self._max_spins[key].value())
        elif key == "ease_both":
            apply_ease_both(self.cache, value,
                            self._min_spins[key].value(),
                            self._max_spins[key].value())

    def _prepare_anchors(self, key):
        """For the inbetween sliders: remember the start/end keys, freeze
        their tangents and report what will be edited.  Runs inside the
        slider's undo chunk."""
        self._anchor_snap = []
        if key not in _ANCHORED_KEYS:
            return
        self._anchor_snap = snapshot_anchors(self.cache)
        lock_anchor_tangents(self.cache)
        for line in describe_anchors(self.cache):
            print("{}: {}".format(_UNDO_NAMES[key], line))

    def _on_press(self, key):
        self._session_active = False
        if not self.cache.capture(attr_filter=self._checked_attrs()):
            cmds.warning("CNG: Select keys first.")
            return
        self._session_active = True
        self._begin_undo(_UNDO_NAMES[key])
        self._prepare_anchors(key)

    def _on_change(self, key):
        if not self._session_active:
            return
        v = self._sliders[key].float_value()
        spin = self._value_spins[key]
        spin.blockSignals(True)
        spin.setValue(v)
        spin.blockSignals(False)
        try:
            self._apply(key, v)
        except Exception as e:
            cmds.warning("CNG: {}".format(e))

    def _on_release(self, key):
        slider = self._sliders[key]
        if self._session_active:
            try:
                self._apply(key, slider.float_value())
            except Exception as e:
                cmds.warning("CNG: {}".format(e))
            self._end_undo()
            self._session_active = False
        self.cache.clear()
        slider.snap_to_zero()
        spin = self._value_spins[key]
        spin.blockSignals(True)
        spin.setValue(0.0)
        spin.blockSignals(False)

    # =================================================================
    #  Typed value: apply once as a single undoable operation
    # =================================================================
    def _on_spin_commit(self, key):
        spin = self._value_spins[key]
        v = spin.value()
        if v == 0.0 or self._session_active:
            return
        if not self.cache.capture(attr_filter=self._checked_attrs()):
            cmds.warning("CNG: Select keys first.")
            self._reset_spin(spin)
            return
        cmds.undoInfo(openChunk=True, chunkName=_UNDO_NAMES[key])
        try:
            self._prepare_anchors(key)
            self._apply(key, v)
        except Exception as e:
            cmds.warning("CNG: {}".format(e))
        finally:
            cmds.undoInfo(closeChunk=True)
        self.cache.clear()
        self._reset_spin(spin)

    def _reset_spin(self, spin):
        spin.blockSignals(True)
        spin.setValue(0.0)
        spin.blockSignals(False)

    # =================================================================
    #  Range fields
    # =================================================================
    def _on_range_changed(self, key):
        if self._session_active:
            return
        lo = self._min_spins[key].value()
        hi = self._max_spins[key].value()
        self._sliders[key].set_float_range(lo, hi)
        self._sliders[key].snap_to_zero()
        spin = self._value_spins[key]
        spin.blockSignals(True)
        spin.setRange(lo, hi)
        spin.setValue(0.0)
        spin.blockSignals(False)

    # =================================================================
    #  Cleanup
    # =================================================================
    def closeEvent(self, event):
        self._end_undo()
        self.cache.clear()
        super(CurveNoiseGenUI, self).closeEvent(event)


def _delete_legacy_ui():
    """Remove any leftover maya.cmds UI from version 1.0.0."""
    try:
        if cmds.workspaceControl(_LEGACY_WORKSPACE, exists=True):
            cmds.deleteUI(_LEGACY_WORKSPACE)
    except Exception:
        pass
    try:
        if cmds.window(_LEGACY_WIN, exists=True):
            cmds.deleteUI(_LEGACY_WIN, window=True)
    except Exception:
        pass


# ===================================================================
#  Launch
# ===================================================================

def launch():
    return CurveNoiseGenUI.display()

if __name__ == "__main__":
    launch()
