import codecs
import os

from pr7wm import compare, diff, folders, textio

LEFT = 'a = 1\r\nb = 2\r\nc = 3\r\nd = 4\r\n'
RIGHT = 'a = 1\nb = 20\nc = 3\nnew line\nd = 4\n'


def write(p, data):
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return str(p)


def test_split_keeps_every_ending():
    lines, ends = textio.split("a\r\nb\nc\rd")
    assert lines == ["a", "b", "c", "d"] and ends == ["\r\n", "\n", "\r", ""]
    assert textio.join(lines, ends) == "a\r\nb\nc\rd"
    assert textio.split("") == ([], [])


def test_unchanged_saves_are_byte_exact(tmp_path):
    samples = {"bom.txt": codecs.BOM_UTF8 + "héllo\r\nwörld".encode(),
               "u16.txt": codecs.BOM_UTF16_LE + "one\r\ntwo\r\n".encode("utf-16-le"),
               "ansi.txt": b"caf\xe9 \x81\x8d\r\nmixed\nends\r",
               "plain.txt": b"no final newline"}
    for name, data in samples.items():
        p = write(tmp_path / name, data)
        fc = compare.FileCompare.open(p, p)
        fc.save("left")
        assert open(p, "rb").read() == data, name


def test_binary_files_are_told_apart(tmp_path):
    a = write(tmp_path / "a.bin", b"MZ\0\1\2")
    b = write(tmp_path / "b.bin", b"MZ\0\1\3")
    fc = compare.FileCompare.open(a, b)
    assert fc.binary and not fc.identical() and fc.rows == []
    u16 = write(tmp_path / "u.txt", codecs.BOM_UTF16_LE + "x".encode("utf-16-le"))
    assert not textio.read(u16).binary


def test_rows_and_blocks():
    a, ae = textio.split(LEFT)
    b, be = textio.split(RIGHT)
    r = diff.compare(a, ae, b, be)
    kinds = [(x.l, x.r, x.kind) for x in r.rows]
    assert kinds == [(0, 0, "same"), (1, 1, "changed"), (2, 2, "same"), (None, 3, "right"), (3, 4, "same")]
    assert [blk.kind for blk in r.blocks] == ["changed", "right"]


def test_line_endings_count_only_when_asked():
    a, ae = textio.split("x\r\ny\r\n")
    b, be = textio.split("x\ny\n")
    assert diff.count(a, ae, b, be) == 0
    assert diff.count(a, ae, b, be, diff.Options(eol=False)) == 1


def test_whitespace_and_case_options():
    a, ae = textio.split("if  (x):\n    return Y \n")
    b, be = textio.split("if (x):\n\treturn y\n")
    assert diff.count(a, ae, b, be) == 1
    assert diff.count(a, ae, b, be, diff.Options(whitespace="changes")) == 1          # case still differs
    assert diff.count(a, ae, b, be, diff.Options(whitespace="changes", case=True)) == 0
    a2, ae2 = textio.split("a b\n")
    b2, be2 = textio.split("ab\n")
    assert diff.count(a2, ae2, b2, be2, diff.Options(whitespace="changes")) == 1
    assert diff.count(a2, ae2, b2, be2, diff.Options(whitespace="all")) == 0


def test_blank_line_differences_are_ignored_but_shown():
    a, ae = textio.split("one\n\ntwo\n")
    b, be = textio.split("one\ntwo\nthree\n")
    r = diff.compare(a, ae, b, be, diff.Options(blank_lines=True))
    assert [x.ignored for x in r.blocks] == [True, False]
    assert len(r.counted) == 1 and any(x.kind == "left" for x in r.rows)


def test_inline_marks_words_and_characters():
    a, b = 'CODEC = "prores_4444"', 'CODEC = "hevc_10bit"'
    ls, rs = diff.inline(a, b)
    assert [a[s:e] for s, e in ls] == ["prores_4444"] and [b[s:e] for s, e in rs] == ["hevc_10bit"]
    ls, rs = diff.inline("FPS = 23.976", "FPS = 24", diff.Options(inline="char"))
    assert ls and all("FPS" not in "FPS = 23.976"[s:e] for s, e in ls)
    assert diff.inline("a  b", "a b", diff.Options(whitespace="changes")) == ([], [])


