"""按格子类型画石板：底色圆角块 + 图标 + 名字，落地时外圈发光。"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen

from common import ui_font, emoji_font


class TileRenderer:
    def __init__(self, tiles):
        self.tiles = tiles
        self.colors = {tid: QColor(t.color) for tid, t in tiles.items()}

    def paint(self, p, rect, kind, glow=0.0):
        tile = self.tiles[kind]
        color = self.colors[kind]
        rc = rect.adjusted(4, 4, -4, -4)
        if glow > 0:
            g = glow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 230, 90, int(180 * g)))
            p.drawRoundedRect(rc.adjusted(-4 - 4 * g, -4 - 4 * g, 4 + 4 * g, 4 + 4 * g), 16, 16)
        p.setPen(QPen(color.darker(125), 2))
        p.setBrush(color.lighter(115))
        p.drawRoundedRect(rc, 12, 12)

        p.setFont(emoji_font(26))
        p.drawText(QRectF(rc.x(), rc.y() + 4, rc.width(), 34), Qt.AlignmentFlag.AlignCenter, tile.icon)
        p.setFont(ui_font(12, bold=True))
        p.setPen(color.darker(220))
        p.drawText(QRectF(rc.x(), rc.bottom() - 24, rc.width(), 20), Qt.AlignmentFlag.AlignCenter, tile.name)
