"""读取并校验 content/ 下的配置，产出 core 层的数据对象。

目录约定：
    content/tiles.toml                 格子类型（外观 + 落地事件）
    content/maps/<地图>/map.toml       节点、连线、坐标
    content/dice/<皮肤>/dice.toml      骰子外观
"""
import dataclasses
import math
import os
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

from game.core import spline
from game.core.graph import MapGraph, Node
from game.core.tiles import TileEvent, TileType
from .art_kinds import DECOR_KINDS, DICE_STYLES, SYMBOLS, TERRAIN_KINDS, TILE_STYLES
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


EVENT_FIELDS = {"coins", "say", "skip_next", "expression", "move", "warp", "weight"}


def _tile_event(path, tid, e):
    unknown = sorted(set(e) - EVENT_FIELDS)
    if unknown:
        raise ContentError(f"{path}：格子类型 {tid} 的事件里有不认识的字段 {unknown}，可用 {sorted(EVENT_FIELDS)}")
    ev = TileEvent(coins=int(e.get("coins", 0)), say=str(e.get("say", "")),
                   skip_next=bool(e.get("skip_next", False)), expression=str(e.get("expression", "")),
                   move=int(e.get("move", 0)), warp=str(e.get("warp", "")), weight=float(e.get("weight", 1)))
    if ev.move and ev.warp:
        raise ContentError(f"{path}：格子类型 {tid} 的同一条事件不能既 move 又 warp")
    if ev.weight <= 0:
        raise ContentError(f"{path}：格子类型 {tid} 的事件 weight 要大于 0")
    return ev


def load_tiles(root=CONTENT_DIR):
    path = os.path.join(root, "tiles.toml")
    data = _read(path)
    tiles = {}
    for tid, t in data.get("types", {}).items():
        if "name" not in t:
            raise ContentError(f"{path}：格子类型 {tid} 缺少 name")
        events = [_tile_event(path, tid, e) for e in t.get("events", [])]
        symbol = t.get("symbol", "")
        if symbol and symbol not in SYMBOLS:
            raise ContentError(f"{path}：格子类型 {tid} 的 symbol {symbol!r} 不认识，可选 {sorted(SYMBOLS)}")
        tiles[tid] = TileType(id=tid, name=t["name"], icon=t.get("icon", ""),
                              color=_color(path, f"格子类型 {tid} 的 color", t.get("color")),
                              events=events, random_expression=bool(t.get("random_expression", False)),
                              symbol=symbol, desc=str(t.get("desc", "")))
    if not tiles:
        raise ContentError(f"{path}：没有定义任何格子类型")
    return tiles


def _road_nodes(d, path, cw, ch):
    """[[road]]：沿一条平滑道路等距排格子。

    road 字段：id、zone（区域名）、points（道路控制点，画布像素）、nodes（格子类型列表），
    from（可选，道路从这个已有节点出发）、to（可选，道路最后连到这个已有节点）。
    节点 id 是 道路id + 两位序号。多条道路 from 同一个节点就形成岔路，先写的是默认出口。
    """
    nodes, edges, polylines = {}, [], []
    for r in d["road"]:
        rid, types, pts = r.get("id"), r.get("nodes", []), r.get("points", [])
        if not rid or not types or len(pts) < 2:
            raise ContentError(f"{path}：[[road]] 需要 id、nodes 和至少 2 个 points")
        poly = spline.sample([tuple(map(float, p)) for p in pts])
        frm, to = r.get("from"), r.get("to")
        offset = 1 if frm else 0
        segs = max(1, len(types) - 1 + offset + (1 if to else 0))
        ids = []
        for k, typ in enumerate(types):
            x, y = spline.at(poly, (k + offset) / segs)
            nid = f"{rid}{k:02d}"
            if nid in nodes:
                raise ContentError(f"{path}：节点 id {nid} 重复，检查道路 id")
            nodes[nid] = Node(id=nid, type=typ, pos=(x / cw, y / ch), next=[], zone=r.get("zone", ""))
            ids.append(nid)
        for a, b in zip(ids, ids[1:]):
            nodes[a].next.append(b)
        if frm:
            edges.append((frm, ids[0], frm, pts[0], rid))
        if to:
            edges.append((ids[-1], to, to, pts[-1], rid))
        polylines.append(poly)
    for a, b, joint, end, rid in edges:
        for nid in (a, b):
            if nid not in nodes:
                raise ContentError(f"{path}：道路 {rid} 连接的节点 {nid} 不存在")
        jx, jy = nodes[joint].pos
        if math.dist((jx * cw, jy * ch), end) > 40:
            raise ContentError(f"{path}：道路 {rid} 的端点 {end} 离连接节点 {joint} 太远，"
                               f"应该写成 [{jx * cw:.0f}, {jy * ch:.0f}]")
        nodes[a].next.append(b)
    return nodes, polylines


