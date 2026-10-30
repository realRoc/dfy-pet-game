"""后宅：家具目录、布局校验、舒适度和套装、存档读写、本机 HTTP 接口，以及桌宠里的入口。
网页本身的测试在 room/ 里（npm test）。运行：python -m unittest discover -s tests"""
import hashlib
import http.client
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import room

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOM_SRC = os.path.join(ROOT, "room")
ROOM_OUT = os.path.join(ROOT, "content", "room")


def place(uid, item, x, y, rot=0):
    return {"id": uid, "item": item, "x": x, "y": y, "rot": rot}


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.cat = room.load_catalog()

    def test_catalog_is_valid(self):
        self.assertEqual(room.validate_catalog(self.cat), [])

    def test_catalog_size_and_sets(self):
        self.assertTrue(10 <= len(self.cat["items"]) <= 15)
        self.assertTrue(2 <= len(self.cat["sets"]) <= 3)

    def test_catalog_is_original_and_commercial(self):
        """家具是代码画的原创图，商业版能直接带。"""
        self.assertTrue(self.cat["license"]["commercial"])
        for it in self.cat["items"]:
            self.assertNotIn("image", it, it["id"])   # 只有 boxes，没有外部图片

    def test_slots_only_use_pose_library(self):
        poses = set(self.cat["poses"])
        for it in self.cat["items"]:
            for s in it.get("slots", []):
                self.assertIn(s["pose"], poses)

    def test_validate_catalog_finds_problems(self):
        bad = json.loads(json.dumps({k: v for k, v in self.cat.items() if k != "by_id"}))
        bad["items"][0]["slots"] = [{"pose": "dance", "at": [0, 0]}]
        bad["items"][1]["set"] = "nope"
        bad["items"][2]["size"] = [0, 1]
        errors = "\n".join(room.validate_catalog(bad))
        self.assertIn("dance", errors)
        self.assertIn("nope", errors)
        self.assertIn("size", errors)


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.cat = room.load_catalog()

    def layout(self, *placed, **kw):
        return dict({"wallpaper": "wall_sea", "floor": "floor_wood", "placed": list(placed)}, **kw)

    def test_valid_layout_is_normalized(self):
        out = room.validate_layout(self.cat, self.layout(place("a", "shell_bed", 0, 0)))
        self.assertEqual(out["version"], room.LAYOUT_VERSION)
        self.assertEqual(out["placed"], [place("a", "shell_bed", 0, 0)])

    def test_out_of_bounds(self):
        with self.assertRaisesRegex(room.LayoutError, "出界"):
            room.validate_layout(self.cat, self.layout(place("a", "shell_bed", 7, 0)))
        with self.assertRaisesRegex(room.LayoutError, "出界"):
            room.validate_layout(self.cat, self.layout(place("a", "coral_stool", -1, 0)))

    def test_rotation_swaps_footprint(self):
        # 2×3 的床转 90° 变成 3×2：放在 x=5 正好贴墙，不转就会出界
        room.validate_layout(self.cat, self.layout(place("a", "shell_bed", 5, 0, rot=1)))
        with self.assertRaisesRegex(room.LayoutError, "出界"):
            room.validate_layout(self.cat, self.layout(place("a", "shell_bed", 6, 0, rot=1)))
        self.assertEqual(room.footprint(self.cat["by_id"]["shell_bed"], 3), (3, 2))

    def test_overlap_same_layer(self):
        with self.assertRaisesRegex(room.LayoutError, "叠在一起"):
            room.validate_layout(self.cat, self.layout(place("a", "shell_bed", 0, 0), place("b", "coral_stool", 1, 2)))

    def test_rug_under_furniture_is_fine(self):
        room.validate_layout(self.cat, self.layout(place("a", "round_rug", 2, 2), place("b", "coral_stool", 3, 3)))
        with self.assertRaisesRegex(room.LayoutError, "叠在一起"):
            room.validate_layout(self.cat, self.layout(place("a", "round_rug", 2, 2), place("b", "lifebuoy_rug", 3, 3)))

    def test_rejects_bad_input(self):
        cases = [
            (self.layout(place("a", "sofa_x", 0, 0)), "没有这件家具"),
            (self.layout(place("a", "coral_stool", 0, 0), place("a", "pothos", 3, 3)), "重复"),
            (self.layout(place("a", "coral_stool", 0.5, 0)), "整数"),
            (self.layout(place("a", "coral_stool", 0, 0, rot=4)), "整数"),
            (self.layout(place("a", "coral_stool", True, 0)), "整数"),
            (self.layout(wallpaper="gold"), "墙纸"),
            (self.layout(floor="lava"), "地板"),
            ({"placed": "x"}, "数组"),
            ([], "对象"),
        ]
        for data, msg in cases:
            with self.assertRaisesRegex(room.LayoutError, msg, msg=str(data)):
                room.validate_layout(self.cat, data)

    def test_too_many_items(self):
        many = [place(f"p{i}", "pothos", i % 8, i // 8 % 8) for i in range(room.MAX_PLACED + 1)]
        with self.assertRaisesRegex(room.LayoutError, "最多"):
            room.validate_layout(self.cat, self.layout(*many))


class SetsTest(unittest.TestCase):
    def setUp(self):
        self.cat = room.load_catalog()

    def progress(self, *placed):
        sets = room.sets_progress(self.cat, room.validate_layout(self.cat, {"placed": list(placed)}))
        return {x["id"]: x for x in sets}

    def test_empty_room(self):
        p = self.progress()
        self.assertEqual(set(p), {s["id"] for s in self.cat["sets"]})
        self.assertTrue(all(x["have"] == 0 and not x["complete"] for x in p.values()))

    def test_complete_only_when_every_piece_is_placed(self):
        gym = [it["id"] for it in self.cat["items"] if it.get("set") == "gym"]
        spots = [(0, 0), (2, 0), (4, 0)]
        gs = self.progress(*[place(f"g{i}", iid, *spots[i]) for i, iid in enumerate(gym[:-1])])["gym"]
        self.assertEqual((gs["have"], gs["total"], gs["complete"]), (len(gym) - 1, len(gym), False))
        self.assertEqual(gs["missing"], [gym[-1]])
        gs = self.progress(*[place(f"g{i}", iid, *spots[i]) for i, iid in enumerate(gym)])["gym"]
        self.assertTrue(gs["complete"])
        self.assertEqual(gs["missing"], [])

    def test_duplicates_count_once(self):
        p = self.progress(place("a", "coral_stool", 0, 0), place("b", "coral_stool", 1, 0))
        self.assertEqual(p["seaside"]["have"], 1)

    def test_full_room_completes_every_set(self):
        spots = iter([(0, 0), (2, 0), (5, 0), (0, 3), (2, 3), (4, 3), (6, 2), (7, 0), (0, 6), (2, 6),
                      (4, 6), (6, 5), (7, 7), (5, 5)])
        placed = [place(f"i{n}", it["id"], *next(spots)) for n, it in enumerate(self.cat["items"])]
        self.assertTrue(all(x["complete"] for x in self.progress(*placed).values()))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, "sub", "room.json")

    def test_new_store_is_empty_room(self):
        s = room.RoomStore(self.path)
        self.assertEqual(s.layout()["placed"], [])
        self.assertFalse(os.path.exists(self.path))

    def test_save_and_reload(self):
        s = room.RoomStore(self.path)
        layout = s.save({"floor": "floor_tile", "placed": [place("a", "beanbag", 3, 3, 2)]})
        self.assertEqual(layout["floor"], "floor_tile")
        again = room.RoomStore(self.path)
        self.assertEqual(again.layout(), layout)

    def test_invalid_save_keeps_old_layout(self):
        s = room.RoomStore(self.path)
        s.save({"placed": [place("a", "beanbag", 3, 3)]})
        with self.assertRaises(room.LayoutError):
            s.save({"placed": [place("a", "beanbag", 9, 9)]})
        self.assertEqual(s.layout()["placed"], [place("a", "beanbag", 3, 3)])
        self.assertEqual(room.RoomStore(self.path).layout()["placed"], [place("a", "beanbag", 3, 3)])

    def test_corrupt_file_starts_empty_and_keeps_backup(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{oops")
        s = room.RoomStore(self.path)
        self.assertEqual(s.layout()["placed"], [])
        self.assertTrue(os.path.exists(self.path + ".bad"))

    def test_layout_copy_is_detached(self):
        s = room.RoomStore(self.path)
        s.layout()["placed"].append("junk")
        self.assertEqual(s.layout()["placed"], [])


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.page = os.path.join(self.tmp, "index.html")
        with open(self.page, "w", encoding="utf-8") as f:
            f.write("<!doctype html><title>后宅</title>")
        self.store = room.RoomStore(os.path.join(self.tmp, "room.json"))
        self.server = room.RoomServer(room.RoomAPI(self.store), page=self.page).start()
        self.addCleanup(self.server.stop)

    def request(self, method, path, body=None, token=True, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        headers = {}
        if token:
            headers["X-Room-Token"] = self.server.token
        if host:
            headers["Host"] = host
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw

    def test_url_has_token(self):
        self.assertIn(f"?t={self.server.token}", self.server.url())
        self.assertTrue(self.server.url().startswith("http://127.0.0.1:"))

    def test_page_and_sprites(self):
        status, body = self.request("GET", "/?t=x", token=False)
        self.assertEqual(status, 200)
        self.assertIn("后宅".encode(), body)
        status, body = self.request("GET", "/character/front.png", token=False)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\x89PNG"))
        self.assertEqual(self.request("GET", "/character/../../etc.png", token=False)[0], 404)

    def test_catalog_and_state(self):
        status, cat = self.request("GET", "/api/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(len(cat["items"]), len(self.store.cat["items"]))
        self.assertNotIn("by_id", cat)
        status, st = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(st["layout"]["placed"], [])
        self.assertEqual({x["id"] for x in st["sets"]}, {x["id"] for x in self.store.cat["sets"]})
        self.assertNotIn("comfort", st)
        self.assertEqual(st["character"]["sprites"]["front"], "/character/front.png")

    def test_put_layout(self):
        status, r = self.request("PUT", "/api/layout", {"placed": [place("a", "pothos", 1, 1)]})
        self.assertEqual(status, 200)
        self.assertEqual(r["layout"]["placed"], [place("a", "pothos", 1, 1)])
        self.assertIn("sets", r)
        self.assertEqual(self.store.layout()["placed"], [place("a", "pothos", 1, 1)])
        status, r = self.request("PUT", "/api/layout", {"placed": [place("a", "pothos", 8, 1)]})
        self.assertEqual(status, 400)
        self.assertIn("出界", r["error"])
        self.assertEqual(self.request("PUT", "/api/layout", b"{nope")[0], 400)

    def test_token_and_host_required(self):
        self.assertEqual(self.request("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.request("PUT", "/api/layout", {"placed": []}, token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/state", host="evil.example:80")[0], 403)
        self.assertEqual(self.request("GET", "/api/state", host=f"localhost:{self.server.port}")[0], 200)

    def test_body_limit_and_unknown(self):
        self.assertEqual(self.request("PUT", "/api/layout", b"x" * (room.MAX_BODY + 1))[0], 413)
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)
        self.assertEqual(self.request("POST", "/")[0], 405)

    def test_missing_page(self):
        os.remove(self.page)
        status, body = self.request("GET", "/", token=False)
        self.assertEqual(status, 404)
        self.assertIn("npm run release".encode(), body)


def source_hash():
    """和 room/tools/release.mjs 的 sourceHash() 同一个算法：路径排序、跳过点文件、换行统一成 LF。"""
    files = ["index.html", "package.json", "package-lock.json", "tsconfig.json", "vite.config.ts"]
    for dirpath, dirnames, names in os.walk(os.path.join(ROOM_SRC, "src")):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in names:
            if not name.startswith("."):
                files.append(os.path.relpath(os.path.join(dirpath, name), ROOM_SRC).replace(os.sep, "/"))
    h = hashlib.sha256()
    for rel in sorted(files):
        with open(os.path.join(ROOM_SRC, rel), "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")
        h.update(rel.encode() + b"\n" + data + b"\n")
    return h.hexdigest()


class RoomBuildTest(unittest.TestCase):
    def test_bundled_page_is_current(self):
        path = os.path.join(ROOM_OUT, "index.html")
        self.assertTrue(os.path.isfile(path), "缺 content/room/index.html，在 room/ 里跑 npm run release")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertNotRegex(html, r'<script[^>]+src="(?!data:)')   # 单文件，不引外部脚本
        with open(os.path.join(ROOM_OUT, "SOURCE_HASH"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), source_hash(), "content/room 不是最新打包：在 room/ 里跑 npm run release")


try:
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QApplication, QPushButton
    import common
    import main
    import pet as pet_mod
except ImportError as e:   # 没装 PySide6
    _SKIP = f"缺依赖: {e}"
else:
    _SKIP = ""


@unittest.skipIf(_SKIP, _SKIP)
class PetRoomEntryTest(unittest.TestCase):
    def setUp(self):
        self.qapp = QApplication.instance() or QApplication([])
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        for target, attr, value in ((common, "CONFIG_PATH", os.path.join(self.tmp, "config.json")),
                                    (pet_mod, "DATA_DIR", self.tmp), (self.qapp, "quit", mock.Mock())):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        self.app = main.PetApp(self.qapp)
        self.pet = self.app.pet
        self.addCleanup(self.pet.timer.stop)
        self.addCleanup(lambda: self.pet.room_server and self.pet.room_server.stop())

    def test_room_save_lives_in_data_dir(self):
        with mock.patch.object(QDesktopServices, "openUrl", return_value=True):
            self.pet.open_room()
        self.assertEqual(self.pet.room_server.api.store.path, os.path.join(self.tmp, "room.json"))

    def test_panel_button_opens_room_in_browser(self):
        opened = []
        with mock.patch.object(QDesktopServices, "openUrl", side_effect=lambda u: opened.append(u) or True):
            btn = next(b for b in self.pet.function_panel.findChildren(QPushButton) if b.toolTip() == "后宅")
            btn.click()
        self.assertEqual(len(opened), 1)
        url = opened[0].toString()
        self.assertTrue(url.startswith("http://127.0.0.1:"), url)
        self.assertIn(self.pet.room_server.token, url)
        # 再开一次复用同一个服务
        server = self.pet.room_server
        with mock.patch.object(QDesktopServices, "openUrl", return_value=True):
            self.pet.open_room()
        self.assertIs(self.pet.room_server, server)

    def test_menu_has_room(self):
        texts = [a.text() for a in self.pet._build_menu().actions()]
        self.assertIn("🏠 后宅", texts)


if __name__ == "__main__":
    unittest.main()
