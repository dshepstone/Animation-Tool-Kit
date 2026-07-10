"""Maya hotkey setup for the Blue Pencil Flipbook Manager.

Bindings are applied through Maya's full hotkey chain — a runtime command, a
nameCommand wrapper, and the key binding itself — and saved with
``savePrefs(hotkeys=True)`` so they survive restarts. Maya locks the built-in
'Maya_Default' hotkey set, so a writable custom set is selected (or created,
sourced from Maya_Default so existing hotkeys carry over) before anything is
bound.

Default bindings live in DEFAULTS. A user can customize them in the Hotkeys
editor; their choices are persisted to a JSON file in the Maya prefs folder.
"""

from __future__ import annotations

import copy
import json
import os

try:
    from maya import cmds
except Exception:
    cmds = None

# Shown under "Custom Scripts" in Maya's own Hotkey Editor.
CATEGORY = "Custom Scripts.Blue Pencil Flipbook"
LOCKED_HOTKEY_SET = "Maya_Default"
CREATE_NEW_SET_LABEL = "< Create New Set >"

# name -> binding. Each binding: label, command (python), key, ctrl, alt, shift.
# Keys are lowercase; Shift is always an explicit modifier flag, never an
# uppercase key, because Maya treats an uppercase keyShortcut as Shift+key.
DEFAULTS = {
    "BPFToggleManager": {"label": "Toggle Blue Pencil Flipbook Manager", "command": "import blue_pencil_flipbook.launch as bp; bp.show()", "key": "b", "ctrl": True, "alt": True, "shift": False},
    "BPFResetTool": {"label": "Reset Blue Pencil Tool", "command": "from blue_pencil_flipbook import maya_blue_pencil_api as a; a.reset_tool()", "key": "r", "ctrl": False, "alt": True, "shift": False},
    "BPFPreviousDrawing": {"label": "Previous Drawing", "command": "import blue_pencil_flipbook.launch as bp; bp.previous_drawing()", "key": ",", "ctrl": False, "alt": True, "shift": False},
    "BPFNextDrawing": {"label": "Next Drawing", "command": "import blue_pencil_flipbook.launch as bp; bp.next_drawing()", "key": ".", "ctrl": False, "alt": True, "shift": False},
    "BPFPlayKeysOnly": {"label": "Play Keys Only", "command": "import blue_pencil_flipbook.launch as bp; bp.play_mode('Keys Only')", "key": "1", "ctrl": False, "alt": True, "shift": False},
    "BPFPlayKeysBreakdowns": {"label": "Play Keys + Breakdowns", "command": "import blue_pencil_flipbook.launch as bp; bp.play_mode('Keys + Breakdowns')", "key": "2", "ctrl": False, "alt": True, "shift": False},
    "BPFPlayAll": {"label": "Play All Drawings", "command": "import blue_pencil_flipbook.launch as bp; bp.play_mode('All Drawings')", "key": "3", "ctrl": False, "alt": True, "shift": False},
    "BPFMarkKey": {"label": "Mark Current Drawing as Key", "command": "import blue_pencil_flipbook.launch as bp; bp.mark_current('KEY')", "key": "1", "ctrl": True, "alt": False, "shift": False},
    "BPFMarkBreakdown": {"label": "Mark Current Drawing as Breakdown", "command": "import blue_pencil_flipbook.launch as bp; bp.mark_current('BREAKDOWN')", "key": "2", "ctrl": True, "alt": False, "shift": False},
    "BPFMarkInbetween": {"label": "Mark Current Drawing as Inbetween", "command": "import blue_pencil_flipbook.launch as bp; bp.mark_current('INBETWEEN')", "key": "3", "ctrl": True, "alt": False, "shift": False},
}

# Order for display in the editor.
ORDER = list(DEFAULTS.keys())


def _warn(message):
    if cmds:
        cmds.warning("Blue Pencil Flipbook Manager: " + message)
    else:
        print("Blue Pencil Flipbook Manager: " + message)


def _store_path():
    if cmds:
        try:
            base = cmds.internalVar(userPrefDir=True)
        except Exception:
            base = os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    folder = os.path.join(base, "blue_pencil_flipbook")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "hotkeys.json")


def _normalize_key(key):
    key = (key or "").strip()
    return key.lower() if len(key) == 1 else key


def default_bindings():
    return copy.deepcopy(DEFAULTS)


