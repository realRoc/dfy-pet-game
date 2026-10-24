"""大肥鱼飞行棋 · 原型

透明置顶的小棋盘：点骰子（或按空格）掷出 1~6，大肥鱼逐格蹦过去，
落地后按格子类型说句话、加减小鱼干。

精灵图与三视图朝向/呼吸/蹦跳的画法来自 dafeiyu-pet（MIT）：
https://github.com/1190fasheqi/dafeiyu-pet
"""
import math
import os
import random
import sys

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QRectF
from PySide6.QtGui import (QPainter, QPixmap, QFont, QColor, QIcon, QFontMetrics,
                           QPolygonF, QPen, QPainterPath, QAction)
from PySide6.QtWidgets import QApplication, QWidget, QMenu

if getattr(sys, "frozen", False):
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BUNDLE_DIR, "sprites")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
UI_FONT = "PingFang SC" if IS_MAC else "Microsoft YaHei"
EMOJI_FONT = "Apple Color Emoji" if IS_MAC else "Segoe UI Emoji"

# ===== 棋盘尺寸 =====
COLS, ROWS = 8, 6          # 外圈 8x6，共 24 格
TILE = 78
PAD = 28
PAD_TOP = 104              # 顶行上方给鱼和气泡留空间
WIN_W = PAD * 2 + COLS * TILE
WIN_H = PAD_TOP + ROWS * TILE + PAD

# ===== 动画参数（秒）=====
TICK_MS = 16
FISH_H = 104
ROLL_TIME = 0.8
SETTLE_TIME = 0.35
HOP_TIME = 0.30
HOP_HEIGHT = 44
LAND_TIME = 0.18
FADE_TIME = 0.12

# 类型: (图标, 名字, 底色)
TILE_TYPES = {
    "start":  ("🏁", "起点",   QColor(255, 214, 102)),
    "fish":   ("🎣", "钓鱼",   QColor(140, 200, 255)),
    "ring":   ("🎯", "套圈",   QColor(255, 170, 160)),
    "candy":  ("🍬", "接糖果", QColor(255, 190, 225)),
    "riddle": ("🧩", "猜谜",   QColor(180, 225, 160)),
    "chest":  ("🎁", "宝箱",   QColor(255, 200, 120)),
    "rest":   ("🛋️", "休息",   QColor(200, 190, 245)),
    "prank":  ("😼", "恶作剧", QColor(190, 190, 205)),
}
LAYOUT = [
    "start", "fish", "candy", "riddle", "rest", "ring", "chest", "fish",
    "prank", "candy", "riddle", "rest", "ring",
    "chest", "fish", "candy", "prank", "riddle", "rest", "ring",
    "chest", "candy", "prank", "fish",
]

# 格子事件: (小鱼干变化, 台词)
TILE_EVENTS = {
    "fish":   [(2, "钓到星星小鱼！+2 小鱼干"), (1, "钓到一只迷你鱼……也算吧 +1")],
    "ring":   [(1, "套中了！小勋章到手 +1"), (0, "差一点点……下次一定")],
    "candy":  [(1, "接住糖果！甜到冒泡泡～ +1"), (2, "糖果雨！嘎嘣脆 +2")],
    "riddle": [(1, "答对了！我果然是大聪明 +1"), (0, "这题超纲了，我先去吃饭")],
    "chest":  [(3, "宝箱里是钻石？！+3"), (1, "开出一个小发卡 +1"), (2, "金币闪闪 +2")],
    "rest":   [(0, "躺一会儿，心情回满～"), (0, "大肥鱼坐的住")],
    "prank":  [(0, "被泡泡裹住了！下回合歇着……")],
}
START_LINE = "路过起点，发工资啦！+3 小鱼干"
ROLL_LINES = ["看我的！", "骰子骰子快显灵！", "这把必是六！", "大肥鱼，出击！"]
SIX_LINE = "六！我就说吧～"
ONE_LINE = "就……一步？"


def ring_cells(cols, rows):
    """外圈格子坐标：从左下角出发，沿底边向右、右边向上、顶边向左、左边向下。"""
    cells = [(c, rows - 1) for c in range(cols)]
    cells += [(cols - 1, r) for r in range(rows - 2, -1, -1)]
    cells += [(c, 0) for c in range(cols - 2, -1, -1)]
    cells += [(0, r) for r in range(1, rows - 1)]
    return cells


def ease_out_back(u):
    c = 1.4
    return 1 + (c + 1) * (u - 1) ** 3 + c * (u - 1) ** 2


