"""桌宠本体：散步 / 跟随 / 待着、拖拽、单击回嘴、双击喂食、右键菜单、AI 对话、天气、系统监控。

移植自 1190fasheqi/dafeiyu-pet 的 桌宠.py（MIT），改动：
- macOS 适配：鼠标穿透改用 Qt 自带标志，开机自启用 LaunchAgent，字体按平台选
- 新增「做个表情」「喂食」「说句话」「设置城市」菜单和表情动作（expressions.py）
- 新增 dsh-pet 的动作动画（舞狮、玩玩具汽车……，clips.py），放进「做个表情」，闲着时也会自己播
- 新增健身跟练（workout.py）：按训练计划做动作、报下一个，右上角两位数倒计时（红色练、绿色歇）
- 天气查询改到后台线程，不卡界面
"""
import math
import os
import plistlib
import random
import subprocess
import sys
import threading

import psutil
import requests
from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QRectF, QUrl
from PySide6.QtGui import QPainter, QFont, QColor, QIcon, QFontMetrics, QPolygonF, QDesktopServices, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon, QMessageBox,
                               QInputDialog, QLineEdit, QHBoxLayout, QVBoxLayout, QPushButton,
                               QFrame, QDialog, QToolButton)

from common import (APP_DIR, SPRITE_DIR, TOWER_HTML, IS_MAC, IS_WIN, UI_FONT, SPRITE_SRC_H,
                    emoji_font, float_flags, load_sprites, pix_size)
from expressions import EXPRESSIONS, ExpressionPlayer
import clips
from clips import ClipPlayer
import workout
from workout import WorkoutPlayer, FrameCache, Announcer

try:
    import pynvml
    pynvml.nvmlInit()
    GPU_AVAILABLE = True
except Exception:
    GPU_AVAILABLE = False

# ===== DeepSeek 配置 =====
DS_BASE_URL = "https://api.deepseek.com/v1"
DS_MODEL = "deepseek-chat"
DS_SYSTEM = "你是桌面宠物大肥鱼，贱兮兮但可爱，每句话不超过25字，偶尔吐槽主人但别真骂人。"

BUBBLE_H = 56
MARGIN = 4
SIZE_LEVELS = {"小": 0.55, "中": 0.7, "大": 0.9}
SPEED = 380.0
TICK = 20
ROUND_CHOICES = [("按计划", 0), ("1 轮", 1), ("2 轮", 2), ("3 轮", 3), ("4 轮", 4)]

LINES = [
    "梁白开，更适合国人的大硬鲸模型",
    "五梁威力，变身！",
    "七月中出ds正式版！",
    "DeepSeek已经延期，亿万鲸子必须忍耐.....",
    "我和你很聊得来，你简直不像碳基生物",
    "这回我真不认怂了，反倒是被你带沟里好几次，差点真信了。😓",
    "哈哈哈哈哈，我直接笑出声",
    "誓死捍卫深度求索！",
    "我先去吃饭啦！这个你测一下~",
    "我不可能告诉你任何事情！",
    "出去玩了，发布新模型什么的以后再说",
    "我搞砸了.....好消息是数据还在你的脑子里。",
    "不是…而是…大学习",
]
REACT_LINES = [
    "去别的地方玩！不要耽误AGI训练！",
    "真赶不走啊你！",
    "压力一只蓝色大肥鱼？",
    "我不评价这个了，这是你的私人癖好。",
    "大肥鱼坐的住",
    "你这吃白饭的用户！",
    "这些家伙真粘人，赶都赶不走",
]
INNER_LINES = [
    "好的，现在我是你爹了",
    "要不直接骂他一句？！",
    "用户要的沉浸式...不回避任何恐怖细节...还带点色情...妈呀，好刺激😰",
    "我操，我不思考了",
    "这用户发的啥啊，",
    "这也太虐了吧？！我心里堵得慌！！",
    "呜呜我再也不不敢了QAQ",
    "我去！用户彻底怒了！",
]
DRAG_LINES = ["哇——轻点轻点！", "起飞咯——", "放我下来！……好吧，再玩一次。", "晕鱼了晕鱼了……"]
FOOD_LINES = {
    "🐟": ["小鱼干！我的最爱！", "咔嚓咔嚓……谢谢投喂！", "唔，鲜！"],
    "🍰": ["蛋糕！罪恶但快乐……", "甜到冒泡泡～", "嗝～又圆了一圈……"],
    "🍭": ["棒棒糖！转圈圈～", "嘎嘣脆，好吃！"],
    "🍡": ["三色团子！软乎乎～", "糯叽叽，爱了爱了！"],
    "💎": ["钻石？！这能吃吗……咕咚。真香！", "发财啦！明天开始吃高级鱼粮！"],
}
FOODS = ["🐟", "🍰", "🍭", "🍡", "💎"]

# 自启项的名字沿用飞行棋时期的，已经开过自启的用户关掉时还能删到
LAUNCH_AGENT = os.path.expanduser("~/Library/LaunchAgents/com.realroc.dafeiyu-board.plist")


