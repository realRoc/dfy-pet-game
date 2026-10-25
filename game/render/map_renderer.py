"""地图绘制：地面层（海、地形、河、道路、平面装饰）+ 立体物件（建筑、树等贴图）。

- 地面层按 CHUNK 大小分块，按当前缩放和屏幕像素比渲染后缓存，镜头移动时只画看得见的块
- 地面块和缩好的贴图都按字节数做 LRU，Retina + 多档缩放巡图也不会无限涨
- 立体物件不进缓存，每帧和角色一起按脚底 y 排序绘制，才能前后遮挡
- 有纹理时地形用纹理平铺，没有时退回纯色 + 程序纹理
"""
import math
import random
from collections import OrderedDict

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient, QTransform)

from game.core import spline

from .decor import paint_decor
from .shapes import catmull_segment, smooth_closed

DEFAULT_PALETTE = {
    "sea_deep": "#3F8DB6", "sea_light": "#8ED2DF", "foam": "#EAF7F5", "sand": "#EFDDB0",
    "grass": "#9FCC89", "grass_dark": "#7DAE6E", "cliff": "#B0A08A", "cliff_dark": "#857563",
    "lake": "#5DB0D4", "lake_light": "#A8DEEA", "path": "#F1E6CB",
    "panel": "#FFFBF2", "panel_edge": "#78A0D2",
}
CORNER = 28
CHUNK = 512
CHUNK_BLEED = 4           # 每块多画一圈，缩放采样时边上不会混进透明像素出现接缝
CHUNK_CACHE_BYTES = 128 << 20     # 地面块缓存上限
SPRITE_CACHE_BYTES = 64 << 20     # 缩好的贴图缓存上限
TEX_SCALE = 0.55          # 纹理 1 像素在世界里的大小
SPRITE_FOOT = (0.5, 0.94)  # 贴图脚底在图里的默认位置（归一化）


def pixmap_bytes(pix):
    return pix.width() * pix.height() * 4


class PixmapCache:
    """按字节数限制的 LRU（QPixmap 按 宽×高×4 估算）。"""

    def __init__(self, limit):
        self.limit, self.size = limit, 0
        self._items = OrderedDict()

    def __len__(self):
        return len(self._items)

    def get(self, key):
        pix = self._items.get(key)
        if pix is not None:
            self._items.move_to_end(key)
        return pix

    def put(self, key, pix):
        self.pop(key)
        self._items[key] = pix
        self.size += pixmap_bytes(pix)
        while self.size > self.limit and len(self._items) > 1:   # 至少留下刚放进来的
            self.pop(next(iter(self._items)))

    def pop(self, key):
        pix = self._items.pop(key, None)
        if pix is not None:
            self.size -= pixmap_bytes(pix)

    def drop_if(self, cond):
        for key in [k for k in self._items if cond(k)]:
            self.pop(key)


class SpriteObject:
    """一个立体物件：贴图、脚底世界坐标、世界高度。"""

    def __init__(self, sid, pix, x, y, h, foot, flip=False):
        self.sid, self.pix, self.x, self.y, self.h, self.flip = sid, pix, x, y, h, flip
        self.w = h * pix.width() / max(1, pix.height())
        fx, fy = foot
        self.rect = QRectF(x - self.w * fx, y - h * fy, self.w, h)
        if flip:
            self.rect.moveLeft(x - self.w * (1 - fx))


