"""回合规则：掷骰、逐边移动、起点工资、落地事件。

UI 只调用这里的方法并播放返回的结果，不在绘制里随机或加钱。
落地事件的结果（小鱼干、位置、暂停）在 land() 里一次写进状态，UI 之后只播动画。
"""
import random
from dataclasses import dataclass, field

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
    expression: str = ""   # 表情 key，"random" 表示随机，空为不做
    path: list = field(default_factory=list)   # 强制移动经过的节点（不含出发点），最后一个是新位置
    warp_to: str = ""      # 传送到的节点


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

    def hop(self, state, dst=None):
        """沿一条边走一步，并结算这条边的起点工资。岔路上必须指定 dst。"""
        src = state.node_id
        exits = self.graph.exits(src)
        if dst is None:
            if len(exits) > 1:
                raise ValueError(f"{src} 是岔路，需要选择出口 {exits}")
            dst = exits[0]
        elif dst not in exits:
            raise ValueError(f"{src} 不能直接走到 {dst}")
        wage = START_WAGE if self.graph.is_start_edge(src, dst) else 0
        state.node_id = dst
        state.coins += wage
        return Hop(src, dst, wage)

    def forced_path(self, node_id, steps):
        """强制移动的路线：前进走默认出口，后退走第一个来路。"""
        path, cur = [], node_id
        for _ in range(abs(steps)):
            cur = self.graph.next_of(cur) if steps > 0 else self.graph.prev_of(cur)
            if cur is None:
                break
            path.append(cur)
        return path

    def land(self, state):
        """回合终点的事件。起点工资已经在 hop 里发过，这里不再给。"""
        kind = self.graph.node(state.node_id).type
        tile = self.tiles[kind]
        if tile.random_expression:
            return Landing(kind, expression="random")
        if not tile.events:
            return Landing(kind)
        ev = self.rng.choices(tile.events, weights=[e.weight for e in tile.events])[0]
        before = state.coins
        state.coins = max(0, state.coins + ev.coins)
        if ev.skip_next:
            state.skip_next = True
        landing = Landing(kind, coins=state.coins - before, say=ev.say, expression=ev.expression)
        if ev.move:
            landing.path = self.forced_path(state.node_id, ev.move)
            if landing.path:
                state.node_id = landing.path[-1]
        elif ev.warp:
            target = self.graph.first_of_type(ev.warp)
            if target and target != state.node_id:
                landing.warp_to = target
                state.node_id = target
        return landing