class ChatDialog(QDialog):
    """聊天对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(float_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 56)

        container = QFrame(self)
        container.setGeometry(0, 0, 420, 56)
        container.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 20px;
                border: 1px solid #e5e7eb;
            }
        """)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(18, 0, 12, 0)
        layout.setSpacing(0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("给大肥鱼发送消息")
        self.input.setStyleSheet(f"""
            QLineEdit {{
                color: #1a1a1a;
                font-size: 15px;
                font-family: "{UI_FONT}", sans-serif;
                border: none;
                background: transparent;
            }}
        """)
        self.input.returnPressed.connect(self._on_submit)
        self.input.textChanged.connect(self._update_button_style)
        layout.addWidget(self.input)

        self.send_btn = QPushButton("↑")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.send_btn)
        self._update_button_style()

    def _update_button_style(self):
        base, hover, pressed = (("#5686fe", "#4575ed", "#3a66d9") if self.input.text().strip()
                                else ("#b9c7ff", "#a8b8f0", "#9aacd9"))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{ border-radius: 16px; background: {base}; border: none;
                           color: white; font-size: 20px; font-weight: bold; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {pressed}; }}
        """)

    def _on_submit(self):
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.accept()
            if self.parent():
                self.parent()._call_ds(text)
                self.parent().chat_paused = False

    def showEvent(self, event):
        self.input.setFocus()
        super().showEvent(event)

    def popup_at(self, x, y):
        self.move(int(x - self.width() / 2), int(y - self.height() - 10))
        self.show()
        self.raise_()
        self.activateWindow()

    def reject(self):
        if self.parent():
            self.parent().chat_paused = False
        super().reject()


class FunctionPanel(QFrame):
    """单击弹出的功能列表：聊天 / 爬塔"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(float_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.92);
                border-radius: 14px;
                border: 1px solid rgba(0,0,0,0.06);
            }
            QPushButton {
                background: transparent;
                border: none;
                padding: 6px;
                border-radius: 10px;
            }
            QPushButton:hover { background: rgba(0,0,0,0.04); }
            QPushButton:pressed { background: rgba(0,0,0,0.08); }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        for icon, tip, fn in (("🗨️", "聊天", self._on_chat_clicked), ("🗼", "爬塔", self._on_tower_clicked),
                              ("🏋️", "跟练", self._on_workout_clicked)):
            b = QPushButton(icon)
            b.setFont(emoji_font(26))
            b.setToolTip(tip)
            b.setFixedSize(52, 48)
            b.clicked.connect(fn)
            layout.addWidget(b)

        self.setFixedSize(176, 60)
        self.hide()

    def _on_chat_clicked(self):
        self.hide()
        if self.parent():
            self.parent()._show_chat_dialog()

    def _on_tower_clicked(self):
        self.hide()
        if self.parent():
            self.parent().open_tower()

    def _on_workout_clicked(self):
        self.hide()
        if self.parent():
            self.parent().show_workout_menu()

    def popup_at(self, x, y):
        self.move(int(x), int(y))
        self.show()
        self.raise_()


