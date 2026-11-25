"""Start PR7-WM. The command line is WinMerge's:

    PR7-WM.exe [/r] [/e] [/wl] [/wr] [/dl DESC] [/dr DESC] [/f FILTER] LEFT [RIGHT]
        /r  include subfolders          /e  Esc closes the window       /wl /wr  the left / right side read-only
        /dl /dr  a description shown instead of the left / right path  /f  the folder compare's filter
        (switches start with / or -; /u /x /s are accepted and ignored)
    PR7-WM.exe --collect PATH        one item from the Explorer menu (the running window gathers them)
    PR7-WM.exe --register-menu       add "Compare in PR7-WM" to Explorer's menu (HKCU); --unregister removes it
    PR7-WM.exe --version
    PR7-WM.exe --selftest OUT.json   compare, merge and save real files and folders offscreen (CI runs the installed exe)

One window per user: a later start hands its command line to the running window, which opens it in a new tab.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys
import tempfile

TIMEOUT_MS = 1500
FLAGS = {"r": "recursive", "e": "esc", "wl": "wl", "wr": "wr", "u": None, "x": None, "s": None, "ub": None}
VALUES = {"dl": "dl", "dr": "dr", "f": "filter"}


def parse(argv: list[str]) -> dict:
    o: dict = {"paths": [], "recursive": None, "filter": None}
    it = iter(argv)
    for a in it:
        name = a[1:].lower() if a[:1] in "/-" and len(a) > 1 else ""
        if name in VALUES:
            o[VALUES[name]] = next(it, "")
        elif name in FLAGS:
            if FLAGS[name]:
                o[FLAGS[name]] = True
        else:
            o["paths"].append(a)
    return o


def server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "Paragon-PR7-WM-" + hashlib.sha1(user.encode()).hexdigest()[:12]


def hand_over(message: dict, wait_ms: int = 0) -> bool:
    """Give a message to the running window. With wait_ms, keep trying that long (it may still be starting)."""
    from PySide6.QtCore import QElapsedTimer, QThread
    from PySide6.QtNetwork import QLocalSocket
    clock = QElapsedTimer()
    clock.start()
    while True:
        s = QLocalSocket()
        s.connectToServer(server_name())
        if s.waitForConnected(TIMEOUT_MS):
            s.write(json.dumps(message).encode() + b"\n")
            s.flush()
            s.waitForBytesWritten(TIMEOUT_MS)
            if not s.waitForDisconnected(TIMEOUT_MS):
                s.disconnectFromServer()
            return True
        if clock.elapsed() >= wait_ms:
            return False
        QThread.msleep(100)


def listen(window):
    """Later starts hand their command line over (PR7-R's hand-off, with its Windows fix: data that's already
    waiting when the connection is accepted is read at once)."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    QLocalServer.removeServer(server_name())
    if not server.listen(server_name()):
        return None

    def connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()

        def read():
            buf.extend(bytes(sock.readAll()))
            if b"\n" not in buf:
                return
            try:
                msg = json.loads(bytes(buf).split(b"\n", 1)[0])
            except ValueError:
                msg = {}
            sock.disconnectFromServer()
            receive(window, msg)
        sock.readyRead.connect(read)
        if sock.bytesAvailable():
            read()
    server.newConnection.connect(connection)
    window.instance_server = server
    return server


def receive(window, msg: dict):
    window.showNormal()
    window.raise_()
    window.activateWindow()
    if msg.get("collect"):
        window.collect(msg["collect"])
    elif msg.get("args") is not None:
        window.run_args(parse(msg["args"]))


