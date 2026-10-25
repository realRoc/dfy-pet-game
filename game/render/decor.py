"""地图装饰的代码画法。每个函数以脚底 (x, y) 为锚点、s 为缩放。

这些都是占位美术：以后有单独的透明 PNG 时，可以按 kind 换成贴图，地图配置不用改。
"""
import math
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen, QRadialGradient

from .shapes import box, poly, shadow

C = QColor


def _tree(p, x, y, s, dec):
    shadow(p, x + 6 * s, y, 26 * s, 8 * s)
    p.setBrush(C("#8A6446"))
    p.drawRoundedRect(QRectF(x - 5 * s, y - 34 * s, 10 * s, 34 * s), 3 * s, 3 * s)
    for dx, dy, r, col in ((-14, -44, 20, "#5E9A63"), (14, -46, 19, "#5E9A63"),
                           (0, -62, 24, "#6FAE6C"), (-6, -66, 12, "#8CC57F")):
        p.setBrush(C(col))
        p.drawEllipse(QPointF(x + dx * s, y + dy * s), r * s, r * s)


def _palm(p, x, y, s, dec):
    shadow(p, x + 14 * s, y, 24 * s, 7 * s)
    trunk = QPainterPath(QPointF(x - 4 * s, y))
    trunk.cubicTo(QPointF(x - 2 * s, y - 30 * s), QPointF(x + 8 * s, y - 50 * s), QPointF(x + 14 * s, y - 70 * s))
    p.setPen(QPen(C("#9C7653"), 7 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(trunk)
    p.setPen(Qt.PenStyle.NoPen)
    top = QPointF(x + 14 * s, y - 70 * s)
    for ang in (-160, -115, -65, -20, 25, 160):
        p.save()
        p.translate(top)
        p.rotate(ang)
        p.setBrush(C("#4F9A5E") if ang % 2 else C("#63B06B"))
        p.drawEllipse(QRectF(0, -6 * s, 34 * s, 12 * s))
        p.restore()


def _mushroom(p, x, y, s, dec):
    shadow(p, x, y, 18 * s, 6 * s)
    p.setBrush(C("#F3E8D2"))
    p.drawRoundedRect(QRectF(x - 6 * s, y - 22 * s, 12 * s, 22 * s), 4 * s, 4 * s)
    cap = QPainterPath()
    cap.moveTo(x - 22 * s, y - 20 * s)
    cap.cubicTo(QPointF(x - 20 * s, y - 46 * s), QPointF(x + 20 * s, y - 46 * s), QPointF(x + 22 * s, y - 20 * s))
    cap.closeSubpath()
    p.setBrush(C(dec.get("color", "#4F8FA8")))
    p.drawPath(cap)
    p.setBrush(C(255, 255, 255, 210))
    for dx, dy, r in ((-9, -30, 3.5), (6, -35, 3), (12, -25, 2.5)):
        p.drawEllipse(QPointF(x + dx * s, y + dy * s), r * s, r * s)


def _bush(p, x, y, s, dec):
    shadow(p, x, y, 22 * s, 6 * s)
    for dx, dy, r, col in ((-12, -10, 12, "#5E9A63"), (12, -10, 12, "#5E9A63"),
                           (0, -16, 15, "#72B26E"), (-4, -20, 7, "#92CA84")):
        p.setBrush(C(col))
        p.drawEllipse(QPointF(x + dx * s, y + dy * s), r * s, r * s)


def _flowers(p, x, y, s, dec):
    rng = random.Random(int(x * 31 + y))
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(9):
        fx, fy = x + rng.uniform(-22, 22) * s, y + rng.uniform(-10, 6) * s
        p.setBrush(C("#6FA866"))
        p.drawEllipse(QPointF(fx, fy + 2 * s), 4 * s, 2.5 * s)
        p.setBrush(C(rng.choice(["#F4A7C0", "#B9A2E3", "#FFF2B0", "#FFFFFF", "#9FC3F0"])))
        p.drawEllipse(QPointF(fx, fy - 2 * s), 3.2 * s, 3.2 * s)


def _rock(p, x, y, s, dec):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(C(234, 247, 245, 150))
    p.drawEllipse(QPointF(x, y), 30 * s, 9 * s)
    p.setBrush(C("#8C8F94"))
    p.drawPolygon(poly((x - 22 * s, y), (x - 16 * s, y - 18 * s), (x, y - 26 * s),
                       (x + 18 * s, y - 16 * s), (x + 22 * s, y)))
    p.setBrush(C("#B3B6BA"))
    p.drawPolygon(poly((x - 14 * s, y - 16 * s), (x, y - 24 * s), (x + 6 * s, y - 12 * s), (x - 8 * s, y - 8 * s)))


def _pixel_tree(p, x, y, s, dec):
    shadow(p, x + 4 * s, y, 24 * s, 7 * s)
    u = 7 * s
    p.setBrush(C("#7A5E8E"))
    p.drawRect(QRectF(x - u / 2, y - 4 * u, u, 4 * u))
    shades = ["#A18BC8", "#B49DDB", "#C7B3EA", "#8E78B8"]
    rng = random.Random(int(x * 7 + y))
    for row, cols in enumerate((3, 5, 5, 3)):
        for c in range(cols):
            bx = x + (c - cols / 2) * u
            by = y - (8 - row) * u
            p.setBrush(C(rng.choice(shades)))
            p.drawRect(QRectF(bx, by, u + 0.5, u + 0.5))


def _pixel_block(p, x, y, s, dec):
    shadow(p, x + 3 * s, y, 16 * s, 5 * s)
    box(p, x, y, 22 * s, 22 * s, 16 * s, C("#A18BC8"), C("#7E69A8"), C("#C5B3EA"))


def _ruin_arch(p, x, y, s, dec):
    shadow(p, x, y, 40 * s, 8 * s)
    stone = C("#B9B2C8")
    for px in (-26, 26):
        box(p, x + px * s, y, 14 * s, 54 * s, 8 * s, stone)
    p.setBrush(stone.darker(110))
    arch = QPainterPath()
    arch.moveTo(x - 33 * s, y - 54 * s)
    arch.lineTo(x + 33 * s, y - 54 * s)
    arch.lineTo(x + 33 * s, y - 66 * s)
    arch.cubicTo(QPointF(x + 20 * s, y - 72 * s), QPointF(x - 20 * s, y - 72 * s), QPointF(x - 33 * s, y - 66 * s))
    arch.closeSubpath()
    p.drawPath(arch)
    p.setBrush(C("#9CC08C"))
    p.drawEllipse(QPointF(x - 30 * s, y - 64 * s), 6 * s, 4 * s)


def _roof(p, x, top, w, rh, d, color):
    """人字屋顶：前山墙 + 向后伸的右坡。"""
    dx, dy = d * 0.6, d * 0.5
    l, r = x - w / 2 - 5, x + w / 2 + 5
    p.setBrush(color.darker(118))
    p.drawPolygon(poly((x, top - rh), (r, top), (r + dx, top - dy), (x + dx, top - rh - dy)))
    p.setBrush(color)
    p.drawPolygon(poly((l, top), (x, top - rh), (x + dx, top - rh - dy), (l + dx, top - dy)))
    p.setBrush(color.lighter(112))
    p.drawPolygon(poly((l, top), (r, top), (x, top - rh)))


def _house(p, x, y, s, dec):
    shadow(p, x + 8 * s, y, 52 * s, 10 * s)
    l, r, t, dx, dy = box(p, x, y, 76 * s, 46 * s, 26 * s, C("#F6EEDC"))
    _roof(p, x, t, 76 * s, 30 * s, 26 * s, C("#3E6FA8"))
    p.setBrush(C("#3E6FA8"))
    p.drawRoundedRect(QRectF(x - 10 * s, y - 30 * s, 20 * s, 30 * s), 9 * s, 9 * s)
    p.setBrush(C("#BFE1F0"))
    p.drawEllipse(QPointF(x - 26 * s, y - 26 * s), 7 * s, 7 * s)
    p.drawEllipse(QPointF(x + 26 * s, y - 26 * s), 7 * s, 7 * s)
    # 红色信箱
    p.setBrush(C("#7A5A40"))
    p.drawRect(QRectF(r + 10 * s, y - 20 * s, 3 * s, 20 * s))
    p.setBrush(C("#D9534F"))
    p.drawRoundedRect(QRectF(r + 4 * s, y - 30 * s, 15 * s, 11 * s), 3 * s, 3 * s)


def _awning(p, l, r, t, stripes, a, b):
    w = (r - l) / stripes
    for i in range(stripes):
        p.setBrush(C(a) if i % 2 == 0 else C(b))
        p.drawPolygon(poly((l + i * w, t), (l + (i + 1) * w, t),
                           (l + (i + 1) * w + 2, t + 14), (l + i * w - 2, t + 14)))


def _shop(p, x, y, s, dec):
    shadow(p, x + 6 * s, y, 46 * s, 9 * s)
    l, r, t, dx, dy = box(p, x, y, 70 * s, 40 * s, 20 * s, C("#C8925E"), top=C("#E2B07C"))
    p.setBrush(C("#F7EBD3"))
    p.drawRect(QRectF(l + 6 * s, y - 18 * s, 58 * s, 18 * s))
    p.setBrush(C("#7A5A40"))
    p.drawRect(QRectF(l, t - 18 * s, 4 * s, 18 * s))
    p.drawRect(QRectF(r - 4 * s, t - 18 * s, 4 * s, 18 * s))
    _awning(p, l - 4 * s, r + 4 * s, t - 22 * s, 6, "#2F5E96", "#F7F3EA")
    # 屋顶上的鱼招牌
    p.setBrush(C("#7FA9C9"))
    p.drawEllipse(QPointF(x, t - 32 * s), 16 * s, 7 * s)
    p.drawPolygon(poly((x + 14 * s, t - 32 * s), (x + 24 * s, t - 39 * s), (x + 24 * s, t - 25 * s)))


def _hospital(p, x, y, s, dec):
    shadow(p, x + 8 * s, y, 54 * s, 10 * s)
    l, r, t, dx, dy = box(p, x, y, 80 * s, 46 * s, 26 * s, C("#F8F2E6"))
    _roof(p, x, t, 80 * s, 26 * s, 26 * s, C("#5FB6A2"))
    p.setBrush(C("#7A5A40"))
    p.drawRoundedRect(QRectF(x - 9 * s, y - 28 * s, 18 * s, 28 * s), 3 * s, 3 * s)
    p.setBrush(C("#BFE1F0"))
    p.drawRect(QRectF(l + 8 * s, y - 32 * s, 14 * s, 12 * s))
    p.drawRect(QRectF(r - 22 * s, y - 32 * s, 14 * s, 12 * s))
    # 屋顶上的白色医疗箱 + 薄荷十字
    bx, by = x + 6 * s, t - 30 * s
    p.setBrush(C("#FFFFFF"))
    p.drawRoundedRect(QRectF(bx - 16 * s, by - 13 * s, 32 * s, 26 * s), 5 * s, 5 * s)
    p.setBrush(C("#3FA58C"))
    p.drawRect(QRectF(bx - 3.5 * s, by - 9 * s, 7 * s, 18 * s))
    p.drawRect(QRectF(bx - 9 * s, by - 3.5 * s, 18 * s, 7 * s))


def _stall(p, x, y, s, dec):
    shadow(p, x, y, 34 * s, 7 * s)
    l, r, t, dx, dy = box(p, x, y, 52 * s, 22 * s, 12 * s, C("#E9B98A"))
    p.setBrush(C("#7A5A40"))
    p.drawRect(QRectF(l, t - 24 * s, 3 * s, 24 * s))
    p.drawRect(QRectF(r - 3 * s, t - 24 * s, 3 * s, 24 * s))
    _awning(p, l - 3 * s, r + 3 * s, t - 28 * s, 5, "#F29BB8", "#FFF4F7")
    for i, col in enumerate(("#F48FB1", "#B39DDB", "#FFE082")):
        p.setBrush(C(col))
        p.drawEllipse(QPointF(l + (12 + i * 14) * s, t - 3 * s), 4.5 * s, 4.5 * s)


def _dock(p, x, y, s, dec):
    """木板码头 / 木板桥：从 at 铺到 to，width 是桥面宽度。"""
    tx, ty = dec.get("to", (x + 50, y))
    w = float(dec.get("width", 20))
    length = math.hypot(tx - x, ty - y)
    ang = math.degrees(math.atan2(ty - y, tx - x))
    p.save()
    p.translate(x, y)
    p.rotate(ang)
    p.setBrush(C(20, 40, 60, 60))
    p.drawRect(QRectF(0, -w / 2 + 6, length, w))
    p.setBrush(C("#6E4F37"))
    for px in range(0, int(length) + 1, 22):
        p.drawRect(QRectF(px - 2, w / 2 - 2, 4, 10))
    plank = max(8.0, w * 0.22)
    n = max(1, int(length // plank))
    for i in range(n):
        p.setBrush(C("#B58A62") if i % 2 else C("#A57B55"))
        p.drawRect(QRectF(i * length / n, -w / 2, length / n - 1.2, w))
    if w > 30:
        # 两侧扶手
        p.setBrush(C("#7A5A40"))
        p.drawRect(QRectF(0, -w / 2 - 3, length, 4))
        p.drawRect(QRectF(0, w / 2 - 1, length, 4))
    p.restore()


def _lily(p, x, y, s, dec):
    p.setBrush(C("#6DB57A"))
    p.drawPie(QRectF(x - 10 * s, y - 6 * s, 20 * s, 12 * s), 30 * 16, 300 * 16)
    p.setBrush(C("#F7B6CF"))
    p.drawEllipse(QPointF(x + 2 * s, y - 2 * s), 3 * s, 3 * s)


def _signpost(p, x, y, s, dec):
    shadow(p, x, y, 12 * s, 4 * s)
    p.setBrush(C("#7A5A40"))
    p.drawRect(QRectF(x - 2.5 * s, y - 40 * s, 5 * s, 40 * s))
    p.setBrush(C("#C79A6B"))
    p.drawPolygon(poly((x - 20 * s, y - 38 * s), (x + 14 * s, y - 38 * s), (x + 20 * s, y - 32 * s),
                       (x + 14 * s, y - 26 * s), (x - 20 * s, y - 26 * s)))
    p.drawPolygon(poly((x + 18 * s, y - 22 * s), (x - 14 * s, y - 22 * s), (x - 20 * s, y - 16 * s),
                       (x - 14 * s, y - 10 * s), (x + 18 * s, y - 10 * s)))


def _boat(p, x, y, s, dec):
    p.setBrush(C(234, 247, 245, 140))
    p.drawEllipse(QPointF(x, y + 2 * s), 38 * s, 9 * s)
    hull = QPainterPath()
    hull.moveTo(x - 32 * s, y - 10 * s)
    hull.lineTo(x + 32 * s, y - 10 * s)
    hull.cubicTo(QPointF(x + 26 * s, y + 4 * s), QPointF(x - 26 * s, y + 4 * s), QPointF(x - 32 * s, y - 10 * s))
    p.setBrush(C("#9C7050"))
    p.drawPath(hull)
    p.setBrush(C("#C4966C"))
    p.drawRect(QRectF(x - 28 * s, y - 12 * s, 56 * s, 4 * s))


def _whale(p, x, y, s, dec):
    p.setBrush(C(234, 247, 245, 150))
    p.drawEllipse(QPointF(x, y + 4 * s), 70 * s, 14 * s)
    back = QPainterPath()
    back.moveTo(x - 64 * s, y)
    back.cubicTo(QPointF(x - 50 * s, y - 46 * s), QPointF(x + 30 * s, y - 50 * s), QPointF(x + 56 * s, y))
    back.closeSubpath()
    p.setBrush(C("#4E7FA0"))
    p.drawPath(back)
    p.setBrush(C("#6E9DBC"))
    p.drawEllipse(QPointF(x - 20 * s, y - 26 * s), 20 * s, 8 * s)
    # 喷水
    p.setPen(QPen(C(255, 255, 255, 200), 3 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for ang in (-30, 0, 30):
        a = math.radians(ang - 90)
        p.drawLine(QPointF(x - 10 * s, y - 40 * s),
                   QPointF(x - 10 * s + math.cos(a) * 16 * s, y - 40 * s + math.sin(a) * 16 * s))
    p.setPen(Qt.PenStyle.NoPen)


def _lamp(p, x, y, s, dec):
    p.setBrush(C("#5B4636"))
    p.drawRect(QRectF(x - 2 * s, y - 34 * s, 4 * s, 34 * s))
    g = QRadialGradient(QPointF(x, y - 38 * s), 16 * s)
    g.setColorAt(0, C(255, 226, 150, 170))
    g.setColorAt(1, C(255, 226, 150, 0))
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y - 38 * s), 16 * s, 16 * s)
    p.setBrush(C("#FFD98A"))
    p.drawRoundedRect(QRectF(x - 5 * s, y - 44 * s, 10 * s, 11 * s), 2 * s, 2 * s)


DECOR_PAINTERS = {
    "tree": _tree, "palm": _palm, "mushroom": _mushroom, "bush": _bush, "flowers": _flowers,
    "rock": _rock, "pixel_tree": _pixel_tree, "pixel_block": _pixel_block, "ruin_arch": _ruin_arch,
    "house": _house, "shop": _shop, "hospital": _hospital, "stall": _stall, "dock": _dock,
    "lily": _lily, "signpost": _signpost, "boat": _boat, "whale": _whale, "lamp": _lamp,
}


def paint_decor(p, dec):
    x, y = dec["at"]
    s = float(dec.get("scale", 1.0))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    if dec.get("flip"):
        p.translate(x, 0)
        p.scale(-1, 1)
        p.translate(-x, 0)
    DECOR_PAINTERS[dec["kind"]](p, x, y, s, dec)
    p.restore()
