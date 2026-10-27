"""健身跟练测试：计划校验、时间线展开、计时推进、偷懒、素材齐全，以及桌宠里从开始练到练完。
需要 PySide6，没装就跳过。运行：python -m unittest discover tests"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    import common
    import workout
    from workout import WorkoutPlayer, PlanError, validate_plan, build_timeline
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


def run(player, secs, dt=0.02):
    events = []
    for _ in range(int(round(secs / dt))):
        events += player.update(dt)
    return events


@unittest.skipIf(_SKIP, _SKIP)
class PlanTest(unittest.TestCase):
    def test_builtin_plans_load(self):
        plans, errors = workout.load_plans()
        self.assertEqual(errors, [])
        self.assertIn("kris_legs_6min", dict(plans))

    def test_kris_timeline(self):
        """Kris 原片：6 个动作每个 45 秒（屈膝礼左右各 22、臀桥三组各 15），动作之间歇 15 秒。"""
        plan = dict(workout.load_plans()[0])["kris_legs_6min"]
        segs = build_timeline(plan)
        work = [s for s in segs if s.kind == "work"]
        self.assertEqual([s.label for s in work][:3], ["开合深蹲", "屈膝礼弓步（右）", "屈膝礼弓步（左）"])
        self.assertEqual(sum(s.secs for s in work), 269)
        self.assertEqual([s.secs for s in segs if s.kind == "rest"], [15] * 5)
        self.assertEqual(segs[0].kind, "prep")
        self.assertEqual(segs[-1].kind, "work")   # 最后一个动作后面不休息

    def test_rounds_insert_round_rest(self):
        plan = validate_plan({"rest": 10, "round_rest": 30,
                              "steps": [{"move": "squat", "secs": 20}, {"move": "lunge", "secs": 20}]})
        segs = build_timeline(plan, rounds=2, prep=False)
        self.assertEqual([(s.kind, s.secs) for s in segs],
                         [("work", 20), ("rest", 10), ("work", 20), ("rest", 30),
                          ("work", 20), ("rest", 10), ("work", 20)])
        self.assertEqual([s.round_no for s in segs if s.kind == "work"], [1, 1, 2, 2])

    def test_validate_rejects_bad_plans(self):
        for bad in ({}, {"steps": []}, {"steps": [{"move": "fly", "secs": 10}]},
                    {"steps": [{"move": "squat", "secs": 0}]}, {"steps": [{"move": "squat", "secs": "10"}]},
                    {"steps": [{"move": "squat", "secs": 10, "side": "up"}]}, {"rest": -1, "steps": [{"move": "squat", "secs": 1}]}):
            with self.assertRaises(PlanError, msg=bad):
                validate_plan(bad)

    def test_user_plan_overrides_and_bad_file_reported(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "kris_legs_6min.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "我的版本", "steps": [{"move": "squat", "secs": 30}]}, f)
        with open(os.path.join(tmp, "坏的.json"), "w", encoding="utf-8") as f:
            f.write("{")
        with mock.patch.object(workout, "USER_PLAN_DIR", tmp):
            plans, errors = workout.load_plans()
            self.assertEqual(dict(plans)["kris_legs_6min"]["name"], "我的版本")
            self.assertEqual(len(errors), 1)
            self.assertIn("坏的.json", errors[0])
            workout.ensure_user_plan_dir()
            example = [n for n in os.listdir(tmp) if n.endswith(".example")]
            self.assertEqual(len(example), 1)
            with open(os.path.join(tmp, example[0]), encoding="utf-8") as f:
                validate_plan(json.load(f))   # 示例本身是合法计划


@unittest.skipIf(_SKIP, _SKIP)
class PlayerTest(unittest.TestCase):
    def setUp(self):
        self.plan = validate_plan({"rest": 5, "steps": [{"move": "squat", "secs": 10},
                                                        {"move": "wall_sit", "secs": 8, "side": "left"}]})

    def test_runs_through_and_finishes(self):
        p = WorkoutPlayer(self.plan, prep=True, slack=False)
        self.assertEqual(p.total, workout.PREP_SECS + 10 + 5 + 8)
        ev = run(p, workout.PREP_SECS + 0.1)
        self.assertEqual(p.seg.kind, "work")
        self.assertEqual([e[1] for e in ev if e[0] == "beep"], ["tick", "tick", "tick", "go"])
        self.assertTrue(any(e[0] == "speak" and "深蹲" in e[1] for e in ev))
        run(p, 10)
        self.assertEqual(p.seg.kind, "rest")
        self.assertEqual(p.next_work().label, "靠墙静蹲（左）")
        run(p, 5 + 8)
        self.assertTrue(p.finished)
        self.assertAlmostEqual(p.elapsed, p.total)
        self.assertFalse(p.done)
        run(p, workout.FINISH_SECS)
        self.assertTrue(p.done)

    def test_pause_freezes_timer(self):
        p = WorkoutPlayer(self.plan, prep=False, slack=False)
        run(p, 2)
        p.toggle_pause()
        run(p, 5)
        self.assertAlmostEqual(p.t, 2, places=3)
        self.assertEqual(p.pose()[0][0][0], "tired")   # 暂停时弯腰喘气
        p.toggle_pause()
        run(p, 1)
        self.assertAlmostEqual(p.t, 3, places=3)

    def test_skip_and_back(self):
        p = WorkoutPlayer(self.plan, prep=False, slack=False)
        run(p, 4)
        p.back()                       # 过了 2 秒：回本段开头
        self.assertEqual((p.idx, p.t), (0, 0.0))
        p.skip()
        self.assertEqual(p.seg.kind, "rest")
        p.back()                       # 刚开始就按：回上一段
        self.assertEqual(p.idx, 0)
        p.skip(); p.skip(); p.skip()
        self.assertTrue(p.finished)

    def test_slack_then_caught(self):
        plan = validate_plan({"steps": [{"move": "squat", "secs": 40}]})
        with mock.patch.object(workout.random, "random", return_value=0.0), \
                mock.patch.object(workout.random, "uniform", return_value=0.5):
            p = WorkoutPlayer(plan, prep=False, slack=True)
        self.assertAlmostEqual(p.slack_at, 20)
        run(p, 20.1)
        self.assertTrue(p.slacking)
        self.assertEqual(p.pose()[0][0][0], "lazy_squat")
        ev = run(p, workout.SLACK_SECS)
        self.assertFalse(p.slacking)
        self.assertTrue(any(e[0] == "say" and e[1] in workout.CAUGHT_LINES for e in ev))

    def test_left_side_mirrors(self):
        p = WorkoutPlayer(self.plan, prep=False, slack=False)
        p.skip(); p.skip()
        layers = p.pose()[0]
        self.assertEqual(layers[0][:2], ("wall_sit", True))

    def test_poses_cycle_through_all_frames(self):
        """每个动作播一遍，用到的帧正好是它 cycle 里的那些，交叉淡化的不透明度加起来是 1。"""
        for key, mv in workout.MOVES.items():
            p = WorkoutPlayer(workout.single_move_plan(key, 12), prep=False, slack=False)
            seen = set()
            for _ in range(600):
                p.update(0.02)
                if p.finished:
                    break
                layers = p.pose()[0]
                self.assertAlmostEqual(sum(a for _, _, a in layers), 1.0, places=6)
                seen |= {f for f, _, _ in layers}
            self.assertEqual(seen, mv.frames, key)


@unittest.skipIf(_SKIP, _SKIP)
class FramesTest(unittest.TestCase):
    def test_all_frames_present(self):
        self.assertTrue(workout.available())
        for name, info in workout.manifest()["frames"].items():
            path = os.path.join(workout.FRAME_DIR, info["file"])
            self.assertTrue(os.path.isfile(path), path)

    def test_frame_cache_scales_to_pet_height(self):
        QApplication.instance() or QApplication([])
        cache = workout.FrameCache()
        pix, ax, ay, w, h = cache.get("stand", 238)
        self.assertAlmostEqual(ay, 238, delta=4)   # 站直的图按桌宠身高缩放
        left, right, up, down = cache.extents(["stand", "bridge_up"], 238)
        self.assertGreater(left + right, w)         # 躺着的图更宽，窗口要撑开


@unittest.skipIf(_SKIP, _SKIP)
class PetWorkoutTest(unittest.TestCase):
    def setUp(self):
        import main
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
        self.pet = self.app.pet
        self.addCleanup(self.pet.timer.stop)
        self.pet.timer.stop()
        self.pet.cfg["workout_voice"] = False
        # 不真的出声
        b = mock.patch.object(workout.Announcer, "beep")
        b.start()
        self.addCleanup(b.stop)

    def tick(self, secs):
        for _ in range(int(secs * 1000 / 20)):
            self.pet.tick()
            if self.pet.workout is None:
                break

    def test_menu_has_workout(self):
        texts = [a.text() for a in self.pet._build_menu().actions()]
        self.assertIn("🏋️ 跟练", texts)

    def test_full_workout_in_pet(self):
        pet = self.pet
        plan = validate_plan({"rest": 2, "steps": [{"move": "squat_open_close", "secs": 3},
                                                   {"move": "glute_bridge_single", "secs": 3, "side": "left"}]})
        h0 = pet.height()
        pet.start_workout(plan)
        self.assertTrue(pet.hud.isVisible())
        self.assertGreaterEqual(pet.width(), pet.win_w)
        pet.grab()                          # 画一帧不报错
        pet.hud.grab()
        self.tick(workout.PREP_SECS + 5.5)
        self.assertEqual(pet.workout.seg.move, "glute_bridge_single")
        pet.grab()
        pet.workout_pause()
        self.assertTrue(pet.workout.paused)
        pet.hud.grab()
        pet.workout_pause()
        pet.play_expression("happy")       # 练着的时候不插表情
        self.assertFalse(pet.expr.active)
        self.tick(4 + workout.FINISH_SECS + 1)
        self.assertIsNone(pet.workout)
        self.assertFalse(pet.hud.isVisible())
        self.assertEqual(pet.height(), h0)

    def test_stop_midway_and_preview(self):
        pet = self.pet
        pet.preview_move("wall_sit")
        self.assertFalse(pet.hud.isVisible())   # 预览不挂计时面板
        self.tick(1)
        pet.grab()
        pet.stop_workout()
        self.assertIsNone(pet.workout)
        pet.function_panel.hide()


if __name__ == "__main__":
    unittest.main()
