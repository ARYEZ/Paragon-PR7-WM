"""Mock-up pictures of PR7-WM, drawn offscreen in the family theme (every file and line is made up):
QT_SCALE_FACTOR=2 python tools/mockup.py OUT_DIR

1_files.png     File compare: two texts side by side, changed lines tinted and the changed words marked, the location
                pane down the left showing every difference at once (OBSIDIAN)
2_folders.png   Folder compare: each file's result (identical, different, only on one side), dates, sizes (AURORA)
3_merge.png     Merging: a difference copied to the right (the right side unsaved), the Diff pane under the texts
                showing the current difference word by word (OBSIDIAN)
"""
import difflib
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel,  # noqa: E402
                               QLineEdit, QSplitter, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from pr7wm import theme, widgets  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/mockup")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
app.setFont(QFont("Inter", 10))

LEFT = '''"""Render settings for the ELSEWORLD master."""

WIDTH = 3840
HEIGHT = 2160
FPS = 23.976
CODEC = "prores_4444"


def output_name(take, version):
    return f"ELSEWORLD_t{take:02d}_v{version}.mov"


def bitrate(width, height):
    return width * height * 12


GRADE = "film_neutral"
LUT = "luts/elseworld_v3.cube"
'''.splitlines()

RIGHT = '''"""Render settings for the ELSEWORLD master."""

WIDTH = 3840
HEIGHT = 2160
FPS = 24
CODEC = "hevc_10bit"
AUDIO = "pcm_s24le"


def output_name(take, version):
    return f"ELSEWORLD_take{take:02d}_v{version:03d}.mov"


def bitrate(width, height):
    return width * height * 12


LUT = "luts/elseworld_v4.cube"
'''.splitlines()


def style():
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet())


def field(text):
    lab = QLabel(text.upper())
    lab.setProperty("role", "field")
    return lab


def dim(text):
    lab = QLabel(text)
    lab.setProperty("role", "dim")
    return lab


def toolbar(groups):
    bar = QWidget()
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(16, 10, 16, 6)
    lay.setSpacing(6)
    for i, group in enumerate(groups):
        if i:
            sep = QLabel()
            sep.setFixedSize(1, 40)
            sep.setStyleSheet(f"background: {theme.PANEL_EDGE};")
            lay.addSpacing(8)
            lay.addWidget(sep)
            lay.addSpacing(8)
        for icon, label in group:
            k = widgets.KeyButton(icon, label)
            k.setFixedSize(QSize(100, 62))
            lay.addWidget(k)
    lay.addStretch(1)
    return bar


# ----------------------------------------------------------------- the aligned diff
def aligned(a, b):
    """Rows of (left line no, left text, right line no, right text, kind) with blank fillers, like WinMerge."""
    rows = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                rows.append((i1 + k + 1, a[i1 + k], j1 + k + 1, b[j1 + k], "same"))
        else:
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                li = i1 + k if i1 + k < i2 else None
                rj = j1 + k if j1 + k < j2 else None
                kind = "changed" if li is not None and rj is not None else ("left" if li is not None else "right")
                rows.append((li + 1 if li is not None else None, a[li] if li is not None else "",
                             rj + 1 if rj is not None else None, b[rj] if rj is not None else "", kind))
    return rows


def word_spans(x, y):
    """Character ranges that differ inside a changed line pair (left, right)."""
    sm = difflib.SequenceMatcher(None, x, y, autojunk=False)
    ls, rs = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            if i2 > i1:
                ls.append((i1, i2))
            if j2 > j1:
                rs.append((j1, j2))
    return ls, rs


CHANGED = "#D6457E"       # family pink: a changed line
ONE_SIDE = "#F07A2A"      # orange: a line only on one side
FILLER = "#3A3438"        # onyx: the blank opposite a one-sided line


class TextPane(QWidget):
    def __init__(self, rows, side, current=None, unsaved=False):
        super().__init__()
        self.rows, self.side, self.current, self.unsaved = rows, side, current, unsaved
        self.setMinimumWidth(400)
        self.font = QFont("DejaVu Sans Mono")
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.font.setPixelSize(13)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(theme.WIDGET))
        p.setFont(self.font)
        fm = QFontMetricsF(self.font)
        lh = fm.height() + 4
        gutter = fm.horizontalAdvance("0000") + 14
        p.fillRect(QRectF(0, 0, gutter, r.height()), QColor(theme.DOCK_TOP))
        for i, (ln, lt, rn, rt, kind) in enumerate(self.rows):
            y = 6 + i * lh
            num, text = (ln, lt) if self.side == "left" else (rn, rt)
            row = QRectF(gutter, y, r.width() - gutter, lh)
            if kind != "same":
                if num is None:
                    c = QColor(FILLER)
                    c.setAlphaF(.55)
                else:
                    c = QColor(CHANGED if kind == "changed" else ONE_SIDE)
                    c.setAlphaF(.22 if i not in (self.current or ()) else .36)
                p.fillRect(row, c)
            if kind == "changed" and num is not None:
                ls, rs = word_spans(lt, rt)
                for a, b in (ls if self.side == "left" else rs):
                    x1 = gutter + 8 + fm.horizontalAdvance(text[:a])
                    x2 = gutter + 8 + fm.horizontalAdvance(text[:b])
                    c = QColor(CHANGED)
                    c.setAlphaF(.55)
                    p.fillRect(QRectF(x1, y + 1, max(3, x2 - x1), lh - 2), c)
            p.setPen(QColor(theme.TEXT_DIM))
            if num is not None:
                p.drawText(QRectF(0, y, gutter - 6, lh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           str(num))
            p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(gutter + 8, y, r.width(), lh), Qt.AlignmentFlag.AlignVCenter, text)
        if self.current:
            ys = 6 + min(self.current) * lh
            ye = 6 + (max(self.current) + 1) * lh
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            p.drawLine(int(gutter), int(ys), r.width(), int(ys))
            p.drawLine(int(gutter), int(ye), r.width(), int(ye))


