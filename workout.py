"""健身跟练：大肥鱼按训练计划带你练，报下一个动作、倒计时、偶尔偷懒。

三块：
- 原子动作 MOVES：每个动作是几张姿势帧（content/workout/frames/，怎么来的见 tools/make_workout_frames.py）
  按节拍循环，再叠一点挤压、发抖之类的身体动作和头顶符号。另有累了、瘫倒、偷懒、喝水、欢呼这些
  大肥鱼人设动作，跟练时自己会用上，也能写进训练计划里。
- 训练计划：JSON，内置的放 content/workout/plans/，自己写的放 workouts/（右键「跟练 → 打开计划文件夹」）。
  展开成一条时间线：准备 → 动作 → 休息 → 动作 …，多轮之间有轮间休息。
- WorkoutPlayer：沿时间线走，告诉桌宠现在画哪张帧、该说什么、该响什么提示音。不碰界面，方便测。
"""
import glob
import json
import math
import os
import random
import subprocess

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPixmap

from common import APP_DIR, BUNDLE_DIR, IS_MAC, IS_WIN, emoji_font

WORKOUT_DIR = os.path.join(BUNDLE_DIR, "content", "workout")
FRAME_DIR = os.path.join(WORKOUT_DIR, "frames")
BUILTIN_PLAN_DIR = os.path.join(WORKOUT_DIR, "plans")
USER_PLAN_DIR = os.path.join(APP_DIR, "workouts")

PREP_SECS = 5
FADE = 0.12        # 两张姿势帧之间的交叉淡化
FINISH_SECS = 9    # 练完：欢呼 3 秒，再瘫倒一会儿
SLACK_SECS = 3.2   # 偷懒一次多久


class Move:
    """一个原子动作。cycle 是一轮里依次摆的姿势 (帧名, 是否镜像)，每个姿势停 beat 秒。
    帧默认朝左（侧面图）或正面；side="left" 时整套镜像。"""

    def __init__(self, label, cycle, beat, cue, tip="", persona=False, fx=None, still=None):
        self.label = label
        self.cycle = [(c, False) if isinstance(c, str) else c for c in cycle]
        self.beat = beat
        self.cue = cue          # 开始时说的话
        self.tip = tip          # 计时面板上的动作要领
        self.persona = persona  # 大肥鱼人设动作（不是正经训练动作）
        self.fx = fx            # 头顶符号：sweat / shake / zzz / sparkle / rice
        self.still = still      # 偷懒时换成哪张帧（站着的动作偷偷刷手机，躺着的直接摆烂）

    @property
    def frames(self):
        return {f for f, _ in self.cycle}


