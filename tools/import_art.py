"""把生成的原图整理成游戏素材：python tools/import_art.py <原图目录> <输出目录>

- 贴图（透明背景）：裁掉透明边，按最长边缩到 SPRITE_MAX
- tiles.png：石板图集，按透明间隙切成一行行、一块块，各自裁边，存成 tile_<序号>.webp
- tex_*.png：纹理，偏移半格后用渐变遮罩混合消掉接缝，缩到 TEX_SIZE

输出 WebP（PySide6-Essentials 自带读取插件），比 PNG 小一个数量级。

原图通常 1~2MB 一张，不进仓库；处理后的小图放 content/art/<地图>/。
"""
import os
import sys

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter

SPRITE_MAX = 640
TILE_MAX = 256
TEX_SIZE = 512
QUALITY = 90


def alpha_bbox(img, rect=None, threshold=12):
    rect = rect or img.rect()
    left, top, right, bottom = rect.right(), rect.bottom(), rect.left(), rect.top()
    step = 2
    for y in range(rect.top(), rect.bottom() + 1, step):
        for x in range(rect.left(), rect.right() + 1, step):
            if img.pixelColor(x, y).alpha() > threshold:
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    if right < left:
        return None
    return QRect(QPoint(left, top), QPoint(right, bottom)).adjusted(-2, -2, 2, 2).intersected(rect)


def fit(img, max_side):
    if max(img.width(), img.height()) <= max_side:
        return img
    return img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def save(img, dst):
    img.save(dst, "WEBP", QUALITY)


def clear_haze(img, floor=40):
    """生成图偶尔在物体周围留一层很淡的半透明雾，透明度低于 floor 的像素直接清掉。"""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            if 0 < img.pixelColor(x, y).alpha() < floor:
                img.setPixelColor(x, y, QColor(0, 0, 0, 0))
    return img


def sprite(src, dst, max_side=SPRITE_MAX):
    img = QImage(src).convertToFormat(QImage.Format.Format_ARGB32)
    box = alpha_bbox(img, threshold=40)
    save(clear_haze(fit(img.copy(box) if box else img, max_side)), dst)


def _runs(flags, min_len=20):
    """连续为 True 的区间 [(开始, 结束)]，太短的当噪点丢掉。"""
    runs, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                runs.append((start, i - 1))
            start = None
    return runs


def sheet(src, out_dir):
    """先按整行透明的间隙切出每一行，再在行内按整列透明的间隙切出每一块。"""
    img = QImage(src).convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()

    def solid(x, y):
        return img.pixelColor(x, y).alpha() > 40

    rows = _runs([any(solid(x, y) for x in range(0, w, 3)) for y in range(h)])
    n = 0
    for top, bottom in rows:
        cols = _runs([any(solid(x, y) for y in range(top, bottom + 1, 3)) for x in range(w)])
        for left, right in cols:
            box = alpha_bbox(img, QRect(left, top, right - left + 1, bottom - top + 1))
            if box:
                save(fit(img.copy(box), TILE_MAX), os.path.join(out_dir, f"tile_{n:02d}.webp"))
                n += 1
    return n


def tileable(src, dst):
    img = QImage(src).convertToFormat(QImage.Format.Format_ARGB32)
    n = min(img.width(), img.height())
    img = img.copy(0, 0, n, n)
    h = n // 2
    # 偏移半格：接缝跑到中间，四边变成原图中心，平铺时连续
    rolled = QImage(n, n, QImage.Format.Format_ARGB32)
    p = QPainter(rolled)
    for dx, dy in ((0, 0), (h, 0), (0, h), (h, h)):
        p.drawImage(QPoint(dx, dy), img, QRect((dx + h) % n, (dy + h) % n, n - h, n - h))
    p.end()
    # 原图乘上“中间不透明、四边透明”的遮罩后盖在上面，把中间的接缝盖住
    masked = img.copy()
    p = QPainter(masked)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    for horizontal in (True, False):
        g = QLinearGradient(0, 0, n, 0) if horizontal else QLinearGradient(0, 0, 0, n)
        for t, a in ((0, 0), (0.3, 255), (0.7, 255), (1, 0)):
            g.setColorAt(t, QColor(0, 0, 0, a))
        p.fillRect(0, 0, n, n, g)
    p.end()
    p = QPainter(rolled)
    p.drawImage(0, 0, masked)
    p.end()
    save(rolled.scaled(TEX_SIZE, TEX_SIZE, Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB32), dst)


def main(src_dir, out_dir):
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    os.makedirs(out_dir, exist_ok=True)
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(".png"):
            continue
        src, stem = os.path.join(src_dir, name), name[:-4]
        if stem.startswith("tex_"):
            tileable(src, os.path.join(out_dir, stem + ".webp"))
        elif stem == "tiles":
            print(f"  图集切出 {sheet(src, out_dir)} 块")
        else:
            sprite(src, os.path.join(out_dir, stem + ".webp"))
        print("✓", name)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
