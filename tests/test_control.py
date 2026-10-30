"""dsh 插件指挥桌宠的 stdin 通道：解析每行 JSON，在主线程上让桌宠说话 / 做表情，管道断了就退出。
需要 PySide6，没装就跳过。运行：python -m unittest discover tests"""
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    import common
    import control
    import main
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


@unittest.skipIf(_SKIP, _SKIP)
class ParseTest(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(control.parse('{"cmd": "say", "text": " 你好 "}'), ("say", "你好"))
        self.assertEqual(control.parse('{"cmd": "emote", "key": "shy"}'), ("emote", "shy"))
        self.assertEqual(control.parse('{"cmd": "emote", "key": "nope"}'), ("emote", None))
        self.assertEqual(control.parse('{"cmd": "clip"}'), ("clip", None))
        self.assertEqual(control.parse('{"cmd": "show"}'), ("show", None))

    def test_long_text_is_cut(self):
        cmd, text = control.parse('{"cmd": "say", "text": "%s"}' % ("鱼" * 100))
        self.assertEqual(len(text), control.SAY_MAX)

    def test_garbage_is_ignored(self):
        for line in ("", "not json", "[1]", '{"cmd": "rm -rf"}', '{"cmd": "say", "text": ""}'):
            self.assertIsNone(control.parse(line), line)


@unittest.skipIf(_SKIP, _SKIP)
class AttachTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for p in (mock.patch.object(common, "CONFIG_PATH", os.path.join(self.tmp, "config.json")),
                  mock.patch.object(self.qapp, "quit")):
            p.start()
            self.addCleanup(p.stop)
        self.app = main.PetApp(self.qapp)
        self.addCleanup(self.app.pet.timer.stop)

    def run_lines(self, *lines):
        quit_ = mock.patch.object(self.app, "quit").start()
        self.addCleanup(mock.patch.stopall)
        ctl = control.attach(self.app, io.StringIO("".join(l + "\n" for l in lines)))
        # 读线程发的信号排队到主线程，转几圈事件循环让它们执行完
        for _ in range(50):
            QCoreApplication.processEvents()
            if quit_.called:
                break
        return ctl, quit_

    def test_say_and_emote_then_quit_on_eof(self):
        pet = self.app.pet
        with mock.patch.object(pet, "play_expression") as emote:
            _, quit_ = self.run_lines('{"cmd": "say", "text": "QQ 里有人夸我"}', '{"cmd": "emote", "key": "love"}')
        self.assertEqual(pet.bubble_text, "QQ 里有人夸我")
        emote.assert_called_once_with("love")
        quit_.assert_called_once()

    def test_show_brings_hidden_pet_back(self):
        self.app.toggle_visible()
        self.assertFalse(self.app.pet.isVisible())
        self.run_lines('{"cmd": "show"}')
        self.assertTrue(self.app.pet.isVisible())


if __name__ == "__main__":
    unittest.main()
