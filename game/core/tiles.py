"""格子类型：外观字段 + 落地事件。

落地事件由几种积木组合，配置里一条事件可以同时写多种：
- coins：加减小鱼干（余额最低 0）
- say：台词
- expression：表情 key 或动作动画名（content/clips/clips.json），"random" 表示随机
- move：强制前进（正数）/ 后退（负数）几格，不触发落点事件，不发起点工资
- warp：传送到这张地图里第一个该类型的格子，不发起点工资
- skip_next：下回合歇着
"""
from dataclasses import dataclass, field


@dataclass
class TileEvent:
    coins: int = 0
    say: str = ""
    skip_next: bool = False
    expression: str = ""
    move: int = 0
    warp: str = ""
    weight: float = 1.0       # 抽中的相对概率


@dataclass
class TileType:
    id: str
    name: str
    icon: str
    color: str                            # "#RRGGBB"
    events: list = field(default_factory=list)   # TileEvent，落地按 weight 随机抽一个
    random_expression: bool = False       # 问号格：随机做一个表情
    symbol: str = ""                      # 石板上的矢量符号，空则用 icon
    desc: str = ""                        # 悬停时显示的效果说明
