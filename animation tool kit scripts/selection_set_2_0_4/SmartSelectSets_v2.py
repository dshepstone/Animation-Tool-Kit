"""
Smart Select Sets v2.0
A more resilient Maya selection-set manager.

Key improvements over the legacy version:
- Class-based architecture instead of global state.
- Separated data model / manager / UI responsibilities.
- Schema-versioned scene and JSON persistence.
- Long DAG path storage with validation and namespace remapping helpers.
- Safer import/export and scene load handling.
- Centralized UI refresh logic.
- Reload-safe launcher.

Tested conceptually for Maya 2025+ with PySide6.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import maya.cmds as cmds
import maya.OpenMayaUI as omui
from shiboken6 import wrapInstance
from PySide6 import QtCore, QtWidgets, QtGui


TOOL_NAME = "SmartSelectSetsToolV2"
TOOL_TITLE = "Smart Select Sets"
TOOL_VERSION = "2.4.0"
SCHEMA_VERSION = 2
SCENE_NODE_NAME = "ConestogaSelectionGroupNode"
SCENE_ATTR_NAME = "groupsData"
DEFAULT_CATEGORY = "Uncategorized"
HIGHLIGHT_COLOR = [1.0, 0.95, 0.55]
HEADER_ACCENT = "#b79aff"


# ------------------------------
# Data model
# ------------------------------

@dataclass
class SelectionGroup:
    group_id: int
    name: str
    category: str
    objects: List[str] = field(default_factory=list)
    color: List[float] = field(default_factory=lambda: [0.7, 0.7, 0.7])
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SelectionGroup":
        return cls(
            group_id=int(data["group_id"]),
            name=str(data.get("name", "Group")),
            category=str(data.get("category", DEFAULT_CATEGORY)),
            objects=list(data.get("objects", [])),
            color=list(data.get("color", [0.7, 0.7, 0.7])),
            notes=str(data.get("notes", "")),
            created_at=float(data.get("created_at", time.time())),
            modified_at=float(data.get("modified_at", time.time())),
        )


@dataclass
class Category:
    name: str
    prefix: str = ""
    collapsed: bool = False
    display_name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Category":
        name = str(data.get("name", DEFAULT_CATEGORY))
        return cls(
            name=name,
            prefix=str(data.get("prefix", "")),
            collapsed=bool(data.get("collapsed", False)),
            display_name=str(data.get("display_name", name)),
        )


# ------------------------------
# Persistence + manager
# ------------------------------

class SmartSelectSetsManager:
    def __init__(self) -> None:
        self.categories: Dict[str, Category] = {DEFAULT_CATEGORY: Category(name=DEFAULT_CATEGORY, display_name=DEFAULT_CATEGORY)}
        self.groups: Dict[int, SelectionGroup] = {}
        self.next_group_id: int = 1

    # ----- category helpers -----
    def ensure_category(self, category_name: str) -> Category:
        category_name = (category_name or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
        if category_name not in self.categories:
            self.categories[category_name] = Category(name=category_name, display_name=category_name)
        return self.categories[category_name]

    def create_category(self, category_name: str) -> None:
        category_name = (category_name or "").strip()
        if not category_name:
            raise ValueError("Category name cannot be empty.")
        if category_name in self.categories:
            raise ValueError(f"Category '{category_name}' already exists.")
        self.categories[category_name] = Category(name=category_name, display_name=category_name)

    def get_category_label(self, category_name: str) -> str:
        category = self.categories.get(category_name)
        if not category:
            return category_name
        return (category.display_name or category.name or category_name).strip() or category_name


    def rename_category(self, old_name: str, new_name: str) -> None:
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("New category name cannot be empty.")
        if old_name not in self.categories:
            raise ValueError(f"Category '{old_name}' does not exist.")

        if old_name == DEFAULT_CATEGORY:
            category = self.categories[old_name]
            category.display_name = new_name
            return

        if new_name in self.categories:
            raise ValueError(f"Category '{new_name}' already exists.")

        category = self.categories.pop(old_name)
        category.name = new_name
        category.display_name = new_name
        self.categories[new_name] = category

        for group in self.groups.values():
            if group.category == old_name:
                group.category = new_name
                group.modified_at = time.time()

    def delete_category(self, category_name: str, delete_groups: bool = False) -> None:
        if category_name not in self.categories:
            raise ValueError(f"Category '{category_name}' does not exist.")

        to_affect = [g for g in self.groups.values() if g.category == category_name]

        if category_name == DEFAULT_CATEGORY:
            if to_affect and not delete_groups:
                raise ValueError("The Uncategorized category contains groups. Move or delete them first, or delete the category with its groups.")
            if delete_groups:
                for group in list(to_affect):
                    del self.groups[group.group_id]
            del self.categories[category_name]
            return

        del self.categories[category_name]
        if delete_groups:
            for group in list(to_affect):
                del self.groups[group.group_id]
        else:
            self.ensure_category(DEFAULT_CATEGORY)
            for group in to_affect:
                group.category = DEFAULT_CATEGORY
                group.modified_at = time.time()

    def set_category_prefix(self, category_name: str, new_prefix: str, remap_objects: bool = True) -> None:
        category = self.ensure_category(category_name)
        old_prefix = category.prefix
        category.prefix = (new_prefix or "").strip()

        if remap_objects and old_prefix != category.prefix:
            for group in self.groups.values():
                if group.category == category_name:
                    group.objects = [self._swap_namespace(obj, old_prefix, category.prefix) for obj in group.objects]
                    group.modified_at = time.time()

    # ----- group helpers -----
    def create_group(
        self,
        name: str,
        category: str,
        objects: List[str],
        color: Optional[List[float]] = None,
        notes: str = "",
    ) -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("Group name cannot be empty.")

        category = self.ensure_category(category).name
        long_paths = self.normalize_objects(objects)
        if not long_paths:
            raise ValueError("No valid objects were provided.")

        group_id = self.next_group_id
        self.next_group_id += 1
        self.groups[group_id] = SelectionGroup(
            group_id=group_id,
            name=name,
            category=category,
            objects=long_paths,
            color=list(color or [0.7, 0.7, 0.7]),
            notes=notes,
        )
        return group_id

    def rename_group(self, group_id: int, new_name: str) -> None:
        group = self.require_group(group_id)
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("Group name cannot be empty.")
        group.name = new_name
        group.modified_at = time.time()

    def delete_group(self, group_id: int) -> None:
        self.require_group(group_id)
        del self.groups[group_id]

    def delete_uncategorized_groups(self) -> int:
        to_delete = [group_id for group_id, group in self.groups.items() if group.category == DEFAULT_CATEGORY]
        for group_id in to_delete:
            del self.groups[group_id]
        return len(to_delete)

    def move_group(self, group_id: int, new_category: str) -> None:
        group = self.require_group(group_id)
        group.category = self.ensure_category(new_category).name
        group.modified_at = time.time()

    def replace_group_members(self, group_id: int, objects: List[str]) -> None:
        group = self.require_group(group_id)
        resolved = self.normalize_objects(objects)
        group.objects = resolved
        group.modified_at = time.time()

    def add_to_group(self, group_id: int, objects: List[str]) -> int:
        group = self.require_group(group_id)
        incoming = self.normalize_objects(objects)
        existing = set(group.objects)
        added = 0
        for obj in incoming:
            if obj not in existing:
                group.objects.append(obj)
                existing.add(obj)
                added += 1
        group.modified_at = time.time()
        return added

    def remove_from_group(self, group_id: int, objects: List[str]) -> int:
        group = self.require_group(group_id)
        removal = set(self.normalize_objects(objects))
        before = len(group.objects)
        group.objects = [obj for obj in group.objects if obj not in removal]
        removed = before - len(group.objects)
        group.modified_at = time.time()
        return removed

    def require_group(self, group_id: int) -> SelectionGroup:
        if group_id not in self.groups:
            raise ValueError(f"Group id '{group_id}' does not exist.")
        return self.groups[group_id]

    # ----- selection + validation -----
    def normalize_objects(self, objects: List[str]) -> List[str]:
        results: List[str] = []
        seen = set()
        for obj in objects or []:
            resolved = self.resolve_object(obj)
            if resolved and resolved not in seen:
                results.append(resolved)
                seen.add(resolved)
        return results

    def resolve_object(self, obj: str) -> Optional[str]:
        if not obj:
            return None

        if cmds.objExists(obj):
            long_names = cmds.ls(obj, long=True) or []
            return long_names[0] if long_names else obj

        short_name = obj.split("|")[-1]
        exact = cmds.ls(short_name, long=True) or []
        if len(exact) == 1:
            return exact[0]

        # fallback: try namespace-insensitive lookup using leaf name after namespace
        leaf = short_name.split(":")[-1]
        candidates = cmds.ls(f"*:{leaf}", long=True) or []
        if len(candidates) == 1:
            return candidates[0]

        no_ns = cmds.ls(leaf, long=True) or []
        if len(no_ns) == 1:
            return no_ns[0]

        return None

    def validate_group(self, group_id: int) -> dict:
        group = self.require_group(group_id)
        resolved = []
        missing = []
        for obj in group.objects:
            found = self.resolve_object(obj)
            if found:
                resolved.append(found)
            else:
                missing.append(obj)
        return {
            "group_id": group_id,
            "group_name": group.name,
            "total": len(group.objects),
            "resolved": resolved,
            "missing": missing,
            "is_valid": len(missing) == 0,
            "is_partial": bool(resolved) and bool(missing),
        }

    def validate_all(self) -> Dict[int, dict]:
        return {group_id: self.validate_group(group_id) for group_id in self.groups}

    def repair_group_paths(self, group_id: int) -> Tuple[int, int]:
        group = self.require_group(group_id)
        repaired = []
        repaired_count = 0
        dropped_count = 0
        seen = set()
        for obj in group.objects:
            resolved = self.resolve_object(obj)
            if resolved:
                if resolved != obj:
                    repaired_count += 1
                if resolved not in seen:
                    repaired.append(resolved)
                    seen.add(resolved)
            else:
                dropped_count += 1
        group.objects = repaired
        group.modified_at = time.time()
        return repaired_count, dropped_count

    def select_group(self, group_id: int, mode: str = "replace") -> dict:
        group = self.require_group(group_id)
        validation = self.validate_group(group_id)
        valid_objects = validation["resolved"]

        if not valid_objects:
            raise ValueError(f"No valid scene objects found for group '{group.name}'.")

        if mode == "replace":
            cmds.select(valid_objects, replace=True)
        elif mode == "add":
            cmds.select(valid_objects, add=True)
        elif mode == "toggle":
            cmds.select(valid_objects, toggle=True)
        elif mode == "deselect":
            cmds.select(valid_objects, deselect=True)
        else:
            raise ValueError(f"Unsupported selection mode: {mode}")
        return validation

    # ----- serialization -----
    def to_payload(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "next_group_id": self.next_group_id,
            "categories": {name: cat.to_dict() for name, cat in self.categories.items()},
            "groups": {str(group_id): group.to_dict() for group_id, group in self.groups.items()},
        }

    def load_payload(self, payload: dict) -> None:
        schema_version = int(payload.get("schema_version", 1))
        if schema_version == 1:
            payload = self._migrate_v1_payload(payload)
            schema_version = int(payload.get("schema_version", 2))

        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {schema_version}")

        self.categories = {}
        for name, cat_data in payload.get("categories", {}).items():
            category = Category.from_dict(cat_data)
            self.categories[name] = category
        if DEFAULT_CATEGORY not in self.categories:
            self.categories[DEFAULT_CATEGORY] = Category(name=DEFAULT_CATEGORY)

        self.groups = {}
        max_group_id = 0
        for key, group_data in payload.get("groups", {}).items():
            group = SelectionGroup.from_dict(group_data)
            group.group_id = int(key)
            self.groups[group.group_id] = group
            self.ensure_category(group.category)
            max_group_id = max(max_group_id, group.group_id)

        next_group_id = int(payload.get("next_group_id", max_group_id + 1))
        self.next_group_id = max(next_group_id, max_group_id + 1)

    def save_to_scene_node(self) -> None:
        payload = json.dumps(self.to_payload(), indent=2)
        if not cmds.objExists(SCENE_NODE_NAME):
            cmds.createNode("transform", name=SCENE_NODE_NAME)
        if not cmds.attributeQuery(SCENE_ATTR_NAME, node=SCENE_NODE_NAME, exists=True):
            cmds.addAttr(SCENE_NODE_NAME, longName=SCENE_ATTR_NAME, dataType="string")
        cmds.setAttr(f"{SCENE_NODE_NAME}.{SCENE_ATTR_NAME}", payload, type="string")

    def load_from_scene_node(self) -> bool:
        if not cmds.objExists(SCENE_NODE_NAME):
            return False
        if not cmds.attributeQuery(SCENE_ATTR_NAME, node=SCENE_NODE_NAME, exists=True):
            return False
        payload_text = cmds.getAttr(f"{SCENE_NODE_NAME}.{SCENE_ATTR_NAME}")
        if not payload_text:
            return False
        self.load_payload(json.loads(payload_text))
        return True

    def export_to_json(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(self.to_payload(), handle, indent=2)

    def import_from_json(self, file_path: str) -> None:
        with open(file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self.load_payload(payload)

    def _migrate_v1_payload(self, payload: dict) -> dict:
        # Legacy structure: {"1": {group_data}, ...}
        categories: Dict[str, dict] = {DEFAULT_CATEGORY: Category(name=DEFAULT_CATEGORY).to_dict()}
        groups: Dict[str, dict] = {}
        max_group_id = 0

        for key, old_group_data in payload.items():
            try:
                group_id = int(key)
            except Exception:
                continue
            max_group_id = max(max_group_id, group_id)
            category_name = str(old_group_data.get("category", DEFAULT_CATEGORY))
            if category_name not in categories:
                categories[category_name] = Category(name=category_name, display_name=category_name).to_dict()
            groups[str(group_id)] = {
                "group_id": group_id,
                "name": old_group_data.get("group_name", "Group"),
                "category": category_name,
                "objects": old_group_data.get("objects", []),
                "color": old_group_data.get("color", [0.7, 0.7, 0.7]),
                "notes": "",
                "created_at": time.time(),
                "modified_at": time.time(),
            }

        return {
            "schema_version": 2,
            "tool_name": TOOL_NAME,
            "tool_version": TOOL_VERSION,
            "next_group_id": max_group_id + 1,
            "categories": categories,
            "groups": groups,
        }

    @staticmethod
    def _swap_namespace(path: str, old_prefix: str, new_prefix: str) -> str:
        if not path:
            return path
        long_parts = path.split("|")
        swapped_parts = []
        for part in long_parts:
            if not part:
                swapped_parts.append(part)
                continue
            if old_prefix:
                if part.startswith(old_prefix + ":"):
                    bare = part[len(old_prefix) + 1 :]
                    swapped_parts.append((new_prefix + ":" + bare) if new_prefix else bare)
                else:
                    swapped_parts.append(part)
            else:
                if new_prefix and ":" not in part:
                    swapped_parts.append(new_prefix + ":" + part)
                else:
                    swapped_parts.append(part)
        return "|".join(swapped_parts)


# ------------------------------
# UI
# ------------------------------


class GroupButton(QtWidgets.QPushButton):
    clickedWithId = QtCore.Signal(int)
    contextMenuRequestedForId = QtCore.Signal(int, QtCore.QPoint)

    def __init__(self, group_id: int, label: str, color: List[float], parent=None):
        super().__init__(label, parent)
        self.group_id = group_id
        self.base_color = color
        self._drag_start_pos: Optional[QtCore.QPoint] = None
        self._drag_started = False
        self.setFixedHeight(44)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context)
        self.clicked.connect(self._emit_click)
        self.apply_color(color)

    def _emit_click(self):
        if not self._drag_started:
            self.clickedWithId.emit(self.group_id)

    def _emit_context(self, pos: QtCore.QPoint):
        self.contextMenuRequestedForId.emit(self.group_id, self.mapToGlobal(pos))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if not (event.buttons() & QtCore.Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        if self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            super().mouseMoveEvent(event)
            return

        self._drag_started = True
        mime = QtCore.QMimeData()
        mime.setData("application/x-smartselect-group-id", str(self.group_id).encode("utf-8"))

        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        drag.setHotSpot(event.pos())
        drag.setPixmap(self.grab())
        drag.exec(QtCore.Qt.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        QtCore.QTimer.singleShot(0, self._reset_drag_state)

    def _reset_drag_state(self):
        self._drag_start_pos = None
        self._drag_started = False

    def apply_color(self, color: List[float]) -> None:
        self.base_color = list(color)
        rgb = tuple(max(0, min(255, int(c * 255))) for c in color)
        self.setStyleSheet(
            "QPushButton {"
            f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
            "border: 1px solid #4c4c4c;"
            "border-radius: 6px;"
            "padding: 6px 10px;"
            "text-align: left;"
            "}"
            "QPushButton:hover { border: 1px solid #202020; }"
        )


class CategoryDropBox(QtWidgets.QGroupBox):
    groupDropped = QtCore.Signal(int, str)

    def __init__(self, category_name: str, title: str, parent=None):
        super().__init__(title, parent)
        self.category_name = category_name
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasFormat("application/x-smartselect-group-id"):
            event.acceptProposedAction()
            self.setProperty("dragHover", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasFormat("application/x-smartselect-group-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent) -> None:
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        self.setProperty("dragHover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if not event.mimeData().hasFormat("application/x-smartselect-group-id"):
            event.ignore()
            return
        try:
            group_id = int(bytes(event.mimeData().data("application/x-smartselect-group-id")).decode("utf-8"))
        except Exception:
            event.ignore()
            return
        self.groupDropped.emit(group_id, self.category_name)
        event.acceptProposedAction()


class SmartSelectSetsWindow(QtWidgets.QDialog):
    WINDOW_OBJECT_NAME = TOOL_NAME

    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setObjectName(self.WINDOW_OBJECT_NAME)
        self.setWindowTitle(f"{TOOL_TITLE}  v{TOOL_VERSION}")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinimizeButtonHint | QtCore.Qt.WindowCloseButtonHint)
        self.resize(640, 720)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        self.manager = SmartSelectSetsManager()
        self.group_buttons: Dict[int, GroupButton] = {}
        self.category_widgets: Dict[str, dict] = {}
        self.popout_windows: Dict[str, "CategoryPopoutWindow"] = {}
        self._timers: List[QtCore.QTimer] = []

        self._build_ui()
        self._connect_scene_jobs()
        self.load_from_scene(show_feedback=False)
        self.refresh_ui()

    # ----- build -----
    def _build_ui(self) -> None:
        self.setMinimumSize(540, 640)
        self.setStyleSheet(self._main_stylesheet())

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.menu_bar = self._build_menu_bar()
        layout.setMenuBar(self.menu_bar)

        layout.addWidget(self._build_header_bar())
        layout.addLayout(self._build_secondary_toolbar())

        self.search_field = QtWidgets.QLineEdit()
        self.search_field.setObjectName("SearchField")
        self.search_field.setPlaceholderText("Filter groups or categories...")
        self.search_field.textChanged.connect(self.refresh_ui)
        layout.addWidget(self.search_field)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.scroll_contents = QtWidgets.QWidget()
        self.categories_layout = QtWidgets.QVBoxLayout(self.scroll_contents)
        self.categories_layout.setContentsMargins(0, 0, 0, 0)
        self.categories_layout.setSpacing(10)
        self.categories_layout.addStretch(1)

        self.scroll_area.setWidget(self.scroll_contents)
        layout.addWidget(self.scroll_area, 1)

        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("StatusLabel")
        layout.addWidget(self.status_label)

    def _main_stylesheet(self) -> str:
        return f"""
        QDialog {{
            background-color: #242424;
            color: #e8e8e8;
        }}
        QLabel {{
            color: #e8e8e8;
        }}
        QLabel#StatusLabel {{
            color: #9c9c9c;
            padding: 2px 4px;
        }}
        QLineEdit, QComboBox, QPlainTextEdit {{
            background-color: #2f2f2f;
            border: 1px solid #434343;
            border-radius: 7px;
            padding: 6px 8px;
            color: #ededed;
        }}
        QLineEdit#SearchField {{
            min-height: 18px;
            padding: 8px 10px;
            border-radius: 9px;
        }}
        QPushButton, QToolButton {{
            background-color: #3b3b3b;
            border: 1px solid #4a4a4a;
            border-radius: 8px;
            padding: 7px 10px;
            color: #f2f2f2;
        }}
        QPushButton:hover, QToolButton:hover {{
            border: 1px solid {HEADER_ACCENT};
            background-color: #434343;
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background-color: #2f2f2f;
        }}
        QGroupBox {{
            background-color: #2b2b2b;
            border: 1px solid #3d3d3d;
            border-radius: 12px;
            margin-top: 10px;
            padding: 10px 8px 8px 8px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: #f0f0f0;
        }}
        QScrollArea {{
            background: transparent;
        }}
        QMenu {{
            background-color: #2c2c2c;
            color: #f0f0f0;
            border: 1px solid #4a4a4a;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 6px 18px;
            border-radius: 6px;
        }}
        QMenu::item:selected {{
            background-color: #454545;
        }}
        QMenuBar {{
            background-color: #2a2a2a;
            border: 1px solid #424242;
            border-radius: 8px;
            padding: 3px 6px;
        }}
        QMenuBar::item {{
            background: transparent;
            color: #f0f0f0;
            padding: 6px 10px;
            border-radius: 6px;
        }}
        QMenuBar::item:selected {{
            background-color: #3d3d3d;
        }}
        QMenuBar::item:pressed {{
            background-color: #454545;
        }}
        QScrollBar:vertical {{
            background: #262626;
            width: 12px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: #4c4c4c;
            min-height: 20px;
            border-radius: 6px;
        }}
        """

    def _build_menu_bar(self) -> QtWidgets.QMenuBar:
        menu_bar = QtWidgets.QMenuBar(self)
        windows_menu = menu_bar.addMenu("Windows")
        windows_menu.addAction("Help", self.show_help)
        windows_menu.addSeparator()
        windows_menu.addAction("About", self.show_about)
        return menu_bar

    def _build_header_bar(self) -> QtWidgets.QWidget:
        container = QtWidgets.QFrame()
        container.setObjectName("HeaderBar")
        container.setStyleSheet(
            "QFrame#HeaderBar {background-color: #343434; border: 1px solid #484848; border-radius: 12px;}"
        )

        row = QtWidgets.QHBoxLayout(container)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(8)

        self.primary_group_button = QtWidgets.QPushButton("Select_Set")
        self.primary_group_button.setObjectName("PrimaryGroupPreview")
        self.primary_group_button.setMinimumHeight(58)
        self.primary_group_button.setMinimumWidth(82)
        self.primary_group_button.clicked.connect(self.create_group_dialog)
        self.primary_group_button.setStyleSheet(
            f"QPushButton#PrimaryGroupPreview {{"
            f"background-color: #ece7f8; color: #5f468f; border: 4px solid {HEADER_ACCENT};"
            "border-radius: 8px; font-weight: 600; padding: 10px 8px; text-align: center;"
            "}"
            "QPushButton#PrimaryGroupPreview:hover {background-color: #f5f1ff;}"
        )
        row.addWidget(self.primary_group_button, 0)

        tools_widget = QtWidgets.QWidget()
        tools_layout = QtWidgets.QHBoxLayout(tools_widget)
        tools_layout.setContentsMargins(4, 0, 4, 0)
        tools_layout.setSpacing(6)

        self._header_actions = []
        self._header_actions.append(self._make_icon_button("+", "Create Selection Group", self.create_group_dialog))
        self._header_actions.append(self._make_icon_button("C", "Create Category", self.create_category_dialog))
        self._header_actions.append(self._make_icon_button("S", "Save to Scene", self.save_to_scene))
        self._header_actions.append(self._make_icon_button("L", "Load from Scene", self.load_from_scene))
        for btn in self._header_actions:
            tools_layout.addWidget(btn)

        row.addWidget(tools_widget, 0)
        row.addStretch(1)

        self.minimize_button = QtWidgets.QToolButton()
        self.minimize_button.setText("–")
        self.minimize_button.setToolTip("Minimize")
        self.minimize_button.setAutoRaise(True)
        self.minimize_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.minimize_button.setFixedSize(28, 28)
        self.minimize_button.clicked.connect(self.showMinimized)
        self.minimize_button.setStyleSheet(
            "QToolButton {background: transparent; border: none; color: #d1d1d1; font-size: 18px; font-weight: 700;}"
            "QToolButton:hover {color: #ffffff; background-color: #454545; border-radius: 8px;}"
        )
        row.addWidget(self.minimize_button, 0, QtCore.Qt.AlignTop)

        self.close_button = QtWidgets.QToolButton()
        self.close_button.setText("×")
        self.close_button.setToolTip("Close")
        self.close_button.setAutoRaise(True)
        self.close_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.close_button.setFixedSize(28, 28)
        self.close_button.clicked.connect(self.close)
        self.close_button.setStyleSheet(
            "QToolButton {background: transparent; border: none; color: #d1d1d1; font-size: 18px; font-weight: 700;}"
            "QToolButton:hover {color: #ffffff; background-color: #454545; border-radius: 8px;}"
        )
        row.addWidget(self.close_button, 0, QtCore.Qt.AlignTop)
        return container

    def _make_icon_button(self, symbol: str, tooltip: str, callback) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setText(symbol)
        button.setToolTip(tooltip)
        button.setAutoRaise(False)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.setFixedSize(28, 28)
        button.clicked.connect(callback)
        button.setStyleSheet(
            f"QToolButton {{background-color: {HEADER_ACCENT}; color: #ffffff; border: 1px solid #8b73cf; border-radius: 7px; font-weight: 700;}}"
            "QToolButton:hover {background-color: #c7b1ff; color: #2f2148;}"
            "QToolButton:pressed {background-color: #9a7fe2;}"
        )
        return button

    def _build_secondary_toolbar(self) -> QtWidgets.QLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)

        self.menu_button = QtWidgets.QToolButton()
        self.menu_button.setText("Options")
        self.menu_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu = QtWidgets.QMenu(self)
        menu.addAction("Save to Scene", self.save_to_scene)
        menu.addAction("Load from Scene", self.load_from_scene)
        menu.addSeparator()
        menu.addAction("Export JSON", self.export_json)
        menu.addAction("Import JSON", self.import_json)
        menu.addSeparator()
        menu.addAction("Validate All Groups", self.validate_all_groups)
        menu.addAction("Delete Uncategorized Groups", self.delete_uncategorized_groups_dialog)
        menu.addSeparator()
        menu.addAction("Help", self.show_help)
        menu.addAction("About", self.show_about)
        self.menu_button.setMenu(menu)
        row.addWidget(self.menu_button)

        validate_btn = QtWidgets.QPushButton("Validate")
        validate_btn.clicked.connect(self.validate_all_groups)
        row.addWidget(validate_btn)


        row.addStretch(1)

        opacity_label = QtWidgets.QLabel("Opacity")
        row.addWidget(opacity_label)

        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(25, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(120)
        self.opacity_slider.valueChanged.connect(self._update_opacity)
        row.addWidget(self.opacity_slider)

        return row

    # ----- lifecycle -----
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            self.manager.save_to_scene_node()
        except Exception as exc:
            cmds.warning(f"Failed to auto-save Smart Select Sets: {exc}")

        for popup in list(self.popout_windows.values()):
            try:
                popup.close()
                popup.deleteLater()
            except Exception:
                pass
        self.popout_windows.clear()
        super().closeEvent(event)

    def _connect_scene_jobs(self) -> None:
        self._script_jobs = []
        try:
            self._script_jobs.append(cmds.scriptJob(event=["SceneOpened", self._on_scene_opened], protected=True))
            self._script_jobs.append(cmds.scriptJob(event=["NewSceneOpened", self._on_scene_opened], protected=True))
        except Exception:
            pass

    def _on_scene_opened(self, *args):
        QtCore.QTimer.singleShot(50, lambda: self.load_from_scene(show_feedback=False))

    # ----- ui refresh -----
    def clear_categories_ui(self) -> None:
        while self.categories_layout.count() > 1:
            item = self.categories_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.group_buttons.clear()
        self.category_widgets.clear()

    def refresh_ui(self) -> None:
        self.clear_categories_ui()
        filter_text = self.search_field.text().strip().lower()

        category_names = sorted(self.manager.categories.keys(), key=lambda x: (x != DEFAULT_CATEGORY, x.lower()))
        validation = self.manager.validate_all()

        for category_name in category_names:
            category = self.manager.categories[category_name]
            groups = [g for g in self.manager.groups.values() if g.category == category_name]
            groups.sort(key=lambda g: g.name.lower())

            if filter_text:
                category_label = self.manager.get_category_label(category_name)
                visible_groups = [g for g in groups if filter_text in g.name.lower() or filter_text in category_name.lower() or filter_text in category_label.lower()]
                if not visible_groups and filter_text not in category_name.lower() and filter_text not in category_label.lower():
                    continue
                groups = visible_groups

            display_label = self.manager.get_category_label(category_name)
            group_box = CategoryDropBox(category_name, display_label)
            group_box.groupDropped.connect(self._move_group_to_category_from_drop)

            outer = QtWidgets.QVBoxLayout(group_box)
            outer.setSpacing(6)

            top_row = QtWidgets.QHBoxLayout()
            prefix_row = QtWidgets.QHBoxLayout()
            prefix_label = QtWidgets.QLabel("Prefix")
            prefix_edit = QtWidgets.QLineEdit(category.prefix)
            prefix_edit.setPlaceholderText("Optional namespace prefix")
            update_btn = QtWidgets.QPushButton("Apply")
            update_btn.clicked.connect(lambda _=False, c=category_name, e=prefix_edit: self.apply_category_prefix(c, e.text()))
            popout_btn = QtWidgets.QPushButton("Pop Out")
            popout_btn.setToolTip("Open a compact floating panel for this category/prefix set.")
            popout_btn.clicked.connect(lambda _=False, c=category_name: self.open_category_popout(c))
            rename_btn = QtWidgets.QPushButton("Rename")
            rename_btn.setToolTip("Rename this category label.")
            rename_btn.clicked.connect(lambda _=False, c=category_name: self.rename_category_dialog(c))
            delete_btn = QtWidgets.QPushButton("Delete")
            delete_btn.setToolTip("Delete this category block.")
            delete_btn.clicked.connect(lambda _=False, c=category_name: self.delete_specific_category_dialog(c))
            prefix_row.addWidget(prefix_label)
            prefix_row.addWidget(prefix_edit, 1)
            prefix_row.addWidget(update_btn)
            prefix_row.addWidget(popout_btn)
            prefix_row.addWidget(rename_btn)
            prefix_row.addWidget(delete_btn)

            top_row.addLayout(prefix_row, 1)

            outer.addLayout(top_row)

            hint = QtWidgets.QLabel("Tip: drag a selection button onto another category to move it.")
            hint.setStyleSheet("color: #8d8d8d; font-size: 11px;")
            outer.addWidget(hint)

            flow = FlowLayout()
            for group in groups:
                label = f"{category.prefix}:{group.name}" if category.prefix else group.name
                button = GroupButton(group.group_id, label, group.color)
                state = validation[group.group_id]
                if state["missing"]:
                    button.setToolTip(
                        "Missing objects:\n" + "\n".join(state["missing"][:12]) +
                        ("\n..." if len(state["missing"]) > 12 else "")
                    )
                    button.setStyleSheet(button.styleSheet() + "QPushButton { border: 2px solid #c98500; }")
                else:
                    button.setToolTip("All objects resolved. Drag to another category to move it.")
                button.clickedWithId.connect(self.on_group_button_clicked)
                button.contextMenuRequestedForId.connect(self.show_group_context_menu)
                self.group_buttons[group.group_id] = button
                flow.addWidget(button)

            if not groups:
                empty_text = "No groups in this category. Drag a button here to move it." if category_name != DEFAULT_CATEGORY else "No uncategorized groups."
                empty = QtWidgets.QLabel(empty_text)
                empty.setStyleSheet("color: #888; font-style: italic;")
                outer.addWidget(empty)
            else:
                outer.addLayout(flow)

            self.categories_layout.insertWidget(self.categories_layout.count() - 1, group_box)
            self.category_widgets[category_name] = {
                "group_box": group_box,
                "prefix_edit": prefix_edit,
                "popout_button": popout_btn,
                "rename_button": rename_btn,
            }

        self.status_label.setText(f"Categories: {len(self.manager.categories)}   Groups: {len(self.manager.groups)}")
        self._sync_popout_windows()

    def _sync_popout_windows(self) -> None:
        existing_categories = set(self.manager.categories.keys())
        for category_name in list(self.popout_windows.keys()):
            popup = self.popout_windows.get(category_name)
            if category_name not in existing_categories:
                if popup:
                    try:
                        popup.close()
                        popup.deleteLater()
                    except Exception:
                        pass
                self.popout_windows.pop(category_name, None)

        for category_name, popup in list(self.popout_windows.items()):
            if popup:
                popup.refresh_buttons()

    def open_category_popout(self, category_name: str) -> None:
        category_name = (category_name or "").strip() or DEFAULT_CATEGORY
        if category_name not in self.manager.categories:
            self._show_error(f"Category '{category_name}' does not exist.")
            return

        popup = self.popout_windows.get(category_name)
        if popup is None or popup.isHidden():
            popup = CategoryPopoutWindow(category_name, self.manager, self)
            popup.destroyed.connect(lambda *_ , c=category_name: self.popout_windows.pop(c, None))
            self.popout_windows[category_name] = popup

        popup.refresh_buttons()
        popup.show()
        popup.raise_()
        popup.activateWindow()

    # ----- commands -----
    def _update_opacity(self, value: int) -> None:
        self.setWindowOpacity(max(0.25, min(1.0, value / 100.0)))

    def _choose_color(self) -> List[float]:
        color = QtWidgets.QColorDialog.getColor(parent=self)
        if not color.isValid():
            return [0.7, 0.7, 0.7]
        return [color.redF(), color.greenF(), color.blueF()]

    def create_category_dialog(self) -> None:
        text, ok = QtWidgets.QInputDialog.getText(self, "Create Category", "Category name:")
        if not ok:
            return
        try:
            self.manager.create_category(text)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def delete_category_dialog(self) -> None:
        category_names = [name for name in sorted(self.manager.categories.keys()) if name != DEFAULT_CATEGORY]
        if not category_names:
            self._show_info("No custom categories exist.")
            return
        category, ok = QtWidgets.QInputDialog.getItem(self, "Delete Category", "Category:", category_names, 0, False)
        if not ok:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Category",
            f"Delete category '{category}'?\n\nGroups in this category will be moved to '{DEFAULT_CATEGORY}'.",
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        try:
            self.manager.delete_category(category)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def create_group_dialog(self) -> None:
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            self._show_info("Select one or more scene objects first.")
            return

        category_pairs = []
        for category_name in sorted(self.manager.categories.keys()):
            category_pairs.append((self.manager.get_category_label(category_name), category_name))

        dialog = CreateGroupDialog(category_pairs, self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        group_name, category_name = dialog.get_values()
        color = dialog.chosen_color
        try:
            self.manager.create_group(group_name, category_name, selection, color=color)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def apply_category_prefix(self, category_name: str, new_prefix: str) -> None:
        try:
            self.manager.set_category_prefix(category_name, new_prefix, remap_objects=True)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def on_group_button_clicked(self, group_id: int) -> None:
        try:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            mode = "replace"
            if modifiers & QtCore.Qt.ShiftModifier:
                mode = "add"
            validation = self.manager.select_group(group_id, mode=mode)
            self._flash_button(group_id)
            if validation["missing"]:
                cmds.warning(
                    f"Group '{validation['group_name']}' has missing objects: {len(validation['missing'])}. "
                    f"Selected only valid members."
                )
        except Exception as exc:
            self._show_error(str(exc))

    def _flash_button(self, group_id: int) -> None:
        button = self.group_buttons.get(group_id)
        group = self.manager.groups.get(group_id)
        if not button or not group:
            return
        button.apply_color(HIGHLIGHT_COLOR)
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: button.apply_color(group.color))
        timer.start(800)
        self._timers.append(timer)

    def show_group_context_menu(self, group_id: int, global_pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("Select", lambda: self._select_context(group_id, "replace"))
        menu.addAction("Add to Selection", lambda: self._select_context(group_id, "add"))
        menu.addSeparator()
        menu.addAction("Add Current Selection to Group", lambda: self._add_current_selection_to_group(group_id))
        menu.addAction("Remove Current Selection from Group", lambda: self._remove_current_selection_from_group(group_id))
        menu.addAction("Replace Group with Current Selection", lambda: self._replace_group_with_current_selection(group_id))
        menu.addSeparator()
        menu.addAction("Rename Group", lambda: self._rename_group_dialog(group_id))
        menu.addAction("Move Group to Category", lambda: self._move_group_dialog(group_id))
        menu.addAction("Choose Button Color", lambda: self._set_group_color(group_id))
        menu.addSeparator()
        menu.addAction("Validate Group", lambda: self._show_group_validation(group_id))
        menu.addAction("Repair Group Paths", lambda: self._repair_group(group_id))
        menu.addSeparator()
        menu.addAction("Delete Group", lambda: self._delete_group(group_id))
        menu.exec(global_pos)

    def _select_context(self, group_id: int, mode: str) -> None:
        try:
            self.manager.select_group(group_id, mode=mode)
            self._flash_button(group_id)
        except Exception as exc:
            self._show_error(str(exc))

    def _add_current_selection_to_group(self, group_id: int) -> None:
        selection = cmds.ls(selection=True, long=True) or []
        try:
            added = self.manager.add_to_group(group_id, selection)
            self.refresh_ui()
            self._show_info(f"Added {added} object(s) to the group.")
        except Exception as exc:
            self._show_error(str(exc))

    def _remove_current_selection_from_group(self, group_id: int) -> None:
        selection = cmds.ls(selection=True, long=True) or []
        try:
            removed = self.manager.remove_from_group(group_id, selection)
            self.refresh_ui()
            self._show_info(f"Removed {removed} object(s) from the group.")
        except Exception as exc:
            self._show_error(str(exc))

    def _replace_group_with_current_selection(self, group_id: int) -> None:
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            self._show_info("Select one or more scene objects first.")
            return
        try:
            self.manager.replace_group_members(group_id, selection)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def _rename_group_dialog(self, group_id: int) -> None:
        group = self.manager.require_group(group_id)
        text, ok = QtWidgets.QInputDialog.getText(self, "Rename Group", "New group name:", text=group.name)
        if not ok:
            return
        try:
            self.manager.rename_group(group_id, text)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def _move_group_dialog(self, group_id: int) -> None:
        category_names = sorted(self.manager.categories.keys())
        current_category = self.manager.require_group(group_id).category
        current_index = category_names.index(current_category) if current_category in category_names else 0
        category, ok = QtWidgets.QInputDialog.getItem(self, "Move Group", "Category:", category_names, current_index, False)
        if not ok:
            return
        try:
            self.manager.move_group(group_id, category)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def _move_group_to_category_from_drop(self, group_id: int, category_name: str) -> None:
        try:
            group = self.manager.require_group(group_id)
            if group.category == category_name:
                return
            self.manager.move_group(group_id, category_name)
            self.refresh_ui()
            self.status_label.setText(f"Moved '{group.name}' to '{self.manager.get_category_label(category_name)}'.")
        except Exception as exc:
            self._show_error(str(exc))

    def delete_specific_category_dialog(self, category_name: str) -> None:
        if category_name not in self.manager.categories:
            self._show_info(f"Category '{category_name}' no longer exists.")
            return

        groups_in_category = [g for g in self.manager.groups.values() if g.category == category_name]

        if category_name == DEFAULT_CATEGORY:
            if groups_in_category:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    "Delete Uncategorized",
                    f"Delete the entire '{DEFAULT_CATEGORY}' block and its {len(groups_in_category)} group(s)?\n\nThis will permanently remove those selection sets.",
                )
                if confirm != QtWidgets.QMessageBox.Yes:
                    return
                delete_groups = True
            else:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    "Delete Uncategorized",
                    f"Delete the entire '{DEFAULT_CATEGORY}' block?",
                )
                if confirm != QtWidgets.QMessageBox.Yes:
                    return
                delete_groups = False
        else:
            if groups_in_category:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    "Delete Category",
                    f"Delete the category '{category_name}'?\n\nIts {len(groups_in_category)} group(s) will be moved to '{DEFAULT_CATEGORY}'.",
                )
                if confirm != QtWidgets.QMessageBox.Yes:
                    return
                delete_groups = False
            else:
                confirm = QtWidgets.QMessageBox.question(
                    self,
                    "Delete Category",
                    f"Delete the category '{category_name}'?",
                )
                if confirm != QtWidgets.QMessageBox.Yes:
                    return
                delete_groups = False

        try:
            self.manager.delete_category(category_name, delete_groups=delete_groups)
            self.refresh_ui()
            if category_name == DEFAULT_CATEGORY:
                self._show_info(f"Deleted the '{DEFAULT_CATEGORY}' category block.")
            else:
                self._show_info(f"Deleted category '{category_name}'.")
        except Exception as exc:
            self._show_error(str(exc))

    def delete_uncategorized_groups_dialog(self) -> None:
        uncategorized = [g for g in self.manager.groups.values() if g.category == DEFAULT_CATEGORY]
        if not uncategorized:
            self._show_info("There are no uncategorized groups to delete.")
            return

        confirm = QtWidgets.QMessageBox.question(
            self,
            "Delete Uncategorized Groups",
            f"Delete {len(uncategorized)} group(s) from '{DEFAULT_CATEGORY}'?\n\nThis will remove those selection sets permanently.",
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        try:
            deleted = self.manager.delete_uncategorized_groups()
            self.refresh_ui()
            self._show_info(f"Deleted {deleted} uncategorized group(s).")
        except Exception as exc:
            self._show_error(str(exc))

    def _set_group_color(self, group_id: int) -> None:
        color = self._choose_color()
        group = self.manager.require_group(group_id)
        group.color = color
        group.modified_at = time.time()
        self.refresh_ui()

    def _show_group_validation(self, group_id: int) -> None:
        result = self.manager.validate_group(group_id)
        message = (
            f"Group: {result['group_name']}\n"
            f"Stored members: {result['total']}\n"
            f"Resolved: {len(result['resolved'])}\n"
            f"Missing: {len(result['missing'])}"
        )
        if result["missing"]:
            message += "\n\nMissing objects:\n" + "\n".join(result["missing"][:20])
            if len(result["missing"]) > 20:
                message += "\n..."
        self._show_info(message)

    def _repair_group(self, group_id: int) -> None:
        try:
            repaired, dropped = self.manager.repair_group_paths(group_id)
            self.refresh_ui()
            self._show_info(f"Repair complete. Repaired: {repaired}   Dropped missing: {dropped}")
        except Exception as exc:
            self._show_error(str(exc))

    def _delete_group(self, group_id: int) -> None:
        group = self.manager.require_group(group_id)
        confirm = QtWidgets.QMessageBox.question(self, "Delete Group", f"Delete group '{group.name}'?")
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        try:
            self.manager.delete_group(group_id)
            self.refresh_ui()
        except Exception as exc:
            self._show_error(str(exc))

    def validate_all_groups(self) -> None:
        results = self.manager.validate_all()
        total_missing = sum(len(data["missing"]) for data in results.values())
        invalid_groups = [data for data in results.values() if data["missing"]]
        self.refresh_ui()
        if not invalid_groups:
            self._show_info("All groups are valid.")
            return
        message = f"Found {len(invalid_groups)} group(s) with missing objects. Total missing objects: {total_missing}."
        self._show_info(message)

    # ----- persistence -----
    def save_to_scene(self) -> None:
        try:
            self.manager.save_to_scene_node()
            self._show_info("Groups saved to the scene.")
        except Exception as exc:
            self._show_error(str(exc))

    def load_from_scene(self, show_feedback: bool = True) -> None:
        try:
            found = self.manager.load_from_scene_node()
            self.refresh_ui()
            if show_feedback:
                self._show_info("Groups loaded from the scene." if found else "No saved scene data found.")
        except Exception as exc:
            self._show_error(str(exc))

    def export_json(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export JSON", "", "JSON Files (*.json)")
        if not file_path:
            return
        try:
            self.manager.export_to_json(file_path)
            self._show_info("Groups exported successfully.")
        except Exception as exc:
            self._show_error(str(exc))

    def import_json(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import JSON", "", "JSON Files (*.json)")
        if not file_path:
            return
        try:
            self.manager.import_from_json(file_path)
            self.refresh_ui()
            self._show_info("Groups imported successfully.")
        except Exception as exc:
            self._show_error(str(exc))

    # ----- dialogs -----
    def show_help(self) -> None:
        self._show_text_dialog(
            "Help",
            f"""{TOOL_TITLE} helps you build clickable Maya selection buttons so you can quickly reselect controls, props, or rig parts without hunting through the Outliner.\n\n"
            "Quick Start\n"
            "1. Select one or more objects in Maya.\n"
            "2. Click the large Select_Set button or the + button.\n"
            "3. Give the new button a name, choose a category, and pick a color.\n"
            "4. Click the new selection button later to reselect those objects.\n\n"
            "Categories\n"
            "- Categories are blocks that hold related selection buttons.\n"
            "- Use categories for characters, props, cameras, or different rig sections.\n"
            "- Prefix lets you apply or remap a namespace-style prefix for that category.\n"
            "- Pop Out opens a smaller floating picker window for that category only.\n"
            "- Rename changes the category name shown in the UI.\n"
            "- Delete removes the category block. If it is a normal category, its buttons are moved to Uncategorized.\n\n"
            "Selection Buttons\n"
            "- Left-click selects the stored objects.\n"
            "- Shift + click adds that group to the current Maya selection.\n"
            "- Right-click a button for extra tools like rename, recolor, replace members, add members, remove members, validate, or move to another category.\n"
            "- You can drag a selection button onto another category block to move it there.\n\n"
            "Saving\n"
            "- Save to Scene stores the data inside the current Maya file.\n"
            "- Load from Scene restores saved groups from the Maya file.\n"
            "- Export JSON creates a backup file you can reuse in other scenes.\n"
            "- Import JSON loads a saved backup file.\n"
            "- The tool also tries to auto-save when the main window closes.\n\n"
            "Validation\n"
            "- Validate checks whether stored objects still exist.\n"
            "- This is useful after rig updates, renaming, or reference swaps.\n"
            "- Missing objects can often be repaired by applying the correct category prefix or editing the group membership.\n\n"
            "Pop-Out Windows\n"
            "- Pop-out windows are small floating pickers for one category.\n"
            "- They can stay open even if the main window is minimized.\n"
            "- Each pop-out has its own opacity slider and close button.\n\n"
            "Tips\n"
            "- Make one category per character or rig for cleaner organization.\n"
            "- Use clear button names like Left Arm, Face Ctrls, or Props.\n"
            "- Export JSON before major scene or rig changes as a backup.\n"
            "- If buttons stop selecting correctly after a rig update, run Validate and reapply the category prefix.\n"""
        )

    def show_about(self) -> None:
        self._show_text_dialog(
            "About",
            f"""{TOOL_TITLE}\nVersion {TOOL_VERSION}\n\n"
            "Smart Select Sets is a Maya picker and selection-set tool designed to make character and shot work faster. It lets you store object selections as named buttons, organize them into categories, and open small pop-out pickers for focused animation work.\n\n"
            "Main features\n"
            "- Category-based selection buttons\n"
            "- Drag and drop buttons between categories\n"
            "- Prefix remapping for category-based namespaces\n"
            "- Pop-out picker windows for individual categories\n"
            "- Scene save/load plus JSON import/export\n"
            "- Validation tools for missing or renamed objects\n"
            "- Auto-save support when closing the main window\n\n"
            "Typical use\n"
            "This tool is useful for character rigs, props, facial controls, body controls, camera sets, and shot-specific animation helpers.\n\n"
            "How it stores data\n"
            "Groups are stored with long Maya object paths when possible for better reliability. The tool can save that data into the Maya scene and also export it as JSON for backup or reuse.\n\n"
            "Goal\n"
            "The goal of the tool is to give you a cleaner, faster way to manage selection sets than relying only on the Outliner or manual selection.\n"""
        )

    def _show_text_dialog(self, title: str, text: str) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"{TOOL_TITLE} - {title}")
        dialog.resize(560, 520)
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        text_edit = QtWidgets.QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(text)
        text_edit.setObjectName("InfoTextDialog")
        layout.addWidget(text_edit, 1)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        dialog.exec()


    def _show_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Smart Select Sets", message)

    def _show_info(self, message: str) -> None:
        QtWidgets.QMessageBox.information(self, "Smart Select Sets", message)



