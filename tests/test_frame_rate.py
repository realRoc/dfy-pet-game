"""帧率：闲着只剩呼吸、轻摇时降到约 16 帧（一帧补 3 步逻辑，计时不变）；
要走路、播动画、做表情、冒气泡、拖拽、dsh 指令一来马上回 50 帧；藏起来时更慢。
运行：python -m unittest discover tests"""
import io
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    import clips
    import common
    import control
    import main
    import pet as pet_mod
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


@unittest.skipIf(_SKIP, _SKIP)
class FrameRateTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        patches = [mock.patch.object(common, "CONFIG_PATH", os.path.join(self.tmp, "config.json")),
                   mock.patch.object(self.qapp, "quit"),
                   mock.patch.object(pet_mod.PetWindow, "_maybe_idle_action", lambda self: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = main.PetApp(self.qapp)
        self.pet = self.app.pet
        self.addCleanup(self.pet.timer.stop)
        self.pet.water.update = lambda *a, **k: []   # 别让喝水提醒插进来
        self.pet.check_system_status = lambda: None
        self.pet.mode = "still"

    def settle(self, frames=20):
        """一帧一帧推（不等定时器真跳），推到她闲下来。"""
        for _ in range(frames):
            self.pet._frame()

    def test_idle_uses_slow_interval_and_keeps_time(self):
        pet = self.pet
        self.settle()
        self.assertEqual(pet.timer.interval(), pet_mod.IDLE_FRAME)
        t = pet.t
        pet._frame()
        self.assertEqual(pet.t - t, pet_mod.IDLE_FRAME // pet_mod.TICK)   # 降帧不降速：一帧补够步数

    def test_walk_restores_full_rate_on_the_first_step(self):
        pet = self.pet
        self.settle()
        pet.mode, pet.rest_until = "wander", 0
        t = pet.t
        pet._frame()
        self.assertIsNotNone(pet.target)
        self.assertEqual(pet.t - t, 1)   # 一迈腿就不再补步
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)
        pet.target, pet.mode = None, "still"   # 走到了：转身那下的交叉淡化完再降回去
        self.settle()
        self.assertEqual(pet.timer.interval(), pet_mod.IDLE_FRAME)

    def test_expression_restores_full_rate_and_drops_after(self):
        pet = self.pet
        self.settle()
        pet.play_expression("happy")
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)
        for _ in range(400):   # 表情 2 秒、气泡 2.8 秒，都过去了
            pet._frame()
        self.assertEqual(pet.timer.interval(), pet_mod.IDLE_FRAME)

    @unittest.skipUnless(clips.AVAILABLE, "没有动作动画素材")
    def test_clip_restores_full_rate(self):
        pet = self.pet
        self.settle()
        self.assertTrue(pet.play_clip())
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)

    def test_bubble_and_jump_restore_full_rate(self):
        pet = self.pet
        self.settle()
        pet.say("说句话")
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)
        pet.bubble_text = ""
        self.settle()
        pet.jump_t = 1.0   # 闲着时自己蹦一下：补步补到一半就停
        t = pet.t
        pet._frame()
        self.assertEqual(pet.t - t, 1)
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)

    def test_drag_restores_full_rate(self):
        pet = self.pet
        self.settle()
        pet.dragging = True
        pet._pace()
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)

    def test_control_command_restores_full_rate(self):
        pet = self.pet
        self.settle()
        quit_ = mock.patch.object(self.app, "quit").start()
        self.addCleanup(mock.patch.stopall)
        # 留着 ctl：它一被回收，读线程发的信号就没人接了
        ctl = control.attach(self.app, io.StringIO('{"cmd": "emote", "key": "love"}\n'))
        deadline = time.monotonic() + 3
        while not quit_.called and time.monotonic() < deadline:   # 读线程发的信号排队到主线程
            QCoreApplication.processEvents()
            time.sleep(0.005)
        self.assertTrue(quit_.called)
        self.assertTrue(pet.expr.active)
        self.assertEqual(pet.timer.interval(), pet_mod.TICK)

    def test_hidden_is_slower_but_water_clock_keeps_running(self):
        pet = self.pet
        self.settle()
        pet.water.phase = "away"   # 气跑了：窗口藏起来，喝水提醒照样计时
        pet.hide()
        pet._frame()
        self.assertEqual(pet.timer.interval(), pet_mod.HIDDEN_FRAME)
        pet._water_acc = 0.0
        pet._frame()
        self.assertAlmostEqual(pet._water_acc, pet_mod.HIDDEN_FRAME / 1000.0)
        pet.water.phase = "wait"
        pet.show()
        self.assertEqual(pet.timer.interval(), pet_mod.IDLE_FRAME)


if __name__ == "__main__":
    unittest.main()
