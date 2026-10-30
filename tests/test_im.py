"""IM 机器人（im/）：人设、LLM 输出解析、白名单、限流、桌面动作冷却、Discord / QQ 消息解析、QQ 网关握手、
没装依赖 / 没配置时的降级。平台全是假的，不连网。运行：python -m unittest discover -s tests"""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    import common
    import control
    import llm
    import main
    from im import core, discord_bot, limits, persona, qq_bot, runner
    from im.base import Adapter
except ImportError as e:   # 没装 PySide6 / requests
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


def msg(text="你好", user="u1", dm=False, group="g1", channel="c1", platform="discord"):
    return core.Incoming(platform=platform, user=user, text=text, dm=dm,
                         group="" if dm else group, channel="" if dm else channel)


@unittest.skipIf(_SKIP, _SKIP)
class PersonaTest(unittest.TestCase):
    def test_reads_preset_from_cordis_patch(self):
        p = persona.character_persona()
        self.assertIn("大肥鱼", p["prompt"])
        self.assertIn("嘴硬心软", p["prompt"])     # 是 dfy-qq preset 那段，不是保底的
        self.assertIn("happy", p["moods"])

    def test_platform_prompt(self):
        s = persona.system_prompt("Discord")
        self.assertIn("通过 Discord 和大家聊天", s)
        self.assertNotIn("QQ", s)
        self.assertNotIn("dafeiyu_desktop", s)    # dsh 工具那段换成了 JSON 约定
        self.assertIn('"desktop"', s)
        self.assertIn("通过 QQ", persona.system_prompt("QQ"))

    def test_yaml_block(self):
        text = "a:\n  prefix: |-\n    第一行\n\n    第二行\n      缩进\n  other: 1\n"
        self.assertEqual(persona._yaml_block(text, "prefix"), "第一行\n\n第二行\n  缩进")
        self.assertIsNone(persona._yaml_block(text, "nope"))

    def test_fallback_when_patch_missing(self):
        with mock.patch.object(persona, "PATCH_PATH", "/nonexistent/cordis.patch.yml"):
            self.assertIn("大肥鱼", persona.character_persona()["prompt"])


@unittest.skipIf(_SKIP, _SKIP)
class ParseReplyTest(unittest.TestCase):
    def test_json(self):
        r, d = core.parse_reply('{"reply": "嘿嘿", "desktop": {"action": "emote", "mood": "shy"}}')
        self.assertEqual((r, d), ("嘿嘿", ("emote", "shy")))

    def test_json_wrapped_in_fence(self):
        r, d = core.parse_reply('```json\n{"reply": "好", "desktop": null}\n```')
        self.assertEqual((r, d), ("好", None))

    def test_not_json_is_plain_reply(self):
        self.assertEqual(core.parse_reply("就是一句话"), ("就是一句话", None))
        self.assertEqual(core.parse_reply("{坏掉的"), ("{坏掉的", None))

    def test_only_three_actions(self):
        self.assertEqual(core.desktop_command({"action": "dance"}), ("clip", None))
        self.assertEqual(core.desktop_command({"action": "say", "text": "鱼" * 100}), ("say", "鱼" * control.SAY_MAX))
        self.assertEqual(core.desktop_command({"action": "emote", "mood": "rm -rf"}), ("emote", None))
        for bad in ({"action": "show"}, {"action": "shell", "cmd": "ls"}, {"action": "say", "text": ""},
                    "say", None, []):
            self.assertIsNone(core.desktop_command(bad), bad)

    def test_reply_is_cut(self):
        r, _ = core.parse_reply(json.dumps({"reply": "长" * 1000}))
        self.assertEqual(len(r), core.REPLY_MAX)