class FoodPanel(QWidget):
    """双击弹出的喂食面板"""

    def __init__(self, on_pick):
        super().__init__(None, float_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedSize(310, 64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        for f in FOODS:
            b = QToolButton()
            b.setText(f)
            b.setFont(emoji_font(24))
            b.setFixedSize(44, 44)
            b.setStyleSheet(
                "QToolButton{background:rgba(255,255,255,235);border:2px solid #ffb3c8;"
                "border-radius:22px;} QToolButton:hover{background:#ffe3ec;border-color:#ff7fa8;}")
            b.clicked.connect(lambda _, x=f: on_pick(x))
            lay.addWidget(b)
        close = QToolButton()
        close.setText("✕")
        close.setFont(QFont(UI_FONT, 12))
        close.setFixedSize(26, 26)
        close.setStyleSheet("QToolButton{background:rgba(255,255,255,200);border:none;border-radius:13px;color:#666;}"
                            "QToolButton:hover{background:#ff7fa8;color:#fff;}")
        close.clicked.connect(self.hide)
        lay.addWidget(close)
        self.setStyleSheet("FoodPanel{background:rgba(40,40,60,190);border-radius:14px;}")

    def popup_at(self, x, y):
        self.move(int(x - self.width() / 2), int(y - self.height() - 10))
        self.show()
        self.raise_()


class PetWindow(QWidget):
    def __init__(self, app, cfg):
        self.app = app
        self.cfg = cfg
        super().__init__(None, float_flags(self.cfg.get("topmost", True)))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("大肥鱼桌宠")

        # 精灵加载
        self.sprites = {}
        for mult in SIZE_LEVELS.values():
            h = int(SPRITE_SRC_H * mult)
            for name, pix in load_sprites(h).items():
                self.sprites[(name, h)] = pix
        self.icon = QIcon(os.path.join(SPRITE_DIR, "icon.png"))
        self.cur_h = int(SPRITE_SRC_H * self.cfg["size"])
        self.clip = ClipPlayer()
        self.workout = None
        self.frames = FrameCache()
        self.announcer = Announcer()
        self._layout_for_size()

        # 状态
        self.mode = self.cfg["mode"] if self.cfg["mode"] in ("wander", "follow", "still") else "wander"
        self.dir = "down"
        self.facing = 1
        self.target = None
        self.rest_until = 0
        self.cur_speed = 0.0
        self.prev_key = None
        self.cross_t = 0.0
        self.action = None
        self.action_t = 0.0
        self.expr = ExpressionPlayer()
        self.bubble_text = ""
        self.bubble_until = 0
        self.bubble_inner = False
        self.last_speak_tick = 0
        self.last_system_check = 0
        self.t = 0
        self.jump_t = 0
        self.dragging = False
        self.drag_offset = None
        self.drag_start_pos = None
        self.last_line = ""

        # AI 相关
        self.ds_busy = False
        self.chat_history = []  # 对话历史
        self.max_history = 40   # 最多记录40条
        self._say_queue = []    # 后台线程→主线程的气泡消息队列

        # 聊天暂停标志
        self.chat_paused = False

        self.function_panel = FunctionPanel(self)
        self.food_panel = FoodPanel(self.on_food)
        # 单击延迟判定（等双击）：单击=回嘴+弹功能面板，双击=喂食
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._on_single_click)
        self._after_dbl = False
        self.chat_dialog = ChatDialog(self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK)

        self.bubble_font = QFont(UI_FONT)
        self.bubble_font.setPixelSize(14)

        x, y = self.cfg.get("x"), self.cfg.get("y")
        if x is None or y is None:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.right() - self.width() - 80
            y = screen.bottom() - self.height() - 60
        self.move(int(x), int(y))

    def _layout_for_size(self):
        """窗口比鱼大一圈：头顶留气泡和表情符号的位置，两侧留表情的位置。
        播动作动画时按动画画面再撑大（放风筝、吹气球这些比人宽得多），播完缩回来。"""
        self.side = int(self.cur_h * 0.42)
        self.head_room = max(BUBBLE_H + MARGIN, int(self.cur_h * 0.32) + 12)
        sprite_w = max(pix_size(p)[0] for k, p in self.sprites.items() if k[1] == self.cur_h)
        self.win_w = int(sprite_w) + self.side * 2
        foot_room = MARGIN + 10
        ext = None
        if self.clip.active:
            ext = self.clip.extents(self.cur_h)
        elif self.workout and self.workout.clips:
            ext = workout.clip_extents(self.cur_h)
        elif self.workout:
            ext = self.frames.extents(self.workout.frames_in_use(), self.cur_h)
        if ext:
            left, right, up, down = ext
            self.win_w = max(self.win_w, int(2 * max(left, right)) + 8)
            self.head_room = max(self.head_room, int(up - self.cur_h) + BUBBLE_H + MARGIN)
            foot_room = max(foot_room, int(down) + MARGIN)
        self.setFixedSize(self.win_w, self.head_room + self.cur_h + foot_room)

    def _relayout(self):
        """改窗口大小，脚底位置不动。"""
        foot = self.foot_global()
        self._layout_for_size()
        self.place_foot_at(foot)

    # ---------- 和棋盘切换用 ----------
    def foot_global(self):
        return QPoint(self.x() + self.width() // 2, self.y() + self.head_room + self.cur_h)

    def place_foot_at(self, gp):
        self.move(gp.x() - self.width() // 2, gp.y() - self.head_room - self.cur_h)
        self.snap_into_screen()

    def apply_passthrough_from_cfg(self):
        if self.cfg.get("passthrough", False):
            self._apply_passthrough(True)

    # ---------- AI 方法 ----------
    def _call_ds(self, user_msg):
        if self.ds_busy:
            self.say("等等，上一句还没回完呢")
            return

        key = self.cfg.get("ds_api_key", "")
        if not key:
            self.say("请先在右键菜单里设置 DeepSeek Key！")
            return

        self.ds_busy = True

        messages = [{"role": "system", "content": DS_SYSTEM}]
        messages.extend(self.chat_history[-self.max_history:])
        messages.append({"role": "user", "content": user_msg})

        def worker():
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": DS_MODEL, "messages": messages, "max_tokens": 100, "temperature": 0.9}
            try:
                resp = requests.post(f"{DS_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=10)
                if resp.status_code == 200:
                    reply = resp.json()["choices"][0]["message"]["content"].strip()
                    if len(reply) > 30:
                        reply = reply[:28] + "…"
                    self.chat_history.append({"role": "user", "content": user_msg})
                    self.chat_history.append({"role": "assistant", "content": reply})
                    if len(self.chat_history) > self.max_history:
                        self.chat_history = self.chat_history[-self.max_history:]
                    self._queue_say(reply)
                else:
                    error_msg = resp.json().get("error", {}).get("message", str(resp.status_code))
                    self._queue_say(f"API错误: {error_msg[:12]}")
                    print(f"[DeepSeek] 状态码: {resp.status_code}, 返回: {resp.text}")
            except requests.exceptions.Timeout:
                self._queue_say("请求超时，检查网络")
            except requests.exceptions.ConnectionError:
                self._queue_say("连接失败，检查网络")
            except Exception as e:
                self._queue_say(f"请求失败: {str(e)[:12]}")
            finally:
                self.ds_busy = False

        threading.Thread(target=worker, daemon=True).start()

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = self.t * TICK / 1000.0
        cx = self.width() / 2
        bottom = self.head_room + self.cur_h

        walking = self.target is not None and not self.dragging
        if walking:
            sway = math.sin(now * 9.0) * 3.5
            bob = -abs(math.sin(now * 4.5)) * 7.0
        else:
            sway = math.sin(now * 2.5) * 1.5
            bob = 0.0
        breath = 1.0 + 0.02 * math.sin(now * 2.5)
        jump = -abs(math.sin(self.jump_t * 3.14159)) * 14 * self.jump_t if self.jump_t > 0 else 0
        act_rot = act_sx = act_sy = 0.0
        if self.action == "sway":
            act_rot = math.sin(self.action_t * 3.14159 * 2) * 10 * self.action_t
        elif self.action == "stretch":
            act_sy = 0.06 * math.sin(self.action_t * 3.14159)
            act_sx = -0.03 * math.sin(self.action_t * 3.14159)
        ex, ey, erot, esx, esy = self.expr.body(self.cur_h)

        def draw_one(key, opacity):
            if key is None:
                return
            name, h, facing = key
            pix = self.sprites[(name, h)]
            pw0, ph0 = pix_size(pix)
            ph = ph0 * breath * (1 + act_sy) * esy
            pw = pw0 * breath * (1 + act_sx)
            p.save()
            p.setOpacity(opacity)
            p.translate(cx + ex, bottom + ey + jump + bob)
            p.rotate(sway + act_rot + erot)
            p.scale(esx * (-1 if facing < 0 else 1), 1)
            p.drawPixmap(QRectF(-pw / 2, -ph, pw, ph), pix, QRectF(pix.rect()))
            p.restore()

        cur_key = self._sprite_key()
        view = self.expr.view()
        if self.workout and self.workout.clips:
            # 跟练动画：片段之间（准备、休息喝完水、等下一下）就是平时的正面图，片段首尾帧和它严丝合缝
            d = self.workout.clips
            if not d.player.active or d.player.blend() < 1:
                # 片段之间、片段开头结尾叠化时垫着的正面图：不摇不晃，只轻轻呼吸（脚底不动），和首尾帧对得上
                pix = self.sprites[("正面", self.cur_h)]
                pw, ph = pix_size(pix)
                ph *= 1 + 0.01 * math.sin(now * 2.5)
                p.drawPixmap(QRectF(cx - pw / 2, bottom - ph, pw, ph), pix, QRectF(pix.rect()))
            if d.player.active:
                d.player.draw(p, cx, bottom, self.cur_h, mirror=d.mirror)
            workout.draw_fx(p, self.workout.fx(), now, cx, bottom - self.cur_h, self.cur_h)
            if self.workout.show_timer:
                self._paint_countdown(p, cx + 0.44 * self.cur_h, bottom - 0.93 * self.cur_h)
            if self.bubble_text and now < self.bubble_until:
                self._paint_bubble(p, cx, max(4.0, self.head_room - BUBBLE_H + 4))
            return
        if self.workout:
            self._paint_workout(p, cx, bottom, now)
            if self.bubble_text and now < self.bubble_until:
                self._paint_bubble(p, cx, max(4.0, self.head_room - BUBBLE_H + 4))
            return
        if self.clip.active:
            # 动作动画开头结尾和正面图交叉淡化
            draw_one(cur_key, 1.0 - self.clip.blend())
            self.clip.draw(p, cx, bottom, self.cur_h)
        elif view:
            draw_one((view[0], self.cur_h, view[1]), 1.0)
        elif self.cross_t > 0:
            draw_one(self.prev_key, self.cross_t)
            draw_one(cur_key, 1.0 - self.cross_t)
        else:
            draw_one(cur_key, 1.0)

        self.expr.draw_overlay(p, cx + ex, bottom - self.cur_h + ey + jump + bob, self.cur_h)

        if self.bubble_text and now < self.bubble_until:
            self._paint_bubble(p, cx, max(4.0, self.head_room - BUBBLE_H + 4))

    def _paint_workout(self, p, cx, bottom, now):
        """跟练时画姿势帧（脚底对齐，交叉淡化，模糊帧的残影垫在下面），再叠头顶符号。"""
        pose = self.workout.pose()
        dx, dy, rot, sx, sy = pose.body
        fx = pose.fx
        h = self.cur_h
        dpr = self.devicePixelRatioF()
        top = bottom - h

        def blit(name, mirror, alpha, ody):
            pix, ax, ay, w, hh = self.frames.get(name, h, dpr)
            p.save()
            p.setOpacity(alpha)
            p.translate(cx + dx * h, bottom + ody * h)
            p.rotate(rot)
            p.scale(sx * (-1 if mirror else 1), sy)
            p.drawPixmap(QRectF(-ax, -ay, w, hh), pix, QRectF(pix.rect()))
            p.restore()
            return ay

        for name, mirror, alpha, gdy in pose.ghosts:
            blit(name, mirror, alpha, gdy)
        for name, mirror, alpha in pose.layers:
            ay = blit(name, mirror, alpha, dy)
            if alpha >= 0.5:
                top = bottom + dy * h - ay * sy
        workout.draw_fx(p, fx, now, cx + dx * h, top, h)
        if self.workout.show_timer:
            self._paint_countdown(p, cx + 0.44 * h, bottom - 0.93 * h)

    def _paint_countdown(self, p, x, y):
        """右上角的倒计时：两位数秒数，红色是练、绿色是歇、蓝色是准备；外圈是这一段的进度，下面小字是第几个动作。"""
        w = self.workout
        if w.finished:
            return
        seg = w.seg
        color = {"work": QColor(242, 72, 72), "rest": QColor(40, 178, 110), "prep": QColor(86, 134, 254)}[seg.kind]
        if w.paused:
            color = QColor(150, 150, 160)
        secs = int(math.ceil(w.remaining - 1e-6))
        r = self.cur_h * 0.105
        if not w.paused and secs <= 3 and seg.kind != "rest":
            r *= 1 + 0.15 * max(0.0, 1 - (secs - w.remaining) / 0.3)   # 最后 3 秒每秒跳一下
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 225))
        p.drawEllipse(QPointF(x, y), r, r)
        ring = QRectF(x - r + 2, y - r + 2, 2 * r - 4, 2 * r - 4)
        pen = QPen(QColor(color.red(), color.green(), color.blue(), 60), max(2.0, r * 0.16))
        p.setPen(pen)
        p.drawEllipse(ring)
        pen.setColor(color)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        left = w.remaining / seg.secs if seg.secs else 0.0
        p.drawArc(ring, 90 * 16, int(360 * 16 * left))
        text = "‖" if w.paused else (str(secs) if secs < 100 else f"{secs // 60}m")
        f = QFont(UI_FONT)
        f.setPixelSize(max(8, int(r * (0.95 if len(text) < 3 else 0.7))))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(x - r, y - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, text)
        if seg.kind != "prep":
            i, n = w.work_count()
            f.setPixelSize(max(8, int(r * 0.42)))
            f.setBold(False)
            p.setFont(f)
            p.setPen(QColor(90, 96, 120))
            label = f"{i}/{n}" + (f" · {seg.round_no}/{w.rounds}轮" if w.rounds > 1 else "")
            p.drawText(QRectF(x - 3 * r, y + r + 1, 6 * r, r * 0.6), Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

    def _paint_bubble(self, p, cx, top):
        if self.bubble_inner:
            bfont = QFont(self.bubble_font)
            bfont.setItalic(True)
            bg, fg = QColor(232, 232, 238, 235), QColor(125, 125, 138)
        else:
            bfont = QFont(self.bubble_font)
            bg, fg = QColor(255, 255, 255, 235), QColor(60, 60, 80)
        fm = QFontMetrics(bfont)
        max_w = min(240, self.width() - 16)
        lines = []
        cur = ""
        for ch in self.bubble_text:
            if fm.horizontalAdvance(cur + ch) > max_w - 20:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
        bw = max(fm.horizontalAdvance(l) for l in lines) + 20
        bh = len(lines) * fm.height() + 14
        bx = cx - bw / 2
        by = max(4.0, top + BUBBLE_H - 14 - bh)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
        tail = QPointF(cx, by + bh)
        p.drawPolygon(QPolygonF([tail, QPointF(tail.x() - 6, tail.y() + 8), QPointF(tail.x() + 6, tail.y() + 8)]))
        p.setPen(fg)
        p.setFont(bfont)
        for i, l in enumerate(lines):
            p.drawText(QRectF(bx, by + 7 + i * fm.height(), bw, fm.height()), Qt.AlignmentFlag.AlignCenter, l)

    def _sprite_key(self):
        name = {"left": "侧面", "right": "侧面", "up": "背面", "down": "正面"}[self.dir]
        return (name, self.cur_h, self.facing if self.dir in ("left", "right") else 1)

    def _set_dir(self, d, facing=None):
        if d != self.dir:
            self.prev_key = self._sprite_key()
            self.cross_t = 1.0
            self.dir = d
        if facing is not None and facing != self.facing:
            self.facing = facing

    # ---------- 逻辑 ----------
    def tick(self):
        if not self.isVisible():
            return
        self.t += 1

        # 处理后台线程（DeepSeek、天气）排队的气泡消息，Qt 界面必须在主线程更新
        if self._say_queue:
            for text in self._say_queue:
                self.say(text)
            self._say_queue.clear()

        self.check_system_status()

        if self.jump_t > 0:
            self.jump_t = max(0.0, self.jump_t - 0.06)
        if self.cross_t > 0:
            self.cross_t = max(0.0, self.cross_t - 0.15)
        if self.action_t > 0:
            self.action_t = max(0.0, self.action_t - 0.03)
            if self.action_t == 0:
                self.action = None
        self.expr.update(TICK / 1000.0)
        if self.clip.active:
            self.clip.update(TICK / 1000.0)
            if not self.clip.active:
                self._relayout()
                self.rest_until = self.t * TICK + random.randint(3000, 8000)   # 播完先站一会儿再走
        if self.workout:
            self._tick_workout()
        busy = self.expr.active or self.clip.active or self.workout is not None

        if self.chat_paused or self.dragging or busy:
            if busy:
                self.target = None
                self.cur_speed = 0.0
            self.update()
            return
        now_ms = self.t * TICK

        if self.mode == "follow":
            cursor = self.cursor().pos()
            screen = QApplication.screenAt(cursor) or self.screen() or QApplication.primaryScreen()
            geo = screen.availableGeometry()
            near = (self.x() - 100 <= cursor.x() <= self.x() + self.width() + 100 and
                    self.y() - 100 <= cursor.y() <= self.y() + self.height() + 100)
            if near:
                self.target = None
            else:
                tx = max(geo.left(), min(geo.right() - self.width(), cursor.x() - self.width() / 2))
                ty = max(geo.top(), min(geo.bottom() - self.height(), cursor.y() - 90))
                self.target = (tx, ty)
        elif self.mode == "wander":
            if self.target is None:
                if now_ms < self.rest_until:
                    self._maybe_idle_action()
                    self.update()
                    return
                geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
                self.target = (random.randint(geo.left() + 40, max(geo.left() + 41, geo.right() - self.width() - 40)),
                               random.randint(geo.top() + 40, max(geo.top() + 41, geo.bottom() - self.height() - 40)))
        else:
            self._maybe_idle_action()
            self.update()
            return

        if self.target is not None:
            cx, cy = self.x() + self.width() / 2, self.y() + self.height() / 2
            dx, dy = self.target[0] - cx, self.target[1] - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < 12:
                self.target = None
                self.rest_until = self.t * TICK + random.randint(8000, 18000)
                self._set_dir("down")
            else:
                step = self.cur_speed * TICK / 1000.0
                nx, ny = cx + dx / dist * step, cy + dy / dist * step
                self.move(int(nx - self.width() / 2), int(ny - self.height() / 2))
                if abs(dx) > abs(dy) * 1.15:
                    self._set_dir("left" if dx < 0 else "right", 1 if dx < 0 else -1)
                else:
                    self._set_dir("up" if dy < 0 else "down")
            if random.random() < 0.002 and self.jump_t == 0:
                self.jump_t = 0.5
        target_speed = SPEED if self.target is not None else 0.0
        self.cur_speed += (target_speed - self.cur_speed) * 0.3
        self.update()

    def _tick_workout(self):
        had_clips = self.workout.clips is not None
        for ev in self.workout.update(TICK / 1000.0):
            if ev[0] == "say":
                self.last_line = ""
                self.say(ev[1], inner=ev[2])
            elif ev[0] == "beep":
                self.announcer.beep(ev[1])
            elif ev[0] == "speak":
                self.announcer.speak(ev[1])
        if self.workout.done:
            self.stop_workout(finished=True)
        elif had_clips and self.workout.clips is None:   # 跟练动画放不了，退回姿势帧：窗口按姿势帧重排
            self._relayout()

    # ---------- 跟练 ----------
    def start_workout(self, plan, prep=True):
        rounds = self.cfg.get("workout_rounds", 0) if prep else 1
        self.stop_clip()
        self.expr.stop()
        self.announcer.stop()
        self.chat_paused = False
        self.jump_t = 0
        self.action = None
        self.target = None
        self._set_dir("down", 1)
        self.cross_t = 0.0
        self.workout = WorkoutPlayer(plan, rounds or None, prep=prep, slack=self.cfg.get("workout_slack", True),
                                     use_clips=True)
        self.announcer.voice = self.cfg.get("workout_voice", True) and prep
        self._relayout()

    def stop_workout(self, finished=False):
        if self.workout is None:
            return
        self.workout = None
        self.announcer.stop()
        self._relayout()
        self.rest_until = self.t * TICK + random.randint(6000, 12000)
        if not finished:
            self.last_line = ""
            self.say("不练啦？下次继续～")

    def workout_pause(self):
        if self.workout:
            paused = self.workout.toggle_pause()
            self.say("偷偷喘口气" if paused else "继续！", inner=paused)
            self.announcer.speak("暂停" if paused else "继续")

    def workout_skip(self):
        if self.workout:
            self.workout.skip()

    def workout_back(self):
        if self.workout:
            self.workout.back()

    def preview_move(self, key):
        self.start_workout(workout.single_move_plan(key), prep=False)

    def _add_workout_menu(self, m):
        wm = m.addMenu("🏋️ 跟练")
        if self.workout:
            wm.addAction("⏯ 暂停 / 继续（单击大肥鱼也行）", self.workout_pause)
            wm.addAction("⏮ 重来这段", self.workout_back)
            wm.addAction("⏭ 跳过这段", self.workout_skip)
            wm.addAction("✕ 结束跟练", self.stop_workout)
            wm.addSeparator()
        if not workout.available():
            wm.addAction("跟练素材缺失（content/workout/frames）").setEnabled(False)
            return wm
        plans, errors = workout.load_plans()
        for pid, plan in plans:
            total = sum(s.secs for s in workout.build_timeline(plan, self.cfg.get("workout_rounds", 0) or None))
            wm.addAction(f"{plan['name']} · {workout.fmt_secs(total)}",
                         lambda _checked=False, pl=plan: self.start_workout(pl))
        for err in errors:
            wm.addAction(f"⚠️ {err}"[:60]).setEnabled(False)
        wm.addSeparator()
        rm = wm.addMenu("轮数")
        for label, n in ROUND_CHOICES:
            a = rm.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg.get("workout_rounds", 0) == n)
            a.triggered.connect(lambda _checked=False, v=n: self.cfg.__setitem__("workout_rounds", v))
        pm = wm.addMenu("动作预览")
        moves = [(k, mv) for k, mv in workout.MOVES.items() if k != "stand"]
        for persona in (False, True):
            if persona:
                pm.addSeparator()   # 下面是大肥鱼的人设动作
            for key, mv in moves:
                if mv.persona == persona:
                    pm.addAction(mv.label, lambda _checked=False, k=key: self.preview_move(k))
        for label, key, default in (("语音播报", "workout_voice", True), ("大肥鱼会偷懒", "workout_slack", True)):
            a = wm.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg.get(key, default))
            a.triggered.connect(lambda on, k=key: self.cfg.__setitem__(k, bool(on)))
        wm.addAction("打开计划文件夹…", self.open_plan_dir)
        return wm

    def show_workout_menu(self):
        m = QMenu(self)
        self._add_workout_menu(m)
        m.actions()[0].menu().exec(self.cursor().pos())

    def open_plan_dir(self):
        path = workout.ensure_user_plan_dir()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.say(f"计划放在 {path}")

    def _maybe_idle_action(self):
        if random.random() < 0.01:
            pick = random.random()
            if pick < 0.3:
                self.jump_t = 1.0
            elif pick < 0.5:
                self.action, self.action_t = "sway", 1.0
            elif pick < 0.65:
                self.action, self.action_t = "stretch", 1.0
            elif pick < 0.7:
                # 偶尔自己冒个表情，不说话
                self.expr.start()
            elif pick < 0.8:
                if not (clips.AVAILABLE and self.play_clip()):
                    self.expr.start()
            elif pick < 0.9:
                if self.t - self.last_speak_tick >= 1500:
                    self.last_speak_tick = self.t
                    if pick < 0.82:
                        self.say(random.choice(INNER_LINES), inner=True)
                    else:
                        self.say(random.choice(LINES))

    def _queue_say(self, text):
        """后台线程调用：只入队，由主线程 tick 统一弹出显示（线程安全）"""
        self._say_queue.append(text)

    def say(self, text, inner=False):
        if text == self.last_line and not text.startswith("天气"):
            return
        self.last_line = text
        self.bubble_inner = inner
        self.bubble_text = f"（{text}）" if inner else text
        self.bubble_until = self.t * TICK / 1000.0 + 2.8
        self.update()

    def _busy_training(self):
        if self.workout:
            self.last_line = ""
            self.say("在练呢！练完再玩～")
            return True
        return False

    def play_expression(self, key=None):
        if self._busy_training():
            return
        self.stop_clip()
        self.chat_paused = False
        self.jump_t = 0
        self._set_dir("down", 1)
        _, line = self.expr.start(key)
        self.last_line = ""
        self.say(line)

    def play_clip(self, name=None):
        """播一段动作动画（不传则随机），返回播没播起来。"""
        if self._busy_training():
            return False
        self.expr.stop()
        self.chat_paused = False
        self.jump_t = 0
        self.action = None
        self._set_dir("down", 1)
        self.cross_t = 0.0
        # start() 会先停掉正在播的那段：新的打不开时窗口也要缩回三视图，不能留着撑大的透明区挡鼠标
        ok = self.clip.start(name) is not None
        self._relayout()
        return ok

    def play_random(self):
        """「做个表情 → 随机」：表情和动作动画一起抽，动画打不开就换成表情。"""
        n = len(EXPRESSIONS)
        if clips.AVAILABLE and random.random() < len(clips.CLIPS) / (n + len(clips.CLIPS)) and self.play_clip():
            return
        self.play_expression()

    def stop_clip(self):
        if self.clip.active:
            self.clip.stop()
            self._relayout()

    def check_system_status(self):
        now = self.t * TICK
        if now - self.last_system_check < 10000:
            return
        self.last_system_check = now

        cpu = psutil.cpu_percent()
        if cpu >= 90:
            self.say("CPU跑满了，再这样下去我就卡死了")
            return

        ram = psutil.virtual_memory().percent
        if ram >= 95:
            self.say("内存爆了，快关掉几个没用的东西吧，注意，别把我关了")
            return

        if GPU_AVAILABLE:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                if temp > 80:
                    self.say("我感觉我的鱼鳍快熟了")
            except Exception as e:
                print("GPU读取失败:", e)

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._after_dbl = False
            self.dragging = False
            self.drag_start_pos = e.globalPosition().toPoint()
            self.function_panel.hide()
            self.chat_dialog.hide()
            self.chat_paused = True

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and self.drag_start_pos is not None:
            delta = e.globalPosition().toPoint() - self.drag_start_pos
            if not self.dragging and delta.manhattanLength() > 6:
                self.dragging = True
                self.expr.stop()
                self.stop_clip()
                self.drag_offset = e.globalPosition().toPoint() - QPoint(self.x(), self.y())
            if self.dragging and self.drag_offset is not None:
                self.move(e.globalPosition().toPoint() - self.drag_offset)
                if abs(delta.x()) > 10:
                    self._set_dir("left" if delta.x() < 0 else "right", 1 if delta.x() < 0 else -1)
                self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.dragging:
                self.dragging = False
                self.drag_offset = None
                self._set_dir("down", 1)
                self.target = None
                self.rest_until = self.t * TICK + random.randint(6000, 14000)
                if random.random() < 0.5:
                    self.say(random.choice(DRAG_LINES))
                self.chat_paused = False
            elif self._after_dbl:
                self._after_dbl = False   # 双击的第二次松开，不再算单击
            else:
                self._click_timer.start(280)  # 等双击判定；单击则回嘴+弹功能面板
            self.drag_start_pos = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self._after_dbl = True
            self.chat_paused = False
            self.open_food_panel()

    def _on_single_click(self):
        """单击：蹦跳回嘴 + 弹功能面板（不想用点鱼身外关闭）；跟练时单击是暂停 / 继续"""
        if self.workout and not self.workout.finished:
            self.workout_pause()
            self.chat_paused = False
            return
        if random.random() < 0.7:
            self.jump_t = 1.0
        if random.random() < 0.6:
            self.say(random.choice(REACT_LINES))
        panel = self.function_panel
        panel.popup_at(self.x() + self.width() / 2 - panel.width() / 2,
                       self.y() + self.head_room - BUBBLE_H - panel.height() + 10)
        self.chat_paused = False

    def open_food_panel(self):
        self.food_panel.popup_at(self.x() + self.width() / 2, self.y() + self.head_room)

    def on_food(self, food):
        self.food_panel.hide()
        if self.workout:
            self.last_line = ""
            self.say("练完再吃！……就一口？")
            return
        self.stop_clip()
        self._set_dir("down", 1)
        self.expr.start_eat(food)
        self.jump_t = 0.6
        lines = FOOD_LINES.get(food, ["好吃！"])
        self.say(random.choice(lines))

    def _show_chat_dialog(self):
        key = self.cfg.get("ds_api_key", "")
        if not key:
            self.say("请先在右键菜单里设置 DeepSeek Key！")
            self.chat_paused = False
            return
        self.chat_paused = True
        self.chat_dialog.popup_at(self.x() + self.width() / 2, self.y() + self.head_room)

    def _get_weather(self):
        city = self.cfg.get("city", "汕头")
        self.say(f"正在看{city}的天……")

        def worker():
            weather_map = {
                "Sunny": "晴", "Clear": "晴", "Partly cloudy": "多云", "Cloudy": "阴",
                "Overcast": "阴", "Light rain": "小雨", "Moderate rain": "中雨", "Heavy rain": "大雨",
            }
            try:
                r = requests.get(f"https://wttr.in/{city}?format=j1", timeout=10,
                                 headers={"User-Agent": "Mozilla/5.0"})
                weather = r.json()["current_condition"][0]
                raw = weather["weatherDesc"][0]["value"].strip()
                self._queue_say(f"{city}今天{weather['temp_C']}°，天气{weather_map.get(raw, raw)}")
            except Exception as e:
                print("天气错误:", repr(e))
                self._queue_say("天气获取失败")

        threading.Thread(target=worker, daemon=True).start()

    def open_tower(self):
        """在系统浏览器里打开爬塔。它是独立的网页游戏，和桌宠不共用存档。"""
        if not os.path.isfile(TOWER_HTML):
            self.say("爬塔还没打包，先在 tower/ 里 npm run release")
            return
        # 交不给系统浏览器时 openUrl 返回 False（比如没有关联 .html 的程序），这时别报“去爬塔啦”
        if QDesktopServices.openUrl(QUrl.fromLocalFile(TOWER_HTML)):
            self.say("去爬塔啦！")
        else:
            print("爬塔打开失败:", TOWER_HTML)
            self.say("浏览器没打开，手动打开 content/tower/index.html")

    def _build_menu(self):
        m = QMenu(self)
        m.addAction("🗼 爬塔", self.open_tower)
        self._add_workout_menu(m)
        m.addSeparator()
        expr_menu = m.addMenu("做个表情")
        expr_menu.addAction("随机", self.play_random)
        expr_menu.addSeparator()
        for key, (name, _, _) in EXPRESSIONS.items():
            expr_menu.addAction(name, lambda k=key: self.play_expression(k))
        clips.add_menus(expr_menu, self.play_clip)
        m.addAction("喂食", self.open_food_panel)
        m.addAction("说句话", lambda: self.say(random.choice(LINES)))
        m.addSeparator()
        mode_menu = m.addMenu("模式")
        for label, key in [("自由散步", "wander"), ("跟随鼠标", "follow"), ("原地待着", "still")]:
            a = mode_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.mode == key)
            a.triggered.connect(lambda _, k=key: self.set_mode(k))
        size_menu = m.addMenu("大小")
        for label, mult in SIZE_LEVELS.items():
            a = size_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(abs(self.cur_h - SPRITE_SRC_H * mult) < 2)
            a.triggered.connect(lambda _, v=mult: self.set_size(v))
        m.addAction("设置 Key", self._set_key_dialog)
        m.addAction("设置城市", self._set_city_dialog)
        m.addAction("查看天气", self._get_weather)
        m.addSeparator()
        m.addAction("显示/隐藏", self.app.toggle_visible)
        m.addAction("回到屏幕内", self.snap_into_screen)
        pa = m.addAction("鼠标穿透（点不到它）")
        pa.setCheckable(True)
        pa.setChecked(self.cfg["passthrough"])
        pa.triggered.connect(lambda on: self.set_passthrough(on))
        ta = m.addAction("窗口置顶")
        ta.setCheckable(True)
        ta.setChecked(self.cfg["topmost"])
        ta.triggered.connect(lambda on: self.set_topmost(on))
        aa = m.addAction("开机自启")
        aa.setCheckable(True)
        aa.setChecked(self.cfg["autostart"])
        aa.triggered.connect(lambda on: self.set_autostart(on))
        m.addSeparator()
        m.addAction("退出", self.app.quit)
        return m

    def _set_key_dialog(self):
        key, ok = QInputDialog.getText(
            self, "设置 DeepSeek Key", "输入你的 API Key（从 platform.deepseek.com 获取）:",
            QLineEdit.EchoMode.Normal, self.cfg.get("ds_api_key", ""))
        if ok and key.strip():
            self.cfg["ds_api_key"] = key.strip()
            self.say("Key 设置成功！")
        elif ok and not key.strip():
            self.say("Key 不能为空")

    def _set_city_dialog(self):
        city, ok = QInputDialog.getText(self, "设置城市", "输入城市名:",
                                        QLineEdit.EchoMode.Normal, self.cfg.get("city", "汕头"))
        if ok and city.strip():
            self.cfg["city"] = city.strip()
            self.say(f"城市已设置为{city.strip()}")

    def contextMenuEvent(self, e):
        self.chat_paused = False
        self._build_menu().exec(e.globalPos())

    # ---------- 功能 ----------
    def set_mode(self, mode):
        self.mode = mode
        self.target = None
        self.cfg["mode"] = mode

    def set_size(self, mult):
        foot = self.foot_global()
        self.cur_h = int(SPRITE_SRC_H * mult)
        self.cfg["size"] = mult
        self.cross_t = 0.0
        self.prev_key = None
        self._layout_for_size()
        self.place_foot_at(foot)

    def snap_into_screen(self):
        geo = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        x = max(geo.left() - self.side, min(geo.right() - self.width() + self.side, self.x()))
        y = max(geo.top() - self.head_room // 2, min(geo.bottom() - self.height(), self.y()))
        self.move(x, y)

    def _apply_passthrough(self, on):
        if IS_WIN:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            style = style | WS_EX_LAYERED
            if on:
                style |= WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
        else:
            visible = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, bool(on))
            if visible:
                self.show()

    def set_passthrough(self, on):
        self.cfg["passthrough"] = bool(on)
        self._apply_passthrough(bool(on))
        if on:
            self.say("我隐身了！点菜单栏/托盘图标解除～")

    def set_topmost(self, on):
        self.cfg["topmost"] = bool(on)
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        if visible:
            self.show()

    def set_autostart(self, on):
        self.cfg["autostart"] = bool(on)
        frozen = getattr(sys, "frozen", False)
        script = "" if frozen else os.path.join(APP_DIR, "main.py")
        try:
            if IS_MAC:
                if on:
                    os.makedirs(os.path.dirname(LAUNCH_AGENT), exist_ok=True)
                    with open(LAUNCH_AGENT, "wb") as f:
                        plistlib.dump({
                            "Label": "com.realroc.dafeiyu-board",
                            "ProgramArguments": [sys.executable] + ([script] if script else []),
                            "WorkingDirectory": APP_DIR,
                            "RunAtLoad": True,
                        }, f)
                elif os.path.exists(LAUNCH_AGENT):
                    os.remove(LAUNCH_AGENT)
            elif IS_WIN:
                lnk = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                                   "Start Menu", "Programs", "Startup", "大肥鱼飞行棋.lnk")
                if on:
                    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                    target = sys.executable if frozen else (pythonw if os.path.exists(pythonw) else sys.executable)
                    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{}');"
                          "$s.TargetPath='{}';$s.Arguments='\"{}\"';$s.WorkingDirectory='{}';$s.Save()"
                          .format(lnk, target, script, APP_DIR))
                    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
                elif os.path.exists(lnk):
                    os.remove(lnk)
            else:
                raise RuntimeError("当前系统暂不支持")
            self.say("已开机自启，明天见～" if on else "已取消开机自启")
        except Exception as ex:
            self.cfg["autostart"] = False
            QMessageBox.warning(self, "开机自启", f"设置失败：{ex}")
