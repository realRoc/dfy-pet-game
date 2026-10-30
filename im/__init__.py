"""IM 机器人：让桌宠的角色在 QQ / Discord 里用自己的身份聊天，聊到开心时桌面上的她也冒个泡。

结构（从里到外）：
- persona.py   角色人设（现在读 cordis.patch.yml 里 dfy-qq preset 的人设，角色包合并后改读角色包）
- limits.py    白名单、回复频率上限、桌面动作冷却
- core.py      平台无关的 Hub：收消息 → 过闸门 → 问 LLM（llm.py）→ 回复 + 可选桌面动作（control.py 的指令）
- base.py      平台适配器接口；discord_bot.py、qq_bot.py 是两个实现
- runner.py    后台线程里的 asyncio 循环，挂各平台的适配器
- qt.py        和桌宠接线（桌面动作排到主线程）、「🔗 连接 IM」设置窗

dsh + dsh-qqbot 那条 QQ 路线不经过这里，照旧用 cordis.patch.yml 的 dfy-qq preset 和 dsh/tool.js。"""
from .runner import available_platforms  # noqa: F401
