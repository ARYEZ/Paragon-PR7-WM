"""The file compare's panes: the two texts (editable, lined up row by row), the location pane down the left and the
diff pane under the texts. FilePage puts them together around one compare.FileCompare.

A text pane is a QPlainTextEdit holding one block per row: a filler row (the blank opposite a line that's only on the
other side) is a block marked with user state FILLER. After an edit, `real_lines` reads the side's lines back (a
filler that got text is a real line now), the compare is run again and both panes are rebuilt, the cursor kept on its
line. Row tints are painted under the text; the marks inside changed lines come from a syntax highlighter.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QKeySequence, QPainter, QPen, QSyntaxHighlighter,
                           QTextCharFormat, QTextCursor, QTextOption)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget)

from . import compare, diff, settings, theme

FILLER = 1
EDIT_DELAY_MS = 350          # an edit is compared again after this pause in typing (WinMerge rescans on a timer too)


def colours() -> dict[str, QColor]:
    """The diff colours in the current finish: the family's pink, orange and onyx / pearl only."""
    dark = theme.FINISH == "obsidian"

    def c(hex_colour, alpha):
        q = QColor(hex_colour)
        q.setAlphaF(alpha)
        return q
    return {"changed": c("#D6457E", .22 if dark else .20), "changed_current": c("#D6457E", .36 if dark else .32),
            "one_side": c("#F07A2A", .22 if dark else .24), "one_side_current": c("#F07A2A", .36 if dark else .38),
            "filler": c("#3A3438", .55) if dark else c("#B9ADB3", .45),
            "word": c("#D6457E", .55 if dark else .42), "ignored": c("#8A8A92", .10),
            "pink": QColor("#D6457E"), "orange": QColor("#F07A2A"),
            "filler_solid": QColor("#3A3438") if dark else QColor("#B9ADB3")}


def mono_font() -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFamilies(["Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Liberation Mono", "monospace"])
    f.setPointSizeF(max(6.0, settings.get_float("font_size", 10.0)))
    return f


class _Marks(QSyntaxHighlighter):
    """The changed words inside a changed line."""

    def __init__(self, pane: "TextPane"):
        super().__init__(pane.document())
        self.pane = pane

    def highlightBlock(self, text):
        spans = self.pane.spans(self.currentBlock().blockNumber())
        if not spans:
            return
        fmt = QTextCharFormat()
        fmt.setBackground(colours()["word"])
        for s, e in spans:
            s, e = min(s, len(text)), min(e, len(text))
            if e > s:
                self.setFormat(s, e - s, fmt)


class _Gutter(QWidget):
    def __init__(self, pane: "TextPane"):
        super().__init__(pane)
        self.pane = pane

    def sizeHint(self):
        return QSize(self.pane.gutter_width(), 0)

    def paintEvent(self, e):
        self.pane.paint_gutter(self, e)


