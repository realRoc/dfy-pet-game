"""dsh-pet 的动作动画（舞狮、玩玩具汽车、涮火锅……），桌宠和棋盘共用。

素材在 content/clips/（怎么来的见 tools/import_clips.py）：透明 webm，VP9 + alpha。
webm 的 alpha 存在单独的 BlockAdditional 里，要用 libvpx-vp9 解码器才拿得到，所以用 PyAV（自带 libvpx）
边播边解：只解到当前该显示的那一帧，不把整段预先解进内存。
没装 PyAV 或素材缺失时 AVAILABLE 为 False，菜单里就不出现这些动作，其他功能照常。
"""
import json
import os
import random

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QImage

from common import BUNDLE_DIR

CLIP_DIR = os.path.join(BUNDLE_DIR, "content", "clips")
FADE = 0.25   # 和三视图之间淡入淡出的秒数

try:
    import av
    with open(os.path.join(CLIP_DIR, "clips.json"), encoding="utf-8") as _f:
        _MANIFEST = json.load(_f)
    CLIPS = _MANIFEST["clips"]
    CATEGORIES = [(c["name"], c["clips"]) for c in _MANIFEST["categories"]]
    _REF = _MANIFEST["ref"]
    AVAILABLE = True
except Exception as e:
    print("动作动画不可用:", e)
    CLIPS, CATEGORIES, _REF = {}, [], None
    AVAILABLE = False


def label(name):
    return CLIPS[name]["label"]


def add_menus(menu, play):
    """在「做个表情」菜单里按分类挂上动作动画。"""
    if not AVAILABLE:
        return
    menu.addSeparator()
    for cat, names in CATEGORIES:
        sub = menu.addMenu(cat)
        for name in names:
            sub.addAction(label(name), lambda n=name: play(n))


class ClipPlayer:
    def __init__(self):
        self.name = None
        self.t = 0.0
        self.dur = 0.0
        self.image = None
        self._container = None
        self._frames = None
        self._decoded = -1

    @property
    def active(self):
        return self.name is not None

    def start(self, name=None):
        """开始播一段（不传则随机），返回名字；打不开返回 None。"""
        if not AVAILABLE:
            return None
        self.stop()
        name = name or random.choice(list(CLIPS))
        info = CLIPS[name]
        try:
            self._container = av.open(os.path.join(CLIP_DIR, info["file"]))
            stream = self._container.streams.video[0]
            decoder = av.CodecContext.create("libvpx-vp9", "r")
            self._frames = (f for pkt in self._container.demux(stream) for f in decoder.decode(pkt))
        except Exception as e:
            print(f"动作动画 {name} 打开失败:", e)
            self.stop()
            return None
        self.name, self.t, self.dur = name, 0.0, info["frames"] / info["fps"]
        self._crop = QRect(*info["crop"])
        self._decoded = -1
        self.image = None
        self._advance()
        return name

    def stop(self):
        if self._container is not None:
            self._container.close()
        self.name, self.image, self._container, self._frames = None, None, None, None

    def update(self, dt):
        if self.name:
            self.t += dt
            if self.t >= self.dur:
                self.stop()
            else:
                self._advance()

    def _advance(self):
        """解到当前时间对应的帧；落后多帧时中间的只解码不转图。"""
        target = int(self.t * CLIPS[self.name]["fps"])
        frame = None
        while self._decoded < target:
            frame = next(self._frames, None)
            if frame is None:
                self.dur = self.t   # 实际帧数比记录的少：播完当前帧就结束
                return
            self._decoded += 1
        if frame is not None:
            rgba = frame.reformat(format="rgba")
            plane = rgba.planes[0]
            img = QImage(bytes(plane), rgba.width, rgba.height, plane.line_size, QImage.Format.Format_RGBA8888)
            self.image = img.copy(self._crop)

    def blend(self):
        """动画的不透明度：开头和结尾和三视图交叉淡化。"""
        if not self.name:
            return 0.0
        return max(0.0, min(1.0, self.t / FADE, (self.dur - self.t) / FADE))

    def _scale(self, h):
        return h / _REF["h"]

    def extents(self, h):
        """以脚底为原点，画面往左、右、上、下各伸出多少（逻辑像素），给窗口留位置用。"""
        if not self.name:
            return 0.0, 0.0, 0.0, 0.0
        s = self._scale(h)
        c = self._crop
        return ((_REF["cx"] - c.x()) * s, (c.x() + c.width() - _REF["cx"]) * s,
                (_REF["foot"] - c.y()) * s, max(0.0, (c.y() + c.height() - _REF["foot"]) * s))

    def draw(self, p, foot_x, foot_y, h):
        """按人物身高 h 缩放，脚底对齐 (foot_x, foot_y)。"""
        if not self.name or self.image is None:
            return
        s = self._scale(h)
        c = self._crop
        p.save()
        p.setOpacity(p.opacity() * self.blend())
        p.drawImage(QRectF(foot_x + (c.x() - _REF["cx"]) * s, foot_y + (c.y() - _REF["foot"]) * s,
                           c.width() * s, c.height() * s), self.image)
        p.restore()
