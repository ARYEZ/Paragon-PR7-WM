"""The folder compare tab: both paths, the filter, Include subfolders, the Show choices, and every item's result
(WinMerge's folder window, its flat view: each file with its Folder column; a folder that's only on one side is one
row). The compare runs on a thread (inline when `sync`); the list is a plain Python model (never QStandardItemModel:
PR7-Z's crash)."""

from __future__ import annotations

import datetime
import threading

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QStyle, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget)

from . import diff, folders, settings, textio, theme, widgets
from .panes import colours

COLUMNS = ["NAME", "FOLDER", "COMPARISON RESULT", "LEFT DATE", "RIGHT DATE", "SIZE"]
SHOW = [("identical", "Show identical"), ("different", "Show different"), ("left", "Show left only"),
        ("right", "Show right only"), ("skipped", "Show skipped")]


def when(t: float | None) -> str:
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M") if t else ""


class FolderModel(QAbstractTableModel):
    def __init__(self, page: "FolderPage"):
        super().__init__()
        self.page = page
        self.rows: list[folders.Item] = []
        self.sort_col, self.sort_desc = -1, False

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self._sort()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def item(self, row: int) -> folders.Item | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def _text(self, it: folders.Item, col: int) -> str:
        if col == 0:
            return it.name
        if col == 1:
            return it.folder.replace("/", "\\")
        if col == 2:
            return folders.result_text(it, self.page.left_root, self.page.right_root)
        if col == 3:
            return when(it.left.mtime) if it.left and not it.is_dir else ""
        if col == 4:
            return when(it.right.mtime) if it.right and not it.is_dir else ""
        if col == 5:
            if it.is_dir:
                return ""
            sizes = {x.size for x in (it.left, it.right) if x}
            return "  /  ".join(textio.fmt_size(s) for s in sorted(sizes))
        return ""

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        it = self.item(index.row())
        if it is None:
            return None
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(it, col)
        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            return widgets.file_icon("folder" if it.is_dir else widgets.kind_of(it.name), 18)
        if role == Qt.ItemDataRole.ForegroundRole and col == 2:
            g = it.group()
            c = colours()
            if g == "different":
                return c["pink"]
            if g in ("left", "right"):
                return c["orange"]
            return QColor(theme.TEXT_DIM)
        if role == Qt.ItemDataRole.ToolTipRole:
            return it.rel.replace("/", "\\")
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.beginResetModel()
        self.sort_col, self.sort_desc = column, order == Qt.SortOrder.DescendingOrder
        self._sort()
        self.endResetModel()

    def _sort(self):
        if self.sort_col < 0:
            return
        c = self.sort_col

        def k(it):
            if c == 5:
                return max((x.size for x in (it.left, it.right) if x), default=-1)
            if c in (3, 4):
                x = it.left if c == 3 else it.right
                return x.mtime if x else 0
            return self._text(it, c).casefold()
        self.rows.sort(key=k, reverse=self.sort_desc)


class Band(QStyledItemDelegate):
    """The family's selection band, one gradient across the whole row (the style sheet would restart it per cell)."""

    def paint(self, painter, option, index):
        if option.state & QStyle.StateFlag.State_Selected:
            view = self.parent()
            w = view.viewport().width()
            painter.save()
            painter.setOpacity(0.24)
            painter.fillRect(option.rect, theme.family_gradient(-view.horizontalOffset(), 0, w, 0))
            painter.restore()
            option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, index)


class _Bridge(QObject):
    done = Signal(object, object)          # items, error
    progress = Signal(str)


