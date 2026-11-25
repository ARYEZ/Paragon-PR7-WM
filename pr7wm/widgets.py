"""Custom-painted Paragon widgets: the PR7-WM mark, the header, compact piano-black keys and line icons."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient, QRegion, QTransform)
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QWidget

from . import theme

# --------------------------------------------------------------------------- the PR7-WM mark
# Same construction as the PR7 plugins' Logo.cpp: letters designed 1 unit tall, upright,
# stems 0.24 wide, bars 0.2 tall, then slanted 0.3; two horizontal "speed cuts".
SLANT = 0.3
SPACING = 0.1
CUTS = [(0.63, 0.68), (0.79, 0.83)]


def _poly(path: QPainterPath, pts, x: float) -> None:
    path.moveTo(pts[0][0] + x, pts[0][1])
    for px, py in pts[1:]:
        path.lineTo(px + x, py)
    path.closeSubpath()


# The letters after PR7-: W and M, drawn like the PR7 letters (0.24 stems, 0.2 bars, P-bowl chamfers).
W_OUTER = [(0, 0), (0.24, 0), (0.31, 0.58), (0.4, 0.22), (0.6, 0.22), (0.69, 0.58), (0.76, 0), (1, 0), (0.83, 1), (0.6, 1), (0.5, 0.62), (0.4, 1), (0.17, 1)]
W_HOLES = []
M_OUTER = [(0, 1), (0, 0), (0.24, 0), (0.5, 0.42), (0.76, 0), (1, 0), (1, 1), (0.76, 1), (0.76, 0.42), (0.5, 0.8), (0.24, 0.42), (0.24, 1)]
M_HOLES = []
WIDTHS = [0.8, 0.84, 0.8, 0.4, 1.0, 1.0]  # P, R, 7, dash, W, M
TOTAL_WIDTH = sum(WIDTHS) + (len(WIDTHS) - 1) * SPACING + SLANT
SEVEN_SHAPE = [(0, 0), (.8, 0), (.8, .2), (.44, 1), (.18, 1), (.5, .2), (0, .2)]


def _lean() -> QTransform:
    return QTransform(1, 0, -SLANT, 1, SLANT, 0)  # x' = x + slant*(1 - y): y is down, the top leans right


def _letters() -> tuple[QPainterPath, QPainterPath]:
    """(P, R, dash, W, M) and the 7, in letter units with y down, slanted."""
    main, seven = QPainterPath(), QPainterPath()
    main.setFillRule(Qt.OddEvenFill)  # bowl counters are holes
    bowl = [(0, 0), (.64, 0), (.8, .15), (.8, .45), (.64, .6), (.24, .6), (.24, 1), (0, 1)]
    counter = [(.24, .2), (.56, .2), (.56, .4), (.24, .4)]
    x = 0.0
    _poly(main, bowl, x); _poly(main, counter, x)
    x += WIDTHS[0] + SPACING
    _poly(main, bowl, x); _poly(main, counter, x)
    _poly(main, [(.4, .6), (.64, .6), (.84, 1), (.6, 1)], x)  # R's leg
    x += WIDTHS[1] + SPACING
    _poly(seven, [(0, 0), (.8, 0), (.8, .2), (.44, 1), (.18, 1), (.5, .2), (0, .2)], x)
    x += WIDTHS[2] + SPACING
    _poly(main, [(0, .42), (.4, .42), (.4, .6), (0, .6)], x)  # dash, clear of the cuts
    x += WIDTHS[3] + SPACING
    _poly(main, W_OUTER, x)
    for hole in W_HOLES:
        _poly(main, hole, x)
    x += WIDTHS[4] + SPACING
    _poly(main, M_OUTER, x)
    for hole in M_HOLES:
        _poly(main, hole, x)
    # Lean forward: the top moves right, the baseline stays.
    lean = QTransform(1, 0, -SLANT, 1, SLANT, 0)  # x' = x + slant*(1 - y): y is down, so the top leans right
    return lean.map(main), lean.map(seven)


_MAIN, _SEVEN = _letters()


def draw_mark(p: QPainter, area: QRectF, glow: bool = True) -> QRectF:
    h = min(area.height(), area.width() / TOTAL_WIDTH)
    bounds = QRectF(area.x(), area.center().y() - h / 2, TOTAL_WIDTH * h, h)
    place = QTransform().translate(bounds.x(), bounds.y()).scale(h, h)
    main, seven = place.map(_MAIN), place.map(_SEVEN)
    sev_grad = theme.family_gradient(bounds.x(), 0, bounds.right(), 0)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if glow:  # a soft neon halo behind the 7
        for ring in (3, 2, 1):
            c = QColor(theme.GLOW); c.setAlphaF(0.1 * (4 - ring))
            p.setPen(QPen(c, h * 0.07 * ring, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(seven)
    clip = QRegion(bounds.adjusted(-h, -h, h, h).toAlignedRect())
    for top, bottom in CUTS:
        clip -= QRegion(QRectF(bounds.x() - h, bounds.y() + h * top, bounds.width() + 2 * h,
                               h * (bottom - top)).toAlignedRect())
    p.setClipRegion(clip)
    p.setPen(Qt.NoPen)
    p.fillPath(main, QColor(theme.TEXT))
    p.fillPath(seven, sev_grad)
    p.restore()
    return bounds


class Header(QWidget):
    """64 px family header: PARAGON and the PR7-WM mark, a subtitle; the current finish on the right."""

    def __init__(self, subtitle: str = "COMPARE", parent=None):
        super().__init__(parent)
        self.subtitle = subtitle
        self.setFixedHeight(64)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        p.fillRect(r, QColor(theme.BACKGROUND))
        glow = QRadialGradient(QPointF(170, 0), 420)
        c = QColor(theme.GLOW); c.setAlphaF(0.07)
        glow.setColorAt(0, c); glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(r, glow)
        f = QFont("Inter", 1); f.setPixelSize(21)
        p.setFont(f); p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(22, 0, 200, r.height()), Qt.AlignVCenter | Qt.AlignLeft, "PARAGON")
        mark = draw_mark(p, QRectF(140, 19, 200, 26))
        f2 = QFont("Inter", 1); f2.setPixelSize(12); f2.setWeight(QFont.DemiBold)
        p.setFont(f2); p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QRectF(mark.right() + 16, 0, 300, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.subtitle)
        p.drawText(QRectF(0, 0, r.width() - 22, r.height()), Qt.AlignVCenter | Qt.AlignRight, theme.FINISH.upper())
        p.setPen(QPen(QColor(theme.PANEL_EDGE), 1))
        p.drawLine(0, r.height() - 1, r.width(), r.height() - 1)




# --------------------------------------------------------------------------- line icons (24x24)
def _folder(p: QPainterPath, dx: float = 0, dy: float = 0, k: float = 1.0) -> None:
    pts = [(2.5, 6), (9, 6), (11, 8.5), (21.5, 8.5), (21.5, 19.5), (2.5, 19.5)]
    p.moveTo(dx + pts[0][0] * k, dy + pts[0][1] * k)
    for x, y in pts[1:]:
        p.lineTo(dx + x * k, dy + y * k)
    p.closeSubpath()


def _icon_path(name: str) -> QPainterPath:
    """GNOME Files' symbolic icons, redrawn as family line icons on a 24-unit grid."""
    p = QPainterPath()
    if name == "back":
        p.moveTo(14.5, 5.5); p.lineTo(8, 12); p.lineTo(14.5, 18.5)
    elif name == "forward":
        p.moveTo(9.5, 5.5); p.lineTo(16, 12); p.lineTo(9.5, 18.5)
    elif name == "search":
        p.addEllipse(QRectF(3.5, 3.5, 12, 12)); p.moveTo(14, 14); p.lineTo(20.5, 20.5)
    elif name == "grid":
        for x in (4, 13.5):
            for y in (4, 13.5):
                p.addRoundedRect(QRectF(x, y, 6.5, 6.5), 1.5, 1.5)
    elif name == "list":
        for y in (6, 12, 18):
            p.addEllipse(QRectF(3.5, y - 1, 2, 2)); p.moveTo(8.5, y); p.lineTo(20.5, y)
    elif name == "menu":
        for y in (6.5, 12, 17.5):
            p.moveTo(4.5, y); p.lineTo(19.5, y)
    elif name == "more":           # the vertical "..." of the path bar's folder menu
        for y in (6, 12, 18):
            p.addEllipse(QRectF(11, y - 1, 2, 2))
    elif name == "sidebar":
        p.addRoundedRect(QRectF(3, 4.5, 18, 15), 2, 2); p.moveTo(9, 4.5); p.lineTo(9, 19.5)
    elif name == "newtab":
        p.addRoundedRect(QRectF(3.5, 5, 17, 14), 2, 2); p.moveTo(12, 8.5); p.lineTo(12, 15.5)
        p.moveTo(8.5, 12); p.lineTo(15.5, 12)
    elif name == "close":
        p.moveTo(7, 7); p.lineTo(17, 17); p.moveTo(17, 7); p.lineTo(7, 17)
    elif name == "recent":         # a clock
        p.addEllipse(QRectF(3.5, 3.5, 17, 17)); p.moveTo(12, 7); p.lineTo(12, 12); p.lineTo(15.5, 14)
    elif name == "star":
        import math
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = 9 if i % 2 == 0 else 3.9
            pts.append((12 + r * math.cos(a), 12.6 + r * math.sin(a)))
        p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        p.closeSubpath()
    elif name == "home":
        p.moveTo(3.5, 11.5); p.lineTo(12, 4); p.lineTo(20.5, 11.5)
        p.moveTo(6, 9.5); p.lineTo(6, 20); p.lineTo(10, 20); p.lineTo(10, 14.5); p.lineTo(14, 14.5)
        p.lineTo(14, 20); p.lineTo(18, 20); p.lineTo(18, 9.5)
    elif name == "desktop":
        p.addRoundedRect(QRectF(3, 4, 18, 12), 1.5, 1.5); p.moveTo(12, 16); p.lineTo(12, 20)
        p.moveTo(8, 20); p.lineTo(16, 20)
    elif name == "documents":
        p.moveTo(5, 2.5); p.lineTo(14, 2.5); p.lineTo(19, 7.5); p.lineTo(19, 21.5); p.lineTo(5, 21.5)
        p.closeSubpath(); p.moveTo(14, 2.5); p.lineTo(14, 7.5); p.lineTo(19, 7.5)
        for y in (11.5, 14.5, 17.5):
            p.moveTo(8, y); p.lineTo(16, y)
    elif name == "downloads":
        p.moveTo(12, 3.5); p.lineTo(12, 15); p.moveTo(7, 10); p.lineTo(12, 15); p.lineTo(17, 10)
        p.moveTo(4, 20); p.lineTo(20, 20)
    elif name == "music":
        p.addEllipse(QRectF(3.5, 14.5, 6, 5)); p.addEllipse(QRectF(13.5, 12.5, 6, 5))
        p.moveTo(9.5, 17); p.lineTo(9.5, 5.5); p.lineTo(19.5, 3.5); p.lineTo(19.5, 15)
        p.moveTo(9.5, 9); p.lineTo(19.5, 7)
    elif name == "pictures":
        p.addRoundedRect(QRectF(3, 4.5, 18, 15), 2, 2); p.addEllipse(QRectF(6.5, 7.5, 3.5, 3.5))
        p.moveTo(3.5, 17.5); p.lineTo(9, 12.5); p.lineTo(13, 16); p.lineTo(16, 13); p.lineTo(20.5, 17)
    elif name == "videos":
        p.addRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
        p.moveTo(10, 9); p.lineTo(15.5, 12); p.lineTo(10, 15); p.closeSubpath()
    elif name == "trash":
        p.moveTo(4, 6.5); p.lineTo(20, 6.5); p.moveTo(9.5, 6.5); p.lineTo(9.5, 4); p.lineTo(14.5, 4)
        p.lineTo(14.5, 6.5); p.moveTo(6, 6.5); p.lineTo(7, 20.5); p.lineTo(17, 20.5); p.lineTo(18, 6.5)
        p.moveTo(10, 10); p.lineTo(10, 17); p.moveTo(14, 10); p.lineTo(14, 17)
    elif name == "drive":
        p.addRoundedRect(QRectF(3, 7, 18, 10), 2, 2); p.addEllipse(QRectF(16, 11, 2, 2))
    elif name == "usb":
        p.addRoundedRect(QRectF(7, 9, 10, 12), 2, 2); p.addRect(QRectF(9, 3.5, 6, 5.5))
        p.moveTo(11, 5.5); p.lineTo(11, 7); p.moveTo(13, 5.5); p.lineTo(13, 7)
    elif name == "eject":
        p.moveTo(12, 5); p.lineTo(18.5, 13); p.lineTo(5.5, 13); p.closeSubpath()
        p.moveTo(5.5, 18); p.lineTo(18.5, 18)
    elif name == "server":         # a connected server
        p.addRoundedRect(QRectF(4, 3, 16, 7.5), 1.5, 1.5)
        p.addRoundedRect(QRectF(4, 13.5, 16, 7.5), 1.5, 1.5)
        p.addEllipse(QRectF(15.5, 6, 1.6, 1.6))
        p.addEllipse(QRectF(15.5, 16.5, 1.6, 1.6))
    elif name == "share":          # a Windows network share: a folder on a network line
        _folder(p, 0, -2.5)
        p.moveTo(12, 17); p.lineTo(12, 21); p.moveTo(5, 21); p.lineTo(19, 21)
    elif name == "network":        # Other Locations
        p.addEllipse(QRectF(3.5, 3.5, 17, 17)); p.moveTo(3.5, 12); p.lineTo(20.5, 12)
        p.addEllipse(QRectF(8, 3.5, 8, 17))
    elif name in ("folder", "bookmark"):
        _folder(p)
    elif name == "file":
        p.moveTo(5, 2.5); p.lineTo(14, 2.5); p.lineTo(19, 7.5); p.lineTo(19, 21.5); p.lineTo(5, 21.5)
        p.closeSubpath(); p.moveTo(14, 2.5); p.lineTo(14, 7.5); p.lineTo(19, 7.5)
    elif name == "archive":        # a page with a zip
        p.moveTo(5, 2.5); p.lineTo(14, 2.5); p.lineTo(19, 7.5); p.lineTo(19, 21.5); p.lineTo(5, 21.5)
        p.closeSubpath()
        for y in (4.5, 7.5, 10.5):
            p.moveTo(10, y); p.lineTo(12, y); p.moveTo(12, y + 1.5); p.lineTo(14, y + 1.5)
        p.addRoundedRect(QRectF(10, 13.5, 4, 4), 1, 1)
    elif name == "operations":     # a pie: the copy/move progress key
        p.addEllipse(QRectF(4, 4, 16, 16))
    elif name == "copy":
        p.addRoundedRect(QRectF(8, 8, 12, 13), 2, 2)
        p.moveTo(5, 16); p.lineTo(4, 16); p.lineTo(4, 3); p.lineTo(16, 3); p.lineTo(16, 5)
    elif name == "undo":
        p.moveTo(8.5, 5); p.lineTo(4.5, 9); p.lineTo(8.5, 13)
        p.moveTo(4.5, 9); p.lineTo(14, 9); p.cubicTo(22, 9, 22, 20, 14, 20); p.lineTo(8, 20)
    elif name == "open":           # an open folder
        p.moveTo(2.5, 19.5); p.lineTo(2.5, 5); p.lineTo(9, 5); p.lineTo(11, 7.5); p.lineTo(19, 7.5); p.lineTo(19, 10)
        p.moveTo(2.5, 19.5); p.lineTo(6, 10); p.lineTo(22, 10); p.lineTo(18.5, 19.5); p.closeSubpath()
    elif name == "print":
        p.addRect(QRectF(7, 3, 10, 5)); p.addRoundedRect(QRectF(3, 8, 18, 9), 2, 2); p.addRect(QRectF(7, 14, 10, 7))
    elif name == "prev":           # page up
        p.moveTo(6, 15); p.lineTo(12, 9); p.lineTo(18, 15)
    elif name == "next":
        p.moveTo(6, 9); p.lineTo(12, 15); p.lineTo(18, 9)
    elif name == "zoomin":
        p.addEllipse(QRectF(3.5, 3.5, 12, 12)); p.moveTo(14, 14); p.lineTo(20.5, 20.5)
        p.moveTo(6.5, 9.5); p.lineTo(12.5, 9.5); p.moveTo(9.5, 6.5); p.lineTo(9.5, 12.5)
    elif name == "zoomout":
        p.addEllipse(QRectF(3.5, 3.5, 12, 12)); p.moveTo(14, 14); p.lineTo(20.5, 20.5)
        p.moveTo(6.5, 9.5); p.lineTo(12.5, 9.5)
    elif name == "fitpage":        # one whole page
        p.addRoundedRect(QRectF(6.5, 3, 11, 18), 1.5, 1.5)
    elif name == "fitwidth":       # a page with arrows to its sides
        p.addRoundedRect(QRectF(7, 4, 10, 16), 1.5, 1.5)
        p.moveTo(2, 12); p.lineTo(5, 12); p.moveTo(3.5, 10.5); p.lineTo(2, 12); p.lineTo(3.5, 13.5)
        p.moveTo(22, 12); p.lineTo(19, 12); p.moveTo(20.5, 10.5); p.lineTo(22, 12); p.lineTo(20.5, 13.5)
    elif name == "facing":         # two pages side by side
        p.addRoundedRect(QRectF(2.5, 5, 9, 14), 1.5, 1.5); p.addRoundedRect(QRectF(12.5, 5, 9, 14), 1.5, 1.5)
    elif name == "rotate":
        p.moveTo(18.5, 4.5); p.lineTo(18.5, 9); p.lineTo(14, 9)
        p.moveTo(18.5, 9); p.cubicTo(16, 4, 7, 3.5, 5, 10); p.cubicTo(3.5, 16, 9, 21, 14.5, 19.5)
    elif name == "bookmarks":
        p.moveTo(7, 3); p.lineTo(17, 3); p.lineTo(17, 21); p.lineTo(12, 16.5); p.lineTo(7, 21); p.closeSubpath()
    elif name == "case":           # "Aa": Find's Match case
        p.moveTo(2.5, 19); p.lineTo(7.5, 5); p.lineTo(12.5, 19); p.moveTo(4.4, 14); p.lineTo(10.6, 14)
        p.addEllipse(QRectF(14, 12.5, 6, 6.5)); p.moveTo(20, 12); p.lineTo(20, 19)
    elif name == "pause":
        p.addRoundedRect(QRectF(6.5, 5, 4, 14), 1, 1); p.addRoundedRect(QRectF(13.5, 5, 4, 14), 1, 1)
    elif name == "stop":
        p.addRoundedRect(QRectF(6, 6, 12, 12), 1.5, 1.5)
    elif name == "skipback":       # |<
        p.moveTo(6, 5.5); p.lineTo(6, 18.5); p.moveTo(18, 5.5); p.lineTo(9.5, 12); p.lineTo(18, 18.5); p.closeSubpath()
    elif name == "skipnext":       # >|
        p.moveTo(18, 5.5); p.lineTo(18, 18.5); p.moveTo(6, 5.5); p.lineTo(14.5, 12); p.lineTo(6, 18.5); p.closeSubpath()
    elif name == "framestep":      # >|| one frame on
        p.moveTo(4.5, 6); p.lineTo(12, 12); p.lineTo(4.5, 18); p.closeSubpath()
        p.moveTo(15, 6); p.lineTo(15, 18); p.moveTo(19, 6); p.lineTo(19, 18)
    elif name == "volume":
        p.moveTo(3.5, 9.5); p.lineTo(7.5, 9.5); p.lineTo(12, 5); p.lineTo(12, 19); p.lineTo(7.5, 14.5); p.lineTo(3.5, 14.5)
        p.closeSubpath(); p.moveTo(15.5, 9); p.cubicTo(17.5, 10.5, 17.5, 13.5, 15.5, 15)
        p.moveTo(18, 6.5); p.cubicTo(21.5, 9.5, 21.5, 14.5, 18, 17.5)
    elif name == "mute":
        p.moveTo(3.5, 9.5); p.lineTo(7.5, 9.5); p.lineTo(12, 5); p.lineTo(12, 19); p.lineTo(7.5, 14.5); p.lineTo(3.5, 14.5)
        p.closeSubpath(); p.moveTo(15.5, 9.5); p.lineTo(20.5, 14.5); p.moveTo(20.5, 9.5); p.lineTo(15.5, 14.5)
    elif name == "playlist":
        for y in (6, 11, 16):
            p.moveTo(3.5, y); p.lineTo(14, y)
        p.moveTo(16.5, 13); p.lineTo(21, 16.5); p.lineTo(16.5, 20); p.closeSubpath()
    elif name == "subtitles":
        p.addRoundedRect(QRectF(2.5, 5, 19, 14), 2.5, 2.5)
        p.moveTo(6, 13); p.lineTo(11, 13); p.moveTo(13, 13); p.lineTo(18, 13); p.moveTo(6, 16); p.lineTo(15, 16)
    elif name == "audiotrack":     # a note
        p.addEllipse(QRectF(4.5, 14.5, 5, 4.5)); p.addEllipse(QRectF(13.5, 12.5, 5, 4.5))
        p.moveTo(9.5, 16.5); p.lineTo(9.5, 5.5); p.lineTo(18.5, 3.5); p.lineTo(18.5, 14.5)
    elif name == "region":         # a dashed frame with a corner handle
        for (x1, y1, x2, y2) in ((3, 4, 9, 4), (12, 4, 18, 4), (21, 4, 21, 10), (21, 13, 21, 19), (3, 7, 3, 13),
                                 (3, 16, 3, 20), (6, 20, 12, 20)):
            p.moveTo(x1, y1); p.lineTo(x2, y2)
        p.addRect(QRectF(15.5, 17.5, 5, 5))
    elif name == "window":
        p.addRoundedRect(QRectF(3, 4.5, 18, 15), 2, 2); p.moveTo(3, 8.5); p.lineTo(21, 8.5)
    elif name == "screen":
        p.addRoundedRect(QRectF(2.5, 4, 19, 12.5), 1.5, 1.5); p.moveTo(9, 20); p.lineTo(15, 20); p.moveTo(12, 16.5); p.lineTo(12, 20)
    elif name == "clipboard":
        p.addRoundedRect(QRectF(5, 4.5, 14, 17), 2, 2); p.addRoundedRect(QRectF(9, 2.5, 6, 4), 1, 1)
    elif name == "select":         # a pointer
        p.moveTo(6, 3.5); p.lineTo(6, 19); p.lineTo(10, 15); p.lineTo(13, 21); p.lineTo(15.5, 20); p.lineTo(12.5, 14)
        p.lineTo(18, 14); p.closeSubpath()
    elif name == "rect":
        p.addRect(QRectF(4, 6, 16, 12))
    elif name == "refresh":        # PR7-SM
        p.moveTo(19.5, 12); p.arcTo(QRectF(4.5, 4.5, 15, 15), 0, 300); p.moveTo(19.5, 5.5); p.lineTo(19.5, 11)
        p.lineTo(14, 11)
    elif name == "chart":
        p.moveTo(3.5, 20.5); p.lineTo(20.5, 20.5); p.moveTo(4, 16); p.lineTo(9, 10); p.lineTo(13, 13.5); p.lineTo(20, 5)
    elif name == "app":            # a program: a window with its title bar
        p.addRoundedRect(QRectF(3.5, 5, 17, 14), 2, 2); p.moveTo(3.5, 9); p.lineTo(20.5, 9)
    elif name == "lock":           # PR7-PM: lock the database
        p.addRoundedRect(QRectF(5, 10.5, 14, 10), 2, 2); p.moveTo(8, 10.5); p.lineTo(8, 7.5)
        p.cubicTo(8, 2.5, 16, 2.5, 16, 7.5); p.lineTo(16, 10.5); p.moveTo(12, 14.5); p.lineTo(12, 16.5)
    elif name == "key":
        p.addEllipse(QRectF(3, 8, 8, 8)); p.moveTo(11, 12); p.lineTo(21, 12); p.moveTo(17, 12); p.lineTo(17, 15.5)
        p.moveTo(20, 12); p.lineTo(20, 15)
    elif name == "user":
        p.addEllipse(QRectF(8, 3.5, 8, 8)); p.moveTo(4.5, 20.5); p.cubicTo(5, 13, 19, 13, 19.5, 20.5)
    elif name == "link":
        p.addEllipse(QRectF(3.5, 3.5, 17, 17)); p.moveTo(3.5, 12); p.lineTo(20.5, 12)
        p.addEllipse(QRectF(8.5, 3.5, 7, 17))
    elif name == "add":
        p.moveTo(12, 4.5); p.lineTo(12, 19.5); p.moveTo(4.5, 12); p.lineTo(19.5, 12)
    elif name == "edit":
        p.moveTo(4.5, 19.5); p.lineTo(5.5, 15); p.lineTo(16, 4.5); p.lineTo(19.5, 8); p.lineTo(9, 18.5)
        p.closeSubpath(); p.moveTo(13.5, 7); p.lineTo(17, 10.5)
    elif name == "eye":
        p.moveTo(2.5, 12); p.cubicTo(7, 4.5, 17, 4.5, 21.5, 12); p.cubicTo(17, 19.5, 7, 19.5, 2.5, 12)
        p.addEllipse(QRectF(9, 9, 6, 6))
    elif name == "dice":           # the password generator
        p.addRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
        for x, y in ((8.5, 8.5), (15.5, 15.5), (12, 12), (15.5, 8.5), (8.5, 15.5)):
            p.addEllipse(QRectF(x - .9, y - .9, 1.8, 1.8))
    elif name == "mail":
        p.addRoundedRect(QRectF(3, 6, 18, 12), 1.5, 1.5); p.moveTo(3.5, 6.5); p.lineTo(12, 13); p.lineTo(20.5, 6.5)
    elif name == "bank":
        p.moveTo(3, 9); p.lineTo(12, 4); p.lineTo(21, 9); p.closeSubpath(); p.moveTo(3, 20); p.lineTo(21, 20)
        for x in (6, 10, 14, 18):
            p.moveTo(x, 11); p.lineTo(x, 17.5)
    elif name == "cart":
        p.moveTo(2.5, 4.5); p.lineTo(5.5, 4.5); p.lineTo(8, 15.5); p.lineTo(18.5, 15.5); p.lineTo(20.5, 8)
        p.lineTo(6.5, 8); p.addEllipse(QRectF(8, 18, 2.5, 2.5)); p.addEllipse(QRectF(16, 18, 2.5, 2.5))
    elif name == "people":
        p.addEllipse(QRectF(5, 5, 6, 6)); p.moveTo(2.5, 19); p.cubicTo(3, 13, 13, 13, 13.5, 19)
        p.addEllipse(QRectF(14, 6, 5, 5)); p.moveTo(15, 13.5); p.cubicTo(19, 13, 21.5, 15, 21.5, 19)
    elif name == "briefcase":
        p.addRoundedRect(QRectF(3, 7.5, 18, 12), 2, 2); p.moveTo(9, 7.5); p.lineTo(9, 4.5); p.lineTo(15, 4.5)
        p.lineTo(15, 7.5); p.moveTo(3, 12.5); p.lineTo(21, 12.5)
    elif name == "wifi":
        p.moveTo(2.5, 9.5); p.cubicTo(8, 3.5, 16, 3.5, 21.5, 9.5); p.moveTo(5.5, 12.5); p.cubicTo(9.5, 8.5, 14.5, 8.5, 18.5, 12.5)
        p.moveTo(8.5, 15.5); p.cubicTo(10.5, 13.5, 13.5, 13.5, 15.5, 15.5); p.addEllipse(QRectF(11, 18, 2, 2))
    elif name == "safe":           # the database (root group)
        p.addRoundedRect(QRectF(3.5, 4, 17, 15), 2, 2); p.addEllipse(QRectF(9, 8, 6, 6)); p.moveTo(6, 19)
        p.lineTo(6, 21); p.moveTo(18, 19); p.lineTo(18, 21)
    elif name == "ellipse":
        p.addEllipse(QRectF(3.5, 5.5, 17, 13))
    elif name == "line":
        p.moveTo(4, 19); p.lineTo(20, 5)
    elif name == "arrow":
        p.moveTo(4, 20); p.lineTo(19, 5); p.moveTo(11, 5); p.lineTo(19, 5); p.lineTo(19, 13)
    elif name == "pen":            # freehand
        p.moveTo(3.5, 17); p.cubicTo(7, 8, 10, 22, 14, 12); p.cubicTo(16, 7, 18, 9, 20.5, 6)
    elif name == "text":
        p.moveTo(5, 6); p.lineTo(19, 6); p.moveTo(12, 6); p.lineTo(12, 19); p.moveTo(9, 19); p.lineTo(15, 19)
    elif name == "bubble":
        p.moveTo(4, 5); p.lineTo(20, 5); p.lineTo(20, 15); p.lineTo(11, 15); p.lineTo(6.5, 19.5); p.lineTo(7.5, 15)
        p.lineTo(4, 15); p.closeSubpath()
    elif name == "step":           # a numbered circle
        p.addEllipse(QRectF(3.5, 3.5, 17, 17)); p.moveTo(10.5, 9); p.lineTo(12.5, 7.5); p.lineTo(12.5, 16.5)
        p.moveTo(10, 16.5); p.lineTo(15, 16.5)
    elif name == "highlight":      # a marker
        p.moveTo(9, 15); p.lineTo(17, 4.5); p.lineTo(21, 8); p.lineTo(12.5, 18.5); p.closeSubpath()
        p.moveTo(9, 15); p.lineTo(7, 19.5); p.lineTo(12.5, 18.5); p.moveTo(3, 21.5); p.lineTo(13, 21.5)
    elif name == "obfuscate":      # pixel squares
        for x in (4, 10, 16):
            for y in (4, 10, 16):
                if (x + y) % 12 == 8 or (x, y) in ((10, 10), (4, 4)):
                    p.addRect(QRectF(x, y, 5, 5))
        p.addRect(QRectF(3.5, 3.5, 17, 17))
    elif name == "copy":
        p.addRoundedRect(QRectF(8, 8, 12, 13), 2, 2)
        p.moveTo(5, 16); p.lineTo(4, 16); p.lineTo(4, 3); p.lineTo(16, 3); p.lineTo(16, 5)
    elif name == "redo":
        p.moveTo(15.5, 5); p.lineTo(19.5, 9); p.lineTo(15.5, 13)
        p.moveTo(19.5, 9); p.lineTo(10, 9); p.cubicTo(2, 9, 2, 20, 10, 20); p.lineTo(16, 20)
    elif name == "left":
        p.moveTo(14.5, 5.5); p.lineTo(8, 12); p.lineTo(14.5, 18.5)
    elif name == "right":
        p.moveTo(9.5, 5.5); p.lineTo(16, 12); p.lineTo(9.5, 18.5)
    elif name == "rotleft":
        p.moveTo(5.5, 4.5); p.lineTo(5.5, 9); p.lineTo(10, 9)
        p.moveTo(5.5, 9); p.cubicTo(8, 4, 17, 3.5, 19, 10); p.cubicTo(20.5, 16, 15, 21, 9.5, 19.5)
    elif name == "flip":           # two halves facing a dashed middle
        p.moveTo(10, 5); p.lineTo(3, 18); p.lineTo(10, 18); p.closeSubpath()
        p.moveTo(14, 5); p.lineTo(21, 18); p.lineTo(14, 18); p.closeSubpath()
        for y in (3, 8, 13, 18):
            p.moveTo(12, y); p.lineTo(12, y + 2)
    elif name == "actual":         # 1:1
        p.moveTo(5, 8); p.lineTo(7, 6.5); p.lineTo(7, 17.5)
        p.addEllipse(QRectF(11.3, 9, 1.4, 1.4)); p.addEllipse(QRectF(11.3, 14, 1.4, 1.4))
        p.moveTo(16, 8); p.lineTo(18, 6.5); p.lineTo(18, 17.5)
    elif name == "fit":            # corners pointing out
        for (x, y, dx, dy) in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
            p.moveTo(x, y + 5 * dy); p.lineTo(x, y); p.lineTo(x + 5 * dx, y)
        p.addRoundedRect(QRectF(8.5, 8.5, 7, 7), 1, 1)
    elif name == "play":           # slideshow
        p.moveTo(8, 5.5); p.lineTo(18.5, 12); p.lineTo(8, 18.5); p.closeSubpath()
    elif name == "thumbs":
        for x in (3.5, 10.25, 17):
            for y in (5, 13):
                p.addRoundedRect(QRectF(x, y, 4.5, 6), 1, 1)
    elif name == "fullscreen":
        for (x, y, dx, dy) in ((3.5, 3.5, 1, 1), (20.5, 3.5, -1, 1), (3.5, 20.5, 1, -1), (20.5, 20.5, -1, -1)):
            p.moveTo(x, y + 5.5 * dy); p.lineTo(x, y); p.lineTo(x + 5.5 * dx, y)
    elif name == "info":
        p.addEllipse(QRectF(3, 3, 18, 18)); p.moveTo(12, 11); p.lineTo(12, 17)
        p.addEllipse(QRectF(11.2, 6.8, 1.6, 1.6))
    elif name == "save":
        p.moveTo(4, 4); p.lineTo(17, 4); p.lineTo(20, 7); p.lineTo(20, 20); p.lineTo(4, 20); p.closeSubpath()
        p.addRect(QRectF(8, 4, 7, 5)); p.addRect(QRectF(7.5, 13, 9, 7))
    elif name == "crop":
        p.moveTo(7, 2.5); p.lineTo(7, 17); p.lineTo(21.5, 17)
        p.moveTo(2.5, 7); p.lineTo(17, 7); p.lineTo(17, 21.5)
    elif name == "pdf":            # a page with three lines of text
        p.moveTo(5, 2.5); p.lineTo(14, 2.5); p.lineTo(19, 7.5); p.lineTo(19, 21.5); p.lineTo(5, 21.5); p.closeSubpath()
        for y in (11, 14.5, 18):
            p.moveTo(8, y); p.lineTo(16, y)
    return p


