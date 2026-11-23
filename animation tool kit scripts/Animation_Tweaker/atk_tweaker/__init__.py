"""Animation Tweaker for the Animation Tool Kit.

Sculpt corrections and polish onto animated meshes after the skin. Every
tweak lives as a target on one post-deformation blendShape per mesh.

    import atk_tweaker
    atk_tweaker.show()

The engine modules (``engine``, ``effects``, ``surface_handle``,
``utilities``, ``cache_versions``) have no UI and can be scripted directly.
"""
import sys

__version__ = "1.2.1"


def show():
    """Open (or raise) the dockable window inside Maya."""
    from .ui import show as open_window
    return open_window()


def shutdown():
    """Called by ATK before Reload Scripts and when Maya quits."""
    ui = sys.modules.get(__name__ + ".ui")
    if ui is not None:
        ui.close()


# Right-click menu actions on the toolbar button. Each reports problems as a
# Maya warning instead of raising into the toolbar.

def _quiet(fn, *args):
    from maya import cmds
    try:
        return fn(*args)
    except Exception as error:
        cmds.warning("Animation Tweaker: %s" % error)
        return None


def toggle_smooth_preview():
    from . import utilities
    return _quiet(utilities.toggle_smooth_preview)


def cycle_camera():
    from . import utilities
    return _quiet(utilities.cycle_camera, True)


def commit_sculpt():
    from . import engine
    return _quiet(engine.commit_sculpt)


def cancel_sculpt():
    from . import engine
    return _quiet(engine.cancel_sculpt)
