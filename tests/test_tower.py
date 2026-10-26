"""桌宠里的爬塔入口：打包好的网页在不在、是不是最新的，单击面板和右键菜单能不能打开它。
爬塔本身的规则测试在 tower/ 里（npm test）。运行：python -m unittest discover -s tests"""
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOWER_SRC = os.path.join(ROOT, "tower")
TOWER_OUT = os.path.join(ROOT, "content", "tower")

try:
    from PySide6.QtCore import QObject, Slot
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication, QPushButton
    import common
    import main
    import pet
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""

    class UrlCatcher(QObject):
        """注册成 file:// 的处理器：openUrl 走 Qt 的真实分发，但不会真的弹出浏览器。"""
        def __init__(self):
            super().__init__()
            self.urls = []

        @Slot("QUrl")
        def open(self, url):
            self.urls.append(url)


def source_hash():
    """和 tower/tools/release.mjs 的 sourceHash() 同一个算法：路径排序、跳过点文件、换行统一成 LF。"""
    files = ["index.html", "package.json", "vite.config.ts"]
    for dirpath, dirnames, names in os.walk(os.path.join(TOWER_SRC, "src")):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in names:
            if not name.startswith("."):
                files.append(os.path.relpath(os.path.join(dirpath, name), TOWER_SRC).replace(os.sep, "/"))
    h = hashlib.sha256()
    for rel in sorted(files):
        with open(os.path.join(TOWER_SRC, rel), "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")
        h.update(rel.encode() + b"\n" + data + b"\n")
    return h.hexdigest()


class TowerBuildTest(unittest.TestCase):
    """不需要 PySide6：只看仓库里提交的打包产物。"""

    def test_bundled_page_exists_and_is_self_contained(self):
        path = os.path.join(TOWER_OUT, "index.html")
        self.assertTrue(os.path.isfile(path), "缺 content/tower/index.html，在 tower/ 里跑 npm run release")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("<canvas", html)
        self.assertIn("大肥鱼爬塔", html)
        # 单文件：脚本和样式都内联，双击就能玩，不依赖开发服务器
        self.assertNotIn('src="./src/', html)
        self.assertNotIn('<script type="module" src=', html)

    def test_bundled_page_matches_sources(self):
        with open(os.path.join(TOWER_OUT, "SOURCE_HASH"), encoding="utf-8") as f:
            built_from = f.read().strip()
        self.assertEqual(built_from, source_hash(),
                         "tower/ 的源码改过但没重新打包：在 tower/ 里跑 npm run release 再提交 content/tower/")


@unittest.skipIf(_SKIP, _SKIP)
class TowerEntryTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        p = mock.patch.object(common, "CONFIG_PATH", os.path.join(self.tmp, "config.json"))
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(self.qapp, "quit")
        q.start()
        self.addCleanup(q.stop)
        self.app = main.PetApp(self.qapp)
        self.addCleanup(self.app.pet.timer.stop)
        self.catcher = UrlCatcher()
        QDesktopServices.setUrlHandler("file", self.catcher, "open")
        self.addCleanup(QDesktopServices.unsetUrlHandler, "file")

    def test_path_points_at_the_bundled_page(self):
        self.assertEqual(os.path.normpath(common.TOWER_HTML), os.path.normpath(os.path.join(TOWER_OUT, "index.html")))
        self.assertTrue(os.path.isfile(common.TOWER_HTML))

    def assert_opened_tower(self):
        self.assertEqual(len(self.catcher.urls), 1)
        url = self.catcher.urls[0]
        self.assertTrue(url.isLocalFile())
        self.assertEqual(os.path.normpath(url.toLocalFile()), os.path.normpath(common.TOWER_HTML))

    def test_click_panel_opens_tower(self):
        pet_w = self.app.pet
        pet_w._on_single_click()
        tower_btn = next(b for b in pet_w.function_panel.findChildren(QPushButton) if b.toolTip() == "爬塔")
        tower_btn.click()
        self.assert_opened_tower()
        self.assertFalse(pet_w.function_panel.isVisible())

    def test_right_click_menu_opens_tower(self):
        action = next(a for a in self.app.pet._build_menu().actions() if a.text() == "🗼 爬塔")
        action.trigger()
        self.assert_opened_tower()

    def test_missing_build_says_so_instead_of_opening(self):
        with mock.patch.object(pet, "TOWER_HTML", os.path.join(self.tmp, "nope.html")):
            self.app.pet.open_tower()
        self.assertEqual(self.catcher.urls, [])
        self.assertIn("npm run release", self.app.pet.bubble_text)


if __name__ == "__main__":
    unittest.main()