class TextPane(QPlainTextEdit):
    """One side's text, one block per row."""

    edited = Signal()
    focused = Signal()

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.rows: list[tuple[int | None, str]] = []    # (line index or None for a filler, kind) per row
        self.current: tuple[int, int] | None = None     # the current difference's rows [a, b)
        self.span_source = None                          # function(row) -> spans
        self.loading = False
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setUndoRedoEnabled(False)                   # Undo is the compare's own (both sides, merges included)
        self.setFont(mono_font())
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.gutter = _Gutter(self)
        self.marks = _Marks(self)
        self.textChanged.connect(self._changed)
        self.blockCountChanged.connect(lambda _: self._fit_gutter())
        self.updateRequest.connect(self._scroll_gutter)
        self.restyle()

    def restyle(self):
        self.setStyleSheet(f"QPlainTextEdit {{ background: {theme.WIDGET}; color: {theme.TEXT}; border: none; "
                           f"border-radius: 0; padding: 0; selection-background-color: {theme.ACCENT_DIM}; "
                           f"selection-color: #FFFFFF; }}")
        self.setFont(mono_font())
        self._fit_gutter()
        self.marks.rehighlight()
        self.viewport().update()

    # ----------------------------------------------------------------- content
    def load(self, rows: list[tuple[int | None, str, str]]):
        """rows: (line index or None, text, kind) per row."""
        self.loading = True
        self.rows = [(n, k) for n, _, k in rows]
        self.setPlainText("\n".join(t for _, t, _ in rows))
        b = self.document().firstBlock()
        if not rows:
            b.setUserState(FILLER)                       # an empty side: the one block isn't a line
        for n, _, _ in rows:
            if not b.isValid():
                break
            b.setUserState(FILLER if n is None else 0)
            b = b.next()
        self.loading = False
        self._fit_gutter()
        self.marks.rehighlight()

    def real_lines(self) -> list[str]:
        out = []
        b = self.document().firstBlock()
        while b.isValid():
            if not (b.userState() == FILLER and b.text() == ""):
                out.append(b.text())
            b = b.next()
        return out

    def spans(self, row: int):
        return self.span_source(row) if self.span_source else None

    def _changed(self):
        if not self.loading and not self.isReadOnly():
            self.edited.emit()

    def cursor_place(self) -> tuple[int, int | None, int]:
        """(row, line index or None, column) of the text cursor."""
        c = self.textCursor()
        row = c.blockNumber()
        line = self.rows[row][0] if 0 <= row < len(self.rows) else None
        return row, line, c.positionInBlock()

    def put_cursor(self, row: int, col: int = 0):
        b = self.document().findBlockByNumber(max(0, min(row, self.document().blockCount() - 1)))
        c = QTextCursor(b)
        c.setPosition(b.position() + min(col, max(0, b.length() - 1)))
        self.setTextCursor(c)

    def first_visible_row(self) -> int:
        return self.firstVisibleBlock().blockNumber()

    def visible_rows(self) -> int:
        lh = QFontMetricsF(self.font()).lineSpacing() or 1
        return max(1, int(self.viewport().height() / lh))

    # ----------------------------------------------------------------- painting
    def paintEvent(self, e):
        p = QPainter(self.viewport())
        col = colours()
        block = self.firstVisibleBlock()
        offset = self.contentOffset()
        w = self.viewport().width()
        bottom = e.rect().bottom()
        cur = self.current
        while block.isValid():
            geo = self.blockBoundingGeometry(block).translated(offset)
            if geo.top() > bottom:
                break
            row = block.blockNumber()
            if row < len(self.rows):
                n, kind = self.rows[row]
                inside = cur is not None and cur[0] <= row < cur[1]
                fill = None
                if kind == "ignored":
                    fill = col["ignored"]
                elif kind != "same":
                    if n is None:
                        fill = col["filler"]
                    elif kind == "changed":
                        fill = col["changed_current" if inside else "changed"]
                    else:
                        fill = col["one_side_current" if inside else "one_side"]
                if fill is not None:
                    p.fillRect(QRectF(0, geo.top(), w, geo.height()), fill)
            block = block.next()
        if cur is not None and cur[1] > cur[0]:
            p.setPen(QPen(QColor(theme.ACCENT), 1.5))
            doc = self.document()
            first, last = doc.findBlockByNumber(cur[0]), doc.findBlockByNumber(cur[1] - 1)
            if first.isValid():
                p.drawLine(0, int(self.blockBoundingGeometry(first).translated(offset).top()), w,
                           int(self.blockBoundingGeometry(first).translated(offset).top()))
            if last.isValid():
                y = int(self.blockBoundingGeometry(last).translated(offset).bottom())
                p.drawLine(0, y, w, y)
        p.end()
        super().paintEvent(e)

    def gutter_width(self) -> int:
        digits = len(str(max(1, sum(1 for n, _ in self.rows if n is not None))))
        return int(QFontMetricsF(self.font()).horizontalAdvance("9" * max(3, digits)) + 16)

    def _fit_gutter(self):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _scroll_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, widget, e):
        p = QPainter(widget)
        p.fillRect(e.rect(), QColor(theme.DOCK_TOP))
        p.setFont(self.font())
        p.setPen(QColor(theme.TEXT_DIM))
        block = self.firstVisibleBlock()
        offset = self.contentOffset()
        w = widget.width()
        while block.isValid():
            geo = self.blockBoundingGeometry(block).translated(offset)
            if geo.top() > e.rect().bottom():
                break
            row = block.blockNumber()
            if row < len(self.rows) and self.rows[row][0] is not None:
                p.drawText(QRectF(0, geo.top(), w - 8, geo.height()),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(self.rows[row][0] + 1))
            block = block.next()

    # ----------------------------------------------------------------- keys
    def event(self, e):
        # Undo / Redo are the window's (the compare's own), not the text box's
        if e.type() == e.Type.ShortcutOverride and (e.matches(QKeySequence.StandardKey.Undo) or
                                                    e.matches(QKeySequence.StandardKey.Redo)):
            e.ignore()
            return False
        return super().event(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.focused.emit()


class Location(QWidget):
    """WinMerge's location pane: the whole compare in miniature (left half, right half), each difference a mark, the
    part on screen a frame. A click or a drag scrolls there."""

    clicked = Signal(int)          # a row

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[tuple[int | None, int | None, str]] = []
        self.view = (0, 0)
        self.setFixedWidth(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_rows(self, rows):
        self.rows = rows
        self.update()

    def set_view(self, first: int, count: int):
        self.view = (first, count)
        self.update()

    def _area(self) -> QRectF:
        return QRectF(self.rect()).adjusted(4, 4, -4, -4)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.DOCK_TOP))
        r = self._area()
        n = max(1, len(self.rows))
        h = r.height() / n
        col = colours()
        half = (r.width() - 2) / 2
        for i, (ln, rn, kind) in enumerate(self.rows):
            if kind in ("same", "ignored"):
                continue
            for k, num in enumerate((ln, rn)):
                c = col["filler_solid"] if num is None else col["pink"] if kind == "changed" else col["orange"]
                p.fillRect(QRectF(r.left() + k * (half + 2), r.top() + i * h, half, max(2.0, h)), c)
        first, count = self.view
        if self.rows:
            p.setPen(QPen(QColor(theme.TEXT_DIM), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(r.left() - 2, r.top() + first * h, r.width() + 3, max(4.0, min(count, n) * h)))

    def _row_at(self, y: float) -> int:
        r = self._area()
        return int(max(0.0, min(1.0, (y - r.top()) / max(1.0, r.height()))) * max(0, len(self.rows) - 1))

    def mousePressEvent(self, e):
        self.clicked.emit(self._row_at(e.position().y()))

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.clicked.emit(self._row_at(e.position().y()))


class ElidedLabel(QLabel):
    """A path that's shortened in the middle with "…" when it doesn't fit (as Windows shows long paths)."""

    def __init__(self, text: str = ""):
        super().__init__()
        self.full = text
        self.setMinimumWidth(10)

    def setText(self, text: str):  # noqa: N802 - Qt's name
        self.full = text
        self._fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        super().setText(self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideMiddle, max(10, self.width())))


