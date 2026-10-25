"""按 DiceSkin 画骰子。最终朝上的一面只由传入的 face 决定。"""
import math
import os

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QPixmap

# 每个点数的点位，单位是 pip_spread
PIPS = {
    1: [(0, 0)],
    2: [(-1, -1), (1, 1)],
    3: [(-1, -1), (0, 0), (1, 1)],
    4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
    5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
    6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)],
}


def ease_out_back(u):
    c = 1.4
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


class DiceRenderer:
    def __init__(self, skin):
        self.skin = skin
        self.colors = {k: QColor(getattr(skin, k))
                       for k in ("body", "border_hot", "border_idle", "pip", "pip_one")}
        self._faces = None

    def face_pixmap(self, face):
        if not self.skin.face_dir:
            return None
        if self._faces is None:
            self._faces = {i: QPixmap(os.path.join(self.skin.face_dir, f"{i}.png")) for i in range(1, 7)}
        return self._faces[face]

    def paint(self, p, rc, face, phase="idle", t=0.0, hot=True):
        """phase: idle / rolling / settle；t 是该阶段已经过的秒数。"""
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