class CategoryPopoutWindow(QtWidgets.QDialog):
    def __init__(self, category_name: str, manager: SmartSelectSetsManager, host_window: SmartSelectSetsWindow):
        # Parent the popout to Maya's main window instead of the main Smart Select Sets window
        # so the popout stays open when the main manager window is minimized.
        super().__init__(maya_main_window())
        self.manager = manager
        self.host_window = host_window
        self.category_name = category_name
        self.group_buttons: Dict[int, GroupButton] = {}
        self._drag_active = False
        self._drag_offset = QtCore.QPoint()
        self._opacity_value = 100

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setObjectName(f"{TOOL_NAME}_{category_name}_Popout")
        self.setWindowFlags(
            QtCore.Qt.Tool |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.resize(360, 220)
        self.setMinimumSize(240, 120)
        self.setStyleSheet(self._popup_stylesheet())
        self._build_ui()
        self._update_opacity(self._opacity_value)
        self.refresh_buttons()

    def _popup_stylesheet(self) -> str:
        return f"""
        QDialog {{
            background: transparent;
            color: #ececec;
        }}
        QFrame#PopupChrome {{
            background-color: #2b2b2b;
            border: 1px solid #474747;
            border-radius: 12px;
        }}
        QFrame#PopupHeader {{
            background-color: #343434;
            border: 1px solid #484848;
            border-radius: 12px;
        }}
        QLabel#PopupTitle {{
            font-weight: 700;
            font-size: 13px;
            color: #f2f2f2;
        }}
        QLabel#PopupSubtitle {{
            color: #b8b8b8;
            font-size: 11px;
        }}
        QPushButton#PopupCloseButton {{
            background-color: transparent;
            border: none;
            color: #dddddd;
            font-size: 20px;
            font-weight: 700;
            padding: 0px;
        }}
        QPushButton#PopupCloseButton:hover {{
            color: white;
        }}
        QSlider#PopupOpacitySlider::groove:horizontal {{
            background: #3d3d3d;
            height: 4px;
            border-radius: 2px;
        }}
        QSlider#PopupOpacitySlider::handle:horizontal {{
            background: {HEADER_ACCENT};
            width: 10px;
            margin: -5px 0;
            border-radius: 5px;
            border: 1px solid #8b73cf;
        }}
        QSlider#PopupOpacitySlider::sub-page:horizontal {{
            background: #7d69b6;
            border-radius: 2px;
        }}
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        """

    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(0)

        self.chrome = QtWidgets.QFrame()
        self.chrome.setObjectName("PopupChrome")
        chrome_layout = QtWidgets.QVBoxLayout(self.chrome)
        chrome_layout.setContentsMargins(10, 10, 10, 10)
        chrome_layout.setSpacing(8)
        outer.addWidget(self.chrome)

        self.header = QtWidgets.QFrame()
        self.header.setObjectName("PopupHeader")
        header_layout = QtWidgets.QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        header_layout.setSpacing(8)
        chrome_layout.addWidget(self.header)

        label_col = QtWidgets.QVBoxLayout()
        label_col.setContentsMargins(0, 0, 0, 0)
        label_col.setSpacing(2)
        header_layout.addLayout(label_col, 1)

        self.title_label = QtWidgets.QLabel()
        self.title_label.setObjectName("PopupTitle")
        label_col.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel("Click to select. Right-click for group options.")
        self.subtitle_label.setObjectName("PopupSubtitle")
        label_col.addWidget(self.subtitle_label)

        opacity_col = QtWidgets.QVBoxLayout()
        opacity_col.setContentsMargins(0, 0, 0, 0)
        opacity_col.setSpacing(2)
        header_layout.addLayout(opacity_col)

        self.opacity_label = QtWidgets.QLabel("Opacity")
        self.opacity_label.setObjectName("PopupSubtitle")
        self.opacity_label.setAlignment(QtCore.Qt.AlignCenter)
        opacity_col.addWidget(self.opacity_label)

        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setObjectName("PopupOpacitySlider")
        self.opacity_slider.setRange(25, 100)
        self.opacity_slider.setValue(self._opacity_value)
        self.opacity_slider.setFixedWidth(90)
        self.opacity_slider.valueChanged.connect(self._update_opacity)
        opacity_col.addWidget(self.opacity_slider)

        self.close_button = QtWidgets.QPushButton("×")
        self.close_button.setObjectName("PopupCloseButton")
        self.close_button.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.close)
        header_layout.addWidget(self.close_button, 0, QtCore.Qt.AlignTop)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        chrome_layout.addWidget(self.scroll_area, 1)

        self.content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)
        self.content_layout.addStretch(1)
        self.scroll_area.setWidget(self.content_widget)

        self.header.installEventFilter(self)
        self.chrome.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj in (self.header, self.chrome):
            if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                child = self.childAt(self.mapFromGlobal(event.globalPosition().toPoint()))
                if child is self.close_button or self.close_button.isAncestorOf(child):
                    return super().eventFilter(obj, event)
                self._drag_active = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            elif event.type() == QtCore.QEvent.MouseMove and self._drag_active and (event.buttons() & QtCore.Qt.LeftButton):
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                self._drag_active = False
                return True
        return super().eventFilter(obj, event)

    def _update_opacity(self, value: int) -> None:
        self._opacity_value = max(25, min(100, int(value)))
        self.setWindowOpacity(self._opacity_value / 100.0)

    def _clear_content(self) -> None:
        while self.content_layout.count() > 1:
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget:
                        child_widget.deleteLater()
                child_layout.deleteLater()
        self.group_buttons.clear()

    def refresh_buttons(self) -> None:
        if self.category_name not in self.manager.categories:
            self.close()
            return

        category = self.manager.categories[self.category_name]
        display_label = self.manager.get_category_label(self.category_name)
        self.setWindowTitle(f"{category.prefix or display_label} Sets")
        self.title_label.setText(category.prefix or display_label)

        subtitle = display_label
        if category.prefix:
            subtitle += f"  •  Prefix: {category.prefix}"
        self.subtitle_label.setText(subtitle)

        self._clear_content()

        flow = FlowLayout()
        groups = [g for g in self.manager.groups.values() if g.category == self.category_name]
        groups.sort(key=lambda g: g.name.lower())
        validation = self.manager.validate_all()

        if not groups:
            empty = QtWidgets.QLabel("No groups in this set yet.")
            empty.setStyleSheet("color: #8e8e8e; font-style: italic; padding: 6px;")
            self.content_layout.insertWidget(self.content_layout.count() - 1, empty)
            return

        for group in groups:
            label = f"{category.prefix}:{group.name}" if category.prefix else group.name
            button = GroupButton(group.group_id, label, group.color)
            button.setMinimumHeight(40)
            state = validation.get(group.group_id, {})
            if state.get("missing"):
                button.setToolTip(
                    "Missing objects:\n" + "\n".join(state["missing"][:12]) +
                    ("\n..." if len(state["missing"]) > 12 else "")
                )
                button.setStyleSheet(button.styleSheet() + "QPushButton { border: 2px solid #c98500; }")
            else:
                button.setToolTip("All objects resolved.")
            button.clickedWithId.connect(self.host_window.on_group_button_clicked)
            button.contextMenuRequestedForId.connect(self.host_window.show_group_context_menu)
            self.group_buttons[group.group_id] = button
            flow.addWidget(button)

        self.content_layout.insertLayout(self.content_layout.count() - 1, flow)


