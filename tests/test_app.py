import json
import os

from pr7wm import app, settings


def test_parse_winmerge_switches():
    o = app.parse(["/r", "/e", "/wl", "/dl", "Theirs", "-dr", "Mine", "/f", "*.py", "/u", "/home/a", "/home/b"])
    assert o["recursive"] and o["esc"] and o["wl"] and not o.get("wr")
    assert o["dl"] == "Theirs" and o["dr"] == "Mine" and o["filter"] == "*.py"
    assert o["paths"] == ["/home/a", "/home/b"]                  # a path starting with / isn't a switch
    assert app.parse(["C:\\x.txt", "C:\\y.txt"])["paths"] == ["C:\\x.txt", "C:\\y.txt"]


def files(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("one\n")
    b.write_text("two\n")
    return str(a), str(b)


def test_run_args(window, tmp_path):
    a, b = files(tmp_path)
    page = window.run_args(app.parse(["/wr", "/dl", "Theirs", a, b]))
    assert page.doc.right.read_only and page.doc.left.title == "Theirs" and window.esc_closes is False
    window.answers["open"] = lambda args: None
    seen = []
    window.answers["open"] = lambda args: seen.append(args)
    window.run_args(app.parse([a]))
    assert seen == [(a, "", False)]                                # one path: Select Files or Folders, left filled


def test_collect_two_items(window, tmp_path):
    a, b = files(tmp_path)
    window.collect(a)
    window.collect(b)
    page = window.flush_collected()
    assert page.doc.left.path == a and page.doc.right.path == b


def test_collect_one_then_another(window, tmp_path):
    a, b = files(tmp_path)
    window.collect(a)
    assert window.flush_collected() is None and settings.get("pending_left") == a
    assert "LEFT SIDE: a.txt" in window.welcome.text()
    window.collect(b)
    page = window.flush_collected()
    assert page.doc.left.path == a and page.doc.right.path == b and settings.get("pending_left") == ""


def test_hand_over_reaches_the_window(window, tmp_path, monkeypatch):
    from PySide6.QtCore import QCoreApplication
    a, b = files(tmp_path)
    monkeypatch.setattr(app, "server_name", lambda: "pr7wm-test-" + str(os.getpid()))
    assert app.listen(window) is not None
    import threading
    got = []
    t = threading.Thread(target=lambda: got.append(app.hand_over({"args": [a, b]})))
    t.start()
    import time
    deadline = time.monotonic() + 10           # the message is read on this (the GUI) thread: keep its events going
    while time.monotonic() < deadline and not (window.tabs.count() and not t.is_alive()):
        QCoreApplication.processEvents()
        t.join(0.01)
    assert got == [True] and window.page().doc.right.path == b
    window.instance_server.close()


def test_selftest(tmp_path):
    out = tmp_path / "out.json"
    assert app.selftest(str(out)) == 0
    r = json.loads(out.read_text())
    assert r["ok"] and r["merged"] == "a\r\nB\r\nc\r\n"