def test_copy_to_right_takes_the_right_line_endings(tmp_path):
    lp, rp = write(tmp_path / "l.txt", LEFT), write(tmp_path / "r.txt", RIGHT)
    fc = compare.FileCompare.open(lp, rp)
    fc.copy(fc.blocks[0], "right")
    assert fc.right.modified and not fc.left.modified
    fc.save("right")
    assert open(rp, "rb").read() == b"a = 1\nb = 2\nc = 3\nnew line\nd = 4\n"   # LF kept, the copied line too
    fc.copy(fc.blocks[0], "left")                         # "new line" into the CRLF side
    fc.save("left")
    assert open(lp, "rb").read() == b"a = 1\r\nb = 2\r\nc = 3\r\nnew line\r\nd = 4\r\n"
    assert fc.identical()


def test_copy_all_undo_redo(tmp_path):
    lp, rp = write(tmp_path / "l.txt", LEFT), write(tmp_path / "r.txt", RIGHT)
    fc = compare.FileCompare.open(lp, rp)
    fc.copy_all("left")
    assert fc.left.lines == fc.right.lines and fc.left.ends == ["\r\n"] * 5
    assert fc.undo() and fc.left.lines == textio.split(LEFT)[0] and not fc.left.modified
    assert fc.redo() and fc.left.lines == fc.right.lines and fc.left.modified


def test_copy_handles_the_end_of_the_file(tmp_path):
    lp = write(tmp_path / "l.txt", "x\ny")                # no final newline
    rp = write(tmp_path / "r.txt", "x\n")
    fc = compare.FileCompare.open(lp, rp)
    fc.copy(fc.blocks[0], "right")
    fc.save("right")
    assert open(rp, "rb").read() == b"x\ny"
    lp2 = write(tmp_path / "l2.txt", "x")
    rp2 = write(tmp_path / "r2.txt", "x\ny\nz")
    fc = compare.FileCompare.open(lp2, rp2)
    fc.copy(fc.blocks[0], "right")                        # the right's extra lines removed
    fc.save("right")
    assert open(rp2, "rb").read() == b"x"


def test_read_only_sides_and_edits(tmp_path):
    lp, rp = write(tmp_path / "l.txt", LEFT), write(tmp_path / "r.txt", RIGHT)
    fc = compare.FileCompare.open(lp, rp, wl=True)
    assert not fc.copy(fc.blocks[0], "left")
    assert fc.set_lines("right", ["a = 1", "b = 2", "c = 3", "d = 4"])
    assert fc.identical()
    fc.save("right")
    assert open(rp, "rb").read() == b"a = 1\nb = 2\nc = 3\nd = 4\n"


def test_changed_on_disk_and_reload(tmp_path):
    lp, rp = write(tmp_path / "l.txt", LEFT), write(tmp_path / "r.txt", RIGHT)
    fc = compare.FileCompare.open(lp, rp)
    assert not fc.left.changed_on_disk()
    write(tmp_path / "l.txt", RIGHT + "more\n")
    assert fc.left.changed_on_disk()
    fc.reload()
    assert fc.counted and fc.left.lines[-1] == "more"


def test_patch(tmp_path):
    lp, rp = write(tmp_path / "l.txt", LEFT), write(tmp_path / "r.txt", RIGHT)
    p = compare.FileCompare.open(lp, rp).patch()
    assert p.startswith("--- " + lp) and "-b = 2\n+b = 20\n" in p and "+new line\n" in p


def test_unencodable(tmp_path):
    lp = write(tmp_path / "l.txt", b"caf\xe9\r\n")          # ANSI
    rp = write(tmp_path / "r.txt", "日本\r\n")
    fc = compare.FileCompare.open(lp, rp)
    fc.copy_all("left")
    assert fc.unencodable("left") == ["日", "本"]


# ------------------------------------------------------------------- folders
def tree(root, files):
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if data is None:
            p.mkdir(exist_ok=True)
        else:
            p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return str(root)


def test_filter_masks():
    f = folders.Filter("*.py;*.txt;!test_*;!build\\;!.git/")
    assert f.file_ok("a.py") and f.file_ok("A.TXT") and not f.file_ok("test_a.py") and not f.file_ok("a.c")
    assert not f.dir_ok("build") and not f.dir_ok(".git") and f.dir_ok("src")
    every = folders.Filter("*.*")
    assert every.file_ok("Makefile") and every.file_ok("a.b.c")
    assert folders.Filter("readme.*").file_ok("README") and folders.Filter("readme.*").file_ok("readme.md")