@unittest.skipIf(_SKIP, _SKIP)
class LimitsTest(unittest.TestCase):
    def test_per_user(self):
        rl = limits.RateLimiter({"per_user_per_min": 2})
        for t in (0, 1):
            self.assertIsNone(rl.check("a", t))
            rl.hit("a", t)
        self.assertEqual(rl.check("a", 2), "user")
        self.assertIsNone(rl.check("b", 2))        # 别人不受影响
        self.assertIsNone(rl.check("a", 61))       # 一分钟后恢复

    def test_global(self):
        rl = limits.RateLimiter({"per_user_per_min": 100, "global_per_min": 3, "global_per_day": 5})
        for i in range(3):
            rl.hit(f"u{i}", 0)
        self.assertEqual(rl.check("x", 1), "minute")
        rl.hit("y", 70)
        rl.hit("z", 70)
        self.assertEqual(rl.check("x", 71), "day")
        self.assertIsNone(rl.check("x", 86401))

    def test_zero_means_never(self):
        self.assertEqual(limits.RateLimiter({"global_per_day": 0}).check("a", 0), "day")

    def test_allowlist(self):
        self.assertTrue(limits.Allowlist().allows("anyone", dm=True))
        a = limits.Allowlist(groups=["g1"], users=[])
        self.assertTrue(a.allows("u", "g1", "c"))
        self.assertFalse(a.allows("u", "g2", "c"))
        self.assertFalse(a.allows("u", dm=True))   # 只限制了群：私聊一律不回
        a = limits.Allowlist(groups=["g1"], channels=["c1"], users=["boss"])
        self.assertTrue(a.allows("boss", "g1", "c1"))
        self.assertFalse(a.allows("boss", "g1", "c2"))
        self.assertFalse(a.allows("other", "g1", "c1"))
        self.assertTrue(a.allows("boss", dm=True))
        self.assertTrue(limits.Allowlist(users=[123]).allows("123", dm=True))   # 数字 id 也认

    def test_cooldown(self):
        c = limits.Cooldown(20)
        self.assertTrue(c.take(0))
        self.assertFalse(c.take(19.9))
        self.assertTrue(c.take(20))


@unittest.skipIf(_SKIP, _SKIP)
class HubTest(unittest.TestCase):
    def setUp(self):
        self.desk = []
        self.calls = []
        self.out = '{"reply": "收到", "desktop": {"action": "emote", "mood": "happy"}}'

        def ask(key, messages):
            self.calls.append((key, messages))
            if isinstance(self.out, Exception):
                raise self.out
            return self.out
        self.hub = core.Hub(lambda: "sk-test", on_desktop=lambda *a: self.desk.append(a), ask=ask)

    def test_reply_and_desktop_cooldown(self):
        o = self.hub.handle(msg(), now=0)
        self.assertEqual(o.reply, "收到")
        self.assertEqual(self.desk, [("emote", "happy")])
        o = self.hub.handle(msg(user="u2"), now=5)
        self.assertEqual(o.reply, "收到")
        self.assertIsNone(o.desktop)               # 20 秒内只动一次，回复照常
        self.hub.handle(msg(user="u3"), now=25)
        self.assertEqual(len(self.desk), 2)

    def test_prompt_and_history(self):
        self.hub.handle(msg("第一句"), now=0)
        self.hub.handle(msg("第二句"), now=1)
        self.hub.handle(msg("别的频道", channel="c2"), now=2)
        key, m = self.calls[1]
        self.assertEqual(key, "sk-test")
        self.assertEqual(m[0]["role"], "system")
        self.assertIn("Discord", m[0]["content"])
        self.assertEqual([x["role"] for x in m[1:]], ["user", "assistant", "user"])
        self.assertIn("第二句", m[-1]["content"])
        self.assertEqual(len(self.calls[2][1]), 2)   # 新频道没有历史

    def test_long_input_is_cut(self):
        self.hub.handle(msg("字" * 5000), now=0)
        self.assertLessEqual(len(self.calls[0][1][-1]["content"]), core.TEXT_IN_MAX)

    def test_blocked_is_silent(self):
        self.hub.set_allowlist("discord", limits.Allowlist(users=["boss"]))
        o = self.hub.handle(msg(user="stranger"), now=0)
        self.assertEqual((o.reply, o.reason), ("", "blocked"))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.hub.handle(msg(user="boss"), now=0).reply, "收到")

    def test_rate_limit_warns_once(self):
        self.hub.limiter = limits.RateLimiter({"per_user_per_min": 1})
        self.hub.handle(msg(), now=0)
        o = self.hub.handle(msg(), now=1)
        self.assertEqual(o.reason, "limited")
        self.assertTrue(o.reply)                   # 第一次超额提示一下
        self.assertEqual(self.hub.handle(msg(), now=2).reply, "")   # 之后不理
        self.assertEqual(len(self.calls), 1)       # 超额的都没花 API
        self.assertEqual(self.hub.handle(msg(), now=61).reply, "收到")

    def test_llm_error(self):
        self.out = llm.LLMError("请求超时，检查网络")
        o = self.hub.handle(msg(), now=0)
        self.assertEqual((o.reply, o.reason), ("（请求超时，检查网络）", "error"))
        self.assertEqual(self.desk, [])

    def test_empty_and_no_desktop_callback(self):
        self.assertEqual(self.hub.handle(msg("   ")).reason, "empty")
        hub = core.Hub(lambda: "k", on_desktop=None, ask=lambda k, m: self.out)
        self.assertIsNone(hub.handle(msg(), now=0).desktop)

    def test_no_key_message(self):
        with self.assertRaises(llm.LLMError):
            llm.chat("", [])


