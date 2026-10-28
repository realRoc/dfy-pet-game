"""喝水提醒：到点了大肥鱼提醒人类喝水，不理她就一级一级加码，最后扔大水、砸碎屏幕、气跑，过一会儿再回来。

几块：
- WaterReminder：计时和升级的状态机，不碰界面，方便测。人在电脑前才计时（键鼠空闲 5 分钟以上算不在），
  夜里不提醒，跟练、拖拽、聊天时先不打扰，等空下来再说。
- 片段：content/water/clips/ 里 Seedance 生成的透明视频（怎么来的见 tools/make_water_clips.py），
  「示范喝水」用跟练动画的 drink。都从正面站姿开始、回到正面站姿，只有气跑那段停在侧面站姿、返场两段从侧面站姿开始，
  好接上平时走路的侧面图。没装 PyAV 或素材缺失时换成 expressions 里的表情。
- ShatterOverlay：扔大水那一下：大瓶水转着飞向屏幕、玻璃裂开、水花溅在玻璃上顺着裂缝往下流。
  一层全屏透明窗口，点得穿，不挡干活，几秒后淡掉。

台词借的梗：大水理论（1.5L 大瓶水、像要去干架）、DeepSleep / 服务器暂时不可用、
新版本太抠门（话变少、语气变冷）、B 站鱼灾「本鲸记下了」、先吃饭后干活、深度思考（用时 xx 分钟）。
"""
import ctypes
import datetime
import math
import os
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

import clips as clip_lib
import workout
from common import BUNDLE_DIR, IS_MAC, IS_WIN, emoji_font, ui_font

CLIP_DIR = os.path.join(BUNDLE_DIR, "content", "water", "clips")
CLIP_FADE = 0.15

INTERVALS = [30, 45, 60, 90]   # 分钟
LEVEL_GAP = 300      # 每一级之间隔几秒：到点、+5、+10、+15 分钟
SNOOZE = 600         # 「等会儿」再等几秒
GOAL = 8             # 一天几杯
IDLE_PAUSE = 300     # 键鼠空闲这么久算人不在，停止计时
AWAY_LONG = 900      # 离开这么久回来，先提醒一次
QUIET = (22, 9)      # 这段时间不提醒
AWAY_SECS = (180, 300)   # 气跑以后多久回来
COLD_SECS = 600      # 回来时还没喝：抠门模式多久
THROW_AT = 3.9       # water_throw 里水瓶飞到镜头前、整幅挡住画面的时刻（秒）；换成表情时用 THROW_AT_EXPR
THROW_AT_EXPR = 0.9

# 每一级播哪段（同一级有几段时随机挑，不和上次重样）
LEVEL_CLIPS = {1: ["water_offer", "water_offer_b", "water_offer_b2"], 2: ["drink"], 3: ["water_knock"], 4: ["water_throw"]}
# 片段打不开时换成的表情
FALLBACK = {
    "water_offer": "thirsty", "water_offer_b": "thirsty", "water_offer_b2": "thirsty", "drink": "thirsty", "water_knock": "angry",
    "water_throw": "angry", "water_leave": "angry", "water_return_sulk": "angry",
    "water_return_makeup": "love", "water_cheers": "happy",
}

LINES = {
    1: ["该喝水啦～💧", "已深度思考（用时 {m} 分钟）：你该喝水了", "本鲸提醒：喝口水再干活",
        "先喝水后干活，大肥鱼说的", "喝口水吧，一口就行～"],
    "welcome": ["欢迎回来！先喝口水～", "回来啦？先喝口水再干活！"],
    2: ["看，像这样，咕嘟咕嘟——", "示范一遍：拿起杯子，喝。", "你不喝我先喝了啊！"],
    3: ["咚咚咚！有人吗？该喝水了！", "严肃实践大水理论！", "成功的人桌上都有大水。", "弱者才喝饮料，强者都喝大水！"],
    4: ["不理我是吧——", "大水攻击！！", "这瓶大水你接好了！"],
    "leave": ["本鲸记下了。", "我去评论区说你坏话了！", "哼，不理你了！", "我去吃饭了，喝完告诉我就行！"],
    "away_drank": ["（远处传来）……哼，这还差不多。"],
    "busy": ["大肥鱼服务器暂时不可用", "服务器繁忙，请稍后再试。"],
    "sulk": ["……喝吧。", "哼，水给你放这了。", "……省 token，不说了。"],
    "makeup": ["……那、那就原谅你了", "喝了就好～本鲸大人有大量", "这才对嘛！"],
    "cheers": ["干杯！今天第 {n}/{goal} 杯～", "咕嘟！今天 {n}/{goal} 杯", "好耶！今天 {n}/{goal} 杯了"],
    "goal": ["{goal} 杯达成！严肃实践大水理论！", "今天 {n} 杯！你就是大水理论本论！"],
    "late": ["现在才喝？哼！", "晚了！……不过喝了就好。"],
    "cold": ["嗯。", "哦。", "喝水。", "省 token 中。", "……"],
    "cold_end": ["……行吧，原谅你了。"],
    "snooze": ["那……就 10 分钟哦", "说好的 10 分钟！本鲸记下了"],
}
_last_line = {}


