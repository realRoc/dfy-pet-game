"""按 DiceSkin 画骰子。最终朝上（cube 是朝前）的一面只由传入的 face 决定。

- flat：平面圆角方块，掷骰时由窗口随机换面做装饰
- cube：真正的立方体，四元数插值旋转后正交投影，最后一帧朝前的面就是结果
"""
import math
import os
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPixmap, QPolygonF, QRadialGradient, QTransform

from .cube import FACE_NORMALS, orientation, q_rotate

# 每个点数的点位，单位是 pip_spread
PIPS = {
    1: [(0, 0)],
    2: [(-1, -1), (1, 1)],
    3: [(-1, -1), (0, 0), (1, 1)],
    4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
    5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
    6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)],
}
# cube：每个面在骰子本地坐标里的两条边方向
FACE_AXES = {
    1: ((1, 0, 0), (0, 1, 0)), 6: ((-1, 0, 0), (0, 1, 0)),
    3: ((0, 0, -1), (0, 1, 0)), 4: ((0, 0, 1), (0, 1, 0)),
    2: ((1, 0, 0), (0, 0, -1)), 5: ((1, 0, 0), (0, 0, 1)),
}
LIGHT = (-0.28, 0.30, 0.91)       # 光从左上偏正面来，结果面最亮
UNIT_SQUARE = QPolygonF([QPointF(-1, -1), QPointF(1, -1), QPointF(1, 1), QPointF(-1, 1)])


def ease_out_back(u):
    c = 1.4
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


def ease_out_cubic(u):
    return 1 - (1 - u) ** 3


def _shade(color, k):
    return QColor(min(255, int(color.red() * k)), min(255, int(color.green() * k)),
                  min(255, int(color.blue() * k)), color.alpha())


