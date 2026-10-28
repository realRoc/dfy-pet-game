"""喝水提醒：状态机的计时、升级、离场返场，碎屏特效能画，桌宠里从扔大水到返场整套走得通。
运行：python -m unittest discover tests"""
import datetime
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPointF, QRect
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication
    import common
    import main
    import water
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""

DAY = datetime.datetime(2026, 10, 28, 14, 0)


def run(w, secs, idle=0.0, busy=False, now=DAY, step=1.0):
    """按秒往前走，收集所有事件。"""
    events = []
    t = 0.0
    while t < secs - 1e-9:
        events += w.update(step, idle, busy, now)
        t += step
    return events


@unittest.skipIf(_SKIP, _SKIP)
class WaterReminderTest(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(common.DEFAULT_CFG, water_cups={})
        self.w = water.WaterReminder(self.cfg)

    def test_first_reminder_at_interval(self):
        self.assertEqual(run(self.w, 45 * 60 - 1), [])
        self.assertEqual(run(self.w, 1), [("level", 1, False)])
        self.assertEqual(self.w.phase, "remind")

    def test_escalates_every_five_minutes_then_finale(self):
        run(self.w, 45 * 60)
        self.assertEqual(run(self.w, 300), [("level", 2, False)])
        self.assertEqual(run(self.w, 300), [("level", 3, False)])
        self.assertEqual(run(self.w, 300), [("level", 4, False)])
        self.assertEqual(self.w.phase, "finale")
        self.assertEqual(run(self.w, 3600), [], "气跑的戏没演完前不往下走")

    def test_away_and_return_sulk_then_cold(self):
        run(self.w, 45 * 60 + 900)
        self.w.left()
        self.assertEqual(self.w.phase, "away")
        events = run(self.w, water.AWAY_SECS[1])
        self.assertEqual(events, [("return", False)])
        self.assertEqual(self.w.phase, "back")
        self.w.returned()
        self.assertEqual(self.w.phase, "wait")
        self.assertEqual(self.w.cold, water.COLD_SECS)
        run(self.w, water.COLD_SECS)
        self.assertEqual(self.w.cold, 0)

    def test_drink_while_away_makes_up(self):
        run(self.w, 45 * 60 + 900)
        self.assertEqual(self.w.drink(DAY)[0], "late")
        self.w.left()
        self.assertEqual(self.w.drink(DAY)[0], "late")
        self.assertEqual(run(self.w, water.AWAY_SECS[1]), [("return", True)])
        self.w.returned()
        self.assertEqual(self.w.cold, 0)
        self.assertEqual(self.w.cups(DAY), 2)

    def test_drink_resets_and_counts_per_day(self):
        run(self.w, 45 * 60 + 300)
        self.assertEqual(self.w.drink(DAY), ("cheers", 1, False))
        self.assertEqual((self.w.phase, self.w.level, self.w.elapsed), ("wait", 0, 0.0))
        self.w.drink(DAY)
        self.assertEqual(self.w.cups(DAY), 2)
        tomorrow = DAY + datetime.timedelta(days=1)
        self.assertEqual(self.w.cups(tomorrow), 0)
        self.assertEqual(self.w.drink(tomorrow)[1], 1)

    def test_drink_ends_cold_mode(self):
        self.w.cold = 100
        self.assertEqual(self.w.drink(DAY), ("cheers", 1, True))
        self.assertEqual(self.w.cold, 0)

    def test_idle_pauses_clock_and_welcome_back(self):
        run(self.w, 30 * 60)
        for i in range(3600):   # 空闲时间一秒秒往上涨
            self.assertEqual(self.w.update(1.0, water.IDLE_PAUSE + i, False, DAY), [])
        self.assertEqual(self.w.phase, "wait", "人不在不计时")
        events = run(self.w, 1)
        self.assertEqual(events, [("level", 1, True)], "离开很久回来先提醒一次")

    def test_short_idle_does_not_welcome(self):
        run(self.w, 10 * 60)
        run(self.w, 600, idle=water.IDLE_PAUSE + 1)
        self.assertEqual(run(self.w, 1), [])

    def test_busy_defers(self):
        self.assertEqual(run(self.w, 50 * 60, busy=True), [])
        self.assertEqual(run(self.w, 1), [("level", 1, False)])
        self.assertEqual(run(self.w, 400, busy=True), [])
        self.assertEqual(run(self.w, 1), [("level", 2, False)])

    def test_quiet_hours_mute_and_off(self):
        night = DAY.replace(hour=23)
        self.assertEqual(run(self.w, 3 * 3600, now=night), [])
        self.cfg["water_quiet"] = False
        self.assertEqual(run(self.w, 45 * 60, now=night), [("level", 1, False)])
        self.cfg["water_quiet"] = True
        run(self.w, 1, now=night)
        self.assertEqual(self.w.phase, "wait", "提醒到一半进了夜里：这一轮作罢")
        w = water.WaterReminder(dict(self.cfg, water_mute=DAY.date().isoformat()))
        self.assertEqual(run(w, 3 * 3600), [])
        w = water.WaterReminder(dict(self.cfg, water_on=False))
        self.assertEqual(run(w, 3 * 3600), [])

    def test_snooze(self):
        run(self.w, 45 * 60)
        self.assertTrue(self.w.snooze())
        self.assertEqual(run(self.w, water.SNOOZE - 1), [])
        self.assertEqual(run(self.w, 1), [("level", 1, False)])
        self.assertFalse(water.WaterReminder(self.cfg).snooze())

    def test_interval_from_config(self):
        self.cfg["water_interval"] = 30
        self.assertEqual(run(self.w, 30 * 60), [("level", 1, False)])

    def test_lines_format(self):
        for level in (1, 2, 3, 4):
            self.assertTrue(water.line(level, m=45))
        self.assertIn("3/8", water.line("cheers", n=3, goal=8))


@unittest.skipIf(_SKIP, _SKIP)
class ShatterOverlayTest(unittest.TestCase):
    def test_paints_every_stage_and_closes(self):
        app = QApplication.instance() or QApplication([])
        hits = []
        o = water.ShatterOverlay(QRect(0, 0, 800, 600), QPointF(600, 400), QPointF(450, 300), 200,
                                 on_impact=lambda: hits.append(1), seed=1)
        o.timer.stop()
        for t in (0.1, 0.5, 0.6, 0.7, 1.5, 6.0, 6.8):
            o.t = t
            img = QImage(800, 600, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(QColor(0, 0, 0, 0))
            p = QPainter(img)
            o.paint(p)
            p.end()
        o.t = 0.0
        o.advance(0.3)
        o.advance(0.3)
        self.assertEqual(hits, [1], "撞上屏幕只响一次")
        o.advance(o.total)
        self.assertTrue(o.done)
        app.processEvents()


@unittest.skipIf(_SKIP, _SKIP)
class PetWaterFlowTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        patches = [mock.patch.object(common, "CONFIG_PATH", os.path.join(self.tmp, "config.json")),
                   mock.patch.object(self.qapp, "quit"),
                   mock.patch.object(water, "user_idle_seconds", return_value=0.0),
                   mock.patch("workout.Announcer.beep")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = main.PetApp(self.qapp)
        self.pet = self.app.pet
        self.pet.timer.stop()
        self.addCleanup(self.pet.timer.stop)

    def ticks(self, n, until=None):
        for _ in range(n):
            self.pet.tick()
            if self.pet.shatter is not None and not self.pet.shatter.done:
                self.pet.shatter.advance(0.02)
            if until and until():
                return True
        return False

    def test_menu_has_water_entries(self):
        menu = self.pet._build_menu()
        wm = next(a.menu() for a in menu.actions() if a.text() == "💧 喝水提醒")
        texts = [a.text() for a in wm.actions()]
        self.assertTrue(any(t.startswith("我喝了") for t in texts), texts)
        self.assertIn("预览", texts)

    def test_level_one_then_click_drinks(self):
        self.pet.water_preview(1)
        self.assertEqual(self.pet.water.phase, "remind")
        self.assertTrue(self.pet.clip.active or self.pet.expr.active)
        self.pet._on_single_click()
        self.assertEqual(self.pet.water.phase, "wait")
        self.assertEqual(self.pet.water.cups(), 1)
        self.assertIn("1/8", self.pet.bubble_text)

    def test_level_two_walks_to_cursor_then_demo(self):
        self.pet.water_preview(2)
        self.assertIsNotNone(self.pet.water_walk)
        self.assertTrue(self.ticks(2000, lambda: self.pet.water_walk is None))
        self.assertTrue(self.pet.clip.active or self.pet.expr.active)

    def test_finale_throw_leave_away_return(self):
        pet = self.pet
        pet.water_preview(4)
        self.assertEqual(pet.water.phase, "finale")
        self.assertTrue(self.ticks(3000, lambda: pet.shatter is not None), "水瓶要出手")
        self.assertTrue(self.ticks(5000, lambda: pet.water_fx == "angry"), "演完转身气鼓鼓走")
        self.assertTrue(self.ticks(5000, lambda: not pet.isVisible()), "走出屏幕藏起来")
        self.assertEqual(pet.water.phase, "away")
        self.assertIn("不可用", self.app.tray.toolTip())
        self.assertTrue(self.ticks(1000, lambda: pet.isVisible()), "预览只离开 8 秒")
        self.assertEqual(pet.water.phase, "back")
        self.assertTrue(self.ticks(5000, lambda: pet.water.phase == "wait"), "走回来演完返场")
        self.assertGreater(pet.water.cold, 0, "没喝：抠门模式")
        pet._on_single_click()
        self.assertIn(pet.bubble_text, water.LINES["cold"])
        self.assertEqual(self.app.tray.toolTip(), common.APP_NAME)

    def test_drink_during_finale_makes_up(self):
        pet = self.pet
        pet.water_preview(4)
        pet._on_single_click()
        self.assertTrue(pet.water.drank_away)
        self.assertTrue(self.ticks(15000, lambda: pet.water.phase == "wait"))
        self.assertEqual(pet.water.cold, 0)


if __name__ == "__main__":
    unittest.main()
