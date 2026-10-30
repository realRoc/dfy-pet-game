"""角色包：清单字段齐全、引用的文件都在；换一个只有立绘的包时，引擎照样起得来，缺的功能按降级走。
运行：python -m unittest discover tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import character

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PackManifestTest(unittest.TestCase):
    def test_every_pack_is_valid(self):
        packs = character.available()
        self.assertIn(character.DEFAULT_ID, packs)
        for cid in packs:
            errors, _ = character.validate(character.find(cid))
            self.assertEqual(errors, [], cid)

    def test_default_pack_has_everything(self):
        """大肥鱼包是全功能的：四类动画、全部台词类别都有，不该有降级提醒。"""
        errors, warnings = character.validate(character.find(character.DEFAULT_ID))
        self.assertEqual((errors, warnings), ([], []))

    def test_default_pack_is_non_commercial(self):
        c = character.load(character.DEFAULT_ID)
        self.assertFalse(c.commercial)
        self.assertEqual(c.license["spdx"], "CC-BY-NC-SA-4.0")
        self.assertTrue(c.license["attribution"])

    def test_validate_reports_missing_fields_and_files(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "character.json"), "w", encoding="utf-8") as f:
            json.dump({"format": 1, "id": "x", "name": "X", "sprites": {"front": "nope.png"},
                       "animations": {"water": "water"}}, f)
        errors, _ = character.validate(tmp)
        joined = "\n".join(errors)
        self.assertIn("license.spdx", joined)
        self.assertIn("立绘 front 不存在", joined)
        self.assertIn("动画 water 缺清单", joined)

    def test_lines_fallback(self):
        c = character.load(character.DEFAULT_ID)
        self.assertEqual(c.lines("no.such.kind", ["默认"]), ["默认"])
        self.assertEqual(c.lines("no.such.kind"), ["……"])
        self.assertIn("{n}", c.lines("water.cheers")[0])


def _minimal_pack(root, cid="bare"):
    """只有三视图和图标、没有动画和台词的包，立绘借大肥鱼的。"""
    src = character.load(character.DEFAULT_ID)
    d = os.path.join(root, cid)
    os.makedirs(os.path.join(d, "sprites"))
    for view in ("front", "side", "back", "icon"):
        shutil.copy(src.sprite(view), os.path.join(d, "sprites", f"{view}.png"))
    manifest = {
        "format": 1, "id": cid, "name": "测试角色",
        "license": {"spdx": "LicenseRef-Test", "commercial": True, "attribution": ["test"]},
        "sprites": {"height": src.sprite_h, "front": "sprites/front.png", "side": "sprites/side.png",
                    "back": "sprites/back.png", "side_faces": "right", "icon": "sprites/icon.png"},
        "persona": {"chat_system": "你是测试角色。"},
    }
    with open(os.path.join(d, "character.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    return d


PROBE = r"""
import json, os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
app = QApplication([])
import common, clips, workout, water, expressions, pet
print(json.dumps({
    "app": common.APP_NAME, "clips": clips.AVAILABLE, "workout": workout.available(),
    "water": water.library() is not None, "expr": expressions.EXPRESSIONS["happy"][2],
    "idle": pet.LINES, "cue": workout.MOVES["cheer"].cue, "lazy": len(workout.LAZY),
    "sprites": sorted(common.load_sprites(100)), "cold": water.line("cold"),
}, ensure_ascii=False))
"""


class BarePackEngineTest(unittest.TestCase):
    """引擎按清单加载：缺的动画、台词都有降级，模块都能导入。换包靠环境变量，所以起一个子进程。"""

    def test_engine_runs_on_bare_pack(self):
        try:
            import PySide6  # noqa: F401
        except ImportError:
            self.skipTest("没装 PySide6")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        pack = _minimal_pack(tmp)
        self.assertEqual(character.validate(pack)[0], [])
        env = dict(os.environ, DFY_CHARACTER=pack, QT_QPA_PLATFORM="offscreen")
        out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        r = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(r["app"], "测试角色")
        self.assertFalse(r["clips"])
        self.assertFalse(r["workout"])
        self.assertFalse(r["water"])
        self.assertEqual(r["expr"], ["（开心）"])
        self.assertEqual(r["idle"], ["……"])
        self.assertEqual(r["cue"], "欢呼")
        self.assertEqual(r["lazy"], 0)
        self.assertEqual(r["sprites"], ["侧面", "正面", "背面"])
        self.assertEqual(r["cold"], "嗯。")


if __name__ == "__main__":
    unittest.main()