def load_bindings():
    """Return saved bindings merged over the defaults (defaults fill any gaps)."""
    bindings = default_bindings()
    try:
        path = _store_path()
        if os.path.exists(path):
            with open(path) as handle:
                saved = json.load(handle)
            for name, binding in (saved or {}).items():
                if name in bindings and isinstance(binding, dict):
                    bindings[name].update({k: binding[k] for k in ("key", "ctrl", "alt", "shift") if k in binding})
    except Exception as exc:
        _warn("Could not read saved hotkeys: {0}".format(exc))
    for binding in bindings.values():
        binding["key"] = _normalize_key(binding.get("key"))
    return bindings


def save_bindings(bindings):
    try:
        with open(_store_path(), "w") as handle:
            json.dump(bindings, handle, indent=2, sort_keys=True)
        return True
    except Exception as exc:
        _warn("Could not save hotkeys: {0}".format(exc))
        return False


def display_string(binding):
    """Return a human-readable string like 'Ctrl+Alt+B'."""
    display = ""
    if binding.get("ctrl"):
        display += "Ctrl+"
    if binding.get("alt"):
        display += "Alt+"
    if binding.get("shift"):
        display += "Shift+"
    key = _normalize_key(binding.get("key"))
    display += key.upper() if len(key) == 1 else key
    return display


# ── Hotkey set management ────────────────────────────────────────────────────
# Maya 2016+ locks Maya_Default: cmds.hotkey() errors while it is the current
# set, which is why bindings silently never appeared. Every apply/remove first
# switches to (or creates) a writable custom set.

def current_hotkey_set():
    try:
        return cmds.hotkeySet(query=True, current=True)
    except Exception:
        return ""


def custom_hotkey_sets():
    all_sets = cmds.hotkeySet(query=True, hotkeySetArray=True) or []
    return [s for s in all_sets if s != LOCKED_HOTKEY_SET]


def activate_hotkey_set(name):
    cmds.hotkeySet(name, edit=True, current=True)
    print("Blue Pencil Flipbook: switched to hotkey set '{0}'".format(name))
    return name


def prompt_create_hotkey_set():
    """Prompt the user to name and create a new hotkey set.

    The set is sourced from Maya_Default so existing hotkeys carry over.
    Returns the new set name, or None if cancelled.
    """
    result = cmds.promptDialog(
        title="Create Hotkey Set",
        message=(
            "The default 'Maya_Default' hotkey set is locked and cannot\n"
            "be modified.  Enter a name for a new custom hotkey set:"
        ),
        button=["Create", "Cancel"],
        defaultButton="Create",
        cancelButton="Cancel",
        text="Custom",
    )
    if result != "Create":
        return None
    name = (cmds.promptDialog(query=True, text=True) or "").strip()
    if not name:
        _warn("hotkey set name cannot be empty.")
        return None
    if cmds.hotkeySet(name, exists=True):
        return activate_hotkey_set(name)
    cmds.hotkeySet(name, source=LOCKED_HOTKEY_SET)
    return activate_hotkey_set(name)


def ensure_writable_hotkey_set():
    """Make sure the current hotkey set is writable (not Maya_Default).

    If Maya_Default is active, prompt the user to choose an existing custom
    set or create a new one. Returns the name of the active writable set, or
    None if the user cancels.
    """
    if cmds is None:
        return None
    current = current_hotkey_set()
    if current and current != LOCKED_HOTKEY_SET:
        return current
    custom_sets = custom_hotkey_sets()
    if not custom_sets:
        return prompt_create_hotkey_set()
    try:
        from . import ui_hotkeys
        choice = ui_hotkeys.select_hotkey_set(custom_sets)
    except Exception:
        choice = custom_sets[0]
    if choice is None:
        return None
    if choice == CREATE_NEW_SET_LABEL:
        return prompt_create_hotkey_set()
    return activate_hotkey_set(choice)


# ── Runtime commands ─────────────────────────────────────────────────────────

def ensure_runtime_commands(bindings=None):
    """Register (or update) an editable runtime command per action.

    Commands appear in Maya's Hotkey Editor under 'Custom Scripts'.
    """
    bindings = bindings or load_bindings()
    for name in ORDER:
        binding = bindings.get(name)
        if not binding:
            continue
        runtime = name + "Runtime"
        label = binding.get("label", name)
        code = binding.get("command", "")
        try:
            if cmds.runTimeCommand(runtime, exists=True):
                cmds.runTimeCommand(runtime, edit=True, command=code, commandLanguage="python")
            else:
                cmds.runTimeCommand(runtime, annotation=label, category=CATEGORY,
                                    commandLanguage="python", command=code)
        except RuntimeError:
            # A stale copy from an older install may have been created with
            # default=True, which Maya refuses to edit. Recreate it.
            try:
                cmds.runTimeCommand(runtime, edit=True, delete=True)
                cmds.runTimeCommand(runtime, annotation=label, category=CATEGORY,
                                    commandLanguage="python", command=code)
            except Exception as exc:
                _warn("could not register runtime command {0}: {1}".format(runtime, exc))


