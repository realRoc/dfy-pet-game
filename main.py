"""大肥鱼飞行棋 · 入口

桌宠和棋盘两个窗口，同一时间只显示一个：
- 棋盘展开：大肥鱼在棋盘上掷骰子跑格子
- 棋盘收起：大肥鱼从当前格子回到桌面，继续散步 / 互动
"""
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from common import APP_NAME, SPRITE_DIR, load_config, save_config, relaunch_in_mac_app
from board_game import BoardWindow
from pet import PetWindow, TICK


class PetApp:
    def __init__(self, qapp):
        self.qapp = qapp
        self.cfg = load_config()
        self.pet = PetWindow(self, self.cfg)
        self.board = BoardWindow(self, self.cfg)

        # 托盘（macOS 是菜单栏图标）：鼠标穿透后从这里解除
        self.tray = QSystemTrayIcon(self.pet.icon, self.pet)
        self.tray.setToolTip(APP_NAME)
        self.tray.setContextMenu(self.pet._build_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        if self.cfg.get("board_open", True):
            bx, by = self.cfg.get("board_x"), self.cfg.get("board_y")
            if bx is None or by is None:
                self.board.place_fish_at(self.pet.foot_global())
            else:
                self.board.move(int(bx), int(by))
            self._show(self.board)
            self.board.on_shown("主人，点骰子带我去玩！")
        else:
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

    def open_board(self):
        if self.board.isVisible():
            self.board.raise_()
            return
        self.pet.function_panel.hide()
        self.pet.food_panel.hide()
        self.pet.chat_dialog.hide()
        self.pet.stop_clip()
        self.board.place_fish_at(self.pet.foot_global())
        self.pet.hide()
        self._show(self.board)
        self.board.on_shown("回到棋盘！继续冒险～")
        self.cfg["board_open"] = True

    def collapse_board(self):
        if not self.board.isVisible():
            return
        self.board.clip.stop()
        foot = self.board.foot_global()
        self.board.save_state()
        self.board.hide()
        self.pet.place_foot_at(foot)
        self.pet.target = None
        self.pet.rest_until = self.pet.t * TICK + 3000
        self.pet._set_dir("down", 1)
        self._show(self.pet)
        self.pet.jump_t = 1.0
        self.pet.last_line = ""
        self.pet.say("棋盘收好啦，我出去溜达～")
        self.cfg["board_open"] = False

    def toggle_visible(self):
        w = self.board if self.cfg.get("board_open") else self.pet
        if w.isVisible():
            w.hide()
        else:
            self._show(w)

    def quit(self):
        self.cfg["x"], self.cfg["y"] = self.pet.x(), self.pet.y()
        self.board.save_state()
        save_config(self.cfg)
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