MOVES = {
    # ---------- 训练动作 ----------
    "squat_open_close": Move("开合深蹲", ["stand", "squat_wide", "stand", "squat_narrow"], 1.0,
                             "开合深蹲！宽一下窄一下～", "宽站距、窄站距交替，膝盖跟脚尖同向", still="lazy_squat"),
    "squat": Move("深蹲", ["stand", "squat_wide"], 1.1, "深蹲，屁股往后坐！", "背挺直，蹲到大腿和地面平行",
                  still="lazy_squat"),
    "curtsy_lunge": Move("屈膝礼弓步", ["stand", "curtsy"], 1.2, "女仆屈膝礼，其实是弓步蹲哦",
                         "后腿斜着交叉到身后，前膝不内扣", still="lazy_squat"),
    "lunge": Move("弓步蹲", ["stand", "lunge", "stand", ("lunge", True)], 1.1, "左右交替弓步蹲！",
                  "前膝 90°，后膝快碰地，上身直立", still="lazy_squat"),
    "deadlift": Move("硬拉", ["lift", "hinge"], 1.4, "硬拉电饭煲！背要平！",
                     "屈髋往后推，背保持平直，没哑铃就拎个电饭煲", still="lazy_squat"),
    "glute_bridge": Move("臀桥", ["bridge_down", "bridge_up"], 1.1, "躺下，臀桥！", "顶髋到最高点夹臀停一下",
                         still="collapse"),
    "glute_bridge_single": Move("单腿臀桥", ["bridge_down", "bridge_single"], 1.2, "单腿臀桥，一条腿抬起来！",
                                "抬起的腿伸直，支撑腿发力顶髋", still="collapse"),
    "wall_sit": Move("靠墙静蹲", ["wall_sit"], 99, "靠墙静蹲，坚持住！", "大腿和地面平行，背贴墙，别憋气",
                     fx="shake", still="tired"),
    # ---------- 大肥鱼人设动作 ----------
    "stand": Move("站好", ["stand"], 99, "准备好了吗？", persona=True),
    "tired": Move("累了", ["tired"], 99, "呼……呼……累死鱼了", "大口喘气，别停下来走两步", persona=True, fx="sweat"),
    "collapse": Move("瘫倒", ["collapse"], 99, "我不行了……让我躺会儿", persona=True),
    "slack": Move("偷懒干饭", ["slack"], 99, "（偷偷干一碗饭……）", persona=True, fx="rice"),
    "lazy_squat": Move("假装在练", ["lazy_squat"], 99, "（我在练，我在练……）", persona=True, fx="zzz"),
    "drink": Move("喝水", ["drink"], 99, "喝口水，歇一下～", "调整呼吸，喝小口水", persona=True),
    "cheer": Move("欢呼", ["cheer"], 99, "练完啦！大肥鱼最棒！", persona=True, fx="sparkle"),
}

SIDE_LABEL = {"left": "左", "right": "右"}

SLACK_LINES = ["就偷懒一下下……", "主人没在看吧……", "先干口饭再说", "摸鱼，鱼的本能"]   # 心声，气泡自己会加括号
CAUGHT_LINES = ["被发现了！继续继续！", "我没偷懒！我在思考！", "已思考 3 秒，继续练！"]
LAST_LINES = ["最后 10 秒！", "坚持住！快到了！", "腿在抖了！别停！"]
REST_LINES = ["休息 {s} 秒，下一个：{next}", "喘口气，下一个：{next}"]


# ---------- 训练计划 ----------
class PlanError(ValueError):
    pass


def validate_plan(plan):
    """检查计划格式，返回整理好的副本；有问题抛 PlanError（信息直接给人看）。"""
    if not isinstance(plan, dict):
        raise PlanError("计划应该是一个 JSON 对象")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PlanError("steps 不能为空")
    out = {
        "name": str(plan.get("name") or "未命名计划"),
        "source": str(plan.get("source") or ""),
        "rest": _num(plan.get("rest", 15), "rest"),
        "round_rest": _num(plan.get("round_rest", 30), "round_rest"),
        "rounds": max(1, int(_num(plan.get("rounds", 1), "rounds"))),
        "steps": [],
    }
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or s.get("move") not in MOVES:
            raise PlanError(f"第 {i} 步的 move 不认识：{s.get('move') if isinstance(s, dict) else s}"
                            f"（可用：{', '.join(MOVES)}）")
        secs = _num(s.get("secs"), f"第 {i} 步的 secs")
        if secs <= 0:
            raise PlanError(f"第 {i} 步的 secs 要大于 0")
        side = s.get("side")
        if side not in (None, "left", "right"):
            raise PlanError(f"第 {i} 步的 side 只能是 left / right")
        step = {"move": s["move"], "secs": secs, "side": side, "rest": _num(s.get("rest", out["rest"]), "rest")}
        if "label" in s:
            step["label"] = str(s["label"])
        out["steps"].append(step)
    return out


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise PlanError(f"{what} 应该是不小于 0 的数字")
    return v


def load_plans():
    """内置计划 + workouts/ 里自己写的，按文件名排序；读不了的计划跳过并记下原因。
    返回 ([(id, plan)], [错误信息])，自己写的和内置同名时用自己写的。"""
    plans, errors = {}, []
    for d in (BUILTIN_PLAN_DIR, USER_PLAN_DIR):
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            pid = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, encoding="utf-8") as f:
                    plans[pid] = validate_plan(json.load(f))
            except Exception as e:
                errors.append(f"{os.path.basename(path)}：{e}")
    return list(plans.items()), errors


