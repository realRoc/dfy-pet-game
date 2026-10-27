"""把生成好的跟练姿势图整理成素材：python tools/make_workout_frames.py <原图目录>

原图是用 ChatGPT 的图片生成（Codex CLI 的 image_gen，参考 sprites/正面.png）一张张画的透明 PNG，
每个姿势一张，文件名就是帧名（stand.png、squat_wide.png……），提示词见 content/workout/README.md。
生成出来的人物大小、留白各不相同，这里逐张：
- 按 alpha 裁掉空白
- 按 POSES 里给的「这个姿势有多高（相对站直）」算出站直时的身高 unit，统一缩放到 UNIT 像素，
  运行时按桌宠身高 / unit 缩放，蹲着、躺着的图和站着的一样大
- 记下脚底锚点：默认是外框底边中点，侧身的图（尾巴、电饭煲伸出去）用 ax 指定身体中线在外框里的位置

产物放 content/workout/frames/：每帧一个 PNG，外加 frames.json。只用 PySide6，不需要别的库。
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt   # noqa: E402
from PySide6.QtGui import QImage   # noqa: E402
from PySide6.QtWidgets import QApplication   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "content", "workout", "frames")
UNIT = 560          # 站直时的身高（像素）：最大号桌宠在 2x 屏上约 612，够用且不太占仓库
ALPHA_MIN = 16
PAD = 2

# 帧名: (姿势高度 / 站直身高, 脚底锚点在外框里的横向位置 0~1)
POSES = {
    "stand":         (1.00, 0.50),
    "squat_wide":    (0.84, 0.50),
    "squat_narrow":  (0.87, 0.50),
    "squat_wide_half":   (0.84, 0.50),
    "squat_narrow_half": (0.95, 0.50),
    "curtsy":        (0.92, 0.50),
    "lunge":         (0.84, 0.50),
    "lunge_half":    (0.82, 0.50),
    "lift":          (0.97, 0.45),
    "hinge":         (0.88, 0.40),
    "bridge_down":   (0.56, 0.50),
    "bridge_up":     (0.47, 0.50),
    "bridge_single": (0.55, 0.50),
    "wall_sit":      (1.00, 0.50),
    "tired":         (0.90, 0.50),
    "collapse":      (0.50, 0.50),
    "slack":         (0.86, 0.50),
    "lazy_squat":    (0.98, 0.50),
    "drink":         (0.97, 0.50),
    "cheer":         (1.00, 0.50),
}


def alpha_bbox(img):
    """alpha 超过阈值的外框 (x0, y0, x1, y1)，含端点。"""
    w, h = img.width(), img.height()
    a = img.convertToFormat(QImage.Format.Format_Alpha8)
    bits = a.constBits()
    stride = a.bytesPerLine()
    data = bytes(bits)
    rows = [y for y in range(h) if max(data[y * stride:y * stride + w]) > ALPHA_MIN]
    cols = [x for x in range(w) if any(data[y * stride + x] > ALPHA_MIN for y in range(rows[0], rows[-1] + 1, 2))]
    return cols[0], rows[0], cols[-1], rows[-1]


def main(src):
    QApplication.instance() or QApplication([])
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = {}
    for name, (rel_h, ax) in POSES.items():
        path = os.path.join(src, f"{name}.png")
        img = QImage(path)
        if img.isNull():
            sys.exit(f"缺 {path}")
        if not img.hasAlphaChannel():
            sys.exit(f"{path} 没有透明通道")
        x0, y0, x1, y1 = alpha_bbox(img)
        x0, y0 = max(0, x0 - PAD), max(0, y0 - PAD)
        x1, y1 = min(img.width() - 1, x1 + PAD), min(img.height() - 1, y1 + PAD)
        crop = img.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        s = UNIT * rel_h / crop.height()
        out = crop.scaled(round(crop.width() * s), round(crop.height() * s),
                          Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        out.save(os.path.join(OUT_DIR, f"{name}.png"), "PNG", 0)
        frames[name] = {"file": f"{name}.png", "w": out.width(), "h": out.height(),
                        "ax": round(out.width() * ax, 1), "ay": out.height() - PAD * s, "unit": UNIT}
        print(f"{name:14s} {img.width()}x{img.height()} → {out.width()}x{out.height()}")
    with open(os.path.join(OUT_DIR, "frames.json"), "w", encoding="utf-8") as f:
        json.dump({"unit": UNIT, "frames": frames}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
