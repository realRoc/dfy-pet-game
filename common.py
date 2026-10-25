"""路径、平台差异、配置读写、精灵加载等公共部分。"""
import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QApplication

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR
SPRITE_DIR = os.path.join(BUNDLE_DIR, "sprites")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
UI_FONT = "PingFang SC" if IS_MAC else "Microsoft YaHei UI"
EMOJI_FONT = "Apple Color Emoji" if IS_MAC else "Segoe UI Emoji"

SPRITE_SRC_H = 340  # sprites/ 里原图的高度

DEFAULT_CFG = {
    "mode": "wander",
    "size": 0.7,
    "topmost": True,
    "passthrough": False,
    "autostart": False,
    "x": None,
    "y": None,
    "ds_api_key": "",
    "city": "汕头",
    "board_open": True,
    "board_x": None,
    "board_y": None,
    "board_map": "medieval",    # content/maps/ 下的地图目录名
    "board_node": None,         # 当前节点 id；为空时从旧字段 board_pos 换算
    "board_pos": 0,
    "board_coins": 0,
    "board_turn": 0,
    "board_skip_next": False,   # 下回合暂停（恶作剧、睡着等事件）
    "dice_skin": None,          # content/dice/ 下的皮肤目录名；为空时用地图默认的骰子
}


def ui_font(px, bold=False):
    f = QFont(UI_FONT)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def emoji_font(px):
    f = QFont(EMOJI_FONT)
    f.setPixelSize(max(1, int(px)))
    return f


def float_flags(topmost=True):
    """无边框浮窗。macOS 上 Tool 窗口会在应用失焦时自动隐藏，只在 Windows 用它来隐藏任务栏图标。"""
    flags = Qt.WindowType.FramelessWindowHint
    if IS_WIN:
        flags |= Qt.WindowType.Tool
    if topmost:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    return flags


def load_config():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        print("配置读取失败:", e)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("配置保存失败:", e)


def load_sprites(height):
    """按逻辑高度加载三视图，按屏幕缩放比生成高清版本（Retina 下不发糊）。"""
    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen else 1.0
    px_h = min(SPRITE_SRC_H, int(height * dpr))
    out = {}
    for name in ("正面", "侧面", "背面"):
        pix = QPixmap(os.path.join(SPRITE_DIR, f"{name}.png"))
        pix = pix.scaledToHeight(px_h, Qt.TransformationMode.SmoothTransformation)
        pix.setDevicePixelRatio(px_h / height)
        out[name] = pix
    return out


def pix_size(pix):
    return pix.width() / pix.devicePixelRatio(), pix.height() / pix.devicePixelRatio()
