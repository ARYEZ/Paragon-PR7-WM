"""PR7-WM's window: WinMerge's menus and keys around tabs of file compares (panes.FilePage) and folder compares
(folder_page.FolderPage). Every question goes through `_ask(kind)` (tests answer through `answers`); `sync = True`
compares folders and applies edits inline (tests)."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from . import __version__, compare, diff, family, finish, settings, theme, widgets
from .dialogs import OpenDialog, OptionsDialog, load_options
from .folder_page import SHOW, FolderPage
from .panes import FilePage, colours

COLLECT_MS = 700          # Explorer starts one PR7-WM per selected item: paths arriving this close together go together


def data_dir() -> str:
    d = os.environ.get("PR7WM_DATA") or os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                                                     "Paragon", "PR7-WM")
    os.makedirs(d, exist_ok=True)
    return d


def _dim(text=""):
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


class MainWindow(QMainWindow):
    def __init__(self, sync: bool = False):
        super().__init__()
        self.sync = sync
        self.answers: dict = {}
        self.said: list = []
        self.setWindowTitle("Paragon PR7-WM")
        self.setAcceptDrops(True)
        self.resize(1320, 860)
        self.esc_closes = False                  # WinMerge's /e
        self._collected: list[str] = []
        self._collect_timer = QTimer(self)
        self._collect_timer.setSingleShot(True)
        self._collect_timer.setInterval(COLLECT_MS)
        self._collect_timer.timeout.connect(self.flush_collected)
        self._build()
        self.restyle()
        self._sync()

    # ================================================================ building
    def _build(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = widgets.Header("COMPARE")
        lay.addWidget(self.header)
        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 10, 16, 6)
        bl.setSpacing(6)
        self.keys: dict[str, widgets.KeyButton] = {}
        groups = [[("open", "open", "Open", lambda: self.open_dialog()),
                   ("save", "file", "Save", self.save),
                   ("folders", "folders", "Folders", lambda: self.open_dialog(folders_first=True))],
                  [("prev", "diff_prev", "Previous", lambda: self.page_call("prev")),
                   ("next", "diff_next", "Next", lambda: self.page_call("next")),
                   ("copy_right", "copy_right", "Copy Right", lambda: self.copy("right")),
                   ("copy_left", "copy_left", "Copy Left", lambda: self.copy("left"))],
                  [("refresh", "refresh", "Refresh", self.refresh), ("options", "gear", "Options", self.options)]]
        for i, group in enumerate(groups):
            if i:
                sep = QLabel()
                sep.setObjectName("sep")
                sep.setFixedSize(1, 40)
                bl.addSpacing(8)
                bl.addWidget(sep)
                bl.addSpacing(8)
            for key, icon, label, slot in group:
                k = widgets.KeyButton(icon, label)
                k.setFixedSize(QSize(100, 62))
                k.clicked.connect(lambda _=False, s=slot: s())
                bl.addWidget(k)
                self.keys[key] = k
        bl.addStretch(1)
        lay.addWidget(bar)

        self.stack = QStackedWidget()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)          # no light base line under the tabs
        self.tabs.tabCloseRequested.connect(lambda i: self.close_tab(i))
        self.tabs.currentChanged.connect(lambda _: self._sync())
        self.welcome = QLabel("OPEN TWO FILES OR FOLDERS TO COMPARE\n\nCtrl+O, or drop them on this window")
        self.welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome.setProperty("role", "dim")
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.tabs)
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(16, 0, 16, 0)
        wl.addWidget(self.stack)
        lay.addWidget(wrap, 1)

        foot = QFrame()
        foot.setObjectName("foot")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(16, 6, 16, 6)
        self.status = _dim("")
        fl.addWidget(self.status, 1)
        self.legend = QLabel("")
        fl.addWidget(self.legend)
        lay.addWidget(foot)
        self._menus()

    def _act(self, menu, text, slot, keys=None, key=None, checkable=False):
        a = QAction(text, self)
        if keys:
            a.setShortcuts([QKeySequence(k) for k in (keys if isinstance(keys, (list, tuple)) else [keys])])
        a.setCheckable(checkable)
        a.triggered.connect(lambda *_: slot())
        menu.addAction(a)
        if key:
            self.acts[key] = a
        return a

    def _menus(self):
        self.acts: dict[str, QAction] = {}
        mb = self.menuBar()
        m = mb.addMenu("&File")
        self._act(m, "Open…", self.open_dialog, "Ctrl+O", "open")
        m.addSeparator()
        self._act(m, "Save", self.save, "Ctrl+S", "save")
        self._act(m, "Save Left", lambda: self.save_side("left"), None, "save_left")
        self._act(m, "Save Left As…", lambda: self.save_side("left", as_new=True), None, "save_left_as")
        self._act(m, "Save Right", lambda: self.save_side("right"), None, "save_right")
        self._act(m, "Save Right As…", lambda: self.save_side("right", as_new=True), None, "save_right_as")
        m.addSeparator()
        self._act(m, "Close", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W", "close")
        m.addSeparator()
        self._act(m, "Exit", self.close, "Alt+F4")
        m = mb.addMenu("&Edit")
        self._act(m, "Undo", self.undo, "Ctrl+Z", "undo")
        self._act(m, "Redo", self.redo, ["Ctrl+Y", "Ctrl+Shift+Z"], "redo")
        m.addSeparator()
        self._act(m, "Find…", self.find, "Ctrl+F", "find")
        self._act(m, "Find Next", lambda: self.find(again=True), "F3", "find_next")
        self._act(m, "Go To…", self.go_to, "Ctrl+G", "goto")
        m.addSeparator()
        self._act(m, "Options…", self.options, None, "options")
        m = mb.addMenu("&View")
        self._act(m, "Location Pane", lambda: self.toggle_pane("location_pane"), None, "location_pane", True)
        self._act(m, "Diff Pane", lambda: self.toggle_pane("diff_pane"), None, "diff_pane", True)
        self.acts["location_pane"].setChecked(settings.get_bool("location_pane", True))
        self.acts["diff_pane"].setChecked(settings.get_bool("diff_pane", False))
        m.addSeparator()
        for key, text in SHOW:
            a = self._act(m, text.title(), lambda k=key: self.toggle_show(k), None, "show_" + key, True)
            a.setChecked(key in (settings.get_list("show") or [k for k, _ in SHOW]))
        m.addSeparator()
        self._act(m, "Refresh", self.refresh, "F5", "refresh")
        fm = m.addMenu("Finish")
        group = QActionGroup(self)
        self.finish_acts = {}
        for name in ("obsidian", "aurora"):
            a = self._act(fm, name.upper(), lambda n=name: self.set_finish(n), checkable=True)
            group.addAction(a)
            self.finish_acts[name] = a
        self.finish_acts[theme.FINISH].setChecked(True)
        m = mb.addMenu("&Merge")
        self._act(m, "Next Difference", lambda: self.page_call("next"), "Alt+Down", "next")
        self._act(m, "Previous Difference", lambda: self.page_call("prev"), "Alt+Up", "prev")
        self._act(m, "First Difference", lambda: self.page_call("first"), "Alt+Home", "first")
        self._act(m, "Last Difference", lambda: self.page_call("last"), "Alt+End", "last")
        self._act(m, "Current Difference", lambda: self.page_call("current"), "Alt+Return", "current")
        m.addSeparator()
        self._act(m, "Copy to Right", lambda: self.copy("right"), "Alt+Right", "copy_right")
        self._act(m, "Copy to Left", lambda: self.copy("left"), "Alt+Left", "copy_left")
        self._act(m, "Copy All to Right", lambda: self.copy_all("right"), None, "copy_all_right")
        self._act(m, "Copy All to Left", lambda: self.copy_all("left"), None, "copy_all_left")
        m.addSeparator()
        self._act(m, "Delete", lambda: self.delete("both"), "Del", "delete")
        self._act(m, "Delete Left", lambda: self.delete("left"), None, "delete_left")
        self._act(m, "Delete Right", lambda: self.delete("right"), None, "delete_right")
        m = mb.addMenu("&Tools")
        self._act(m, "Generate Patch…", self.generate_patch, None, "patch")
        self._act(m, "Compare in the Explorer Menu", self.toggle_explorer_menu, None, "explorer_menu", True)
        m = mb.addMenu("&Help")
        self._act(m, "Check for Updates…", self.check_updates, None, "updates")
        self._act(m, "About PR7-WM", self.about, None, "about")
        self._explorer_menu_state()

    # ================================================================ look
    def restyle(self):
        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.palette())
            app.setStyleSheet(theme.stylesheet())
        self.centralWidget().setStyleSheet(
            f"QWidget#central {{ background: {theme.BACKGROUND}; }} QLabel#sep {{ background: {theme.PANEL_EDGE}; }} "
            f"QFrame#foot {{ background: {theme.TAB_FRAME}; border-top: 1px solid {theme.PANEL_EDGE}; }} "
            f"QTabWidget::pane {{ border: none; background: {theme.BACKGROUND}; }}")
        c = colours()
        self.legend.setText(f"<span style='color:{c['pink'].name()}'>■</span> changed     "
                            f"<span style='color:{c['orange'].name()}'>■</span> only on one side")
        self.legend.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
        self.header.update()
        for a_name, a in getattr(self, "finish_acts", {}).items():
            a.setChecked(a_name == theme.FINISH)
        for page in self.pages():
            page.restyle()

    def set_finish(self, name: str):
        theme.set_finish(name)
        finish.set(theme.FINISH)                 # every family app follows (finish.py)
        settings.set("finish", theme.FINISH)
        self.restyle()

    # ================================================================ asking
    def _ask(self, kind: str, payload=None):
        if kind in self.answers:
            a = self.answers[kind]
            return a(payload) if callable(a) else a
        if kind == "say":
            k, text = payload
            self._say(k, text)
            return None
        if kind == "confirm":
            return QMessageBox.question(self, "PR7-WM", payload) == QMessageBox.StandardButton.Yes
        if kind == "save_changes":           # (name) -> save / discard / cancel
            box = QMessageBox(QMessageBox.Icon.Question, "PR7-WM", f"Save the changes to {payload}?", parent=self)
            save = box.addButton("SAVE", QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton("DON'T SAVE", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("CANCEL", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            return "save" if box.clickedButton() is save else "discard" if box.clickedButton() is discard else "cancel"
        if kind == "save_as":
            return QFileDialog.getSaveFileName(self, f"Save the {payload[0]} side as", payload[1] or "")[0]
        if kind == "patch_file":
            return QFileDialog.getSaveFileName(self, "Generate Patch", payload, "Patches (*.patch *.diff)")[0]
        if kind == "open":
            dlg = OpenDialog(self, *payload)
            return dlg.values() if dlg.exec() else None
        if kind == "options":
            dlg = OptionsDialog(self)
            if dlg.exec():
                dlg.save()
                return True
            return False
        if kind == "find":
            text, ok = QInputDialog.getText(self, "Find", "FIND WHAT", text=payload or "")
            return text if ok else None
        if kind == "goto":
            n, ok = QInputDialog.getInt(self, "Go To", "LINE NUMBER", 1, 1, max(1, payload))
            return n if ok else None
        if kind == "reload":
            return QMessageBox.question(self, "PR7-WM", payload) == QMessageBox.StandardButton.Yes
        return None

    def _say(self, kind: str, text: str):
        self.said.append((kind, text))
        if "say" in self.answers:
            self.answers["say"](kind, text)
            return
        icon = QMessageBox.Icon.Warning if kind in ("error", "warning") else QMessageBox.Icon.Information
        QMessageBox(icon, "PR7-WM", text, parent=self).exec()

    # ================================================================ tabs
    def pages(self) -> list:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def page(self):
        return self.tabs.currentWidget()

    def _add(self, page, title: str):
        page.changed.connect(lambda p=page: self._page_changed(p))
        i = self.tabs.addTab(page, title)
        self.tabs.setCurrentIndex(i)
        self.tabs.setTabToolTip(i, title)
        self.stack.setCurrentWidget(self.tabs)
        self._sync()
        return page

    def _page_changed(self, page):
        i = self.tabs.indexOf(page)
        if i >= 0:
            self.tabs.setTabText(i, page.title())
        if page is self.page():
            self._sync()

    def compare_paths(self, left: str, right: str, recursive: bool | None = None, filter_text: str | None = None,
                      **kw):
        """Open a compare: two folders -> a folder compare, otherwise a file compare (a folder and a file: the file of
        that name in the folder, as WinMerge does)."""
        left, right = os.path.abspath(left) if left else left, os.path.abspath(right) if right else right
        if left and right and os.path.isdir(left) and os.path.isdir(right):
            return self.compare_folders(left, right, recursive, filter_text)
        if left and right and os.path.isdir(left) != os.path.isdir(right):
            if os.path.isdir(left):
                left = os.path.join(left, os.path.basename(right))
            else:
                right = os.path.join(right, os.path.basename(left))
        for p in (left, right):
            if p and not os.path.isfile(p):
                self._say("error", f"{p} isn't there.")
                return None
        return self.compare_files(left, right, **kw)

    def compare_files(self, left: str | None, right: str | None, options: diff.Options | None = None, **kw):
        try:
            doc = compare.FileCompare.open(left, right, options or load_options(), **kw)
        except OSError as e:
            self._say("error", f"Couldn't open {e.filename or ''}:\n{e.strerror or e}")
            return None
        page = FilePage(doc, sync=self.sync)
        self._add(page, page.title())
        if not doc.binary and not doc.counted and left and right:
            self._say("info", "The selected files are identical.")
        page.panes["left"].setFocus()
        return page

    def compare_folders(self, left: str, right: str, recursive: bool | None = None, filter_text: str | None = None):
        page = FolderPage(left, right,
                          settings.get_bool("recursive", True) if recursive is None else recursive,
                          filter_text if filter_text is not None else
                          (settings.get("folder_filter", "*.*") or "*.*"),
                          settings.get("folder_method", "full") or "full", load_options(), sync=self.sync,
                          ask=self._ask)
        page.open_files.connect(lambda it, p=page: self.open_folder_item(p, it))
        page.view.customContextMenuRequested.connect(lambda pos, p=page: self._folder_menu(p, pos))
        self._add(page, page.title())
        page.refresh()
        return page

    def open_folder_item(self, page: FolderPage, it):
        self.compare_files(page.paths_of(it, "left"), page.paths_of(it, "right"), page.options)

    def close_tab(self, i: int) -> bool:
        page = self.tabs.widget(i)
        if page is None:
            return False
        if not self._may_close(page):
            return False
        if isinstance(page, FolderPage):
            page.stop()
        self.tabs.removeTab(i)
        page.deleteLater()
        if not self.tabs.count():
            self.stack.setCurrentWidget(self.welcome)
        self._sync()
        return True

    def _may_close(self, page) -> bool:
        if not isinstance(page, FilePage):
            return True
        page.apply_edits()
        for side in ("left", "right"):
            s = page.doc.side(side)
            if not s.modified:
                continue
            got = self._ask("save_changes", s.name)
            if got == "cancel" or got is None:
                return False
            if got == "save" and not self._save_side(page, side):
                return False
        return True

    def closeEvent(self, e):
        for page in self.pages():
            if not self._may_close(page):
                e.ignore()
                return
        for page in self.pages():
            if isinstance(page, FolderPage):
                page.stop()
        e.accept()

    # ================================================================ commands
    def open_dialog(self, left: str = "", right: str = "", folders_first: bool = False):
        got = self._ask("open", (left, right, folders_first))
        if not got:
            return None
        return self.compare_paths(got["left"], got["right"], got.get("recursive"), got.get("filter"),
                                  wl=got.get("wl", False), wr=got.get("wr", False))

    def page_call(self, name: str):
        page = self.page()
        if page is not None and hasattr(page, name):
            got = getattr(page, name)()
            self._sync()
            return got
        return None

    def copy(self, to: str):
        page = self.page()
        if page is None:
            return False
        got = page.copy(to)
        self._sync()
        return got

    def copy_all(self, to: str):
        page = self.page()
        if isinstance(page, FilePage):
            got = page.copy_all(to)
            self._sync()
            return got
        if isinstance(page, FolderPage):
            page.view.selectAll()
            return page.copy(to)
        return False

    def delete(self, side: str):
        page = self.page()
        if isinstance(page, FolderPage):
            return page.delete(side)
        return False                  # in a text pane the Delete key is the pane's own

    def undo(self):
        page = self.page()
        if isinstance(page, FilePage):
            page.undo()
            self._sync()

    def redo(self):
        page = self.page()
        if isinstance(page, FilePage):
            page.redo()
            self._sync()

    def refresh(self):
        page = self.page()
        if isinstance(page, FolderPage):
            page.refresh()
        elif isinstance(page, FilePage):
            self._check_disk(page, asking=True)
            page.recompare()
        self._sync()

    def save(self):
        page = self.page()
        if not isinstance(page, FilePage):
            return False
        page.apply_edits()
        ok = True
        for side in ("left", "right"):
            if page.doc.side(side).modified:
                ok &= self._save_side(page, side)
        self._sync()
        return ok

    def save_side(self, side: str, as_new: bool = False):
        page = self.page()
        if not isinstance(page, FilePage):
            return False
        page.apply_edits()
        got = self._save_side(page, side, as_new)
        self._sync()
        return got

    def _save_side(self, page: FilePage, side: str, as_new: bool = False) -> bool:
        s = page.doc.side(side)
        path = None
        if as_new or not s.path or s.read_only:
            path = self._ask("save_as", (side, s.path or ""))
            if not path:
                return False
        bad = page.doc.unencodable(side)
        if bad:
            self._say("error", f"{s.text.encoding.label} can't hold these characters: {''.join(bad[:20])}\n"
                               f"Nothing was saved.")
            return False
        try:
            page.doc.save(side, path)
        except OSError as e:
            self._say("error", f"Couldn't save {path or s.path}:\n{e.strerror or e}")
            return False
        page.rebuild()
        return True

    def find(self, again: bool = False):
        page = self.page()
        if not isinstance(page, FilePage):
            return False
        pane = page.focused_pane()
        text = getattr(self, "_find_text", "")
        if not again or not text:
            got = self._ask("find", text)
            if not got:
                return False
            text = self._find_text = got
        if pane.find(text):
            return True
        c = pane.textCursor()                       # wrap round to the top, as WinMerge does
        c.movePosition(c.MoveOperation.Start)
        pane.setTextCursor(c)
        if pane.find(text):
            return True
        self._say("info", f"Can't find “{text}”.")
        return False

    def go_to(self):
        page = self.page()
        if not isinstance(page, FilePage):
            return False
        pane = page.focused_pane()
        n = self._ask("goto", max(1, len(page.doc.side(pane.side).lines)))
        if not n:
            return False
        row = page.doc.row_of(pane.side, int(n) - 1)
        pane.put_cursor(row)
        page.scroll_to_row(row)
        pane.setFocus()
        return True

    def options(self):
        if not self._ask("options"):
            return False
        o = load_options()
        for page in self.pages():
            if isinstance(page, FilePage):
                page.recompare(o)
                page.restyle()
            elif isinstance(page, FolderPage):
                page.options = o
                page.method = settings.get("folder_method", "full") or "full"
        self._sync()
        return True

    def toggle_pane(self, key: str):
        on = self.acts[key].isChecked()
        settings.set(key, on)
        for page in self.pages():
            if isinstance(page, FilePage):
                (page.show_location if key == "location_pane" else page.show_diff_pane)(on)

    def toggle_show(self, key: str):
        on = self.acts["show_" + key].isChecked()
        for page in self.pages():
            if isinstance(page, FolderPage):
                page.set_show(key, on)
        shown = set(settings.get_list("show") or [k for k, _ in SHOW])
        (shown.add if on else shown.discard)(key)
        settings.set("show", sorted(shown))

    def generate_patch(self):
        page = self.page()
        if not isinstance(page, FilePage) or page.doc.binary:
            self._say("info", "Generate Patch works on a file compare of two text files.")
            return None
        page.apply_edits()
        base = page.doc.left.path or os.path.join(os.path.expanduser("~"), "compare")
        path = self._ask("patch_file", os.path.splitext(base)[0] + ".patch")
        if not path:
            return None
        text = page.doc.patch()
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        self._say("info", f"Patch written: {path}")
        return path

    # ================================================================ folder compare's menu
    def _folder_menu(self, page: FolderPage, pos):
        sel = page.selected()
        if not sel:
            return
        m = QMenu(self)
        it = sel[0]
        if not it.is_dir:
            m.addAction("Compare", lambda: page.open_item(it))
        m.addAction("Copy to Right", lambda: page.copy("right")).setEnabled(page.can_copy("right"))
        m.addAction("Copy to Left", lambda: page.copy("left")).setEnabled(page.can_copy("left"))
        m.addSeparator()
        m.addAction("Delete Left", lambda: page.delete("left")).setEnabled(any(i.left for i in sel))
        m.addAction("Delete Right", lambda: page.delete("right")).setEnabled(any(i.right for i in sel))
        m.addAction("Delete Both", lambda: page.delete("both"))
        m.addSeparator()
        for side in ("left", "right"):
            p = page.paths_of(it, side)
            a = m.addAction(f"Open {side.title()}", lambda p=p: self.open_externally(p))
            a.setEnabled(bool(p))
            a = m.addAction(f"Show {side.title()} in Folder", lambda p=p: self.show_in_folder(p))
            a.setEnabled(bool(p))
        if self.answers.get("menu"):
            self.last_menu = m
            return
        m.exec(page.view.viewport().mapToGlobal(pos))

    def open_externally(self, path: str | None):
        if not path:
            return False
        run = self.answers.get("launch")
        if run:
            return run(path)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        return QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def show_in_folder(self, path: str | None):
        """In PR7-E when it's installed (the family's file manager), else Explorer with the item selected."""
        if not path:
            return False
        run = self.answers.get("launch")
        if run:
            return run(os.path.dirname(path))
        if family.find("PR7-E"):
            return family.launch("PR7-E", [os.path.dirname(path)])
        if sys.platform == "win32":
            subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)])
            return True
        return self.open_externally(os.path.dirname(path))

    # ================================================================ Explorer menu
    def _explorer_menu_state(self):
        a = self.acts.get("explorer_menu")
        if a is None:
            return
        if sys.platform != "win32":
            a.setEnabled(False)
            return
        from . import shell
        a.setChecked(shell.menu_registered())

    def toggle_explorer_menu(self):
        from . import shell
        try:
            if self.acts["explorer_menu"].isChecked():
                shell.register(shell.exe_command())
            else:
                shell.unregister()
        except OSError as e:
            self._say("error", f"Couldn't change the Explorer menu: {e}")
        self._explorer_menu_state()

    # ================================================================ files changed elsewhere
    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            page = self.page()
            if isinstance(page, FilePage):
                QTimer.singleShot(0, lambda p=page: self._check_disk(p))

    def _check_disk(self, page: FilePage, asking: bool = True) -> bool:
        """WinMerge asks when a compared file changed on disk: reload it (a side with unsaved changes asks too)."""
        changed = [s for s in (page.doc.left, page.doc.right) if s.changed_on_disk()]
        if not changed:
            return False
        for s in changed:
            s.stamp = compare._stamp(s.path)       # ask once per change
        names = ", ".join(s.name for s in changed)
        if asking and not self._ask("reload", f"{names} changed outside PR7-WM. Load it again?" +
                                    ("\n\nYour unsaved changes would be lost." if any(s.modified for s in changed)
                                     else "")):
            return False
        page.doc.reload()
        page.rebuild()
        self._sync()
        return True

    # ================================================================ the command line and the Explorer menu
    def run_args(self, o: dict):
        """A parsed command line (app.parse): open what it names."""
        self.esc_closes = self.esc_closes or o.get("esc", False)
        paths = o.get("paths", [])
        kw = {k: o[k] for k in ("wl", "wr", "dl", "dr") if o.get(k)}
        if len(paths) >= 2:
            return self.compare_paths(paths[0], paths[1], o.get("recursive"), o.get("filter"), **kw)
        if len(paths) == 1:
            return self.open_dialog(paths[0])
        return None

    def collect(self, path: str):
        """One item from the Explorer menu (each selected item starts its own PR7-WM, which hands it over)."""
        if path and path not in self._collected:
            self._collected.append(path)
        self._collect_timer.start()

    def flush_collected(self):
        self._collect_timer.stop()
        paths, self._collected = self._collected, []
        if len(paths) >= 2:
            settings.set("pending_left", "")
            return self.compare_paths(paths[0], paths[1])
        if len(paths) == 1:
            left = settings.get("pending_left", "")
            if left and left != paths[0] and os.path.exists(left):
                settings.set("pending_left", "")
                return self.compare_paths(left, paths[0])
            settings.set("pending_left", paths[0])          # the left side, waiting for the right (Select Left)
            self.note = (f"LEFT SIDE: {os.path.basename(paths[0].rstrip(os.sep)) or paths[0]}\n\n"
                         f"Choose the right side with Compare in PR7-WM in Explorer")
            self.welcome.setText(self.note)
            self._sync()
            self.status.setText(f"Left side chosen: {paths[0]}")
        return None

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.esc_closes:
            self.close()
            return
        super().keyPressEvent(e)

    # ================================================================ drag and drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.dropped(paths)

    def dropped(self, paths: list[str]):
        if len(paths) >= 2:
            return self.compare_paths(paths[0], paths[1])
        if len(paths) == 1:
            return self.open_dialog(paths[0])
        return None

    # ================================================================ keys, menus and status
    def _sync(self):
        if not hasattr(self, "acts"):
            return
        page = self.page()
        f = isinstance(page, FilePage)
        fo = isinstance(page, FolderPage)
        a = self.acts
        mod = f and page.modified()
        for k in ("save",):
            a[k].setEnabled(bool(mod))
        for side in ("left", "right"):
            a[f"save_{side}"].setEnabled(bool(f and page.doc.side(side).modified))
            a[f"save_{side}_as"].setEnabled(bool(f and not page.doc.binary))
        a["close"].setEnabled(page is not None)
        a["undo"].setEnabled(bool(f and page.doc.undo_stack))
        a["redo"].setEnabled(bool(f and page.doc.redo_stack))
        for k in ("find", "find_next", "goto", "patch"):
            a[k].setEnabled(bool(f and not page.doc.binary))
        for k in ("next", "prev", "first", "last", "current"):
            a[k].setEnabled(bool(f and page.doc.counted) or fo)
        for to in ("right", "left"):
            a[f"copy_{to}"].setEnabled(bool((f or fo) and page.can_copy(to)))
            a[f"copy_all_{to}"].setEnabled(bool(f and page.can_copy(to)) or fo)
        for k in ("delete", "delete_left", "delete_right"):
            a[k].setEnabled(bool(fo and page.selected()))
        self.keys["save"].setEnabled(bool(mod))
        self.keys["prev"].setEnabled(a["prev"].isEnabled())
        self.keys["next"].setEnabled(a["next"].isEnabled())
        self.keys["copy_right"].setEnabled(a["copy_right"].isEnabled())
        self.keys["copy_left"].setEnabled(a["copy_left"].isEnabled())
        self.keys["refresh"].setEnabled(page is not None)
        self.status.setText(page.status() if page is not None else "Ready")
        title = page.title() if page is not None else ""
        self.setWindowTitle(f"{title} - Paragon PR7-WM" if title else "Paragon PR7-WM")

    def check_updates(self):
        from . import update_ui
        update_ui.check(self, manual=True)

    def about(self):
        self._say("info", f"Paragon PR7-WM {__version__}\nFile and folder compare that works the way WinMerge "
                          f"works.")
