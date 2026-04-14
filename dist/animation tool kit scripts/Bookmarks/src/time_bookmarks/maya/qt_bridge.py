"""Maya Qt integration bridge.

Isolates every call to ``shiboken2``/``shiboken6`` and ``maya.OpenMayaUI``
so that no other module ever touches them directly.

All methods are static — there is no instance state.  Import this module only
when running inside Maya; the module itself is safe to import without Maya
(all Maya calls are deferred inside method bodies).
"""

from __future__ import annotations


class MayaQtBridge:
    """Provides Qt widget references that are anchored to Maya's own UI."""

    # ------------------------------------------------------------------
    # Window / widget access
    # ------------------------------------------------------------------

    @staticmethod
    def get_maya_main_window():
        """Return Maya's main window as a ``QWidget``.

        Works with both PySide2/shiboken2 (Maya 2022–2024) and
        PySide6/shiboken6 (Maya 2025+).
        """
        from maya.OpenMayaUI import MQtUtil

        ptr = MQtUtil.mainWindow()
        if ptr is None:
            raise RuntimeError("Could not obtain Maya main window pointer")

        return MayaQtBridge.wrap_instance(int(ptr), MayaQtBridge._q_widget_class())

    @staticmethod
    def get_timeline_widget():
        """Return the Maya timeline (``timeControl``) as a ``QWidget``.

        Uses the MEL global ``$gPlayBackSlider`` which has been the canonical
        timeline variable since Maya 2011.
        """
        import maya.mel as mel
        from maya.OpenMayaUI import MQtUtil

        # The MEL assignment is necessary to read a global into a local var.
        timeline_name: str = mel.eval("$_tmpBridge = $gPlayBackSlider")
        ptr = MQtUtil.findControl(timeline_name)
        if ptr is None:
            raise RuntimeError(
                f"Could not find Maya timeline widget '{timeline_name}'"
            )

        return MayaQtBridge.wrap_instance(int(ptr), MayaQtBridge._q_widget_class())

    # ------------------------------------------------------------------
    # Shiboken abstraction
    # ------------------------------------------------------------------

    @staticmethod
    def wrap_instance(ptr: int, cls):
        """Wrap a raw C++ pointer into a Python Qt object.

        Handles both shiboken6 (PySide6 / Maya 2025+) and
        shiboken2 (PySide2 / Maya 2022–2024) transparently.
        """
        shiboken = MayaQtBridge._shiboken()
        return shiboken.wrapInstance(ptr, cls)

    @staticmethod
    def get_qt_binding() -> str:
        """Return ``'PySide6'`` or ``'PySide2'`` depending on what Maya ships."""
        try:
            import shiboken6  # noqa: F401
            return "PySide6"
        except ImportError:
            return "PySide2"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _shiboken():
        """Return the available shiboken module."""
        try:
            import shiboken6
            return shiboken6
        except ImportError:
            import shiboken2  # type: ignore[import]
            return shiboken2

    @staticmethod
    def _q_widget_class():
        """Return ``QWidget`` from whichever Qt binding is active."""
        try:
            from PySide6.QtWidgets import QWidget
            return QWidget
        except ImportError:
            from PySide2.QtWidgets import QWidget  # type: ignore[import]
            return QWidget