def discord_message(content, author_id=1, bot=False, guild=True, mentions=()):
    return NS(author=NS(id=author_id, bot=bot, display_name="小明", name="xm"), content=content,
              guild=NS(id=10) if guild else None, channel=NS(id=20), mentions=[NS(id=i) for i in mentions])


@unittest.skipIf(_SKIP, _SKIP)
class DiscordTest(unittest.TestCase):
    me = NS(id=99)

    def test_to_incoming(self):
        m = discord_bot.to_incoming(discord_message("<@99> 吃了吗", mentions=[99]), self.me)
        self.assertEqual((m.text, m.user, m.group, m.channel, m.dm, m.name), ("吃了吗", "1", "10", "20", False, "小明"))
        m = discord_bot.to_incoming(discord_message("<@!99>在吗", mentions=[99]), self.me)
        self.assertEqual(m.text, "在吗")
        dm = discord_bot.to_incoming(discord_message("私聊", guild=False), self.me)
        self.assertEqual((dm.dm, dm.group, dm.chat), (True, "", "discord:dm:1"))

    def test_ignored(self):
        for m in (discord_message("没 @ 她"), discord_message("@别人", mentions=[5]),
                  discord_message("<@99>", bot=True, mentions=[99]), discord_message("自己", author_id=99, guild=False)):
            self.assertIsNone(discord_bot.to_incoming(m, self.me))

    def test_invite_url(self):
        url = discord_bot.invite_url("123")
        self.assertIn("client_id=123", url)
        self.assertIn("scope=bot", url)
        self.assertIn("permissions=68608", url)    # 看频道 + 发消息 + 读历史，没有管理员之类的

    def test_client_id_from_token(self):
        import base64
        head = base64.b64encode(b"112233445566").decode().rstrip("=")
        self.assertEqual(discord_bot.client_id_from_token(f"{head}.xx.yy"), "112233445566")
        self.assertEqual(discord_bot.client_id_from_token("乱填"), "")

    def test_check_token(self):
        with mock.patch.object(discord_bot.requests, "get") as get:
            get.return_value = NS(status_code=200, json=lambda: {"id": "7", "username": "dfy"})
            self.assertEqual(discord_bot.check_token("t"), (True, "机器人 dfy 可以用", "7"))
            self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bot t"})
            get.return_value = NS(status_code=401)
            self.assertFalse(discord_bot.check_token("t")[0])
            get.side_effect = discord_bot.requests.ConnectionError()
            self.assertIn("网络", discord_bot.check_token("t")[1])
        self.assertFalse(discord_bot.check_token("  ")[0])


@unittest.skipIf(_SKIP or not getattr(discord_bot, "AVAILABLE", False), _SKIP or "没装 discord.py")
class DiscordAdapterTest(unittest.TestCase):
    def run_with(self, error):
        statuses = []
        a = discord_bot.DiscordAdapter(NS(handle=None), {"token": "SECRET"}, lambda *s: statuses.append(s))

        async def start(self_, token):
            raise error
        with mock.patch.object(discord_bot.discord.Client, "start", start):
            asyncio.run(a.run())
        return a, statuses

    def test_client_setup_and_bad_token(self):
        a, statuses = self.run_with(discord_bot.discord.LoginFailure("bad"))
        self.assertEqual(a.state, "error")
        self.assertIn("token 不对", a.detail)
        intents = a.client.intents
        self.assertTrue(intents.guild_messages and intents.dm_messages)
        self.assertFalse(intents.message_content)   # 不要特权 intent
        self.assertFalse(intents.members)
        self.assertFalse(a.client.allowed_mentions.everyone)

    def test_on_message_replies_without_mentions(self):
        a, _ = self.run_with(discord_bot.discord.LoginFailure("bad"))
        a.hub = NS(handle=lambda m: core.Outcome(reply=f"回 {m.text} @everyone"))
        a.client._connection.user = NS(id=99)

        class Typing:
            async def __aenter__(self):
                pass

            async def __aexit__(self, *e):
                return False
        m = discord_message("<@99> hi", mentions=[99])
        m.channel.typing = Typing
        m.reply = mock.AsyncMock()
        asyncio.run(a.client.on_message(m))
        m.reply.assert_awaited_once()
        args, kw = m.reply.call_args
        self.assertEqual(args, ("回 hi @everyone",))
        self.assertFalse(kw["allowed_mentions"].everyone)   # 文字里有 @everyone 也不会真的 @
        self.assertFalse(kw["mention_author"])


