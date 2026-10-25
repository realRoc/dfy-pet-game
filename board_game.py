"""飞行棋盘窗口

棋盘是一张比窗口大的世界地图，镜头跟着大肥鱼走（像马里奥派对）：
点骰子 / 掷骰按钮（或按空格）掷出 1~6，大肥鱼逐格蹦过去；走到岔路口停下来让你选方向。
拖动地图可以四处看，滚轮缩放，左下角小地图点一下就跳过去，按 C 或「回到大肥鱼」镜头回来。
点右上角「收起」或按 Esc，棋盘收起，大肥鱼回到桌面继续当桌宠。

地图、格子类型、骰子皮肤来自 content/（见 game/content/loader.py），
规则在 game/core/rules.py，这里只负责镜头、动画、绘制和输入。
地图里的绘制都在世界坐标里进行，界面（顶栏、托盘、小地图、气泡）在窗口坐标里画。

精灵图与三视图朝向/呼吸/蹦跳的画法来自 dafeiyu-pet（MIT）：
https://github.com/1190fasheqi/dafeiyu-pet
"""
import math
import os
import random

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPoint, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QFontMetrics, QPolygonF, QPen, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget, QMenu

from common import ui_font, float_flags, load_sprites, pix_size
from expressions import EXPRESSIONS, ExpressionPlayer
from game.content import CONTENT_DIR, ContentError, load_dice_skin, load_map, load_tiles, map_names
from game.core.rules import Rules
from game.core.state import BoardState
from game.render.dice_renderer import DiceRenderer
from game.render.map_renderer import MapRenderer
from game.render.tile_renderer import TileRenderer

# ===== 动画参数（秒）=====
TICK_MS = 16
IDLE_TICK_MS = 80          # 没有动画时降到每秒十来帧，只够大肥鱼呼吸
MAX_DT = 0.1               # 卡顿时最多补这么多时间，免得一下跳太远
HOP_TIME = 0.26
HOP_HEIGHT = 40
LAND_TIME = 0.18
FADE_TIME = 0.12
CAM_FOLLOW = 5.0           # 镜头追角色的速度，越大越紧
EVENT_DELAY = 0.8          # 落地事件的台词先显示一会儿，再开始强制移动 / 传送
WARP_OUT, WARP_IN = 0.35, 0.45

# ===== 界面（窗口坐标）=====
MARGIN = 16
HUD_H = 46
TRAY_W, TRAY_H = 372, 100
MINI_W = 230
INK = QColor("#284D79")
CREAM = QColor(248, 242, 230, 240)

DEFAULT_MAP = "medieval"
START_LINE = "路过起点，发工资啦！+3 小鱼干"
ROLL_LINES = ["看我的！", "骰子骰子快显灵！", "这把必是六！", "大肥鱼，出击！"]
SIX_LINE = "六！我就说吧～"
ONE_LINE = "就……一步？"


def content_ids(kind):
    """content/maps 或 content/dice 下的目录名。"""
    path = os.path.join(CONTENT_DIR, kind)
    return sorted(n for n in os.listdir(path) if os.path.isdir(os.path.join(path, n)))


def load_content(cfg):
    """按配置加载地图和骰子皮肤；名字不存在时退回默认。骰子没指定时用地图自带的。"""
    tiles = load_tiles()
    try:
        graph = load_map(cfg.get("board_map") or DEFAULT_MAP, tiles=tiles)
    except ContentError as e:
        print(f"地图加载失败，改用 {DEFAULT_MAP}:", e)
        graph = load_map(DEFAULT_MAP, tiles=tiles)
    try:
        skin = load_dice_skin(cfg.get("dice_skin") or graph.dice)
    except ContentError as e:
        print("骰子皮肤加载失败，改用地图默认:", e)
        skin = load_dice_skin(graph.dice)
    return tiles, graph, skin


