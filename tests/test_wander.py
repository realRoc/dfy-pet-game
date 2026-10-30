"""闲逛：挑的目标让整个窗口留在屏幕里；走路被屏幕边挡住就停下来歇着，不会背身原地走一辈子。
运行：python -m unittest discover tests"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    import common
    import main
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


def far_away(pet):
    """挪到离屏幕老远的地方。offscreen 屏幕只有 800 见方，窗口占了快一半，随机目标偶尔就落在脚下 12px 内，
    同一帧就算「走到了」把目标清掉；挪远了才稳定看得到刚挑的目标。"""
    pet.move(-5000, -5000)


@unittest.skipIf(_SKIP, _SKIP)
class WanderTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        patches = [mock.patch.object(common, "CONFIG_PATH", os.path.join(self.tmp, "config.json")),
                   mock.patch.object(self.qapp, "quit")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = main.PetApp(self.qapp)
        self.pet = self.app.pet
        self.pet.timer.stop()
        self.addCleanup(self.pet.timer.stop)
        self.pet.mode = "wander"
        self.pet.water.update = lambda *a, **k: []   # 别让喝水提醒插进来

    def test_target_keeps_whole_window_on_screen(self):
        pet = self.pet
        geo = (pet.screen() or QApplication.primaryScreen()).availableGeometry()
        for _ in range(50):
            pet.target, pet.rest_until = None, 0
            far_away(pet)
            pet.tick()
            cx, cy = pet.target
            self.assertGreaterEqual(cx - pet.width() / 2, geo.left())
            self.assertLessEqual(cx + pet.width() / 2, geo.right() + 1)
            self.assertGreaterEqual(cy - pet.height() / 2, geo.top())
            self.assertLessEqual(cy + pet.height() / 2, geo.bottom() + 1)

    def test_blocked_walk_gives_up_and_rests(self):
        pet = self.pet
        pet.rest_until = 0
        far_away(pet)
        pet.tick()
        self.assertIsNotNone(pet.target)
        with mock.patch.object(pet, "move"):   # 系统把窗口挡住：怎么 move 都不动
            for _ in range(80):
                pet.tick()
                if pet.target is None:
                    break
        self.assertIsNone(pet.target)
        self.assertEqual(pet.dir, "down")
        self.assertGreater(pet.rest_until, pet.t * 20)


if __name__ == "__main__":
    unittest.main()