class Location(QWidget):
    """WinMerge's location pane: the whole file in miniature, each difference a mark, the view a frame."""

    def __init__(self, rows):
        super().__init__()
        self.rows = rows
        self.setFixedWidth(34)

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(4, 6, -4, -6)
        p.fillRect(self.rect(), QColor(theme.DOCK_TOP))
        n = max(1, len(self.rows))
        h = r.height() / n
        for half, side in ((0, "left"), (1, "right")):
            x = r.left() + half * (r.width() / 2 + 1)
            for i, (ln, _, rn, _, kind) in enumerate(self.rows):
                if kind == "same":
                    continue
                num = ln if side == "left" else rn
                c = QColor(FILLER if num is None else CHANGED if kind == "changed" else ONE_SIDE)
                p.fillRect(QRectF(x, r.top() + i * h, r.width() / 2 - 1, max(2, h)), c)
        p.setPen(QPen(QColor(theme.TEXT_DIM), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(r.left() - 1, r.top(), r.width() + 2, r.height() * .75))


def file_header(name, path, unsaved=False):
    w = QFrame()
    w.setObjectName("fh")
    w.setStyleSheet(f"QFrame#fh {{ background: {theme.DOCK_TOP}; border-bottom: 1px solid {theme.PANEL_EDGE}; }}")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(10, 5, 10, 5)
    t = QLabel(name + ("  *" if unsaved else ""))
    t.setStyleSheet("font-weight: 600;" + (f" color: {theme.LED_ORANGE};" if unsaved else ""))
    lay.addWidget(t)
    lay.addWidget(dim(path), 1)
    lay.addWidget(dim("UTF-8  ·  CRLF"))
    return w


def file_compare(rows, current=None, unsaved=False, diff_pane=False):
    split = QWidget()
    sl = QHBoxLayout(split)
    sl.setContentsMargins(16, 0, 16, 0)
    sl.setSpacing(6)
    sl.addWidget(Location(rows))
    for side, name, path in (("left", "render_settings.py", r"D:\Studio\ELSEWORLD\tools\render_settings.py"),
                             ("right", "render_settings.py", r"\\NAS\Backup\ELSEWORLD\tools\render_settings.py")):
        col = QWidget()
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(file_header(name, path, unsaved and side == "right"))
        cl.addWidget(TextPane(rows, side, current), 1)
        sl.addWidget(col, 1)
    if not diff_pane:
        return split
    s = QSplitter(Qt.Orientation.Vertical)
    s.addWidget(split)
    pane = QWidget()
    pl = QVBoxLayout(pane)
    pl.setContentsMargins(16, 6, 16, 0)
    pl.addWidget(field("Diff pane  ·  difference 3 of 6"))
    i = sorted(current)[0]
    two = [rows[i]]
    row = QHBoxLayout()
    for side in ("left", "right"):
        row.addWidget(TextPane(two, side), 1)
    pl.addLayout(row)
    s.addWidget(pane)
    s.setSizes([560, 110])
    return s


def status(text, right=""):
    f = QFrame()
    f.setStyleSheet(f"QFrame {{ background: {theme.TAB_FRAME}; border-top: 1px solid {theme.PANEL_EDGE}; }}")
    lay = QHBoxLayout(f)
    lay.setContentsMargins(16, 6, 16, 6)
    lay.addWidget(dim(text))
    lay.addStretch(1)
    key = QLabel(f"<span style='color:{CHANGED}'>■</span> changed     <span style='color:{ONE_SIDE}'>■</span> "
                 f"only on one side" + (f"          {right}" if right else ""))
    key.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
    lay.addWidget(key)
    return f


def tabs(names, current):
    t = QTabBar()
    t.setExpanding(False)
    t.setDrawBase(False)
    for n in names:
        t.addTab(n)
    t.setCurrentIndex(current)
    t.setTabsClosable(True)
    h = QWidget()
    hl = QHBoxLayout(h)
    hl.setContentsMargins(16, 0, 16, 0)
    hl.addWidget(t)
    hl.addStretch(1)
    return h


def window(body, status_bar, current_tab=0):
    w = QWidget()
    w.setObjectName("win")
    w.setStyleSheet(f"QWidget#win {{ background: {theme.BACKGROUND}; }}")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(widgets.Header("COMPARE"))
    lay.addWidget(toolbar([[("open", "Open"), ("file", "Save"), ("folders", "Folders")],
                           [("diff_prev", "Previous"), ("diff_next", "Next"), ("copy_right", "Copy Right"),
                            ("copy_left", "Copy Left")],
                           [("refresh", "Refresh"), ("gear", "Options")]]))
    lay.addWidget(tabs(["render_settings.py", "ELSEWORLD  ·  folders"], current_tab))
    lay.addWidget(body, 1)
    lay.addWidget(status_bar)
    w.resize(1320, 820)
    return w


def folder_compare():
    t = QTreeWidget()
    t.setHeaderLabels(["NAME", "FOLDER", "COMPARISON RESULT", "LEFT DATE", "RIGHT DATE", "SIZE"])
    t.setRootIsDecorated(False)
    t.setIndentation(0)
    t.setIconSize(QSize(18, 18))
    h = t.header()
    h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    rows = [("render_settings.py", "tools", "Text files are different  ·  6 differences", "2026-11-25 09:30",
             "2026-11-22 23:58", "1.1 KB", CHANGED),
            ("export.py", "tools", "Text files are identical", "2026-11-20 18:02", "2026-11-20 18:02", "4.0 KB", None),
            ("ELSEWORLD_edit_v12.drp", "Projects", "Binary files are different", "2026-11-25 09:30",
             "2026-11-22 23:58", "48.1 MB", CHANGED),
            ("credits.txt", "Projects", "Text files are different  ·  2 differences", "2026-11-25 08:40",
             "2026-11-25 08:52", "4 KB", CHANGED),
            ("A001_C0006.mov", "Footage", "Left only: D:\\Studio\\ELSEWORLD\\Footage", "2026-11-24 18:02", "",
             "3.42 GB", ONE_SIDE),
            ("Last Light (stems).zip", "Music", "Right only: \\\\NAS\\Backup\\ELSEWORLD\\Music", "",
             "2026-11-20 12:01", "612 MB", ONE_SIDE),
            ("notes_for_mix.md", "", "Text files are identical", "2026-11-19 22:41", "2026-11-19 22:41", "2 KB", None),
            ("thumbs", "Footage", "Folders are different", "", "", "", CHANGED)]
    for name, folder, result, ld, rd, size, colour in rows:
        it = QTreeWidgetItem([name, folder, result, ld, rd, size])
        it.setIcon(0, widgets.file_icon("folder" if name == "thumbs" else widgets.kind_of(name), 18))
        if colour:
            it.setForeground(2, QColor(colour))
        else:
            it.setForeground(2, QColor(theme.TEXT_DIM))
        t.addTopLevelItem(it)
    t.setCurrentItem(t.topLevelItem(0))
    box = QWidget()
    bl = QVBoxLayout(box)
    bl.setContentsMargins(16, 6, 16, 0)
    paths = QHBoxLayout()
    paths.addWidget(field("Left"))
    paths.addWidget(QLineEdit(r"D:\Studio\ELSEWORLD"), 1)
    paths.addWidget(field("Right"))
    paths.addWidget(QLineEdit(r"\\NAS\Backup\ELSEWORLD"), 1)
    bl.addLayout(paths)
    opts = QHBoxLayout()
    opts.addWidget(field("Filter"))
    f = QLineEdit("*.*  ·  not .git, __pycache__")
    f.setFixedWidth(260)
    opts.addWidget(f)
    for text, on in (("Include subfolders", True), ("Show identical", True), ("Show different", True),
                     ("Show left only", True), ("Show right only", True)):
        c = QCheckBox(text)
        c.setChecked(on)
        opts.addWidget(c)
    opts.addStretch(1)
    bl.addLayout(opts)
    bl.addWidget(t, 1)
    return box


def shoot(widget, name):
    widget.show()
    app.processEvents()
    widget.grab().save(str(out / name))
    widget.close()


rows = aligned(LEFT, RIGHT)
diffs = [i for i, r in enumerate(rows) if r[4] != "same"]
theme.set_finish("obsidian")
style()
shoot(window(file_compare(rows, current={diffs[0]}), status("Difference 1 of 6  ·  line 6 of 19",
                                                               "Python  ·  ignore whitespace: off")), "1_files.png")
theme.set_finish("aurora")
style()
shoot(window(folder_compare(), status("8 items  ·  4 different  ·  1 left only  ·  1 right only  ·  2 identical"),
             current_tab=1), "2_folders.png")
theme.set_finish("obsidian")
style()
merged = list(rows)
i = next(k for k in diffs if 'f"ELSEWORLD' in rows[k][1])
cur = {i}
shoot(window(file_compare(merged, current=cur, unsaved=True, diff_pane=True),
             status("Difference 3 of 6  ·  copied to the right (Ctrl+Z undoes)", "right side unsaved")),
      "3_merge.png")
print("ok", out)
