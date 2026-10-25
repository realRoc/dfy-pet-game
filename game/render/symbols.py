"""石板上的矢量符号，在 32×32 的单位格里画，以 (0, 0) 为中心。

除了颜色，每种格子还有不同的图形，色弱也能分清。
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainterPath, QPen

from .shapes import poly


def _pen(p, color, w):
    p.setPen(QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))


def _flag(p, c):
    _pen(p, c, 2.6)
    p.drawLine(QPointF(-8, 13), QPointF(-8, -13))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(poly((-7, -13), (11, -8), (-7, -2)))


def _fish(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QRectF(-12, -7, 20, 14))
    p.drawPolygon(poly((6, 0), (14, -7), (14, 7)))
    p.setBrush(Qt.GlobalColor.white)
    p.drawEllipse(QPointF(-6, -1.5), 2, 2)


def _hook(p, c):
    _pen(p, c, 3)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(3, -13))
    path.lineTo(3, 4)
    path.cubicTo(QPointF(3, 13), QPointF(-9, 13), QPointF(-9, 4))
    p.drawPath(path)
    p.drawLine(QPointF(-9, 4), QPointF(-5, 1))
    p.drawEllipse(QPointF(3, -13), 2.5, 2.5)


def _chest(p, c):
    _pen(p, c, 2.4)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-12, -6, 24, 16), 2, 2)
    p.drawLine(QPointF(-12, 0), QPointF(12, 0))
    lid = QPainterPath(QPointF(-12, -6))
    lid.cubicTo(QPointF(-12, -14), QPointF(12, -14), QPointF(12, -6))
    p.drawPath(lid)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRect(QRectF(-2.5, -3, 5, 6))


def _bench(p, c):
    _pen(p, c, 2.6)
    p.drawLine(QPointF(-12, 0), QPointF(12, 0))
    p.drawLine(QPointF(-12, -7), QPointF(12, -7))
    p.drawLine(QPointF(-9, 0), QPointF(-9, 9))
    p.drawLine(QPointF(9, 0), QPointF(9, 9))
    p.drawLine(QPointF(-9, -7), QPointF(-9, 0))
    p.drawLine(QPointF(9, -7), QPointF(9, 0))


def _sign(p, c):
    _pen(p, c, 2.4)
    p.drawLine(QPointF(0, -4), QPointF(0, 13))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(poly((-11, -13), (8, -13), (13, -8), (8, -3), (-11, -3)))


def _fork(p, c):
    _pen(p, c, 2.8)
    p.drawLine(QPointF(0, 13), QPointF(0, 2))
    p.drawLine(QPointF(0, 2), QPointF(-9, -9))
    p.drawLine(QPointF(0, 2), QPointF(9, -9))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPolygon(poly((-13, -13), (-4, -12), (-11, -5)))
    p.drawPolygon(poly((13, -13), (4, -12), (11, -5)))


def _leaf(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    path = QPainterPath(QPointF(-10, 10))
    path.cubicTo(QPointF(-12, -6), QPointF(2, -14), QPointF(12, -12))
    path.cubicTo(QPointF(12, 2), QPointF(2, 12), QPointF(-10, 10))
    p.drawPath(path)
    _pen(p, Qt.GlobalColor.white, 1.6)
    p.drawLine(QPointF(-8, 8), QPointF(8, -8))


def _shop(p, c):
    _pen(p, c, 2.4)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-10, -4, 20, 16), 2, 2)
    bag = QPainterPath(QPointF(-5, -4))
    bag.cubicTo(QPointF(-5, -13), QPointF(5, -13), QPointF(5, -4))
    p.drawPath(bag)


def _pixel(p, c):
    """像素小怪：一格 4 单位的方块图。"""
    rows = ["..X...X..", "...XXX...", "..XXXXX..", ".XX.X.XX.", "XXXXXXXXX", "X.XXXXX.X", "X.X...X.X"]
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    u = 3.2
    for r, line in enumerate(rows):
        for col, ch in enumerate(line):
            if ch == "X":
                p.drawRect(QRectF((col - 4.5) * u, (r - 3.5) * u, u + 0.2, u + 0.2))


def _cross(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(-4.5, -12, 9, 24), 2, 2)
    p.drawRoundedRect(QRectF(-12, -4.5, 24, 9), 2, 2)


def _question(p, c):
    _pen(p, c, 3.2)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(-7, -6))
    path.cubicTo(QPointF(-7, -15), QPointF(8, -15), QPointF(8, -7))
    path.cubicTo(QPointF(8, -1), QPointF(0, 0), QPointF(0, 5))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(0, 11), 2.4, 2.4)


SYMBOL_PAINTERS = {
    "flag": _flag, "fish": _fish, "hook": _hook, "chest": _chest, "bench": _bench, "sign": _sign,
    "fork": _fork, "leaf": _leaf, "shop": _shop, "pixel": _pixel, "cross": _cross, "question": _question,
}


def paint_symbol(p, name, cx, cy, size, color):
    p.save()
    p.translate(cx, cy)
    p.scale(size / 32, size / 32)
    SYMBOL_PAINTERS[name](p, color)
    p.restore()