@unittest.skipIf(_SKIP, _SKIP)
class QQParseTest(unittest.TestCase):
    def test_c2c(self):
        m = qq_bot.parse_event("C2C_MESSAGE_CREATE", {"id": "m1", "content": " 你好 ", "author": {"user_openid": "o1"}})
        self.assertEqual((m.platform, m.user, m.text, m.dm), ("qq", "o1", "你好", True))
        self.assertEqual(qq_bot.reply_request(m, "嗯"),
                         ("/v2/users/o1/messages", {"content": "嗯", "msg_type": 0, "msg_id": "m1", "msg_seq": 1}))

    def test_group_at(self):
        m = qq_bot.parse_event("GROUP_AT_MESSAGE_CREATE", {"id": "m2", "content": "<@!123> 在吗", "group_openid": "G",
                                                           "author": {"member_openid": "o2"}})
        self.assertEqual((m.user, m.group, m.text, m.dm), ("o2", "G", "在吗", False))
        self.assertEqual(qq_bot.reply_request(m, "在")[0], "/v2/groups/G/messages")

    def test_ignored(self):
        self.assertIsNone(qq_bot.parse_event("GUILD_CREATE", {}))
        self.assertIsNone(qq_bot.parse_event("C2C_MESSAGE_CREATE", {"author": {"user_openid": "o", "bot": True}}))
        self.assertIsNone(qq_bot.parse_event("GROUP_AT_MESSAGE_CREATE", {"author": {"member_openid": "o"}}))
        self.assertIsNone(qq_bot.parse_event("C2C_MESSAGE_CREATE", None))

    def test_check_credentials(self):
        with mock.patch.object(qq_bot.requests, "post") as post:
            post.return_value = NS(status_code=200, json=lambda: {"access_token": "x", "expires_in": 7200})
            self.assertTrue(qq_bot.check_credentials("1", "s")[0])
            self.assertEqual(post.call_args.kwargs["json"], {"appId": "1", "clientSecret": "s"})
            post.return_value = NS(status_code=200, json=lambda: {"code": 100016, "message": "invalid appid"})
            ok, text = qq_bot.check_credentials("1", "s")
            self.assertFalse(ok)
            self.assertIn("invalid appid", text)
        self.assertFalse(qq_bot.check_credentials("", "s")[0])


class _Resp:
    def __init__(self, data, status=200):
        self.data, self.status = data, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self.data


class _WS:
    def __init__(self, frames):
        self.frames, self.sent, self.close_code = list(frames), [], 1000

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0)
        if not self.frames:
            raise StopAsyncIteration
        return NS(type=qq_bot.aiohttp.WSMsgType.TEXT, data=json.dumps(self.frames.pop(0)))

    async def send_json(self, data):
        self.sent.append(data)


class _HangingWS(_WS):
    """帧发完以后一直等，直到被 close()；ack=True 时每个心跳都回一个 ACK。"""

    def __init__(self, frames, ack=False):
        super().__init__(frames)
        self.ack, self.closed = ack, False
        self.wake = None

    async def __anext__(self):
        if self.wake is None:
            self.wake = asyncio.Event()
        while not self.frames:
            if self.closed:
                raise StopAsyncIteration
            self.wake.clear()
            await self.wake.wait()
        return NS(type=qq_bot.aiohttp.WSMsgType.TEXT, data=json.dumps(self.frames.pop(0)))

    async def send_json(self, data):
        self.sent.append(data)
        if self.ack and data.get("op") == 1:
            self.frames.append({"op": 11})
            self.wake.set()

    async def close(self):
        self.closed = True
        if self.wake:
            self.wake.set()


class _Session:
    def __init__(self, ws):
        self.ws, self.posts = ws, []

    def post(self, url, json=None):
        return _Resp({"access_token": "TOKEN", "expires_in": 7200})

    def request(self, method, url, json=None, headers=None):
        self.posts.append((method, url, json, headers))
        return _Resp({"url": "wss://gateway"} if url.endswith("/gateway") else {"id": "sent"})

    def ws_connect(self, url, heartbeat=None):
        return self.ws

    async def close(self):
        pass


