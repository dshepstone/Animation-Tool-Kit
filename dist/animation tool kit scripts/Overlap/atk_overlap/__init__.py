"""ATK's isolated Overlap package, with a UI-independent simulation API."""

__version__ = "0.5.0"


def show():
    """Open the standalone dockable window inside Maya."""
    from .ui import show as open_window
    return open_window()


def create_session(controls, settings=None):
    """ATK integration entry point. Does not construct UI or change animation."""
    from .maya_engine import Session
    from .settings import Settings
    return Session(controls, settings or Settings())
