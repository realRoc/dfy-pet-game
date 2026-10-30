"""后宅：一个等距视角的小房间，摆家具、凑套装。

几块：
- 家具目录：content/room/catalog.json（家具、套装、姿势库、墙纸、地板）。家具都是网页里按 boxes 用代码画的原创图，
  可以商用；家具不带角色动画，只声明「姿势槽位」（slots），角色走过去按姿势库里的标准姿势待着。
- 布局：摆了哪些家具、在哪、朝哪，选了哪种墙纸地板，存在 DATA_DIR/room.json。规则（不出界、不重叠）在这里校验，
  网页那边只是预判，以这里为准。
- 套装：套装里每件都摆上了就算集齐，网页显示进度、集齐时提示。
- RoomAPI：网页用的全部接口（目录、状态、改布局），只收发 JSON 能表示的东西，不碰传输。
  现在由 RoomServer 包成 127.0.0.1 上的 HTTP 服务，网页用系统浏览器打开；以后迁到 Electron 时换成 IPC，接口不变。
这个模块不依赖 Qt。
"""
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from character import CHAR

_HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(_HERE, "content", "room", "catalog.json")
PAGE_PATH = os.path.join(_HERE, "content", "room", "index.html")
LAYOUT_VERSION = 1
MAX_PLACED = 120
MAX_BODY = 64 * 1024
LAYERS = ("object", "rug")   # 地毯和家具互不挡，地毯和地毯、家具和家具不能叠


class LayoutError(ValueError):
    pass


def load_catalog(path=CATALOG_PATH):
    with open(path, encoding="utf-8") as f:
        cat = json.load(f)
    cat["by_id"] = {it["id"]: it for it in cat["items"]}
    return cat


def validate_catalog(cat):
    """目录自查：返回错误列表。测试和改目录的人用。"""
    errors = []
    sets = {s["id"] for s in cat["sets"]}
    w, d = cat["room"]["w"], cat["room"]["d"]
    seen = set()
    for it in cat["items"]:
        iid = it.get("id")
        if not iid or iid in seen:
            errors.append(f"家具 id 缺失或重复: {iid}")
        seen.add(iid)
        sx, sy = it.get("size", (0, 0))
        if not (isinstance(sx, int) and isinstance(sy, int) and 1 <= sx <= w and 1 <= sy <= d):
            errors.append(f"{iid}: size 要是房间以内的正整数格")
        if it.get("layer") not in LAYERS:
            errors.append(f"{iid}: layer 只能是 {LAYERS}")
        if it.get("set") and it["set"] not in sets:
            errors.append(f"{iid}: 没有套装 {it['set']}")
        if not it.get("name"):
            errors.append(f"{iid}: 缺 name")
        if not it.get("boxes"):
            errors.append(f"{iid}: 没有 boxes，画不出来")
        for b in it.get("boxes", []):
            (bx, by, _), (bw, bd, bh) = b["at"], b["size"]
            if bx < 0 or by < 0 or bx + bw > sx + 1e-9 or by + bd > sy + 1e-9 or min(bw, bd, bh) <= 0:
                errors.append(f"{iid}: box {b} 超出占地或尺寸不对")
        for s in it.get("slots", []):
            if s.get("pose") not in cat["poses"]:
                errors.append(f"{iid}: 槽位姿势 {s.get('pose')} 不在姿势库里")
            ax, ay = s.get("at", (None, None))
            if ax is None or not (-1 <= ax <= sx + 1 and -1 <= ay <= sy + 1):
                errors.append(f"{iid}: 槽位 {s} 离家具太远")
    for s in cat["sets"]:
        if not any(it.get("set") == s["id"] for it in cat["items"]):
            errors.append(f"套装 {s['id']} 里一件家具都没有")
    for key in ("wallpapers", "floors"):
        if not cat.get(key):
            errors.append(f"缺 {key}")
    return errors


