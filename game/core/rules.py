"""回合规则：掷骰、逐边移动、起点工资、落地事件。

UI 只调用这里的方法并播放返回的结果，不在绘制里随机或加钱。
"""
import random
from dataclasses import dataclass

from .dice import D6

START_WAGE = 3


@dataclass
class Hop:
    src: str
    dst: str
    wage: int = 0          # 这一步经过起点发的工资


@dataclass
class Landing:
    kind: str
    coins: int = 0
    say: str = ""
    expression: bool = False   # 让 UI 随机播一个表情


class Rules:
    def __init__(self, graph, tiles, dice=None, rng=None):
        self.graph = graph
        self.tiles = tiles
        self.dice = dice or D6()
        self.rng = rng or random.Random()

    def begin_turn(self, state):
        """开始一个回合：回合数 +1，返回点数；被恶作剧暂停时返回 None。"""
        state.turn += 1
        if state.skip_next:
            state.skip_next = False
            return None
        return self.dice.roll(self.rng)

    def hop(self, state):
        """沿默认出口走一条边，并结算这条边的起点工资。"""
        src = state.node_id
        dst = self.graph.next_of(src)
        wage = START_WAGE if self.graph.is_start_edge(src, dst) else 0
        state.node_id = dst
        state.coins += wage
        return Hop(src, dst, wage)

    def land(self, state):
        """回合终点的事件。起点工资已经在 hop 里发过，这里不再给。"""
        kind = self.graph.node(state.node_id).type
        tile = self.tiles[kind]
        if tile.random_expression:
            return Landing(kind, expression=True)
        if not tile.events:
            return Landing(kind)
        ev = self.rng.choice(tile.events)
        state.coins += ev.coins
        if ev.skip_next:
            state.skip_next = True
        return Landing(kind, coins=ev.coins, say=ev.say)
