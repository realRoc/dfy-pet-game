"""飞行棋盘窗口

透明置顶的小棋盘：点骰子（或按空格）掷出 1~6，大肥鱼逐格蹦过去，
落地后按格子类型触发事件。问号格会让大肥鱼随机做一个表情。
点右上角「收起」或按 Esc，棋盘收起，大肥鱼回到桌面继续当桌宠。

地图、格子类型、骰子皮肤来自 content/（见 game/content/loader.py），
规则在 game/core/rules.py，这里只负责动画、绘制和输入。

精灵图与三视图朝向/呼吸/蹦跳的画法来自 dafeiyu-pet（MIT）：
https://github.com/1190fasheqi/dafeiyu-pet
"""
import math
import random

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPoint, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QFontMetrics, QPolygonF, QPen, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget, QMenu

from common import ui_font, float_flags, load_sprites, pix_size
from expressions import EXPRESSIONS, ExpressionPlayer
from game.content import ContentError, load_dice_skin, load_map, load_tiles
from game.core.rules import Rules
from game.core.state import BoardState
from game.render.dice_renderer import DiceRenderer
from game.render.tile_renderer import TileRenderer

# ===== 窗口边距 =====
PAD = 28
PAD_TOP = 104              # 顶行上方给鱼、气泡和收起按钮留空间

# ===== 动画参数（秒）=====
TICK_MS = 16
FISH_H = 104
HOP_TIME = 0.30
HOP_HEIGHT = 44
LAND_TIME = 0.18
FADE_TIME = 0.12

START_LINE = "路过起点，发工资啦！+3 小鱼干"
ROLL_LINES = ["看我的！", "骰子骰子快显灵！", "这把必是六！", "大肥鱼，出击！"]
SIX_LINE = "六！我就说吧～"
ONE_LINE = "就……一步？"


def load_content(cfg):
    """按配置加载地图和骰子皮肤；配置里的名字不存在时退回 classic。"""
    tiles = load_tiles()
    try:
        graph = load_map(cfg.get("board_map") or "classic", tiles=tiles)
    except ContentError as e:
        print("地图加载失败，改用 classic:", e)
        graph = load_map("classic", tiles=tiles)
    try:
        skin = load_dice_skin(cfg.get("dice_skin") or "classic")
    except ContentError as e:
        print("骰子皮肤加载失败，改用 classic:", e)
        skin = load_dice_skin("classic")
    return tiles, graph, skin


