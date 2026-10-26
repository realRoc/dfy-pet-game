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
    from PySide6.QtWidgets import QApplication, QPushButton
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

    def test_single_click_panel_has_chat_and_tower(self):
        pet = self.app.pet
        pet._on_single_click()
        self.assertTrue(pet.function_panel.isVisible())
        buttons = pet.function_panel.findChildren(QPushButton)
        self.assertEqual([b.toolTip() for b in buttons], ["聊天", "爬塔"])

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


if __name__ == "__main__":
    unittest.main()