class FolderPage(QWidget):
    changed = Signal()
    open_files = Signal(object)            # an Item: open its file compare

    kind = "folder"

    def __init__(self, left: str, right: str, recursive: bool = True, filter_text: str = folders.DEFAULT_FILTER,
                 method: str = "full", options: diff.Options | None = None, parent=None, sync: bool = False,
                 ask=None):
        super().__init__(parent)
        self.left_root, self.right_root = left, right
        self.method, self.options = method, options or diff.Options()
        self.sync = sync
        self.ask = ask                      # the window's _ask
        self.items: list[folders.Item] = []
        self.running = False
        self.error = ""
        self._cancel = threading.Event()
        self.bridge = _Bridge()
        self.bridge.done.connect(self._compared)
        self.bridge.progress.connect(self._progress)
        self.progress_text = ""

        def field(text):
            lab = QLabel(text.upper())
            lab.setProperty("role", "field")
            return lab
        paths = QHBoxLayout()
        paths.addWidget(field("Left"))
        self.left_edit = QLineEdit(left)
        self.left_edit.returnPressed.connect(self.refresh)
        paths.addWidget(self.left_edit, 1)
        paths.addWidget(field("Right"))
        self.right_edit = QLineEdit(right)
        self.right_edit.returnPressed.connect(self.refresh)
        paths.addWidget(self.right_edit, 1)
        opts = QHBoxLayout()
        opts.addWidget(field("Filter"))
        self.filter_edit = QLineEdit(filter_text)
        self.filter_edit.setFixedWidth(260)
        self.filter_edit.setToolTip("Masks separated by ;  ·  !mask leaves files out  ·  !name\\ leaves a folder out")
        self.filter_edit.returnPressed.connect(self.refresh)
        opts.addWidget(self.filter_edit)
        self.recursive = QCheckBox("Include subfolders")
        self.recursive.setChecked(recursive)
        self.recursive.toggled.connect(lambda _: self.refresh())
        opts.addWidget(self.recursive)
        shown = settings.get_list("show") or [k for k, _ in SHOW]
        self.show_boxes: dict[str, QCheckBox] = {}
        for key, text in SHOW:
            c = QCheckBox(text)
            c.setChecked(key in shown)
            c.toggled.connect(self._show_changed)
            opts.addWidget(c)
            self.show_boxes[key] = c
        opts.addStretch(1)
        self.model = FolderModel(self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(Band(self.view))
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setShowGrid(False)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(26)
        self.view.setWordWrap(False)
        self.view.setIconSize(QSize(18, 18))
        h = self.view.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.view.setColumnWidth(0, 260)
        self.view.setColumnWidth(1, 160)
        for c in (3, 4):
            self.view.setColumnWidth(c, 140)
        self.view.setColumnWidth(5, 160)
        self.view.doubleClicked.connect(lambda idx: self.open_item(self.model.item(idx.row())))
        self.view.selectionModel().selectionChanged.connect(lambda *a: self.changed.emit())
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.restyle()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.addLayout(paths)
        lay.addLayout(opts)
        lay.addWidget(self.view, 1)

    # ----------------------------------------------------------------- comparing
    def title(self) -> str:
        import os
        name = os.path.basename(self.left_root.rstrip("/\\")) or self.left_root
        return f"{name}  ·  folders"

    def modified(self) -> bool:
        return False

    def restyle(self):
        # Qt's own selection colour would be drawn under the family's band (dark red in AURORA): none
        self.view.setStyleSheet("QTableView { selection-background-color: transparent; } "
                                "QTableView::item:selected { background: transparent; }")
        self.view.viewport().update()

    def refresh(self):
        """Compare again (F5; also after a path, the filter or Include subfolders changed)."""
        import os
        self.left_root, self.right_root = self.left_edit.text().strip(), self.right_edit.text().strip()
        if not (os.path.isdir(self.left_root) and os.path.isdir(self.right_root)):
            self.error = "Both sides must be folders that exist"
            self.items = []
            self.show_rows()
            return
        settings.set("folder_filter", self.filter_edit.text())
        self._cancel.clear()
        self.running, self.error = True, ""
        self.changed.emit()
        args = (self.left_root, self.right_root, self.recursive.isChecked(), folders.Filter(self.filter_edit.text()),
                self.method, self.options)

        def work():
            try:
                got = folders.compare(*args, progress=(None if self.sync else self.bridge.progress.emit),
                                      cancelled=self._cancel.is_set)
                self.bridge.done.emit(got, None)
            except folders.Cancelled:
                self.bridge.done.emit(None, "Stopped")
            except Exception as e:  # noqa: BLE001 - shown in the status line
                self.bridge.done.emit(None, str(e))
        if self.sync:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def stop(self):
        self._cancel.set()

    def _progress(self, rel: str):
        self.progress_text = rel
        self.changed.emit()

    def _compared(self, items, error):
        self.running = False
        if error:
            self.error = error
        else:
            self.items = items
        self.show_rows()

    def shown_groups(self) -> set[str]:
        return {k for k, c in self.show_boxes.items() if c.isChecked()}

    def _show_changed(self):
        settings.set("show", sorted(self.shown_groups()))
        self.show_rows()

    def set_show(self, key: str, on: bool):
        self.show_boxes[key].setChecked(on)

    def show_rows(self):
        groups = self.shown_groups()
        rows = [it for it in self.items
                if not (it.is_dir and it.left and it.right) and it.result and it.group() in groups]
        keep = {it.rel for it in self.selected()}
        self.model.set_rows(rows)
        for i, it in enumerate(self.model.rows):
            if it.rel in keep:
                self.view.selectRow(i)
        self.changed.emit()

    # ----------------------------------------------------------------- selection and actions
    def selected(self) -> list[folders.Item]:
        rows = sorted({i.row() for i in self.view.selectionModel().selectedRows()}) if self.view.selectionModel() else []
        return [self.model.rows[r] for r in rows if r < len(self.model.rows)]

    def select(self, rel: str) -> bool:
        for i, it in enumerate(self.model.rows):
            if it.rel == rel:
                self.view.selectRow(i)
                self.view.scrollTo(self.model.index(i, 0))
                return True
        return False

    def open_item(self, it: folders.Item | None):
        if it is not None and not it.is_dir:
            self.open_files.emit(it)

    def next(self):
        return self._step(1)

    def prev(self):
        return self._step(-1)

    def first(self):
        return self._jump(False)

    def last(self):
        return self._jump(True)

    def current(self):
        sel = self.selected()
        if sel:
            self.open_item(sel[0])
            return True
        return False

    def _differs(self, it: folders.Item) -> bool:
        return it.group() in ("different", "left", "right")

    def _step(self, d: int) -> bool:
        rows = self.model.rows
        cur = self.view.currentIndex().row()
        i = cur + d
        while 0 <= i < len(rows):
            if self._differs(rows[i]):
                self.view.selectRow(i)
                self.view.scrollTo(self.model.index(i, 0))
                return True
            i += d
        return False

    def _jump(self, last: bool) -> bool:
        idx = [i for i, it in enumerate(self.model.rows) if self._differs(it)]
        if not idx:
            return False
        i = idx[-1] if last else idx[0]
        self.view.selectRow(i)
        self.view.scrollTo(self.model.index(i, 0))
        return True

    def can_copy(self, to: str) -> bool:
        src = "left" if to == "right" else "right"
        return any(getattr(it, src) is not None for it in self.selected())

    def copy(self, to: str) -> bool:
        """Copy the selected items to the other side (WinMerge asks first)."""
        src = "left" if to == "right" else "right"
        items = [it for it in self.selected() if getattr(it, src) is not None]
        if not items:
            return False
        what = items[0].name if len(items) == 1 else f"{len(items)} items"
        if not self.ask("confirm", f"Copy {what} to the {to}?\n\nAnything with the same name there is replaced."):
            return False
        errors = []
        for it in items:
            try:
                folders.copy(it, to, self.left_root, self.right_root)
            except OSError as e:
                errors.append(f"{it.rel}: {e.strerror or e}")
        if errors:
            self.ask("say", ("warning", "Some items weren't copied:\n" + "\n".join(errors[:12])))
        self.refresh()
        return not errors

    def delete(self, side: str) -> bool:
        """Delete the selected items' copies on one side ("left" / "right") or both ("both"), to the Recycle Bin."""
        sides = ("left", "right") if side == "both" else (side,)
        jobs = [(it, s) for it in self.selected() for s in sides if getattr(it, s) is not None]
        if not jobs:
            return False
        names = sorted({it.name for it, _ in jobs})
        what = names[0] if len(names) == 1 else f"{len(names)} items"
        where = {"left": "on the left", "right": "on the right", "both": "on both sides"}[side]
        if not self.ask("confirm", f"Move {what} {where} to the Recycle Bin?"):
            return False
        errors = []
        for it, s in jobs:
            try:
                folders.delete(it, s, self.left_root, self.right_root)
            except OSError as e:
                errors.append(f"{it.rel}: {e.strerror or e}")
        if errors:
            self.ask("say", ("warning", "Some items weren't deleted:\n" + "\n".join(errors[:12])))
        self.refresh()
        return not errors

    def paths_of(self, it: folders.Item, side: str) -> str | None:
        if getattr(it, side) is None:
            return None
        return it.path(self.left_root if side == "left" else self.right_root)

    # ----------------------------------------------------------------- status
    def status(self) -> str:
        if self.running:
            return "Comparing…  " + self.progress_text.replace("/", "\\")
        if self.error:
            return self.error
        c = folders.counts(self.items)
        total = sum(c.values())
        parts = [f"{total} item{'s' if total != 1 else ''}", f"{c['different']} different",
                 f"{c['left']} left only", f"{c['right']} right only", f"{c['identical']} identical"]
        if c["skipped"]:
            parts.append(f"{c['skipped']} skipped")
        sel = self.selected()
        if len(sel) > 1:
            parts.append(f"{len(sel)} selected")
        return "  ·  ".join(parts)