def single_move_plan(move, secs=12):
    """「动作预览」：只练一个动作，不要准备和休息。"""
    return validate_plan({"name": MOVES[move].label, "rest": 0, "steps": [{"move": move, "secs": secs}]})


def step_label(step):
    label = step.get("label") or MOVES[step["move"]].label
    side = SIDE_LABEL.get(step.get("side"))
    return f"{label}（{side}）" if side else label


class Segment:
    """时间线上的一段。kind: prep 准备 / work 训练 / rest 休息。"""

    def __init__(self, kind, move, secs, label, side=None, index=0, round_no=1):
        self.kind, self.move, self.secs, self.label = kind, move, secs, label
        self.side, self.index, self.round_no = side, index, round_no


def build_timeline(plan, rounds=None, prep=True):
    rounds = rounds or plan["rounds"]
    steps = plan["steps"]
    segs = []
    if prep:
        segs.append(Segment("prep", "stand", PREP_SECS, "准备"))
    for r in range(1, rounds + 1):
        for i, s in enumerate(steps):
            segs.append(Segment("work", s["move"], s["secs"], step_label(s), s.get("side"), i, r))
            if i < len(steps) - 1:
                rest = s["rest"]
            else:
                rest = plan["round_rest"] if r < rounds else 0
            if rest > 0:
                segs.append(Segment("rest", "drink", rest, "休息" if i < len(steps) - 1 else "轮间休息",
                                    index=i, round_no=r))
    return segs


def fmt_secs(s):
    s = max(0, int(math.ceil(s - 1e-6)))
    return f"{s // 60}:{s % 60:02d}"


# ---------- 帧 ----------
_MANIFEST = None


def manifest():
    global _MANIFEST
    if _MANIFEST is None:
        try:
            with open(os.path.join(FRAME_DIR, "frames.json"), encoding="utf-8") as f:
                _MANIFEST = json.load(f)
        except Exception as e:
            print("跟练素材不可用:", e)
            _MANIFEST = {"frames": {}}
    return _MANIFEST


def available():
    frames = manifest()["frames"]
    return bool(frames) and all(m.frames <= frames.keys() for m in MOVES.values())


