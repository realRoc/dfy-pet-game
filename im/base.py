"""平台适配器的接口。一个适配器 = 一个平台的一个机器人连接，跑在 Runner 的 asyncio 线程里。

子类实现：
- available()：依赖装没装（没装就不出现这个平台的入口）
- configured(conf)：设置里填够了没有
- run()：连上平台、收消息、交给 hub.handle、把 Outcome.reply 发回去；一直跑到断开或出错
- close()：让 run() 尽快返回

状态只有四种：off（没开）/ connecting / online / error，detail 是给人看的一句话，**不能带 token**。"""


class Adapter:
    platform = ""
    label = ""

    def __init__(self, hub, conf, on_status=None):
        self.hub = hub
        self.conf = dict(conf)
        self.on_status = on_status
        self.state, self.detail = "off", "未连接"

    @staticmethod
    def available():
        return False

    @staticmethod
    def configured(conf):
        return False

    def set_status(self, state, detail):
        for secret in self.secrets():
            if secret:
                detail = detail.replace(secret, "***")
        self.state, self.detail = state, detail
        if self.on_status:
            self.on_status(self.platform, state, detail)

    def secrets(self):
        """会出现在报错里、要打码的值。"""
        return [v for k, v in self.conf.items() if k in ("token", "secret") and isinstance(v, str)]

    async def run(self):
        raise NotImplementedError

    async def close(self):
        pass
