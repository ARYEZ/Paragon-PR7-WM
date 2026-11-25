"""Comparing two texts line by line, the way WinMerge does (no Qt).

Each line is compared through a key built from WinMerge's options (ignore whitespace: compare / ignore changes /
ignore all, ignore case, ignore carriage return differences), and difflib lines the two sides up. The result is a
list of rows, one per line of the window, with a blank filler opposite a line that's only on one side, and a list of
differences (blocks of rows). With "ignore blank lines", a difference made only of blank lines is still shown but
marked ignored: Next / Previous skip it and it isn't counted, as in WinMerge.

`inline` finds what changed inside a changed line (word level, WinMerge's default, or character level).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

WHITESPACE = ("compare", "changes", "all")      # WinMerge's three choices
_WS = re.compile(r"\s+")
_TOKENS = re.compile(r"\w+|\s+|.", re.UNICODE)


@dataclass
class Options:
    whitespace: str = "compare"     # compare / changes (amount of whitespace ignored) / all (whitespace ignored)
    blank_lines: bool = False       # ignore blank lines
    case: bool = False              # ignore case
    eol: bool = True                # ignore carriage return differences (Windows / Unix / Mac line endings)
    inline: str = "word"            # what's marked inside a changed line: word / char / "" (nothing)

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict) -> "Options":
        o = cls()
        for k, v in (d or {}).items():
            if hasattr(o, k):
                setattr(o, k, v)
        if o.whitespace not in WHITESPACE:
            o.whitespace = "compare"
        return o


def key(line: str, end: str, o: Options) -> str:
    """What a line is compared by."""
    s = line
    if o.whitespace == "all":
        s = _WS.sub("", s)
    elif o.whitespace == "changes":          # GNU diff -b: runs of whitespace alike, trailing whitespace ignored
        s = _WS.sub(" ", s).rstrip()
    if o.case:
        s = s.casefold()
    if not o.eol:
        s += "\0" + end
    return s


@dataclass
class Row:
    l: int | None           # line index on the left (None: a filler)
    r: int | None
    kind: str               # same / changed (on both sides) / left / right (only on that side)
    block: int = -1         # the difference this row belongs to


@dataclass
class Block:
    index: int
    row1: int               # rows [row1, row2)
    row2: int
    l1: int                 # left lines [l1, l2)
    l2: int
    r1: int
    r2: int
    ignored: bool = False

    @property
    def kind(self) -> str:
        if self.r1 == self.r2:
            return "left"
        if self.l1 == self.l2:
            return "right"
        return "changed"


@dataclass
class Result:
    rows: list[Row]
    blocks: list[Block]

    @property
    def counted(self) -> list[Block]:
        """The differences that count (Next / Previous, "N differences")."""
        return [b for b in self.blocks if not b.ignored]


def _blank(line: str) -> bool:
    return not line.strip()


def compare(left: list[str], left_ends: list[str], right: list[str], right_ends: list[str],
            o: Options | None = None) -> Result:
    o = o or Options()
    ka = [key(a, e, o) for a, e in zip(left, left_ends)]
    kb = [key(b, e, o) for b, e in zip(right, right_ends)]
    # autojunk would call frequent lines (blank ones, "}") junk in long files and give odd alignments; only very
    # long files use it, where the plain match gets slow
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=len(ka) + len(kb) > 40000)
    rows: list[Row] = []
    blocks: list[Block] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            rows.extend(Row(i1 + k, j1 + k, "same") for k in range(i2 - i1))
            continue
        start = len(rows)
        b = Block(len(blocks), start, start, i1, i2, j1, j2)
        for k in range(max(i2 - i1, j2 - j1)):
            li = i1 + k if i1 + k < i2 else None
            rj = j1 + k if j1 + k < j2 else None
            kind = "changed" if li is not None and rj is not None else ("left" if li is not None else "right")
            rows.append(Row(li, rj, kind, b.index))
        b.row2 = len(rows)
        if o.blank_lines:
            b.ignored = all(_blank(x) for x in left[i1:i2]) and all(_blank(x) for x in right[j1:j2])
        blocks.append(b)
    return Result(rows, blocks)


def inline(a: str, b: str, o: Options | None = None) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Character ranges that differ inside a changed pair of lines: (left ranges, right ranges)."""
    o = o or Options()
    if not o.inline:
        return [], []
    if o.inline == "char":
        ta = [(i, i + 1) for i in range(len(a))]
        tb = [(i, i + 1) for i in range(len(b))]
    else:
        ta = [m.span() for m in _TOKENS.finditer(a)]
        tb = [m.span() for m in _TOKENS.finditer(b)]

    def norm(text, spans):
        out = []
        for s, e in spans:
            t = text[s:e]
            if t.isspace():
                if o.whitespace == "all":
                    continue                       # whitespace doesn't count at all
                if o.whitespace == "changes":
                    t = " "
            out.append(((t.casefold() if o.case else t), (s, e)))
        return out
    na, nb = norm(a, ta), norm(b, tb)
    sm = difflib.SequenceMatcher(None, [t for t, _ in na], [t for t, _ in nb], autojunk=False)
    ls: list[tuple[int, int]] = []
    rs: list[tuple[int, int]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if i2 > i1:
            _add(ls, na[i1][1][0], na[i2 - 1][1][1])
        if j2 > j1:
            _add(rs, nb[j1][1][0], nb[j2 - 1][1][1])
    if o.whitespace == "changes":                  # trailing whitespace alone isn't a change
        ls = [(s, e) for s, e in ls if a[s:e].strip() or e < len(a.rstrip())]
        rs = [(s, e) for s, e in rs if b[s:e].strip() or e < len(b.rstrip())]
    return ls, rs


def _add(spans: list[tuple[int, int]], s: int, e: int) -> None:
    if spans and s <= spans[-1][1]:
        spans[-1] = (spans[-1][0], max(e, spans[-1][1]))
    else:
        spans.append((s, e))


def count(left: list[str], left_ends: list[str], right: list[str], right_ends: list[str],
          o: Options | None = None) -> int:
    """How many differences count (folder compare's "N differences")."""
    return len(compare(left, left_ends, right, right_ends, o).counted)