class FrameCache:
    """按桌宠身高缩放好的姿势帧。每张图记着脚底锚点 (ax, ay) 和「站直时的身高」unit（像素），
    缩放 = 桌宠身高 / unit，这样躺着、蹲着的图和站着的一样大。"""

    def __init__(self):
        self._cache = {}

    def get(self, name, h, dpr=1.0):
        key = (name, h, dpr)
        if key not in self._cache:
            info = manifest()["frames"][name]
            pix = QPixmap(os.path.join(FRAME_DIR, info["file"]))
            s = h / info["unit"]
            px_w = max(1, int(pix.width() * s * dpr))
            pix = pix.scaledToWidth(px_w, Qt.TransformationMode.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
            self._cache[key] = (pix, info["ax"] * s, info["ay"] * s, pix.width() / dpr, pix.height() / dpr)
        return self._cache[key]

    def extents(self, names, h):
        """这些帧以脚底为原点往左、右、上、下各伸出多少（逻辑像素），镜像也算上。"""
        left = right = up = down = 0.0
        for n in names:
            info = manifest()["frames"][n]
            s = h / info["unit"]
            ax, ay, w, hh = info["ax"] * s, info["ay"] * s, info["w"] * s, info["h"] * s
            side = max(ax, w - ax)
            left, right = max(left, side), max(right, side)
            up, down = max(up, ay), max(down, hh - ay)
        return left, right, up, down


# ---------- 播放 ----------
class WorkoutPlayer:
    """沿时间线走。update(dt) 返回这一帧发生的事件，桌宠据此说话、响提示音、报语音：
    ("say", 文本, 是否心声) / ("beep", "tick"|"go"|"rest"|"done") / ("speak", 文本)"""

    def __init__(self, plan, rounds=None, prep=True, slack=True):
        self.plan = plan
        self.segs = build_timeline(plan, rounds, prep)
        self.rounds = rounds or plan["rounds"]
        self.total = sum(s.secs for s in self.segs)
        self.slack_enabled = slack
        self.celebrate = prep   # 动作预览（不带准备）练完直接结束，不欢呼
        self.idx = 0
        self.t = 0.0
        self.paused = False
        self.finished = False   # 时间线走完，正在欢呼 / 瘫倒
        self.finish_t = 0.0
        self.anim_t = 0.0       # 动画时钟，暂停时也走（暂停时大肥鱼原地喘气）
        self.slack_at = None
        self.slack_t = None
        self._pending = []
        self._enter()

    # --- 查询 ---
    @property
    def seg(self):
        return self.segs[min(self.idx, len(self.segs) - 1)]

    @property
    def done(self):
        return self.finished and self.finish_t >= FINISH_SECS

    @property
    def remaining(self):
        return 0.0 if self.finished else max(0.0, self.seg.secs - self.t)

    @property
    def elapsed(self):
        if self.finished:
            return self.total
        return sum(s.secs for s in self.segs[:self.idx]) + self.t

    def next_work(self):
        for s in self.segs[self.idx + 1:]:
            if s.kind == "work":
                return s
        return None

    def work_count(self):
        """(这是第几个动作, 一轮几个动作)"""
        return self.seg.index + 1, len(self.plan["steps"])

    @property
    def slacking(self):
        return self.slack_t is not None

    # --- 控制 ---
    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def skip(self):
        if not self.finished:
            self._goto(self.idx + 1)

    def back(self):
        """回到本段开头；刚开始一两秒内再按就回上一段。"""
        if self.finished:
            self.finished = False
            self._goto(len(self.segs) - 1)
        elif self.t < 2 and self.idx > 0:
            self._goto(self.idx - 1)
        else:
            self._goto(self.idx)

    def _goto(self, i):
        if i >= len(self.segs):
            self._finish()
            return
        self.idx, self.t = max(0, i), 0.0
        self._enter()

    def _enter(self):
        s = self.seg
        self.slack_t = None
        self.slack_at = None
        m = MOVES[s.move]
        nxt = self.next_work()
        if s.kind == "prep":
            first = self.segs[1].label if len(self.segs) > 1 else ""
            self._pending += [("say", f"准备！第一个：{first}", False), ("speak", f"准备，第一个，{first}")]
        elif s.kind == "work":
            inner = m.cue.startswith("（")   # 括号里的是心声，用灰色气泡（气泡自己加括号）
            self._pending += [("beep", "go"), ("say", m.cue.strip("（）"), inner), ("speak", f"开始，{s.label}")]
            if self.slack_enabled and m.still and s.secs >= 30 and random.random() < 0.35:
                self.slack_at = s.secs * random.uniform(0.35, 0.65)
        else:
            nl = nxt.label if nxt else "没有了"
            self._pending += [("beep", "rest"),
                              ("say", random.choice(REST_LINES).format(s=int(s.secs), next=nl), False),
                              ("speak", f"休息{int(s.secs)}秒，下一个，{nl}")]

    def _finish(self):
        self.finished, self.finish_t = True, 0.0
        self.idx = len(self.segs) - 1
        if not self.celebrate:
            self.finish_t = FINISH_SECS
            return
        self._pending += [("beep", "done"), ("say", MOVES["cheer"].cue, False),
                          ("speak", f"练完了，一共{fmt_secs(self.total)}，辛苦啦")]

    def update(self, dt):
        self.anim_t += dt
        if self.finished:
            prev = self.finish_t
            self.finish_t += dt
            if prev < 3.0 <= self.finish_t:
                self._pending.append(("say", MOVES["collapse"].cue, False))
            return self._flush()
        if self.paused:
            return self._flush()
        s = self.seg
        prev, self.t = self.t, self.t + dt
        # 最后 3 秒滴答
        for n in (3, 2, 1):
            if prev < s.secs - n <= self.t:
                self._pending.append(("beep", "tick"))
                if s.kind != "work":
                    self._pending.append(("say", str(n), False))
        if s.kind == "work" and s.secs >= 30 and prev < s.secs - 10 <= self.t:
            self._pending.append(("say", random.choice(LAST_LINES), False))
        if s.kind == "work" and s.secs >= 20 and prev < s.secs / 2 <= self.t and s.side is None:
            self._pending.append(("speak", "一半了"))
        # 偷懒：中途摆烂几秒，然后「被发现了」
        if self.slack_at is not None and prev < self.slack_at <= self.t:
            self.slack_t = 0.0
            self._pending.append(("say", random.choice(SLACK_LINES), True))
        elif self.slack_t is not None:
            self.slack_t += dt
            if self.slack_t >= SLACK_SECS:
                self.slack_t, self.slack_at = None, None
                self._pending.append(("say", random.choice(CAUGHT_LINES), False))
        if self.t >= s.secs:
            self._goto(self.idx + 1)
        return self._flush()

    def _flush(self):
        out, self._pending = self._pending, []
        return out

    # --- 动画 ---
    def pose(self):
        """现在画什么：[(帧名, 镜像, 不透明度)]（交叉淡化时两张）、身体变换 (dx, dy, rot, sx, sy) 和头顶符号。"""
        s = self.seg
        if self.finished:
            key = "cheer" if self.finish_t < 3.0 else "collapse"
            return self._hold(key, self.finish_t if key == "cheer" else self.finish_t - 3.0)
        if self.paused:
            return self._hold("tired" if s.kind == "work" else MOVES[s.move].cycle[0][0], self.anim_t)
        if s.kind == "rest":
            # 刚练完先弯腰喘两秒，再喝水
            if self.t < 2.5 and self.idx > 0 and self.segs[self.idx - 1].secs >= 30:
                return self._hold("tired", self.t)
            return self._hold("drink", self.t)
        m = MOVES[s.move]
        if self.slacking and m.still:
            return self._hold(m.still, self.slack_t)
        mirror = s.side == "left"
        n = len(m.cycle)
        pos = self.t / m.beat
        i = int(pos) % n
        u = pos - int(pos)              # 这个姿势停了多久（以拍计）
        frame, flip = m.cycle[i]
        layers = [(frame, flip != mirror, 1.0)]
        if n > 1 and u * m.beat < FADE and self.t >= m.beat:
            pf, pflip = m.cycle[(i - 1) % n]
            a = u * m.beat / FADE
            layers = [(pf, pflip != mirror, 1.0 - a), (frame, flip != mirror, a)]
        # 落到新姿势时压一下，然后轻轻呼吸
        land = max(0.0, 1.0 - u * m.beat / 0.2) if n > 1 else 0.0
        sx, sy = 1 + 0.035 * land, 1 - 0.045 * land
        dx = dy = rot = 0.0
        fx = m.fx
        tired = s.kind == "work" and s.secs >= 30 and self.t > s.secs - 10
        if m.fx == "shake" or tired:
            amp = 0.006 + (0.01 if tired else 0.0)
            dx = math.sin(self.anim_t * 47) * amp
            fx = fx or "sweat"
        sy *= 1 + 0.012 * math.sin(self.anim_t * 3)
        return layers, (dx, dy, rot, sx, sy), fx

    def _hold(self, key, t):
        m = MOVES[key]
        sy = 1 + 0.015 * math.sin(t * 3)
        dy = 0.0
        if key == "tired":
            sy = 1 + 0.03 * math.sin(t * 9)      # 大喘气
        elif key == "cheer":
            dy = -abs(math.sin(t * math.pi * 1.6)) * 0.08
        elif key == "lazy_squat":
            sy = 1 - 0.02 * abs(math.sin(t * 1.5))
        return [(m.cycle[0][0], False, 1.0)], (0.0, dy, 0.0, 1 / (sy ** 0.5), sy), m.fx

    def frames_in_use(self):
        """这次跟练可能用到的帧，给窗口留地方用。"""
        names = {"stand", "tired", "drink", "cheer", "collapse"}
        for s in self.segs:
            m = MOVES[s.move]
            names |= m.frames
            if m.still:
                names.add(m.still)
        return names


def draw_fx(p, fx, t, head_x, head_y, h):
    """头顶符号，和 expressions 的画法一样：按身高 h 的比例给尺寸。"""
    if not fx:
        return

    def emo(ch, x, y, size, alpha=1.0):
        if alpha <= 0.01:
            return
        p.save()
        p.setOpacity(p.opacity() * min(1.0, alpha))
        p.setPen(QColor(0, 0, 0))
        p.setFont(emoji_font(size))
        p.drawText(QRectF(x - size, y - size, size * 2, size * 2), Qt.AlignmentFlag.AlignCenter, ch)
        p.restore()

    if fx in ("sweat", "shake"):
        for i, side in enumerate((-1, 1)):
            ph = (t * 0.9 + i * 0.5) % 1
            emo("💦", head_x + side * (0.3 + ph * 0.05) * h, head_y + (0.1 + ph * 0.25) * h, 0.09 * h, 1 - ph)
    elif fx == "zzz":
        for i in range(2):
            ph = (t * 0.5 + i / 2) % 1
            emo("💤", head_x + (0.22 + ph * 0.12) * h, head_y + 0.05 * h - ph * 0.2 * h, 0.09 * h, 1 - ph)
    elif fx == "sparkle":
        for i, (ox, oy) in enumerate([(-0.35, 0.1), (0.35, 0.05), (0.2, -0.1), (-0.2, -0.08)]):
            emo("✨", head_x + ox * h, head_y + oy * h, 0.1 * h, abs(math.sin(t * 4 + i * 1.3)))
    elif fx == "rice":
        emo("🍚", head_x + 0.3 * h, head_y + 0.05 * h + math.sin(t * 5) * 0.02 * h, 0.12 * h)


class Announcer:
    """提示音和语音播报。macOS 用系统自带的 afplay / say（婷婷），Windows 只有提示音，其他系统不出声。
    都是后台子进程，不卡界面；新的语音会打断还没说完的上一句。"""
    SOUNDS = {"tick": "Tink", "go": "Glass", "rest": "Pop", "done": "Hero"}

    def __init__(self):
        self.voice = True
        self._say = None

    def beep(self, kind):
        try:
            if IS_MAC:
                subprocess.Popen(["afplay", f"/System/Library/Sounds/{self.SOUNDS.get(kind, 'Tink')}.aiff"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif IS_WIN:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK if kind == "done" else winsound.MB_OK)
        except Exception as e:
            print("提示音失败:", e)

    def speak(self, text):
        if not (self.voice and IS_MAC):
            return
        self.stop()
        try:
            self._say = subprocess.Popen(["say", "-v", "Tingting", "-r", "210", text],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print("语音播报失败:", e)

    def stop(self):
        if self._say is not None and self._say.poll() is None:
            self._say.terminate()
        self._say = None


def ensure_user_plan_dir():
    """建 workouts/ 并放一份示例，返回路径。"""
    os.makedirs(USER_PLAN_DIR, exist_ok=True)
    example = os.path.join(USER_PLAN_DIR, "示例-两轮深蹲.json.example")
    if not os.path.exists(example):
        with open(example, "w", encoding="utf-8") as f:
            json.dump({
                "name": "示例：深蹲 + 靠墙静蹲 两轮",
                "rest": 15, "round_rest": 40, "rounds": 2,
                "steps": [
                    {"move": "squat", "secs": 40},
                    {"move": "lunge", "secs": 40},
                    {"move": "wall_sit", "secs": 30, "rest": 20},
                    {"move": "collapse", "secs": 10, "label": "躺平一下"},
                ],
                "_说明": "去掉文件名末尾的 .example 就会出现在「跟练」菜单里。move 可用："
                         + "、".join(f"{k}（{m.label}）" for k, m in MOVES.items()),
            }, f, ensure_ascii=False, indent=2)
    return USER_PLAN_DIR
