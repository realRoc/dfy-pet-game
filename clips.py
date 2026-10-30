"""dsh-pet 的动作动画（舞狮、玩玩具汽车、涮火锅……）。

素材在角色包的 actions 动画目录里（大肥鱼是 characters/dafeiyu/clips/，怎么来的见 tools/import_clips.py）：透明 webm，VP9 + alpha。
webm 的 alpha 存在单独的 BlockAdditional 里，要用 libvpx-vp9 解码器才拿得到，所以用 PyAV（自带 libvpx）
边播边解：只解到当前该显示的那一帧，不把整段预先解进内存。
没装 PyAV、包里没有这类动画或素材缺失时 AVAILABLE 为 False，菜单里就不出现这些动作，其他功能照常。
"""
import json
import os
import random

from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QImage

from character import CHAR

CLIP_DIR = CHAR.anim_dir("actions") or ""
FADE = 0.25   # 和三视图之间淡入淡出的秒数

try:
    import av
    if not CLIP_DIR:
        raise FileNotFoundError(f"角色包 {CHAR.id} 没有动作动画")
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


class Library:
    """另一套同样格式的透明动画（目录里一个 clips.json + 若干 webm），比如跟练动画。
    clips.json 里每段可以带 offset：素材已经裁过时，crop 是文件里的范围，offset 是它在原画面里的位置。"""

    def __init__(self, directory, table, ref, fade):
        self.dir, self.clips, self.ref, self.fade = directory, table, ref, fade


def load_library(directory, fade=0.0):
    """读一套动画；没装 PyAV 或素材缺失返回 None。"""
    if not AVAILABLE and "av" not in globals():
        return None
    try:
        with open(os.path.join(directory, "clips.json"), encoding="utf-8") as f:
            m = json.load(f)
        return Library(directory, m["clips"], m["ref"], fade)
    except Exception as e:
        print("动画素材不可用:", directory, e)
        return None


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
            # 显式接住 triggered(bool) 的 checked，免得哪天它被塞进 n、名字变成 False 而随机播
            sub.addAction(label(name), lambda _checked=False, n=name: play(n))


class ClipPlayer:
    def __init__(self, lib=None):
        self.lib = lib          # None：dsh-pet 那套（模块里的 CLIP_DIR / CLIPS）
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

    @property
    def _clips(self):
        return self.lib.clips if self.lib else CLIPS

    @property
    def _ref(self):
        return self.lib.ref if self.lib else _REF

    def start(self, name=None, fades=(True, True)):
        """开始播一段（不传则随机），返回名字；打不开或第一帧就解不出来返回 None。
        fades：(开头, 结尾) 要不要和三视图淡入淡出；首帧 / 尾帧不是正面站姿的那头别淡，不然会叠出个站着的虚影。"""
        if not (AVAILABLE or self.lib):
            return None
        self.stop()
        name = name or random.choice(list(self._clips))
        info = self._clips[name]
        try:
            self._container = av.open(os.path.join(self.lib.dir if self.lib else CLIP_DIR, info["file"]))
            stream = self._container.streams.video[0]
            decoder = av.CodecContext.create("libvpx-vp9", "r")
            self._frames = (f for pkt in self._container.demux(stream) for f in decoder.decode(pkt))
        except Exception as e:
            print(f"动作动画 {name} 打开失败:", e)
            self.stop()
            return None
        self.name, self.t, self.dur = name, 0.0, info["frames"] / info["fps"]
        self._fades = fades
        self._crop = QRect(*info["crop"])
        self._pos = info.get("offset", info["crop"][:2])   # 画面在原画面里的位置
        self._decoded = -1
        self.image = None
        self._advance()
        if self.image is None:   # 解码出错（_advance 里已经停掉）或者一帧都没有
            self.stop()
            return None
        return name

    def stop(self):
        if self._container is not None:
            try:
                self._container.close()
            except Exception as e:
                print("动作动画关闭失败:", e)
        self.name, self.image, self._container, self._frames = None, None, None, None

    def update(self, dt):
        if self.name:
            self.t += dt
            if self.t >= self.dur:
                self.stop()
            else:
                self._advance()

    def _advance(self):
        """解到当前时间对应的帧；落后多帧时中间的只解码不转图。
        素材损坏、下载不完整之类解码出错时停掉这段，回到三视图，不往界面回调里抛异常。"""
        try:
            target = int(self.t * self._clips[self.name]["fps"])
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
        except Exception as e:
            print(f"动作动画 {self.name} 解码失败:", e)
            self.stop()

    def blend(self):
        """动画的不透明度：开头和结尾和三视图交叉淡化。"""
        if not self.name:
            return 0.0
        fade = self.lib.fade if self.lib else FADE
        if fade <= 0:
            return 1.0
        a = self.t / fade if self._fades[0] else 1.0
        b = (self.dur - self.t) / fade if self._fades[1] else 1.0
        return max(0.0, min(1.0, a, b))

    def _scale(self, h):
        return h / self._ref["h"]

    def extents(self, h):
        """以脚底为原点，画面往左、右、上、下各伸出多少（逻辑像素），给窗口留位置用。"""
        if not self.name:
            return 0.0, 0.0, 0.0, 0.0
        return clip_extents(self._ref, self._pos, self._crop.width(), self._crop.height(), h)

    def draw(self, p, foot_x, foot_y, h, mirror=False):
        """按人物身高 h 缩放，脚底对齐 (foot_x, foot_y)；mirror 时以脚底中线左右翻过来。"""
        if not self.name or self.image is None:
            return
        s = self._scale(h)
        ref, (x, y) = self._ref, self._pos
        p.save()
        p.setOpacity(p.opacity() * self.blend())
        p.translate(foot_x, foot_y)
        if mirror:
            p.scale(-1, 1)
        p.drawImage(QRectF((x - ref["cx"]) * s, (y - ref["foot"]) * s,
                           self._crop.width() * s, self._crop.height() * s), self.image)
        p.restore()


def clip_extents(ref, pos, w, hh, h):
    """一段画面（左上角在原画面 pos、大小 w×hh）按人物身高 h 缩放后，以脚底为原点往左、右、上、下各伸出多少。"""
    s = h / ref["h"]
    x, y = pos
    return ((ref["cx"] - x) * s, (x + w - ref["cx"]) * s,
            (ref["foot"] - y) * s, max(0.0, (y + hh - ref["foot"]) * s))
