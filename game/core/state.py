"""棋盘存档状态，以及和旧配置字段（board_pos 等）的兼容。"""
from dataclasses import dataclass


@dataclass
class BoardState:
    node_id: str
    coins: int = 0
    turn: int = 0
    skip_next: bool = False

    @classmethod
    def from_cfg(cls, cfg, graph):
        node = cfg.get("board_node")
        saved_map = cfg.get("board_map")
        if saved_map not in (None, graph.id):
            node = graph.start          # 换了地图，从新地图起点出发
        elif node not in graph.nodes:
            node = graph.legacy_node(cfg.get("board_pos", 0) or 0)
        return cls(node_id=node,
                   coins=int(cfg.get("board_coins", 0) or 0),
                   turn=int(cfg.get("board_turn", 0) or 0),
                   skip_next=bool(cfg.get("board_skip_next", False)))

    def to_cfg(self, graph):
        return {
            "board_map": graph.id,
            "board_node": self.node_id,
            # 旧字段继续写，回退到旧版本时位置不丢
            "board_pos": graph.order.index(self.node_id),
            "board_coins": self.coins,
            "board_turn": self.turn,
            "board_skip_next": self.skip_next,   # 下回合暂停，存档里也要记住，重启不能绕过
        }
