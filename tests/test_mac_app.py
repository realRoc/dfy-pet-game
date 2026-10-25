"""macOS 启动壳 relaunch_in_mac_app 的测试：文件操作在临时目录里做，execve 用 mock 拦下。"""
import os
import plistlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import common


class RelaunchInMacAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        # 假的 framework 版 Python：base_prefix/Resources/Python.app/Contents/MacOS/Python
        self.base = os.path.join(self.tmp, "framework")
        self.src = os.path.join(self.base, "Resources", "Python.app", "Contents", "MacOS", "Python")
        os.makedirs(os.path.dirname(self.src))
        with open(self.src, "wb") as f:
            f.write(b"interpreter v1")
        self.app_dir = os.path.join(self.tmp, "repo")
        os.makedirs(self.app_dir)
        self.contents = os.path.join(self.app_dir, "build", f"{common.APP_NAME}.app", "Contents")
        self.exe = os.path.join(self.contents, "MacOS", common.APP_NAME)
        self.plist = os.path.join(self.contents, "Info.plist")

        env = {k: v for k, v in os.environ.items() if k not in ("DFY_IN_APP", "__PYVENV_LAUNCHER__")}
        for p in (
            mock.patch.object(common, "IS_MAC", True),
            mock.patch.object(common, "APP_DIR", self.app_dir),
            mock.patch.object(sys, "base_prefix", self.base),
            mock.patch.object(sys, "executable", "/venv/bin/python"),
            mock.patch.object(sys, "argv", ["main.py", "--flag"]),
            mock.patch.dict(os.environ, env, clear=True),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.execve = mock.patch("common.os.execve").start()
        self.addCleanup(mock.patch.stopall)

    def read_plist(self):
        with open(self.plist, "rb") as f:
            return plistlib.load(f)

    def assert_skipped(self):
        common.relaunch_in_mac_app()
        self.execve.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.app_dir, "build")))

    def test_skip_when_not_mac(self):
        with mock.patch.object(common, "IS_MAC", False):
            self.assert_skipped()

    def test_skip_when_frozen(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assert_skipped()

    def test_skip_when_already_relaunched(self):
        os.environ["DFY_IN_APP"] = "1"
        self.assert_skipped()

    def test_skip_without_framework_python(self):
        os.remove(self.src)
        self.assert_skipped()

    def test_fresh_build_and_execve(self):
        common.relaunch_in_mac_app()
        with open(self.exe, "rb") as f:
            self.assertEqual(f.read(), b"interpreter v1")
        info = self.read_plist()
        self.assertEqual(info["CFBundleName"], common.APP_NAME)
        self.assertEqual(info["CFBundleExecutable"], common.APP_NAME)
        self.execve.assert_called_once()
        path, argv, env = self.execve.call_args.args
        self.assertEqual(path, self.exe)
        self.assertEqual(argv, [self.exe, os.path.abspath("main.py"), "--flag"])
        self.assertEqual(env["DFY_IN_APP"], "1")
        self.assertEqual(env["__PYVENV_LAUNCHER__"], "/venv/bin/python")

    def test_recover_missing_plist(self):
        # 上次复制完解释器就被打断：exe 和源一样，但没有 Info.plist
        os.makedirs(os.path.dirname(self.exe))
        shutil.copy2(self.src, self.exe)
        common.relaunch_in_mac_app()
        self.assertEqual(self.read_plist()["CFBundleName"], common.APP_NAME)
        self.execve.assert_called_once()

    def test_recover_corrupt_plist(self):
        os.makedirs(os.path.dirname(self.exe))
        shutil.copy2(self.src, self.exe)
        with open(self.plist, "wb") as f:
            f.write(b"<?xml half written")
        common.relaunch_in_mac_app()
        self.assertEqual(self.read_plist()["CFBundleName"], common.APP_NAME)

    def test_replace_stale_plist(self):
        os.makedirs(os.path.dirname(self.exe))
        shutil.copy2(self.src, self.exe)
        with open(self.plist, "wb") as f:
            plistlib.dump({"CFBundleName": "大肥鱼飞行棋"}, f)
        common.relaunch_in_mac_app()
        self.assertEqual(self.read_plist()["CFBundleName"], common.APP_NAME)

    def test_recopy_when_interpreter_changes(self):
        common.relaunch_in_mac_app()
        with open(self.src, "wb") as f:
            f.write(b"interpreter v2")
        common.relaunch_in_mac_app()
        with open(self.exe, "rb") as f:
            self.assertEqual(f.read(), b"interpreter v2")

    def test_execve_failure_falls_back(self):
        self.execve.side_effect = OSError("exec format error")
        with mock.patch("builtins.print") as log:
            common.relaunch_in_mac_app()  # 不抛异常，调用方继续用 Python 运行
        self.execve.assert_called_once()
        log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
