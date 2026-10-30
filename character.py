"""角色包：一个角色的立绘、动画、台词、人设和授权都放在 characters/<id>/ 里，character.json 是清单。

引擎只认清单，换角色只换包、不改代码。用哪个包看环境变量 DFY_CHARACTER（包名，或者包目录的绝对路径），
不设就是默认的 dafeiyu。清单格式见 characters/README.md。

包里缺某类动画时 anim_dir() 返回 None，对应功能按原来的降级逻辑走（没有跟练片段退回姿势帧，
姿势帧也没有就不出跟练；没有喝水片段就换成表情）。缺某类台词时用引擎给的默认台词。
这个模块不依赖 Qt，工具脚本和测试也能直接用。
"""
import json
import os
import sys

if getattr(sys, "frozen", False):
    _BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    _BUNDLE = os.path.dirname(os.path.abspath(__file__))
CHARACTERS_DIR = os.path.join(_BUNDLE, "characters")
DEFAULT_ID = "dafeiyu"
FORMAT = 1

VIEWS = ("front", "side", "back")
ANIMATIONS = ("actions", "workout", "workout_frames", "water")
# 清单里必须有的字段（点分路径）
REQUIRED = ["format", "id", "name", "license.spdx", "license.commercial", "license.attribution",
            "sprites.height", "sprites.front", "sprites.side", "sprites.back", "sprites.side_faces", "sprites.icon",
            "persona.chat_system"]
# 引擎会用到的台词类别；包里缺了用默认台词，validate() 只提醒不报错
LINE_KINDS = ["idle", "react", "inner", "drag", "food", "system", "expressions", "water", "workout"]


def _get(data, dotted):
    node = data
    for k in dotted.split("."):
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node


class Character:
    def __init__(self, directory):
        self.dir = os.path.abspath(directory)
        with open(os.path.join(self.dir, "character.json"), encoding="utf-8") as f:
            self.data = json.load(f)
        d = self.data
        self.id = d["id"]
        self.name = d["name"]
        self.license = d["license"]
        self.commercial = bool(d["license"].get("commercial"))
        self.sprite_h = d["sprites"]["height"]
        self.side_faces = d["sprites"].get("side_faces", "left")
        self.persona = d.get("persona", {})
        self.timing = d.get("timing", {})

    def path(self, rel):
        return os.path.join(self.dir, rel)

    def sprite(self, view):
        """front / side / back / icon 的图片路径。"""
        return self.path(self.data["sprites"][view])

    def anim_dir(self, kind):
        """某类动画的目录（actions / workout / workout_frames / water）；包里没有返回 None。"""
        rel = self.data.get("animations", {}).get(kind)
        return self.path(rel) if rel else None

    def lines(self, dotted, default=None):
        """取一类台词，比如 lines("idle")、lines("water.cheers")；包里没有就用 default。"""
        v = _get(self.data.get("lines", {}), dotted)
        if v in (None, [], {}):
            return default if default is not None else ["……"]
        return v


def find(cid):
    return cid if os.path.isabs(cid) else os.path.join(CHARACTERS_DIR, cid)


def available():
    """characters/ 里所有的包名。"""
    try:
        return sorted(n for n in os.listdir(CHARACTERS_DIR)
                      if os.path.isfile(os.path.join(CHARACTERS_DIR, n, "character.json")))
    except OSError:
        return []


def validate(directory):
    """检查一个包：必需字段齐不齐、引用的文件和目录在不在。返回 (错误, 提醒) 两个列表。"""
    errors, warnings = [], []
    try:
        with open(os.path.join(directory, "character.json"), encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [f"character.json 读不了: {e}"], []
    for key in REQUIRED:
        if _get(data, key) is None:
            errors.append(f"缺字段 {key}")
    if data.get("format") not in (None, FORMAT):
        errors.append(f"format {data.get('format')} 不认识（引擎支持 {FORMAT}）")
    if data.get("id") and os.path.basename(os.path.normpath(directory)) != data["id"]:
        warnings.append(f"目录名和 id {data['id']} 不一致")
    for view in VIEWS + ("icon",):
        rel = _get(data, f"sprites.{view}")
        if rel and not os.path.isfile(os.path.join(directory, rel)):
            errors.append(f"立绘 {view} 不存在: {rel}")
    if _get(data, "sprites.side_faces") not in (None, "left", "right"):
        errors.append("sprites.side_faces 只能是 left / right")
    for kind, rel in (data.get("animations") or {}).items():
        if kind not in ANIMATIONS:
            warnings.append(f"不认识的动画类别 {kind}")
            continue
        manifest = "frames.json" if kind == "workout_frames" else "clips.json"
        mpath = os.path.join(directory, rel, manifest)
        if not os.path.isfile(mpath):
            errors.append(f"动画 {kind} 缺清单: {rel}/{manifest}")
            continue
        with open(mpath, encoding="utf-8") as f:
            table = json.load(f)
        items = table.get("frames" if kind == "workout_frames" else "clips", {})
        for name, info in items.items():
            if not os.path.isfile(os.path.join(directory, rel, info["file"])):
                errors.append(f"动画 {kind}/{name} 文件不存在: {info['file']}")
    for kind in ANIMATIONS:
        if kind not in (data.get("animations") or {}):
            warnings.append(f"没有 {kind} 动画，对应功能会降级")
    for kind in LINE_KINDS:
        if not _get(data, f"lines.{kind}"):
            warnings.append(f"没有 {kind} 台词，用默认台词")
    return errors, warnings


def load(cid=None):
    return Character(find(cid or os.environ.get("DFY_CHARACTER") or DEFAULT_ID))


CHAR = load()