class BoardWindow(QWidget):
    def __init__(self, app, cfg):
        super().__init__(None, float_flags(cfg.get("topmost", True)))
        self.app = app
        self.cfg = cfg
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.tiles, self.graph, self.skin = load_content(cfg)
        self.rules = Rules(self.graph, self.tiles)
        self.tile_painter = TileRenderer(self.tiles)
        self.dice_painter = DiceRenderer(self.skin)
        cw, ch = self.graph.canvas
        self.win_w, self.win_h = PAD * 2 + cw, PAD_TOP + ch + PAD
        self.setFixedSize(int(self.win_w), int(self.win_h))
        self.setWindowTitle("大肥鱼飞行棋")
        self.sprites = load_sprites(FISH_H)

        # 存档状态（位置、小鱼干、回合）
        self.board = BoardState.from_cfg(cfg, self.graph)

        # 鱼的状态
        self.fish_xy = self.tile_anchor(self.board.node_id)
        self.dir, self.facing = "down", 1
        self.prev_key, self.fade_t = None, 0.0
        self.land_t = 0.0
        self.expr = ExpressionPlayer()

        # 动画阶段: idle / rolling / settle / moving
        self.state = "idle"
        self.state_t = 0.0
        self.dice_face = random.randint(1, 6)
        self.roll_result = 0
        self.steps_left = 0
        self.hop_from = self.hop_to = self.board.node_id
        self.glow_node, self.glow_t = None, 0.0

        self.bubble_text, self.bubble_left = "", 0.0
        self.drag_off = None
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_ms = 0
        self.now = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)

    # ---------- 几何 ----------
    def tile_rect(self, node_id):
        ax, ay = self.graph.anchor(node_id)
        t = self.graph.tile
        return QRectF(PAD + ax - t / 2, PAD_TOP + ay - t / 2, t, t)

    def tile_anchor(self, node_id):
        """鱼脚站的位置：格子中心略偏下。"""
        rc = self.tile_rect(node_id)
        return QPointF(rc.center().x(), rc.center().y() + self.graph.tile * 0.26)

    def board_rect(self):
        cw, ch = self.graph.canvas
        return QRectF(PAD, PAD_TOP, cw, ch)

    def inner_rect(self):
        """外圈地图中间的空地，放标题、骰子和状态。"""
        t = self.graph.tile
        return self.board_rect().adjusted(t, t, -t, -t)

    def dice_rect(self):
        inner = self.inner_rect()
        s = self.skin.size
        return QRectF(inner.center().x() - s / 2, inner.center().y() - s / 2 + 4, s, s)

    def collapse_rect(self):
        """放在中间空地的右上角，鱼走外圈时不会挡住它。"""
        inner = self.inner_rect()
        return QRectF(inner.right() - 84 - 12, inner.top() + 12, 84, 30)

    # ---------- 和桌宠切换用 ----------
    def foot_global(self):
        a = self.tile_anchor(self.board.node_id)
        return self.mapToGlobal(QPoint(int(a.x()), int(a.y())))

    def place_fish_at(self, gp):
        """把窗口摆到让鱼脚正好落在屏幕坐标 gp 上（再收回屏幕内）。"""
        a = self.tile_anchor(self.board.node_id)
        x, y = gp.x() - int(a.x()), gp.y() - int(a.y())
        screen = QApplication.screenAt(gp) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = max(geo.left(), min(geo.right() - int(self.win_w), x))
        y = max(geo.top() - PAD_TOP // 2, min(geo.bottom() - int(self.win_h), y))
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

    def roll(self):
        if self.state != "idle":
            return
        self.expr.stop()
        result = self.rules.begin_turn(self.board)
        if result is None:
            self.say("泡泡还没破……这回合歇着 😼")
            return
        self.state, self.state_t = "rolling", 0.0
        self.roll_result = result
        self.say(random.choice(ROLL_LINES), self.skin.roll_time + self.skin.settle_time)

    def restart(self):
        if self.state != "idle":
            return
        self.board = BoardState(node_id=self.graph.start)
        self.fish_xy = self.tile_anchor(self.board.node_id)
        self.set_dir("down")
        self.say("重新开始！")

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

    def start_hop(self):
        self.hop_from = self.board.node_id
        self.hop_to = self.graph.next_of(self.hop_from)
        self.face_towards(self.hop_from, self.hop_to)
        self.state, self.state_t = "moving", 0.0

    def finish_move(self):
        self.state = "idle"
        self.set_dir("down")
        self.glow_node, self.glow_t = self.board.node_id, 1.0
        landing = self.rules.land(self.board)
        if landing.expression:
            name, line = self.expr.start()
            self.say(f"【{name}】{line}", self.expr.dur + 0.8)
        elif landing.say:
            self.say(landing.say, 3.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            pos = e.position()
            if self.collapse_rect().contains(pos):
                self.collapse()
            elif self.dice_rect().adjusted(-10, -10, 10, 10).contains(pos):
                self.roll()
            else:
                self.drag_off = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self.drag_off is not None:
            self.move(e.globalPosition().toPoint() - self.drag_off)

    def mouseReleaseEvent(self, _):
        self.drag_off = None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            self.roll()
        elif e.key() == Qt.Key.Key_Escape:
            self.collapse()

    def contextMenuEvent(self, e):
        busy = self.state != "idle"
        m = QMenu(self)
        a = m.addAction("掷骰子", self.roll)
        a.setEnabled(not busy)
        expr_menu = m.addMenu("做个表情")
        expr_menu.setEnabled(not busy)
        expr_menu.addAction("随机", self.play_expression)
        expr_menu.addSeparator()
        for key, (name, _, _) in EXPRESSIONS.items():
            expr_menu.addAction(name, lambda k=key: self.play_expression(k))
        a = m.addAction("重新开始", self.restart)
        a.setEnabled(not busy)
        m.addSeparator()
        a = m.addAction("收起棋盘", self.collapse)
        a.setEnabled(not busy)
        m.addAction("退出", self.app.quit)
        m.exec(e.globalPos())

    # ---------- 逻辑 ----------
    def tick(self):
        ms = self.clock.elapsed()
        dt = min(0.05, (ms - self.last_ms) / 1000.0)
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
            # 每 70ms 换一个面，越到后面越慢；只是装饰，结果在 roll() 里已经定了
            roll_time = self.skin.roll_time
            step = 0.07 + 0.08 * (self.state_t / roll_time) ** 2
            if self.state_t % step < dt:
                self.dice_face = random.choice([f for f in range(1, 7) if f != self.dice_face])
            if self.state_t >= roll_time:
                self.dice_face = self.roll_result
                self.state, self.state_t = "settle", 0.0
                if self.roll_result == 6:
                    self.say(SIX_LINE)
                elif self.roll_result == 1:
                    self.say(ONE_LINE)
        elif self.state == "settle":
            if self.state_t >= self.skin.settle_time:
                self.steps_left = self.roll_result
                self.start_hop()
        elif self.state == "moving":
            u = min(1.0, self.state_t / HOP_TIME)
            a, b = self.tile_anchor(self.hop_from), self.tile_anchor(self.hop_to)
            self.fish_xy = QPointF(a.x() + (b.x() - a.x()) * u,
                                   a.y() + (b.y() - a.y()) * u - HOP_HEIGHT * 4 * u * (1 - u))
            if u >= 1.0:
                # 跳完这条边才真正结算：位置和起点工资
                hop = self.rules.hop(self.board)
                self.land_t = 1.0
                self.steps_left -= 1
                if hop.wage:
                    self.say(START_LINE)
                if self.steps_left > 0:
                    self.start_hop()
                else:
                    self.finish_move()
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.paint_panel(p)
        for nid, node in self.graph.nodes.items():
            glow = self.glow_t if nid == self.glow_node else 0.0
            self.tile_painter.paint(p, self.tile_rect(nid), node.type, glow)
        self.paint_center(p)
        self.paint_dice(p)
        self.paint_fish(p)
        self.paint_collapse(p)
        self.paint_bubble(p)

    def paint_panel(self, p):
        rc = self.board_rect().adjusted(-14, -14, 14, 14)
        p.setPen(QPen(QColor(120, 160, 210, 200), 2))
        p.setBrush(QColor(255, 251, 242, 238))
        p.drawRoundedRect(rc, 22, 22)

    def paint_collapse(self, p):
        rc = self.collapse_rect()
        p.setPen(QPen(QColor(120, 160, 210, 220), 1.5))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(rc, 15, 15)
        p.setFont(ui_font(13, bold=True))
        p.setPen(QColor(70, 110, 170) if self.state == "idle" else QColor(170, 175, 190))
        p.drawText(rc, Qt.AlignmentFlag.AlignCenter, "收起 ▾")

    def paint_center(self, p):
        inner = self.inner_rect().adjusted(14, 14, -14, -14)
        p.setFont(ui_font(24, bold=True))
        p.setPen(QColor(60, 100, 160))
        p.drawText(QRectF(inner.x(), inner.y() + 6, inner.width(), 34), Qt.AlignmentFlag.AlignCenter,
                   "大肥鱼飞行棋")

        p.setFont(ui_font(13))
        p.setPen(QColor(120, 130, 150))
        hint = "点骰子 / 空格 掷骰 · 右键菜单 · Esc 收起"
        p.drawText(QRectF(inner.x(), self.dice_rect().bottom() + 18, inner.width(), 20),
                   Qt.AlignmentFlag.AlignCenter, hint)

        p.setFont(ui_font(15, bold=True))
        p.setPen(QColor(80, 90, 110))
        status = f"🐟 小鱼干 × {self.board.coins}    第 {self.board.turn} 回合"
        if self.board.skip_next:
            status += "    🫧 下回合暂停"
        p.drawText(QRectF(inner.x(), inner.bottom() - 30, inner.width(), 24),
                   Qt.AlignmentFlag.AlignCenter, status)

    def paint_dice(self, p):
        phase = self.state if self.state in ("rolling", "settle") else "idle"
        hot = self.state == "idle" and not self.board.skip_next
        self.dice_painter.paint(p, self.dice_rect(), self.dice_face, phase, self.state_t, hot)

    def paint_fish(self, p):
        x, y = self.fish_xy.x(), self.fish_xy.y()
        hopping = self.state == "moving"
        ground = self.tile_anchor(self.hop_to if hopping else self.board.node_id)
        if hopping:
            u = min(1.0, self.state_t / HOP_TIME)
            a = self.tile_anchor(self.hop_from)
            ground = QPointF(a.x() + (ground.x() - a.x()) * u, a.y() + (ground.y() - a.y()) * u)
        ex, ey, erot, esx, esy = self.expr.body(FISH_H)
        air = max(0.0, ground.y() - y - ey)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(max(10, 55 - air * 0.6))))
        p.drawEllipse(QPointF(ground.x() + ex, ground.y()), max(8, 26 - air * 0.25), max(3, 7 - air * 0.06))

        # 呼吸 + 落地挤压 + 空中拉伸 + 表情动作
        sy = 1.0 + 0.02 * math.sin(self.now * 2.5)
        sx = 1.0
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
        self.expr.draw_overlay(p, fx, fy - FISH_H * sy * esy, FISH_H)

    def paint_bubble(self, p):
        if self.bubble_left <= 0 or not self.bubble_text:
            return
        f = ui_font(14)
        fm = QFontMetrics(f)
        bw = fm.horizontalAdvance(self.bubble_text) + 24
        bh = fm.height() + 14
        head_gap = FISH_H * (0.36 if self.expr.active else 0.06)
        tip = QPointF(self.fish_xy.x(), self.fish_xy.y() - FISH_H - head_gap)
        bx = max(6.0, min(self.win_w - bw - 6, tip.x() - bw / 2))
        by = max(6.0, tip.y() - bh - 8)
        alpha = int(240 * min(1.0, self.bubble_left / 0.3))

        path = QPainterPath()
        path.addRoundedRect(QRectF(bx, by, bw, bh), 10, 10)
        tx = max(bx + 12, min(bx + bw - 12, tip.x()))
        path.addPolygon(QPolygonF([QPointF(tx - 7, by + bh - 1), QPointF(tx + 7, by + bh - 1),
                                   QPointF(tx, by + bh + 8)]))
        p.setPen(QPen(QColor(120, 160, 210, alpha), 1.5))
        p.setBrush(QColor(255, 255, 255, alpha))
        p.drawPath(path.simplified())
        p.setFont(f)
        p.setPen(QColor(60, 60, 80, alpha))
        p.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, self.bubble_text)


if __name__ == "__main__":
    import main
    main.main()