def selftest(out: str) -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["PR7WM_DATA"] = tempfile.mkdtemp()
    os.environ["PR7WM_TRASH"] = tempfile.mkdtemp()
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    app = QApplication.instance() or QApplication(sys.argv[:1])
    result: dict = {}
    try:
        from . import __version__, theme
        from .main_window import MainWindow
        theme.load_fonts()
        d = tempfile.mkdtemp()
        L, R = os.path.join(d, "left"), os.path.join(d, "right")
        os.makedirs(os.path.join(L, "sub"))
        os.makedirs(os.path.join(R, "sub"))
        files = {"same.txt": ("one\r\n", "one\r\n"), "notes.txt": ("a\r\nb\r\nc\r\n", "a\r\nB\r\nc\r\nd\r\n"),
                 "sub/data.bin": (b"\0\1\2", b"\0\1\3"), "only_left.txt": ("l", None)}
        for rel, (a, b) in files.items():
            for root, data in ((L, a), (R, b)):
                if data is not None:
                    with open(os.path.join(root, *rel.split("/")), "wb") as f:
                        f.write(data.encode() if isinstance(data, str) else data)
        w = MainWindow(sync=True)
        w.answers.update({"say": lambda k, t: None, "confirm": True, "save_changes": "discard", "menu": True,
                          "reload": True})
        w.show()
        folder = w.compare_paths(L, R)
        results = {it.rel: it.result for it in folder.items}
        page = w.compare_paths(os.path.join(L, "notes.txt"), os.path.join(R, "notes.txt"))
        diffs = len(page.doc.counted)
        page.first()
        w.copy("left")                      # B to the left
        w.save()
        with open(os.path.join(L, "notes.txt"), "rb") as f:
            merged = f.read()
        result = {"version": __version__, "folder": results, "differences": diffs,
                  "merged": merged.decode("latin-1"), "fonts": "Inter" in QFontDatabase.families()}
        result["ok"] = (results.get("notes.txt") == "different" and results.get("same.txt") == "identical"
                        and results.get("sub/data.bin") == "binary_different"
                        and results.get("only_left.txt") == "left_only" and diffs == 2
                        and merged == b"a\r\nB\r\nc\r\n")
        w.close()
    except Exception as e:  # noqa: BLE001 - reported in the output
        import traceback
        result = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    app.clipboard().clear()
    return 0 if result.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not argv[0].startswith("--"):
        return _window(argv)
    if argv[0] == "--collect":
        return _window([], collect=argv[1] if len(argv) > 1 else "")
    # a command-line mode (CI): an unexpected error must end the process with a code; in the windowed exe it would
    # otherwise open an error box that waits for a click nobody gives
    try:
        return _command(argv)
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - reported, then a failing exit code
        import traceback
        if sys.stderr is not None:
            sys.stderr.write(traceback.format_exc())
        return 2


def _command(argv: list[str]) -> int:
    if argv[:1] == ["--version"]:
        from . import __version__
        print(__version__)
        return 0
    if argv[:1] == ["--selftest"] and len(argv) == 2:
        return selftest(argv[1])
    if argv[:1] == ["--register-menu"]:
        from . import shell
        shell.register(shell.exe_command())
        return 0
    if argv[:1] in (["--unregister"], ["--unregister-menu"]):
        from . import shell
        shell.unregister()
        return 0
    print(__doc__)
    return 1


def _lock():
    """The first PR7-WM of this user holds this lock while it starts the window; later ones hand over to it (Explorer
    starts several at once for a multiple selection)."""
    from PySide6.QtCore import QLockFile
    lock = QLockFile(os.path.join(tempfile.gettempdir(), server_name() + ".lock"))
    lock.setStaleLockTime(0)
    return lock


def _window(argv: list[str], collect: str | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from . import settings, theme
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Paragon")
    app.setApplicationName("PR7-WM")
    message = {"collect": collect} if collect is not None else {"args": argv}
    lock = _lock()
    if not lock.tryLock(0):
        # another PR7-WM has the window (or is starting it): give it this command line
        if hand_over(message, wait_ms=8000):
            return 0
        lock.removeStaleLockFile()
        lock.tryLock(0)
    elif hand_over(message):                   # a window from before the lock (an older start)
        return 0
    from . import finish
    theme.set_finish(finish.start(settings.get("finish", "obsidian")))
    theme.load_fonts()
    app.setPalette(theme.palette())
    from PySide6.QtGui import QIcon
    icon = os.path.join(os.path.dirname(__file__), "icons", "app.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    from .main_window import MainWindow
    w = MainWindow()
    from PySide6.QtCore import QTimer
    _follow = QTimer(w)                      # one finish for the family: follow another app's switch (finish.py)
    _follow.timeout.connect(lambda: finish.follow(theme.FINISH, w.set_finish))
    _follow.start(2000)
    listen(w)
    w.show()
    if collect is not None:
        QTimer.singleShot(0, lambda: w.collect(collect))
    else:
        QTimer.singleShot(0, lambda: w.run_args(parse(argv)))
    from . import update_ui
    update_ui.start(w)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