class CreateGroupDialog(QtWidgets.QDialog):
    def __init__(self, category_pairs: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Selection Group")
        self.resize(380, 140)
        self.chosen_color = [0.7, 0.7, 0.7]
        self._category_pairs = list(category_pairs)

        layout = QtWidgets.QVBoxLayout(self)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Group name")
        layout.addWidget(self.name_edit)

        self.category_combo = QtWidgets.QComboBox()
        for label, internal_name in self._category_pairs:
            self.category_combo.addItem(label, internal_name)
        layout.addWidget(self.category_combo)

        row = QtWidgets.QHBoxLayout()
        color_btn = QtWidgets.QPushButton("Choose Color")
        color_btn.clicked.connect(self.choose_color)
        row.addWidget(color_btn)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(parent=self)
        if color.isValid():
            self.chosen_color = [color.redF(), color.greenF(), color.blueF()]

    def get_values(self) -> Tuple[str, str]:
        return self.name_edit.text().strip(), str(self.category_combo.currentData() or self.category_combo.currentText().strip())


# ------------------------------
# Helper widgets
# ------------------------------

class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0

        for item in self._items:
            space_x = self.spacing()
            space_y = self.spacing()
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


# ------------------------------
# Maya integration
# ------------------------------

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is None:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def show_smart_select_sets() -> SmartSelectSetsWindow:
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if widget.objectName() == SmartSelectSetsWindow.WINDOW_OBJECT_NAME:
            try:
                widget.close()
                widget.deleteLater()
            except Exception:
                pass

    window = SmartSelectSetsWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    return window


# Legacy-friendly alias for shelf buttons / old launchers.
def create_selection_group_manager_ui():
    return show_smart_select_sets()

