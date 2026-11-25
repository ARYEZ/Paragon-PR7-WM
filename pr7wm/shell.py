"""The Explorer menu's "Compare in PR7-WM" (HKCU only): a registry verb on files (`*`) and folders. Explorer starts
one PR7-WM per selected item with `--collect "<path>"`; the running window gathers them (app.py): two items are
compared, one item becomes the left side for the next "Compare in PR7-WM" (WinMerge's Select Left / Compare to).

`base` is the Classes key under HKCU; tests on Windows CI pass a throwaway key so they never touch the real menu."""

from __future__ import annotations

import os
import sys

VERB = "PR7WM.Compare"
TEXT = "Compare in PR7-WM"
BASE = r"Software\Classes"
TARGETS = ("*", "Directory")


def exe_command() -> str:
    """How to start this PR7-WM: the installed .exe, or Python with the package when run from the sources."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m pr7wm'


def _icon() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.join(os.path.dirname(__file__), "icons", "app.ico")


def register(command: str, base: str = BASE) -> None:
    import winreg
    for target in TARGETS:
        key = rf"{base}\{target}\shell\{VERB}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, TEXT)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, _icon())
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, f'{command} --collect "%1"')
    _changed()


def unregister(base: str = BASE) -> None:
    import winreg
    for target in TARGETS:
        key = rf"{base}\{target}\shell\{VERB}"
        for sub in (key + r"\command", key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass
    _changed()


def menu_registered(base: str = BASE) -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{base}\*\shell\{VERB}\command"):
            return True
    except OSError:
        return False


def command_of(target: str = "*", base: str = BASE) -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{base}\{target}\shell\{VERB}\command") as k:
            return winreg.QueryValueEx(k, None)[0]
    except OSError:
        return None


def _changed() -> None:
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)     # SHCNE_ASSOCCHANGED
    except Exception:  # noqa: BLE001 - only a refresh
        pass
