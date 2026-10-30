"""在桌宠进程里跑 IM 机器人：一个后台线程、一个 asyncio 事件循环，各平台的适配器都挂在上面。
不碰 Qt：桌面动作和状态变化都通过回调交出去，由 im/qt.py 排到主线程。"""
import asyncio
import threading

from .discord_bot import DiscordAdapter
from .qq_bot import QQAdapter

ADAPTERS = {a.platform: a for a in (QQAdapter, DiscordAdapter)}

# cfg["im"] 的默认值。token / secret 只存在本地 config.json，不打日志、不显示在状态里
DEFAULTS = {
    "qq": {"enabled": False, "app_id": "", "secret": "", "allow_groups": [], "allow_users": []},
    "discord": {"enabled": False, "token": "", "allow_guilds": [], "allow_channels": [], "allow_users": []},
}


def settings(cfg, platform):
    """cfg["im"][platform]，缺的字段补默认值（原地写回 cfg，改了直接存）。"""
    sec = cfg.setdefault("im", {}).setdefault(platform, {})
    for k, v in DEFAULTS[platform].items():
        sec.setdefault(k, list(v) if isinstance(v, list) else v)
    return sec


def allowlist_args(platform, conf):
    """设置里的白名单 → Allowlist(groups, channels, users) 的参数。"""
    if platform == "discord":
        return conf.get("allow_guilds"), conf.get("allow_channels"), conf.get("allow_users")
    return conf.get("allow_groups"), (), conf.get("allow_users")


def available_platforms():
    return [p for p, a in ADAPTERS.items() if a.available()]


class Runner:
    def __init__(self, hub, on_status=None):
        self.hub = hub
        self.on_status = on_status
        self.loop = None
        self.thread = None
        self.tasks = {}       # 平台 → (adapter, asyncio.Task)

    def _ensure_loop(self):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            self.thread = threading.Thread(target=self.loop.run_forever, name="im", daemon=True)
            self.thread.start()

    def status(self, platform):
        entry = self.tasks.get(platform)
        return (entry[0].state, entry[0].detail) if entry else ("off", "未连接")

    def start(self, platform, conf):
        """连上一个平台（已经连着就先断开再连，用新设置）。"""
        cls = ADAPTERS[platform]
        if not (cls.available() and cls.configured(conf)):
            return False
        self.stop(platform)
        self._ensure_loop()
        adapter = cls(self.hub, conf, self.on_status)

        async def main():
            adapter.task = asyncio.current_task()
            try:
                await adapter.run()
            except asyncio.CancelledError:
                raise
            except Exception as e:     # 适配器自己没接住的，也只能变成状态，不能把线程带崩
                adapter.set_status("error", f"出错了：{str(e)[:80] or type(e).__name__}")
            else:
                if adapter.state != "error":
                    adapter.set_status("off", "已断开")

        fut = asyncio.run_coroutine_threadsafe(main(), self.loop)
        self.tasks[platform] = (adapter, fut)
        return True

    def stop(self, platform, timeout=5):
        entry = self.tasks.pop(platform, None)
        if not entry:
            return
        adapter, fut = entry

        async def halt():
            # 先让适配器自己体面地断开（Discord 下线、QQ 关 WebSocket），还没停就取消，等它收完尾
            try:
                await asyncio.wait_for(adapter.close(), timeout)
            except Exception:
                pass
            task = getattr(adapter, "task", None)
            if task is not None and not task.done():
                task.cancel()
                await asyncio.wait([task], timeout=timeout)
        try:
            asyncio.run_coroutine_threadsafe(halt(), self.loop).result(timeout * 2 + 1)
        except Exception:
            fut.cancel()
        adapter.set_status("off", "已断开")

    def stop_all(self):
        for p in list(self.tasks):
            self.stop(p, timeout=2)
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.loop = None
