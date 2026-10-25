"""地图图结构：节点 + 有向边。

坐标只用于画面，移动规则只看 next，不靠坐标推断相邻。
"""
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    type: str
    pos: tuple            # 归一化坐标 (0~1, 0~1)，相对地图画布
    next: list = field(default_factory=list)


@dataclass
class MapGraph:
    id: str
    name: str
    start: str
    canvas: tuple         # 地图画布逻辑尺寸 (w, h)
    tile: float           # 格子逻辑边长
    nodes: dict           # id -> Node，保持配置文件里的顺序
    grid: tuple = None    # 网格地图的 (列, 行)，自由地图为 None

    @property
    def order(self):
        return list(self.nodes)

    def node(self, node_id):
        return self.nodes[node_id]

    def next_of(self, node_id):
        """沿默认出口走一步。阶段 A 还没有分岔，取第一个出口。"""
        return self.nodes[node_id].next[0]

    def is_start_edge(self, a, b):
        """起点经过 = 正向走完一条进入起点的边。"""
        return b == self.start and b in self.nodes[a].next

    def legacy_node(self, index):
        """旧存档 board_pos 是外圈下标，按配置顺序映射到节点。"""
        order = self.order
        return order[int(index) % len(order)]

    def anchor(self, node_id):
        """节点中心在地图画布上的逻辑坐标。"""
        x, y = self.nodes[node_id].pos
        return x * self.canvas[0], y * self.canvas[1]