class DiceRenderer:
    def __init__(self, skin):
        self.skin = skin
        self.colors = {k: QColor(getattr(skin, k))
                       for k in ("body", "side", "border_hot", "border_idle", "pip", "pip_one")}
        self._faces = None
        self._from = self._to = 1
        self._axis, self._turns = (1, 0.4, 0.2), 2

    def begin_roll(self, result, current):
        """开始一次掷骰动画：从当前朝前的 current 转到 result。旋转轴只是装饰。"""
        self._from, self._to = current, result
        self._axis = (random.uniform(0.4, 1), random.uniform(-0.6, 0.6), random.uniform(-0.5, 0.5))
        self._turns = random.choice((1, 2))

    def paint(self, p, rc, face, phase="idle", t=0.0, hot=True):
        """phase: idle / rolling / settle；t 是该阶段已经过的秒数。"""
        if self.skin.style == "cube":
            self.paint_cube(p, rc, face, phase, t)
        else:
            self.paint_flat(p, rc, face, phase, t, hot)

    # ---------- flat ----------
    def face_pixmap(self, face):
        if not self.skin.face_dir:
            return None
        if self._faces is None:
            self._faces = {i: QPixmap(os.path.join(self.skin.face_dir, f"{i}.png")) for i in range(1, 7)}
        return self._faces[face]

    def paint_flat(self, p, rc, face, phase, t, hot):
        s = self.skin
        k = rc.width() / s.size
        rot, lift, scale = 0.0, 0.0, 1.0
        if phase == "rolling":
            fade = max(0.0, 1 - t / s.roll_time)
            rot = math.sin(t * 38) * 22 * fade
            lift = -abs(math.sin(t * 14)) * 18 * fade * k
        elif phase == "settle":
            u = min(1.0, t / s.settle_time)
            scale = 0.85 + 0.15 * ease_out_back(u)

        c = rc.center()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, s.shadow_alpha))
        p.drawEllipse(QPointF(c.x(), rc.bottom() + 6 * k), rc.width() * 0.42 * (1 + lift / (60 * k)), 7 * k)

        p.save()
        p.translate(c.x(), c.y() + lift)
        p.rotate(rot)
        p.scale(scale, scale)
        body = QRectF(-rc.width() / 2, -rc.height() / 2, rc.width(), rc.height())
        pix = self.face_pixmap(face)
        if pix is not None and not pix.isNull():
            p.drawPixmap(body, pix, QRectF(pix.rect()))
        else:
            border = self.colors["border_hot"] if hot else self.colors["border_idle"]
            p.setPen(QPen(border, s.border_width * k))
            p.setBrush(self.colors["body"])
            p.drawRoundedRect(body, s.radius * k, s.radius * k)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.colors["pip_one"] if face == 1 else self.colors["pip"])
            r = (s.pip_one_r if face == 1 else s.pip_r) * k
            d = s.pip_spread * k
            for px, py in PIPS[face]:
                p.drawEllipse(QPointF(px * d, py * d), r, r)
        p.restore()

    # ---------- cube ----------
    def cube_motion(self, phase, t):
        """返回 (旋转进度 e, 离地高度, 纵向缩放, 读点数高亮)。"""
        s = self.skin
        if phase == "rolling":
            if t < s.press_time:                        # 按下压缩
                return 0.0, 0.0, 1 - 0.14 * math.sin(math.pi / 2 * t / s.press_time), 0.0
            t -= s.press_time
            if t < s.spin_time:                         # 弹起旋转
                u = t / s.spin_time
                return ease_out_cubic(u), s.lift * 4 * u * (1 - u), 1 + 0.06 * math.sin(math.pi * u), 0.0
            u = min(1.0, (t - s.spin_time) / s.land_time)   # 落地回弹
            return 1.0, 8 * math.sin(math.pi * u), 1 - 0.1 * math.sin(math.pi * u), 0.0
        if phase == "settle":                           # 读点数
            u = min(1.0, t / s.read_time)
            return 1.0, 0.0, 1.0, 1 - u
        return 1.0, 0.0, 1.0, 0.0

    def paint_cube(self, p, rc, face, phase, t):
        s = self.skin
        k = rc.width() / s.size
        if phase != "rolling":
            self._from = self._to = face
        e, height, sy, glow = self.cube_motion(phase, t)
        q = orientation(self._from, self._to, e, self._axis, self._turns)
        a = rc.width() * 0.40                       # 半边长，投影后外轮廓约等于 rc
        cx, ground = rc.center().x(), rc.center().y() + a * 1.05

        p.setPen(Qt.PenStyle.NoPen)
        lift_k = 1 - min(1.0, height / max(1.0, s.lift)) * 0.45
        p.setBrush(QColor(20, 40, 60, int(s.shadow_alpha * lift_k)))
        p.drawEllipse(QPointF(cx + 4 * k, ground + 2 * k), a * 1.15 * lift_k, a * 0.32 * lift_k)
        if glow > 0:
            g = QRadialGradient(QPointF(cx, ground - a), a * 1.8)
            g.setColorAt(0, QColor(255, 226, 140, int(150 * glow)))
            g.setColorAt(1, QColor(255, 226, 140, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, ground - a), a * 1.8, a * 1.8)

        p.save()
        # 以底部为支点做挤压，看起来像压在地上
        p.translate(cx, ground - height * k)
        p.scale(1 + (1 - sy) * 0.6, sy)
        p.translate(0, -a * 1.05)
        faces = []
        for f, n in FACE_NORMALS.items():
            nz = q_rotate(q, n)
            if nz[2] <= 0.02:
                continue
            u_ax, v_ax = FACE_AXES[f]
            corners = []
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                v = tuple(a * (n[i] + su * u_ax[i] + sv * v_ax[i]) for i in range(3))
                x, y, _ = q_rotate(q, v)
                corners.append(QPointF(x, -y))
            light = max(0.0, sum(nz[i] * LIGHT[i] for i in range(3)))
            faces.append((nz[2], f, QPolygonF(corners), 0.80 + 0.22 * light))
        faces.sort(key=lambda x: x[0])
        for _, f, quad, bright in faces:
            tr = QTransform.quadToQuad(UNIT_SQUARE, quad)
            if tr is None:
                continue
            p.save()
            p.setTransform(tr, True)
            p.setBrush(_shade(self.colors["side"], bright))
            p.drawRoundedRect(QRectF(-1.02, -1.02, 2.04, 2.04), 0.36, 0.36)
            p.setBrush(_shade(self.colors["body"], bright))
            p.drawRoundedRect(QRectF(-0.88, -0.88, 1.76, 1.76), 0.30, 0.30)
            self._pips(p, f, bright, k / a)
            p.restore()
        p.restore()

    def _pips(self, p, f, bright, unit):
        s = self.skin
        d = s.pip_spread * unit
        r = (s.pip_one_r if f == 1 else s.pip_r) * unit
        base = self.colors["pip_one"] if f == 1 else self.colors["pip"]
        for px, py in PIPS[f]:
            c = QPointF(px * d, py * d)
            g = QRadialGradient(QPointF(c.x() + r * 0.25, c.y() + r * 0.3), r * 1.1)
            g.setColorAt(0, _shade(base, 0.85 * bright))
            g.setColorAt(0.75, _shade(base, 1.0 * bright))
            g.setColorAt(1, _shade(base.lighter(150), bright))
            p.setBrush(g)
            p.drawEllipse(c, r, r)
