"""大肥鱼桌宠 · 入口"""
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from common import APP_NAME, SPRITE_DIR, load_config, save_config, relaunch_in_mac_app
from pet import PetWindow


class PetApp:
    def __init__(self, qapp):
        self.qapp = qapp
        self.cfg = load_config()
        self.pet = PetWindow(self, self.cfg)

        # 托盘（macOS 是菜单栏图标）：鼠标穿透后从这里解除
        self.tray = QSystemTrayIcon(self.pet.icon, self.pet)
        self.tray.setToolTip(APP_NAME)
        self.tray.setContextMenu(self.pet._build_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self._show(self.pet)
        self.pet.snap_into_screen()
        self.pet.apply_passthrough_from_cfg()

    def _show(self, w):
        w.show()
        w.raise_()
        w.activateWindow()

    def _on_tray_activated(self, _reason):
        # 菜单里的勾选状态（模式、穿透等）每次打开前刷新
        self.tray.setContextMenu(self.pet._build_menu())

    def toggle_visible(self):
        if self.pet.isVisible():
            self.pet.hide()
        else:
            self._show(self.pet)

    def quit(self):
        self.cfg["x"], self.cfg["y"] = self.pet.x(), self.pet.y()
        save_config(self.cfg)
        self.pet.announcer.stop()
        self.tray.hide()
        self.qapp.quit()


def main():
    relaunch_in_mac_app()
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP_NAME)
    qapp.setWindowIcon(QIcon(os.path.join(SPRITE_DIR, "icon.png")))
    app = PetApp(qapp)
    qapp.aboutToQuit.connect(lambda: save_config(app.cfg))
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