@unittest.skipIf(_SKIP or not getattr(qq_bot, "AVAILABLE", False), _SKIP or "没装 aiohttp")
class QQGatewayTest(unittest.TestCase):
    def test_handshake_and_reply(self):
        ws = _WS([{"op": 10, "d": {"heartbeat_interval": 45000}},
                  {"op": 0, "s": 1, "t": "READY", "d": {"user": {"username": "大肥鱼bot"}}},
                  {"op": 0, "s": 2, "t": "C2C_MESSAGE_CREATE",
                   "d": {"id": "m1", "content": "hi", "author": {"user_openid": "o1"}}}])
        session = _Session(ws)
        hub = NS(handle=lambda m: core.Outcome(reply=f"回 {m.text}"))
        statuses = []
        a = qq_bot.QQAdapter(hub, {"app_id": "1", "secret": "SECRET"}, lambda *s: statuses.append(s))
        a.session = session

        async def go():
            await a._session_once()
            for _ in range(20):           # 等回复那个 task 跑完
                await asyncio.sleep(0)
        asyncio.run(go())
        self.assertEqual(ws.sent[0]["op"], 2)
        self.assertEqual(ws.sent[0]["d"], {"token": "QQBot TOKEN", "intents": 1 << 25, "shard": [0, 1]})
        self.assertIn(("qq", "online", "已上线：大肥鱼bot"), statuses)
        method, url, body, headers = session.posts[-1]
        self.assertEqual((method, url), ("POST", "https://api.sgroup.qq.com/v2/users/o1/messages"))
        self.assertEqual(body["content"], "回 hi")
        self.assertEqual(headers, {"Authorization": "QQBot TOKEN"})

    def test_missing_heartbeat_ack_reconnects(self):
        """半开连接：心跳写进去不报错、也收不到任何帧。连着两次没 ACK 就自己断开，抛错走重连，而不是一直挂着「在线」。"""
        ws = _HangingWS([{"op": 10, "d": {"heartbeat_interval": 20}},
                         {"op": 0, "s": 1, "t": "READY", "d": {"user": {"username": "b"}}}])
        a = qq_bot.QQAdapter(NS(handle=None), {"app_id": "1", "secret": "s"})
        a.session = _Session(ws)
        with self.assertRaisesRegex(RuntimeError, "心跳"):
            asyncio.run(asyncio.wait_for(a._session_once(), 2))
        self.assertTrue(ws.closed)

    def test_acked_heartbeat_stays_connected(self):
        ws = _HangingWS([{"op": 10, "d": {"heartbeat_interval": 20}}], ack=True)
        a = qq_bot.QQAdapter(NS(handle=None), {"app_id": "1", "secret": "s"})
        a.session = _Session(ws)
        with self.assertRaises(asyncio.TimeoutError):   # 0.3 秒里发了十几次心跳都有 ACK，一直连着
            asyncio.run(asyncio.wait_for(a._session_once(), 0.3))
        self.assertGreater(sum(1 for m in ws.sent if m["op"] == 1), 5)
        self.assertFalse(ws.closed)

    def test_backoff_resets_only_after_stable_session(self):
        """服务端一连上就踢（op 7 / 9、握手后马上关）时，等待时间要一路加长，不能每次都从 2 秒重来。"""
        a = qq_bot.QQAdapter(NS(handle=None), {"app_id": "1", "secret": "s"})
        online = iter([0, 0, 0, 0, 0, 0, 120, 0])
        delays = []

        async def session_once():
            return next(online)

        async def sleep(d):
            delays.append(d)
            if len(delays) == 8:
                a.closing = True
        a._session_once = session_once
        with mock.patch.object(qq_bot.aiohttp, "ClientSession", lambda **kw: _Session(None)), \
                mock.patch.object(qq_bot.asyncio, "sleep", sleep):
            asyncio.run(a.run())
        self.assertEqual(delays, [2, 5, 10, 30, 60, 60, 2, 5])

    def test_auth_failure_stops(self):
        ws = _WS([])
        ws.close_code = 4004
        a = qq_bot.QQAdapter(NS(handle=None), {"app_id": "1", "secret": "s"})
        a.session = _Session(ws)
        with self.assertRaises(PermissionError):
            asyncio.run(a._session_once())


