"""大肥鱼桌宠 · 入口"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from common import APP_NAME, ICON_PATH, load_config, save_config, relaunch_in_mac_app
from pet import PetWindow


class PetApp:
    def __init__(self, qapp):
        self.qapp = qapp
        self.cfg = load_config()
        self.im = self._make_im()   # 要在 PetWindow 之前：功能面板、右键菜单看它有没有决定出不出「连接 IM」
        self.pet = PetWindow(self, self.cfg)

        # 托盘（macOS 是菜单栏图标）：鼠标穿透后从这里解除
        self.tray = QSystemTrayIcon(self.pet.icon, self.pet)
        self.tray.setToolTip(APP_NAME)
        # 托盘只用这一个菜单，打开前原地重建内容。macOS 上 activated 是菜单已经弹出来时才发，
        # 那时再 setContextMenu 换菜单、删旧菜单，正弹着的菜单就被删了，一点就闪退
        self.tray_menu = QMenu(self.pet)
        self.tray_menu.aboutToShow.connect(self._refresh_tray_menu)
        self._refresh_tray_menu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()

        self._show(self.pet)
        self.pet.snap_into_screen()
        self.pet.apply_passthrough_from_cfg()
        if self.im:
            self.im.start_enabled()

    def _make_im(self):
        """IM 机器人（im/）。依赖没装（discord.py / aiohttp）就是 None，入口也不出现。"""
        try:
            from im.qt import IMService
        except Exception as e:
            print("IM 机器人不可用:", e)
            return None
        return IMService(self) if IMService.platforms() else None

    def _show(self, w):
        w.show()
        w.raise_()
        w.activateWindow()

    def _refresh_tray_menu(self):
        """菜单里的勾选状态（模式、穿透等）、喝水杯数每次打开前刷新。
        clear() 只删动作、不删子菜单，旧子菜单挂在托盘菜单下，得自己删。"""
        m = self.tray_menu
        old_subs = m.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly)
        m.clear()
        for sub in old_subs:
            sub.deleteLater()
        self.pet._fill_menu(m)

    def toggle_visible(self):
        if self.pet.isVisible():
            self.pet.hide()
        else:
            self._show(self.pet)

    def quit(self):
        self.cfg["x"], self.cfg["y"] = self.pet.x(), self.pet.y()
        save_config(self.cfg)
        if self.im:
            self.im.shutdown()
        self.pet.announcer.stop()
        if self.pet.room_server:
            self.pet.room_server.stop()
        self.tray.hide()
        self.qapp.quit()


def main():
    relaunch_in_mac_app()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP_NAME)
    qapp.setWindowIcon(QIcon(ICON_PATH))
    app = PetApp(qapp)
    qapp.aboutToQuit.connect(lambda: save_config(app.cfg))
    if os.environ.get("DFY_CONTROL") == "stdin":  # 作为 dsh 插件的子进程跑
        import control
        app.control = control.attach(app)
    sys.exit(qapp.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        try:
            qapp = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, f"{APP_NAME}出错", str(ex))
        except Exception:
            pass
        raise
