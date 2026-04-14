"""Entry-point for the Maya Time Bookmarks tool.

Call ``launch()`` from Maya's Script Editor or a shelf button::

    import time_bookmarks.main
    time_bookmarks.main.launch()

Re-entrant safe: calling ``launch()`` when the panel is already open simply
raises the existing window rather than creating a duplicate.

Outside Maya (CI, ``dev_launch.py``) the function falls back to the dev
launcher, which uses in-memory fakes.
"""

from __future__ import annotations


def launch() -> None:
    """Detect the execution context and start the appropriate launcher."""
    try:
        import maya.cmds  # noqa: F401  — presence check only
        _launch_in_maya()
    except ImportError:
        from time_bookmarks.dev_launch import main
        main()


# ---------------------------------------------------------------------------
# Maya-specific wiring
# ---------------------------------------------------------------------------

def _launch_in_maya() -> None:
    """Wire real Maya adapters, apply the singleton guard, show the panel."""
    from time_bookmarks.qt_compat import QtWidgets
    from time_bookmarks.core.bookmark_service import BookmarkService
    from time_bookmarks.core.controller import BookmarkController
    from time_bookmarks.maya.adapter import MayaTimeAdapter
    from time_bookmarks.maya.persistence import MayaScenePersistence
    from time_bookmarks.maya.qt_bridge import MayaQtBridge
    from time_bookmarks.ui.bookmark_panel import BookmarkPanel

    # ---- Singleton guard ------------------------------------------------
    app = QtWidgets.QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            if widget.objectName() == "MayaTimeBookmarksPanel" and widget.isVisible():
                widget.raise_()
                widget.activateWindow()
                return

    # ---- Adapters -------------------------------------------------------
    try:
        maya_parent = MayaQtBridge.get_maya_main_window()
    except Exception:
        maya_parent = None

    service = BookmarkService()
    controller = BookmarkController(
        service=service,
        time_adapter=MayaTimeAdapter(),
        persistence=MayaScenePersistence(),
    )

    # ---- Panel ----------------------------------------------------------
    panel = BookmarkPanel(controller=controller, parent=maya_parent)

    # Load any bookmarks saved with the current scene before showing the panel.
    controller.load_from_scene()

    # ---- Timeline overlay + input filter --------------------------------
    _install_timeline_components(controller, panel)

    panel.show()


def _install_timeline_components(controller, panel) -> None:
    """Attach the overlay and event filter to the Maya timeline widget.

    Wrapped in a try/except so that a failure here never prevents the
    main panel from opening — the tool degrades gracefully to panel-only
    mode if the timeline widget cannot be found.
    """
    try:
        from time_bookmarks.maya.qt_bridge import MayaQtBridge
        from time_bookmarks.maya.input_filter import TimelineEventFilter
        from time_bookmarks.ui.timeline_overlay import TimelineOverlay

        timeline_widget = MayaQtBridge.get_timeline_widget()

        # ---- Event filter -----------------------------------------------
        event_filter = TimelineEventFilter(parent=timeline_widget)
        timeline_widget.installEventFilter(event_filter)

        # Wire each shortcut signal to the appropriate handler.
        event_filter.create_requested.connect(panel.open_create_dialog)
        event_filter.navigate_next_requested.connect(controller.navigate_next)
        event_filter.navigate_prev_requested.connect(controller.navigate_prev)
        event_filter.jump_requested.connect(
            controller.jump_to_bookmark_at_current_frame
        )
        event_filter.remove_requested.connect(controller.remove_at_current_frame)
        event_filter.panel_requested.connect(panel.show)
        event_filter.visibility_requested.connect(controller.toggle_visibility)

        # ---- Overlay ----------------------------------------------------
        overlay = TimelineOverlay(parent_widget=timeline_widget)

        def _refresh_overlay() -> None:
            bookmarks = controller.list_bookmarks()
            frame_range = controller.get_playback_range()
            overlay.set_bookmarks(bookmarks, frame_range)

        # Update overlay whenever bookmarks change.
        controller.on_bookmarks_changed(_refresh_overlay)

        # Connect visibility toggle to the overlay.
        if controller.notifier is not None:
            controller.notifier.visibility_changed.connect(overlay.set_visible)

        # Initial paint.
        _refresh_overlay()

    except Exception as exc:  # pragma: no cover
        import warnings
        warnings.warn(
            f"time_bookmarks: could not install timeline components: {exc}",
            stacklevel=2,
        )


if __name__ == "__main__":
    launch()
