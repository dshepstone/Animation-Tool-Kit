"""Entry-point for the Maya Time Bookmarks tool.

Call ``launch()`` from Maya's Script Editor or a shelf button::

    import time_bookmarks.main
    time_bookmarks.main.launch()

Re-entrant safe: calling ``launch()`` when the panel is already open simply
raises the existing window rather than creating a duplicate.  Any previous
session's timeline overlay, event filter, and scriptJobs are torn down
before new ones are installed, so repeated launches never accumulate
orphaned callbacks or stacked overlay widgets.

Outside Maya (CI, ``dev_launch.py``) the function falls back to the dev
launcher, which uses in-memory fakes.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Module-level session registry.
#
# Holds references to everything created by the last launch() so a relaunch
# (or panel close) can clean up deterministically.  Without this, every
# launch stacked a fresh TimelineOverlay + event filter on Maya's timeline
# widget and leaked scriptJobs.
# ---------------------------------------------------------------------------
_SESSION: dict = {
    "panel": None,
    "controller": None,
    "overlay": None,
    "event_filter": None,
    "timeline_widget": None,
    "script_jobs": [],
}


def launch() -> None:
    """Detect the execution context and start the appropriate launcher."""
    try:
        import maya.cmds  # noqa: F401  — presence check only
        _launch_in_maya()
    except ImportError:
        from time_bookmarks.dev_launch import main
        main()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _kill_script_jobs() -> None:
    """Kill every scriptJob owned by this tool. Safe to call repeatedly."""
    try:
        import maya.cmds as cmds
    except ImportError:
        _SESSION["script_jobs"] = []
        return
    for job_id in _SESSION["script_jobs"]:
        try:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        except Exception:
            pass
    _SESSION["script_jobs"] = []


def _cleanup_session() -> None:
    """Tear down overlay, event filter, and scriptJobs from a prior launch.

    Every step is individually guarded: Qt widgets may already have been
    destroyed by Maya (RuntimeError on access), and that must never abort
    the rest of the cleanup.
    """
    _kill_script_jobs()

    timeline_widget = _SESSION.get("timeline_widget")
    event_filter = _SESSION.get("event_filter")
    if timeline_widget is not None and event_filter is not None:
        try:
            timeline_widget.removeEventFilter(event_filter)
        except RuntimeError:
            pass  # underlying C++ widget already deleted
    _SESSION["event_filter"] = None
    _SESSION["timeline_widget"] = None

    overlay = _SESSION.get("overlay")
    if overlay is not None:
        try:
            overlay.hide()
            overlay.setParent(None)
            overlay.deleteLater()
        except RuntimeError:
            pass
    _SESSION["overlay"] = None


# ---------------------------------------------------------------------------
# Maya-specific wiring
# ---------------------------------------------------------------------------

def _panel_is_alive(panel) -> bool:
    """True when *panel* exists and its C++ object hasn't been destroyed."""
    if panel is None:
        return False
    try:
        panel.objectName()  # raises RuntimeError if the QWidget is dead
        return True
    except RuntimeError:
        return False


def _launch_in_maya() -> None:
    """Wire real Maya adapters, apply the singleton guard, show the panel."""
    from time_bookmarks.core.bookmark_service import BookmarkService
    from time_bookmarks.core.controller import BookmarkController
    from time_bookmarks.maya.adapter import MayaTimeAdapter
    from time_bookmarks.maya.persistence import MayaScenePersistence
    from time_bookmarks.maya.qt_bridge import MayaQtBridge
    from time_bookmarks.ui.bookmark_panel import BookmarkPanel

    # ---- Singleton guard ------------------------------------------------
    # If a previous panel is still alive (visible or merely hidden after
    # being closed), re-show it; its controller, overlay, and scriptJobs
    # are already in place.  If the overlay died (Maya UI rebuilt), the
    # timeline components are reinstalled against the live timeline.
    existing = _SESSION.get("panel")
    if _panel_is_alive(existing):
        overlay = _SESSION.get("overlay")
        overlay_ok = False
        try:
            overlay_ok = overlay is not None and overlay.parent() is not None
        except RuntimeError:
            overlay_ok = False
        if not overlay_ok:
            _cleanup_session()
            _install_timeline_components(_SESSION["controller"], existing)
        existing.show()
        existing.raise_()
        existing.activateWindow()
        return

    # A stale session (panel closed, Maya UI rebuilt, module reloaded):
    # tear everything down before building fresh components.
    _cleanup_session()

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
    _SESSION["panel"] = panel
    _SESSION["controller"] = controller

    # Load any bookmarks saved with the current scene before showing the panel.
    controller.load_from_scene()

    # ---- Timeline overlay + input filter + scriptJobs --------------------
    _install_timeline_components(controller, panel)

    panel.show()


