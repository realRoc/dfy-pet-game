"""QQ 官方机器人直连（不装 dsh）：QQ 开放平台（q.qq.com）的机器人 AppID / AppSecret，走 WebSocket 网关收消息。

和 dsh-qqbot 用的是同一套开放平台协议（鉴权 → /gateway → IDENTIFY → 心跳 → 事件），只收两种事件：
单聊（C2C_MESSAGE_CREATE）和群里 @她（GROUP_AT_MESSAGE_CREATE），都用被动回复（带 msg_id）。
WebSocket 是机器人主动连出去，不用公网回调地址，家里电脑就能跑。

平台的限制（这里解决不了，写在 docs/im-bots.md）：
- 机器人没提审上线前只能在「沙箱」里用：开发设置里配好的沙箱群和沙箱成员才收得到消息
- 开放平台要求调用接口的出口 IP 在白名单里，家里宽带 IP 变了要去后台改
- 只能被动回复：别人发来消息后的一段时间内回，不能主动找人聊

依赖 aiohttp（discord.py 带着它，requirements.txt 里装了）；没装就不出现 QQ 直连入口。"""
import asyncio
import json
import re
import time

import requests

from .base import Adapter
from .core import Incoming

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API = "https://api.sgroup.qq.com"
INTENT_GROUP_AND_C2C = 1 << 25

try:
    import aiohttp
    AVAILABLE = True
except Exception:
    aiohttp = None
    AVAILABLE = False


def check_credentials(app_id, secret, timeout=10):
    """只用 HTTP 换一次 access_token 验 AppID / AppSecret。返回 (ok, 给人看的说明)。"""
    app_id, secret = (app_id or "").strip(), (secret or "").strip()
    if not (app_id and secret):
        return False, "AppID 和 AppSecret 都要填"
    try:
        r = requests.post(TOKEN_URL, json={"appId": app_id, "clientSecret": secret}, timeout=timeout)
        data = r.json()
    except requests.RequestException:
        return False, "连不上 QQ 开放平台，检查网络"
    except ValueError:
        return False, f"QQ 开放平台返回 {r.status_code}"
    if not data.get("access_token"):
        return False, f"AppID 或 AppSecret 不对（{str(data.get('message') or data)[:40]}）"
    return True, "AppID / AppSecret 可以用"


def parse_event(kind, d):
    """网关的一条 DISPATCH 事件 → Incoming；不是消息、或者是机器人发的，返回 None。"""
    if not isinstance(d, dict):
        return None
    author = d.get("author") or {}
    if author.get("bot"):
        return None
    text = re.sub(r"<@!?\w+>", "", str(d.get("content") or "")).strip()
    if kind == "C2C_MESSAGE_CREATE":
        user = author.get("user_openid")
        return Incoming(platform="qq", user=str(user), text=text, dm=True, raw=d) if user else None
    if kind == "GROUP_AT_MESSAGE_CREATE":
        user, group = author.get("member_openid"), d.get("group_openid")
        if not (user and group):
            return None
        return Incoming(platform="qq", user=str(user), text=text, group=str(group), channel=str(group), raw=d)
    return None


def reply_request(msg, text):
    """被动回复的 (路径, body)。"""
    d = msg.raw
    path = f"/v2/users/{msg.user}/messages" if msg.dm else f"/v2/groups/{msg.group}/messages"
    return path, {"content": text, "msg_type": 0, "msg_id": d.get("id"), "msg_seq": 1}


