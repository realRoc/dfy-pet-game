"""桌宠入口的冒烟测试：offscreen 下起 PetApp，点单击面板、建菜单、切置顶 / 显隐，退出时存档。
配置写到临时目录，不碰仓库里的 config.json。需要 PySide6，没装就跳过。
运行：python -m unittest discover tests"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QTimer
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QApplication, QMenu, QPushButton
    import common
    import main
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


@unittest.skipIf(_SKIP, _SKIP)
class PetAppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cfg_path = os.path.join(self.tmp, "config.json")
        p = mock.patch.object(common, "CONFIG_PATH", self.cfg_path)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(self.qapp, "quit")
        q.start()
        self.addCleanup(q.stop)
        self.app = main.PetApp(self.qapp)
        self.addCleanup(self.app.pet.timer.stop)

    def test_starts_and_menu_has_no_board(self):
        pet = self.app.pet
        self.assertTrue(pet.isVisible())
        texts = [a.text() for a in pet._build_menu().actions()]
        self.assertIn("退出", texts)
        self.assertFalse(any("飞行棋" in t for t in texts), texts)

    def test_single_click_panel_has_chat_tower_workout_room(self):
        pet = self.app.pet
        pet._on_single_click()
        self.assertTrue(pet.function_panel.isVisible())
        buttons = pet.function_panel.findChildren(QPushButton)
        self.assertEqual([b.toolTip() for b in buttons], ["聊天", "爬塔", "跟练", "后宅"])

    def test_chat_and_function_panel_are_hidden_windows(self):
        """两个面板有父控件，不带窗口类型就成了桌宠窗口里的子控件：
        聊天框一启动就显示在窗口外头，popup_at 给的屏幕坐标被当成窗口内坐标，弹出来看不见"""
        pet = self.app.pet
        for w in (pet.chat_dialog, pet.function_panel):
            self.assertTrue(w.isWindow(), type(w).__name__)
            self.assertFalse(w.isVisible(), type(w).__name__)
        pet._on_single_click()
        panel = pet.function_panel
        self.assertTrue(panel.isVisible())
        self.assertEqual(panel.mapToGlobal(QPoint(0, 0)), panel.pos())

    def test_topmost_and_toggle_visible(self):
        pet = self.app.pet
        pet.set_topmost(False)
        pet.set_topmost(True)
        self.app.toggle_visible()
        self.assertFalse(pet.isVisible())
        self.app.toggle_visible()
        self.assertTrue(pet.isVisible())

    def test_quit_saves_config(self):
        self.app.quit()
        self.qapp.quit.assert_called_once()
        with open(self.cfg_path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual((saved["x"], saved["y"]), (self.app.pet.x(), self.app.pet.y()))
        self.assertFalse(any(k.startswith("board_") for k in saved), saved)

    def test_menus_freed_after_use(self):
        """右键、托盘、跟练菜单每次都新建一棵，用完要删掉，不然挂在桌宠窗口下越积越多。"""
        pet = self.app.pet
        flush = lambda: QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        flush()
        base = len(pet.findChildren(QMenu))
        # 菜单 exec() 会一直等着点，弹出来就关掉（类上 patch exec 拦不住 PySide 的调用）
        closer = QTimer()
        closer.timeout.connect(lambda: (w := QApplication.activePopupWidget()) and w.close())
        closer.start(0)
        self.addCleanup(closer.stop)
        for _ in range(5):
            self.app.tray_menu.aboutToShow.emit()
            pet.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1), QPoint(1, 1)))
            pet.show_workout_menu()
            flush()
        self.assertEqual(len(pet.findChildren(QMenu)), base)

    def test_tray_menu_rebuilt_in_place(self):
        """macOS 上菜单栏菜单弹出来时才刷新；换掉或删掉正弹着的菜单，菜单就闪一下没了。"""
        menu = self.app.tray.contextMenu()
        self.app.pet.set_mode("still")
        menu.aboutToShow.emit()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertIs(self.app.tray.contextMenu(), menu)
        # 先拿住 QAction：PySide6 6.10 里它的包装一回收，menu() 拿到的子菜单包装就失效了
        act = next(a for a in menu.actions() if a.text() == "模式")
        self.assertEqual([a.text() for a in act.menu().actions() if a.isChecked()], ["原地待着"])


if __name__ == "__main__":
    unittest.main()
