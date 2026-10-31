"""路径、平台差异、配置读写、精灵加载等公共部分。"""
import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QApplication

from character import CHAR

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR
# 配置、自写的训练计划、macOS 的 .app 外壳这些要写的东西放这里。
# 作为 dsh 插件跑时代码在 node_modules 里，升级会整个换掉，dsh 插件用 DFY_DATA_DIR 指到它自己的数据目录
DATA_DIR = os.environ.get("DFY_DATA_DIR") or APP_DIR
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
UI_FONT = "PingFang SC" if IS_MAC else "Microsoft YaHei UI"
EMOJI_FONT = "Apple Color Emoji" if IS_MAC else "Segoe UI Emoji"

APP_NAME = CHAR.name
SPRITE_SRC_H = CHAR.sprite_h  # 角色包里立绘原图的高度
ICON_PATH = CHAR.sprite("icon")
# 引擎里三视图的名字 → 清单里的键
VIEWS = {"正面": "front", "侧面": "side", "背面": "back"}

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
    "water_on": True,        # 喝水提醒，默认开
    "water_interval": 45,    # 分钟
    "water_quiet": True,     # 22:00–9:00 不提醒
    "water_mute": "",        # 「今天别提醒了」的日期
    "water_cups": {},        # {"date": "2026-10-28", "n": 3}
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
    """无边框浮窗。macOS 上 Tool 窗口会在应用失焦时自动隐藏，只在 Windows 用它来隐藏任务栏图标。
    macOS 上也得带窗口类型：setWindowFlags 会整个换掉 flags，有父控件的面板（聊天框、功能面板）
    不带 Window 就成了桌宠窗口里的子控件，按屏幕坐标 move 出去就看不见了。"""
    flags = Qt.WindowType.FramelessWindowHint
    flags |= Qt.WindowType.Tool if IS_WIN else Qt.WindowType.Window
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
        contents = os.path.join(DATA_DIR, "build", f"{APP_NAME}.app", "Contents")
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
        os.makedirs(DATA_DIR, exist_ok=True)
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
    for name, view in VIEWS.items():
        pix = QPixmap(CHAR.sprite(view))
        if view == "side" and CHAR.side_faces == "right":   # 引擎按侧面图脸朝左来镜像
            pix = QPixmap.fromImage(pix.toImage().flipped(Qt.Orientation.Horizontal))
        pix = pix.scaledToHeight(px_h, Qt.TransformationMode.SmoothTransformation)
        pix.setDevicePixelRatio(px_h / height)
        out[name] = pix
    return out


def pix_size(pix):
    return pix.width() / pix.devicePixelRatio(), pix.height() / pix.devicePixelRatio()
