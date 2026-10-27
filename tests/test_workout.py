"""健身跟练测试：计划校验、时间线展开、计时推进、偷懒、素材齐全、跟练动画怎么接，以及桌宠里从开始练到练完。
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
        """每个动作播一遍，用到的帧正好是它时间轴里的那些；叠化时也总有一张是实的，人不会变半透明。"""
        for key, mv in workout.MOVES.items():
            p = WorkoutPlayer(workout.single_move_plan(key, 12), prep=False, slack=False)
            seen = set()
            for _ in range(600):
                p.update(0.02)
                if p.finished:
                    break
                layers = p.pose()[0]
                self.assertAlmostEqual(max(a for _, _, a in layers), 1.0, places=6)
                seen |= {f for f, _, _ in layers}
            self.assertEqual(seen, mv.frames, key)


# 假的片段长度（秒）：没写的都是 5 秒
FAKE_DUR = {"bridge_enter": 4, "bridge_exit": 4, "wall_sit_enter": 4, "wall_sit_exit": 4,
            "drink": 6, "collapse": 8, **{n: 7 for n in ("lazy_phone", "lazy_think", "lazy_flop", "lazy_fish",
                                                        "lazy_fake")}, "lazy_rice": 8, "lazy_tailnap": 8,
            "lazy_doze": 6}


class FakeClipPlayer:
    """不解码的 ClipPlayer：只记播了哪些段、按 FAKE_DUR 走完。"""
    def __init__(self, lib):
        self.name, self.t, self.dur, self.log = None, 0.0, 0.0, lib.log

    @property
    def active(self):
        return self.name is not None

    def start(self, name, fades=(True, True)):
        self.log.fades[name] = fades
        if name == self.log.broken:
            return None
        self.name, self.t, self.dur = name, 0.0, FAKE_DUR.get(name, 5)
        self.log.append(name)
        return name

    def update(self, dt):
        self.t += dt
        if self.t >= self.dur:
            self.name = None


class _Log(list):
    broken = None

    def __init__(self):
        super().__init__()
        self.fades = {}


@unittest.skipIf(_SKIP, _SKIP)
class ClipModeTest(unittest.TestCase):
    """跟练动画怎么接：换姿势先起身再躺下、偷懒只在一下练完回到站姿时开始、练完欢呼再瘫倒，片段从不半路切走。"""

    def setUp(self):
        self.log = _Log()
        lib = mock.Mock(log=self.log)
        for p in (mock.patch.object(workout, "clip_library", lambda: lib),
                  mock.patch.object(workout.clip_lib, "ClipPlayer", FakeClipPlayer)):
            p.start()
            self.addCleanup(p.stop)

    def player(self, steps, rest=0, prep=False, slack=False, **kw):
        plan = validate_plan({"rest": rest, "steps": steps, **kw})
        return WorkoutPlayer(plan, prep=prep, slack=slack, use_clips=True)

    def test_standing_move_loops_whole_clips(self):
        p = self.player([{"move": "squat", "secs": 12}])
        self.assertIsNotNone(p.clips)
        run(p, 12.1)
        self.assertTrue(p.finished)
        self.assertEqual(self.log, ["squat"] * 3)      # 第三下 10 秒开始，过了 12 秒也要练完这一下
        self.assertFalse(p.done)                       # 动作预览：等手上这一下练完回到站姿才结束
        run(p, 3)
        self.assertTrue(p.done)

    def test_floor_move_gets_down_and_up(self):
        p = self.player([{"move": "glute_bridge", "secs": 10}, {"move": "glute_bridge_single", "secs": 10},
                         {"move": "squat", "secs": 10}], rest=0)
        run(p, 30)
        self.assertEqual(self.log[:4], ["bridge_enter", "bridge_loop", "bridge_loop", "bridge_single_loop"])
        i = self.log.index("bridge_exit")
        self.assertEqual(self.log[i + 1], "squat")     # 起身之后才去站着练
        self.assertNotIn("bridge_enter", self.log[1:])  # 两种臀桥在同一个姿势上接着练，不起身
        # 只在站姿那头和正面图叠化，躺着的那头叠化会叠出个站着的虚影
        self.assertEqual(self.log.fades, {"bridge_enter": (True, False), "bridge_loop": (False, False),
                                          "bridge_single_loop": (False, False), "bridge_exit": (False, True),
                                          "squat": (True, True)})

    def test_rest_pants_then_drinks(self):
        p = self.player([{"move": "wall_sit", "secs": 30}, {"move": "squat", "secs": 5}], rest=15)
        run(p, 30 + 15)
        i = self.log.index("wall_sit_exit")
        self.assertEqual(self.log[i + 1:i + 3], ["tired", "drink"])

    def test_left_side_mirrors_standing_only(self):
        p = self.player([{"move": "curtsy_lunge", "secs": 5, "side": "left"}])
        run(p, 0.1)
        self.assertTrue(p.clips.mirror)
        p = self.player([{"move": "glute_bridge_single", "secs": 10, "side": "left"}])
        run(p, 6)
        self.assertEqual(p.clips.name, "bridge_single_loop")
        self.assertFalse(p.clips.mirror)               # 躺着的循环段翻过来就和进入那段接不上了

    def test_slack_waits_for_neutral_then_caught(self):
        with mock.patch.object(workout.random, "random", return_value=0.0), \
                mock.patch.object(workout.random, "uniform", return_value=0.3):
            p = self.player([{"move": "squat", "secs": 40}], slack=True)
        self.assertAlmostEqual(p.slack_at, 12)
        ev = run(p, 12.5)
        self.assertFalse(p.slacking)                   # 12 秒时第三下还没练完
        self.assertEqual(self.log, ["squat"] * 3)
        ev += run(p, 3)
        self.assertTrue(p.slacking)
        lazy = self.log[-1]
        self.assertIn(lazy, workout.LAZY)
        self.assertIn(("say", workout.LAZY[lazy][0], True), ev)
        ev = run(p, FAKE_DUR[lazy] + 0.1)
        self.assertIn(("say", workout.LAZY[lazy][1], False), ev)
        self.assertFalse(p.slacking)
        self.assertEqual(self.log[-1], "squat")        # 偷懒回到站姿，接着练

    def test_no_slack_on_floor_or_short_moves(self):
        with mock.patch.object(workout.random, "random", return_value=0.0):
            p = self.player([{"move": "glute_bridge", "secs": 40}, {"move": "squat", "secs": 15}], slack=True)
            self.assertIsNone(p.slack_at)
            run(p, 40.1)
            self.assertIsNone(p.slack_at)

    def test_lazy_never_repeats_back_to_back(self):
        d = workout.ClipDirector(mock.Mock(log=self.log))
        picks = []
        for _ in range(30):
            d.update(0.0, None, "squat", lazy=True)
            picks.append(d.name)
            d.update(100.0, None, None)
        self.assertTrue(all(a != b for a, b in zip(picks, picks[1:])))

    def test_finish_cheers_then_collapses(self):
        p = self.player([{"move": "glute_bridge", "secs": 6}], prep=True)
        ev = run(p, workout.PREP_SECS + 6.1)
        self.assertTrue(p.finished)
        ev += run(p, 30)
        self.assertTrue(p.done)
        self.assertEqual(self.log[-3:], ["bridge_exit", "cheer", "collapse"])
        self.assertIn(("say", workout.MOVES["collapse"].cue, False), ev)

    def test_pause_pants_and_skip_drops_queue(self):
        p = self.player([{"move": "squat", "secs": 30}, {"move": "squat", "secs": 30}], rest=15)
        run(p, 1)
        p.toggle_pause()
        run(p, 10)
        self.assertEqual(self.log, ["squat", "tired"])
        p.toggle_pause()
        run(p, 30)
        self.assertEqual(p.seg.kind, "rest")
        p.skip()                                       # 跳过休息：排着的喘气 / 喝水不播了
        self.assertEqual(p.clips.queue, [])

    def test_broken_clip_falls_back_to_frames(self):
        self.log.broken = "squat"
        p = self.player([{"move": "squat", "secs": 5}])
        run(p, 0.1)
        self.assertIsNone(p.clips)
        self.assertEqual(p.pose()[0][0][0], "stand")


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


class _PetBase(unittest.TestCase):
    CLIPS = False   # False：只测姿势帧那套，把跟练动画关掉

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
        if not self.CLIPS:
            c = mock.patch.object(workout, "clip_library", lambda: None)
            c.start()
            self.addCleanup(c.stop)
        # 不真的出声
        b = mock.patch.object(workout.Announcer, "beep")
        b.start()
        self.addCleanup(b.stop)

    def tick(self, secs):
        for _ in range(int(secs * 1000 / 20)):
            self.pet.tick()
            if self.pet.workout is None:
                break


@unittest.skipIf(_SKIP, _SKIP)
class PetWorkoutTest(_PetBase):
    def test_menu_has_workout(self):
        texts = [a.text() for a in self.pet._build_menu().actions()]
        self.assertIn("🏋️ 跟练", texts)

    def test_full_workout_in_pet(self):
        pet = self.pet
        plan = validate_plan({"rest": 2, "steps": [{"move": "squat_open_close", "secs": 3},
                                                   {"move": "glute_bridge_single", "secs": 3, "side": "left"}]})
        h0 = pet.height()
        pet.start_workout(plan)
        self.assertTrue(pet.workout.show_timer)
        self.assertGreaterEqual(pet.width(), pet.win_w)
        pet.grab()                          # 画一帧（含右上角倒计时）不报错
        self.tick(workout.PREP_SECS + 5.5)
        self.assertEqual(pet.workout.seg.move, "glute_bridge_single")
        pet.grab()
        pet._on_single_click()              # 跟练时单击是暂停
        self.assertTrue(pet.workout.paused)
        self.assertFalse(pet.function_panel.isVisible())
        pet.grab()
        pet.workout_pause()
        self.assertFalse(pet.workout.paused)
        pet.play_expression("happy")       # 练着的时候不插表情
        self.assertFalse(pet.expr.active)
        self.tick(4 + workout.FINISH_SECS + 1)
        self.assertIsNone(pet.workout)
        self.assertEqual(pet.height(), h0)

    def test_stop_midway_and_preview(self):
        pet = self.pet
        pet.preview_move("wall_sit")
        self.assertFalse(pet.workout.show_timer)   # 预览不显示倒计时
        self.tick(1)
        pet.grab()
        pet.stop_workout()
        self.assertIsNone(pet.workout)
        pet.function_panel.hide()



@unittest.skipIf(_SKIP or workout.clip_library() is None, _SKIP or "没装 PyAV 或跟练动画缺失")
class PetClipWorkoutTest(_PetBase):
    """真解码跟练动画：桌宠里从开始练到练完，片段之间画正面图，片段按正面图的大小摆。"""
    CLIPS = True

    def test_clip_workout_in_pet(self):
        pet = self.pet
        plan = validate_plan({"rest": 3, "steps": [{"move": "squat", "secs": 6},
                                                   {"move": "curtsy_lunge", "secs": 6, "side": "left"}]})
        h0 = pet.height()
        pet.start_workout(plan)
        self.assertIsNotNone(pet.workout.clips)
        self.assertGreater(pet.height(), h0)            # 瘫倒、躺平比人宽，窗口撑开
        pet.grab()                                       # 准备时画正面图
        self.tick(workout.PREP_SECS + 0.5)
        d = pet.workout.clips
        self.assertEqual(d.name, "squat")
        self.assertIsNotNone(d.player.image)
        # 首帧和正面图一样高：按 ref 缩放后人物外框不超出正面图太多
        left, right, up, down = d.player.extents(pet.cur_h)
        self.assertLess(up, pet.cur_h * 1.6)
        pet.grab()
        self.tick(60)
        self.assertIsNone(pet.workout)                   # 练完、欢呼、瘫倒、爬起来，结束
        self.assertEqual(pet.height(), h0)


if __name__ == "__main__":
    unittest.main()
