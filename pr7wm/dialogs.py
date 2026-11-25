"""PR7-WM's dialogs: Select Files or Folders (WinMerge's Open) and Options."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QRadioButton, QTabWidget, QVBoxLayout, QWidget)

from . import diff, folders, settings

RECENT = 12


def _field(text):
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


class OpenDialog(QDialog):
    """Select Files or Folders: two paths (files or folders), the filter, Include subfolders, read-only sides."""

    def __init__(self, parent=None, left: str = "", right: str = "", folders_first: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Select Files or Folders")
        self.setMinimumWidth(720)
        self.folders_first = folders_first
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.edits: dict[str, QComboBox] = {}
        self.read_only: dict[str, QCheckBox] = {}
        for side, value in (("left", left), ("right", right)):
            row = QHBoxLayout()
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems([p for p in settings.get_list(f"recent_{side}") if p])
            combo.setCurrentText(value)
            combo.lineEdit().setPlaceholderText("A file or a folder")
            row.addWidget(combo, 1)
            for kind in ("file", "folder"):
                b = QPushButton(kind.upper() + "…")
                b.clicked.connect(lambda _=False, s=side, k=kind: self.browse(s, k))
                row.addWidget(b)
            ro = QCheckBox("Read-only")
            row.addWidget(ro)
            form.addRow(_field(side), row)
            self.edits[side], self.read_only[side] = combo, ro
        self.filter = QLineEdit(settings.get("folder_filter", folders.DEFAULT_FILTER) or folders.DEFAULT_FILTER)
        self.filter.setToolTip("Masks separated by ;  ·  !mask leaves files out  ·  !name\\ leaves a folder out")
        form.addRow(_field("Filter"), self.filter)
        self.recursive = QCheckBox("Include subfolders")
        self.recursive.setChecked(settings.get_bool("recursive", True))
        form.addRow("", self.recursive)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.compare_button = buttons.addButton("COMPARE", QDialogButtonBox.ButtonRole.AcceptRole)
        self.compare_button.setDefault(True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def browse(self, side: str, kind: str):
        start = self.edits[side].currentText() or self.edits["left"].currentText()
        start = start if os.path.isdir(start) else os.path.dirname(start)
        if kind == "folder":
            got = QFileDialog.getExistingDirectory(self, f"Choose the {side} folder", start)
        else:
            got, _ = QFileDialog.getOpenFileName(self, f"Choose the {side} file", start)
        if got:
            self.edits[side].setCurrentText(os.path.normpath(got))

    def _accept(self):
        if self.edits["left"].currentText().strip() and self.edits["right"].currentText().strip():
            self.remember()
            self.accept()

    def remember(self):
        for side, combo in self.edits.items():
            p = combo.currentText().strip()
            recent = [p] + [x for x in settings.get_list(f"recent_{side}") if x != p]
            settings.set(f"recent_{side}", recent[:RECENT])
        settings.set("recursive", self.recursive.isChecked())
        settings.set("folder_filter", self.filter.text())

    def values(self) -> dict:
        return {"left": self.edits["left"].currentText().strip(), "right": self.edits["right"].currentText().strip(),
                "recursive": self.recursive.isChecked(), "filter": self.filter.text(),
                "wl": self.read_only["left"].isChecked(), "wr": self.read_only["right"].isChecked()}


def load_options() -> diff.Options:
    import json
    try:
        return diff.Options.from_dict(json.loads(settings.get("options", "{}") or "{}"))
    except ValueError:
        return diff.Options()


def save_options(o: diff.Options) -> None:
    settings.set("options", o.to_dict())


class OptionsDialog(QDialog):
    """Edit > Options: Compare (the diff options), Folder compare, Text."""

    WS = [("compare", "Compare"), ("changes", "Ignore changes"), ("all", "Ignore all")]
    INLINE = [("word", "Word level"), ("char", "Character level"), ("", "Off")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Options")
        self.setMinimumWidth(520)
        o = load_options()
        tabs = QTabWidget()
        page = QWidget()
        pl = QVBoxLayout(page)
        box = QGroupBox("WHITESPACE")
        bl = QHBoxLayout(box)
        self.ws_group = QButtonGroup(self)          # radios that are siblings need their own group (else one set)
        self.ws: dict[str, QRadioButton] = {}
        for key, text in self.WS:
            r = QRadioButton(text)
            r.setChecked(o.whitespace == key)
            self.ws_group.addButton(r)
            bl.addWidget(r)
            self.ws[key] = r
        bl.addStretch(1)
        pl.addWidget(box)
        self.blank = QCheckBox("Ignore blank lines")
        self.blank.setChecked(o.blank_lines)
        self.case = QCheckBox("Ignore case")
        self.case.setChecked(o.case)
        self.eol = QCheckBox("Ignore carriage return differences (Windows / Unix / Mac line endings)")
        self.eol.setChecked(o.eol)
        for w in (self.blank, self.case, self.eol):
            pl.addWidget(w)
        row = QHBoxLayout()
        row.addWidget(_field("Highlight inside changed lines"))
        self.inline = QComboBox()
        for key, text in self.INLINE:
            self.inline.addItem(text, key)
        self.inline.setCurrentIndex(max(0, self.inline.findData(o.inline)))
        row.addWidget(self.inline)
        row.addStretch(1)
        pl.addLayout(row)
        pl.addStretch(1)
        tabs.addTab(page, "COMPARE")

        page = QWidget()
        fl = QFormLayout(page)
        self.method = QComboBox()
        for key, text in folders.METHODS.items():
            self.method.addItem(text, key)
        self.method.setCurrentIndex(max(0, self.method.findData(settings.get("folder_method", "full") or "full")))
        fl.addRow(_field("Compare method"), self.method)
        self.filter = QLineEdit(settings.get("folder_filter", folders.DEFAULT_FILTER) or folders.DEFAULT_FILTER)
        fl.addRow(_field("Default filter"), self.filter)
        self.recursive = QCheckBox("Include subfolders")
        self.recursive.setChecked(settings.get_bool("recursive", True))
        fl.addRow("", self.recursive)
        tabs.addTab(page, "FOLDER COMPARE")

        page = QWidget()
        tl = QFormLayout(page)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(6, 32)
        self.font_size.setSingleStep(0.5)
        self.font_size.setValue(settings.get_float("font_size", 10.0))
        self.font_size.setSuffix(" pt")
        tl.addRow(_field("Text size"), self.font_size)
        tabs.addTab(page, "TEXT")

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def options(self) -> diff.Options:
        ws = next((k for k, r in self.ws.items() if r.isChecked()), "compare")
        return diff.Options(whitespace=ws, blank_lines=self.blank.isChecked(), case=self.case.isChecked(),
                            eol=self.eol.isChecked(), inline=self.inline.currentData() or "")

    def save(self) -> None:
        save_options(self.options())
        settings.set("folder_method", self.method.currentData())
        settings.set("folder_filter", self.filter.text())
        settings.set("recursive", self.recursive.isChecked())
        settings.set("font_size", self.font_size.value())