def footprint(item, rot):
    """转了 rot 个 90° 之后占几格 (宽, 深)。"""
    sx, sy = item["size"]
    return (sy, sx) if rot % 2 else (sx, sy)


def default_layout(cat):
    return {"version": LAYOUT_VERSION, "wallpaper": cat["wallpapers"][0]["id"], "floor": cat["floors"][0]["id"],
            "placed": []}


def validate_layout(cat, data):
    """校验并规整一份布局（网页发来的、或者存档读出来的），不合规抛 LayoutError。"""
    if not isinstance(data, dict):
        raise LayoutError("布局要是一个对象")
    wallpapers = {x["id"] for x in cat["wallpapers"]}
    floors = {x["id"] for x in cat["floors"]}
    wallpaper = data.get("wallpaper", cat["wallpapers"][0]["id"])
    floor = data.get("floor", cat["floors"][0]["id"])
    if wallpaper not in wallpapers:
        raise LayoutError(f"没有这种墙纸: {wallpaper}")
    if floor not in floors:
        raise LayoutError(f"没有这种地板: {floor}")
    placed = data.get("placed", [])
    if not isinstance(placed, list):
        raise LayoutError("placed 要是数组")
    if len(placed) > MAX_PLACED:
        raise LayoutError(f"最多摆 {MAX_PLACED} 件")
    w, d = cat["room"]["w"], cat["room"]["d"]
    grid = {layer: {} for layer in LAYERS}
    out, uids = [], set()
    for p in placed:
        if not isinstance(p, dict):
            raise LayoutError("每件家具要是一个对象")
        uid, iid = p.get("id"), p.get("item")
        item = cat["by_id"].get(iid)
        if item is None:
            raise LayoutError(f"没有这件家具: {iid}")
        if not isinstance(uid, str) or not uid or len(uid) > 40 or uid in uids:
            raise LayoutError(f"家具实例 id 缺失或重复: {uid}")
        uids.add(uid)
        x, y, rot = p.get("x"), p.get("y"), p.get("rot", 0)
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, rot)) or rot not in (0, 1, 2, 3):
            raise LayoutError(f"{item['name']}: 位置和朝向要是整数（rot 0~3）")
        fw, fd = footprint(item, rot)
        if x < 0 or y < 0 or x + fw > w or y + fd > d:
            raise LayoutError(f"{item['name']} 出界了")
        cells = grid[item["layer"]]
        for cx in range(x, x + fw):
            for cy in range(y, y + fd):
                if (cx, cy) in cells:
                    raise LayoutError(f"{item['name']} 和 {cells[(cx, cy)]} 叠在一起了")
                cells[(cx, cy)] = item["name"]
        out.append({"id": uid, "item": iid, "x": x, "y": y, "rot": rot})
    return {"version": LAYOUT_VERSION, "wallpaper": wallpaper, "floor": floor, "placed": out}


def sets_progress(cat, layout):
    """每个套装摆了几件、还差哪几件、集齐没有。"""
    have = {p["item"] for p in layout["placed"]}
    out = []
    for s in cat["sets"]:
        members = [it["id"] for it in cat["items"] if it.get("set") == s["id"]]
        missing = [m for m in members if m not in have]
        out.append({"id": s["id"], "name": s["name"], "have": len(members) - len(missing), "total": len(members),
                    "complete": not missing, "missing": missing})
    return out