def make_pair(tmp_path):
    left = tree(tmp_path / "L", {"same.txt": "x\n", "text.py": "a\nb\nc\n", "bin.dat": b"\0\1\2",
                                 "only_left.txt": "l", "sub/inner.txt": "one\n", "lonely/x.txt": "x",
                                 ".git/config": "skip"})
    right = tree(tmp_path / "R", {"same.txt": "x\r\n", "text.py": "a\nB\nc\nd\n", "bin.dat": b"\0\1\3",
                                  "only_right.txt": "r", "sub/inner.txt": "one\n", ".git/config": "other"})
    return left, right


def test_folder_compare_results(tmp_path):
    left, right = make_pair(tmp_path)
    items = folders.compare(left, right, flt=folders.Filter("*.*;!.git\\"))
    by = {i.rel: i for i in items}
    assert ".git" not in by and ".git/config" not in by
    assert by["same.txt"].result == folders.IDENTICAL and by["same.txt"].diffs == 0      # CR differences ignored
    assert by["text.py"].result == folders.DIFFERENT and by["text.py"].diffs == 2
    assert by["bin.dat"].result == folders.BIN_DIFFERENT
    assert by["only_left.txt"].result == folders.LEFT_ONLY and by["only_right.txt"].result == folders.RIGHT_ONLY
    assert by["lonely"].result == folders.LEFT_ONLY and "lonely/x.txt" not in by
    assert by["sub"].result == folders.IDENTICAL and by["sub/inner.txt"].result == folders.IDENTICAL
    assert [i.rel for i in items][:3] == ["lonely", "sub", "sub/inner.txt"]           # folders first, tree order
    assert folders.result_text(by["text.py"], left, right) == "Text files are different  ·  2 differences"
    assert folders.result_text(by["only_left.txt"], left, right) == f"Left only: {left}"
    c = folders.counts(items)
    assert c == {"identical": 2, "different": 2, "left": 2, "right": 1, "skipped": 0}


def test_other_methods(tmp_path):
    left, right = make_pair(tmp_path)
    os.utime(os.path.join(left, "text.py"), (1_700_000_000, 1_700_000_000))
    os.utime(os.path.join(right, "text.py"), (1_700_000_001, 1_700_000_001))
    by = {i.rel: i for i in folders.compare(left, right, method="date")}
    assert by["text.py"].result == folders.SAME_DATE
    by = {i.rel: i for i in folders.compare(left, right, method="date_size")}
    assert by["text.py"].result == folders.DIFFERENT_DATE
    by = {i.rel: i for i in folders.compare(left, right, method="quick")}
    assert by["same.txt"].result == folders.DIFFERENT                                   # bytes differ
    by = {i.rel: i for i in folders.compare(left, right, recursive=False)}
    assert by["sub"].result == folders.SKIPPED and "sub/inner.txt" not in by


def test_folder_copy_and_delete(tmp_path):
    left, right = make_pair(tmp_path)
    by = {i.rel: i for i in folders.compare(left, right)}
    folders.copy(by["text.py"], "right", left, right)
    assert open(os.path.join(right, "text.py")).read() == "a\nb\nc\n" and by["text.py"].result == folders.IDENTICAL
    folders.copy(by["lonely"], "right", left, right)
    assert open(os.path.join(right, "lonely", "x.txt")).read() == "x"
    folders.delete(by["only_right.txt"], "right", left, right)
    assert not os.path.exists(os.path.join(right, "only_right.txt"))
    assert os.path.exists(os.path.join(os.environ["PR7WM_TRASH"], "only_right.txt"))
    again = {i.rel: i for i in folders.compare(left, right)}
    assert again["text.py"].result == folders.IDENTICAL and again["lonely"].result == folders.IDENTICAL
    assert "only_right.txt" not in again


def test_cancel(tmp_path):
    import pytest
    left, right = make_pair(tmp_path)
    with pytest.raises(folders.Cancelled):
        folders.compare(left, right, cancelled=lambda: True)