class SideHeader(QFrame):
    """A side's name, path (or WinMerge's /dl /dr description), encoding and line endings; orange * when unsaved."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidehead")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        self.name = QLabel()
        self.path = ElidedLabel()
        self.path.setProperty("role", "dim")
        self.info = QLabel()
        self.info.setProperty("role", "dim")
        lay.addWidget(self.name)
        lay.addWidget(self.path, 1)
        lay.addWidget(self.info)
        self.restyle()

    def restyle(self):
        self.setStyleSheet(f"QFrame#sidehead {{ background: {theme.DOCK_TOP}; "
                           f"border-bottom: 1px solid {theme.PANEL_EDGE}; }}")

    def show_side(self, s: compare.Side):
        self.name.setText(s.name + ("  *" if s.modified else "") + ("  (READ-ONLY)" if s.read_only else ""))
        self.name.setStyleSheet("font-weight: 600;" + (f" color: {theme.LED_ORANGE};" if s.modified else ""))
        shown = s.title if s.description or s.path else ""
        self.path.setText(shown)
        self.path.setToolTip(s.path or "")
        t = s.text
        self.info.setText("" if t.binary else f"{t.encoding.label}  ·  {t.eol_label()}")


class FilePage(QWidget):
    """One file compare tab."""

    changed = Signal()          # anything the window shows changed (title, status, keys)

    kind = "file"

    def __init__(self, doc: compare.FileCompare, parent=None, sync: bool = False):
        super().__init__(parent)
        self.doc = doc
        self.cur: int = -1                  # the current difference (block index), -1 none
        self.sync = sync
        self._scrolling = False
        self._pending: set[str] = set()
        self._span_cache: dict[int, tuple] = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(EDIT_DELAY_MS)
        self.timer.timeout.connect(self.apply_edits)

        self.location = Location()
        self.location.clicked.connect(self.scroll_to_row)
        self.heads = {"left": SideHeader(), "right": SideHeader()}
        self.panes = {"left": TextPane("left"), "right": TextPane("right")}
        self.detail = {"left": TextPane("left"), "right": TextPane("right")}
        for side in ("left", "right"):
            pane = self.panes[side]
            pane.span_source = lambda row, s=side: self.spans(s, row)
            pane.edited.connect(lambda s=side: self.edited(s))
            pane.cursorPositionChanged.connect(lambda s=side: self._cursor_moved(s))
            pane.verticalScrollBar().valueChanged.connect(lambda v, s=side: self._scrolled(s, v, True))
            pane.horizontalScrollBar().valueChanged.connect(lambda v, s=side: self._scrolled(s, v, False))
            d = self.detail[side]
            d.setReadOnly(True)
            d.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            d.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
            d.span_source = lambda row, s=side: self._detail_spans(s, row)

        texts = QWidget()
        tl = QHBoxLayout(texts)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        tl.addWidget(self.location)
        for side in ("left", "right"):
            col = QWidget()
            cl = QVBoxLayout(col)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            cl.addWidget(self.heads[side])
            cl.addWidget(self.panes[side], 1)
            tl.addWidget(col, 1)
        self.diff_box = QWidget()
        dl = QVBoxLayout(self.diff_box)
        dl.setContentsMargins(0, 6, 0, 0)
        dl.setSpacing(4)
        self.diff_title = QLabel("DIFF PANE")
        self.diff_title.setProperty("role", "field")
        dl.addWidget(self.diff_title)
        dr = QHBoxLayout()
        dr.setSpacing(6)
        dr.addSpacing(36)
        dr.addWidget(self.detail["left"], 1)
        dr.addWidget(self.detail["right"], 1)
        dl.addLayout(dr, 1)
        self.split = QSplitter(Qt.Orientation.Vertical)
        self.split.addWidget(texts)
        self.split.addWidget(self.diff_box)
        self.split.setStretchFactor(0, 5)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([600, 120])
        self.binary_note = QLabel()
        self.binary_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.binary_note.setProperty("role", "heading")
        self.binary_note.hide()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.split, 1)
        lay.addWidget(self.binary_note, 1)
        self.show_location(settings.get_bool("location_pane", True))
        self.show_diff_pane(settings.get_bool("diff_pane", False))
        self.rebuild()
        if self.doc.counted:
            self.go(self.doc.counted[0], focus=False)

    # ----------------------------------------------------------------- what's shown
    def title(self) -> str:
        l, r = self.doc.left, self.doc.right
        name = l.name if l.name == r.name else f"{l.name}  ·  {r.name}"
        return name + (" *" if l.modified or r.modified else "")

    def modified(self) -> bool:
        return self.doc.left.modified or self.doc.right.modified

    def view_rows(self, side: str):
        lines = self.doc.side(side).lines
        out = []
        for r in self.doc.rows:
            n = r.l if side == "left" else r.r
            kind = r.kind
            if r.block >= 0 and self.doc.blocks[r.block].ignored:
                kind = "ignored"
            out.append((n, lines[n] if n is not None else "", kind))
        return out

    def rebuild(self, keep: bool = True):
        """Fill both panes from the compare (after a compare, a merge, an undo, an edit)."""
        self._span_cache.clear()
        binary = self.doc.binary
        self.split.setVisible(not binary)
        self.binary_note.setVisible(binary)
        if binary:
            same = self.doc.identical()
            self.binary_note.setText("BINARY FILES ARE IDENTICAL" if same else "BINARY FILES ARE DIFFERENT")
            for side in ("left", "right"):
                self.heads[side].show_side(self.doc.side(side))
            self.changed.emit()
            return
        places = {}
        if keep:
            for side, pane in self.panes.items():
                places[side] = (pane.cursor_place(), pane.verticalScrollBar().value(),
                                pane.horizontalScrollBar().value())
        for side in ("left", "right"):
            pane = self.panes[side]
            pane.load(self.view_rows(side))
            pane.setReadOnly(self.doc.side(side).read_only)
            self.heads[side].show_side(self.doc.side(side))
        self.location.set_rows([(r.l, r.r, "ignored" if r.block >= 0 and self.doc.blocks[r.block].ignored else
                                 r.kind) for r in self.doc.rows])
        if self.cur >= len(self.doc.blocks):
            self.cur = -1
        self._mark_current()
        for side, ((row, line, col), v, h) in places.items():
            pane = self.panes[side]
            self._scrolling = True
            if line is not None:
                pane.put_cursor(self.doc.row_of(side, line), col)
            else:
                pane.put_cursor(min(row, max(0, len(self.doc.rows) - 1)), 0)
            pane.verticalScrollBar().setValue(v)
            pane.horizontalScrollBar().setValue(h)
            self._scrolling = False
        self._view_changed()
        self.changed.emit()

    def restyle(self):
        for w in list(self.panes.values()) + list(self.detail.values()):
            w.restyle()
        for h in self.heads.values():
            h.restyle()
        for side in ("left", "right"):
            self.heads[side].show_side(self.doc.side(side))
        self.location.update()

    def show_location(self, on: bool):
        self.location.setVisible(on)

    def show_diff_pane(self, on: bool):
        self.diff_box.setVisible(on)

    # ----------------------------------------------------------------- inline marks
    def spans(self, side: str, row: int):
        if row >= len(self.doc.rows):
            return None
        r = self.doc.rows[row]
        if r.kind != "changed" or (r.block >= 0 and self.doc.blocks[r.block].ignored):
            return None
        got = self._span_cache.get(row)
        if got is None:
            a, b = self.doc.left.lines[r.l], self.doc.right.lines[r.r]
            got = diff.inline(a, b, self.doc.options)
            self._span_cache[row] = got
        return got[0] if side == "left" else got[1]

    def _detail_spans(self, side: str, row: int):
        b = self.current_block()
        return self.spans(side, b.row1 + row) if b else None

    # ----------------------------------------------------------------- the current difference
    def current_block(self) -> diff.Block | None:
        return self.doc.blocks[self.cur] if 0 <= self.cur < len(self.doc.blocks) else None

    def _mark_current(self):
        b = self.current_block()
        for pane in self.panes.values():
            pane.current = (b.row1, b.row2) if b else None
            pane.viewport().update()
        for side, d in self.detail.items():
            if b:
                rows = self.view_rows(side)[b.row1:b.row2]
            else:
                rows = []
            d.load(rows)
        n = self.doc.number(b) if b else 0
        self.diff_title.setText(f"DIFF PANE  ·  DIFFERENCE {n} OF {len(self.doc.counted)}" if n else "DIFF PANE")

    def go(self, block: diff.Block | None, focus: bool = True):
        """Make a difference current and show it (Next / Previous / First / Last)."""
        if block is None:
            return False
        self.cur = block.index
        self._mark_current()
        for side, pane in self.panes.items():
            pane.put_cursor(block.row1, 0)
        self._center(block.row1, block.row2)
        if focus:
            self.focused_pane().setFocus()
        self.changed.emit()
        return True

    def _center(self, a: int, b: int):
        pane = self.panes["left"]
        visible = pane.visible_rows()
        top = max(0, a - max(0, (visible - (b - a)) // 2)) if b - a < visible else a
        self._scrolling = True
        for p in self.panes.values():
            p.verticalScrollBar().setValue(top)
        self._scrolling = False
        self._view_changed()

    def scroll_to_row(self, row: int):
        visible = self.panes["left"].visible_rows()
        top = max(0, row - visible // 2)
        for p in self.panes.values():
            p.verticalScrollBar().setValue(top)

    def focused_pane(self) -> TextPane:
        for p in self.panes.values():
            if p.hasFocus():
                return p
        return self.panes.get(getattr(self, "_last_side", "left"), self.panes["left"])

    def _cursor_moved(self, side: str):
        if self.panes[side].loading:
            return
        self._last_side = side
        row = self.panes[side].textCursor().blockNumber()
        b = self.doc.block_at(row)
        if b is not None and not b.ignored and b.index != self.cur:
            self.cur = b.index                     # clicking in a difference selects it (WinMerge)
            self._mark_current()
        if not self._scrolling:
            other = self.panes["right" if side == "left" else "left"]
            if other.textCursor().blockNumber() != row and not other.hasFocus():
                other.blockSignals(True)
                other.put_cursor(row, 0)
                other.blockSignals(False)
        self.changed.emit()

    def next(self):
        return self.go(self.doc.next_block(self._anchor_row()))

    def prev(self):
        return self.go(self.doc.prev_block(self._anchor_row(top=True)))

    def first(self):
        return self.go(self.doc.counted[0] if self.doc.counted else None)

    def last(self):
        return self.go(self.doc.counted[-1] if self.doc.counted else None)

    def current(self):
        b = self.current_block()
        return self.go(b) if b else self.next()

    def _anchor_row(self, top: bool = False) -> int:
        b = self.current_block()
        if b is not None:
            return b.row1 if top else b.row1
        return self.focused_pane().textCursor().blockNumber() - (0 if top else 1)

    # ----------------------------------------------------------------- merging and editing
    def copy(self, to: str) -> bool:
        self.apply_edits()
        b = self.current_block()
        if b is None:
            row = self.focused_pane().textCursor().blockNumber()
            b = self.doc.block_at(row)
        if b is None or not self.doc.copy(b, to):
            return False
        row = b.row1
        self.rebuild()
        nb = self.doc.block_at(row) or self.doc.next_block(row - 1)
        self.cur = nb.index if nb else -1
        self._mark_current()
        return True

    def copy_all(self, to: str) -> bool:
        self.apply_edits()
        if not self.doc.copy_all(to):
            return False
        self.cur = -1
        self.rebuild()
        return True

    def can_copy(self, to: str) -> bool:
        return self.doc.can_copy(to) and bool(self.doc.counted)

    def edited(self, side: str):
        self._pending.add(side)
        if self.sync:
            self.apply_edits()
        else:
            self.timer.start()
        self.heads[side].name.setText(self.doc.side(side).name + "  *")
        self.heads[side].name.setStyleSheet(f"font-weight: 600; color: {theme.LED_ORANGE};")

    def apply_edits(self) -> bool:
        self.timer.stop()
        done = False
        for side in sorted(self._pending):
            done |= self.doc.set_lines(side, self.panes[side].real_lines())
        self._pending.clear()
        if done:
            b = self.current_block()
            self.rebuild()
            if b is None:
                self.cur = -1
        return done

    def undo(self) -> bool:
        self.apply_edits()
        if self.doc.undo():
            self.rebuild()
            return True
        return False

    def redo(self) -> bool:
        self.apply_edits()
        if self.doc.redo():
            self.rebuild()
            return True
        return False

    def recompare(self, options: diff.Options | None = None):
        self.apply_edits()
        if options is not None:
            self.doc.options = options
        self.doc.compute()
        self.rebuild()

    # ----------------------------------------------------------------- scrolling together
    def _scrolled(self, side: str, value: int, vertical: bool):
        if self._scrolling:
            return
        self._scrolling = True
        other = self.panes["right" if side == "left" else "left"]
        bar = other.verticalScrollBar() if vertical else other.horizontalScrollBar()
        bar.setValue(value)
        self._scrolling = False
        self._view_changed()

    def _view_changed(self):
        pane = self.panes["left"]
        self.location.set_view(pane.first_visible_row(), pane.visible_rows())

    # ----------------------------------------------------------------- status
    def status(self) -> str:
        if self.doc.binary:
            return "Binary files  ·  " + ("identical" if self.doc.identical() else "different")
        n = len(self.doc.counted)
        b = self.current_block()
        pane = self.focused_pane()
        row, line, col = pane.cursor_place()
        where = f"Ln {line + 1}  Col {col + 1}" if line is not None else ""
        if n == 0:
            head = "The selected files are identical" if not self.doc.blocks else \
                "No differences that count (only ignored ones)"
        elif b is not None and self.doc.number(b):
            head = f"Difference {self.doc.number(b)} of {n}"
        else:
            head = f"{n} difference{'s' if n != 1 else ''}"
        return "  ·  ".join(x for x in (head, where) if x)
