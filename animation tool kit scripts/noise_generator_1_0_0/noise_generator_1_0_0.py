"""
Curve Noise Generator - Maya Animation Curve Tool
===================================================
Dockable Maya UI for animation curve manipulation:
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
each operation so the next drag starts fresh.

Author : Claude (Anthropic)
Requires: Autodesk Maya 2020+
Usage  :
    import curve_noise_generator
    curve_noise_generator.launch()

Notes:
    - Opens floating at full UI size on first launch.
    - Can be docked like a standard Maya workspace panel.
"""

from __future__ import division, print_function
import math
import random
import maya.cmds as cmds
import maya.mel as mel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WIN   = "cng_win"
WORKSPACE = "cng_workspaceControl"
TITLE = "Curve Noise Generator"

UI_WIDTH = 340
UI_HEIGHT = 900

# Named controls
S_N_SLIDER   = "cng_nSldr"
S_N_FIELD    = "cng_nFld"
S_N_MIN      = "cng_nMin"
S_N_MAX      = "cng_nMax"
S_N_TAPER    = "cng_nTaper"
S_NB_SLIDER  = "cng_nbSldr"
S_NB_FIELD   = "cng_nbFld"
S_NB_MIN     = "cng_nbMin"
S_NB_MAX     = "cng_nbMax"
S_SC_SLIDER  = "cng_scSldr"
S_SC_FIELD   = "cng_scFld"
S_SC_MIN     = "cng_scMin"
S_SC_MAX     = "cng_scMax"
S_SC_BOTH    = "cng_scBoth"
S_E_SLIDER   = "cng_eSldr"
S_E_FIELD    = "cng_eFld"
S_E_MIN      = "cng_eMin"
S_E_MAX      = "cng_eMax"
S_EB_SLIDER  = "cng_ebSldr"
S_EB_FIELD   = "cng_ebFld"
S_EB_MIN     = "cng_ebMin"
S_EB_MAX     = "cng_ebMax"
S_MAIN_FORM   = "cng_mainForm"
S_MAIN_SCROLL = "cng_mainScroll"
S_ROOT_COL    = "cng_rootCol"

# Channel filter checkboxes
S_CB_TX = "cng_cbTX"
S_CB_TY = "cng_cbTY"
S_CB_TZ = "cng_cbTZ"
S_CB_RX = "cng_cbRX"
S_CB_RY = "cng_cbRY"
S_CB_RZ = "cng_cbRZ"

DEF_MIN  = -10.0
DEF_MAX  =  10.0
ABS_MIN  =   0.1
ABS_MAX  = 150.0

# Colours
C_GREEN   = (0.30, 0.54, 0.30)
C_ORANGE  = (0.62, 0.40, 0.24)
C_GREY    = (0.36, 0.36, 0.36)
C_BLUE    = (0.32, 0.40, 0.48)
C_DKBG    = (0.20, 0.20, 0.20)
C_SLIDBG  = (0.17, 0.17, 0.17)
C_ACCENT  = (0.28, 0.52, 0.52)

# Map checkbox control names to Maya attribute suffixes
_CHANNEL_MAP = {
    S_CB_TX: "translateX",
    S_CB_TY: "translateY",
    S_CB_TZ: "translateZ",
    S_CB_RX: "rotateX",
    S_CB_RY: "rotateY",
    S_CB_RZ: "rotateZ",
}

ALL_NAMED_CTRLS = (
    S_N_SLIDER, S_N_FIELD, S_N_MIN, S_N_MAX, S_N_TAPER,
    S_NB_SLIDER, S_NB_FIELD, S_NB_MIN, S_NB_MAX,
    S_SC_SLIDER, S_SC_FIELD, S_SC_MIN, S_SC_MAX, S_SC_BOTH,
    S_E_SLIDER, S_E_FIELD, S_E_MIN, S_E_MAX,
    S_EB_SLIDER, S_EB_FIELD, S_EB_MIN, S_EB_MAX,
    S_MAIN_FORM, S_MAIN_SCROLL, S_ROOT_COL,
    S_CB_TX, S_CB_TY, S_CB_TZ, S_CB_RX, S_CB_RY, S_CB_RZ,
)


# ===================================================================
#  Channel filter helpers
# ===================================================================

