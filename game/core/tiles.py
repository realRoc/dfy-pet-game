"""格子类型：外观字段 + 落地事件。"""
from dataclasses import dataclass, field


@dataclass
class TileEvent:
    coins: int = 0
    say: str = ""
    skip_next: bool = False


@dataclass
class TileType:
    id: str
    name: str
    icon: str
    color: str                            # "#RRGGBB"
    events: list = field(default_factory=list)   # TileEvent，落地随机抽一个
    random_expression: bool = False       # 问号格：随机做一个表情