class BoardWindow(QWidget):
    def __init__(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if IS_WIN:
            # macOS 上 Tool 窗口会在应用失焦时自动隐藏，只在 Windows 用它来隐藏任务栏图标
            flags |= Qt.WindowType.Tool
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIN_W, WIN_H)
        self.setWindowTitle("大肥鱼飞行棋")

        self.cells = ring_cells(COLS, ROWS)
        assert len(self.cells) == len(LAYOUT)
        self.ui_font = QFont(UI_FONT)
        self.emoji_font = QFont(EMOJI_FONT)
        self.load_sprites()

        # 鱼的状态
        self.pos_idx = 0
        self.fish_xy = self.tile_anchor(0)
        self.dir, self.facing = "down", 1
        self.prev_key, self.fade_t = None, 0.0
        self.land_t = 0.0

        # 回合状态: idle / rolling / settle / moving
        self.state = "idle"
        self.state_t = 0.0
        self.dice_face = random.randint(1, 6)
        self.roll_result = 0
        self.steps_left = 0
        self.hop_from = self.hop_to = 0
        self.skip_next = False
        self.coins = 0
        self.turn = 0
        self.glow_idx, self.glow_t = None, 0.0

        self.bubble_text, self.bubble_left = "", 0.0
        self.say("主人，点骰子带我去玩！", 3.5)

        self.drag_off = None
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_ms = 0
        self.now = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(TICK_MS)

    # ---------- 资源 ----------
    def load_sprites(self):
        dpr = (QApplication.primaryScreen().devicePixelRatio()
               if QApplication.primaryScreen() else 1.0)
        self.sprites = {}
        for name in ("正面", "侧面", "背面"):
            pix = QPixmap(os.path.join(SPRITE_DIR, f"{name}.png"))
            pix = pix.scaledToHeight(int(FISH_H * dpr), Qt.TransformationMode.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
            self.sprites[name] = pix

    # ---------- 几何 ----------
    def tile_rect(self, idx):
        c, r = self.cells[idx]
        return QRectF(PAD + c * TILE, PAD_TOP + r * TILE, TILE, TILE)

    def tile_anchor(self, idx):
        """鱼脚站的位置：格子中心略偏下。"""
        rc = self.tile_rect(idx)
        return QPointF(rc.center().x(), rc.center().y() + TILE * 0.26)

    def inner_rect(self):
        return QRectF(PAD + TILE, PAD_TOP + TILE, (COLS - 2) * TILE, (ROWS - 2) * TILE)

    def dice_rect(self):
        inner = self.inner_rect()
        s = 84
        return QRectF(inner.center().x() - s / 2, inner.center().y() - s / 2 + 4, s, s)

    # ---------- 交互 ----------
    def say(self, text, secs=2.6):
        self.bubble_text, self.bubble_left = text, secs

    def roll(self):
        if self.state != "idle":
            return
        self.turn += 1
        if self.skip_next:
            self.skip_next = False
            self.say("泡泡还没破……这回合歇着 😼")
            return
        self.state, self.state_t = "rolling", 0.0
        self.roll_result = random.randint(1, 6)
        self.say(random.choice(ROLL_LINES), ROLL_TIME + SETTLE_TIME)

    def restart(self):
        if self.state != "idle":
            return
        self.pos_idx, self.coins, self.turn, self.skip_next = 0, 0, 0, False
        self.fish_xy = self.tile_anchor(0)
        self.set_dir("down")
        self.say("重新开始！")

    def set_dir(self, d, facing=1):
        if (d, facing) != (self.dir, self.facing):
            self.prev_key = self.sprite_key()
            self.fade_t = 1.0
            self.dir, self.facing = d, facing

    def sprite_key(self):
        name = {"left": "侧面", "right": "侧面", "up": "背面", "down": "正面"}[self.dir]
        return name, (self.facing if self.dir in ("left", "right") else 1)

    def face_towards(self, a, b):
        ca, cb = self.cells[a], self.cells[b]
        dx, dy = cb[0] - ca[0], cb[1] - ca[1]
        if dx:
            # 侧面原图朝左，向右走时镜像
            self.set_dir("left" if dx < 0 else "right", 1 if dx < 0 else -1)
        else:
            self.set_dir("up" if dy < 0 else "down")

    def start_hop(self):
        self.hop_from = self.pos_idx
        self.hop_to = (self.pos_idx + 1) % len(self.cells)
        self.face_towards(self.hop_from, self.hop_to)
        self.state, self.state_t = "moving", 0.0

    def finish_move(self):
        self.state = "idle"
        self.set_dir("down")
        kind = LAYOUT[self.pos_idx]
        self.glow_idx, self.glow_t = self.pos_idx, 1.0
        if kind == "start":
            return
        delta, line = random.choice(TILE_EVENTS[kind])
        self.coins += delta
        if kind == "prank":
            self.skip_next = True
        self.say(line, 3.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.dice_rect().adjusted(-10, -10, 10, 10).contains(e.position()):
                self.roll()
            else:
                self.drag_off = e.globalPosition().toPoint() - self.pos()
        elif e.button() == Qt.MouseButton.RightButton:
            self.show_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self.drag_off is not None:
            self.move(e.globalPosition().toPoint() - self.drag_off)

    def mouseReleaseEvent(self, _):
        self.drag_off = None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            self.roll()
        elif e.key() == Qt.Key.Key_Escape:
            QApplication.quit()

    def show_menu(self, gpos):
        m = QMenu(self)
        for text, fn in (("掷骰子", self.roll), ("重新开始", self.restart), ("退出", QApplication.quit)):
            act = QAction(text, m)
            act.triggered.connect(fn)
            m.addAction(act)
        m.exec(gpos)

    # ---------- 逻辑 ----------
    def tick(self):
        ms = self.clock.elapsed()
        dt = min(0.05, (ms - self.last_ms) / 1000.0)
        self.last_ms = ms
        self.now += dt
        self.state_t += dt
        self.fade_t = max(0.0, self.fade_t - dt / FADE_TIME)
        self.land_t = max(0.0, self.land_t - dt / LAND_TIME)
        self.glow_t = max(0.0, self.glow_t - dt / 1.2)
        self.bubble_left -= dt

        if self.state == "rolling":
            # 每 70ms 换一个面，越到后面越慢
            step = 0.07 + 0.08 * (self.state_t / ROLL_TIME) ** 2
            if self.state_t % step < dt:
                self.dice_face = random.choice([f for f in range(1, 7) if f != self.dice_face])
            if self.state_t >= ROLL_TIME:
                self.dice_face = self.roll_result
                self.state, self.state_t = "settle", 0.0
                if self.roll_result == 6:
                    self.say(SIX_LINE)
                elif self.roll_result == 1:
                    self.say(ONE_LINE)
        elif self.state == "settle":
            if self.state_t >= SETTLE_TIME:
                self.steps_left = self.roll_result
                self.start_hop()
        elif self.state == "moving":
            u = min(1.0, self.state_t / HOP_TIME)
            a, b = self.tile_anchor(self.hop_from), self.tile_anchor(self.hop_to)
            self.fish_xy = QPointF(a.x() + (b.x() - a.x()) * u,
                                   a.y() + (b.y() - a.y()) * u - HOP_HEIGHT * 4 * u * (1 - u))
            if u >= 1.0:
                self.pos_idx = self.hop_to
                self.land_t = 1.0
                self.steps_left -= 1
                if self.pos_idx == 0:
                    self.coins += 3
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
        for i in range(len(self.cells)):
            self.paint_tile(p, i)
        self.paint_center(p)
        self.paint_dice(p)
        self.paint_fish(p)
        self.paint_bubble(p)

    def paint_panel(self, p):
        rc = QRectF(PAD - 14, PAD_TOP - 14, COLS * TILE + 28, ROWS * TILE + 28)
        p.setPen(QPen(QColor(120, 160, 210, 200), 2))
        p.setBrush(QColor(255, 251, 242, 238))
        p.drawRoundedRect(rc, 22, 22)

    def paint_tile(self, p, i):
        icon, name, color = TILE_TYPES[LAYOUT[i]]
        rc = self.tile_rect(i).adjusted(4, 4, -4, -4)
        if i == self.glow_idx and self.glow_t > 0:
            g = self.glow_t
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 230, 90, int(180 * g)))
            p.drawRoundedRect(rc.adjusted(-4 - 4 * g, -4 - 4 * g, 4 + 4 * g, 4 + 4 * g), 16, 16)
        p.setPen(QPen(color.darker(125), 2))
        p.setBrush(color.lighter(115))
        p.drawRoundedRect(rc, 12, 12)

        f = QFont(self.emoji_font)
        f.setPixelSize(26)
        p.setFont(f)
        p.drawText(QRectF(rc.x(), rc.y() + 4, rc.width(), 34), Qt.AlignmentFlag.AlignCenter, icon)
        f = QFont(self.ui_font)
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(color.darker(220))
        p.drawText(QRectF(rc.x(), rc.bottom() - 24, rc.width(), 20), Qt.AlignmentFlag.AlignCenter, name)

    def paint_center(self, p):
        inner = self.inner_rect().adjusted(14, 14, -14, -14)
        f = QFont(self.ui_font)
        f.setPixelSize(24)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(60, 100, 160))
        p.drawText(QRectF(inner.x(), inner.y() + 6, inner.width(), 34), Qt.AlignmentFlag.AlignCenter,
                   "大肥鱼飞行棋")

        f.setPixelSize(13)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(120, 130, 150))
        hint = "点骰子 / 空格 掷骰 · 右键菜单 · 拖动空白处移动"
        p.drawText(QRectF(inner.x(), self.dice_rect().bottom() + 18, inner.width(), 20),
                   Qt.AlignmentFlag.AlignCenter, hint)

        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(80, 90, 110))
        status = f"🐟 小鱼干 × {self.coins}    第 {self.turn} 回合"
        if self.skip_next:
            status += "    🫧 下回合暂停"
        p.drawText(QRectF(inner.x(), inner.bottom() - 30, inner.width(), 24),
                   Qt.AlignmentFlag.AlignCenter, status)

    def paint_dice(self, p):
        rc = self.dice_rect()
        rot, lift, scale = 0.0, 0.0, 1.0
        if self.state == "rolling":
            k = 1 - self.state_t / ROLL_TIME
            rot = math.sin(self.state_t * 38) * 22 * k
            lift = -abs(math.sin(self.state_t * 14)) * 18 * k
        elif self.state == "settle":
            u = min(1.0, self.state_t / SETTLE_TIME)
            scale = 0.85 + 0.15 * ease_out_back(u)

        c = rc.center()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(c.x(), rc.bottom() + 6), rc.width() * 0.42 * (1 + lift / 60), 7)

        p.save()
        p.translate(c.x(), c.y() + lift)
        p.rotate(rot)
        p.scale(scale, scale)
        body = QRectF(-rc.width() / 2, -rc.height() / 2, rc.width(), rc.height())
        hot = self.state == "idle" and not self.skip_next
        p.setPen(QPen(QColor(90, 140, 210) if hot else QColor(170, 175, 190), 3))
        p.setBrush(QColor(255, 255, 255))
        p.drawRoundedRect(body, 16, 16)

        pips = {1: [(0, 0)], 2: [(-1, -1), (1, 1)], 3: [(-1, -1), (0, 0), (1, 1)],
                4: [(-1, -1), (1, -1), (-1, 1), (1, 1)],
                5: [(-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)],
                6: [(-1, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)]}[self.dice_face]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(225, 70, 80) if self.dice_face == 1 else QColor(50, 70, 110))
        r = 9 if self.dice_face == 1 else 7
        for px, py in pips:
            p.drawEllipse(QPointF(px * 22, py * 22), r, r)
        p.restore()

    def paint_fish(self, p):
        x, y = self.fish_xy.x(), self.fish_xy.y()
        hopping = self.state == "moving"
        ground = self.tile_anchor(self.hop_to if hopping else self.pos_idx)
        if hopping:
            u = min(1.0, self.state_t / HOP_TIME)
            a = self.tile_anchor(self.hop_from)
            ground = QPointF(a.x() + (ground.x() - a.x()) * u, a.y() + (ground.y() - a.y()) * u)
        air = max(0.0, ground.y() - y)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(55 - air * 0.6)))
        p.drawEllipse(ground, 26 - air * 0.25, 7 - air * 0.06)

        # 呼吸 + 落地挤压 + 空中拉伸
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

        def draw_one(key, opacity):
            name, facing = key
            pix = self.sprites[name]
            w = pix.width() / pix.devicePixelRatio()
            h = pix.height() / pix.devicePixelRatio()
            p.save()
            p.setOpacity(opacity)
            p.translate(x, y)
            p.rotate(sway)
            p.scale(sx * facing, sy)
            p.drawPixmap(QRectF(-w / 2, -h, w, h), pix, QRectF(pix.rect()))
            p.restore()

        if self.fade_t > 0 and self.prev_key:
            draw_one(self.prev_key, self.fade_t)
        draw_one(self.sprite_key(), 1.0 - self.fade_t * 0.5)

    def paint_bubble(self, p):
        if self.bubble_left <= 0 or not self.bubble_text:
            return
        f = QFont(self.ui_font)
        f.setPixelSize(14)
        fm = QFontMetrics(f)
        bw = fm.horizontalAdvance(self.bubble_text) + 24
        bh = fm.height() + 14
        tip = QPointF(self.fish_xy.x(), self.fish_xy.y() - FISH_H - 6)
        bx = max(6.0, min(WIN_W - bw - 6, tip.x() - bw / 2))
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


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(os.path.join(SPRITE_DIR, "icon.png")))
    w = BoardWindow()
    screen = app.primaryScreen().availableGeometry()
    w.move(screen.center().x() - WIN_W // 2, screen.center().y() - WIN_H // 2)
    w.show()
    w.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