class QQAdapter(Adapter):
    platform = "qq"
    label = "QQ"
    RETRY = (2, 5, 10, 30, 60)
    STABLE = 60          # 上线撑过这么多秒才算连好了，重连等待从头算；不然服务端一连上就踢，会 2 秒猛连一次
    MISSED_ACKS = 2      # 连着这么多次心跳没回 ACK，就当连接已经断了（半开连接写进去不报错，只能靠这个发现）

    @staticmethod
    def available():
        return AVAILABLE

    @staticmethod
    def configured(conf):
        return bool(conf.get("app_id") and conf.get("secret"))

    def __init__(self, hub, conf, on_status=None):
        super().__init__(hub, conf, on_status)
        self.session = None
        self.closing = False
        self._token, self._token_until = "", 0.0

    async def _access_token(self):
        if self._token and time.monotonic() < self._token_until:
            return self._token
        async with self.session.post(TOKEN_URL, json={"appId": self.conf["app_id"],
                                                      "clientSecret": self.conf["secret"]}) as r:
            data = await r.json(content_type=None)
        if not data.get("access_token"):
            raise PermissionError(f"AppID 或 AppSecret 不对（{str(data.get('message') or '')[:40]}）")
        self._token = data["access_token"]
        self._token_until = time.monotonic() + int(data.get("expires_in") or 7200) - 120
        return self._token

    async def _api(self, method, path, body=None):
        token = await self._access_token()
        async with self.session.request(method, API + path, json=body,
                                        headers={"Authorization": f"QQBot {token}"}) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                what = "取网关地址" if path == "/gateway" else "发消息"   # 路径里有对方的 openid，不往外报
                detail = data.get("message") if isinstance(data, dict) else data
                raise RuntimeError(f"{what}返回 {r.status}：{str(detail)[:60]}")
            return data

    async def run(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        tries = 0
        try:
            while not self.closing:
                self.set_status("connecting", "连接中…")
                online_for = 0
                try:
                    online_for = await self._session_once()
                except PermissionError as e:
                    self.set_status("error", str(e))
                    return       # 密钥不对，重连也没用
                except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, ValueError) as e:
                    self.set_status("error", f"断开了：{str(e)[:80] or type(e).__name__}，稍后重连")
                if self.closing:
                    break
                if online_for >= self.STABLE:
                    tries = 0
                await asyncio.sleep(self.RETRY[min(tries, len(self.RETRY) - 1)])
                tries += 1
        finally:
            await self.session.close()

    async def _session_once(self):
        """连一次网关，一直收到断开为止。返回上线（READY）后撑了几秒，没上线就是 0。"""
        url = (await self._api("GET", "/gateway"))["url"]
        async with self.session.ws_connect(url, heartbeat=None) as ws:
            seq = None
            beat = None
            ready_at = None
            last_ack = time.monotonic()
            dead = False
            try:
                async for frame in ws:
                    if frame.type != aiohttp.WSMsgType.TEXT:
                        break
                    data = json.loads(frame.data)
                    op = data.get("op")
                    if data.get("s") is not None:
                        seq = data["s"]
                    if op == 10:    # HELLO：开始心跳，然后 IDENTIFY
                        interval = data["d"]["heartbeat_interval"] / 1000

                        async def heartbeat():
                            nonlocal dead
                            while True:
                                await asyncio.sleep(interval)
                                if time.monotonic() - last_ack > interval * (self.MISSED_ACKS + 0.5):
                                    dead = True
                                    await ws.close()   # 收消息的循环随之结束，走下面的重连
                                    return
                                await ws.send_json({"op": 1, "d": seq})
                        last_ack = time.monotonic()
                        beat = asyncio.ensure_future(heartbeat())
                        await ws.send_json({"op": 2, "d": {"token": f"QQBot {await self._access_token()}",
                                                           "intents": INTENT_GROUP_AND_C2C, "shard": [0, 1]}})
                    elif op == 11:   # HEARTBEAT_ACK
                        last_ack = time.monotonic()
                    elif op == 0:
                        if data.get("t") == "READY":
                            ready_at = time.monotonic()
                            bot = (data.get("d") or {}).get("user") or {}
                            self.set_status("online", f"已上线：{bot.get('username') or self.conf['app_id']}")
                        else:
                            msg = parse_event(data.get("t"), data.get("d"))
                            if msg is not None:
                                asyncio.ensure_future(self._answer(msg))
                    elif op in (7, 9):   # 要求重连 / 会话失效：重新走一遍
                        break
            finally:
                if beat:
                    beat.cancel()
            if ws.close_code == 4004:
                raise PermissionError("鉴权失败：AppID / AppSecret 不对")
            if ws.close_code in (4914, 4915):
                raise PermissionError("这个机器人没开通单聊 / 群聊的消息权限，去开放平台的开发设置里看看")
            if dead:
                raise RuntimeError("心跳没有回应，连接可能断了")
        return 0 if ready_at is None else time.monotonic() - ready_at

    async def _answer(self, msg):
        out = await asyncio.to_thread(self.hub.handle, msg)
        if not out.reply:
            return
        path, body = reply_request(msg, out.reply)
        try:
            await self._api("POST", path, body)
        except Exception as e:
            print("[QQ] 回复失败:", str(e)[:120])

    async def close(self):
        self.closing = True
        if self.session is not None:
            await self.session.close()