def _install_timeline_components(controller, panel) -> None:
    """Attach the overlay, event filter, and timeline scriptJobs.

    Wrapped in a try/except so that a failure here never prevents the
    main panel from opening — the tool degrades gracefully to panel-only
    mode if the timeline widget cannot be found.
    """
    try:
        from time_bookmarks.maya.qt_bridge import MayaQtBridge
        from time_bookmarks.maya.input_filter import TimelineEventFilter
        from time_bookmarks.ui.timeline_overlay import TimelineOverlay

        timeline_widget = MayaQtBridge.get_timeline_widget()
        _SESSION["timeline_widget"] = timeline_widget

        # ---- Event filter -----------------------------------------------
        event_filter = TimelineEventFilter(parent=timeline_widget)
        timeline_widget.installEventFilter(event_filter)
        _SESSION["event_filter"] = event_filter

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
        _SESSION["overlay"] = overlay

        def _refresh_overlay() -> None:
            """Repaint markers from frame values + the *current* range.

            Re-queries the playback range every time, so bookmark pixel
            positions are always derived from stored frame numbers — never
            from a cached or visual position.
            """
            try:
                bookmarks = controller.list_bookmarks()
                frame_range = controller.get_playback_range()
                overlay.set_bookmarks(bookmarks, frame_range)
            except Exception:
                # Overlay destroyed (Maya UI rebuilt) or no scene loaded —
                # never break Maya's event loop; the next launch() rebuilds
                # the overlay and cleans up stale scriptJobs.
                pass

        # Update overlay whenever bookmarks change.
        controller.on_bookmarks_changed(_refresh_overlay)

        # Connect visibility toggle to the overlay.
        if controller.notifier is not None:
            controller.notifier.visibility_changed.connect(overlay.set_visible)

        # ---- scriptJobs: keep markers tied to the live timeline ----------
        # FIX: previously the overlay only refreshed when bookmarks changed,
        # so editing the playback range left markers at stale pixel
        # positions.  These jobs make the overlay track the timeline.
        _install_script_jobs(controller, _refresh_overlay)

        # When the panel is destroyed (closed window garbage-collected,
        # Maya shutting down), tear the whole session down so no orphaned
        # scriptJobs or overlay survive.
        panel.destroyed.connect(lambda *_: _cleanup_session())

        # Initial paint.
        _refresh_overlay()

    except Exception as exc:  # pragma: no cover
        import warnings
        warnings.warn(
            f"time_bookmarks: could not install timeline components: {exc}",
            stacklevel=2,
        )


def _install_script_jobs(controller, refresh_overlay) -> None:
    """Create the Maya scriptJobs that keep the tool in sync.

    Any previously-registered jobs are killed first so repeated installs
    can never accumulate duplicates.
    """
    import maya.cmds as cmds

    _kill_script_jobs()

    def _on_scene_changed() -> None:
        """New/opened scene: reload that scene's bookmarks, then repaint."""
        try:
            controller.load_from_scene()
        except Exception:
            pass
        refresh_overlay()

    jobs = []
    # Playback range edited via the range slider, the start/end fields,
    # or playbackOptions — reposition every marker against the new range.
    for event_name in ("playbackRangeChanged", "playbackRangeSliderChanged"):
        try:
            jobs.append(
                cmds.scriptJob(event=[event_name, refresh_overlay], protected=False)
            )
        except Exception:
            pass  # event not available in this Maya version — skip

    # Time unit changes re-scale the timeline display.
    try:
        jobs.append(
            cmds.scriptJob(event=["timeUnitChanged", refresh_overlay], protected=False)
        )
    except Exception:
        pass

    # Scene lifecycle: load the bookmarks belonging to the new scene.
    for event_name in ("SceneOpened", "NewSceneOpened"):
        try:
            jobs.append(
                cmds.scriptJob(event=[event_name, _on_scene_changed], protected=False)
            )
        except Exception:
            pass

    _SESSION["script_jobs"] = jobs


if __name__ == "__main__":
    launch()
