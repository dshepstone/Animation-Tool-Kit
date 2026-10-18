"""Follow Maya keyframe deltas without adding commands to the undo queue.

API 1.0 is intentional: it exposes the MFnKeyframeDelta function sets on all
supported Maya versions. Callbacks are owned by KeyTracker and removed on stop.
"""
import json


def follow_edits(marks, events, removed, key_times, restoring=False):
    """Apply exact key edits; batches move from a snapshot to avoid collisions.

    Events are (operation, curve UUID, old time token, new time token). Deleted
    records live only in the session's undo history, never in the saved marks.
    key_times includes unlabelled keys so overlapping group moves are distinct
    from successive moves of the same key before Maya's next idle event.
    """
    marks = dict(marks)
    pending = []

    def identity(uuid, time):
        return uuid + "@" + time

    def commit_moves():
        previous = dict(marks)
        for uuid, old, new in pending:
            marks.pop(identity(uuid, old), None)
            key_times.setdefault(uuid, set()).discard(old)
        for uuid, old, new in pending:
            label = previous.get(identity(uuid, old))
            if label is not None:
                marks[identity(uuid, new)] = label
            key_times.setdefault(uuid, set()).add(new)
        pending.clear()

    for operation, uuid, old, new in events:
        if operation == "move":
            if old == new:
                continue
            duplicate = any(u == uuid and o == old for u, o, n in pending)
            chained = (old not in key_times.get(uuid, set()) and
                       any(u == uuid and n == old for u, o, n in pending))
            if duplicate or chained:
                commit_moves()
            pending.append((uuid, old, new))
            continue
        commit_moves()
        token = old if operation == "remove" else new
        key = identity(uuid, token)
        if operation == "remove":
            removed.setdefault(key, []).append(marks.pop(key, None))
            key_times.setdefault(uuid, set()).discard(token)
        elif operation == "add":
            # A newly created key never inherits a deleted key's old label.
            if restoring and removed.get(key):
                marks.pop(key, None)
                label = removed[key].pop()
                if label is not None:
                    marks[key] = label
            elif not restoring:
                marks.pop(key, None)
            key_times.setdefault(uuid, set()).add(token)
    commit_moves()
    return marks