# ── Hotkey assignment ────────────────────────────────────────────────────────

def assign_hotkey(name, binding):
    """Assign one action's keyboard shortcut.

    Caller must ensure a writable hotkey set is active and runtime commands
    are registered. Returns True if assigned, False if skipped (no key, or
    the user declined to overwrite a conflicting binding).
    """
    key = _normalize_key(binding.get("key"))
    if not key:
        return False
    ctrl = bool(binding.get("ctrl"))
    alt = bool(binding.get("alt"))
    shift = bool(binding.get("shift"))
    runtime = name + "Runtime"
    nc_name = name + "NameCommand"
    label = binding.get("label", name)
    display = display_string(binding)

    # Check for an existing binding on the same combo.
    query_kw = {}
    if ctrl:
        query_kw["ctl"] = True
    if alt:
        query_kw["alt"] = True
    if shift:
        query_kw["sht"] = True
    try:
        existing = cmds.hotkey(key, query=True, name=True, **query_kw)
    except Exception:
        existing = ""
    if existing and existing != nc_name:
        result = cmds.confirmDialog(
            title="Hotkey Conflict",
            message=(
                "'{0}' is already assigned to:\n{1}\n\n"
                "Overwrite with {2}?".format(display, existing, label)
            ),
            button=["Overwrite", "Cancel"],
            defaultButton="Cancel",
            cancelButton="Cancel",
        )
        if result != "Overwrite":
            return False

    # nameCommand wraps the runtime command; the binding points at it.
    cmds.nameCommand(nc_name, annotation=label, sourceType="mel", command=runtime)
    hotkey_kw = {"keyShortcut": key, "name": nc_name, "ctrlModifier": ctrl, "altModifier": alt}
    try:
        cmds.hotkey(shiftModifier=shift, **hotkey_kw)
    except TypeError:
        # Older Maya builds lack shiftModifier; bind without it.
        cmds.hotkey(**hotkey_kw)
    print("Blue Pencil Flipbook: hotkey '{0}' -> {1}".format(display, runtime))
    return True


def apply_bindings(bindings, persist=True):
    """Apply a full set of bindings through the Maya hotkey chain.

    Returns (applied, skipped) counts, or None if the user cancelled the
    writable-hotkey-set step.
    """
    if cmds is None:
        return None
    if ensure_writable_hotkey_set() is None:
        return None
    ensure_runtime_commands(bindings)
    applied = 0
    skipped = 0
    for name in ORDER:
        binding = bindings.get(name)
        if not binding or not _normalize_key(binding.get("key")):
            continue
        try:
            if assign_hotkey(name, binding):
                applied += 1
            else:
                skipped += 1
        except Exception as exc:
            skipped += 1
            _warn("could not bind {0}: {1}".format(name, exc))
    try:
        cmds.savePrefs(hotkeys=True)
    except Exception:
        pass
    if persist:
        save_bindings(bindings)
    return applied, skipped


def remove_hotkeys(bindings=None):
    """Unbind the tool's hotkeys (the runtime commands stay registered)."""
    if cmds is None:
        return False
    if ensure_writable_hotkey_set() is None:
        return False
    bindings = bindings or load_bindings()
    for name in ORDER:
        binding = bindings.get(name)
        if not binding:
            continue
        key = _normalize_key(binding.get("key"))
        if not key:
            continue
        kwargs = dict(keyShortcut=key, name="",
                      ctrlModifier=bool(binding.get("ctrl")),
                      altModifier=bool(binding.get("alt")))
        try:
            try:
                cmds.hotkey(shiftModifier=bool(binding.get("shift")), **kwargs)
            except TypeError:
                cmds.hotkey(**kwargs)
        except Exception as exc:
            _warn("could not unbind {0}: {1}".format(name, exc))
    try:
        cmds.savePrefs(hotkeys=True)
    except Exception:
        pass
    return True


def create_default_hotkeys():
    return apply_bindings(load_bindings())


def reset_default_hotkeys():
    if remove_hotkeys(load_bindings()) is False:
        return None
    defaults = default_bindings()
    return apply_bindings(defaults)
