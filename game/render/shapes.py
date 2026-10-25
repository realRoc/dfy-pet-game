"""绘制小工具：平滑闭合曲线、Catmull-Rom 曲线段、带厚度的盒子、影子。"""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainterPath, QPolygonF


def smooth_closed(points):
    """过所有点的平滑闭合曲线（Catmull-Rom 转三次贝塞尔）。"""
    pts = [QPointF(x, y) for x, y in points]
    n = len(pts)
    path = QPainterPath(pts[0])
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        path.cubicTo(p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6, p2)
    path.closeSubpath()
    return path


def catmull_segment(path, p0, p1, p2, p3):
    """在 path 上追加 p1→p2 的平滑段，p0、p3 是前后邻点。"""
    path.cubicTo(p1 + (p2 - p0) / 6, p2 - (p3 - p1) / 6, p2)


def shadow(p, x, y, rx, ry, alpha=45):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(20, 40, 50, alpha))
    p.drawEllipse(QPointF(x, y), rx, ry)


def poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def box(p, x, y, w, h, d, front, side=None, top=None):
    """底边中心在 (x, y) 的盒子：正面 w×h，向右上斜出深度 d。光从左上来，侧面更暗。"""
    side = side or front.darker(125)
    top = top or front.lighter(108)
    dx, dy = d * 0.6, d * 0.5
    l, r, t = x - w / 2, x + w / 2, y - h
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(side)
    p.drawPolygon(poly((r, y), (r + dx, y - dy), (r + dx, t - dy), (r, t)))
    p.setBrush(top)
    p.drawPolygon(poly((l, t), (r, t), (r + dx, t - dy), (l + dx, t - dy)))
    p.setBrush(front)
    p.drawRect(l, t, w, h)
    return l, r, t, dx, dy
