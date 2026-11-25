import os
import sys

import pytest

from pr7wm import diff, settings, theme

LEFT = "a = 1\r\nb = 2\r\nc = 3\r\nd = 4\r\n"
RIGHT = "a = 1\nb = 20\nc = 3\nnew line\nd = 4\n"


def pair(tmp_path, left=LEFT, right=RIGHT, names=("left.py", "right.py")):
    a, b = tmp_path / names[0], tmp_path / names[1]
    a.write_bytes(left.encode() if isinstance(left, str) else left)
    b.write_bytes(right.encode() if isinstance(right, str) else right)
    return str(a), str(b)


def test_file_compare_lines_up(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    assert page.panes["left"].toPlainText().split("\n") == ["a = 1", "b = 2", "c = 3", "", "d = 4"]
    assert page.panes["right"].toPlainText().split("\n") == ["a = 1", "b = 20", "c = 3", "new line", "d = 4"]
    assert page.panes["left"].rows[3] == (None, "right")                 # the filler opposite "new line"
    assert page.cur == 0 and window.status.text().startswith("Difference 1 of 2")
    assert page.spans("left", 1) == [(4, 5)] and page.spans("right", 1) == [(4, 6)]
    assert window.tabs.tabText(0) == "left.py  ·  right.py"


def test_next_previous_first_last(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    window.acts["next"].trigger()
    assert page.cur == 1 and window.status.text().startswith("Difference 2 of 2")
    assert not window.page_call("next")                                 # no more
    window.acts["prev"].trigger()
    assert page.cur == 0
    window.acts["last"].trigger()
    assert page.cur == 1
    window.acts["first"].trigger()
    assert page.cur == 0
    page.panes["left"].put_cursor(4)                                    # clicking in a difference selects it
    page.panes["left"].put_cursor(1)
    assert page.cur == 0


def test_copy_save_and_undo(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    assert window.acts["copy_right"].isEnabled() and not window.acts["save"].isEnabled()
    window.acts["copy_right"].trigger()                                 # b = 2 to the right
    assert page.doc.right.lines[1] == "b = 2" and window.tabs.tabText(0).endswith("*")
    assert window.acts["save"].isEnabled() and window.keys["save"].isEnabled()
    window.acts["undo"].trigger()
    assert page.doc.right.lines[1] == "b = 20" and not page.modified()
    window.acts["redo"].trigger()
    window.acts["save"].trigger()
    assert open(b, "rb").read() == b"a = 1\nb = 2\nc = 3\nnew line\nd = 4\n"
    assert open(a, "rb").read() == LEFT.encode()                         # the other side untouched
    assert not window.tabs.tabText(0).endswith("*")


def test_copy_all_left(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    window.acts["copy_all_left"].trigger()
    window.save()
    assert open(a, "rb").read() == b"a = 1\r\nb = 20\r\nc = 3\r\nnew line\r\nd = 4\r\n"
    assert page.doc.identical() and window.status.text().startswith("The selected files are identical")


def test_typing_in_a_pane(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    pane = page.panes["left"]
    pane.put_cursor(3)                                                  # the filler row
    pane.insertPlainText("new line")
    assert page.doc.left.lines == ["a = 1", "b = 2", "c = 3", "new line", "d = 4"]
    assert len(page.doc.counted) == 1 and page.doc.left.modified
    pane.put_cursor(1, 5)
    pane.insertPlainText("0")
    assert page.doc.identical()
    window.save_side("left")
    assert open(a, "rb").read() == b"a = 1\r\nb = 20\r\nc = 3\r\nnew line\r\nd = 4\r\n"
    window.acts["undo"].trigger()                                       # typing undoes too
    assert page.doc.left.lines[1] == "b = 2"


def test_closing_with_unsaved_changes(window, tmp_path):
    a, b = pair(tmp_path)
    window.compare_files(a, b)
    window.copy("right")
    window.answers["save_changes"] = "cancel"
    assert not window.close_tab(0) and window.tabs.count() == 1
    window.answers["save_changes"] = "save"
    assert window.close_tab(0) and window.tabs.count() == 0
    assert open(b, "rb").read().startswith(b"a = 1\nb = 2\n")
    assert window.stack.currentWidget() is window.welcome


def test_save_as_and_untitled_sides(window, tmp_path):
    a, _ = pair(tmp_path)
    page = window.compare_files(a, None)
    assert page.doc.right.name == "Untitled" and len(page.doc.counted) == 1
    window.copy_all("right")
    target = tmp_path / "copy.py"
    window.answers["save_as"] = lambda args: str(target)
    assert window.save()
    assert target.read_bytes() == LEFT.encode() and page.doc.right.path == str(target)


def test_read_only_side(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b, wr=True)
    assert not window.acts["copy_right"].isEnabled() and window.acts["copy_left"].isEnabled()
    assert page.panes["right"].isReadOnly() and "READ-ONLY" in page.heads["right"].name.text()
    assert not window.copy("right")


def test_options_change_the_compare(window, tmp_path):
    a, b = pair(tmp_path, "x = 1\n", "X  =  1\n")
    page = window.compare_files(a, b)
    assert len(page.doc.counted) == 1

    def choose(_):
        from pr7wm.dialogs import save_options
        save_options(diff.Options(whitespace="all", case=True))
        return True
    window.answers["options"] = choose
    window.options()
    assert page.doc.identical()


def test_options_dialog_saves(qapp):
    from pr7wm.dialogs import OptionsDialog, load_options
    dlg = OptionsDialog()
    dlg.ws["changes"].setChecked(True)
    assert not dlg.ws["compare"].isChecked()                         # its own group: one choice at a time
    dlg.blank.setChecked(True)
    dlg.inline.setCurrentIndex(dlg.inline.findData("char"))
    dlg.method.setCurrentIndex(dlg.method.findData("quick"))
    dlg.save()
    o = load_options()
    assert o.whitespace == "changes" and o.blank_lines and o.inline == "char"
    assert settings.get("folder_method") == "quick"
    settings.set("options", "")
    settings.set("folder_method", "")


def test_binary_files(window, tmp_path):
    a, b = pair(tmp_path, b"MZ\0\1", b"MZ\0\2", ("a.exe", "b.exe"))
    page = window.compare_files(a, b)
    assert page.binary_note.text() == "BINARY FILES ARE DIFFERENT" and not page.split.isVisibleTo(page)
    assert not window.acts["copy_right"].isEnabled()
    window.answers["find"] = lambda app: None                        # PR7-HX not installed: nothing offered
    window._sync()
    assert not window.acts["open_hx"].isEnabled()
    opened = []
    window.answers["find"] = {"PR7-HX": "C:\\PR7-HX\\PR7-HX.exe"}.get
    window.answers["launch_hx"] = lambda paths: opened.append(paths) or True
    window._sync()
    assert window.acts["open_hx"].isEnabled()
    window.acts["open_hx"].trigger()
    assert opened == [[a, b]]                                         # both files, to compare their bytes there


def test_binary_files_in_a_folder_compare_open_in_pr7hx(window, tmp_path):
    L, R = tmp_path / "L", tmp_path / "R"
    L.mkdir()
    R.mkdir()
    (L / "app.bin").write_bytes(b"MZ\0\1")
    (R / "app.bin").write_bytes(b"MZ\0\2")
    (L / "notes.txt").write_text("a\n")
    (R / "notes.txt").write_text("b\n")
    page = window.compare_paths(str(L), str(R))
    opened = []
    window.answers["find"] = {"PR7-HX": "PR7-HX.exe"}.get
    window.answers["launch_hx"] = lambda paths: opened.append(paths) or True
    page.select("app.bin")
    window._folder_menu(page, page.view.rect().center())
    act = next(a for a in window.last_menu.actions() if a.text() == "Open in PR7-HX")
    act.trigger()
    assert opened == [[str(L / "app.bin"), str(R / "app.bin")]]
    page.select("notes.txt")                                          # a text file: WM compares it itself
    window._folder_menu(page, page.view.rect().center())
    assert "Open in PR7-HX" not in [a.text() for a in window.last_menu.actions()]


def test_say_goes_through_say_even_with_an_answer(window):
    window.answers["say"] = lambda kind, text: window.heard.append((kind, text))
    window.heard = []
    window._ask("say", ("info", "hello"))
    assert window.heard == [("info", "hello")] and ("info", "hello") in window.said


def test_identical_files_say_so(window, tmp_path):
    a, b = pair(tmp_path, "same\n", "same\r\n")
    window.compare_files(a, b)
    assert ("info", "The selected files are identical.") in window.said


def test_changed_on_disk_reloads(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    with open(b, "w", newline="") as f:
        f.write(LEFT)
    window.answers["reload"] = True
    window.refresh()
    assert page.doc.identical()


def test_patch(window, tmp_path):
    a, b = pair(tmp_path)
    window.compare_files(a, b)
    target = tmp_path / "out.patch"
    window.answers["patch_file"] = lambda base: str(target)
    window.generate_patch()
    text = target.read_text()
    assert "-b = 2\n+b = 20\n" in text and "+new line\n" in text


def test_find_and_go_to(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    page.panes["right"].setFocus()
    page._last_side = "right"
    window.answers["find"] = "new"
    assert window.find()
    assert page.panes["right"].textCursor().selectedText() == "new"
    window.answers["goto"] = 5
    assert window.go_to() and page.panes["right"].textCursor().blockNumber() == 4


def test_drop_two_files(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.dropped([a, b])
    assert page is not None and window.tabs.count() == 1


def test_finish_switch(window, tmp_path):
    from pr7wm.panes import colours
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    window.set_finish("aurora")
    assert theme.FINISH == "aurora" and page.panes["left"].palette() is not None
    light = colours()["filler"]
    window.set_finish("obsidian")
    assert colours()["filler"] != light


# ------------------------------------------------------------------- folders
def folders_pair(tmp_path):
    L, R = tmp_path / "L", tmp_path / "R"
    for root, files in ((L, {"same.txt": "x\n", "diff.txt": "a\nb\n", "only_left.txt": "l"}),
                        (R, {"same.txt": "x\n", "diff.txt": "a\nB\n", "only_right.txt": "r"})):
        for rel, data in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)
    return str(L), str(R)


def test_folder_compare(window, tmp_path):
    L, R = folders_pair(tmp_path)
    page = window.compare_paths(L, R)
    assert page.kind == "folder"
    assert {it.rel: it.result for it in page.model.rows} == {"same.txt": "identical", "diff.txt": "different",
                                                             "only_left.txt": "left_only", "only_right.txt": "right_only"}
    assert window.status.text() == "4 items  ·  1 different  ·  1 left only  ·  1 right only  ·  1 identical"
    page.set_show("identical", False)
    assert "same.txt" not in [it.rel for it in page.model.rows]
    assert window.page_call("first") and page.selected()[0].group() != "identical"
    page.select("diff.txt")
    window.acts["current"].trigger()                                   # opens the file compare
    assert window.tabs.count() == 2 and window.page().kind == "file"
    assert window.page().doc.left.path == os.path.join(L, "diff.txt")


def test_folder_copy_and_delete(window, tmp_path):
    L, R = folders_pair(tmp_path)
    page = window.compare_paths(L, R)
    page.select("diff.txt")
    assert window.copy("right")
    assert open(os.path.join(R, "diff.txt")).read() == "a\nb\n"
    assert {it.rel: it.result for it in page.items}["diff.txt"] == "identical"   # compared again
    page.select("only_right.txt")
    window.acts["delete"].trigger()
    assert not os.path.exists(os.path.join(R, "only_right.txt"))
    assert os.path.exists(os.path.join(os.environ["PR7WM_TRASH"], "only_right.txt"))
    window.answers["confirm"] = False
    page.select("only_left.txt")
    assert not page.delete("left") and os.path.exists(os.path.join(L, "only_left.txt"))


def test_folder_menu_and_filter(window, tmp_path):
    L, R = folders_pair(tmp_path)
    page = window.compare_paths(L, R)
    page.select("only_left.txt")
    window._folder_menu(page, page.view.rect().center())
    names = [a.text() for a in window.last_menu.actions() if a.text()]
    assert names[:3] == ["Compare", "Copy to Right", "Copy to Left"]
    assert not next(a for a in window.last_menu.actions() if a.text() == "Copy to Left").isEnabled()
    page.filter_edit.setText("*.*;!only_*")
    page.refresh()
    assert sorted(it.rel for it in page.items) == ["diff.txt", "same.txt"]


def test_a_folder_and_a_file(window, tmp_path):
    L, R = folders_pair(tmp_path)
    page = window.compare_paths(L, os.path.join(R, "diff.txt"))     # the file of that name in the folder
    assert page.kind == "file" and page.doc.left.path == os.path.join(L, "diff.txt")


def test_view_panes(window, tmp_path):
    a, b = pair(tmp_path)
    page = window.compare_files(a, b)
    window.acts["diff_pane"].setChecked(True)
    window.toggle_pane("diff_pane")
    assert page.diff_box.isVisibleTo(page) and settings.get_bool("diff_pane")
    assert page.detail["left"].toPlainText() == "b = 2" and "DIFFERENCE 1 OF 2" in page.diff_title.text()
    window.acts["location_pane"].setChecked(False)
    window.toggle_pane("location_pane")
    assert not page.location.isVisibleTo(page)
    settings.set("diff_pane", False)
    settings.set("location_pane", True)


@pytest.mark.skipif(sys.platform == "win32", reason="elsewhere the Explorer menu can't be set")
def test_explorer_menu_is_windows_only(window):
    assert not window.acts["explorer_menu"].isEnabled()


def test_version():
    import pr7wm
    assert pr7wm.__version__.count(".") == 2
