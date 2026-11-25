"""Folder compare (no Qt), the way WinMerge's folder window compares.

Both folders are walked (links / junctions not followed); every file gets a result: text files identical or
different (with how many differences, by the same diff options as the file compare), binary files identical or
different, left only / right only. A folder that's only on one side is one item (its contents aren't listed);
folders on both sides are walked when "Include subfolders" is on, and their own row says whether anything in them
differs.

Compare methods (WinMerge's): full contents (text files by their differences, binary files byte by byte), quick
contents (byte by byte), modified date, date and size, size. Times within 2 s are the same (FAT keeps 2 s steps).

File filters (WinMerge's mask filter): masks separated by `;`, `*.*` matches every file (with or without a dot, as on
Windows), `!mask` leaves files out, and a mask ending in `\\` names a folder to leave out (`!.git\\`).
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import stat
from dataclasses import dataclass, field

from . import diff, textio, trash

METHODS = {"full": "Full Contents", "quick": "Quick Contents", "date": "Modified Date",
           "date_size": "Modified Date and Size", "size": "Size"}
TIME_TOLERANCE = 2.0
DEFAULT_FILTER = "*.*"
TEXT_LIMIT = 50 * 1024 * 1024        # larger text files are compared byte by byte (WinMerge does too, by size)

# result codes
IDENTICAL, DIFFERENT = "identical", "different"
BIN_IDENTICAL, BIN_DIFFERENT = "binary_identical", "binary_different"
LEFT_ONLY, RIGHT_ONLY = "left_only", "right_only"
SKIPPED, ERROR = "skipped", "error"
SAME_DATE, DIFFERENT_DATE = "same_date", "different_date"

GROUPS = {"identical": (IDENTICAL, BIN_IDENTICAL, SAME_DATE), "different": (DIFFERENT, BIN_DIFFERENT, DIFFERENT_DATE),
          "left": (LEFT_ONLY,), "right": (RIGHT_ONLY,), "skipped": (SKIPPED, ERROR)}


class Filter:
    def __init__(self, text: str = DEFAULT_FILTER):
        self.text = text.strip() or DEFAULT_FILTER
        self.include: list[re.Pattern] = []
        self.exclude: list[re.Pattern] = []
        self.exclude_dirs: list[re.Pattern] = []
        for part in re.split(r"[;\n]", self.text):
            part = part.strip()
            if not part:
                continue
            neg = part.startswith("!")
            if neg:
                part = part[1:].strip()
            is_dir = part.endswith(("\\", "/"))
            part = part.rstrip("\\/")
            if not part:
                continue
            rx = _mask(part)
            if is_dir:
                if neg:
                    self.exclude_dirs.append(rx)
            elif neg:
                self.exclude.append(rx)
            else:
                self.include.append(rx)
        if not self.include:
            self.include.append(_mask("*.*"))

    def file_ok(self, name: str) -> bool:
        n = name.casefold()
        return any(r.match(n) for r in self.include) and not any(r.match(n) for r in self.exclude)

    def dir_ok(self, name: str) -> bool:
        n = name.casefold()
        return not any(r.match(n) for r in self.exclude_dirs)


def _mask(m: str) -> re.Pattern:
    m = m.casefold()
    if m in ("*.*", "*"):
        return re.compile(r".*\Z", re.S)
    if m.endswith(".*"):                    # "name.*" also matches "name" (Windows)
        return re.compile(fnmatch.translate(m[:-2]).replace(r"\Z", r"(\..*)?\Z"), re.S)
    return re.compile(fnmatch.translate(m), re.S)


@dataclass
class Info:
    size: int
    mtime: float
    is_dir: bool = False
    attrs: int = 0
    name: str = ""              # as spelled on disk (Windows matches names whatever their case)


@dataclass
class Item:
    rel: str                     # relative path with "/" between parts
    is_dir: bool
    left: Info | None
    right: Info | None
    result: str = ""
    diffs: int | None = None     # text files: how many differences
    note: str = ""               # an error, or why it was skipped
    children: list["Item"] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.rel.rsplit("/", 1)[-1]

    @property
    def folder(self) -> str:
        return self.rel.rsplit("/", 1)[0] if "/" in self.rel else ""

    def group(self) -> str:
        for g, codes in GROUPS.items():
            if self.result in codes:
                return g
        return "different"

    def path(self, root: str) -> str:
        return os.path.join(root, *self.rel.split("/"))


def _scan(path: str, flt: Filter) -> dict[str, tuple[bool, Info]]:
    out: dict[str, tuple[bool, Info]] = {}
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_symlink() or _is_junction(e):
                        continue
                    is_dir = e.is_dir(follow_symlinks=False)
                    if is_dir and not flt.dir_ok(e.name):
                        continue
                    if not is_dir and not flt.file_ok(e.name):
                        continue
                    st = e.stat(follow_symlinks=False)
                    out[e.name.casefold() if os.name == "nt" else e.name] = (
                        is_dir, Info(0 if is_dir else st.st_size, st.st_mtime, is_dir,
                                     getattr(st, "st_file_attributes", 0), e.name))
                except OSError:
                    continue
    except OSError:
        pass
    return out


def _is_junction(e: os.DirEntry) -> bool:
    try:
        return bool(e.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, OSError):
        return False


class Cancelled(Exception):
    pass


def compare(left: str, right: str, recursive: bool = True, flt: Filter | None = None, method: str = "full",
            options: diff.Options | None = None, progress=None, cancelled=None) -> list[Item]:
    """Every item in tree order (a folder before its contents). `progress(rel)` is called per file; `cancelled()`
    returning True stops with Cancelled."""
    flt = flt or Filter()
    options = options or diff.Options()
    out: list[Item] = []

    def walk(rel: str, lp: str, rp: str) -> bool:
        """Lists one folder pair; True when anything in it differs."""
        a, b = _scan(lp, flt), _scan(rp, flt)
        keys = sorted(set(a) | set(b), key=lambda k: (not (a.get(k) or b.get(k))[0], k.casefold()))
        differs = False
        for k in keys:
            if cancelled and cancelled():
                raise Cancelled()
            la, rb = a.get(k), b.get(k)
            name = (la or rb)[1].name or k
            r = f"{rel}/{name}" if rel else name
            if la and rb and la[0] != rb[0]:        # a file on one side, a folder on the other: two items
                for side, got in (("left", la), ("right", rb)):
                    it = Item(r, got[0], got[1] if side == "left" else None, got[1] if side == "right" else None,
                              LEFT_ONLY if side == "left" else RIGHT_ONLY)
                    out.append(it)
                differs = True
                continue
            is_dir = (la or rb)[0]
            it = Item(r, is_dir, la[1] if la else None, rb[1] if rb else None)
            out.append(it)
            if not la or not rb:
                it.result = LEFT_ONLY if la else RIGHT_ONLY
                differs = True
                continue
            if is_dir:
                if recursive:
                    sub = walk(r, os.path.join(lp, name), os.path.join(rp, rb[1].name or name))
                    it.result = DIFFERENT if sub else IDENTICAL
                    differs |= sub
                else:
                    it.result = SKIPPED
                    it.note = "Subfolders aren't compared"
                continue
            if progress:
                progress(r)
            compare_files(it, os.path.join(lp, name), os.path.join(rp, rb[1].name or name), method,
                          options)
            differs |= it.group() != "identical"
        return differs

    walk("", left, right)
    return out


def compare_files(it: Item, lp: str, rp: str, method: str, options: diff.Options) -> None:
    a, b = it.left, it.right
    try:
        if method == "size":
            it.result = IDENTICAL if a.size == b.size else DIFFERENT
            return
        if method in ("date", "date_size"):
            same = abs(a.mtime - b.mtime) <= TIME_TOLERANCE and (method == "date" or a.size == b.size)
            it.result = SAME_DATE if same else DIFFERENT_DATE
            return
        with open(lp, "rb") as fa:
            head_a = fa.read(textio.SNIFF)
        with open(rp, "rb") as fb:
            head_b = fb.read(textio.SNIFF)
        binary = textio.is_binary(head_a) or textio.is_binary(head_b)
        if method == "quick" or binary or max(a.size, b.size) > TEXT_LIMIT:
            from .compare import files_equal
            same = files_equal(lp, rp)
            if binary:
                it.result = BIN_IDENTICAL if same else BIN_DIFFERENT
            else:
                it.result = IDENTICAL if same else DIFFERENT
            return
        from .compare import files_equal
        if files_equal(lp, rp):
            it.result, it.diffs = IDENTICAL, 0
            return
        ta, tb = textio.read(lp), textio.read(rp)
        n = diff.count(ta.lines, ta.ends, tb.lines, tb.ends, options)
        it.diffs = n
        it.result = IDENTICAL if n == 0 else DIFFERENT
    except OSError as e:
        it.result, it.note = ERROR, e.strerror or str(e)


def result_text(it: Item, left_root: str, right_root: str) -> str:
    """WinMerge's Comparison result column."""
    r = it.result
    if r == LEFT_ONLY:
        return f"Left only: {os.path.dirname(it.path(left_root))}"
    if r == RIGHT_ONLY:
        return f"Right only: {os.path.dirname(it.path(right_root))}"
    if it.is_dir:
        return {IDENTICAL: "Folders are identical", DIFFERENT: "Folders are different"}.get(r, it.note or "Skipped")
    if r == IDENTICAL:
        return "Text files are identical" if it.diffs is not None else "Files are identical"
    if r == DIFFERENT:
        if it.diffs:
            return f"Text files are different  ·  {it.diffs} difference{'s' if it.diffs != 1 else ''}"
        return "Files are different"
    return {BIN_IDENTICAL: "Binary files are identical", BIN_DIFFERENT: "Binary files are different",
            SAME_DATE: "Files have the same date", DIFFERENT_DATE: "Files have different dates",
            ERROR: f"Error: {it.note}", SKIPPED: it.note or "Skipped"}.get(r, r)


