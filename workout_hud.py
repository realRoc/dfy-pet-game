"""跟练时挂在大肥鱼脚下的计时面板：当前动作、倒计时、下一个动作、整体进度，外加 上一段 / 暂停 / 下一段 / 结束。"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QToolButton

from common import float_flags, ui_font
from workout import MOVES, fmt_secs

W, H = 300, 132
KIND = {"prep": ("准备", QColor(86, 134, 254)), "work": ("训练", QColor(255, 128, 64)),
        "rest": ("休息", QColor(46, 184, 120))}


class WorkoutHUD(QWidget):
    def __init__(self, on_back, on_pause, on_skip, on_stop):
        super().__init__(None, float_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.player = None
        self.buttons = {}
        for i, (key, text, tip, fn) in enumerate((("back", "⏮", "重来这段（连按回上一段）", on_back),
                                                  ("pause", "⏸", "暂停 / 继续", on_pause),
                                                  ("skip", "⏭", "跳过这段", on_skip),
                                                  ("stop", "✕", "结束跟练", on_stop))):
            b = QToolButton(self)
            b.setText(text)
            b.setToolTip(tip)
            b.setFont(ui_font(15))
            b.setFixedSize(30, 26)
            b.move(W - 4 * 32 - 8 + i * 32, H - 34)
            b.setStyleSheet("QToolButton{background:rgba(255,255,255,30);border:none;border-radius:8px;color:white;}"
                            "QToolButton:hover{background:rgba(255,255,255,70);}")
            b.clicked.connect(fn)
            self.buttons[key] = b

    def show_for(self, player):
        self.player = player
        self.refresh()
        self.show()
        self.raise_()

    def refresh(self):
        if self.player:
            self.buttons["pause"].setText("▶" if self.player.paused else "⏸")
        self.update()

    def follow(self, foot, head_top, screen_geo):
        """贴在脚底下，屏幕下面放不下就放到头顶上。"""
        x = int(foot.x() - W / 2)
        y = foot.y() + 6
        if y + H > screen_geo.bottom():
            y = head_top - H - 6
        x = max(screen_geo.left(), min(screen_geo.right() - W, x))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    def paintEvent(self, _):
        pl = self.player
        if pl is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(28, 32, 50, 228))
        p.drawRoundedRect(QRectF(0, 0, W, H), 16, 16)

        seg = pl.seg
        if pl.finished:
            tag, color = "完成", QColor(255, 196, 64)
        else:
            tag, color = KIND[seg.kind]
        # 标签 + 动作名
        p.setFont(ui_font(11, True))
        tw = p.fontMetrics().horizontalAdvance(tag) + 14
        p.setBrush(color)
        p.drawRoundedRect(QRectF(12, 11, tw, 20), 10, 10)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(12, 11, tw, 20), Qt.AlignmentFlag.AlignCenter, tag)
        title = "练完啦！" if pl.finished else seg.label
        if pl.slacking and not pl.finished:
            title += " · 大肥鱼在摸鱼"
        p.setFont(ui_font(15, True))
        p.drawText(QRectF(18 + tw, 8, W - tw - 30, 26), Qt.AlignmentFlag.AlignVCenter, title)

        # 右上：第几个 / 第几轮
        p.setFont(ui_font(11))
        p.setPen(QColor(180, 186, 210))
        if seg.kind != "prep" and not pl.finished:
            i, n = pl.work_count()
            info = f"{i}/{n}" + (f" · 第{seg.round_no}/{pl.rounds}轮" if pl.rounds > 1 else "")
            p.drawText(QRectF(0, 36, W - 14, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, info)

        # 大倒计时
        p.setPen(QColor(255, 255, 255) if not pl.paused else QColor(160, 164, 180))
        p.setFont(ui_font(34, True))
        big = fmt_secs(pl.elapsed) if pl.finished else fmt_secs(pl.remaining)
        p.drawText(QRectF(14, 34, 120, 44), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, big)
        if pl.paused:
            p.setFont(ui_font(12, True))
            p.drawText(QRectF(112, 52, 60, 20), Qt.AlignmentFlag.AlignVCenter, "已暂停")

        # 下一个
        p.setFont(ui_font(12))
        p.setPen(QColor(210, 214, 232))
        nxt = pl.next_work()
        if pl.finished:
            line = f"一共 {fmt_secs(pl.total)}，辛苦啦"
        elif nxt is None:
            line = "这是最后一个！"
        else:
            line = f"下一个：{nxt.label} {int(nxt.secs)}s"
        if seg.kind == "work" and not pl.finished and MOVES[seg.move].tip and pl.remaining > seg.secs - 6:
            line = MOVES[seg.move].tip   # 每段开头几秒先显示动作要领
        p.drawText(QRectF(14, 76, W - 28, 18), Qt.AlignmentFlag.AlignVCenter, p.fontMetrics().elidedText(
            line, Qt.TextElideMode.ElideRight, W - 28))

        # 本段进度条
        frac = 1.0 if pl.finished else min(1.0, pl.t / seg.secs if seg.secs else 1.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(QRectF(14, 98, W - 28, 5), 2.5, 2.5)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(14, 98, (W - 28) * frac, 5), 2.5, 2.5)

        # 全程进度
        p.setFont(ui_font(10))
        p.setPen(QColor(160, 166, 190))
        total_frac = pl.elapsed / pl.total if pl.total else 1.0
        p.drawText(QRectF(14, H - 30, W - 4 * 32 - 26, 18), Qt.AlignmentFlag.AlignVCenter,
                   f"全程 {int(total_frac * 100)}% · 剩 {fmt_secs(pl.total - pl.elapsed)}")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(14, H - 12, W - 4 * 32 - 26, 3), 1.5, 1.5)
        p.setBrush(QColor(255, 196, 64))
        p.drawRoundedRect(QRectF(14, H - 12, (W - 4 * 32 - 26) * total_frac, 3), 1.5, 1.5)