class BoardWindow(QWidget):
    def __init__(self, app, cfg):
        super().__init__(None, float_flags(cfg.get("topmost", True)))
        self.app = app
        self.cfg = cfg
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setWindowTitle("大肥鱼飞行棋")

        # 鱼的状态
        self.dir, self.facing = "down", 1
        self.prev_key, self.fade_t = None, 0.0
        self.land_t = 0.0
        self.expr = ExpressionPlayer()

        # 动画阶段: idle / rolling / settle / moving / choose / forced（事件强制移动）/ warp（事件传送）
        self.state = "idle"
        self.state_t = 0.0
        self.dice_face = random.randint(1, 6)
        self.roll_result = 0
        self.steps_left = 0
        self.dest_nodes = set()
        self.choices, self.choice_idx = [], 0
        self.forced_from, self.forced_nodes = None, []
        self.warp_from, self.fish_scale = None, 1.0
        self.glow_node, self.glow_t = None, 0.0
        self.hover_node = None
        self.press_btn = None

        self.board = None
        self.load_content()

        self.bubble_text, self.bubble_left = "", 0.0
        self.drag_off = None
        self.pan_from = None
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_ms = 0
        self.now = 0.0
        self.was_busy = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def load_content(self):
        """（重新）加载地图、格子、骰子，并按新地图调整窗口和镜头。"""
        self.tiles, self.graph, self.skin = load_content(self.cfg)
        self.rules = Rules(self.graph, self.tiles)
        self.map_painter = MapRenderer(self.graph)
        self.tile_painter = TileRenderer(self.tiles, self.graph.tile_style,
                                         (self.graph.art.get("tile_sprites", {}), self.map_painter))
        self.dice_painter = DiceRenderer(self.skin)
        self.fish_h = self.graph.fish_h
        self.tilt = self.graph.tilt
        self.sprites = load_sprites(self.fish_h)
        if self.board is None:
            self.board = BoardState.from_cfg(self.cfg, self.graph)
        else:
            # 换了地图：小鱼干、回合和暂停保留，从新地图起点出发
            self.board = BoardState(node_id=self.graph.start, coins=self.board.coins, turn=self.board.turn,
                                    skip_next=self.board.skip_next)
        self.hop_from = self.hop_to = self.board.node_id
        self.fish_xy = self.tile_anchor(self.board.node_id)
        self.fit_to_screen(QApplication.primaryScreen())
        self.recenter(snap=True)

    # ---------- 窗口与镜头 ----------
    def fit_to_screen(self, screen):
        """窗口用地图建议的尺寸，放不下时缩小；整张图都能看到的小地图跟着缩放。"""
        cw, ch = self.graph.canvas
        ww, wh = self.graph.window or (cw * self.graph.zoom, ch * self.graph.zoom)
        k = 1.0
        if screen is not None:
            geo = screen.availableGeometry()
            k = min(1.0, geo.width() * 0.94 / ww, geo.height() * 0.92 / wh)
        self.setFixedSize(max(1, int(ww * k)), max(1, int(wh * k)))
        self.base_zoom = self.graph.zoom * (k if self.fits_whole(self.graph.zoom, ww, wh) else 1.0)
        self.zoom = getattr(self, "zoom", self.base_zoom) if getattr(self, "_zoom_map", None) == self.graph.id \
            else self.base_zoom
        self._zoom_map = self.graph.id
        self.zoom = min(max(self.zoom, self.min_zoom()), self.max_zoom())

    def fits_whole(self, zoom, w=None, h=None):
        cw, ch = self.graph.canvas
        w, h = w or self.width(), h or self.height()
        return cw * zoom <= w + 1 and ch * zoom * self.graph.tilt <= h + 1

    def is_big(self):
        """世界比窗口大：镜头可以移动，有小地图。"""
        return not self.fits_whole(self.base_zoom)

    def min_zoom(self):
        cw, ch = self.graph.canvas
        return min(self.base_zoom, self.width() / cw, self.height() / (ch * self.tilt)) if self.is_big() else self.base_zoom

    def max_zoom(self):
        return self.base_zoom * 1.6 if self.is_big() else self.base_zoom

    def clamp_cam(self, c):
        cw, ch = self.graph.canvas
        hw, hh = self.width() / 2 / self.zoom, self.height() / 2 / (self.zoom * self.tilt)
        x = cw / 2 if cw <= hw * 2 else min(max(c.x(), hw), cw - hw)
        y = ch / 2 if ch <= hh * 2 else min(max(c.y(), hh), ch - hh)
        return QPointF(x, y)

    def fish_focus(self):
        g = self.ground_point()
        return QPointF(g.x(), g.y() - self.fish_h * 0.4 / self.tilt)

    def recenter(self, snap=False):
        self.cam_free = False
        if snap:
            self.cam = self.clamp_cam(self.fish_focus())

    def view_rect(self):
        w, h = self.width() / self.zoom, self.height() / (self.zoom * self.tilt)
        return QRectF(self.cam.x() - w / 2, self.cam.y() - h / 2, w, h)

    # 镜头：地面纵向按 tilt 压扁（像从斜上方看），建筑、树、角色、格子都直立着画在投影后的脚底位置
    def to_world(self, pos):
        return QPointF(self.cam.x() + (pos.x() - self.width() / 2) / self.zoom,
                       self.cam.y() + (pos.y() - self.height() / 2) / (self.zoom * self.tilt))

    def to_screen(self, wp):
        return QPointF((wp.x() - self.cam.x()) * self.zoom + self.width() / 2,
                       (wp.y() - self.cam.y()) * self.zoom * self.tilt + self.height() / 2)

    def upright(self, p, foot):
        """把画笔切到“直立”坐标：以 foot 为脚底，往上的高度不压扁。调用方负责 p.restore()。"""
        sp = self.to_screen(foot)
        p.save()
        p.translate(sp)
        p.scale(self.zoom, self.zoom)
        p.translate(-foot.x(), -foot.y())

    def upright_rect(self, rect, foot):
        """直立物体（世界坐标 rect、脚底 foot）在屏幕上的矩形。"""
        sp = self.to_screen(foot)
        z = self.zoom
        return QRectF(sp.x() + (rect.left() - foot.x()) * z, sp.y() + (rect.top() - foot.y()) * z,
                      rect.width() * z, rect.height() * z)

    def set_zoom(self, z, around=None):
        around = around or QPointF(self.width() / 2, self.height() / 2)
        before = self.to_world(around)
        self.zoom = min(max(z, self.min_zoom()), self.max_zoom())
        after = self.to_world(around)
        self.cam = self.clamp_cam(self.cam + (before - after))

    # ---------- 几何 ----------
    def tile_rect(self, node_id):
        ax, ay = self.graph.anchor(node_id)
        t = self.graph.tile
        return QRectF(ax - t / 2, ay - t / 2, t, t)

    def tile_anchor(self, node_id):
        """鱼脚站的位置（世界坐标）。"""
        ax, ay = self.graph.anchor(node_id)
        return QPointF(ax, ay + self.tile_painter.foot_offset(self.graph.tile))

    def node_at(self, pos):
        """屏幕坐标下指到的格子。"""
        for nid in self.graph.nodes:
            c = QPointF(*self.graph.anchor(nid))
            if self.upright_rect(self.tile_painter.shape(self.tile_rect(nid)), c).contains(pos):
                return nid
        return None

    def tray_rect(self):
        return QRectF(self.width() - MARGIN - TRAY_W, self.height() - MARGIN - TRAY_H, TRAY_W, TRAY_H)

    def dice_rect(self):
        tray = self.tray_rect()
        s = min(self.skin.size, TRAY_H - 22)
        return QRectF(tray.left() + 28, tray.center().y() - s / 2 - 2, s, s)

    def roll_btn_rect(self):
        tray = self.tray_rect()
        return QRectF(tray.right() - 24 - 176, tray.center().y() - 27, 176, 54)

    def hud_left_rect(self):
        title = f"⠿  🐋 大肥鱼飞行棋{'  · ' + self.graph.subtitle if self.graph.subtitle else ''}"
        return QRectF(MARGIN, MARGIN, QFontMetrics(ui_font(19, bold=True)).horizontalAdvance(title) + 40, HUD_H)

    def hud_right_rect(self):
        return QRectF(self.width() - MARGIN - 330, MARGIN, 330, HUD_H)

    def collapse_rect(self):
        hud = self.hud_right_rect()
        return QRectF(hud.right() - 8 - 86, hud.top() + 7, 86, HUD_H - 14)

    def home_btn_rect(self):
        return QRectF(MARGIN, MARGIN + HUD_H + 10, 150, 38)

    def minimap_rect(self):
        cw, ch = self.graph.canvas
        h = MINI_W * ch / cw
        return QRectF(MARGIN, self.height() - MARGIN - h, MINI_W, h)

    def choice_items(self):
        """岔路口每个出口的箭头：(出口节点, 屏幕上的标签框, 方向)。"""
        if self.state != "choose":
            return []
        here = self.to_screen(QPointF(*self.graph.anchor(self.board.node_id)))
        items = []
        f = ui_font(17, bold=True)
        for nid in self.choices:
            d = self.to_screen(QPointF(*self.graph.anchor(nid))) - here
            n = math.hypot(d.x(), d.y()) or 1
            d = QPointF(d.x() / n, d.y() / n)
            c = here + d * (self.graph.tile * self.zoom * 0.6 + 86)
            node = self.graph.node(nid)
            label = node.zone or self.tiles[node.type].name
            w = QFontMetrics(f).horizontalAdvance(label) + 58
            items.append((nid, QRectF(c.x() - w / 2, c.y() - 21, w, 42), d, label))
        return items

    # ---------- 和桌宠切换用 ----------
    def foot_global(self):
        s = self.to_screen(self.tile_anchor(self.board.node_id))
        return self.mapToGlobal(QPoint(int(s.x()), int(s.y())))

    def place_fish_at(self, gp):
        """把窗口摆到让鱼脚正好落在屏幕坐标 gp 上（再收回屏幕内）。"""
        screen = QApplication.screenAt(gp) or QApplication.primaryScreen()
        self.fit_to_screen(screen)
        self.recenter(snap=True)
        s = self.to_screen(self.tile_anchor(self.board.node_id))
        x, y = gp.x() - int(s.x()), gp.y() - int(s.y())
        geo = screen.availableGeometry()
        x = max(geo.left(), min(geo.right() - self.width(), x))
        y = max(geo.top(), min(geo.bottom() - self.height(), y))
        self.move(x, y)

    def save_state(self):
        self.cfg.update(self.board.to_cfg(self.graph), board_x=self.x(), board_y=self.y())

    def on_shown(self, greeting):
        self.set_dir("down")
        self.land_t = 1.0
        self.say(greeting, 3.0)

    # ---------- 交互 ----------
    def say(self, text, secs=2.6):
        self.bubble_text, self.bubble_left = text, secs
        self.wake()

    def wake(self):
        """有输入或新动画：马上整窗重画，恢复满帧。"""
        self.was_busy = True
        if self.timer.interval() != TICK_MS:
            self.timer.setInterval(TICK_MS)
        self.update()

    def animating(self):
        """掷骰 / 移动 / 选路 / 事件、镜头没停稳、气泡 / 表情 / 光圈还在播，就要满帧整窗重画。"""
        if self.state != "idle" or self.expr.active:
            return True
        if max(self.fade_t, self.land_t, self.glow_t) > 0 or (self.bubble_left > 0 and self.bubble_text):
            return True
        return not self.cam_free and self.cam != self.clamp_cam(self.fish_focus())

    def fish_rect(self):
        """空闲时画面上只有大肥鱼在呼吸，只重画它这一块（留出影子和左右摆动的余量）。"""
        h = self.fish_h
        box = QRectF(self.fish_xy.x() - h * 0.55, self.fish_xy.y() - h * 1.15, h * 1.1, h * 1.15 + 14)
        return self.upright_rect(box, self.ground_point()).adjusted(-4, -4, 4, 4).toAlignedRect()

    def roll(self):
        if self.state != "idle":
            return
        self.expr.stop()
        self.recenter()
        result = self.rules.begin_turn(self.board)
        if result is None:
            self.say("泡泡还没破……这回合歇着 😼")
            return
        self.state, self.state_t = "rolling", 0.0
        self.roll_result = result
        self.dice_painter.begin_roll(result, self.dice_face)
        if self.skin.style == "cube":
            self.dice_face = result
        self.say(random.choice(ROLL_LINES), self.skin.rolling_time + self.skin.reveal_time)

    def restart(self):
        if self.state != "idle":
            return
        self.board = BoardState(node_id=self.graph.start)
        self.fish_xy = self.tile_anchor(self.board.node_id)
        self.recenter(snap=True)
        self.set_dir("down")
        self.say("重新开始！")

    def switch_map(self, map_id):
        if self.state != "idle" or map_id == self.graph.id:
            return
        foot = self.foot_global()
        self.cfg["board_map"] = map_id
        self.load_content()
        self.place_fish_at(foot)
        self.say(f"来到了「{self.graph.name}」！")

    def switch_dice(self, skin_id):
        if self.state != "idle":
            return
        self.cfg["dice_skin"] = skin_id
        self.skin = load_dice_skin(skin_id or self.graph.dice)
        self.dice_painter = DiceRenderer(self.skin)
        self.say(f"换上了{self.skin.name}骰子")

    def play_expression(self, key=None):
        if self.state != "idle":
            return
        self.set_dir("down")
        name, line = self.expr.start(key)
        self.say(line, self.expr.dur + 0.6)
        return name

    def collapse(self):
        if self.state == "idle":
            self.app.collapse_board()

    def set_dir(self, d, facing=1):
        if (d, facing) != (self.dir, self.facing):
            self.prev_key = self.sprite_key()
            self.fade_t = 1.0
            self.dir, self.facing = d, facing

    def sprite_key(self):
        name = {"left": "侧面", "right": "侧面", "up": "背面", "down": "正面"}[self.dir]
        return name, (self.facing if self.dir in ("left", "right") else 1)

    def face_towards(self, a, b):
        (ax, ay), (bx, by) = self.graph.anchor(a), self.graph.anchor(b)
        dx, dy = bx - ax, by - ay
        if abs(dx) > abs(dy):
            # 侧面原图朝左，向右走时镜像
            self.set_dir("left" if dx < 0 else "right", 1 if dx < 0 else -1)
        else:
            self.set_dir("up" if dy < 0 else "down")

    def continue_move(self):
        """还有步数：单出口直接走，岔路口停下来等玩家选。"""
        exits = self.graph.exits(self.board.node_id)
        if len(exits) == 1:
            self.start_hop(exits[0])
            return
        self.state, self.state_t = "choose", 0.0
        self.choices, self.choice_idx = list(exits), 0
        self.set_dir("down")
        self.recenter()
        self.bubble_left = 0      # 选项标签就在脚边，气泡会挡住它们

    def choose(self, idx):
        if self.state != "choose" or not (0 <= idx < len(self.choices)):
            return
        dst = self.choices[idx]
        self.choices = []
        self.bubble_left = 0
        self.dest_nodes = self.graph.destinations(dst, self.steps_left - 1)
        self.start_hop(dst)

    def start_hop(self, dst):
        self.hop_from, self.hop_to = self.board.node_id, dst
        self.face_towards(self.hop_from, self.hop_to)
        self.state, self.state_t = "moving", 0.0

    def finish_move(self):
        self.state = "idle"
        self.dest_nodes = set()
        self.set_dir("down")
        self.glow_node, self.glow_t = self.board.node_id, 1.0
        here = self.board.node_id
        landing = self.rules.land(self.board)
        if landing.expression:
            key = landing.expression if landing.expression in EXPRESSIONS else None
            name, line = self.expr.start(key)
            self.say(landing.say or f"【{name}】{line}", max(3.0, self.expr.dur + 0.8))
        elif landing.say:
            self.say(landing.say, 3.0)
        # 位置在 land() 里已经改好，这里只播动画
        if landing.path:
            self.forced_from, self.forced_nodes = here, list(landing.path)
            self.state, self.state_t = "forced", 0.0
        elif landing.warp_to:
            self.warp_from = here
            self.state, self.state_t = "warp", 0.0

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.wake()
        pos = e.position()
        if self.collapse_rect().contains(pos):
            self.collapse()
        elif self.roll_btn_rect().contains(pos) or self.dice_rect().adjusted(-8, -8, 8, 8).contains(pos):
            self.press_btn = "roll"
        elif self.cam_free and self.home_btn_rect().contains(pos):
            self.recenter()
        elif self.is_big() and self.minimap_rect().contains(pos):
            self.press_btn = "minimap"
            self.jump_minimap(pos)
        elif any(rc.contains(pos) for _, rc, _, _ in self.choice_items()):
            for i, (_, rc, _, _) in enumerate(self.choice_items()):
                if rc.contains(pos):
                    self.choose(i)
                    break
        elif self.hud_left_rect().contains(pos) or not self.is_big():
            if not (self.tray_rect().contains(pos) or self.hud_right_rect().contains(pos)):
                self.drag_off = e.globalPosition().toPoint() - self.pos()
        elif not (self.tray_rect().contains(pos) or self.hud_right_rect().contains(pos)):
            self.pan_from = (pos, QPointF(self.cam))

    def jump_minimap(self, pos):
        mm = self.minimap_rect()
        cw, ch = self.graph.canvas
        self.cam = self.clamp_cam(QPointF((pos.x() - mm.left()) / mm.width() * cw,
                                          (pos.y() - mm.top()) / mm.height() * ch))
        self.cam_free = True

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.drag_off is not None:
            self.move(e.globalPosition().toPoint() - self.drag_off)
            return
        if self.press_btn == "minimap":
            self.jump_minimap(pos)
            self.wake()
            return
        if self.pan_from is not None:
            start, cam0 = self.pan_from
            d = pos - start
            if self.cam_free or math.hypot(d.x(), d.y()) > 4:
                self.cam = self.clamp_cam(cam0 - QPointF(d.x() / self.zoom, d.y() / (self.zoom * self.tilt)))
                self.cam_free = True
                self.wake()
            return
        node = self.node_at(pos)
        if node != self.hover_node:
            self.hover_node = node
            self.wake()

    def mouseReleaseEvent(self, e):
        pos = e.position()
        if self.press_btn == "roll" and (self.roll_btn_rect().contains(pos)
                                         or self.dice_rect().adjusted(-8, -8, 8, 8).contains(pos)):
            self.roll()
        self.press_btn = None
        self.drag_off = None
        self.pan_from = None
        self.wake()

    def wheelEvent(self, e):
        if not self.is_big():
            return
        steps = e.angleDelta().y() / 120
        self.set_zoom(self.zoom * (1.12 ** steps), e.position())
        self.cam_free = True
        self.wake()

    def leaveEvent(self, _):
        if self.hover_node is not None:
            self.hover_node = None
            self.wake()

    def keyPressEvent(self, e):
        k = e.key()
        if e.isAutoRepeat() and k not in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            return
        self.wake()
        if self.state == "choose":
            if k in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                self.choice_idx = (self.choice_idx - 1) % len(self.choices)
            elif k in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab):
                self.choice_idx = (self.choice_idx + 1) % len(self.choices)
            elif k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.choose(self.choice_idx)
            elif Qt.Key.Key_1 <= k <= Qt.Key.Key_9:
                self.choose(k - Qt.Key.Key_1)
            return
        if k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.roll()
        elif k == Qt.Key.Key_C:
            self.recenter()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) and self.is_big():
            self.set_zoom(self.zoom * 1.15)
        elif k == Qt.Key.Key_Minus and self.is_big():
            self.set_zoom(self.zoom / 1.15)
        elif k == Qt.Key.Key_Escape:
            self.collapse()

    def contextMenuEvent(self, e):
        busy = self.state != "idle"
        m = QMenu(self)
        a = m.addAction("掷骰子", self.roll)
        a.setEnabled(not busy)
        m.addAction("镜头回到大肥鱼", self.recenter)
        expr_menu = m.addMenu("做个表情")
        expr_menu.setEnabled(not busy)
        expr_menu.addAction("随机", self.play_expression)
        expr_menu.addSeparator()
        for key, (name, _, _) in EXPRESSIONS.items():
            expr_menu.addAction(name, lambda k=key: self.play_expression(k))
        map_menu = m.addMenu("换地图")
        map_menu.setEnabled(not busy)
        for map_id, name in map_names().items():
            act = map_menu.addAction(name, lambda i=map_id: self.switch_map(i))
            act.setCheckable(True)
            act.setChecked(map_id == self.graph.id)
        dice_menu = m.addMenu("换骰子")
        dice_menu.setEnabled(not busy)
        act = dice_menu.addAction("跟随地图", lambda: self.switch_dice(None))
        act.setCheckable(True)
        act.setChecked(not self.cfg.get("dice_skin"))
        for skin_id in content_ids("dice"):
            act = dice_menu.addAction(skin_id, lambda i=skin_id: self.switch_dice(i))
            act.setCheckable(True)
            act.setChecked(self.cfg.get("dice_skin") == skin_id)
        a = m.addAction("重新开始", self.restart)
        a.setEnabled(not busy)
        m.addSeparator()
        a = m.addAction("收起棋盘", self.collapse)
        a.setEnabled(not busy)
        m.addAction("退出", self.app.quit)
        m.exec(e.globalPos())
        self.wake()

    # 收起棋盘（回到桌宠）时整个停掉，不再每 16ms 醒一次
    def showEvent(self, e):
        self.last_ms = self.clock.elapsed()
        self.was_busy = True
        self.timer.start(TICK_MS)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    # ---------- 逻辑 ----------
    def tick(self):
        ms = self.clock.elapsed()
        dt = min(MAX_DT, (ms - self.last_ms) / 1000.0)
        self.last_ms = ms
        if not self.isVisible():
            return
        self.now += dt
        self.state_t += dt
        self.fade_t = max(0.0, self.fade_t - dt / FADE_TIME)
        self.land_t = max(0.0, self.land_t - dt / LAND_TIME)
        self.glow_t = max(0.0, self.glow_t - dt / 1.2)
        self.bubble_left -= dt
        self.expr.update(dt)

        if self.state == "rolling":
            if self.skin.style == "flat":
                # 每 70ms 换一个面，越到后面越慢；只是装饰，结果在 roll() 里已经定了
                step = 0.07 + 0.08 * (self.state_t / self.skin.roll_time) ** 2
                if self.state_t % step < dt:
                    self.dice_face = random.choice([f for f in range(1, 7) if f != self.dice_face])
            if self.state_t >= self.skin.rolling_time:
                self.dice_face = self.roll_result
                self.dest_nodes = self.graph.destinations(self.board.node_id, self.roll_result)
                self.state, self.state_t = "settle", 0.0
                if self.roll_result == 6:
                    self.say(SIX_LINE)
                elif self.roll_result == 1:
                    self.say(ONE_LINE)
        elif self.state == "settle":
            if self.state_t >= self.skin.reveal_time:
                self.steps_left = self.roll_result
                self.continue_move()
        elif self.state == "moving":
            u = min(1.0, self.state_t / HOP_TIME)
            a, b = self.tile_anchor(self.hop_from), self.tile_anchor(self.hop_to)
            self.fish_xy = QPointF(a.x() + (b.x() - a.x()) * u,
                                   a.y() + (b.y() - a.y()) * u - HOP_HEIGHT * 4 * u * (1 - u))
            if u >= 1.0:
                # 跳完这条边才真正结算：位置和起点工资
                hop = self.rules.hop(self.board, self.hop_to)
                self.land_t = 1.0
                self.steps_left -= 1
                if hop.wage:
                    self.say(START_LINE)
                if self.steps_left > 0:
                    self.continue_move()
                else:
                    self.finish_move()

        elif self.state == "forced":
            self.tick_forced()
        elif self.state == "warp":
            self.tick_warp()

        if not self.cam_free:
            target = self.clamp_cam(self.fish_focus())
            d = target - self.cam
            # 追到很近就直接贴上，镜头停稳了才能降频
            self.cam = target if abs(d.x()) + abs(d.y()) < 0.3 else self.cam + d * min(1.0, dt * CAM_FOLLOW)
        self.cam = self.clamp_cam(self.cam)

        busy = self.animating()
        if busy or self.was_busy:
            self.update()           # 刚停下的这一帧也整窗画，擦掉消失的气泡和光圈
        else:
            self.update(self.fish_rect())
        self.was_busy = busy
        interval = TICK_MS if busy else IDLE_TICK_MS
        if self.timer.interval() != interval:
            self.timer.setInterval(interval)

    def tick_forced(self):
        """事件推着走：沿 forced_nodes 一格格跳，不结算格子。"""
        t = self.state_t - EVENT_DELAY
        if t < 0:
            return
        a, b = self.forced_from, self.forced_nodes[0]
        if t < 0.02:
            self.face_towards(a, b)
        u = min(1.0, t / HOP_TIME)
        pa, pb = self.tile_anchor(a), self.tile_anchor(b)
        self.fish_xy = QPointF(pa.x() + (pb.x() - pa.x()) * u,
                               pa.y() + (pb.y() - pa.y()) * u - HOP_HEIGHT * 4 * u * (1 - u))
        if u >= 1.0:
            self.land_t = 1.0
            self.forced_from = self.forced_nodes.pop(0)
            if self.forced_nodes:
                self.state_t = EVENT_DELAY
            else:
                self.state = "idle"
                self.set_dir("down")
                self.glow_node, self.glow_t = self.board.node_id, 1.0

    def tick_warp(self):
        """事件传送：原地缩小消失，镜头飞过去，在目的地弹出来。"""
        t = self.state_t - EVENT_DELAY
        if t < 0:
            return
        if t < WARP_OUT:
            self.fish_scale = 1 - t / WARP_OUT
            return
        if self.warp_from is not None:
            self.warp_from = None
            self.fish_xy = self.tile_anchor(self.board.node_id)
            self.set_dir("down")
        u = min(1.0, (t - WARP_OUT) / WARP_IN)
        self.fish_scale = max(0.01, 1 + 0.15 * math.sin(u * math.pi)) * u
        if u >= 1.0:
            self.fish_scale = 1.0
            self.land_t = 1.0
            self.state = "idle"
            self.glow_node, self.glow_t = self.board.node_id, 1.0

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        dpr = self.devicePixelRatioF()
        device_scale = self.zoom * dpr
        self.tile_painter.device_scale = device_scale

        p.save()
        if self.is_big():
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 28, 28)
            p.setClipPath(path)
        # 地面层：纵向压扁
        p.save()
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(self.zoom, self.zoom * self.tilt)
        p.translate(-self.cam.x(), -self.cam.y())
        # 只画要重画的区域（空闲时只有大肥鱼那一块）
        dirty = QRectF(e.rect())
        view = QRectF(self.to_world(dirty.topLeft()), self.to_world(dirty.bottomRight()))
        self.map_painter.paint_ground_cached(p, view, math.ceil(self.zoom * 4) / 4, dpr, self.tilt)
        p.restore()

        # 格子、建筑、角色：直立地画在脚底的投影位置
        screen = dirty.adjusted(-40, -40, 40, 40)
        mark = 0.5 + 0.5 * math.sin(self.now * 6)
        for nid in sorted(self.graph.nodes, key=lambda n: self.graph.anchor(n)[1]):
            rc, c = self.tile_rect(nid), QPointF(*self.graph.anchor(nid))
            if not screen.intersects(self.upright_rect(rc, c)):
                continue
            glow = self.glow_t if nid == self.glow_node else 0.0
            self.upright(p, c)
            self.tile_painter.paint(p, rc, self.graph.node(nid).type, glow,
                                    mark if nid in self.dest_nodes else 0.0, nid == self.hover_node)
            p.restore()
        self.paint_world_objects(p, screen, device_scale)
        if self.hover_node:
            c = QPointF(*self.graph.anchor(self.hover_node))
            self.upright(p, c)
            self.tile_painter.paint_label(p, self.tile_rect(self.hover_node),
                                          self.graph.node(self.hover_node).type, self.graph.canvas[0])
            p.restore()
        p.restore()

        self.paint_choices(p)
        if dirty.top() <= self.home_btn_rect().bottom() + 2:
            self.paint_hud(p)
        if self.is_big() and dirty.intersects(self.minimap_rect().adjusted(-6, -6, 6, 6)):
            self.paint_minimap(p)
        if dirty.bottom() >= self.tray_rect().top() - 2:
            self.paint_tray(p)
        self.paint_bubble(p)

    def paint_world_objects(self, p, screen, device_scale):
        """建筑 / 树等贴图和大肥鱼按脚底 y 排序；挡住大肥鱼的贴图变半透明。"""
        hopping = self.state in ("moving", "forced")
        ground = self.ground_point()
        fish_box = self.upright_rect(QRectF(self.fish_xy.x() - self.fish_h * 0.3, self.fish_xy.y() - self.fish_h,
                                            self.fish_h * 0.6, self.fish_h), ground)
        items = []
        for obj in self.map_painter.objects:
            foot = QPointF(obj.x, obj.y)
            r = self.upright_rect(obj.rect, foot)
            if r.intersects(screen):
                items.append((obj.y, obj, foot, r))
        items.append((ground.y(), None, ground, None))
        for _, obj, foot, r in sorted(items, key=lambda it: it[0]):
            self.upright(p, foot)
            if obj is None:
                self.paint_fish(p, ground, hopping)
            else:
                cover = obj.y > ground.y() and r.intersects(fish_box)
                self.map_painter.paint_object(p, obj, device_scale, 0.45 if cover else 1.0)
            p.restore()

    def ground_point(self):
        if self.state == "forced":
            t = self.state_t - EVENT_DELAY
            if t < 0 or not self.forced_nodes:
                return self.tile_anchor(self.forced_from)
            u = min(1.0, t / HOP_TIME)
            a, b = self.tile_anchor(self.forced_from), self.tile_anchor(self.forced_nodes[0])
            return QPointF(a.x() + (b.x() - a.x()) * u, a.y() + (b.y() - a.y()) * u)
        if self.state == "warp" and self.warp_from is not None:
            return self.tile_anchor(self.warp_from)
        if self.state != "moving":
            return self.tile_anchor(self.board.node_id)
        u = min(1.0, self.state_t / HOP_TIME)
        a, b = self.tile_anchor(self.hop_from), self.tile_anchor(self.hop_to)
        return QPointF(a.x() + (b.x() - a.x()) * u, a.y() + (b.y() - a.y()) * u)

    def pill(self, p, rc, fill=CREAM, edge=QColor(40, 77, 121, 60)):
        p.setPen(QPen(edge, 1.2))
        p.setBrush(fill)
        p.drawRoundedRect(rc, rc.height() / 2, rc.height() / 2)

    def paint_choices(self, p):
        items = self.choice_items()
        if not items:
            return
        pulse = 0.5 + 0.5 * math.sin(self.now * 5)
        for i, (_, rc, d, label) in enumerate(items):
            on = i == self.choice_idx
            if on:
                glow = QColor(255, 214, 102, int(120 + 100 * pulse))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glow)
                p.drawRoundedRect(rc.adjusted(-5, -5, 5, 5), rc.height() / 2 + 5, rc.height() / 2 + 5)
            self.pill(p, rc, QColor(255, 255, 255, 245) if on else CREAM,
                      INK if on else QColor(40, 77, 121, 90))
            # 指向出口的小三角
            c = QPointF(rc.left() + 24, rc.center().y())
            ang = math.atan2(d.y(), d.x())
            tri = QPolygonF([QPointF(c.x() + math.cos(ang + a) * r, c.y() + math.sin(ang + a) * r)
                             for a, r in ((0, 11), (2.4, 9), (-2.4, 9))])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(INK)
            p.drawPolygon(tri)
            p.setFont(ui_font(17, bold=True))
            p.setPen(INK)
            p.drawText(rc.adjusted(40, 0, -14, 0), Qt.AlignmentFlag.AlignVCenter, label)

    def paint_hud(self, p):
        # 左上：拖动柄 + 名字 + 地图副标题
        left = self.hud_left_rect()
        self.pill(p, left)
        p.setFont(ui_font(19, bold=True))
        p.setPen(INK)
        p.drawText(left.adjusted(18, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter,
                   f"⠿  🐋 大肥鱼飞行棋{'  · ' + self.graph.subtitle if self.graph.subtitle else ''}")
        if self.cam_free:
            btn = self.home_btn_rect()
            self.pill(p, btn, QColor(255, 255, 255, 240), INK)
            p.setFont(ui_font(15, bold=True))
            p.drawText(btn, Qt.AlignmentFlag.AlignCenter, "📍 回到大肥鱼")

        # 右上：小鱼干、回合、收起
        hud = self.hud_right_rect()
        self.pill(p, hud)
        p.setFont(ui_font(18, bold=True))
        p.setPen(INK)
        p.drawText(QRectF(hud.left() + 20, hud.top(), 120, HUD_H), Qt.AlignmentFlag.AlignVCenter,
                   f"🐟 {self.board.coins}")
        p.setFont(ui_font(17))
        p.drawText(QRectF(hud.left() + 104, hud.top(), 120, HUD_H), Qt.AlignmentFlag.AlignVCenter,
                   f"第 {self.board.turn} 回合")
        rc = self.collapse_rect()
        idle = self.state == "idle"
        p.setPen(QPen(QColor(40, 77, 121, 120 if idle else 50), 1.2))
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawRoundedRect(rc, rc.height() / 2, rc.height() / 2)
        p.setFont(ui_font(16, bold=True))
        p.setPen(INK if idle else QColor(170, 175, 190))
        p.drawText(rc, Qt.AlignmentFlag.AlignCenter, "收起 ▾")

    def paint_minimap(self, p):
        mm = self.minimap_rect()
        pix = self.map_painter.minimap(MINI_W * self.devicePixelRatioF())
        p.setPen(QPen(QColor(40, 77, 121, 90), 1.5))
        p.setBrush(CREAM)
        p.drawRoundedRect(mm.adjusted(-5, -5, 5, 5), 14, 14)
        p.drawPixmap(mm, pix, QRectF(pix.rect()))
        cw, ch = self.graph.canvas
        k = mm.width() / cw

        def mp(x, y):
            return QPointF(mm.left() + x * k, mm.top() + y * k)

        p.setPen(Qt.PenStyle.NoPen)
        for nid in self.dest_nodes:
            p.setBrush(QColor(255, 214, 102))
            p.drawEllipse(mp(*self.graph.anchor(nid)), 3.5, 3.5)
        v = self.view_rect()
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.6))
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRect(QRectF(mp(v.left(), v.top()), mp(v.right(), v.bottom())).intersected(mm))
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.setBrush(INK)
        p.drawEllipse(mp(self.fish_xy.x(), self.fish_xy.y()), 5, 5)

    def paint_tray(self, p):
        # 左下：状态与操作提示（大地图时让出小地图的位置）
        notes = []
        if self.board.skip_next:
            notes.append("🫧 下回合暂停")
        notes.append("空格掷骰 · 拖动看地图 · 滚轮缩放 · Esc 收起" if self.is_big()
                     else "空格掷骰 · 悬停看格子 · 右键换地图 · Esc 收起")
        text = "   ".join(notes)
        f = ui_font(15)
        left = MARGIN * 2 + MINI_W if self.is_big() else MARGIN
        w = min(QFontMetrics(f).horizontalAdvance(text) + 36, self.width() - TRAY_W - MARGIN * 2 - left)
        hint = QRectF(left, self.height() - MARGIN - 40, w, 40)
        self.pill(p, hint, QColor(248, 242, 230, 215))
        p.setFont(f)
        p.setPen(QColor(70, 95, 130))
        p.drawText(hint, Qt.AlignmentFlag.AlignCenter, text)

        # 右下：骰子 + 掷骰按钮
        tray = self.tray_rect()
        p.setPen(QPen(QColor(40, 77, 121, 60), 1.2))
        p.setBrush(CREAM)
        p.drawRoundedRect(tray, 28, 28)
        phase = self.state if self.state in ("rolling", "settle") else "idle"
        can_roll = self.state == "idle"
        self.dice_painter.paint(p, self.dice_rect(), self.dice_face, phase, self.state_t,
                                can_roll and not self.board.skip_next)

        btn = self.roll_btn_rect()
        if self.state == "rolling":
            label = "掷骰中…"
        elif self.state == "choose":
            label = f"选方向 · 剩 {self.steps_left} 步"
        elif self.state == "forced":
            label = "被推着走…"
        elif self.state == "warp":
            label = "传送中…"
        elif self.state in ("settle", "moving"):
            label = f"前进 {self.steps_left if self.state == 'moving' else self.roll_result} 步"
        elif self.board.skip_next:
            label = "歇一回合"
        else:
            label = "掷骰子"
        pressed = self.press_btn == "roll"
        fill = INK if can_roll else QColor(150, 165, 190)
        if pressed:
            fill = fill.darker(115)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 40, 70, 60))
        p.drawRoundedRect(btn.translated(0, 3), btn.height() / 2, btn.height() / 2)
        p.setBrush(fill)
        p.drawRoundedRect(btn.translated(0, 2 if pressed else 0), btn.height() / 2, btn.height() / 2)
        p.setFont(ui_font(20 if self.state == "choose" else 22, bold=True))
        p.setPen(QColor(255, 255, 255))
        p.drawText(btn.translated(0, 2 if pressed else 0), Qt.AlignmentFlag.AlignCenter, label)

    def paint_fish(self, p, ground, hopping):
        x, y = self.fish_xy.x(), self.fish_xy.y()
        ex, ey, erot, esx, esy = self.expr.body(self.fish_h)
        air = max(0.0, ground.y() - y - ey)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(max(10, 55 - air * 0.6))))
        p.drawEllipse(QPointF(ground.x() + ex, ground.y()), max(8, 26 - air * 0.25), max(3, 7 - air * 0.06))

        # 呼吸 + 落地挤压 + 空中拉伸 + 表情动作
        sy = (1.0 + 0.02 * math.sin(self.now * 2.5)) * self.fish_scale
        sx = self.fish_scale
        if self.land_t > 0:
            squash = 0.14 * math.sin(self.land_t * math.pi)
            sy -= squash
            sx += squash * 0.7
        if hopping:
            stretch = 0.06 * math.sin(min(1.0, self.state_t / HOP_TIME) * math.pi)
            sy += stretch
            sx -= stretch * 0.5
        sway = math.sin(self.now * 9.0) * 4 if hopping else math.sin(self.now * 2.5) * 1.5
        fx, fy = x + ex, y + ey

        def draw_one(key, opacity):
            name, facing = key
            pix = self.sprites[name]
            w, h = pix_size(pix)
            p.save()
            p.setOpacity(opacity)
            p.translate(fx, fy)
            p.rotate(sway + erot)
            p.scale(sx * esx * facing, sy * esy)
            p.drawPixmap(QRectF(-w / 2, -h, w, h), pix, QRectF(pix.rect()))
            p.restore()

        view = self.expr.view()
        if view:
            draw_one(view, 1.0)
        else:
            if self.fade_t > 0 and self.prev_key:
                draw_one(self.prev_key, self.fade_t)
            draw_one(self.sprite_key(), 1.0 - self.fade_t * 0.5)
        self.expr.draw_overlay(p, fx, fy - self.fish_h * sy * esy, self.fish_h)

    def paint_bubble(self, p):
        if self.bubble_left <= 0 or not self.bubble_text:
            return
        f = ui_font(17)
        fm = QFontMetrics(f)
        bw = fm.horizontalAdvance(self.bubble_text) + 28
        bh = fm.height() + 16
        head_gap = self.fish_h * (0.36 if self.expr.active else 0.06)
        ground = self.ground_point()
        tip = self.to_screen(ground) + QPointF(self.fish_xy.x() - ground.x(),
                                                self.fish_xy.y() - ground.y() - self.fish_h - head_gap) * self.zoom
        bx = max(6.0, min(self.width() - bw - 6, tip.x() - bw / 2))
        by = max(MARGIN + HUD_H + 6, tip.y() - bh - 8)
        # 气泡不压住掷骰按钮和岔路选项
        tray = self.tray_rect()
        if QRectF(bx, by, bw, bh).intersects(tray):
            by = tray.top() - bh - 10
        alpha = int(240 * min(1.0, self.bubble_left / 0.3))

        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, bw, bh), 12, 12)
        tx = max(bx + 14, min(bx + bw - 14, tip.x()))
        if by + bh < tip.y() + 4:
            path.addPolygon(QPolygonF([QPointF(tx - 8, by + bh - 1), QPointF(tx + 8, by + bh - 1),
                                       QPointF(tx, by + bh + 9)]))
        p.setPen(QPen(QColor(120, 160, 210, alpha), 1.5))
        p.setBrush(QColor(255, 255, 255, alpha))
        p.drawPath(path.simplified())
        p.setFont(f)
        p.setPen(QColor(40, 60, 90, alpha))
        p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, self.bubble_text)


if __name__ == "__main__":
    import main
    main.main()