class RoomStore:
    """布局存档，线程安全（HTTP 服务在后台线程里读写）。"""

    def __init__(self, path, cat=None):
        self.path = path
        self.cat = cat or load_catalog()
        self._lock = threading.Lock()
        self._layout = self._read()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return validate_layout(self.cat, json.load(f))
        except FileNotFoundError:
            pass
        except Exception as e:   # 坏档、目录改了导致旧档不合规：从空房间开始，旧档留个备份
            print("后宅存档读不了，从空房间开始:", e)
            try:
                os.replace(self.path, self.path + ".bad")
            except OSError:
                pass
        return default_layout(self.cat)

    def layout(self):
        with self._lock:
            return json.loads(json.dumps(self._layout))

    def save(self, data):
        """校验、写盘，返回规整后的布局；不合规抛 LayoutError，原布局不动。"""
        layout = validate_layout(self.cat, data)
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(layout, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
            self._layout = layout
        return layout


class RoomAPI:
    """网页的全部接口。HTTP 和以后的 Electron IPC 都只是把这三个方法包一层。"""

    def __init__(self, store, char=CHAR):
        self.store = store
        self.char = char

    def catalog(self):
        cat = self.store.cat
        return {k: cat[k] for k in ("format", "license", "room", "poses", "wallpapers", "floors", "sets", "items")}

    def state(self):
        c = self.char
        layout = self.store.layout()
        return {
            "layout": layout,
            "sets": sets_progress(self.store.cat, layout),
            "character": {"id": c.id, "name": c.name, "side_faces": c.side_faces,
                          "sprites": {v: f"/character/{v}.png" for v in ("front", "side", "back")}},
        }

    def put_layout(self, data):
        layout = self.store.save(data)
        return {"layout": layout, "sets": sets_progress(self.store.cat, layout)}


class RoomServer:
    """把 RoomAPI 包成 127.0.0.1 上的 HTTP 服务，后台线程跑。

    只听本机；要求 Host 是 127.0.0.1 / localhost（挡 DNS rebinding）；/api/ 下都要带启动时生成的 token
    （网页地址里 ?t= 给的），本机别的网页拿不到 token，就读写不了布局。"""

    def __init__(self, api, page=PAGE_PATH):
        self.api, self.page = api, page
        self.token = secrets.token_urlsafe(16)
        self.httpd = None
        self.thread = None

    @property
    def port(self):
        return self.httpd.server_address[1] if self.httpd else None

    def url(self):
        return f"http://127.0.0.1:{self.port}/?t={self.token}"

    def start(self, port=0):
        if self.httpd:
            return self
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(self))
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="room-server", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


def _make_handler(server):
    api = server.api

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):   # 不往终端刷访问日志
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            return host in ("127.0.0.1", "localhost")

        def _route(self, method):
            if not self._host_ok():
                return self._send(403, {"error": "只接受本机访问"})
            path = self.path.split("?", 1)[0]
            if path.startswith("/api/"):
                if not secrets.compare_digest(self.headers.get("X-Room-Token", ""), server.token):
                    return self._send(403, {"error": "token 不对"})
                if method == "GET" and path == "/api/catalog":
                    return self._send(200, api.catalog())
                if method == "GET" and path == "/api/state":
                    return self._send(200, api.state())
                if method == "PUT" and path == "/api/layout":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n <= 0 or n > MAX_BODY:
                        return self._send(413, {"error": "请求太大或为空"})
                    try:
                        data = json.loads(self.rfile.read(n))
                        return self._send(200, api.put_layout(data))
                    except LayoutError as e:
                        return self._send(400, {"error": str(e)})
                    except ValueError:
                        return self._send(400, {"error": "不是合法的 JSON"})
                return self._send(404, {"error": "没有这个接口"})
            if method != "GET":
                return self._send(405, {"error": "不支持"})
            if path in ("/", "/index.html"):
                try:
                    with open(server.page, "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                except OSError:
                    return self._send(404, "后宅网页还没打包：在 room/ 里跑 npm run release".encode(),
                                      "text/plain; charset=utf-8")
            view = path[len("/character/"):-len(".png")] if path.startswith("/character/") and path.endswith(".png") else None
            if view in ("front", "side", "back"):
                try:
                    with open(api.char.sprite(view), "rb") as f:
                        return self._send(200, f.read(), "image/png")
                except OSError:
                    pass
            return self._send(404, {"error": "没有这个文件"})

        def do_GET(self):
            self._route("GET")

        def do_PUT(self):
            self._route("PUT")

        def do_POST(self):
            self._route("POST")

    return Handler