def line(kind, **fmt):
    """挑一句台词，不和这类上一句重样。"""
    pool = LINES[kind]
    choices = [s for s in pool if s != _last_line.get(kind)] or pool
    s = random.choice(choices)
    _last_line[kind] = s
    return s.format(**fmt) if fmt else s


# ---------- 人在不在 ----------
_cg = None


def user_idle_seconds():
    """键盘鼠标多久没动了（秒）。macOS 用 CoreGraphics，Windows 用 GetLastInputInfo，其他系统当作一直在。"""
    global _cg
    try:
        if IS_MAC:
            if _cg is None:
                _cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
                f = _cg.CGEventSourceSecondsSinceLastEventType
                f.restype, f.argtypes = ctypes.c_double, [ctypes.c_int32, ctypes.c_uint32]
            # kCGEventSourceStateCombinedSessionState、kCGAnyInputEventType
            return max(0.0, _cg.CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF))
        if IS_WIN:
            class LastInput(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            info = LastInput(ctypes.sizeof(LastInput), 0)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)
    except Exception as e:
        print("读空闲时间失败:", e)
    return 0.0


# ---------- 状态机 ----------
class WaterReminder:
    """phase：
    - wait：等下一次。人在电脑前才计时，到点了（且不忙、不在夜里）就发 ("level", 1, 是否刚回来)
    - remind：正在提醒，第 1~3 级；每隔 LEVEL_GAP 秒升一级
    - finale：第 4 级，扔大水、气跑，桌宠演完了调 left()
    - away：不在，AWAY_SECS 秒后发 ("return", 不在时喝没喝)
    - back：返场中，桌宠演完了调 returned()
    配置存在 cfg 里：water_on、water_interval（分钟）、water_quiet（夜里不提醒）、water_mute（这天别提醒了）、
    water_cups（{"date", "n"}，今天喝了几杯）。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.phase = "wait"
        self.level = 0
        self.elapsed = 0.0       # 上次喝水 / 上一轮提醒以来，人在电脑前过了几秒
        self.since = 0.0         # 这一级 / 离开以来过了几秒
        self.away_for = 0.0
        self.drank_away = False  # 扔完大水到回来之间喝了没有
        self.cold = 0.0          # 抠门模式还剩几秒
        self.idle_peak = 0.0     # 这次离开电脑多久了

    # ----- 配置 -----
    @property
    def enabled(self):
        return bool(self.cfg.get("water_on", True))

    @property
    def interval(self):
        return 60.0 * self.cfg.get("water_interval", 45)

    def quiet(self, now):
        start, end = QUIET
        return bool(self.cfg.get("water_quiet", True)) and (now.hour >= start or now.hour < end)

    def muted(self, now):
        return self.cfg.get("water_mute") == now.date().isoformat()

    def cups(self, now=None):
        now = now or datetime.datetime.now()
        c = self.cfg.get("water_cups") or {}
        return c.get("n", 0) if c.get("date") == now.date().isoformat() else 0

    # ----- 计时 -----
    def update(self, dt, idle=0.0, busy=False, now=None):
        """往前走 dt 秒，返回这一下要演的事：("level", 级别, 是否刚回来) / ("return", 不在时喝没喝)。"""
        now = now or datetime.datetime.now()
        self.cold = max(0.0, self.cold - dt)
        if self.phase == "away":
            self.since += dt
            if self.since >= self.away_for:
                self.phase = "back"
                return [("return", self.drank_away)]
            return []
        if self.phase in ("finale", "back"):
            return []
        if not self.enabled or self.muted(now) or self.quiet(now):
            if self.phase == "remind":
                self._reset()
            return []
        if idle >= IDLE_PAUSE:
            self.idle_peak = max(self.idle_peak, idle)
            return []
        welcome = self.idle_peak >= AWAY_LONG
        self.idle_peak = 0.0
        if self.phase == "wait":
            self.elapsed += dt
            if welcome and self.elapsed >= self.interval / 2:
                self.elapsed = max(self.elapsed, self.interval)
            if self.elapsed >= self.interval and not busy:
                self.phase, self.level, self.since = "remind", 1, 0.0
                return [("level", 1, welcome)]
        elif self.phase == "remind":
            self.since += dt
            if self.since >= LEVEL_GAP and not busy:
                return [self._raise(self.level + 1)]
        return []

    def _raise(self, level):
        self.level, self.since = level, 0.0
        if level >= 4:
            self.phase, self.drank_away = "finale", False
        else:
            self.phase = "remind"
        return ("level", level, False)

    def _reset(self):
        self.phase, self.level, self.since, self.elapsed = "wait", 0, 0.0, 0.0

    # ----- 人类的回应 -----
    def drink(self, now=None):
        """人类喝了。返回 (情形, 今天第几杯, 是不是从抠门模式里出来)；情形：
        "cheers" 平时 / 提醒中喝的，"late" 扔大水气跑的路上、不在的时候、返场路上喝的（等她回来再和好）。"""
        now = now or datetime.datetime.now()
        n = self.cups(now) + 1
        self.cfg["water_cups"] = {"date": now.date().isoformat(), "n": n}
        was_cold, self.cold = self.cold > 0, 0.0
        if self.phase in ("finale", "away", "back"):
            self.drank_away = True
            return "late", n, was_cold
        self._reset()
        return "cheers", n, was_cold

    def snooze(self):
        """「等会儿」：这一轮作罢，SNOOZE 秒后从第 1 级重来。"""
        if self.phase == "remind":
            self._reset()
            self.elapsed = max(0.0, self.interval - SNOOZE)
            return True
        return False

    def force(self, level):
        """菜单里的预览：直接跳到某一级。"""
        if self.phase in ("finale", "away", "back"):
            return None
        return self._raise(level)

    def left(self):
        """气跑出屏幕了。"""
        self.phase, self.since = "away", 0.0
        self.away_for = random.uniform(*AWAY_SECS)

    def returned(self):
        """返场演完了：没喝的话进抠门模式。"""
        if not self.drank_away:
            self.cold = COLD_SECS
        self.drank_away = False
        self._reset()


# ---------- 素材 ----------
_LIB = False


def library():
    """喝水片段；没装 PyAV 或素材缺失返回 None。"""
    global _LIB
    if _LIB is False:
        _LIB = clip_lib.load_library(CLIP_DIR, CLIP_FADE) if os.path.isdir(CLIP_DIR) else None
    return _LIB


def clip_source(name):
    """这段片段在哪套素材里；没有返回 None（换成 FALLBACK 里的表情）。"""
    lib = workout.clip_library() if name == "drink" else library()
    return lib if lib is not None and name in lib.clips else None


def pick_clip(level, last=None):
    names = LEVEL_CLIPS[level]
    have = [n for n in names if clip_source(n)] or names
    return random.choice([n for n in have if n != last] or have)


# ---------- 头顶符号 ----------
def draw_fx(p, fx, t, head_x, head_y, h):
    """angry：气跑路上头顶的 💢；cold：抠门模式头顶飘的「省 token 中」。"""
    if not fx:
        return
    p.save()
    if fx == "angry":
        s = 0.15 * h * (1 + 0.18 * abs(math.sin(t * 9)))
        p.setPen(QColor(0, 0, 0))
        p.setFont(emoji_font(s))
        p.drawText(QRectF(head_x + 0.22 * h - s, head_y + 0.1 * h - s, 2 * s, 2 * s), Qt.AlignmentFlag.AlignCenter, "💢")
    elif fx == "cold":
        f = ui_font(max(9, int(0.065 * h)))
        p.setFont(f)
        p.setPen(QColor(120, 128, 150, 200))
        y = head_y - 0.02 * h + math.sin(t * 1.6) * 0.012 * h
        p.drawText(QRectF(head_x - 0.5 * h, y - 0.06 * h, h, 0.08 * h), Qt.AlignmentFlag.AlignCenter, "省 token 中…")
    p.restore()


# ---------- 大水 ----------
def draw_bottle(p, H, alpha=1.0):
    """以瓶子中心为原点画一桶高 H 的大水：和 water_throw 片段里扔出来的一样是桶装水——
    圆肩粗桶身、短瓶颈蓝盖子、两道加强筋，中间一圈蓝标签上写「大水」，满满一桶水。"""
    W = 0.66 * H
    top = -H / 2
    p.save()
    p.setOpacity(p.opacity() * alpha)
    body = QPainterPath()
    body.addRoundedRect(QRectF(-W / 2, top + 0.22 * H, W, 0.78 * H), 0.16 * W, 0.16 * W)
    shoulder = QPainterPath()
    shoulder.moveTo(-0.13 * W, top + 0.08 * H)
    shoulder.lineTo(0.13 * W, top + 0.08 * H)
    shoulder.cubicTo(0.16 * W, top + 0.16 * H, W / 2, top + 0.14 * H, W / 2, top + 0.3 * H)
    shoulder.lineTo(-W / 2, top + 0.3 * H)
    shoulder.cubicTo(-W / 2, top + 0.14 * H, -0.16 * W, top + 0.16 * H, -0.13 * W, top + 0.08 * H)
    jug = body.united(shoulder)
    glass = QLinearGradient(-W / 2, 0, W / 2, 0)
    glass.setColorAt(0, QColor(200, 232, 255, 180))
    glass.setColorAt(0.5, QColor(232, 246, 255, 120))
    glass.setColorAt(1, QColor(170, 210, 245, 180))
    p.setPen(QPen(QColor(70, 130, 210, 220), max(1.0, 0.012 * H)))
    p.setBrush(glass)
    p.drawPath(jug)
    water = QPainterPath()
    water.addRect(QRectF(-W, top + 0.24 * H, 2 * W, H))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(95, 170, 240, 130))
    p.drawPath(jug.intersected(water))
    p.setPen(QPen(QColor(70, 130, 210, 150), max(1.0, 0.01 * H)))   # 加强筋
    for y in (0.36, 0.86):
        p.drawLine(QPointF(-W / 2, top + y * H), QPointF(W / 2, top + y * H))
    label = QRectF(-W / 2, top + 0.5 * H, W, 0.22 * H)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(38, 104, 220, 235))
    p.drawRect(label)
    p.setFont(ui_font(max(6, int(0.12 * H)), bold=True))
    p.setPen(QColor(255, 255, 255))
    p.drawText(label, Qt.AlignmentFlag.AlignCenter, "大水")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 120))
    p.drawRoundedRect(QRectF(-0.38 * W, top + 0.28 * H, 0.07 * W, 0.64 * H), 0.035 * W, 0.035 * W)
    p.setBrush(QColor(30, 80, 170, 240))
    p.drawRoundedRect(QRectF(-0.15 * W, top, 0.3 * W, 0.09 * H), 0.04 * W, 0.04 * W)
    p.restore()


# ---------- 碎屏 ----------
def _cracks(rng, R):
    """以撞击点为原点的裂纹：放射状主裂纹（带分叉）、两圈环状裂纹、中心的碎片。
    每条线是 [(x, y, 离撞击点多远), ...]，长出来的时候按距离一截一截画。"""
    lines = []
    n = rng.randint(11, 15)
    rays = []
    for i in range(n):
        a = 2 * math.pi * (i + rng.uniform(-0.3, 0.3)) / n
        length = R * rng.uniform(0.55, 1.0)
        pts, r = [(0.0, 0.0, 0.0)], 0.0
        while r < length:
            r += R * rng.uniform(0.04, 0.09)
            a += rng.uniform(-0.18, 0.18)
            pts.append((math.cos(a) * r, math.sin(a) * r, r))
            if r > 0.2 * R and rng.random() < 0.12:
                b = a + rng.choice((-1, 1)) * rng.uniform(0.35, 0.7)
                br, bpts = r, [pts[-1]]
                for _ in range(rng.randint(2, 4)):
                    br += R * rng.uniform(0.04, 0.08)
                    b += rng.uniform(-0.2, 0.2)
                    bpts.append((pts[-1][0] + math.cos(b) * (br - r), pts[-1][1] + math.sin(b) * (br - r), br))
                lines.append(bpts)
        lines.append(pts)
        rays.append(pts)
    for _ in range(rng.randint(16, 22)):   # 撞击点周围一圈细碎的短裂纹
        a, r = rng.uniform(0, 2 * math.pi), R * rng.uniform(0.04, 0.14)
        lines.append([(0.0, 0.0, 0.0), (math.cos(a) * r, math.sin(a) * r, r)])
    for frac in (0.05, 0.1, 0.17, 0.27, 0.4):
        ring_r = frac * R
        hits = []
        for pts in rays:
            hit = min(pts, key=lambda q: abs(q[2] - ring_r))
            hits.append(hit)
        for a, b in zip(hits, hits[1:] + hits[:1]):
            if rng.random() < (0.15 if frac < 0.2 else 0.35):
                continue
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            k = rng.uniform(0.9, 1.12)
            lines.append([a, (mx * k, my * k, ring_r), b])
    shards = []
    for a, b in zip(rays, rays[1:] + rays[:1]):
        if rng.random() < 0.55:
            pa = min(a, key=lambda q: abs(q[2] - 0.12 * R))
            pb = min(b, key=lambda q: abs(q[2] - 0.12 * R))
            shards.append(((0.0, 0.0), (pa[0], pa[1]), (pb[0], pb[1]), rng.randint(25, 70)))
    return lines, shards


class ShatterOverlay(QWidget):
    """扔大水那一下，盖在整块屏幕上：
    0 ~ FLY 秒：大水从她头顶转着飞过来，越来越大
    撞上的一刻：闪白、屏幕抖一下、裂纹 0.18 秒内长满、水花往外溅，瓶子弹回去掉下去
    之后：水顺着裂缝往下流，停 HOLD 秒，FADE 秒淡掉，自己关掉。
    点得穿（WindowTransparentForInput），不抢焦点。坐标都是这块屏幕里的。"""
    FLY = 0.55
    HOLD = 5.5
    FADE = 1.0

    def __init__(self, geo, start, impact, h, on_impact=None, seed=None):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        if IS_WIN:
            flags |= Qt.WindowType.Tool
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(geo)
        origin = QPointF(geo.topLeft())
        self.start, self.impact, self.h = QPointF(start) - origin, QPointF(impact) - origin, h
        side = min(geo.width(), geo.height())
        self.big = 0.5 * side           # 撞上时瓶子多高
        self.R = 0.45 * side            # 裂纹最长多长
        rng = random.Random(seed)
        self.lines, self.shards = _cracks(rng, self.R)
        self.drops = [(rng.uniform(0, 2 * math.pi), rng.uniform(250, 900), rng.uniform(3, 10)) for _ in range(28)]
        self.drips = []
        for _ in range(7):
            pts = rng.choice(self.lines)
            q = pts[min(len(pts) - 1, rng.randint(1, 3))]
            self.drips.append((q[0], q[1], rng.uniform(0.15, 1.6), rng.uniform(8, 22), rng.uniform(6, 22),
                               rng.uniform(4, 7)))
        self.t = 0.0
        self.on_impact = on_impact
        self.done = False
        self._last = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)
        self.timer.start(16)

    @property
    def total(self):
        return self.FLY + self.HOLD + self.FADE

    def _step(self):
        now = time.monotonic()
        self.advance(min(0.1, now - self._last))
        self._last = now

    def advance(self, dt):
        before = self.t
        self.t += dt
        if before < self.FLY <= self.t and self.on_impact:
            self.on_impact()
        if self.t >= self.total and not self.done:
            self.done = True
            self.timer.stop()
            self.close()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        self.paint(p)
        p.end()

    def paint(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t, fly = self.t, self.FLY
        if t < fly:
            self._paint_flying(p, t / fly)
            return
        tau = t - fly
        p.setOpacity(max(0.0, min(1.0, 1 - (t - fly - self.HOLD) / self.FADE)))
        if tau < 0.35:   # 屏幕抖一下
            k = 1 - tau / 0.35
            p.translate(math.sin(tau * 95) * 14 * k, math.cos(tau * 77) * 9 * k)
        c = self.impact
        stain = QRadialGradient(c, 0.3 * self.R)
        stain.setColorAt(0, QColor(170, 215, 255, 70))
        stain.setColorAt(1, QColor(170, 215, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(stain)
        p.drawEllipse(c, 0.3 * self.R, 0.3 * self.R)
        self._paint_cracks(p, min(1.0, tau / 0.18))
        self._paint_drips(p, tau)
        self._paint_splash(p, tau)
        if tau < 0.6:   # 瓶子弹回去、掉下去
            u = tau / 0.6
            p.save()
            p.translate(c.x() + 0.15 * self.R * u, c.y() + 0.9 * self.R * u * u)
            p.rotate(540 + 200 * u)
            draw_bottle(p, self.big * (1 - 0.55 * u), alpha=1 - u)
            p.restore()
        if tau < 0.25:   # 闪白
            flash = QRadialGradient(c, 0.5 * self.R)
            flash.setColorAt(0, QColor(255, 255, 255, int(230 * (1 - tau / 0.25))))
            flash.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(flash)
            p.drawEllipse(c, 0.5 * self.R, 0.5 * self.R)

    def _paint_flying(self, p, u):
        e = u * u   # 越飞越快
        x = self.start.x() + (self.impact.x() - self.start.x()) * e
        y = self.start.y() + (self.impact.y() - self.start.y()) * e - math.sin(math.pi * u) * 0.12 * self.R
        p.save()
        p.translate(x, y)
        p.rotate(540 * u)
        draw_bottle(p, 0.9 * self.h + (self.big - 0.9 * self.h) * e)
        p.restore()

    def _paint_cracks(self, p, grow):
        c = self.impact
        reach = grow * self.R
        p.save()
        p.translate(c)
        p.setPen(Qt.PenStyle.NoPen)
        for a, b, d, alpha in self.shards:
            if grow < 0.6:
                break
            p.setBrush(QColor(255, 255, 255, alpha))
            p.drawPolygon(QPolygonF([QPointF(*a), QPointF(*b), QPointF(*d)]))
        # 深色描一遍、白色高光偏一点再描一遍：深色桌面上看得见白线，浅色窗口上看得见深线
        dark = QPen(QColor(20, 28, 45, 170), 3.4)
        light = QPen(QColor(255, 255, 255, 240), 1.5)
        for pen, off in ((dark, 0.0), (light, -1.0)):
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for pts in self.lines:
                for (x0, y0, r0), (x1, y1, r1) in zip(pts, pts[1:]):
                    if r1 > reach:
                        break
                    p.drawLine(QPointF(x0 + off, y0 + off), QPointF(x1 + off, y1 + off))
        p.restore()

    def _paint_splash(self, p, tau):
        if tau > 0.9:
            return
        c = self.impact
        a = 1 - tau / 0.9
        for ang, v, s in self.drops:
            x = c.x() + math.cos(ang) * v * tau
            y = c.y() + math.sin(ang) * v * tau + 0.5 * 1600 * tau * tau
            p.setBrush(QColor(140, 200, 255, int(200 * a)))
            p.drawEllipse(QPointF(x, y), s, s * 1.15)
            p.setBrush(QColor(255, 255, 255, int(180 * a)))
            p.drawEllipse(QPointF(x - s * 0.3, y - s * 0.35), s * 0.3, s * 0.3)

    def _paint_drips(self, p, tau):
        c = self.impact
        for x, y, delay, v0, acc, s in self.drips:
            k = tau - delay
            if k <= 0:
                continue
            dy = v0 * k + 0.5 * acc * k * k
            x0, y0 = c.x() + x, c.y() + y
            trail = QLinearGradient(x0, y0, x0, y0 + dy)
            trail.setColorAt(0, QColor(160, 210, 255, 30))
            trail.setColorAt(1, QColor(160, 210, 255, 120))
            p.setPen(QPen(trail, s * 0.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + dy))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(150, 205, 255, 210))
            p.drawEllipse(QPointF(x0, y0 + dy), s * 0.75, s)
            p.setBrush(QColor(255, 255, 255, 200))
            p.drawEllipse(QPointF(x0 - s * 0.25, y0 + dy - s * 0.35), s * 0.22, s * 0.22)