def load_map(map_id="classic", root=CONTENT_DIR, tiles=None):
    """读取地图。传入 tiles 时顺便检查节点类型都有定义。"""
    path = os.path.join(root, "maps", map_id, "map.toml")
    d = _read(path)
    raw = d.get("node", [])
    if not raw and not d.get("road"):
        raise ContentError(f"{path}：没有任何 [[node]] 或 [[road]]")
    grid = tuple(d["grid"]) if "grid" in d else None
    cw, ch = (float(v) for v in d.get("canvas", (0, 0)))
    # 网格格子铺在 grid_area = [x, y, w, h]（画布像素）里，默认铺满画布
    gx, gy, gw, gh = (float(v) for v in d.get("grid_area", (0, 0, cw, ch)))
    ids = [n.get("id") for n in raw]
    dup = {i for i in ids if ids.count(i) > 1}
    if None in ids or dup:
        raise ContentError(f"{path}：节点 id 缺失或重复 {sorted(i for i in dup if i)}")
    if cw <= 0 or ch <= 0:
        raise ContentError(f"{path}：canvas 需要正的宽高")

    nodes, roads = {}, []
    if d.get("road"):
        nodes, roads = _road_nodes(d, path, cw, ch)
        ids = list(nodes)
    for i, n in enumerate(raw):
        nid = n["id"]
        if "cell" in n:
            if not grid:
                raise ContentError(f"{path}：节点 {nid} 用了 cell，但地图没有 grid")
            c, r = n["cell"]
            pos = ((gx + (c + 0.5) * gw / grid[0]) / cw, (gy + (r + 0.5) * gh / grid[1]) / ch)
        elif "xy" in n:
            pos = (float(n["xy"][0]) / cw, float(n["xy"][1]) / ch)
        elif "pos" in n:
            pos = (float(n["pos"][0]), float(n["pos"][1]))
        else:
            raise ContentError(f"{path}：节点 {nid} 需要 xy、pos 或 cell")
        nxt = list(n.get("next", []))
        if not nxt:
            # 没写 next 时默认连到下一个节点，最后一个在 loop 地图里连回第一个
            if i + 1 < len(raw):
                nxt = [ids[i + 1]]
            elif d.get("loop", False):
                nxt = [ids[0]]
        nodes[nid] = Node(id=nid, type=n.get("type", ""), pos=pos, next=nxt)

    art_dir = os.path.join(root, "art", d["art_dir"]) if d.get("art_dir") else None
    art = {"terrain": d.get("terrain", []), "decor": d.get("decor", []),
           "palette": d.get("palette", {}), "path_width": float(d.get("path_width", 0)),
           "roads": roads, "art_dir": art_dir, "sprites": d.get("sprites", {}),
           "textures": d.get("textures", {}), "tile_sprites": d.get("tile_sprites", {})}
    graph = MapGraph(id=map_id, name=d.get("name", map_id), start=d.get("start", ids[0]),
                     canvas=(cw, ch), tile=float(d.get("tile", 78)), nodes=nodes, grid=grid,
                     subtitle=d.get("subtitle", ""),
                     window=tuple(float(v) for v in d["window"]) if "window" in d else None,
                     zoom=float(d.get("zoom", 1.0)), tilt=float(d.get("tilt", 1.0)),
                     fish_h=float(d.get("fish_h", 104)), dice=d.get("dice", "classic"),
                     tile_style=d.get("tile_style", "card"), art=art)
    _validate_map(graph, path, tiles)
    _validate_art(graph, path)
    return graph


def _art_file(g, path, name, what):
    if not g.art["art_dir"]:
        raise ContentError(f"{path}：用了贴图 {what}，但地图没有 art_dir")
    f = os.path.join(g.art["art_dir"], name)
    if not os.path.isfile(f):
        raise ContentError(f"{path}：{what} 的图片 {f} 不存在")
    return f


