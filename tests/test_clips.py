"""动作动画播放器测试：真解码素材，以及解码出错时安全降级。需要 PySide6 和 PyAV，没装就跳过。
运行：python -m unittest discover tests"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import clips
    from clips import ClipPlayer
except ImportError as e:   # 没装 PySide6
    clips = None
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = "" if clips.AVAILABLE else "没装 PyAV 或素材缺失"


@unittest.skipIf(_SKIP, _SKIP)
class ClipMenuTest(unittest.TestCase):
    def test_menu_plays_named_clip(self):
        """点菜单里哪一段就播哪一段（triggered 带的 checked 不能顶掉名字）。"""
        from PySide6.QtWidgets import QApplication, QMenu
        app = QApplication.instance() or QApplication([])
        menu = QMenu()
        played = []
        clips.add_menus(menu, played.append)
        subs = menu.findChildren(QMenu)
        self.assertEqual([s.title() for s in subs], [c for c, _ in clips.CATEGORIES])
        for sub, (_, names) in zip(subs, clips.CATEGORIES):
            for act, name in zip(sub.actions(), names):
                self.assertEqual(act.text(), clips.label(name))
                played.clear()
                act.trigger()
                self.assertEqual(played, [name])
        self.assertIsNotNone(app)


@unittest.skipIf(_SKIP, _SKIP)
class ClipPlayerTest(unittest.TestCase):
    def setUp(self):
        self.NAME = next(iter(clips.CLIPS))
        self.info = clips.CLIPS[self.NAME]

    def test_play_through(self):
        """真打开一段，第一帧按外框裁好，往后推进能换帧，播完自己停。"""
        p = ClipPlayer()
        self.assertEqual(p.start(self.NAME), self.NAME)
        x, y, w, h = self.info["crop"]
        self.assertEqual((p.image.width(), p.image.height()), (w, h))
        first = p.image
        step = 1.0 / self.info["fps"]
        for _ in range(5):
            p.update(step)
        self.assertTrue(p.active)
        self.assertGreaterEqual(p._decoded, 5)
        self.assertIsNot(p.image, first)
        while p.active:
            p.update(step * 10)
        self.assertIsNone(p.image)
        self.assertIsNone(p._container)

    def test_every_clip_decodes(self):
        """清单里每段都能真的解出第一帧，不只是文件存在。"""
        p = ClipPlayer()
        for name in clips.CLIPS:
            self.assertEqual(p.start(name), name, name)
            self.assertFalse(p.image.isNull(), name)
        p.stop()

    def test_unreadable_file(self):
        """文件损坏：start 返回 None，不抛异常。"""
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, self.info["file"]), "wb") as f:
                f.write(b"\x1aE\xdf\xa3 not really a webm" * 64)
            with mock.patch.object(clips, "CLIP_DIR", tmp):
                p = ClipPlayer()
                self.assertIsNone(p.start(self.NAME))
                self.assertFalse(p.active)
        finally:
            shutil.rmtree(tmp)

    def test_truncated_file(self):
        """下载不完整：能播多少播多少，提前结束，不抛异常。"""
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(clips.CLIP_DIR, self.info["file"])
            with open(src, "rb") as f:
                data = f.read()
            with open(os.path.join(tmp, self.info["file"]), "wb") as f:
                f.write(data[:len(data) // 3])
            with mock.patch.object(clips, "CLIP_DIR", tmp):
                p = ClipPlayer()
                p.start(self.NAME)
                for _ in range(10 * self.info["frames"]):
                    if not p.active:
                        break
                    p.update(1.0 / self.info["fps"])
                self.assertFalse(p.active)
                self.assertIsNone(p._container)
        finally:
            shutil.rmtree(tmp)

    def test_first_decode_error(self):
        """解码器第一帧就报错：start 返回 None，容器已关。"""
        class BrokenDecoder:
            def decode(self, pkt):
                raise RuntimeError("boom")
        fake_av = mock.Mock(open=clips.av.open)   # 老版本 PyAV 的扩展类型不能直接 patch 方法
        fake_av.CodecContext.create.return_value = BrokenDecoder()
        with mock.patch.object(clips, "av", fake_av):
            p = ClipPlayer()
            self.assertIsNone(p.start(self.NAME))
        self.assertFalse(p.active)
        self.assertIsNone(p._container)

    def test_decode_error_while_playing(self):
        """播到一半解码出错：停掉这段，update 不往外抛。"""
        p = ClipPlayer()
        p.start(self.NAME)

        def broken():
            raise RuntimeError("boom")
            yield
        p._frames = broken()
        p.update(1.0 / self.info["fps"])
        self.assertFalse(p.active)
        self.assertIsNone(p._container)
        p.update(1.0 / self.info["fps"])   # 停了以后再推进也没事

    def test_reformat_error_while_playing(self):
        """帧转换出错同样降级。"""
        p = ClipPlayer()
        p.start(self.NAME)

        class BadFrame:
            def reformat(self, **kw):
                raise ValueError("bad frame")
        p._frames = iter([BadFrame()] * 3)
        p.update(1.0 / self.info["fps"])
        self.assertFalse(p.active)

    def test_close_error(self):
        """关容器出错也不影响停下来。"""
        p = ClipPlayer()
        p.start(self.NAME)
        real = p._container
        p._container = mock.Mock(close=mock.Mock(side_effect=OSError("close failed")))
        p.stop()
        real.close()
        self.assertFalse(p.active)


@unittest.skipIf(_SKIP, _SKIP)
class PetClipFallbackTest(unittest.TestCase):
    """桌宠播着撑大窗口的动画 A，再切到打不开的 B：窗口缩回三视图，脚底不动。"""

    def setUp(self):
        from PySide6.QtWidgets import QApplication
        from common import DEFAULT_CFG
        from pet import PetWindow
        self.app = QApplication.instance() or QApplication([])
        self.pet = PetWindow(mock.Mock(), dict(DEFAULT_CFG))
        self.pet.timer.stop()   # 不让 tick 在测试中途推进动画
        self.pet.move(400, 300)
        self.base = self.pet.size()
        widest = max(clips.CLIPS, key=lambda n: clips.CLIPS[n]["crop"][2])
        self.wide, self.broken = widest, next(n for n in clips.CLIPS if n != widest)
        self.tmp = tempfile.mkdtemp()
        for name, info in clips.CLIPS.items():
            src = os.path.join(clips.CLIP_DIR, info["file"])
            dst = os.path.join(self.tmp, info["file"])
            if name == self.broken:
                with open(dst, "wb") as f:
                    f.write(b"not a webm" * 64)
            else:
                os.symlink(src, dst)
        patcher = mock.patch.object(clips, "CLIP_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.pet.clip.stop()
        self.pet.close()
        shutil.rmtree(self.tmp)

    def test_failed_switch_restores_window(self):
        pet = self.pet
        self.assertTrue(pet.play_clip(self.wide))
        self.assertGreater(pet.width(), self.base.width())
        foot = pet.foot_global()
        self.assertFalse(pet.play_clip(self.broken))
        self.assertFalse(pet.clip.active)
        self.assertEqual(pet.size(), self.base)
        self.assertEqual(pet.foot_global(), foot)

    def test_random_falls_back_to_expression(self):
        pet = self.pet
        choice = clips.random.choice   # 只把「随机抽动画」钉到打不开的那段，抽表情照旧

        def pick(seq):
            return self.broken if self.broken in seq else choice(seq)
        with mock.patch("pet.random.random", return_value=0.0), \
                mock.patch("random.choice", side_effect=pick):
            pet.play_random()
        self.assertFalse(pet.clip.active)
        self.assertTrue(pet.expr.active)
        self.assertEqual(pet.size(), self.base)


if __name__ == "__main__":
    unittest.main()
