"""地图图结构：节点 + 有向边。

坐标只用于画面，移动规则只看 next，不靠坐标推断相邻。
一个节点可以有多个出口（岔路），走到这里且还有步数时由玩家选择。
"""
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    type: str
    pos: tuple            # 归一化坐标 (0~1, 0~1)，相对地图画布
    next: list = field(default_factory=list)
    zone: str = ""        # 所在区域 / 道路名，岔路选择时显示


@dataclass
class MapGraph:
    id: str
    name: str
    start: str
    canvas: tuple         # 地图画布（世界）逻辑尺寸 (w, h)
    tile: float           # 格子逻辑边长
    nodes: dict           # id -> Node，保持配置文件里的顺序
    grid: tuple = None    # 网格地图的 (列, 行)，自由地图为 None
    subtitle: str = ""
    window: tuple = None  # 默认窗口逻辑尺寸；None 表示和画布一样大
    zoom: float = 1.0     # 默认镜头缩放（屏幕像素 / 世界像素）
    tilt: float = 1.0     # 镜头倾斜：地面纵向压缩比例，1 是正俯视，越小越像从斜上方看
    fish_h: float = 104   # 角色在画布上的高度
    dice: str = "classic"         # 这张地图默认的骰子皮肤
    tile_style: str = "card"      # card：彩色方块；stone：矢量石板；sprite：贴图石板
    art: dict = field(default_factory=dict)   # 地形、装饰、色板、贴图，交给绘制层解释

    @property
    def order(self):
        return list(self.nodes)

    def node(self, node_id):
        return self.nodes[node_id]

    def exits(self, node_id):
        return self.nodes[node_id].next

    def is_fork(self, node_id):
        return len(self.nodes[node_id].next) > 1

    def next_of(self, node_id):
        """默认出口（第一个）。"""
        return self.nodes[node_id].next[0]

    def prev_of(self, node_id):
        """第一个连到 node_id 的节点（按配置顺序）；没有来路时为 None。"""
        for nid, n in self.nodes.items():
            if node_id in n.next:
                return nid
        return None

    def first_of_type(self, kind):
        for nid, n in self.nodes.items():
            if n.type == kind:
                return nid
        return None

    def path_from(self, node_id, steps):
        """沿默认出口走 steps 步经过的节点（不含出发点）。"""
        path, cur = [], node_id
        for _ in range(steps):
            cur = self.next_of(cur)
            path.append(cur)
        return path

    def destinations(self, node_id, steps):
        """走 steps 步所有可能的终点（考虑每个岔路）。"""
        cur = {node_id}
        for _ in range(steps):
            cur = {n for c in cur for n in self.nodes[c].next}
        return cur

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
