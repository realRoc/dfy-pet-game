"""按格子类型画格子。

- card：彩色圆角方块 + emoji 图标 + 名字（经典外圈）
- stone：带厚度的石板 + 矢量符号，名字在悬停时显示
- sprite：地图提供的石板贴图（tile_sprites），没有贴图的类型退回 stone
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFontMetrics, QPen

from common import ui_font, emoji_font
from .symbols import paint_symbol

STONE_RATIO = 0.74        # 石板高 / 宽
STONE_DEPTH = 0.12        # 石板厚度 / 宽


class TileRenderer:
    def __init__(self, tiles, style="card", sprites=None):
        """sprites：(格子类型 -> 贴图 id, MapRenderer)，sprite 风格用。"""
        self.tiles = tiles
        self.style = style
        self.colors = {tid: QColor(t.color) for tid, t in tiles.items()}
        self.tile_sprites, self.map_painter = sprites or ({}, None)
        self.device_scale = 2.0

    def foot_offset(self, tile):
        """角色脚底相对格子中心向下的偏移。"""
        return tile * (0.26 if self.style == "card" else 0.06)

    def shape(self, rect):
        """格子的可点击 / 可悬停区域。"""
        if self.style == "card":
            return rect.adjusted(4, 4, -4, -4)
        w = rect.width()
        h = w * STONE_RATIO
        return QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h + w * STONE_DEPTH)

    def paint(self, p, rect, kind, glow=0.0, mark=0.0, hover=False):
        """glow：刚落地的金色光圈；mark：本回合将到达的格子（0~1 脉动）。"""
        if self.style == "card":
            self.paint_card(p, rect, kind, glow, mark)
        elif self.style == "sprite" and kind in self.tile_sprites:
            self.paint_sprite(p, rect, kind, glow, mark, hover)
        else:
            self.paint_stone(p, rect, kind, glow, mark, hover)

    def paint_sprite(self, p, rect, kind, glow, mark, hover):
        sid = self.tile_sprites[kind]
        w = rect.width() * 1.18
        sw, sh = self.map_painter.sprite_size(sid, 1)
        h = w * sh / sw
        lift = 5 if hover else 0
        c = rect.center()
        p.setPen(Qt.PenStyle.NoPen)
        if glow > 0:
            p.setBrush(QColor(255, 220, 110, int(190 * glow)))
            p.drawEllipse(c + QPointF(0, h * 0.12), w * (0.62 + 0.12 * glow), h * (0.5 + 0.1 * glow))
        if mark > 0:
            p.setPen(QPen(QColor(40, 77, 121, int(140 + 110 * mark)), 4, Qt.PenStyle.DashLine))
            p.setBrush(QColor(255, 255, 255, int(70 * mark)))
            p.drawEllipse(c + QPointF(0, h * 0.1), w * 0.66, h * 0.56)
            p.setPen(Qt.PenStyle.NoPen)
        box = QRectF(c.x() - w / 2, c.y() - h / 2 - lift, w, h)
        pix = self.map_painter.scaled_sprite(sid, w, h, self.device_scale)
        p.drawPixmap(box, pix, QRectF(pix.rect()))

    def paint_card(self, p, rect, kind, glow, mark):
        tile = self.tiles[kind]
        color = self.colors[kind]
        rc = rect.adjusted(4, 4, -4, -4)
        if glow > 0:
            g = glow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 230, 90, int(180 * g)))
            p.drawRoundedRect(rc.adjusted(-4 - 4 * g, -4 - 4 * g, 4 + 4 * g, 4 + 4 * g), 16, 16)
        if mark > 0:
            p.setPen(QPen(QColor(40, 77, 121, int(120 + 100 * mark)), 3, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rc.adjusted(-5, -5, 5, 5), 15, 15)
        p.setPen(QPen(color.darker(125), 2))
        p.setBrush(color.lighter(115))
        p.drawRoundedRect(rc, 12, 12)

        p.setFont(emoji_font(26))
        p.drawText(QRectF(rc.x(), rc.y() + 4, rc.width(), 34), Qt.AlignmentFlag.AlignCenter, tile.icon)
        p.setFont(ui_font(12, bold=True))
        p.setPen(color.darker(220))
        p.drawText(QRectF(rc.x(), rc.bottom() - 24, rc.width(), 20), Qt.AlignmentFlag.AlignCenter, tile.name)

    def paint_stone(self, p, rect, kind, glow, mark, hover):
        tile = self.tiles[kind]
        color = self.colors[kind]
        w = rect.width()
        h = w * STONE_RATIO
        depth = w * STONE_DEPTH
        lift = 3 if hover else 0
        top = QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2 - lift, w, h)
        r = h * 0.34

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 50, 40, 55))
        p.drawRoundedRect(top.translated(2, depth + 3 + lift), r, r)
        if glow > 0:
            p.setBrush(QColor(255, 220, 110, int(170 * glow)))
            grow = 6 + 6 * glow
            p.drawRoundedRect(top.adjusted(-grow, -grow, grow, grow + depth), r + grow, r + grow)
        if mark > 0:
            p.setPen(QPen(QColor(40, 77, 121, int(130 + 110 * mark)), 2.6, Qt.PenStyle.DashLine))
            p.setBrush(QColor(255, 255, 255, int(60 * mark)))
            p.drawRoundedRect(top.adjusted(-6, -6, 6, 6 + depth), r + 6, r + 6)
            p.setPen(Qt.PenStyle.NoPen)
        side = color.darker(135)
        p.setBrush(side)
        p.drawRoundedRect(top.translated(0, depth), r, r)
        p.drawRect(QRectF(top.left(), top.center().y(), w, depth))
        p.setBrush(color.lighter(104))
        p.drawRoundedRect(top, r, r)
        # 顶面高光和内描边，做出石头的倒角感
        p.setBrush(QColor(255, 255, 255, 70))
        p.drawRoundedRect(top.adjusted(4, 3, -4, -h * 0.45), r * 0.8, r * 0.8)
        p.setPen(QPen(color.darker(112), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(top.adjusted(1, 1, -1, -1), r, r)

        ink = color.darker(230) if color.lightness() > 200 else color.darker(190)
        if tile.symbol:
            paint_symbol(p, tile.symbol, top.center().x(), top.center().y(), h * 0.62, ink)
        else:
            p.setFont(emoji_font(h * 0.5))
            p.drawText(top, Qt.AlignmentFlag.AlignCenter, tile.icon)

    def paint_label(self, p, rect, kind, canvas_w):
        """悬停说明：名字 + 效果，画在格子上方。"""
        tile = self.tiles[kind]
        title_f, desc_f = ui_font(15, bold=True), ui_font(13)
        tw = QFontMetrics(title_f).horizontalAdvance(tile.name)
        dw = QFontMetrics(desc_f).horizontalAdvance(tile.desc) if tile.desc else 0
        bw = max(tw, dw) + 28
        bh = 30 + (20 if tile.desc else 0)
        bx = min(max(8.0, rect.center().x() - bw / 2), canvas_w - bw - 8)
        by = rect.top() - bh - 10
        if by < 60:
            by = rect.bottom() + 14
        box = QRectF(bx, by, bw, bh)
        p.setPen(QPen(QColor(40, 77, 121, 90), 1.2))
        p.setBrush(QColor(248, 242, 230, 245))
        p.drawRoundedRect(box, 10, 10)
        p.setFont(title_f)
        p.setPen(QColor("#284D79"))
        p.drawText(QRectF(bx, by + 6, bw, 20), Qt.AlignmentFlag.AlignCenter, tile.name)
        if tile.desc:
            p.setFont(desc_f)
            p.setPen(QColor(70, 90, 120))
            p.drawText(QRectF(bx, by + 27, bw, 18), Qt.AlignmentFlag.AlignCenter, tile.desc)