# Kinds of file and what they're drawn with: (glyph inside the page, colour name in theme).
FILE_KINDS = {"audio": "music", "video": "videos", "image": "pictures", "archive": "archive", "text": "documents",
              "document": "documents"}


def kind_of(name: str, is_dir: bool = False) -> str:
    if is_dir:
        return "folder"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    for kind, exts in (("audio", "mp3 flac m4a ogg opus wav wma aac"), ("video", "mp4 mkv avi mov webm wmv"),
                       ("image", "jpg jpeg png gif webp bmp tif tiff heic svg"),
                       ("archive", "zip 7z rar tar gz xz bz2 zst iso"), ("text", "txt md log ini cfg json xml csv py"),
                       ("document", "pdf doc docx odt xls xlsx ppt pptx rtf")):
        if ext in exts.split():
            return kind
    return "file"


def draw_icon(p: QPainter, name: str, rect: QRectF, colour, width: float = 1.7, fill: QColor | None = None) -> None:
    path = _icon_path(name)
    s = min(rect.width(), rect.height()) / 24.0
    t = QTransform().translate(rect.center().x() - 12 * s, rect.center().y() - 12 * s).scale(s, s)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if fill is not None:
        p.fillPath(t.map(path), fill)
    p.setPen(QPen(colour, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(t.map(path))
    p.restore()


def file_icon(kind: str, size: int = 18) -> QIcon:
    """Folder: orange line, faint fill. Drives: family red. Files: a pearl page; known kinds carry their glyph."""
    return QIcon(file_pixmap(kind, size))


def file_pixmap(kind: str, size: int = 18) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r = QRectF(0, 0, size, size)
    w = 1.3 + size / 48  # the pen isn't scaled with the path: keep big icons fine-lined
    if kind in ("folder", "bookmark"):
        fill = QColor(theme.LED_ORANGE)
        fill.setAlphaF(0.12)
        draw_icon(p, "folder", r, QColor(theme.LED_ORANGE), w * 1.05, fill)
    elif kind in ("drive", "usb", "network", "trash", "server", "share", "desktop"):
        draw_icon(p, kind, r, QColor(theme.ACCENT), w)
    elif kind in FILE_KINDS and kind not in ("text", "document") and size >= 32:
        fill = QColor(theme.TEXT_DIM)
        fill.setAlphaF(0.08)
        draw_icon(p, "file", r, QColor(theme.TEXT_DIM), w, fill)
        g = QRectF(r.center().x() - size * .2, r.center().y() - size * .08, size * .4, size * .4)
        draw_icon(p, FILE_KINDS[kind], g, QColor(theme.ACCENT if kind == "archive" else theme.LED_ORANGE), w * .8)
    elif kind in ("text", "document"):
        draw_icon(p, "documents", r, QColor(theme.TEXT_DIM), w)
    elif kind in FILE_KINDS:
        draw_icon(p, FILE_KINDS[kind], r, QColor(theme.LED_ORANGE if kind != "archive" else theme.ACCENT), w)
    else:
        draw_icon(p, "file", r, QColor(theme.TEXT_DIM), w)
    p.end()
    return pm


def line_icon(name: str, colour: str | None = None, size: int = 18) -> QIcon:
    """One of the family line icons by name (PR7-PM's groups and entries), in a family colour."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw_icon(p, name, QRectF(0, 0, size, size), QColor(colour or theme.LED_ORANGE), 1.3 + size / 48)
    p.end()
    return QIcon(pm)


# --------------------------------------------------------------------------- compact piano-black keys
class SmallKey(QAbstractButton):
    """A compact family piano-black key: icon only (the tooltip names it). Checkable keys (the log, the trees,
    the queue, sync browsing) show the family gradient bar at their foot when on."""

    def __init__(self, icon: str, tip: str, checkable: bool = False, parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.setToolTip(tip)
        self.setCheckable(checkable)
        self.setFixedSize(QSize(38, 34))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        down, hover = self.isDown(), self.underMouse() and self.isEnabled()
        r = QRectF(self.rect()).adjusted(2, 1, -2, -4)
        if down:
            r.translate(0, 1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 110 if down else 150))
        p.drawRoundedRect(r.translated(0, 2), 5, 5)
        ch = QLinearGradient(r.topLeft(), r.bottomLeft())
        for pos, c in ((0, "#57565C"), (.18, "#2A292E"), (.7, "#111113"), (1, "#020203")):
            ch.setColorAt(pos, QColor(c))
        p.setBrush(ch)
        p.drawRoundedRect(r, 5, 5)
        face = r.adjusted(2, 2, -2, -3)
        tf = QLinearGradient(face.topLeft(), face.bottomLeft())
        tf.setColorAt(0, QColor("#1C1B20"))
        tf.setColorAt(1, QColor("#060607"))
        p.setBrush(tf)
        p.drawRoundedRect(face, 3.5, 3.5)
        p.setPen(QPen(QColor(255, 255, 255, 105), 1))
        p.drawLine(QPointF(face.left() + 3, face.top() + 0.5), QPointF(face.right() - 3, face.top() + 0.5))
        if hover:
            c = QColor(theme.GLOW)
            c.setAlphaF(0.8)
            p.setPen(QPen(c, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-0.5, -0.5, 0.5, 0.5), 5.5, 5.5)
        if self.isChecked():
            bar = QRectF(face.left() + 6, face.bottom() - 3, face.width() - 12, 2)
            p.setPen(Qt.NoPen)
            p.setBrush(theme.family_gradient(bar.left(), 0, bar.right(), 0))
            p.drawRoundedRect(bar, 1, 1)
        colour = QColor("#FFFFFF") if (hover or down or self.isChecked()) else QColor(theme.ON_DARK)
        if not self.isEnabled():
            colour = QColor(theme.TEXT_DIM)
        draw_icon(p, self.icon_name, QRectF(face.center().x() - 9, face.center().y() - 9.5, 18, 18), colour, 1.6)


# --------------------------------------------------------------------------- labelled toolbar keys
class KeyButton(QAbstractButton):
    """A toolbar key: the family's piano-black key (PR7-Z's) with an icon and an upper-case label."""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.icon_name, self.label = icon, label.upper()
        self.setFixedSize(QSize(78, 62))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(label.title())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        down = self.isDown()
        hover = self.underMouse() and self.isEnabled()
        r = QRectF(self.rect()).adjusted(3, 2, -3, -5)
        if down:
            r.translate(0, 1)
        # drop shadow
        sh = QColor(0, 0, 0, int(255 * (0.35 if down else 0.6)))
        p.setPen(Qt.NoPen); p.setBrush(sh)
        p.drawRoundedRect(r.translated(0, 2 if down else 3), 6, 6)
        # chamfer
        ch = QLinearGradient(r.topLeft(), r.bottomLeft())
        for pos, c in ((0, "#57565C"), (.18, "#2A292E"), (.7, "#111113"), (1, "#020203")):
            ch.setColorAt(pos, QColor(c))
        p.setBrush(ch); p.drawRoundedRect(r, 6, 6)
        # red glow in the side chamfers
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g0 = QColor(theme.GLOW); g0.setAlphaF(0); g1 = QColor(theme.GLOW); g1.setAlphaF(0.75)
        g.setColorAt(0, g0); g.setColorAt(1, g1)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(r.left(), r.top() + 4, 2.2, r.height() - 8), 1, 1)
        p.drawRoundedRect(QRectF(r.right() - 2.2, r.top() + 4, 2.2, r.height() - 8), 1, 1)
        # top face
        face = r.adjusted(3, 2.5, -3, -4)
        tf = QLinearGradient(face.topLeft(), face.bottomLeft())
        tf.setColorAt(0, QColor("#1C1B20")); tf.setColorAt(1, QColor("#060607"))
        p.setBrush(tf); p.drawRoundedRect(face, 4, 4)
        gloss = QColor(255, 255, 255, int(255 * 0.13))
        p.setBrush(gloss)
        p.save(); p.setClipRect(QRectF(face.left(), face.top(), face.width(), face.height() * 0.55))
        p.drawRoundedRect(face, 4, 4); p.restore()
        p.setPen(QPen(QColor(255, 255, 255, int(255 * 0.45)), 1))
        p.drawLine(QPointF(face.left() + 4, face.top() + 0.5), QPointF(face.right() - 4, face.top() + 0.5))
        p.setPen(QPen(QColor(0, 0, 0, int(255 * 0.6)), 0.8)); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(face, 4, 4)
        outer = QColor(theme.GLOW) if hover else QColor("#000000")
        if hover:
            outer.setAlphaF(0.8)
        p.setPen(QPen(outer, 1)); p.drawRoundedRect(r.adjusted(-0.5, -0.5, 0.5, 0.5), 6.5, 6.5)
        # icon and label
        colour = QColor("#FFFFFF") if (hover or down) else QColor(theme.ON_DARK)   # the key stays black in AURORA
        if not self.isEnabled():
            colour = QColor(theme.TEXT_DIM)
        if not self.label:  # icon-only key (Up): centred
            side = min(18.0, face.height() - 6)
            draw_icon(p, self.icon_name, QRectF(face.center().x() - side / 2, face.center().y() - side / 2, side, side),
                      colour, 1.7)
            return
        draw_icon(p, self.icon_name, QRectF(face.center().x() - 11, face.top() + 7, 22, 22), colour, 1.7)
        f = QFont("Inter", 1); f.setPixelSize(10); f.setWeight(QFont.DemiBold)
        p.setFont(f); p.setPen(colour)
        p.drawText(QRectF(face.left(), face.bottom() - 19, face.width(), 15), Qt.AlignCenter, self.label)
