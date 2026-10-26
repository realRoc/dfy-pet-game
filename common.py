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

APP_NAME = "大肥鱼"
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


def relaunch_in_mac_app():
    """macOS 上程序坞和 ⌘Tab 显示的是可执行文件所在 .app 的名字，直接跑解释器就是 Python。
    把解释器复制进 build/大肥鱼.app，再从那里重新启动自己；
    __PYVENV_LAUNCHER__ 和系统自带的 python 启动器用法一样，让它照旧用当前的虚拟环境。"""
    if not IS_MAC or getattr(sys, "frozen", False) or os.environ.get("DFY_IN_APP"):
        return
    src = os.path.join(sys.base_prefix, "Resources", "Python.app", "Contents", "MacOS", "Python")
    if not os.path.isfile(src):  # 不是 framework 版的 Python，没有可借用的解释器
        return
    try:
        import filecmp
        import plistlib
        import shutil
        contents = os.path.join(APP_DIR, "build", f"{APP_NAME}.app", "Contents")
        exe = os.path.join(contents, "MacOS", APP_NAME)
        if not (os.path.isfile(exe) and filecmp.cmp(src, exe, shallow=False)):
            os.makedirs(os.path.dirname(exe), exist_ok=True)
            shutil.copy2(src, exe)
        # Info.plist 单独检查：上次可能复制完解释器就被打断，没写上或写坏了
        plist = os.path.join(contents, "Info.plist")
        info = {
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleExecutable": APP_NAME,
            "CFBundleIdentifier": "io.github.dfy-pet-game",
            "CFBundlePackageType": "APPL",
            "NSHighResolutionCapable": True,
        }
        try:
            with open(plist, "rb") as f:
                plist_ok = plistlib.load(f) == info
        except Exception:
            plist_ok = False
        if not plist_ok:
            with open(plist, "wb") as f:
                plistlib.dump(info, f)
        env = dict(os.environ, DFY_IN_APP="1", __PYVENV_LAUNCHER__=sys.executable)
        os.execve(exe, [exe, os.path.abspath(sys.argv[0])] + sys.argv[1:], env)
    except Exception as e:
        print("以独立程序名启动失败，继续用 Python 运行:", e)


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
