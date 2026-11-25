"""Screenshots of the real PR7-WM window on generated files (made-up content):
QT_SCALE_FACTOR=2 python tools/screenshots.py OUT_DIR

files.png     a file compare with the location pane (OBSIDIAN)
folders.png   a folder compare (AURORA)
merge.png     a difference copied to the right, the Diff pane open (OBSIDIAN)
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["PR7WM_DATA"] = tempfile.mkdtemp()
os.environ["PARAGON_FAMILY_FILE"] = os.path.join(tempfile.mkdtemp(), "finish")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])

from pr7wm import settings, theme  # noqa: E402

theme.load_fonts()
app.setFont(QFont("Inter", 10))
from pr7wm.main_window import MainWindow  # noqa: E402

LEFT = '''"""Render settings for the ELSEWORLD master."""

WIDTH = 3840
HEIGHT = 2160
FPS = 23.976
CODEC = "prores_4444"


def output_name(take, version):
    return f"ELSEWORLD_t{take:02d}_v{version}.mov"


def bitrate(width, height):
    return width * height * 12


GRADE = "film_neutral"
LUT = "luts/elseworld_v3.cube"
'''

RIGHT = '''"""Render settings for the ELSEWORLD master."""

WIDTH = 3840
HEIGHT = 2160
FPS = 24
CODEC = "hevc_10bit"
AUDIO = "pcm_s24le"


def output_name(take, version):
    return f"ELSEWORLD_take{take:02d}_v{version:03d}.mov"


def bitrate(width, height):
    return width * height * 12


LUT = "luts/elseworld_v4.cube"
'''

base = Path(tempfile.mkdtemp()) / "Studio"
left, right = base / "ELSEWORLD", base / "Backup" / "ELSEWORLD"
files = {"tools/render_settings.py": (LEFT, RIGHT), "tools/export.py": ("def export():\n    pass\n",) * 2,
         "Projects/credits.txt": ("Directed by\nA. Person\n\nMusic\nB. Person\n", "Directed by\nA. Person\n\nMusic\n"
                                  "B. Person and C. Person\n\nThanks\n"),
         "Projects/ELSEWORLD_edit_v12.drp": (b"DRP\0\1\2\3" * 400, b"DRP\0\1\2\4" * 420),
         "Footage/A001_C0006.mov": (b"\0\0\0\x18ftypqt  " * 900, None),
         "Music/Last Light (stems).zip": (None, b"PK\3\4" * 1200),
         "notes_for_mix.md": ("# Notes\n\nKeep the score low under dialogue.\n",) * 2}
for rel, (a, b) in files.items():
    for root, data in ((left, a), (right, b)):
        if data is None:
            continue
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data.encode().replace(b"\n", b"\r\n") if isinstance(data, str) else data)


def shoot(w, name):
    w.show()
    for _ in range(5):
        app.processEvents()
    w.grab().save(str(out / name))


theme.set_finish("obsidian")
settings.set("finish", "obsidian")
w = MainWindow(sync=True)
w.answers.update({"say": lambda k, t: None, "confirm": True, "save_changes": "discard", "menu": True})
w.resize(1320, 820)
w.restyle()
page = w.compare_files(str(left / "tools/render_settings.py"), str(right / "tools/render_settings.py"))
w.compare_folders(str(left), str(right))
w.tabs.setCurrentIndex(0)
shoot(w, "files.png")

w.set_finish("aurora")
w.tabs.setCurrentIndex(1)
w.page().select("tools/render_settings.py")
shoot(w, "folders.png")

w.set_finish("obsidian")
w.tabs.setCurrentIndex(0)
w.acts["diff_pane"].setChecked(True)
w.toggle_pane("diff_pane")
page.first()
page.next()
page.next()
w.copy("right")
page.go(page.doc.counted[1], focus=False)
w._sync()
shoot(w, "merge.png")
w.close()
print("ok", out)