def _get_curve_attr(crv):
    """Return the attribute name an anim curve drives (e.g. 'translateX')."""
    conns = cmds.listConnections(crv + ".output", plugs=True) or []
    if not conns:
        return ""
    plug = conns[0]
    if "." in plug:
        return plug.split(".")[-1]
    return ""


def _checked_attrs():
    """Return the set of Maya attr names enabled by the channel checkboxes.
    If NONE are checked, return None -> meaning 'all curves pass'."""
    active = set()
    for cb, attr in _CHANNEL_MAP.items():
        if _qcb(cb):
            active.add(attr)
    return active if active else None


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

            next_idx = last_idx + 1
            v = cmds.keyframe(crv, q=True, index=(next_idx, next_idx),
                              valueChange=True)
            t = cmds.keyframe(crv, q=True, index=(next_idx, next_idx),
                              timeChange=True)
            if v and t:
                self.next_key[crv] = v[0]
                self.next_time[crv] = t[0]

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

def _bake_range(curves):
    tt = []
    for c in curves:
        tt.extend(cmds.keyframe(c, q=True, selected=True, timeChange=True) or [])
    if tt:
        return (int(min(tt)), int(max(tt)))
    r = _tl_range()
    return (int(r[0]), int(r[1]))

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _qf(ctl, default=0.0):
    try:    return cmds.floatField(ctl, q=True, value=True)
    except: return default

def _qcb(ctl, default=False):
    try:    return cmds.checkBox(ctl, q=True, value=True)
    except: return default


# ===================================================================
#  Bake
# ===================================================================

def bake(interval):
    sel = cmds.ls(sl=True)
    if not sel:
        cmds.warning("CNG: Nothing selected."); return
    ac = set()
    for o in sel:
        ac.update(cmds.keyframe(o, q=True, name=True) or [])
    if not ac:
        cmds.warning("CNG: No anim curves."); return

    allowed = _checked_attrs()
    curves = _filter_curves(sorted(ac), allowed)
    if not curves:
        cmds.warning("CNG: No curves match the checked channels."); return

    sf, ef = _bake_range(curves)
    cmds.undoInfo(openChunk=True, chunkName="Bake on {}'s".format(interval))
    try:
        for crv in curves:
            conns = cmds.listConnections(crv + ".output", plugs=True) or []
            if not conns: continue
            plug = conns[0]
            sampled = {}
            for f in range(sf, ef + 1):
                v = cmds.keyframe(crv, q=True, time=(f, f), eval=True, valueChange=True)
                if v: sampled[f] = v[0]
            cmds.cutKey(crv, time=(sf, ef), clear=True)

            baked_frames = []
            for f in range(sf, ef + 1, interval):
                if f in sampled:
                    cmds.setKeyframe(plug, time=f, value=sampled[f])
                    if f != sf and f != ef:
                        baked_frames.append(f)
            if ef not in range(sf, ef + 1, interval) and ef in sampled:
                cmds.setKeyframe(plug, time=ef, value=sampled[ef])

            cmds.keyTangent(crv, time=(sf, ef), itt="auto", ott="auto")

            for f in baked_frames:
                cmds.keyframe(crv, time=(f, f), tickDrawSpecial=True)
                cmds.keyframe(crv, time=(f, f), breakdown=True)

            for bf in (sf, ef):
                try:
                    cmds.keyframe(crv, time=(bf, bf), tickDrawSpecial=False)
                    cmds.keyframe(crv, time=(bf, bf), breakdown=False)
                except:
                    pass

        cmds.inViewMessage(amg="<hl>Baked on {}'s</hl>  ({}-{})".format(interval, sf, ef),
                           pos="midCenter", fade=True)
    except Exception as e:
        cmds.warning("Bake error: {}".format(e))
    finally:
        cmds.undoInfo(closeChunk=True)


# ===================================================================
#  Noise -- direct value offset  (IDENTICAL to original project file)
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
#  Ease  (IDENTICAL to original project file)
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
#  Restore
# ===================================================================

def restore_captured(cache):
    if not cache.ok(): return
    cmds.undoInfo(openChunk=True, chunkName="CNG Restore")
    try:    _write_base(cache)
    finally: cmds.undoInfo(closeChunk=True)