def counts(items: list[Item]) -> dict[str, int]:
    c = {g: 0 for g in GROUPS}
    for it in items:
        if it.is_dir and it.left and it.right:
            continue                       # folders on both sides aren't counted (their files are)
        c[it.group()] += 1
    return c


# --------------------------------------------------------------------- actions
def copy(it: Item, to: str, left_root: str, right_root: str) -> None:
    """Copy an item to the other side (Copy Left to Right / Right to Left): a file over the other one, a folder with
    everything in it."""
    src_root, dst_root = (left_root, right_root) if to == "right" else (right_root, left_root)
    src, dst = it.path(src_root), it.path(dst_root)
    if not os.path.lexists(src):
        raise FileNotFoundError(2, "It isn't there any more", src)
    os.makedirs(os.path.dirname(dst) or dst_root, exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)
    else:
        if os.path.isdir(dst):
            raise IsADirectoryError(21, "A folder has that name on the other side", dst)
        shutil.copy2(src, dst)
    info = _info(dst)
    if to == "right":
        it.right = info
    else:
        it.left = info
    it.result = BIN_IDENTICAL if it.result in (BIN_DIFFERENT, BIN_IDENTICAL) else IDENTICAL
    if it.diffs is not None:
        it.diffs = 0


def delete(it: Item, side: str, left_root: str, right_root: str) -> None:
    """Delete one side's copy (to the Recycle Bin)."""
    p = it.path(left_root if side == "left" else right_root)
    trash.send(p)
    if side == "left":
        it.left = None
    else:
        it.right = None
    if it.left is None and it.right is None:
        it.result = ""
    else:
        it.result = RIGHT_ONLY if it.left is None else LEFT_ONLY


def _info(path: str) -> Info | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return Info(0 if os.path.isdir(path) else st.st_size, st.st_mtime, os.path.isdir(path))