class MapRenderer:
    def __init__(self, graph):
        self.graph = graph
        self.art = graph.art
        self.pal = {k: QColor(v) for k, v in {**DEFAULT_PALETTE, **self.art.get("palette", {})}.items()}
        self._chunks = PixmapCache(CHUNK_CACHE_BYTES)
        self._chunk_scale = None
        self._scaled = PixmapCache(SPRITE_CACHE_BYTES)
        self._textures = {k: QPixmap(v) for k, v in self.art.get("textures", {}).items()}
        self._sprites = {sid: QPixmap(s["path"]) for sid, s in self.art.get("sprites", {}).items()}
        self.objects = self._build_objects()
        self._minimap = None

    @property
    def has_terrain(self):
        return bool(self.art.get("terrain"))

    # ---------- 贴图 ----------
    def sprite_size(self, sid, h):
        pix = self._sprites[sid]
        return h * pix.width() / max(1, pix.height()), h

    def scaled_sprite(self, sid, w, h, device_scale):
        """按屏幕实际像素缓存缩好的贴图，避免每帧大图缩小。"""
        key = (sid, int(w * device_scale), int(h * device_scale))
        pix = self._scaled.get(key)
        if pix is None:
            pix = self._sprites[sid].scaled(max(1, key[1]), max(1, key[2]),
                                            Qt.AspectRatioMode.IgnoreAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)
            self._scaled.put(key, pix)
        return pix

    def _build_objects(self):
        objs = []
        sprites = self.art.get("sprites", {})
        for dec in self.art.get("decor", []):
            sid = dec.get("sprite")
            if not sid or dec.get("layer") == "ground":
                continue
            s = sprites[sid]
            x, y = dec["at"]
            objs.append(SpriteObject(sid, self._sprites[sid], x, y, float(s["h"]) * float(dec.get("scale", 1)),
                                     tuple(s.get("foot", SPRITE_FOOT)), bool(dec.get("flip"))))
        return objs

    def paint_object(self, p, obj, device_scale, opacity=1.0):
        pix = self.scaled_sprite(obj.sid, obj.rect.width(), obj.rect.height(), device_scale)
        p.save()
        p.setOpacity(opacity)
        if obj.flip:
            p.translate(obj.rect.center().x(), 0)
            p.scale(-1, 1)
            p.translate(-obj.rect.center().x(), 0)
        p.drawPixmap(obj.rect, pix, QRectF(pix.rect()))
        p.restore()

    # ---------- 地面层缓存 ----------
    def paint_ground_cached(self, p, view, scale, dpr, tilt=1.0):
        """把与 view（世界坐标矩形）相交的地面块画出来。p 已经变换到世界坐标（含纵向压缩 tilt）。"""
        cw, ch = self.graph.canvas
        sx, sy = round(scale * dpr, 3), round(scale * tilt * dpr, 3)
        x0, y0 = max(0, int(view.left() // CHUNK)), max(0, int(view.top() // CHUNK))
        x1 = min(int(math.ceil(cw / CHUNK)) - 1, int(view.right() // CHUNK))
        y1 = min(int(math.ceil(ch / CHUNK)) - 1, int(view.bottom() // CHUNK))
        if (sx, sy) != self._chunk_scale:
            # 换了缩放档位：别的档位的块短时间用不上，先腾出来
            self._chunk_scale = (sx, sy)
            self._chunks.drop_if(lambda k: k[2:] != (sx, sy))
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                key = (cx, cy, sx, sy)
                pix = self._chunks.get(key)
                if pix is None:
                    pix = self._render_chunk(cx, cy, sx, sy)
                    self._chunks.put(key, pix)
                rc = QRectF(cx * CHUNK, cy * CHUNK, CHUNK, CHUNK)
                span = CHUNK + CHUNK_BLEED * 2
                kx, ky = pix.width() / span, pix.height() / span
                src = QRectF(CHUNK_BLEED * kx, CHUNK_BLEED * ky, CHUNK * kx, CHUNK * ky)
                p.drawPixmap(rc, pix, src)

    def _render_chunk(self, cx, cy, sx, sy):
        span = CHUNK + CHUNK_BLEED * 2
        w, h = max(1, int(math.ceil(span * sx))), max(1, int(math.ceil(span * sy)))
        pix = QPixmap(w, h)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(w / span, h / span)
        p.translate(-cx * CHUNK + CHUNK_BLEED, -cy * CHUNK + CHUNK_BLEED)
        p.setClipRect(QRectF(cx * CHUNK - CHUNK_BLEED, cy * CHUNK - CHUNK_BLEED, span, span))
        self.paint(p)
        p.end()
        return pix

    def minimap(self, width):
        """整张地图的缩略图（只有地面层）。"""
        if self._minimap is None or self._minimap.width() != int(width):
            cw, ch = self.graph.canvas
            k = width / cw
            pix = QPixmap(int(width), int(ch * k))
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.scale(k, k)
            self.paint(p, detail=False)
            p.end()
            self._minimap = pix
        return self._minimap

    # 旧接口：整张地面层画成一张图（小地图用）
    def pixmap(self, scale, dpr):
        cw, ch = self.graph.canvas
        pix = QPixmap(max(1, int(cw * scale * dpr)), max(1, int(ch * scale * dpr)))
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(scale * dpr, scale * dpr)
        self.paint(p)
        p.end()
        return pix

    # ---------- 地面层 ----------
    def paint(self, p, detail=True):
        self.detail = detail
        self._land = None
        if self.has_terrain:
            self.paint_sea(p)
            for t in self.art["terrain"]:
                getattr(self, "paint_" + t["kind"])(p, t)
        else:
            self.paint_panel(p)
        if self.art.get("path_width"):
            self.paint_paths(p)
        for dec in sorted((d for d in self.art.get("decor", []) if not d.get("sprite")),
                          key=lambda d: d["at"][1]):
            paint_decor(p, dec)
        # 平铺在地上的贴图（桥、码头）进地面层缓存，角色会走在它们上面
        sprites = self.art.get("sprites", {})
        for dec in self.art.get("decor", []):
            if dec.get("sprite") and dec.get("layer") == "ground":
                s = sprites[dec["sprite"]]
                x, y = dec["at"]
                obj = SpriteObject(dec["sprite"], self._sprites[dec["sprite"]], x, y,
                                   float(s["h"]) * float(dec.get("scale", 1)), tuple(s.get("foot", SPRITE_FOOT)),
                                   bool(dec.get("flip")))
                self.paint_object(p, obj, 2.0)

    def texture_brush(self, key, fallback):
        pix = self._textures.get(key)
        if pix is None or pix.isNull():
            return QBrush(fallback)
        b = QBrush(pix)
        b.setTransform(QTransform.fromScale(TEX_SCALE, TEX_SCALE))
        return b

    def paint_panel(self, p):
        nodes = [self.graph.anchor(n) for n in self.graph.nodes]
        half = self.graph.tile / 2 + 14
        xs, ys = [x for x, _ in nodes], [y for _, y in nodes]
        rc = QRectF(min(xs) - half, min(ys) - half, max(xs) - min(xs) + half * 2, max(ys) - min(ys) + half * 2)
        edge = QColor(self.pal["panel_edge"])
        edge.setAlpha(200)
        p.setPen(QPen(edge, 2))
        panel = QColor(self.pal["panel"])
        panel.setAlpha(238)
        p.setBrush(panel)
        p.drawRoundedRect(rc, 22, 22)

    def paint_sea(self, p):
        cw, ch = self.graph.canvas
        rc = QRectF(0, 0, cw, ch)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.texture_brush("water", self.pal["sea_light"]))
        p.drawRoundedRect(rc, CORNER, CORNER)
        g = QRadialGradient(QPointF(cw * 0.5, ch * 0.5), max(cw, ch) * 0.62)
        light, deep = QColor(self.pal["sea_light"]), QColor(self.pal["sea_deep"])
        light.setAlpha(70 if self._textures.get("water") else 255)
        deep.setAlpha(200 if self._textures.get("water") else 255)
        g.setColorAt(0.0, light)
        g.setColorAt(0.75, deep)
        g.setColorAt(1.0, deep.darker(115))
        p.setBrush(g)
        p.drawRoundedRect(rc, CORNER, CORNER)
        if not self.detail:
            return
        rng = random.Random(7)
        foam = QColor(self.pal["foam"])
        foam.setAlpha(90)
        p.setPen(QPen(foam, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for _ in range(int(cw * ch / 9000)):
            x, y, w = rng.uniform(20, cw - 20), rng.uniform(20, ch - 20), rng.uniform(12, 30)
            p.drawArc(QRectF(x, y, w, w * 0.45), 20 * 16, 140 * 16)

    def _raised(self, p, path, cliff, top_brush, cliff_col, dark_col, texture, in_sea=True):
        """带悬崖厚度的地块：浅滩和浪花（在海里时）→ 崖壁 → 顶面。"""
        if in_sea:
            shallow = QColor(self.pal["sea_light"]).lighter(115)
            shallow.setAlpha(150)
            p.setPen(QPen(shallow, 90, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path.translated(0, cliff))
            foam = QColor(self.pal["foam"])
            foam.setAlpha(200)
            p.setPen(QPen(foam, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path.translated(0, cliff + 5))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(30, 50, 40, 50))
            p.drawPath(path.translated(6, cliff + 6))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.texture_brush("cliff", cliff_col))
        p.drawPath(path.translated(0, cliff))
        shade = QLinearGradient(0, 0, 0, 1)
        shade.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
        d1, d2 = QColor(dark_col), QColor(dark_col)
        d1.setAlpha(60)
        d2.setAlpha(150)
        shade.setColorAt(0, d1)
        shade.setColorAt(1, d2)
        p.setBrush(shade)
        p.drawPath(path.translated(0, cliff))

        p.setBrush(top_brush)
        p.drawPath(path)
        # 顶面边缘一圈亮边，像草坡的倒角
        edge = QColor(255, 255, 240, 70)
        p.setPen(QPen(edge, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        texture(path)

    def _grass_variation(self, p, path, seed):
        """纹理上压一层主色调，再叠大块柔和明暗，打散平铺的重复感。"""
        if self._textures.get("grass"):
            tint = QColor(self.pal["grass"])
            tint.setAlpha(110)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tint)
            p.drawPath(path)
        if not self.detail:
            return
        rng = random.Random(seed)
        rc = path.boundingRect()
        p.save()
        p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(int(rc.width() * rc.height() / 90000)):
            x, y = rng.uniform(rc.left(), rc.right()), rng.uniform(rc.top(), rc.bottom())
            r = rng.uniform(120, 320)
            col = QColor(255, 255, 210) if rng.random() < 0.5 else QColor(self.pal["grass_dark"]).darker(120)
            g = QRadialGradient(QPointF(x, y), r)
            col.setAlpha(42)
            g.setColorAt(0, col)
            col.setAlpha(0)
            g.setColorAt(1, col)
            p.setBrush(g)
            p.drawEllipse(QPointF(x, y), r, r)
        p.restore()

    def _grass_texture(self, p, path, seed):
        if not self.detail:
            return
        rng = random.Random(seed)
        rc = path.boundingRect()
        dark = QColor(self.pal["grass_dark"])
        dark.setAlpha(110 if self._textures.get("grass") else 150)
        light = QColor(self.pal["grass"]).lighter(118)
        p.setBrush(Qt.BrushStyle.NoBrush)
        density = 5200 if self._textures.get("grass") else 1400
        for _ in range(int(rc.width() * rc.height() / density)):
            x, y = rng.uniform(rc.left(), rc.right()), rng.uniform(rc.top(), rc.bottom())
            if not path.contains(QPointF(x, y)):
                continue
            if rng.random() < 0.6:
                p.setPen(QPen(dark, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x - 3, y), QPointF(x - 1, y - 6))
                p.drawLine(QPointF(x + 1, y), QPointF(x + 3, y - 6))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(light)
                p.drawEllipse(QPointF(x, y), 2.4, 1.5)
                p.setBrush(Qt.BrushStyle.NoBrush)

    def paint_island(self, p, t):
        path = smooth_closed(t["points"])
        self._land = path if self._land is None else self._land.united(path)
        cliff = float(t.get("cliff", 28))
        rim = float(t.get("rim", 20))

        def texture(pth):
            p.save()
            p.setClipPath(pth, Qt.ClipOperation.IntersectClip)
            p.setPen(QPen(self.texture_brush("sand", self.pal["sand"]), rim * 2, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(pth)
            p.restore()
            self._grass_variation(p, pth, 13)
            self._grass_texture(p, pth, 11)

        self._raised(p, path, cliff, self.texture_brush("grass", self.pal["grass"]),
                     self.pal["cliff"], self.pal["cliff_dark"], texture)

    def paint_plateau(self, p, t):
        """抬高的台地。texture 指定顶面纹理（比如主城的石板）；block 指定方块草地的格子大小。"""
        path = smooth_closed(t["points"])
        top = QColor(t.get("color", "#C6B9E4"))
        brush = self.texture_brush(t["texture"], top) if "texture" in t else QBrush(top)

        def texture(pth):
            if "texture" in t and "block" not in t:
                return
            # 一格一格的方块草地
            rng = random.Random(5)
            rc = pth.boundingRect()
            p.setPen(Qt.PenStyle.NoPen)
            u = int(t.get("block", 14))
            for gx in range(int(rc.left()), int(rc.right()), u):
                for gy in range(int(rc.top()), int(rc.bottom()), u):
                    if rng.random() < 0.3 and pth.contains(QPointF(gx + u / 2, gy + u / 2)):
                        p.setBrush(top.lighter(110) if rng.random() < 0.5 else top.darker(106))
                        p.drawRect(QRectF(gx, gy, u, u))

        cliff_col = QColor(t.get("cliff_color", top.darker(125).name()))
        self._raised(p, path, float(t.get("cliff", 16)), brush, cliff_col, cliff_col.darker(125), texture,
                     in_sea=False)

    def paint_sand(self, p, t):
        path = smooth_closed(t["points"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.texture_brush("sand", self.pal["sand"]))
        p.drawPath(path)

    def paint_patch(self, p, t):
        """地面色块：纹理或颜色，边缘柔和。"""
        path = smooth_closed(t["points"])
        if "texture" in t:
            brush = self.texture_brush(t["texture"], self.pal["grass"])
        else:
            brush = QBrush(QColor(t.get("color", "#8FBF7A")))
        alpha = float(t.get("alpha", 1.0))
        p.save()
        if self._land is not None:
            p.setClipPath(self._land, Qt.ClipOperation.IntersectClip)
        p.setPen(Qt.PenStyle.NoPen)
        for grow, a in ((26, 0.25), (14, 0.45), (0, 1.0)):
            p.setOpacity(alpha * a)
            if grow:
                p.setPen(QPen(brush, grow * 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(brush)
            p.drawPath(path)
        p.restore()

    def _water_fill(self, p, shape_painter, light, deep):
        p.setBrush(self.texture_brush("water", light))
        shape_painter()
        tint = QColor(deep)
        tint.setAlpha(110 if self._textures.get("water") else 0)
        p.setBrush(tint)
        shape_painter()

    def paint_lake(self, p, t):
        """湖：center + radius 画椭圆，或者 points 画任意轮廓。"""
        if "points" in t:
            shape = smooth_closed(t["points"])
            rc = shape.boundingRect()
            cx, cy, rx, ry = rc.center().x(), rc.center().y(), rc.width() / 2, rc.height() / 2
        else:
            (cx, cy), (rx, ry) = t["center"], t["radius"]
            shape = QPainterPath()
            shape.addEllipse(QPointF(cx, cy), rx, ry)
        p.setPen(QPen(self.texture_brush("sand", self.pal["sand"]), 26, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)
        p.setPen(Qt.PenStyle.NoPen)
        self._water_fill(p, lambda: p.drawPath(shape), self.pal["lake_light"], self.pal["lake"])
        g = QRadialGradient(QPointF(cx - rx * 0.2, cy - ry * 0.3), max(rx, ry))
        g.setColorAt(0, QColor(255, 255, 255, 60))
        g.setColorAt(1, QColor(20, 60, 110, 70))
        p.setBrush(g)
        p.drawPath(shape)
        if self.detail:
            p.setBrush(QColor(30, 70, 110, 70))
            rng = random.Random(int(cx + cy))
            for _ in range(3):
                p.drawEllipse(QPointF(cx + rng.uniform(-rx, rx) * 0.5, cy + rng.uniform(-ry, ry) * 0.5), 12, 5)

    def paint_river(self, p, t):
        pts = spline.sample([tuple(map(float, q)) for q in t["points"]])
        path = QPainterPath(QPointF(*pts[0]))
        for q in pts[1:]:
            path.lineTo(QPointF(*q))
        w = float(t.get("width", 60))
        cap, join = Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.texture_brush("sand", self.pal["sand"]), w + 26, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path)
        p.setPen(QPen(self.texture_brush("water", self.pal["lake_light"]), w, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path)
        tint = QColor(self.pal["lake"])
        tint.setAlpha(110 if self._textures.get("water") else 0)
        p.setPen(QPen(tint, w, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path)

    # ---------- 道路 ----------
    def _edge_path(self):
        """没有 [[road]] 的地图：按节点连线画平滑道路。"""
        g = self.graph
        prev = {}
        for nid, n in g.nodes.items():
            for t in n.next:
                prev.setdefault(t, nid)
        path = QPainterPath()
        for a, na in g.nodes.items():
            for b in na.next:
                p0 = QPointF(*g.anchor(prev.get(a, a)))
                p1, p2 = QPointF(*g.anchor(a)), QPointF(*g.anchor(b))
                p3 = QPointF(*g.anchor(g.nodes[b].next[0]))
                path.moveTo(p1)
                catmull_segment(path, p0, p1, p2, p3)
        return path

    def _road_path(self):
        path = QPainterPath()
        for poly in self.art.get("roads", []):
            path.moveTo(QPointF(*poly[0]))
            for q in poly[1:]:
                path.lineTo(QPointF(*q))
        return path

    def paint_paths(self, p):
        w = self.art["path_width"]
        path = self._road_path() if self.art.get("roads") else self._edge_path()
        edge = QColor(self.pal["path"]).darker(125)
        edge.setAlpha(140)
        cap, join = Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(edge, w + 8, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path.translated(0, 3))
        p.setPen(QPen(self.texture_brush("path", self.pal["path"]), w, Qt.PenStyle.SolidLine, cap, join))
        p.drawPath(path)
        if self._textures.get("path") or not self.detail:
            return
        rng = random.Random(9)
        pebble = QColor(self.pal["path"]).darker(112)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pebble)
        n = int(path.length() / 11)
        for i in range(n):
            pt = path.pointAtPercent(i / n)
            ang = rng.uniform(0, math.tau)
            off = rng.uniform(-w * 0.3, w * 0.3)
            p.drawEllipse(QPointF(pt.x() + math.cos(ang) * off, pt.y() + math.sin(ang) * off), 1.6, 1.2)
