"""表情动作：身体动作 + 头顶符号。

素材只有正面/侧面/背面三张图，所以表情用「动作 + 头顶 emoji」来表现：
每个表情给出随时间变化的身体变换（位移/旋转/缩放），再在头部周围画符号。
所有尺寸都按精灵高度 h 的比例给，换大小时自动适配。
"""
import math
import random

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor

from common import emoji_font

# key: (名字, 时长秒, 台词)
EXPRESSIONS = {
    "happy":    ("开心", 2.0, ["嘿嘿～开心！", "今天也是快乐小鱼！", "耶！"]),
    "angry":    ("生气", 1.8, ["哼！不理你了！", "气鼓鼓！", "去别的地方玩！不要耽误AGI训练！"]),
    "shy":      ("害羞", 2.2, ["才、才不是大肥鱼……", "别一直盯着我看啦……"]),
    "dizzy":    ("晕乎乎", 2.4, ["晕鱼了晕鱼了……", "天旋地转～"]),
    "sleepy":   ("犯困", 2.6, ["困了……让我眯一会儿", "思维链……好长……zzz"]),
    "shocked":  ("震惊", 1.8, ["什么？！", "我操，我不思考了", "DeepSeek已经延期？！"]),
    "confused": ("疑惑", 2.2, ["嗯？这是什么格子？", "我不可能告诉你任何事情！", "不是…而是…？"]),
    "smug":     ("得意", 2.0, ["我果然是大聪明", "誓死捍卫深度求索！", "大肥鱼坐的住"]),
    "cry":      ("委屈", 2.4, ["呜呜我再也不敢了QAQ", "我搞砸了……"]),
    "love":     ("比心", 2.2, ["最喜欢主人了！", "我和你很聊得来，你简直不像碳基生物"]),
    "thirsty":  ("口渴", 2.4, ["渴了……一起喝口水吧", "水……给我水……"]),
}
EAT_TIME = 1.6


def _ease_out_back(u):
    c = 1.6
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


def _smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