# ===================================================================
#  UI
# ===================================================================

class CurveNoiseGenUI(object):

    def __init__(self):
        self.cache = KeyCache()
        self._drag = False
        self._build()

    # helpers
    def _nmin(self):  return _qf(S_N_MIN, DEF_MIN)
    def _nmax(self):  return _qf(S_N_MAX, DEF_MAX)
    def _nbmin(self): return _qf(S_NB_MIN, DEF_MIN)
    def _nbmax(self): return _qf(S_NB_MAX, DEF_MAX)
    def _scmin(self): return _qf(S_SC_MIN, DEF_MIN)
    def _scmax(self): return _qf(S_SC_MAX, DEF_MAX)
    def _emin(self):  return _qf(S_E_MIN, DEF_MIN)
    def _emax(self):  return _qf(S_E_MAX, DEF_MAX)
    def _ebmin(self): return _qf(S_EB_MIN, DEF_MIN)
    def _ebmax(self): return _qf(S_EB_MAX, DEF_MAX)

    def _auto_cap(self):
        if not self.cache.ok():
            af = _checked_attrs()
            ok = self.cache.capture(attr_filter=af)
            if not ok:
                cmds.warning("CNG: Select keys first.")
            return ok
        return True

    def _release(self):
        self.cache.clear()

    def _refresh_scroll(self, *_):
        """Force the outer scroll area to recalculate after docking, floating,
        or switching between horizontal / vertical UI blocks."""
        try:
            if cmds.scrollLayout(S_MAIN_SCROLL, exists=True):
                cmds.scrollLayout(
                    S_MAIN_SCROLL, e=True,
                    childResizable=True,
                    verticalScrollBarAlwaysVisible=True
                )
        except:
            pass

        try:
            if cmds.columnLayout(S_ROOT_COL, exists=True):
                cmds.columnLayout(S_ROOT_COL, e=True, adj=True)
        except:
            pass

        try:
            cmds.evalDeferred(
                lambda: cmds.scrollLayout(
                    S_MAIN_SCROLL, e=True,
                    childResizable=True,
                    verticalScrollBarAlwaysVisible=True
                ) if cmds.scrollLayout(S_MAIN_SCROLL, exists=True) else None
            )
        except:
            pass

    # =================================================================
    #  Compact slider row builder (horizontal)
    # =================================================================
    def _make_slider_row(self, slider_name, field_name,
                         mn, mx, drag_cb, release_cb):
        row = cmds.rowLayout(nc=2, adj=2, cw2=(48, 200),
                             cat=[(1, "both", 4), (2, "both", 2)])

        cmds.floatField(field_name, v=0, pre=1, w=46, h=20,
                        minValue=mn, maxValue=mx,
                        cc=lambda v: self._field_to_slider(field_name, slider_name, v))

        cmds.floatSlider(slider_name, min=mn, max=mx, v=0, h=20,
                         dc=drag_cb, cc=release_cb)

        cmds.setParent("..")

    def _field_to_slider(self, field, slider, val):
        cmds.floatSlider(slider, e=True, v=val)

    def _slider_to_field(self, slider, field, val):
        try:
            cmds.floatField(field, e=True, v=val)
        except:
            pass

    # =================================================================
    #  Min/Max range row builder (reusable)
    # =================================================================
    def _make_range_row(self, min_ctl, max_ctl, range_cb):
        rf = cmds.formLayout(h=22)
        nl = cmds.text(label="Min", fn="smallPlainLabelFont")
        nf1 = cmds.floatField(min_ctl, v=DEF_MIN, pre=0, h=20,
                               minValue=-ABS_MAX, maxValue=-ABS_MIN,
                               cc=lambda *_: range_cb())
        nl2 = cmds.text(label="Max", fn="smallPlainLabelFont")
        nf2 = cmds.floatField(max_ctl, v=DEF_MAX, pre=0, h=20,
                               minValue=ABS_MIN, maxValue=ABS_MAX,
                               cc=lambda *_: range_cb())
        cmds.formLayout(rf, e=True,
            attachForm=[
                (nl,  "left", 8),  (nl,  "top", 3),
                (nl2, "top", 3),
                (nf2, "right", 8), (nf2, "top", 0), (nf2, "bottom", 0),
                (nf1, "top", 0),   (nf1, "bottom", 0),
            ],
            attachControl=[
                (nf1, "left", 4, nl),
                (nl2, "left", 12, nf1),
                (nf2, "left", 4, nl2),
            ],
            attachPosition=[
                (nf1, "right", 6, 50),
                (nl2, "left", 6, 50),
            ])
        cmds.setParent("..")

    # =================================================================
    #  Build
    # =================================================================
    def _build(self):
        if cmds.workspaceControl(WORKSPACE, exists=True):
            cmds.deleteUI(WORKSPACE)
        if cmds.window(WIN, exists=True):
            cmds.deleteUI(WIN, window=True)
        for c in ALL_NAMED_CTRLS:
            if cmds.control(c, exists=True):
                try:
                    cmds.deleteUI(c)
                except:
                    pass

        use_workspace = hasattr(cmds, 'workspaceControl')

        if use_workspace:
            cmds.workspaceControl(
                WORKSPACE, label=TITLE, floating=True, retain=False,
                initialWidth=UI_WIDTH, initialHeight=UI_HEIGHT,
                minimumWidth=180, minimumHeight=520,
                widthProperty='free', heightProperty='free',
                loadImmediately=True,
            )
            cmds.workspaceControl(WORKSPACE, e=True, restore=True, visible=True)
            cmds.setParent(WORKSPACE)
            main_form = cmds.formLayout(S_MAIN_FORM)
            main_scroll = cmds.scrollLayout(
                S_MAIN_SCROLL,
                childResizable=True,
                verticalScrollBarAlwaysVisible=True
            )
            cmds.formLayout(
                main_form, e=True,
                attachForm=[
                    (main_scroll, "top", 0),
                    (main_scroll, "left", 0),
                    (main_scroll, "right", 0),
                    (main_scroll, "bottom", 0),
                ]
            )
        else:
            cmds.window(WIN, title=TITLE, widthHeight=(UI_WIDTH, UI_HEIGHT),
                        sizeable=True)
            main_form = cmds.formLayout(S_MAIN_FORM)
            main_scroll = cmds.scrollLayout(
                S_MAIN_SCROLL,
                childResizable=True,
                verticalScrollBarAlwaysVisible=True
            )
            cmds.formLayout(
                main_form, e=True,
                attachForm=[
                    (main_scroll, "top", 0),
                    (main_scroll, "left", 0),
                    (main_scroll, "right", 0),
                    (main_scroll, "bottom", 0),
                ]
            )

        root = cmds.columnLayout(S_ROOT_COL, adj=True, rs=0)

        # ---- HEADER --------------------------------------------------
        cmds.separator(h=6, style="none")
        cmds.text(label="  " + TITLE, fn="boldLabelFont", align="left", h=20)
        cmds.separator(h=4, style="none")

        # ---- CHANNEL FILTER -------------------------------------------
        cmds.text(label="  Channels  (none checked = all)",
                  fn="smallBoldLabelFont", align="left", h=16)
        cmds.separator(h=3, style="none")

        cmds.rowLayout(nc=4, adj=4, cw4=(30, 52, 52, 52),
                       cat=[(1, "left", 8), (2, "left", 0),
                            (3, "left", 0), (4, "left", 0)])
        cmds.text(label="T", fn="smallBoldLabelFont")
        cmds.checkBox(S_CB_TX, label="TX", v=False)
        cmds.checkBox(S_CB_TY, label="TY", v=False)
        cmds.checkBox(S_CB_TZ, label="TZ", v=False)
        cmds.setParent("..")

        cmds.rowLayout(nc=4, adj=4, cw4=(30, 52, 52, 52),
                       cat=[(1, "left", 8), (2, "left", 0),
                            (3, "left", 0), (4, "left", 0)])
        cmds.text(label="R", fn="smallBoldLabelFont")
        cmds.checkBox(S_CB_RX, label="RX", v=False)
        cmds.checkBox(S_CB_RY, label="RY", v=False)
        cmds.checkBox(S_CB_RZ, label="RZ", v=False)
        cmds.setParent("..")
        cmds.separator(h=6, style="in")

        # ---- BAKE ----------------------------------------------------
        cmds.text(label="  Bake", fn="smallBoldLabelFont", align="left", h=16)
        cmds.separator(h=3, style="none")
        frm = cmds.formLayout(h=28)
        b1 = cmds.button(label="1's", bgc=C_BLUE, c=lambda *_: bake(1))
        b2 = cmds.button(label="2's", bgc=C_BLUE, c=lambda *_: bake(2))
        b3 = cmds.button(label="3's", bgc=C_BLUE, c=lambda *_: bake(3))
        b4 = cmds.button(label="4's", bgc=C_BLUE, c=lambda *_: bake(4))
        m = 6
        cmds.formLayout(frm, e=True,
            attachForm=[
                (b1, "left", m), (b1, "top", 0), (b1, "bottom", 0),
                (b4, "right", m), (b4, "top", 0), (b4, "bottom", 0),
                (b2, "top", 0), (b2, "bottom", 0),
                (b3, "top", 0), (b3, "bottom", 0),
            ],
            attachPosition=[
                (b1, "right", 2, 25),
                (b2, "left", 2, 25), (b2, "right", 2, 50),
                (b3, "left", 2, 50), (b3, "right", 2, 75),
                (b4, "left", 2, 75),
            ])
        cmds.setParent(root)
        cmds.separator(h=8, style="in")

        # ---- NOISE ---------------------------------------------------
        cmds.text(label="", h=2, bgc=C_ACCENT)
        cmds.separator(h=4, style="none")
        cmds.text(label="  Noise   ( + zigzag  |  - random )",
                  fn="boldLabelFont", align="left", h=20)
        cmds.separator(h=3, style="none")
        self._make_range_row(S_N_MIN, S_N_MAX, self._noise_range)
        cmds.separator(h=3, style="none")
        self._make_slider_row(S_N_SLIDER, S_N_FIELD, DEF_MIN, DEF_MAX,
            drag_cb=lambda v: self._noise_drag(v),
            release_cb=lambda v: self._noise_end(v))
        cmds.separator(h=3, style="none")
        cmds.rowLayout(nc=2, adj=2, cw2=(140, 120),
                       cat=[(1, "left", 6), (2, "right", 6)])
        cmds.checkBox(S_N_TAPER, label="Taper noise", v=False)
        cmds.button(label="Reset Noise", h=20, bgc=C_GREY,
                    c=lambda *_: self._noise_reset())
        cmds.setParent("..")
        cmds.separator(h=6, style="none")

        # ---- NOISE BUILD ---------------------------------------------
        cmds.text(label="", h=2, bgc=C_ACCENT)
        cmds.separator(h=4, style="none")
        cmds.text(label="  Noise Build   ( + zigzag  |  - random  |  edges pinned )",
                  fn="boldLabelFont", align="left", h=20)
        cmds.separator(h=3, style="none")
        self._make_range_row(S_NB_MIN, S_NB_MAX, self._noise_build_range)
        cmds.separator(h=3, style="none")
        self._make_slider_row(S_NB_SLIDER, S_NB_FIELD, DEF_MIN, DEF_MAX,
            drag_cb=lambda v: self._noise_build_drag(v),
            release_cb=lambda v: self._noise_build_end(v))
        cmds.separator(h=3, style="none")
        cmds.rowLayout(nc=1, adj=1, cat=(1, "both", 6))
        cmds.button(label="Reset Noise Build", h=20, bgc=C_GREY,
                    c=lambda *_: self._noise_build_reset())
        cmds.setParent("..")
        cmds.separator(h=6, style="none")

        # ---- SCALE ---------------------------------------------------
        cmds.text(label="", h=2, bgc=C_ACCENT)
        cmds.separator(h=4, style="none")
        cmds.text(label="  Scale   ( + amplify  |  - compress  |  edges pinned )",
                  fn="boldLabelFont", align="left", h=20)
        cmds.separator(h=3, style="none")
        self._make_range_row(S_SC_MIN, S_SC_MAX, self._scale_range)
        cmds.separator(h=3, style="none")
        self._make_slider_row(S_SC_SLIDER, S_SC_FIELD, DEF_MIN, DEF_MAX,
            drag_cb=lambda v: self._scale_drag(v),
            release_cb=lambda v: self._scale_end(v))
        cmds.separator(h=3, style="none")
        cmds.rowLayout(nc=2, adj=2, cw2=(140, 120),
                       cat=[(1, "left", 6), (2, "right", 6)])
        cmds.checkBox(S_SC_BOTH, label="Scale both sides", v=False)
        cmds.button(label="Reset Scale", h=20, bgc=C_GREY,
                    c=lambda *_: self._scale_reset())
        cmds.setParent("..")
        cmds.separator(h=6, style="none")

        # ---- EASE ----------------------------------------------------
        cmds.text(label="", h=2, bgc=C_ACCENT)
        cmds.separator(h=4, style="none")
        cmds.text(label="  Ease   ( + to next key  |  - to prev key )",
                  fn="boldLabelFont", align="left", h=20)
        cmds.separator(h=3, style="none")
        self._make_range_row(S_E_MIN, S_E_MAX, self._ease_range)
        cmds.separator(h=3, style="none")
        self._make_slider_row(S_E_SLIDER, S_E_FIELD, DEF_MIN, DEF_MAX,
            drag_cb=lambda v: self._ease_drag(v),
            release_cb=lambda v: self._ease_end(v))
        cmds.separator(h=3, style="none")
        cmds.rowLayout(nc=1, adj=1, cat=(1, "both", 6))
        cmds.button(label="Reset Ease", h=20, bgc=C_GREY,
                    c=lambda *_: self._ease_reset())
        cmds.setParent("..")
        cmds.separator(h=6, style="none")

        # ---- EASE BOTH -----------------------------------------------
        cmds.text(label="", h=2, bgc=C_ACCENT)
        cmds.separator(h=4, style="none")
        cmds.text(label="  Ease Both   ( + amplify  |  - settle )",
                  fn="boldLabelFont", align="left", h=20)
        cmds.separator(h=3, style="none")
        self._make_range_row(S_EB_MIN, S_EB_MAX, self._ease_both_range)
        cmds.separator(h=3, style="none")
        self._make_slider_row(S_EB_SLIDER, S_EB_FIELD, DEF_MIN, DEF_MAX,
            drag_cb=lambda v: self._ease_both_drag(v),
            release_cb=lambda v: self._ease_both_end(v))
        cmds.separator(h=3, style="none")
        cmds.rowLayout(nc=1, adj=1, cat=(1, "both", 6))
        cmds.button(label="Reset Ease Both", h=20, bgc=C_GREY,
                    c=lambda *_: self._ease_both_reset())
        cmds.setParent("..")

        # ---- UTILITY -------------------------------------------------
        cmds.separator(h=8, style="in")
        cmds.rowLayout(nc=1, adj=1, cat=(1, "both", 6))
        cmds.button(label="Close", h=20, c=lambda *_: self._close())
        cmds.setParent("..")
        cmds.separator(h=6, style="none")

        if use_workspace:
            cmds.evalDeferred(
                lambda: cmds.workspaceControl(
                    WORKSPACE, e=True, floating=True,
                    resizeWidth=UI_WIDTH, resizeHeight=UI_HEIGHT,
                ) if cmds.workspaceControl(WORKSPACE, exists=True) else None
            )
            cmds.evalDeferred(lambda: self._refresh_scroll())
        else:
            cmds.showWindow(WIN)
            cmds.window(WIN, e=True, widthHeight=(UI_WIDTH, UI_HEIGHT))
            cmds.evalDeferred(lambda: self._refresh_scroll())

    # =================================================================
    #  CAPTURE
    # =================================================================
    def _on_capture(self):
        af = _checked_attrs()
        ok = self.cache.capture(attr_filter=af)
        if ok:
            for s in (S_N_SLIDER, S_NB_SLIDER, S_SC_SLIDER, S_E_SLIDER, S_EB_SLIDER):
                cmds.floatSlider(s, e=True, v=0)
            for f in (S_N_FIELD, S_NB_FIELD, S_SC_FIELD, S_E_FIELD, S_EB_FIELD):
                cmds.floatField(f, e=True, v=0)
            self._refresh_scroll()
        else:
            cmds.warning("CNG: No valid keys found.")

    # =================================================================
    #  Generic drag / end helpers
    # =================================================================
    def _begin_undo(self, name):
        if not self._drag:
            cmds.undoInfo(openChunk=True, chunkName=name)
            self._drag = True

    def _end_undo(self):
        if self._drag:
            self._drag = False
            cmds.undoInfo(closeChunk=True)

    def _snap_release(self, slider, field):
        cmds.floatSlider(slider, e=True, v=0)
        cmds.floatField(field, e=True, v=0)
        self._release()

    # =================================================================
    #  NOISE
    # =================================================================
    def _noise_range(self):
        lo, hi = self._nmin(), self._nmax()
        cmds.floatSlider(S_N_SLIDER, e=True, min=lo, max=hi)
        cmds.floatField(S_N_FIELD, e=True, minValue=lo, maxValue=hi)

    def _noise_drag(self, v):
        self._slider_to_field(S_N_SLIDER, S_N_FIELD, v)
        if not self._auto_cap(): return
        self._begin_undo("CNG Noise")
        apply_noise(self.cache, v, taper=_qcb(S_N_TAPER))

    def _noise_end(self, v):
        self._slider_to_field(S_N_SLIDER, S_N_FIELD, v)
        if self.cache.ok() and v != 0.0:
            self._begin_undo("CNG Noise")
            apply_noise(self.cache, v, taper=_qcb(S_N_TAPER))
        self._end_undo()
        self._snap_release(S_N_SLIDER, S_N_FIELD)

    def _noise_reset(self):
        cmds.floatSlider(S_N_SLIDER, e=True, v=0)
        cmds.floatField(S_N_FIELD, e=True, v=0)
        if self.cache.ok():
            cmds.undoInfo(openChunk=True, chunkName="CNG Reset Noise")
            _write_base(self.cache)
            cmds.undoInfo(closeChunk=True)
        self._release()

    # =================================================================
    #  NOISE BUILD
    # =================================================================
    def _noise_build_range(self):
        lo, hi = self._nbmin(), self._nbmax()
        cmds.floatSlider(S_NB_SLIDER, e=True, min=lo, max=hi)
        cmds.floatField(S_NB_FIELD, e=True, minValue=lo, maxValue=hi)

    def _noise_build_drag(self, v):
        self._slider_to_field(S_NB_SLIDER, S_NB_FIELD, v)
        if not self._auto_cap(): return
        self._begin_undo("CNG Noise Build")
        apply_noise_build(self.cache, v)

    def _noise_build_end(self, v):
        self._slider_to_field(S_NB_SLIDER, S_NB_FIELD, v)
        if self.cache.ok() and v != 0.0:
            self._begin_undo("CNG Noise Build")
            apply_noise_build(self.cache, v)
        self._end_undo()
        self._snap_release(S_NB_SLIDER, S_NB_FIELD)

    def _noise_build_reset(self):
        cmds.floatSlider(S_NB_SLIDER, e=True, v=0)
        cmds.floatField(S_NB_FIELD, e=True, v=0)
        if self.cache.ok():
            cmds.undoInfo(openChunk=True, chunkName="CNG Reset Noise Build")
            _write_base(self.cache)
            cmds.undoInfo(closeChunk=True)
        self._release()

    # =================================================================
    #  SCALE
    # =================================================================
    def _scale_range(self):
        lo, hi = self._scmin(), self._scmax()
        cmds.floatSlider(S_SC_SLIDER, e=True, min=lo, max=hi)
        cmds.floatField(S_SC_FIELD, e=True, minValue=lo, maxValue=hi)

    def _scale_drag(self, v):
        self._slider_to_field(S_SC_SLIDER, S_SC_FIELD, v)
        if not self._auto_cap(): return
        self._begin_undo("CNG Scale")
        apply_scale(self.cache, v, self._scmin(), self._scmax(),
                    both_sides=_qcb(S_SC_BOTH))

    def _scale_end(self, v):
        self._slider_to_field(S_SC_SLIDER, S_SC_FIELD, v)
        if self.cache.ok() and v != 0.0:
            self._begin_undo("CNG Scale")
            apply_scale(self.cache, v, self._scmin(), self._scmax(),
                        both_sides=_qcb(S_SC_BOTH))
        self._end_undo()
        self._snap_release(S_SC_SLIDER, S_SC_FIELD)

    def _scale_reset(self):
        cmds.floatSlider(S_SC_SLIDER, e=True, v=0)
        cmds.floatField(S_SC_FIELD, e=True, v=0)
        if self.cache.ok():
            cmds.undoInfo(openChunk=True, chunkName="CNG Reset Scale")
            _write_base(self.cache)
            cmds.undoInfo(closeChunk=True)
        self._release()

    # =================================================================
    #  EASE
    # =================================================================
    def _ease_range(self):
        lo, hi = self._emin(), self._emax()
        cmds.floatSlider(S_E_SLIDER, e=True, min=lo, max=hi)
        cmds.floatField(S_E_FIELD, e=True, minValue=lo, maxValue=hi)

    def _ease_drag(self, v):
        self._slider_to_field(S_E_SLIDER, S_E_FIELD, v)
        if not self._auto_cap(): return
        self._begin_undo("CNG Ease")
        apply_ease(self.cache, v, self._emin(), self._emax())

    def _ease_end(self, v):
        self._slider_to_field(S_E_SLIDER, S_E_FIELD, v)
        if self.cache.ok() and v != 0.0:
            self._begin_undo("CNG Ease")
            apply_ease(self.cache, v, self._emin(), self._emax())
        self._end_undo()
        self._snap_release(S_E_SLIDER, S_E_FIELD)

    def _ease_reset(self):
        cmds.floatSlider(S_E_SLIDER, e=True, v=0)
        cmds.floatField(S_E_FIELD, e=True, v=0)
        if self.cache.ok():
            cmds.undoInfo(openChunk=True, chunkName="CNG Reset Ease")
            _write_base(self.cache)
            cmds.undoInfo(closeChunk=True)
        self._release()

    # =================================================================
    #  EASE BOTH
    # =================================================================
    def _ease_both_range(self):
        lo, hi = self._ebmin(), self._ebmax()
        cmds.floatSlider(S_EB_SLIDER, e=True, min=lo, max=hi)
        cmds.floatField(S_EB_FIELD, e=True, minValue=lo, maxValue=hi)

    def _ease_both_drag(self, v):
        self._slider_to_field(S_EB_SLIDER, S_EB_FIELD, v)
        if not self._auto_cap(): return
        self._begin_undo("CNG Ease Both")
        apply_ease_both(self.cache, v, self._ebmin(), self._ebmax())

    def _ease_both_end(self, v):
        self._slider_to_field(S_EB_SLIDER, S_EB_FIELD, v)
        if self.cache.ok() and v != 0.0:
            self._begin_undo("CNG Ease Both")
            apply_ease_both(self.cache, v, self._ebmin(), self._ebmax())
        self._end_undo()
        self._snap_release(S_EB_SLIDER, S_EB_FIELD)

    def _ease_both_reset(self):
        cmds.floatSlider(S_EB_SLIDER, e=True, v=0)
        cmds.floatField(S_EB_FIELD, e=True, v=0)
        if self.cache.ok():
            cmds.undoInfo(openChunk=True, chunkName="CNG Reset Ease Both")
            _write_base(self.cache)
            cmds.undoInfo(closeChunk=True)
        self._release()

    # =================================================================
    #  RESTORE / CLOSE
    # =================================================================
    def _on_restore(self):
        for s in (S_N_SLIDER, S_NB_SLIDER, S_SC_SLIDER, S_E_SLIDER, S_EB_SLIDER):
            cmds.floatSlider(s, e=True, v=0)
        for f in (S_N_FIELD, S_NB_FIELD, S_SC_FIELD, S_E_FIELD, S_EB_FIELD):
            cmds.floatField(f, e=True, v=0)
        if self.cache.ok():
            cmds.undoInfo(openChunk=True, chunkName="CNG Restore")
            _write_base(self.cache)
            cmds.undoInfo(closeChunk=True)
        self._release()

    def _close(self):
        if cmds.workspaceControl(WORKSPACE, exists=True):
            cmds.deleteUI(WORKSPACE)
        elif cmds.window(WIN, exists=True):
            cmds.deleteUI(WIN, window=True)


# ===================================================================
#  Launch
# ===================================================================

def launch():
    return CurveNoiseGenUI()

if __name__ == "__main__":
    launch()
