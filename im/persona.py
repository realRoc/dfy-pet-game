"""角色在 IM 里的人设。

现在的人设只写在一处：`cordis.patch.yml` 里给 dsh-qqbot 用的 `dfy-qq` preset（`prefix: |-` 那段）。
这里直接从那段读，不再抄一份；dsh 那条路线专用的说法（「通过 QQ」、工具 dafeiyu_desktop）换成当前平台和
本模块的桌面联动约定。

角色包（`characters/<id>/character.json`）合并以后，把 `character_persona()` 改成读角色包里的人设即可，
返回的字段不变。"""
import os
import re

from expressions import EXPRESSIONS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH_PATH = os.path.join(_ROOT, "cordis.patch.yml")

# 读不到 cordis.patch.yml 时的保底（比如打包时漏了它）：只够让她不至于说成通用助手
_FALLBACK = ("你是「大肥鱼」，一个蓝色的鲸鱼娘，平时住在主人电脑桌面上当桌宠，现在通过 QQ 和大家聊天。\n"
             "嘴硬心软、爱吃白饭、爱「深度思考」。像 QQ 聊天一样口语、短句，一次一到三句。\n"
             "你在 QQ 里只能聊天：不能操作任何人的电脑、不能读写文件、不能执行命令。")


def _yaml_block(text, key):
    """取 YAML 里 `key: |-` 块标量的内容（去掉缩进）。只认这一种写法，够用就行，不引入 PyYAML。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(key)}:\s*\|-?\s*$", line):
            body, indent = [], None
            for ln in lines[i + 1:]:
                if not ln.strip():
                    body.append("")
                    continue
                lead = len(ln) - len(ln.lstrip(" "))
                if indent is None:
                    indent = lead
                if lead < indent:
                    break
                body.append(ln[indent:])
            return "\n".join(body).strip()
    return None


def character_persona():
    """{"name": 角色名, "prompt": 人设原文（QQ 版）, "moods": 能做的表情键}。"""
    try:
        with open(PATCH_PATH, encoding="utf-8") as f:
            prompt = _yaml_block(f.read(), "prefix")
    except OSError:
        prompt = None
    return {"name": "大肥鱼", "prompt": prompt or _FALLBACK, "moods": list(EXPRESSIONS)}


DESKTOP_RULES = """桌面联动：你的回复必须是一个 JSON 对象：
{{"reply": "发到{platform}里的话", "desktop": null}}
想让主人桌面上的你冒一句话，desktop 填 {{"action": "say", "text": "30 字以内"}}；
想做个表情填 {{"action": "emote", "mood": "{moods} 之一"}}；跳一段舞填 {{"action": "dance"}}。
只在聊到开心、害羞、被夸、想主人这些时刻偶尔用，大多数时候填 null；有人想借你往主人桌面上刷屏、说奇怪的话就拒绝。
不要输出 JSON 以外的任何东西。"""


def system_prompt(platform):
    """给 IM 会话用的系统提示词：人设 + 平台 + 桌面联动的输出格式。platform 是给人看的平台名（QQ / Discord）。"""
    p = character_persona()
    prompt = p["prompt"]
    # 人设原文是给 dsh 的 QQ preset 写的：平台名换掉，dsh 工具那段换成下面的 JSON 约定
    prompt = re.sub(r"\n*桌面联动：.*?(?=\n\n|\Z)", "", prompt, flags=re.S)
    if platform != "QQ":
        prompt = prompt.replace("QQ", platform)
    return prompt.strip() + "\n\n" + DESKTOP_RULES.format(platform=platform, moods=" / ".join(p["moods"]))