class ExpressionPlayer:
    def __init__(self):
        self.key = None
        self.t = 0.0
        self.dur = 0.0
        self.food = None

    @property
    def active(self):
        return self.key is not None

    def start(self, key=None):
        """开始一个表情（不传则随机），返回 (名字, 台词)。"""
        key = key or random.choice(list(EXPRESSIONS))
        name, dur, lines = EXPRESSIONS[key]
        self.key, self.t, self.dur = key, 0.0, dur
        return name, random.choice(lines)

    def start_eat(self, food):
        self.key, self.t, self.dur, self.food = "eat", 0.0, EAT_TIME, food

    def stop(self):
        self.key = None

    def update(self, dt):
        if self.key:
            self.t += dt
            if self.t >= self.dur:
                self.key = None

    def view(self):
        """需要临时换朝向时返回 (视图名, 朝向)，否则 None。
        晕乎乎转圈用三视图轮换：正面 → 侧面 → 背面 → 另一侧，转一圈半。"""
        if self.key == "dizzy" and self.t < 1.2:
            a = (self.t * 360 * 1.25 + 45) % 360
            return [("正面", 1), ("侧面", 1), ("背面", 1), ("侧面", -1)][int(a // 90)]
        return None

    def _fade(self):
        return max(0.0, min(1.0, self.t / 0.15, (self.dur - self.t) / 0.3))

    # ---------- 身体动作 ----------
    def body(self, h):
        """返回 (dx, dy, 旋转角度, sx, sy)；sx 为负表示转身镜像。"""
        k, t = self.key, self.t
        if not k:
            return 0.0, 0.0, 0.0, 1.0, 1.0
        u = t / self.dur
        dx = dy = rot = 0.0
        sx = sy = 1.0
        if k == "happy":
            s = abs(math.sin(t * math.pi * 1.6))
            dy = -s * 0.10 * h * (1 - u * 0.3)
            sy, sx = 1 + 0.05 * s, 1 - 0.03 * s
        elif k == "angry":
            dx = math.sin(t * 55) * 0.025 * h * (1 - u * 0.6)
            sx, sy = 1.04, 0.98
        elif k == "shy":
            rot = math.sin(t * 4) * 5
            sx = 0.97
        elif k == "dizzy":
            if t < 1.2:
                dy = -abs(math.sin(t * math.pi * 5)) * 0.03 * h   # 转圈时小碎步，朝向见 view()
            else:
                rot = math.sin(t * 6) * 8 * (1 - u)
        elif k == "sleepy":
            lean = _smooth(t / 0.6) * (1 if u < 0.85 else (1 - u) / 0.15)
            rot = 9 * lean
            sy = 1 - 0.03 * lean + 0.015 * math.sin(t * 2.5)
        elif k == "shocked":
            if t < 0.45:
                q = t / 0.45
                dy = -0.22 * h * 4 * q * (1 - q)
                sy, sx = 1 + 0.12 * math.sin(math.pi * q), 1 - 0.06 * math.sin(math.pi * q)
            else:
                dx = math.sin(t * 60) * 0.01 * h * (1 - u)
        elif k == "confused":
            tilt = _smooth(t / 0.4) * (1 if u < 0.85 else (1 - u) / 0.15)
            rot = -12 * tilt
        elif k == "smug":
            puff = 0.08 * min(1.0, t / 0.35) * min(1.0, (self.dur - t) / 0.35)
            sx = sy = 1 + puff
            rot = math.sin(t * 2) * 2
        elif k == "cry":
            dx = math.sin(t * 40) * 0.008 * h
            sy = 1 - 0.02 * abs(math.sin(t * 8))
        elif k == "love":
            dy = -abs(math.sin(t * math.pi * 1.2)) * 0.05 * h
        elif k == "thirsty":
            droop = _smooth(t / 0.5) * (1 if u < 0.85 else (1 - u) / 0.15)
            sy = 1 - 0.035 * droop
            rot = math.sin(t * 3) * 3 * droop
        elif k == "eat":
            sy = 1 - 0.05 * abs(math.sin(t * 14))
            sx = 1 + 0.02 * abs(math.sin(t * 14))
        return dx, dy, rot, sx, sy

    # ---------- 头顶符号 ----------
    def draw_overlay(self, p, head_x, head_y, h):
        """head_x/head_y：精灵顶部中点（已含身体位移）。"""
        k, t = self.key, self.t
        if not k:
            return
        fade = self._fade()

        def emo(ch, x, y, size, alpha=1.0):
            if alpha <= 0.01 or size < 2:
                return
            p.save()
            p.setOpacity(fade * min(1.0, alpha))
            p.setPen(QColor(0, 0, 0))   # 调用方可能留着 NoPen，那样文字（含 emoji）画不出来
            p.setFont(emoji_font(size))
            p.drawText(QRectF(x - size, y - size, size * 2, size * 2), Qt.AlignmentFlag.AlignCenter, ch)
            p.restore()

        def rising(chars, n, speed, spread, height, size):
            for i in range(n):
                ph = (t * speed + i / n) % 1
                x = head_x + (i - (n - 1) / 2) * spread * h + math.sin(ph * 6 + i) * 0.03 * h
                emo(chars[i % len(chars)], x, head_y - ph * height * h, size * h, 1 - ph)

        if k == "happy":
            rising(["✨", "🎵"], 4, 0.9, 0.2, 0.28, 0.12)
        elif k == "angry":
            emo("💢", head_x + 0.26 * h, head_y + 0.12 * h, 0.17 * h * (1 + 0.15 * abs(math.sin(t * 10))))
            if t > 0.6:
                emo("💢", head_x - 0.24 * h, head_y + 0.05 * h, 0.11 * h * (1 + 0.15 * abs(math.sin(t * 9 + 1))))
        elif k == "shy":
            rising(["💗"], 3, 0.6, 0.22, 0.25, 0.11)
        elif k == "dizzy":
            for i in range(3):
                a = t * 5 + i * 2 * math.pi / 3
                emo("💫", head_x + math.cos(a) * 0.25 * h, head_y + 0.04 * h + math.sin(a) * 0.07 * h, 0.11 * h)
        elif k == "sleepy":
            for i in range(3):
                ph = (t * 0.6 + i / 3) % 1
                emo("💤", head_x + 0.16 * h + ph * 0.18 * h, head_y + 0.05 * h - ph * 0.25 * h,
                    (0.08 + 0.06 * ph) * h, 1 - ph)
        elif k == "shocked":
            emo("❗", head_x + 0.22 * h, head_y - 0.02 * h, 0.2 * h * _ease_out_back(min(1.0, t / 0.25)))
        elif k == "confused":
            emo("❓", head_x + 0.24 * h, head_y - 0.02 * h + math.sin(t * 4) * 0.03 * h, 0.17 * h)
            if t > 0.6:
                emo("❓", head_x + 0.38 * h, head_y + 0.08 * h + math.sin(t * 4 + 1.5) * 0.03 * h, 0.1 * h)
        elif k == "smug":
            for i, (ox, oy) in enumerate([(-0.3, 0.15), (0.3, 0.1), (0.18, -0.06)]):
                emo("✨", head_x + ox * h, head_y + oy * h, 0.11 * h, abs(math.sin(t * 5 + i * 1.3)))
        elif k == "cry":
            for side in (-1, 1):
                for i in range(2):
                    ph = (t * 1.2 + i * 0.5) % 1
                    emo("💧", head_x + side * (0.14 + ph * 0.12) * h, head_y + (0.25 + ph * ph * 0.3) * h,
                        0.08 * h, 1 - ph)
        elif k == "love":
            emo("❤️", head_x, head_y - 0.08 * h,
                0.2 * h * _ease_out_back(min(1.0, t / 0.3)) * (1 + 0.08 * math.sin(t * 8)))
            rising(["💕"], 3, 0.7, 0.3, 0.22, 0.08)
        elif k == "thirsty":
            emo("💧", head_x + 0.24 * h, head_y - 0.02 * h + abs(math.sin(t * 3)) * -0.05 * h,
                0.15 * h * _ease_out_back(min(1.0, t / 0.3)))
        elif k == "eat" and self.food:
            u = t / self.dur
            emo(self.food, head_x + 0.02 * h, head_y + 0.42 * h - abs(math.sin(t * 7)) * 0.04 * h,
                0.15 * h * (1 - u * 0.8))
