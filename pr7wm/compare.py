"""One file compare (no Qt): two sides, the differences between them, and WinMerge's merging (Copy to Right / Left,
Copy All), Undo / Redo, saving and Generate Patch.

A side is a file (or an unnamed, empty text). Copied lines take the destination's main line ending (WinMerge's
default), and every other line keeps its own, so a side saved after copying one difference changes only those bytes.
Undo keeps whole snapshots of both sides (edits made in a pane come in as `set_lines`, one step each).
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field

from . import diff, textio

UNDO_LIMIT = 200


@dataclass
class Side:
    path: str | None = None
    text: textio.Text = field(default_factory=textio.empty)
    description: str = ""            # WinMerge's /dl /dr: shown instead of the path
    read_only: bool = False
    modified: bool = False
    stamp: tuple | None = None       # (size, mtime_ns) when read or saved: tells a change made elsewhere

    @classmethod
    def open(cls, path: str | None, description: str = "", read_only: bool = False) -> "Side":
        s = cls(path, textio.empty(), description, read_only)
        if path:
            s.text = textio.read(path)
            s.stamp = _stamp(path)
        return s

    @property
    def name(self) -> str:
        return os.path.basename(self.path) if self.path else (self.description or "Untitled")

    @property
    def title(self) -> str:
        return self.description or self.path or "Untitled"

    @property
    def lines(self) -> list[str]:
        return self.text.lines

    @property
    def ends(self) -> list[str]:
        return self.text.ends

    def changed_on_disk(self) -> bool:
        return bool(self.path) and self.stamp is not None and _stamp(self.path) != self.stamp


def _stamp(path: str) -> tuple | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


class FileCompare:
    def __init__(self, left: Side, right: Side, options: diff.Options | None = None):
        self.left, self.right = left, right
        self.options = options or diff.Options()
        self.undo_stack: list[tuple] = []
        self.redo_stack: list[tuple] = []
        self.result = diff.Result([], [])
        self.compute()

    @classmethod
    def open(cls, left: str | None, right: str | None, options: diff.Options | None = None, **kw) -> "FileCompare":
        return cls(Side.open(left, kw.get("dl", ""), kw.get("wl", False)),
                   Side.open(right, kw.get("dr", ""), kw.get("wr", False)), options)

    # ----------------------------------------------------------------- the differences
    @property
    def binary(self) -> bool:
        return self.left.text.binary or self.right.text.binary

    @property
    def rows(self) -> list[diff.Row]:
        return self.result.rows

    @property
    def blocks(self) -> list[diff.Block]:
        return self.result.blocks

    @property
    def counted(self) -> list[diff.Block]:
        return self.result.counted

    def compute(self) -> None:
        if self.binary:
            self.result = diff.Result([], [])
            return
        self.result = diff.compare(self.left.lines, self.left.ends, self.right.lines, self.right.ends, self.options)

    def side(self, name: str) -> Side:
        return self.left if name == "left" else self.right

    def identical(self) -> bool:
        if self.binary:
            return self.binary_identical()
        return not self.counted

    def binary_identical(self) -> bool:
        if not (self.left.path and self.right.path):
            return False
        try:
            return files_equal(self.left.path, self.right.path)
        except OSError:
            return False

    def number(self, block: diff.Block) -> int:
        """1-based position among the counted differences (0 for an ignored one)."""
        for n, b in enumerate(self.counted, 1):
            if b.index == block.index:
                return n
        return 0

    def block_at(self, row: int) -> diff.Block | None:
        if 0 <= row < len(self.rows) and self.rows[row].block >= 0:
            return self.blocks[self.rows[row].block]
        return None

    def next_block(self, row: int) -> diff.Block | None:
        return next((b for b in self.counted if b.row1 > row), None)

    def prev_block(self, row: int) -> diff.Block | None:
        return next((b for b in reversed(self.counted) if b.row2 <= row), None)

    def row_of(self, side: str, line: int) -> int:
        """The row showing a line of one side (the nearest one at or after it)."""
        attr = "l" if side == "left" else "r"
        for i, r in enumerate(self.rows):
            v = getattr(r, attr)
            if v is not None and v >= line:
                return i
        return max(0, len(self.rows) - 1)

    # ----------------------------------------------------------------- undo
    def _snapshot(self) -> tuple:
        return (list(self.left.lines), list(self.left.ends), self.left.modified,
                list(self.right.lines), list(self.right.ends), self.right.modified)

    def _restore(self, snap: tuple) -> None:
        self.left.text.lines, self.left.text.ends, self.left.modified = list(snap[0]), list(snap[1]), snap[2]
        self.right.text.lines, self.right.text.ends, self.right.modified = list(snap[3]), list(snap[4]), snap[5]
        self.compute()

    def _push(self) -> None:
        self.undo_stack.append(self._snapshot())
        del self.undo_stack[:-UNDO_LIMIT]
        self.redo_stack.clear()

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append(self._snapshot())
        self._restore(self.undo_stack.pop())
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append(self._snapshot())
        self._restore(self.redo_stack.pop())
        return True

    # ----------------------------------------------------------------- merging
    def can_copy(self, to: str) -> bool:
        return not self.binary and not self.side(to).read_only

    def copy(self, block: diff.Block, to: str) -> bool:
        """Copy one difference to the other side (Merge > Copy to Right / Copy to Left)."""
        if not self.can_copy(to):
            return False
        self._push()
        self._copy(block, to)
        self.side(to).modified = True
        self.compute()
        return True

    def copy_all(self, to: str) -> bool:
        if not self.can_copy(to) or not self.blocks:
            return False
        self._push()
        for b in reversed(self.blocks):          # from the end, so earlier line numbers stay right
            self._copy(b, to)
        self.side(to).modified = True
        self.compute()
        return True

    def _copy(self, b: diff.Block, to: str) -> None:
        src, dst = (self.left, self.right) if to == "right" else (self.right, self.left)
        s1, s2, d1, d2 = (b.l1, b.l2, b.r1, b.r2) if to == "right" else (b.r1, b.r2, b.l1, b.l2)
        if not dst.path and not dst.lines:          # an empty, unnamed side takes on the copied file's form
            dst.text.eol, dst.text.encoding = src.text.eol, src.text.encoding
        eol = textio.EOLS[dst.text.eol][1]
        lines = src.lines[s1:s2]
        ends = [eol if e else "" for e in src.ends[s1:s2]]
        dl, de = dst.text.lines, dst.text.ends
        at_end = d2 == len(dl)
        old_final = de[-1] if de else eol
        dl[d1:d2] = lines
        de[d1:d2] = ends
        for k in range(len(dl) - 1):            # every line but the last ends with a line ending
            if not de[k]:
                de[k] = eol
        if at_end and dl:                       # the block was the end of the destination: its final line
            if lines and s2 == len(src.lines):
                de[-1] = eol if src.ends[s2 - 1] else ""        # ... is the source's final line, as it ends
            elif lines:
                de[-1] = eol
            else:
                de[-1] = de[-1] if old_final else ""            # lines removed: "no final ending" stays

    def set_lines(self, side: str, lines: list[str]) -> bool:
        """An edit made in a pane: the side's new lines. Each unchanged line keeps its ending."""
        s = self.side(side)
        if lines == s.lines:
            return False
        self._push()
        old_lines, old_ends = s.lines, s.ends
        eol = textio.EOLS[s.text.eol][1]
        ends = [eol] * len(lines)
        sm = difflib.SequenceMatcher(None, old_lines, lines, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                ends[j1:j2] = old_ends[i1:i2]
        if lines:
            last_old = old_ends[-1] if old_ends else eol
            ends[-1] = last_old if last_old == "" else ends[-1]
            for k in range(len(lines) - 1):
                if not ends[k]:
                    ends[k] = eol
        s.text.lines, s.text.ends = list(lines), ends
        s.modified = True
        self.compute()
        return True

    # ----------------------------------------------------------------- files
    def save(self, side: str, path: str | None = None) -> str:
        """Write one side (to `path`: Save As). Raises UnicodeEncodeError / OSError."""
        s = self.side(side)
        target = path or s.path
        if not target:
            raise ValueError("no file name")
        textio.write(target, s.text)
        s.path, s.modified, s.stamp = target, False, _stamp(target)
        if path:
            s.read_only = False
        return target

    def unencodable(self, side: str) -> list[str]:
        s = self.side(side)
        return textio.unencodable(s.text.text, s.text.encoding)

    def reload(self) -> None:
        for s in (self.left, self.right):
            if s.path and os.path.exists(s.path):
                s.text = textio.read(s.path)
                s.stamp = _stamp(s.path)
                s.modified = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.compute()

    def patch(self, context: int = 3) -> str:
        """Tools > Generate Patch: a unified diff, the left as the original."""
        a = [x + "\n" for x in self.left.lines]
        b = [x + "\n" for x in self.right.lines]
        out = difflib.unified_diff(a, b, self.left.title, self.right.title, _when(self.left.path),
                                   _when(self.right.path), n=context)
        return "".join(out)


def _when(path: str | None) -> str:
    if not path:
        return ""
    try:
        import datetime
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return ""


def files_equal(a: str, b: str, chunk: int = 1 << 20) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(chunk), fb.read(chunk)
            if x != y:
                return False
            if not x:
                return True