def _validate_art(g, path):
    if not 0.3 <= g.tilt <= 1.0:
        raise ContentError(f"{path}：tilt 应在 0.3~1.0 之间")
    if g.tile_style not in TILE_STYLES:
        raise ContentError(f"{path}：tile_style 只能是 {sorted(TILE_STYLES)}")
    for key, value in g.art["palette"].items():
        _color(path, f"palette.{key}", value)
    sprites = g.art["sprites"]
    for sid, s in sprites.items():
        if "file" not in s or "h" not in s:
            raise ContentError(f"{path}：贴图 {sid} 需要 file 和 h（在世界里的高度）")
        s["path"] = _art_file(g, path, s["file"], f"贴图 {sid}")
    for key, name in g.art["textures"].items():
        g.art["textures"][key] = _art_file(g, path, name, f"纹理 {key}")
    for kind, sid in g.art["tile_sprites"].items():
        if sid not in sprites:
            raise ContentError(f"{path}：tile_sprites.{kind} 引用了没定义的贴图 {sid}")
    for i, t in enumerate(g.art["terrain"]):
        kind = t.get("kind")
        if kind not in TERRAIN_KINDS:
            raise ContentError(f"{path}：第 {i + 1} 个 [[terrain]] 的 kind {kind!r} 不认识，可选 {sorted(TERRAIN_KINDS)}")
        if kind == "lake":
            if ("center" not in t or "radius" not in t) and len(t.get("points", [])) < 3:
                raise ContentError(f"{path}：湖需要 center + radius，或者至少 3 个 points")
        elif kind == "river":
            if len(t.get("points", [])) < 2:
                raise ContentError(f"{path}：河需要至少 2 个 points")
        elif len(t.get("points", [])) < 3:
            raise ContentError(f"{path}：{kind} 需要至少 3 个 points")
        for key in ("color", "cliff_color"):
            if key in t:
                _color(path, f"[[terrain]] {kind} 的 {key}", t[key])
        if "texture" in t and t["texture"] not in g.art["textures"]:
            raise ContentError(f"{path}：[[terrain]] {kind} 用了没登记的纹理 {t['texture']!r}")
    for i, dec in enumerate(g.art["decor"]):
        kind = dec.get("kind")
        if "sprite" in dec:
            if dec["sprite"] not in sprites:
                raise ContentError(f"{path}：第 {i + 1} 个 [[decor]] 引用了没定义的贴图 {dec['sprite']!r}")
        elif kind not in DECOR_KINDS:
            raise ContentError(f"{path}：第 {i + 1} 个 [[decor]] 的 kind {kind!r} 不认识，可选 {sorted(DECOR_KINDS)}")
        if len(dec.get("at", [])) != 2:
            raise ContentError(f"{path}：第 {i + 1} 个 [[decor]] 需要 at = [x, y]")


def _validate_map(g, path, tiles):
    if g.start not in g.nodes:
        raise ContentError(f"{path}：起点 {g.start} 不存在")
    for n in g.nodes.values():
        if tiles is not None and n.type not in tiles:
            raise ContentError(f"{path}：节点 {n.id} 的类型 {n.type!r} 没有在 tiles.toml 里定义")
        if tiles is not None:
            for ev in tiles[n.type].events:
                if ev.warp and g.first_of_type(ev.warp) is None:
                    raise ContentError(f"{path}：{n.type} 格的事件会传送到 {ev.warp!r} 格，但这张地图里没有")
        if not n.next:
            raise ContentError(f"{path}：节点 {n.id} 没有出口，会卡住")
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
    for key in ("body", "side", "border_hot", "border_idle", "pip", "pip_one"):
        if key in d:
            _color(path, key, d[key])
    if d.get("style", "flat") not in DICE_STYLES:
        raise ContentError(f"{path}：style 只能是 {sorted(DICE_STYLES)}")
    if d.get("face_dir"):
        face_dir = os.path.join(skin_dir, d["face_dir"])
        missing = [f"{i}.png" for i in range(1, 7)
                   if not os.path.isfile(os.path.join(face_dir, f"{i}.png"))]
        if missing:
            raise ContentError(f"{path}：face_dir 里缺少 {missing}")
        d["face_dir"] = face_dir
    d.setdefault("name", skin_id)
    return DiceSkin(id=skin_id, **d)


def map_names(root=CONTENT_DIR):
    """{地图目录名: 显示名}，只读名字，不做完整加载（给菜单用）。"""
    out = {}
    for map_id in _subdirs(os.path.join(root, "maps")):
        try:
            out[map_id] = _read(os.path.join(root, "maps", map_id, "map.toml")).get("name", map_id)
        except ContentError:
            continue
    return out


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
    skins = set(_subdirs(os.path.join(root, "dice")))
    for map_id in _subdirs(os.path.join(root, "maps")):
        try:
            g = load_map(map_id, root, tiles)
            if g.dice not in skins:
                raise ContentError(f"默认骰子皮肤 {g.dice!r} 不存在")
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
