"""The Recycle Bin (no Qt): Windows' SHFileOperationW with FOF_ALLOWUNDO, the call Explorer makes (PR7-E's), without
any prompt (deleting a compared file must not stop at a dialog). Elsewhere a
trash folder. PR7WM_TRASH points it at a folder: tests always set it, so they never touch the real Recycle Bin."""

from __future__ import annotations

import os
import shutil
import sys
import time


def _folder_send(path: str, root: str) -> None:
    os.makedirs(root, exist_ok=True)
    name = os.path.basename(path.rstrip("\\/"))
    dst = os.path.join(root, name)
    n = 2
    while os.path.lexists(dst):
        stem, ext = os.path.splitext(name)
        dst = os.path.join(root, f"{stem} ({n}){ext}")
        n += 1
    shutil.move(path, dst)


def send(path: str) -> None:
    path = os.path.abspath(path)
    env = os.environ.get("PR7WM_TRASH")
    if env:
        _folder_send(path, env)
        return
    if sys.platform != "win32":
        _folder_send(path, os.path.join(os.path.expanduser("~"), ".local", "share", "Trash", "files"))
        return
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, path + "\x00", None,
                         FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI, False, None, None)
    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    for _ in range(20):                       # the shell can return a moment before the file is gone
        if not os.path.lexists(path):
            return
        time.sleep(0.05)
    raise OSError(res or 5, "Windows couldn't move it to the Recycle Bin", path)
