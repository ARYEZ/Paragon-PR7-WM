"""Check a real install of PR7-WM-Setup.exe (CI, Windows): verify_install.py installed|uninstalled

`installed`: the files, the Start menu entry, the uninstall entry, "Compare in PR7-WM" in Explorer's menu (files and
folders) starting the installed exe, and the installed exe's --selftest: real folders compared, a difference merged
and saved byte for byte. `uninstalled`: all of it gone, the Explorer menu entry too."""
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

HKCU = winreg.HKEY_CURRENT_USER
APP = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PR7-WM"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Paragon PR7-WM.lnk"
UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{2E52DD0D-51E7-40B7-B5C4-F0EDC2C9E8B9}_is1"
MENU = r"Software\Classes\{}\shell\PR7WM.Compare"


def value(root, path, name=""):
    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def check(ok, what, p):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        p.append(what)


def installed():
    p = []
    exe = APP / "PR7-WM.exe"
    for f in (exe, APP / "unins000.exe", APP / "_internal" / "pr7wm" / "fonts" / "Inter-Regular.ttf"):
        check(f.is_file(), f"file {f}", p)
    check(SHORTCUT.is_file(), "Start menu shortcut", p)
    check(value(HKCU, UNINSTALL, "DisplayName") == "Paragon PR7-WM", "Installed apps entry", p)
    for target in ("*", "Directory"):
        cmd = value(HKCU, MENU.format(target) + r"\command") or ""
        check(str(exe).lower() in cmd.lower() and cmd.endswith('--collect "%1"'),
              f"Explorer menu on {target} starts the installed exe ({cmd})", p)
        check(value(HKCU, MENU.format(target)) == "Compare in PR7-WM", f"Explorer menu text on {target}", p)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.json"
        try:
            subprocess.run([str(exe), "--selftest", str(out)], timeout=600, check=False)
        except subprocess.TimeoutExpired:
            pass
        got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        check(got.get("ok") is True and got.get("fonts") is True,
              f"the installed exe compares folders, merges and saves ({got})", p)
    return p


def uninstalled():
    deadline = time.time() + 60
    while True:
        p = []
        check(not (APP / "PR7-WM.exe").exists(), "program files removed", p)
        check(not SHORTCUT.exists(), "Start menu shortcut removed", p)
        check(value(HKCU, UNINSTALL, "DisplayName") is None, "Installed apps entry removed", p)
        for target in ("*", "Directory"):
            check(value(HKCU, MENU.format(target) + r"\command") is None, f"Explorer menu on {target} removed", p)
        if not p or time.time() > deadline:
            return p
        print("... waiting for the uninstaller to finish")
        time.sleep(3)


if __name__ == "__main__":
    problems = {"installed": installed, "uninstalled": uninstalled}[sys.argv[1]]()
    print("\nALL OK" if not problems else f"\n{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
