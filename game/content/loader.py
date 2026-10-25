"""读取并校验 content/ 下的配置，产出 core 层的数据对象。

目录约定：
    content/tiles.toml                 格子类型（外观 + 落地事件）
    content/maps/<地图>/map.toml       节点、连线、坐标
    content/dice/<皮肤>/dice.toml      骰子外观
"""
import dataclasses
import os
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from game.core.graph import MapGraph, Node
from game.core.tiles import TileEvent, TileType
from .skins import DiceSkin

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTENT_DIR = os.path.join(getattr(sys, "_MEIPASS", _ROOT), "content")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ContentError(ValueError):
    pass


def _read(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ContentError(f"找不到配置文件 {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ContentError(f"{path} 格式错误：{e}") from None


def _color(path, where, value):
    if not isinstance(value, str) or not HEX_COLOR.match(value):
        raise ContentError(f"{path}：{where} 应为 #RRGGBB，现在是 {value!r}")
    return value


def load_tiles(root=CONTENT_DIR):
    path = os.path.join(root, "tiles.toml")
    data = _read(path)
    tiles = {}
    for tid, t in data.get("types", {}).items():
        if "name" not in t:
            raise ContentError(f"{path}：格子类型 {tid} 缺少 name")
        events = [TileEvent(coins=int(e.get("coins", 0)), say=str(e.get("say", "")),
                            skip_next=bool(e.get("skip_next", False)))
                  for e in t.get("events", [])]
        tiles[tid] = TileType(id=tid, name=t["name"], icon=t.get("icon", ""),
                              color=_color(path, f"格子类型 {tid} 的 color", t.get("color")),
                              events=events, random_expression=bool(t.get("random_expression", False)))
    if not tiles:
        raise ContentError(f"{path}：没有定义任何格子类型")
    return tiles


def load_map(map_id="classic", root=CONTENT_DIR, tiles=None):
    """读取地图。传入 tiles 时顺便检查节点类型都有定义。"""
    path = os.path.join(root, "maps", map_id, "map.toml")
    d = _read(path)
    raw = d.get("node", [])
    if not raw:
        raise ContentError(f"{path}：没有任何 [[node]]")
    grid = tuple(d["grid"]) if "grid" in d else None
    ids = [n.get("id") for n in raw]
    dup = {i for i in ids if ids.count(i) > 1}
    if None in ids or dup:
        raise ContentError(f"{path}：节点 id 缺失或重复 {sorted(i for i in dup if i)}")

    nodes = {}
    for i, n in enumerate(raw):
        nid = n["id"]
        if "cell" in n:
            if not grid:
                raise ContentError(f"{path}：节点 {nid} 用了 cell，但地图没有 grid")
            c, r = n["cell"]
            pos = ((c + 0.5) / grid[0], (r + 0.5) / grid[1])
        elif "pos" in n:
            pos = (float(n["pos"][0]), float(n["pos"][1]))
        else:
            raise ContentError(f"{path}：节点 {nid} 需要 pos 或 cell")
        nxt = list(n.get("next", []))
        if not nxt:
            # 没写 next 时默认连到下一个节点，最后一个在 loop 地图里连回第一个
            if i + 1 < len(raw):
                nxt = [ids[i + 1]]
            elif d.get("loop", False):
                nxt = [ids[0]]
        nodes[nid] = Node(id=nid, type=n.get("type", ""), pos=pos, next=nxt)

    graph = MapGraph(id=map_id, name=d.get("name", map_id), start=d.get("start", ids[0]),
                     canvas=tuple(d.get("canvas", (0, 0))), tile=float(d.get("tile", 78)),
                     nodes=nodes, grid=grid)
    _validate_map(graph, path, tiles)
    return graph


def _validate_map(g, path, tiles):
    if g.canvas[0] <= 0 or g.canvas[1] <= 0:
        raise ContentError(f"{path}：canvas 需要正的宽高")
    if g.start not in g.nodes:
        raise ContentError(f"{path}：起点 {g.start} 不存在")
    for n in g.nodes.values():
        if tiles is not None and n.type not in tiles:
            raise ContentError(f"{path}：节点 {n.id} 的类型 {n.type!r} 没有在 tiles.toml 里定义")
        if not n.next:
            raise ContentError(f"{path}：节点 {n.id} 没有出口，会卡住")
        if len(n.next) > 1:
            raise ContentError(f"{path}：节点 {n.id} 有多个出口，分岔要等规则支持路口选择后再开")
        for t in n.next:
            if t not in g.nodes:
                raise ContentError(f"{path}：节点 {n.id} 连向不存在的 {t}")
        x, y = n.pos
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ContentError(f"{path}：节点 {n.id} 的坐标超出 0~1")
    seen, todo = set(), [g.start]
    while todo:
        cur = todo.pop()
        if cur not in seen:
            seen.add(cur)
            todo.extend(g.nodes[cur].next)
    lost = [i for i in g.nodes if i not in seen]
    if lost:
        raise ContentError(f"{path}：从起点走不到这些节点 {lost}")


def load_dice_skin(skin_id="classic", root=CONTENT_DIR):
    skin_dir = os.path.join(root, "dice", skin_id)
    path = os.path.join(skin_dir, "dice.toml")
    d = _read(path)
    known = {f.name for f in dataclasses.fields(DiceSkin)} - {"id"}
    unknown = sorted(set(d) - known)
    if unknown:
        raise ContentError(f"{path}：不认识的字段 {unknown}")
    for key in ("body", "border_hot", "border_idle", "pip", "pip_one"):
        if key in d:
            _color(path, key, d[key])
    if d.get("face_dir"):
        face_dir = os.path.join(skin_dir, d["face_dir"])
        missing = [f"{i}.png" for i in range(1, 7)
                   if not os.path.isfile(os.path.join(face_dir, f"{i}.png"))]
        if missing:
            raise ContentError(f"{path}：face_dir 里缺少 {missing}")
        d["face_dir"] = face_dir
    d.setdefault("name", skin_id)
    return DiceSkin(id=skin_id, **d)


def _subdirs(path):
    if not os.path.isdir(path):
        return []
    return sorted(n for n in os.listdir(path) if os.path.isdir(os.path.join(path, n)))


def check_all(root=CONTENT_DIR):
    """加载全部内容，返回 (通过项, 错误) 两个列表。"""
    ok, errors = [], []
    try:
        tiles = load_tiles(root)
        ok.append(f"格子类型 {len(tiles)} 种")
    except ContentError as e:
        tiles = None
        errors.append(str(e))
    for map_id in _subdirs(os.path.join(root, "maps")):
        try:
            g = load_map(map_id, root, tiles)
            ok.append(f"地图 {map_id}（{g.name}）{len(g.nodes)} 个节点")
        except (ContentError, KeyError, TypeError, ValueError) as e:
            errors.append(f"地图 {map_id}：{e}")
    for skin_id in _subdirs(os.path.join(root, "dice")):
        try:
            s = load_dice_skin(skin_id, root)
            ok.append(f"骰子皮肤 {skin_id}（{s.name}）")
        except (ContentError, TypeError) as e:
            errors.append(f"骰子皮肤 {skin_id}：{e}")
    return ok, errors
