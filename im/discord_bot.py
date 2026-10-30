"""Discord 适配器：用户自己建的 Discord 机器人，@她 或私信她时用角色身份回复。

用 discord.py（可选依赖，没装就不出现 Discord 入口）。不申请 Message Content 这个特权 intent：
Discord 本来就把「@了机器人的消息」和私信的正文发给机器人，别的消息她也不该看。"""
import asyncio
import base64
import re

import requests

from .base import Adapter
from .core import Incoming

API = "https://discord.com/api/v10"
# 邀请链接只要这三个权限：看得见频道（1<<10）、发消息（1<<11）、读消息历史（1<<16，回复某条消息要它）
PERMISSIONS = (1 << 10) | (1 << 11) | (1 << 16)

try:
    import discord
    AVAILABLE = True
except Exception:   # 没装 discord.py，或者它在这个 Python 上起不来
    discord = None
    AVAILABLE = False


def invite_url(client_id):
    return f"https://discord.com/oauth2/authorize?client_id={client_id}&scope=bot&permissions={PERMISSIONS}"


def client_id_from_token(token):
    """bot token 第一段是机器人用户 id 的 base64，对机器人来说就是应用的 client id。解不出来返回空串。"""
    try:
        head = token.split(".")[0]
        cid = base64.b64decode(head + "=" * (-len(head) % 4)).decode("ascii")
        return cid if cid.isdigit() else ""
    except Exception:
        return ""


def check_token(token, timeout=10):
    """只用 HTTP 验一下 token（不连网关、不用 discord.py）。返回 (ok, 给人看的说明, client_id)。"""
    token = (token or "").strip()
    if not token:
        return False, "还没填 token", ""
    try:
        r = requests.get(f"{API}/users/@me", headers={"Authorization": f"Bot {token}"}, timeout=timeout)
    except requests.RequestException:
        return False, "连不上 Discord，检查网络（国内可能要代理）", ""
    if r.status_code == 401:
        return False, "token 不对：去开发者后台 Bot 页面重新复制", ""
    if r.status_code != 200:
        return False, f"Discord 返回 {r.status_code}", ""
    me = r.json()
    return True, f"机器人 {me.get('username', '?')} 可以用", str(me.get("id") or client_id_from_token(token))


def to_incoming(message, me):
    """discord.Message → Incoming；不该回的（机器人发的、群里没 @她、@everyone）返回 None。
    只用到 message 的几个属性，测试里拿 SimpleNamespace 冒充。"""
    author = message.author
    if getattr(author, "bot", False) or author.id == me.id:
        return None
    dm = message.guild is None
    if not dm and not any(u.id == me.id for u in message.mentions):
        return None
    text = re.sub(rf"<@!?{me.id}>", "", message.content or "").strip()
    return Incoming(
        platform="discord", user=str(author.id), text=text, dm=dm,
        group="" if dm else str(message.guild.id), channel="" if dm else str(message.channel.id),
        name=getattr(author, "display_name", "") or getattr(author, "name", ""), raw=message)


class DiscordAdapter(Adapter):
    platform = "discord"
    label = "Discord"

    @staticmethod
    def available():
        return AVAILABLE

    @staticmethod
    def configured(conf):
        return bool(conf.get("token"))

    def __init__(self, hub, conf, on_status=None):
        super().__init__(hub, conf, on_status)
        self.client = None

    async def run(self):
        intents = discord.Intents.none()
        intents.guilds = True           # 频道 / 服务器信息，to_incoming 要用
        intents.guild_messages = True   # 群里 @她 的消息
        intents.dm_messages = True      # 私信
        client = self.client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())

        @client.event
        async def on_ready():
            self.set_status("online", f"已上线：{client.user}")

        @client.event
        async def on_message(message):
            msg = to_incoming(message, client.user)
            if msg is None:
                return
            async with message.channel.typing():
                out = await asyncio.to_thread(self.hub.handle, msg)
            if out.reply:
                # 回复里不准 @ 任何人（包括 @everyone），LLM 被人带着刷屏也只是一段文字
                await message.reply(out.reply, mention_author=False,
                                    allowed_mentions=discord.AllowedMentions.none())

        self.set_status("connecting", "连接中…")
        try:
            await client.start(self.conf["token"])
        except discord.LoginFailure:
            self.set_status("error", "token 不对：去开发者后台 Bot 页面重新复制")
        except discord.PrivilegedIntentsRequired:
            self.set_status("error", "缺权限：这个机器人不该要特权 intent，检查一下设置")

    async def close(self):
        if self.client is not None:
            await self.client.close()
