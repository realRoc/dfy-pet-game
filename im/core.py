"""IM 适配层的核心：平台无关的「收到一条消息 → 决定回不回 → 用角色人设问 LLM → 回复 + 可选的桌面动作」。

各平台（discord_bot.py、qq_bot.py）只负责把平台事件变成 Incoming、把回复发回去；
白名单、限流、历史、人设、桌面动作的校验和冷却都在这里，所有平台一套规矩。

安全边界：IM 里的人只能和她聊天。LLM 的输出只被当成两样东西——一段回复文字，和一个可选的桌面动作；
桌面动作只有 say / emote / dance 三种，过 control.parse_msg 校验和截断，再过 20 秒冷却。没有别的工具。"""
import collections
import json
import re
import threading
from dataclasses import dataclass, field

import control
import llm

from . import persona
from .limits import Allowlist, Cooldown, RateLimiter

TEXT_IN_MAX = 500    # 别人发来的话最多喂给 LLM 这么长
REPLY_MAX = 300      # 回复最多这么长（Discord 一条上限 2000，QQ 更短的也装得下）
HISTORY = 8          # 每个会话记最近几条（用户 + 她的）

# LLM 给的桌面动作 → control.py 的指令；IM 里不能 show（把藏起来的桌宠叫出来），也不能有别的
_ACTIONS = {"say": "say", "emote": "emote", "dance": "clip"}

LIMIT_REPLIES = {
    "user": "你说得太快啦，本鲸要喘口气（一分钟后再来）",
    "minute": "找我的人太多了，服务器繁忙，请稍后再试",
    "day": "今天聊太多了，本鲸要去 DeepSleep 了，明天见",
}


@dataclass
class Incoming:
    """一条平台无关的消息。id 都转成字符串；私聊时 group / channel 为空。"""
    platform: str           # "discord" / "qq"
    user: str               # 发消息的人
    text: str               # 已经去掉 @她 的正文
    dm: bool = False
    group: str = ""         # Discord 的服务器 / QQ 的群
    channel: str = ""       # Discord 的频道；QQ 群没有频道，和 group 一样
    name: str = ""          # 显示名，只给 LLM 看看是谁在说话
    raw: object = field(default=None, repr=False)   # 平台自己的消息对象，回复时用

    @property
    def chat(self):
        """会话键：一个频道 / 一个群 / 一个私聊各记各的历史。"""
        return f"{self.platform}:{'dm:' + self.user if self.dm else self.channel or self.group}"


@dataclass
class Outcome:
    reply: str = ""                 # 要发回 IM 的话；空就不回
    desktop: tuple = None           # (cmd, arg)，已经过校验和冷却
    reason: str = ""                # 没回的原因：empty / blocked / limited / error（调试和测试用）


def parse_reply(text):
    """LLM 的输出 → (回复文字, 桌面动作或 None)。按 JSON 解；不是 JSON 就整段当回复，桌面动作作废。"""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    data = None
    if m:
        try:
            data = json.loads(m.group(0))
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return text[:REPLY_MAX], None
    reply = str(data.get("reply") or "").strip()[:REPLY_MAX]
    return reply, desktop_command(data.get("desktop"))


def desktop_command(d):
    """LLM 给的 desktop 字段 → control 指令 (cmd, arg)；不认识的一律 None。"""
    if not isinstance(d, dict):
        return None
    cmd = _ACTIONS.get(d.get("action"))
    if not cmd:
        return None
    return control.parse_msg({"cmd": cmd, "text": d.get("text"), "key": d.get("mood")})


def _ask_default(key, messages):
    return llm.chat(key, messages, max_tokens=300, temperature=0.9, json_mode=True, timeout=20)


class Hub:
    """所有平台共用一个。handle() 会阻塞调 LLM，平台在自己的线程 / executor 里调它。

    get_key: 返回 DeepSeek Key 的函数（设置里改了 Key 不用重启机器人）
    on_desktop: 桌面动作的回调 (cmd, arg)，由 Qt 那边排到主线程执行；不传就不做桌面动作
    ask: (key, messages) → LLM 原始输出，测试里替换掉"""

    def __init__(self, get_key, on_desktop=None, limits=None, ask=None):
        self.get_key = get_key
        self.on_desktop = on_desktop
        self.limiter = RateLimiter(limits)
        self.cooldown = Cooldown()
        self.ask = ask or _ask_default
        self.history = collections.defaultdict(lambda: collections.deque(maxlen=HISTORY))
        self.lock = threading.Lock()    # 两个平台的线程可能同时进来
        self.allow = {}                 # 平台 → Allowlist
        self.warned = set()             # 已经提示过超额的 (人, 原因)

    def set_allowlist(self, platform, allowlist):
        self.allow[platform] = allowlist

    def handle(self, msg, now=None):
        text = (msg.text or "").strip()[:TEXT_IN_MAX]
        if not text:
            return Outcome(reason="empty")
        allow = self.allow.get(msg.platform) or Allowlist()
        if not allow.allows(msg.user, msg.group, msg.channel, msg.dm):
            return Outcome(reason="blocked")   # 不回，也不提示：白名单外的人不该知道她在
        user_key = f"{msg.platform}:{msg.user}"
        with self.lock:
            why = self.limiter.check(user_key, now)
            if why:
                # 超额了每人只提示一次，之后不理，不然提示本身也会被刷屏；正常回过一次再重新算
                first = (user_key, why) not in self.warned
                self.warned.add((user_key, why))
                return Outcome(reply=LIMIT_REPLIES[why] if first else "", reason="limited")
            self.limiter.hit(user_key, now)
            self.warned = {w for w in self.warned if w[0] != user_key}
            hist = list(self.history[msg.chat])
        messages = [{"role": "system", "content": persona.system_prompt(_label(msg.platform))}]
        messages += hist
        who = f"[{msg.name}] " if msg.name and not msg.dm else ""
        messages.append({"role": "user", "content": who + text})
        try:
            raw = self.ask(self.get_key(), messages)
        except llm.LLMError as e:
            return Outcome(reply=f"（{e}）", reason="error")
        reply, desktop = parse_reply(raw)
        with self.lock:
            self.history[msg.chat].append({"role": "user", "content": who + text})
            self.history[msg.chat].append({"role": "assistant", "content": json.dumps(
                {"reply": reply, "desktop": None}, ensure_ascii=False)})
            if desktop and not (self.on_desktop and self.cooldown.take(now)):
                desktop = None
        if desktop:
            self.on_desktop(*desktop)
        return Outcome(reply=reply, desktop=desktop)


def _label(platform):
    return {"discord": "Discord", "qq": "QQ"}.get(platform, platform)
