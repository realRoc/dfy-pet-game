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


if __name__ == "__main__":
    unittest.main()