class KeyTracker:
    def __init__(self, store, cmds):
        import maya.OpenMaya as om
        import maya.OpenMayaAnim as oma
        self.om, self.oma = om, oma
        self.store, self.cmds = store, cmds
        self.callbacks = []
        self.removed = {}
        self.deleted_curves = {}
        self.key_times = {}
        self.suspended = False
        self.restoring = False
        self._busy = False
        self._last_error = None

    @staticmethod
    def token(time):
        import maya.OpenMaya as om
        return "%.9f" % time.asUnits(om.MTime.kSeconds)

    def _warning(self, exc):
        if str(exc) != self._last_error:
            self.cmds.warning("Timeline Ticks tracking: " + str(exc))
            self._last_error = str(exc)

    def _write(self, marks):
        node = self.store.node()
        if node is None:
            return
        # No cmds.setAttr here: the user's key edit must remain the next Undo.
        selection = self.om.MSelectionList()
        selection.add(node)
        obj = self.om.MObject()
        selection.getDependNode(0, obj)
        plug = self.om.MFnDependencyNode(obj).findPlug("atkTimelineTicks", False)
        plug.setString(json.dumps({"version": 1, "marks": marks}, sort_keys=True))

    def capture(self):
        """Snapshot all keys on annotated curves, including unselected curves."""
        for identity in self.store.read():
            uuid = identity.split("@", 1)[0]
            if uuid in self.key_times:
                continue
            nodes = self.cmds.ls(uuid) or []
            if nodes:
                times = self.cmds.keyframe(nodes[0], q=True, timeChange=True) or []
                self.key_times[uuid] = {"%.9f" % self.om.MTime(t, self.om.MTime.uiUnit()).asUnits(
                    self.om.MTime.kSeconds) for t in times}

    def start(self):
        if self.callbacks:
            return self
        self.flush()  # Do not replay edits that happened before tracking began.
        om, oma = self.om, self.oma
        try:
            self.callbacks.append(oma.MAnimMessage.addAnimKeyframeEditedCallback(self._edited))
            self.callbacks.append(om.MEventMessage.addEventCallback("Undo", self._undo_redo))
            self.callbacks.append(om.MEventMessage.addEventCallback("Redo", self._undo_redo))
            self.callbacks.append(om.MDGMessage.addNodeRemovedCallback(self._node_removed, "animCurve"))
            self.callbacks.append(om.MDGMessage.addNodeAddedCallback(self._node_added, "animCurve"))
            for event in (om.MSceneMessage.kBeforeNew, om.MSceneMessage.kBeforeOpen,
                          om.MSceneMessage.kBeforeImport):
                self.callbacks.append(om.MSceneMessage.addCallback(event, self._before_scene))
            for event in (om.MSceneMessage.kAfterNew, om.MSceneMessage.kAfterOpen,
                          om.MSceneMessage.kAfterImport):
                self.callbacks.append(om.MSceneMessage.addCallback(event, self._after_scene))
            self.callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave, self.flush))
            self.capture()
        except Exception:
            self.stop()
            raise
        return self

    def stop(self):
        self.flush()
        for callback in self.callbacks:
            self.om.MMessage.removeCallback(callback)
        self.callbacks.clear()

    def flush(self, *args):
        if not self._busy:
            self.oma.MAnimMessage.flushAnimKeyframeEditedCallbacks()

    def _undo_redo(self, *args):
        self.restoring = True
        try:
            self.flush()
        finally:
            self.restoring = False

    def _before_scene(self, *args):
        self.flush()
        self.suspended = True

    def _after_scene(self, *args):
        self.flush()  # Discard deltas emitted by reading a file.
        self.removed.clear()
        self.deleted_curves.clear()
        self.key_times.clear()
        self.suspended = False
        try:
            self.capture()
        except Exception as exc:
            self._warning(exc)

    def _edited(self, deltas, *args):
        if self.suspended or self._busy or not self.key_times:
            return
        self._busy = True
        try:
            marks = self.store.read()
            if not marks and not self.key_times:
                return
            events = []
            for index in range(deltas.length()):
                obj = deltas[index]
                base = self.oma.MFnKeyframeDelta(obj)
                try:
                    uuid = self.om.MFnDependencyNode(base.paramCurve()).uuid().asString()
                except RuntimeError:
                    continue  # A deleted curve is handled by the DG callback.
                if uuid not in self.key_times or uuid in self.deleted_curves:
                    continue
                kind = obj.apiType()
                if kind == self.om.MFn.kKeyframeDeltaMove:
                    change = self.oma.MFnKeyframeDeltaMove(obj)
                    events.append(("move", uuid, self.token(change.previousTime()),
                                   self.token(change.currentTime())))
                elif kind == self.om.MFn.kKeyframeDeltaAddRemove:
                    change = self.oma.MFnKeyframeDeltaAddRemove(obj)
                    token = self.token(change.time())
                    if change.deltaType() == change.kRemoved:
                        events.append(("remove", uuid, token, token))
                    elif change.deltaType() == change.kAdded:
                        events.append(("add", uuid, token, token))
                elif kind == self.om.MFn.kKeyframeDeltaBlockAddRemove:
                    change = self.oma.MFnKeyframeDeltaBlockAddRemove(obj)
                    times = self.om.MTimeArray()
                    change.getTimes(times)
                    operation = "remove" if change.deltaType() == change.kRemoved else "add"
                    events.extend((operation, uuid, self.token(times[i]), self.token(times[i]))
                                  for i in range(times.length()))
            updated = follow_edits(marks, events, self.removed, self.key_times, self.restoring)
            if updated != marks:
                self._write(updated)
            self._last_error = None
        except Exception as exc:
            self._warning(exc)
        finally:
            self._busy = False

    def _node_removed(self, obj, *args):
        if self.suspended:
            return
        try:
            uuid = self.om.MFnDependencyNode(obj).uuid().asString()
            if uuid not in self.key_times:
                return
            marks = self.store.read()
            deleted = {k: v for k, v in marks.items() if k.startswith(uuid + "@")}
            if deleted:
                self.deleted_curves[uuid] = deleted
                self._write({k: v for k, v in marks.items() if k not in deleted})
        except Exception as exc:
            self._warning(exc)

    def _node_added(self, obj, *args):
        if self.suspended or not self.deleted_curves:
            return
        try:
            uuid = self.om.MFnDependencyNode(obj).uuid().asString()
            # Undo restores the same curve UUID; a new curve gets a fresh UUID.
            deleted = self.deleted_curves.pop(uuid, None)
            if deleted:
                marks = self.store.read()
                marks.update(deleted)
                self._write(marks)
        except Exception as exc:
            self._warning(exc)