class _FakeAdapter(Adapter):
    platform, label = "fake", "Fake"
    started = None

    @staticmethod
    def available():
        return True

    @staticmethod
    def configured(conf):
        return bool(conf.get("token"))

    async def run(self):
        self.set_status("online", f"用 {self.conf['token']} 连上了")
        _FakeAdapter.started.set()
        await asyncio.sleep(3600)


@unittest.skipIf(_SKIP, _SKIP)
class RunnerTest(unittest.TestCase):
    def test_start_stop_and_redaction(self):
        import threading
        _FakeAdapter.started = threading.Event()
        seen = []
        r = runner.Runner(hub=None, on_status=lambda *s: seen.append(s))
        with mock.patch.dict(runner.ADAPTERS, {"fake": _FakeAdapter}):
            self.assertFalse(r.start("fake", {"token": ""}))     # 没配置不启动
            self.assertTrue(r.start("fake", {"token": "SECRET-TOKEN"}))
            self.assertTrue(_FakeAdapter.started.wait(5))
            self.assertEqual(r.status("fake"), ("online", "用 *** 连上了"))   # token 不出现在状态里
            r.stop("fake")
            self.assertEqual(r.status("fake"), ("off", "未连接"))
        r.stop_all()
        self.assertFalse(any("SECRET" in s[2] for s in seen))

    def test_settings_defaults(self):
        cfg = {"im": {"discord": {"token": "t"}}}
        conf = runner.settings(cfg, "discord")
        self.assertEqual(conf["token"], "t")
        self.assertEqual(conf["allow_users"], [])
        self.assertFalse(conf["enabled"])
        self.assertIs(cfg["im"]["discord"], conf)
        self.assertEqual(runner.settings({}, "qq")["app_id"], "")


@unittest.skipIf(_SKIP, _SKIP)
class AppTest(unittest.TestCase):
    """接到桌宠上：有依赖就出现入口；没依赖照常启动、没有入口；勾着 enabled 但没填密钥不去连。"""

    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        p = mock.patch.object(common, "CONFIG_PATH", os.path.join(self.tmp, "config.json"))
        p.start()
        self.addCleanup(p.stop)

    def make_app(self):
        app = main.PetApp(self.qapp)
        self.addCleanup(app.pet.timer.stop)
        if app.im:
            self.addCleanup(app.im.shutdown)
        return app

    def menu_texts(self, app):
        return [a.text() for a in app.pet._build_menu().actions()]

    def test_entry_when_available(self):
        from im.qt import IMService
        with mock.patch.object(IMService, "platforms", staticmethod(lambda: ["qq", "discord"])):
            app = self.make_app()
            app.im.open_dialog()
        self.assertIsNotNone(app.im)
        self.assertIn("🔗 连接 IM", self.menu_texts(app))
        from PySide6.QtWidgets import QPushButton
        tips = [b.toolTip() for b in app.pet.function_panel.findChildren(QPushButton)]
        self.assertEqual(tips, ["聊天", "爬塔", "跟练", "连接 IM"])
        self.assertEqual(set(app.im.dialog.sections), {"qq", "discord"})
        app.im.dialog.close()

    def test_no_entry_without_deps(self):
        from im.qt import IMService
        with mock.patch.object(IMService, "platforms", staticmethod(lambda: [])):
            app = self.make_app()
        self.assertIsNone(app.im)
        self.assertNotIn("🔗 连接 IM", self.menu_texts(app))
        app.quit = lambda: None   # 退出路径不碰 app.im

    def test_import_failure_is_survivable(self):
        with mock.patch.dict("sys.modules", {"im.qt": None}):
            app = self.make_app()
        self.assertIsNone(app.im)

    def test_enabled_but_unconfigured_does_not_connect(self):
        with open(common.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"im": {"discord": {"enabled": True, "token": ""}, "qq": {"enabled": True}}}, f)
        app = self.make_app()
        if app.im:
            self.assertEqual(app.im.runner.tasks, {})

    def test_desktop_action_runs_on_pet(self):
        from im.qt import IMService
        with mock.patch.object(IMService, "platforms", staticmethod(lambda: ["qq"])):
            app = self.make_app()
        with mock.patch.object(app.pet, "play_expression") as play:
            app.im.desktop.emit("emote", "shy")
            self.qapp.processEvents()
        play.assert_called_once_with("shy")


if __name__ == "__main__":
    unittest.main()
