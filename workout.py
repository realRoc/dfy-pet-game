"""健身跟练：大肥鱼按训练计划带你练，报下一个动作、倒计时、偶尔偷懒。

几块：
- 跟练动画（首选）：content/workout/clips/ 里 Seedance 生成的透明视频（怎么来的见 tools/make_workout_clips.py），
  每段都从正面站姿开始、回到正面站姿；ClipDirector 一段播完再挑下一段，所以动作、偷懒、喘气喝水之间总是
  中立 → 动作 / 偷懒 → 中立，不会上一秒还在偷懒下一秒就在练。
- 原子动作 MOVES：每个动作是一条关键帧时间轴（Key），姿势帧在 content/workout/frames/（怎么来的见
  tools/make_workout_frames.py），按各自的停留时长循环，再叠蓄力、残影、落定余震、呼吸发抖这些小动作和头顶符号。另有累了、瘫倒、偷懒、喝水、欢呼这些
  大肥鱼人设动作，跟练时自己会用上，也能写进训练计划里。没装 PyAV 或跟练动画缺失时用这一套画。
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
from collections import namedtuple

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPixmap

import clips as clip_lib
from common import BUNDLE_DIR, DATA_DIR, IS_MAC, IS_WIN, emoji_font

WORKOUT_DIR = os.path.join(BUNDLE_DIR, "content", "workout")
FRAME_DIR = os.path.join(WORKOUT_DIR, "frames")
CLIP_DIR = os.path.join(WORKOUT_DIR, "clips")
CLIP_FADE = 0.15   # 片段开头结尾和正面图叠化几秒：视频比原画软一点，硬切会闪一下；左边的镜像也靠它带过去
BUILTIN_PLAN_DIR = os.path.join(WORKOUT_DIR, "plans")
USER_PLAN_DIR = os.path.join(DATA_DIR, "workouts")

PREP_SECS = 5
FINISH_SECS = 9    # 练完：欢呼 3 秒，再瘫倒一会儿
SLACK_SECS = 3.2   # 偷懒一次多久


def _ease(kind, a):
    a = max(0.0, min(1.0, a))
    if kind == "in":       # 越来越快：往下坐、发力前
        return a * a
    if kind == "out":      # 越来越慢：落定、站稳
        return 1 - (1 - a) * (1 - a)
    if kind == "linear":
        return a
    return a * a * (3 - 2 * a)


class Key:
    """时间轴上的一拍：摆 frame 这张图，停 hold 秒。思路照火纹战斗动画那套，只是动作都小：
    - 关键帧：站好 / 蹲到底这类 pose，停得最久，节奏靠它们在时间轴上的位置
    - 过渡帧：半蹲这类中间姿势，停得短，决定这一下是慢慢坐下去还是一下站起来
    - 蓄力帧：大一点的动作前先反向动一下（下蹲前吸气微微挺高、跳之前先压低）
    - 模糊帧：最快的那一拍（smear）带上一张图的残影，拉出速度感
    进入这一拍时，身体参数 (dy, sy, rot) 在 tween 秒内按 ease 从上一拍补间过来。图片默认硬切（中间姿势就是过渡），
    正面 ↔ 侧面这种没有中间帧的才给 fade 秒叠化，叠化时两张都尽量不透明，免得人变半透明。
    land：落定时压一下再弹两下（衣裙头发跟着晃的余震）；pulse=(幅度, 次/秒)：停着时的小起伏（喘气、咽水）；
    shake：发抖的幅度。dy、shake 以身高为单位，rot 是角度。"""

    def __init__(self, frame, hold, mirror=False, fade=0.0, tween=None, ease="inout",
                 dy=0.0, sy=1.0, rot=0.0, land=0.0, smear=False, pulse=(0.0, 0.0), shake=0.0):
        self.frame, self.hold, self.mirror, self.fade = frame, hold, mirror, fade
        self.tween = min(hold, 0.2) if tween is None else tween
        self.ease, self.dy, self.sy, self.rot = ease, dy, sy, rot
        self.land, self.smear, self.pulse, self.shake = land, smear, pulse, shake


class Move:
    """一个原子动作：keys 是一次动作（一个 rep）的时间轴，循环播放。
    帧默认朝左（侧面图）或正面；side="left" 时整套镜像。"""

    def __init__(self, label, keys, cue, tip="", persona=False, fx=None, still=None):
        self.label = label
        self.keys = keys
        self.rep = sum(k.hold for k in keys)
        self.cue = cue          # 开始时说的话
        self.tip = tip          # 动作要领
        self.persona = persona  # 大肥鱼人设动作（不是正经训练动作）
        self.fx = fx            # 头顶符号：sweat / shake / zzz / sparkle / rice
        self.still = still      # 偷懒时换成哪个动作（站着的动作偷偷刷手机，躺着的直接摆烂）

    @property
    def frames(self):
        return {k.frame for k in self.keys}


def _squat(bottom, half):
    """一次深蹲约 1.9 秒：站着呼吸 → 吸气微微挺高（蓄力）→ 半蹲（过渡，越坐越快）→ 蹲到底停住、
    衣裙晃两下 → 半蹲（模糊帧，一下站起来）→ 站直略微拉长再回落。"""
    return [
        Key("stand", 0.50, pulse=(0.008, 1.4)),
        Key("stand", 0.14, sy=1.025, dy=-0.008, tween=0.12, ease="out"),
        Key(half, 0.16, ease="in"),
        Key(bottom, 0.70, land=1.0, sy=0.985, pulse=(0.006, 2.0)),
        Key(half, 0.09, smear=True, sy=1.03, tween=0.06),
        Key("stand", 0.30, sy=1.03, land=0.5, ease="out"),
    ]


def _lunge(mirror):
    """一侧弓步约 2.1 秒：站直 → 迈步前轻轻一提（蓄力）→ 半弓步 → 压到底停住 → 半弓步（蹬回来）→ 站直。"""
    return [
        Key("stand", 0.40, pulse=(0.008, 1.4)),
        Key("stand", 0.12, sy=1.02, dy=-0.01, tween=0.1, ease="out"),
        Key("lunge_half", 0.18, mirror=mirror, fade=0.06, ease="in"),
        Key("lunge", 0.70, mirror=mirror, land=0.9, sy=0.985, pulse=(0.006, 2.0)),
        Key("lunge_half", 0.10, mirror=mirror, smear=True, sy=1.03, tween=0.06),
        Key("stand", 0.30, fade=0.06, sy=1.025, land=0.4, ease="out"),
    ]


MOVES = {
    # ---------- 训练动作 ----------
    "squat_open_close": Move("开合深蹲", _squat("squat_wide", "squat_wide_half") + _squat("squat_narrow", "squat_narrow_half"),
                             "开合深蹲！宽一下窄一下～", "宽站距、窄站距交替，膝盖跟脚尖同向", still="lazy_squat"),
    "squat": Move("深蹲", _squat("squat_wide", "squat_wide_half"), "深蹲，屁股往后坐！", "背挺直，蹲到大腿和地面平行",
                  still="lazy_squat"),
    "curtsy_lunge": Move("屈膝礼弓步", [
        Key("stand", 0.45, pulse=(0.008, 1.4)),
        Key("stand", 0.14, sy=1.03, dy=-0.012, tween=0.12, ease="out"),       # 踮一下脚
        Key("curtsy", 0.80, fade=0.1, ease="out", land=0.6, rot=-2.0, pulse=(0.006, 1.6)),   # 优雅地慢慢屈下去
        Key("stand", 0.35, fade=0.08, sy=1.02, land=0.3, ease="out"),
    ], "女仆屈膝礼，其实是弓步蹲哦", "后腿斜着交叉到身后，前膝不内扣", still="lazy_squat"),
    "lunge": Move("弓步蹲", _lunge(False) + _lunge(True), "左右交替弓步蹲！", "前膝 90°，后膝快碰地，上身直立",
                  still="lazy_squat"),
    "deadlift": Move("硬拉", [
        Key("lift", 0.45, pulse=(0.008, 1.4)),
        Key("lift", 0.16, sy=0.98, tween=0.14),                                # 收紧核心
        Key("hinge", 0.85, fade=0.12, tween=0.6, ease="inout", land=0.4, pulse=(0.005, 2.0)),   # 慢慢放下去（离心）
        Key("lift", 0.40, smear=True, sy=1.03, tween=0.12, ease="out", land=0.5),   # 一口气拉起来
    ], "硬拉电饭煲！背要平！", "屈髋往后推，背保持平直，没哑铃就拎个电饭煲", still="lazy_squat"),
    "glute_bridge": Move("臀桥", [
        Key("bridge_down", 0.50, pulse=(0.008, 1.2)),
        Key("bridge_up", 0.65, ease="out", land=0.5, shake=0.003),             # 顶上去夹臀，微微发抖
        Key("bridge_down", 0.40, fade=0.1, ease="inout"),                      # 慢慢放下
    ], "躺下，臀桥！", "顶髋到最高点夹臀停一下", still="collapse"),
    "glute_bridge_single": Move("单腿臀桥", [
        Key("bridge_down", 0.50, pulse=(0.008, 1.2)),
        Key("bridge_single", 0.70, ease="out", land=0.5, shake=0.004),
        Key("bridge_down", 0.45, fade=0.1, ease="inout"),
    ], "单腿臀桥，一条腿抬起来！", "抬起的腿伸直，支撑腿发力顶髋", still="collapse"),
    "wall_sit": Move("靠墙静蹲", [
        Key("wall_sit", 3.2, pulse=(0.006, 1.1), shake=0.004),
        Key("wall_sit", 0.25, dy=0.012, sy=0.99, tween=0.08, ease="in", shake=0.006),   # 腿一软往下滑一点
        Key("wall_sit", 0.6, tween=0.35, ease="out", land=0.4, shake=0.005),             # 又顶回去
    ], "靠墙静蹲，坚持住！", "大腿和地面平行，背贴墙，别憋气", fx="shake", still="tired"),
    # ---------- 大肥鱼人设动作 ----------
    "stand": Move("站好", [
        Key("stand", 1.3, pulse=(0.008, 1.3)),
        Key("stand", 0.6, rot=1.2, tween=0.5),                                 # 重心左右换一换
        Key("stand", 0.10, sy=0.96, tween=0.08, ease="in"),                    # 原地小跳：先压
        Key("stand", 0.16, dy=-0.035, sy=1.03, tween=0.12, ease="out"),
        Key("stand", 0.5, land=0.6, tween=0.12, ease="in", pulse=(0.008, 1.3)),
        Key("stand", 0.6, rot=-1.2, tween=0.5),
    ], "准备好了吗？", persona=True),
    "tired": Move("累了", [
        Key("tired", 1.2, pulse=(0.028, 2.6)),                                 # 大喘气
        Key("tired", 0.5, rot=2.0, tween=0.4, pulse=(0.02, 2.2)),
        Key("tired", 0.5, rot=-1.0, tween=0.4, pulse=(0.02, 2.2)),
    ], "呼……呼……累死鱼了", "大口喘气，别停下来走两步", persona=True, fx="sweat"),
    "collapse": Move("瘫倒", [
        Key("collapse", 2.4, pulse=(0.012, 0.6)),
        Key("collapse", 0.12, sy=1.03, tween=0.05, ease="out"),                # 抽一下
        Key("collapse", 1.5, land=0.6, pulse=(0.012, 0.6)),
    ], "我不行了……让我躺会儿", persona=True),
    "slack": Move("偷懒干饭", [
        Key("slack", 1.4, pulse=(0.012, 4.0)),                                 # 嚼嚼嚼
        Key("slack", 0.5, rot=-2.5, tween=0.25, pulse=(0.004, 1.0)),           # 偷瞄一眼
        Key("slack", 0.9, tween=0.25, pulse=(0.012, 4.0)),
    ], "（偷偷干一碗饭……）", persona=True, fx="rice"),
    "lazy_squat": Move("假装在练", [
        Key("lazy_squat", 0.9, dy=0.008, sy=0.99, tween=0.8, ease="inout"),    # 有气无力地蹲一点点
        Key("lazy_squat", 0.9, tween=0.8, ease="inout"),
        Key("lazy_squat", 0.8, rot=1.5, tween=0.4),                            # 刷手机刷入迷，歪一下
    ], "（我在练，我在练……）", persona=True, fx="zzz"),
    "drink": Move("喝水", [
        Key("drink", 0.7, pulse=(0.008, 1.3)),
        Key("drink", 1.3, rot=-3.5, dy=-0.005, tween=0.35, pulse=(0.012, 2.6)),   # 仰头咕咚咕咚
        Key("drink", 0.25, rot=0.0, tween=0.2, ease="out", land=0.4),            # 哈～
        Key("drink", 0.8, pulse=(0.008, 1.3)),
    ], "喝口水，歇一下～", "调整呼吸，喝小口水", persona=True),
    "cheer": Move("欢呼", [
        Key("cheer", 0.20),
        Key("cheer", 0.10, sy=0.93, tween=0.08, ease="in"),                    # 蓄力：先压低
        Key("cheer", 0.26, dy=-0.09, sy=1.06, tween=0.22, ease="out", smear=True),   # 蹦起来
        Key("cheer", 0.10, sy=0.94, tween=0.1, ease="in"),                     # 落地
        Key("cheer", 0.30, land=0.8, tween=0.12, ease="out"),
    ], "练完啦！大肥鱼最棒！", persona=True, fx="sparkle"),
}

SIDE_LABEL = {"left": "左", "right": "右"}

SLACK_LINES = ["就偷懒一下下……", "主人没在看吧……", "先干口饭再说", "摸鱼，鱼的本能"]   # 心声，气泡自己会加括号

# ---------- 跟练动画 ----------
# 躺着 / 蹲着练的姿势：(进入那段, 起身那段)。进入那段从站姿到这个姿势，起身那段回到站姿
POSTURES = {"bridge": ("bridge_enter", "bridge_exit"), "wall": ("wall_sit_enter", "wall_sit_exit")}
# 动作 → (要在哪个姿势上练, 循环播的那段)；姿势 None 是站着，循环段 None 是站着不动（画平时的正面图）
MOVE_CLIPS = {
    "squat_open_close": (None, "squat_open_close"),
    "squat": (None, "squat"),
    "curtsy_lunge": (None, "curtsy_lunge"),
    "lunge": (None, "lunge"),
    "deadlift": (None, "deadlift"),
    "glute_bridge": ("bridge", "bridge_loop"),
    "glute_bridge_single": ("bridge", "bridge_single_loop"),
    "wall_sit": ("wall", "wall_sit_loop"),
    "stand": (None, None),
    "tired": (None, "tired"),
    "collapse": (None, "collapse"),
    "slack": (None, "lazy_rice"),
    "lazy_squat": (None, "lazy_fake"),
    "drink": (None, "drink"),
    "cheer": (None, "cheer"),
}
# 偷懒的片段：(开始偷懒时的心声, 被发现时说的话, 第几秒被发现)。每段都是 中立 → 偷懒 → 被发现 → 中立
LAZY = {
    "lazy_doze": ("眼皮好重……就眯一下", "没睡！我没睡！", 3.5),
    "lazy_phone": ("就看一眼消息……", "我在查动作要领！", 4.0),
    "lazy_rice": ("先干口饭再说", "吃饱了才有力气练！", 4.5),
    "lazy_think": ("让我深度思考一下……", "已思考 3 秒，继续练！", 4.2),
    "lazy_flop": ("躺平，鱼的本能", "被发现了！继续继续！", 4.2),
    "lazy_fish": ("偷吃一口小鱼干……", "没吃！嘴里什么都没有！", 4.2),
    "lazy_fake": ("我在练，我在练……", "这次认真练！", 4.2),
    "lazy_tailnap": ("抱着尾巴睡一会儿……", "我醒着！我醒着！", 4.8),
}
CLIP_SLACK_CHANCE = 0.55   # 20 秒以上的站着练的动作，有多大概率中途偷懒一次
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
    return clip_library() is not None or (bool(frames) and all(m.frames <= frames.keys() for m in MOVES.values()))


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


# ---------- 动画 ----------
Pose = namedtuple("Pose", "layers ghosts body fx")
Pose.__doc__ = """layers：[(帧名, 镜像, 不透明度)]，叠化时是两张（先画旧的），至少一张不透明；
ghosts：模糊帧的残影 [(帧名, 镜像, 不透明度, dy)]，画在 layers 下面；
body：身体变换 (dx, dy, rot, sx, sy)，dx / dy 以身高为单位；fx：头顶符号。"""


def animate(move, t, mirror=False):
    """动作播到第 t 秒时的样子。时间轴循环；第一拍开头不和「上一轮的最后一拍」交叉淡化。"""
    keys = move.keys
    tt = t % move.rep
    i, start = 0, 0.0
    while i < len(keys) - 1 and tt >= start + keys[i].hold:
        start += keys[i].hold
        i += 1
    k, prev = keys[i], keys[i - 1]
    u = tt - start
    a = _ease(k.ease, u / k.tween) if k.tween > 0 else 1.0
    dy = prev.dy + (k.dy - prev.dy) * a
    sy = prev.sy + (k.sy - prev.sy) * a
    rot = prev.rot + (k.rot - prev.rot) * a
    if k.land:
        # 落定：先压扁再弹两下，衣裙头发跟着晃，越晃越小
        e = math.exp(-u * 9)
        sy -= 0.04 * k.land * e * math.cos(u * 22)
        rot += 1.6 * k.land * e * math.sin(u * 16)
    if k.pulse[0]:
        sy += k.pulse[0] * math.sin(2 * math.pi * k.pulse[1] * t)
    sx = 1 + (1 - sy) * 0.6        # 压扁时变宽、拉长时变窄，看着有体积
    dx = (math.sin(t * 47) + 0.5 * math.sin(t * 31)) * k.shake if k.shake else 0.0

    cur = (k.frame, k.mirror != mirror)
    old = (prev.frame, prev.mirror != mirror)
    played_prev = t - u > 1e-9
    layers = [cur + (1.0,)]
    if old != cur and played_prev and u < k.fade:
        # 叠化：前半段旧图不透明、新图渐显，后半段反过来，任何时候至少一张是实的
        f = u / k.fade
        layers = [old + (min(1.0, 2 * (1 - f)),), cur + (min(1.0, 2 * f),)]
    ghosts = []
    if k.smear and played_prev:
        # 模糊帧：上一拍的样子留一个渐隐的残影
        ghosts = [old + (0.35 * (1 - u / k.hold), prev.dy)]
    return Pose(layers, ghosts, (dx, dy, rot, sx, sy), move.fx)


# ---------- 跟练动画 ----------
_CLIP_LIB = False   # False：还没读过；None：不可用


def clip_library():
    """跟练动画素材；没装 PyAV、素材缺失或缺了要用的段时返回 None（退回姿势帧那套）。"""
    global _CLIP_LIB
    if _CLIP_LIB is False:
        lib = clip_lib.load_library(CLIP_DIR, CLIP_FADE)
        if lib is not None:
            need = {c for c, _ in POSTURES.values()} | {c for _, c in POSTURES.values()} | set(LAZY)
            need |= {c for _, c in MOVE_CLIPS.values() if c}
            missing = sorted(need - lib.clips.keys())
            if missing:
                print("跟练动画缺这些段，改用姿势帧:", missing)
                lib = None
        _CLIP_LIB = lib
    return _CLIP_LIB


def clip_extents(h):
    """跟练动画以脚底为原点往左、右、上、下最多伸出多少（逻辑像素），给窗口留地方。镜像也算上。"""
    lib = clip_library()
    left = right = up = down = 0.0
    for info in lib.clips.values():
        l, r, u, d = clip_lib.clip_extents(lib.ref, info.get("offset", info["crop"][:2]),
                                           info["crop"][2], info["crop"][3], h)
        side = max(l, r)
        left, right, up, down = max(left, side), max(right, side), max(up, u), max(down, d)
    return left, right, up, down


class ClipDirector:
    """跟练动画的导演。一段播完（这时一定停在正面站姿，或者某个躺着 / 蹲着的姿势上）才挑下一段，
    所以任何两段都是接上的。挑的顺序：
    1. 在躺着 / 蹲着的姿势上，但接下来不在这个姿势上练（或者有排着队的站着的片段）：先起身
    2. 排着队的（休息时先喘气再喝水、暂停时喘气、练完欢呼再瘫倒）
    3. 要躺下 / 蹲下练：先进入那个姿势
    4. 要偷懒且站着：播一段偷懒（不和上一次重样）
    5. 这个动作的循环段；没有就站着（画平时的正面图）"""

    def __init__(self, lib):
        self.player = clip_lib.ClipPlayer(lib)
        self.posture = None
        self.mirror = False
        self.queue = []
        self.last_lazy = None
        self.failed = False   # 素材打不开 / 解码出错：WorkoutPlayer 退回姿势帧

    @property
    def name(self):
        return self.player.name

    @property
    def idle(self):
        return not self.player.active and not self.queue and self.posture is None

    def update(self, dt, posture, loop, mirror=False, lazy=False):
        """往前走 dt 秒；正好开始了新的一段时返回它的名字。"""
        if self.player.active:
            self.player.update(dt)
            if self.player.active:
                return None
        was = self.posture
        name, mirror = self._pick(posture, loop, mirror, lazy)
        if name is None:
            return None
        # 只在正面站姿那头和正面图叠化：进入那段只淡入、起身那段只淡出、躺着的循环段都不淡
        if self.player.start(name, fades=(was is None, self.posture is None)) is None:
            self.failed = True
            return None
        self.mirror = mirror
        return name

    def _pick(self, posture, loop, mirror, lazy):
        if self.posture and (self.queue or posture != self.posture):
            name = POSTURES[self.posture][1]
            self.posture = None
            return name, False
        if self.queue:
            return self.queue.pop(0), False
        if posture and self.posture is None:
            self.posture = posture
            return POSTURES[posture][0], False
        if lazy and self.posture is None:
            name = random.choice([n for n in LAZY if n != self.last_lazy])
            self.last_lazy = name
            return name, False
        # 躺着 / 蹲着的姿势首尾接的是进入那段的最后一帧，翻过来就接不上了，只有站着的动作能镜像
        return loop, mirror and self.posture is None


# ---------- 播放 ----------
class WorkoutPlayer:
    """沿时间线走。update(dt) 返回这一帧发生的事件，桌宠据此说话、响提示音、报语音：
    ("say", 文本, 是否心声) / ("beep", "tick"|"go"|"rest"|"done") / ("speak", 文本)"""

    def __init__(self, plan, rounds=None, prep=True, slack=True, use_clips=False):
        self.plan = plan
        self.segs = build_timeline(plan, rounds, prep)
        self.rounds = rounds or plan["rounds"]
        self.total = sum(s.secs for s in self.segs)
        self.slack_enabled = slack
        self.celebrate = prep   # 动作预览（不带准备）练完直接结束，不欢呼
        self.show_timer = prep  # 动作预览也不显示倒计时
        self.idx = 0
        self.t = 0.0
        self.paused = False
        self.finished = False   # 时间线走完，正在欢呼 / 瘫倒
        self.finish_t = 0.0
        self.anim_t = 0.0       # 动画时钟，暂停时也走（暂停时大肥鱼原地喘气）
        self.slack_at = None
        self.slack_t = None
        self.caught_at = None
        self._pending = []
        lib = clip_library() if use_clips else None
        self.clips = ClipDirector(lib) if lib else None   # None：用姿势帧那套
        self._enter()

    # --- 查询 ---
    @property
    def seg(self):
        return self.segs[min(self.idx, len(self.segs) - 1)]

    @property
    def done(self):
        if self.clips:   # 等手上这段播完（练完是欢呼、瘫倒），回到站姿再结束
            return self.finished and self.clips.idle
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
        if self.clips:
            self.clips.queue = ["tired"] if self.paused else []   # 暂停时弯腰喘口气，然后站着等
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
        if self.clips and self.slacking:
            self._caught()   # 偷懒的片段还在播：时间到了，算她被发现
        self.slack_t = None
        self.slack_at = None
        m = MOVES[s.move]
        if self.clips:
            self.clips.queue = []
            if s.kind == "rest":
                # 刚练完先弯腰喘一会儿，再喝水
                tired = self.idx > 0 and self.segs[self.idx - 1].secs >= 30 and s.secs >= 9
                self.clips.queue = ["tired", "drink"] if tired else ["drink"]
        nxt = self.next_work()
        if s.kind == "prep":
            first = self.segs[1].label if len(self.segs) > 1 else ""
            self._pending += [("say", f"准备！第一个：{first}", False), ("speak", f"准备，第一个，{first}")]
        elif s.kind == "work":
            inner = m.cue.startswith("（")   # 括号里的是心声，用灰色气泡（气泡自己加括号）
            self._pending += [("beep", "go"), ("say", m.cue.strip("（）"), inner), ("speak", f"开始，{s.label}")]
            if self.clips:
                posture = MOVE_CLIPS[s.move][0]
                if self.slack_enabled and not m.persona and posture is None and s.secs >= 20 \
                        and random.random() < CLIP_SLACK_CHANCE:
                    self.slack_at = s.secs * random.uniform(0.2, 0.55)
            elif self.slack_enabled and m.still and s.secs >= 30 and random.random() < 0.35:
                self.slack_at = s.secs * random.uniform(0.35, 0.65)
        else:
            nl = nxt.label if nxt else "没有了"
            self._pending += [("beep", "rest"),
                              ("say", random.choice(REST_LINES).format(s=int(s.secs), next=nl), False),
                              ("speak", f"休息{int(s.secs)}秒，下一个，{nl}")]

    def _finish(self):
        self.finished, self.finish_t = True, 0.0
        self.idx = len(self.segs) - 1
        if self.clips:
            if self.slacking:
                self._caught()
            self.slack_t = self.slack_at = None
            self.clips.queue = ["cheer", "collapse"] if self.celebrate else []
        if not self.celebrate:
            self.finish_t = FINISH_SECS
            return
        self._pending += [("beep", "done"), ("say", MOVES["cheer"].cue, False),
                          ("speak", f"练完了，一共{fmt_secs(self.total)}，辛苦啦")]

    def update(self, dt):
        self.anim_t += dt
        if self.clips:
            self._update_clips(dt)
        if self.finished:
            prev = self.finish_t
            self.finish_t += dt
            if not self.clips and prev < 3.0 <= self.finish_t:
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
        # 偷懒：中途摆烂几秒，然后「被发现了」。用跟练动画时由 _update_clips 管
        if self.clips:
            pass
        elif self.slack_at is not None and prev < self.slack_at <= self.t:
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

    def _want(self):
        """现在想播什么：(姿势, 循环段, 镜像)。"""
        s = self.seg
        if self.finished or self.paused or s.kind != "work":
            return None, None, False
        posture, loop = MOVE_CLIPS[s.move]
        return posture, loop, s.side == "left"

    def _update_clips(self, dt):
        d = self.clips
        posture, loop, mirror = self._want()
        lazy = False
        if self.slack_at is not None and not self.paused and not self.finished and self.t >= self.slack_at:
            # 到点了：等手上这一下练完（回到站姿）再偷懒；剩的时间不够偷懒一整段就算了
            if self.seg.secs - self.t >= 9:
                lazy = True
            else:
                self.slack_at = None
        started = d.update(dt, posture, loop, mirror, lazy)
        if d.failed:
            print("跟练动画播放失败，改用姿势帧")
            self.clips = None
            self.slack_t = self.slack_at = None
            return
        if started in LAZY and lazy:
            self.slack_at = None
            self.slack_t = 0.0
            self.caught_at = LAZY[started][2]
            self._pending.append(("say", LAZY[started][0], True))
        elif started == "collapse" and self.finished:
            self._pending.append(("say", MOVES["collapse"].cue, False))
        if self.slack_t is not None:
            self.slack_t += dt
            if self.caught_at is not None and self.slack_t >= self.caught_at:
                self._caught()
            if d.name not in LAZY:
                self.slack_t = None

    def _caught(self):
        if self.caught_at is not None:
            self._pending.append(("say", LAZY[self.clips.last_lazy][1], False))
        self.caught_at = None

    def fx(self):
        """用跟练动画时叠的头顶符号：练到最后 10 秒冒汗。"""
        s = self.seg
        if not self.finished and not self.paused and s.kind == "work" and s.secs >= 30 \
                and self.t > s.secs - 10 and not self.slacking:
            return "sweat"
        return None

    # --- 动画 ---
    def pose(self):
        """现在画什么，见 Pose。"""
        s = self.seg
        if self.finished:
            if self.finish_t < 3.0:
                return animate(MOVES["cheer"], self.finish_t)
            return animate(MOVES["collapse"], self.finish_t - 3.0)
        if self.paused:   # 暂停时弯腰喘气（休息、准备时照常）
            return animate(MOVES["tired" if s.kind == "work" else s.move], self.anim_t)
        if s.kind == "rest":
            # 刚练完先弯腰喘两秒，再喝水
            if self.t < 2.5 and self.idx > 0 and self.segs[self.idx - 1].secs >= 30:
                return animate(MOVES["tired"], self.t)
            return animate(MOVES["drink"], self.t)
        m = MOVES[s.move]
        if self.slacking and m.still:
            return animate(MOVES[m.still], self.slack_t)
        pose = animate(m, self.t, mirror=s.side == "left")
        if s.kind == "work" and s.secs >= 30 and self.t > s.secs - 10:
            # 最后 10 秒：腿开始抖，冒汗
            dx, dy, rot, sx, sy = pose.body
            k = (self.t - (s.secs - 10)) / 10
            dx += math.sin(self.anim_t * 47) * (0.004 + 0.008 * k)
            pose = Pose(pose.layers, pose.ghosts, (dx, dy, rot, sx, sy), pose.fx or "sweat")
        return pose

    def frames_in_use(self):
        """这次跟练可能用到的帧，给窗口留地方用。"""
        names = {"stand", "tired", "drink", "cheer", "collapse"}
        for s in self.segs:
            m = MOVES[s.move]
            names |= m.frames
            if m.still:
                names |= MOVES[m.still].frames
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
    SOUNDS = {"tick": "Tink", "go": "Glass", "rest": "Pop", "done": "Hero", "crash": "Basso"}

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
