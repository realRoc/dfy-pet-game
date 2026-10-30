"""IM 会话的闸门：白名单、回复频率上限、桌面动作冷却。都是纯逻辑，时间从外面传进来，好测。"""
import collections
import time

# 回复频率上限的默认值：防止有人在群里刷屏、把主人的 DeepSeek 额度刷光
DEFAULT_LIMITS = {
    "per_user_per_min": 4,    # 同一个人一分钟最多几条回复
    "global_per_min": 20,     # 所有人加起来一分钟最多几条
    "global_per_day": 300,    # 一天最多几条
}
# 和 dsh 那条路线（dsh/bridge.js 的 COOLDOWN_MS）一样：IM 里的她多久能让桌面上的自己动一次
DESKTOP_COOLDOWN = 20.0


class Window:
    """滑动窗口计数：window 秒内最多 limit 次。"""

    def __init__(self, limit, window):
        self.limit, self.window = int(limit), float(window)
        self.hits = collections.deque()

    def _trim(self, now):
        while self.hits and now - self.hits[0] >= self.window:
            self.hits.popleft()

    def allows(self, now):
        self._trim(now)
        return self.limit > 0 and len(self.hits) < self.limit

    def hit(self, now):
        self.hits.append(now)


class RateLimiter:
    """每人每分钟、全局每分钟、全局每天三道上限。check() 只看不记，记账用 hit()：
    被白名单拦掉、没 @ 她的消息都不该占额度，所以先 check 再真正回复时 hit。"""

    def __init__(self, limits=None):
        lim = dict(DEFAULT_LIMITS, **(limits or {}))
        self.per_user = lim["per_user_per_min"]
        self.users = {}
        self.minute = Window(lim["global_per_min"], 60)
        self.day = Window(lim["global_per_day"], 86400)

    def _user(self, key):
        w = self.users.get(key)
        if w is None:
            if len(self.users) > 2000:   # 别让陌生人的计数无限长下去
                self.users.clear()
            w = self.users[key] = Window(self.per_user, 60)
        return w

    def check(self, user_key, now=None):
        """返回 None 表示可以回；否则返回原因 "user" / "minute" / "day"。"""
        now = time.monotonic() if now is None else now
        if not self.day.allows(now):
            return "day"
        if not self.minute.allows(now):
            return "minute"
        if not self._user(user_key).allows(now):
            return "user"
        return None

    def hit(self, user_key, now=None):
        now = time.monotonic() if now is None else now
        for w in (self.day, self.minute, self._user(user_key)):
            w.hit(now)


def _ids(values):
    return {str(v).strip() for v in (values or []) if str(v).strip()}


class Allowlist:
    """可选白名单。三个列表都空 = 谁都能找她。
    填了任何一个，就只放行：群 / 服务器在 groups 里（填了的话）、频道在 channels 里（填了的话）、人在 users 里（填了的话）；
    私聊没有群和频道，这时只认 users——只限制了群没写人的话，私聊一律不回，免得陌生人私聊绕过白名单。"""

    def __init__(self, groups=(), channels=(), users=()):
        self.groups, self.channels, self.users = _ids(groups), _ids(channels), _ids(users)

    @property
    def open(self):
        return not (self.groups or self.channels or self.users)

    def allows(self, user, group=None, channel=None, dm=False):
        if self.open:
            return True
        if dm:
            return str(user) in self.users
        if self.groups and str(group) not in self.groups:
            return False
        if self.channels and str(channel) not in self.channels:
            return False
        if self.users and str(user) not in self.users:
            return False
        return True


class Cooldown:
    """桌面动作冷却：seconds 秒内只放行一次（所有平台共用一个）。"""

    def __init__(self, seconds=DESKTOP_COOLDOWN):
        self.seconds = seconds
        self.last = None

    def take(self, now=None):
        now = time.monotonic() if now is None else now
        if self.last is not None and now - self.last < self.seconds:
            return False
        self.last = now
        return True
