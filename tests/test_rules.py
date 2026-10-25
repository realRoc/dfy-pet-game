"""纯规则与内容加载测试，不需要窗口。运行：python -m unittest discover tests"""
import os
import random
import shutil
import tempfile
import unittest

from game.content import CONTENT_DIR, ContentError, check_all, load_dice_skin, load_map, load_tiles
from game.core.rules import START_WAGE, Rules
from game.core.state import BoardState


class ContentTest(unittest.TestCase):
    def test_all_content_valid(self):
        ok, errors = check_all()
        self.assertEqual(errors, [])
        self.assertTrue(ok)

    def test_classic_matches_old_ring(self):
        g = load_map("classic", tiles=load_tiles())
        self.assertEqual(len(g.nodes), 24)
        self.assertEqual(g.start, "m00")
        self.assertEqual(g.next_of("m23"), "m00")
        self.assertEqual([g.node(f"m{i:02d}").type for i in (0, 1, 16, 23)],
                         ["start", "fish", "prank", "fish"])

    def test_dice_skin(self):
        s = load_dice_skin("classic")
        self.assertEqual((s.pip, s.pip_one), ("#32466E", "#E14650"))


class BrokenContentTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        shutil.copytree(CONTENT_DIR, self.root, dirs_exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_unknown_tile_type(self):
        self.write("maps/bad/map.toml", 'canvas = [100, 100]\nloop = true\n'
                   'node = [{ id = "a", type = "start", pos = [0.1, 0.1] },'
                   ' { id = "b", type = "nope", pos = [0.5, 0.5] }]\n')
        with self.assertRaises(ContentError):
            load_map("bad", self.root, load_tiles(self.root))

    def test_dangling_next(self):
        self.write("maps/bad/map.toml", 'canvas = [100, 100]\n'
                   'node = [{ id = "a", type = "start", pos = [0.1, 0.1], next = ["zz"] }]\n')
        with self.assertRaises(ContentError):
            load_map("bad", self.root)

    def test_dice_typo_field(self):
        self.write("dice/bad/dice.toml", 'pip_colour = "#000000"\n')
        with self.assertRaises(ContentError):
            load_dice_skin("bad", self.root)

    def test_check_all_reports_instead_of_raising(self):
        self.write("dice/bad/dice.toml", 'body = "white"\n')
        _, errors = check_all(self.root)
        self.assertEqual(len(errors), 1)


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.tiles = load_tiles()
        self.graph = load_map("classic", tiles=self.tiles)
        self.rules = Rules(self.graph, self.tiles, rng=random.Random(1))

    def test_wage_only_on_edge_into_start(self):
        st = BoardState(node_id="m23")
        hop = self.rules.hop(st)
        self.assertEqual((hop.dst, hop.wage, st.coins), ("m00", START_WAGE, START_WAGE))
        landing = self.rules.land(st)       # 正好停在起点，不发第二次
        self.assertEqual((landing.coins, st.coins), (0, START_WAGE))
        hop = self.rules.hop(st)
        self.assertEqual(hop.wage, 0)

    def test_full_lap_pays_once(self):
        st = BoardState(node_id="m00")
        wages = sum(self.rules.hop(st).wage for _ in range(24))
        self.assertEqual((st.node_id, wages), ("m00", START_WAGE))

    def test_prank_skips_next_turn(self):
        st = BoardState(node_id="m16")
        self.rules.land(st)
        self.assertTrue(st.skip_next)
        self.assertIsNone(self.rules.begin_turn(st))
        self.assertFalse(st.skip_next)
        self.assertIn(self.rules.begin_turn(st), range(1, 7))
        self.assertEqual(st.turn, 2)

    def test_mystery_asks_for_expression(self):
        st = BoardState(node_id="m03", coins=5)
        landing = self.rules.land(st)
        self.assertTrue(landing.expression)
        self.assertEqual(st.coins, 5)

    def test_event_coins_applied_once(self):
        st = BoardState(node_id="m06")          # 宝箱
        landing = self.rules.land(st)
        self.assertEqual(st.coins, landing.coins)
        self.assertIn(landing.coins, (1, 2, 3))


class SaveCompatTest(unittest.TestCase):
    def setUp(self):
        self.graph = load_map("classic")

    def test_old_board_pos(self):
        st = BoardState.from_cfg({"board_pos": 5, "board_coins": 7, "board_turn": 3}, self.graph)
        self.assertEqual((st.node_id, st.coins, st.turn), ("m05", 7, 3))

    def test_round_trip_keeps_old_field(self):
        st = BoardState(node_id="m17", coins=4, turn=9)
        cfg = st.to_cfg(self.graph)
        self.assertEqual((cfg["board_pos"], cfg["board_node"], cfg["board_map"]), (17, "m17", "classic"))
        self.assertEqual(BoardState.from_cfg(cfg, self.graph), st)

    def test_round_trip_keeps_skip_next(self):
        st = BoardState(node_id="m16", coins=2, turn=5, skip_next=True)
        cfg = st.to_cfg(self.graph)
        self.assertTrue(cfg["board_skip_next"])
        self.assertEqual(BoardState.from_cfg(cfg, self.graph), st)
        # 老存档没有这个字段：不暂停
        self.assertFalse(BoardState.from_cfg({"board_node": "m16"}, self.graph).skip_next)

    def test_skip_survives_restart(self):
        """落地置位 → 退出保存 → 重启恢复 → 下一回合被消耗，再下一回合正常掷骰。"""
        rules = Rules(self.graph, load_tiles(), rng=random.Random(1))
        st = BoardState(node_id="m16")          # 恶作剧格
        rules.land(st)
        self.assertTrue(st.skip_next)
        cfg = st.to_cfg(self.graph)
        st = BoardState.from_cfg(cfg, self.graph)
        self.assertTrue(st.skip_next)
        self.assertIsNone(rules.begin_turn(st))
        self.assertFalse(st.skip_next)
        self.assertFalse(BoardState.from_cfg(st.to_cfg(self.graph), self.graph).skip_next)
        self.assertIn(rules.begin_turn(st), range(1, 7))

    def test_unknown_node_or_other_map(self):
        st = BoardState.from_cfg({"board_node": "zz", "board_pos": 2}, self.graph)
        self.assertEqual(st.node_id, "m02")
        st = BoardState.from_cfg({"board_map": "island", "board_node": "m09"}, self.graph)
        self.assertEqual(st.node_id, "m00")


if __name__ == "__main__":
    unittest.main()


class IslandTest(unittest.TestCase):
    """环岛大地图：道路自动排格子，两个岔路口。"""

    def setUp(self):
        self.tiles = load_tiles()
        self.graph = load_map("island", tiles=self.tiles)
        self.rules = Rules(self.graph, self.tiles, rng=random.Random(2))

    def walk(self, start, first, stop):
        """从 start 先走到 first，再沿默认出口走到 stop，返回步数。"""
        n, cur = 1, first
        while cur != stop:
            cur = self.graph.next_of(cur)
            n += 1
        return n

    def test_forks_and_branch_lengths(self):
        forks = {n: self.graph.exits(n) for n in self.graph.nodes if self.graph.is_fork(n)}
        self.assertEqual(forks, {"a08": ["b00", "p00"], "c16": ["d00", "g00"]})
        self.assertEqual(self.walk("a08", "b00", "c00"), 10)   # 蘑菇森林
        self.assertEqual(self.walk("a08", "p00", "c00"), 6)    # 像素小桥（捷径）
        self.assertEqual(self.walk("c16", "d00", "e00"), 8)    # 海湾栈道
        self.assertEqual(self.walk("c16", "g00", "e00"), 10)   # 花园小路
        self.assertEqual(self.graph.next_of("e08"), "a00")

    def test_nodes_spaced_along_roads(self):
        import math
        for a, n in self.graph.nodes.items():
            for b in n.next:
                d = math.dist(self.graph.anchor(a), self.graph.anchor(b))
                self.assertTrue(110 < d < 220, f"{a}->{b} 间距 {d:.0f}")

    def test_destinations_cover_both_branches(self):
        self.assertEqual(self.graph.destinations("a07", 2), {"b00", "p00"})
        self.assertEqual(self.graph.destinations("a00", 3), {"a03"})

    def test_hop_at_fork_needs_choice(self):
        st = BoardState(node_id="a08")
        with self.assertRaises(ValueError):
            self.rules.hop(st)
        with self.assertRaises(ValueError):
            self.rules.hop(st, "c00")
        self.assertEqual(self.rules.hop(st, "p00").dst, "p00")
        self.assertEqual(st.node_id, "p00")

    def test_wage_on_entering_start(self):
        st = BoardState(node_id="e08")
        self.assertEqual(self.rules.hop(st).wage, START_WAGE)

    def test_unbuilt_features_give_no_fake_reward(self):
        for kind in ("fishing", "forest", "shop", "pixel", "hospital", "story", "fork"):
            self.assertTrue(all(ev.coins == 0 for ev in self.tiles[kind].events), kind)

    def test_supply_pays_one(self):
        st = BoardState(node_id="a01")
        self.rules.land(st)
        self.assertEqual(st.coins, 1)

    def test_every_tile_type_has_sprite(self):
        used = {n.type for n in self.graph.nodes.values()}
        self.assertEqual(used - set(self.graph.art["tile_sprites"]), set())

    def test_road_end_must_meet_node(self):
        root = tempfile.mkdtemp()
        try:
            shutil.copytree(CONTENT_DIR, root, dirs_exist_ok=True)
            path = os.path.join(root, "maps", "island", "map.toml")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.replace("points = [[760, 1080], [960, 1080]", "points = [[900, 1300], [960, 1080]"))
            with self.assertRaises(ContentError):
                load_map("island", root)
        finally:
            shutil.rmtree(root)


class ArtCoverageTest(unittest.TestCase):
    """配置允许的每种美术都要有画法，否则加载通过、绘制时才报错。"""

    def test_painters_cover_kinds(self):
        from game.content.art_kinds import DECOR_KINDS, SYMBOLS, TERRAIN_KINDS
        from game.render.decor import DECOR_PAINTERS
        from game.render.map_renderer import MapRenderer
        from game.render.symbols import SYMBOL_PAINTERS
        self.assertEqual(set(DECOR_PAINTERS), DECOR_KINDS)
        self.assertEqual(set(SYMBOL_PAINTERS), SYMBOLS)
        for kind in TERRAIN_KINDS:
            self.assertTrue(hasattr(MapRenderer, "paint_" + kind), kind)

    def test_island_sprites_exist_and_loaded(self):
        g = load_map("island")
        self.assertTrue(all(os.path.isfile(s["path"]) for s in g.art["sprites"].values()))
        self.assertTrue(all(os.path.isfile(t) for t in g.art["textures"].values()))

    def test_bad_decor_and_symbol_rejected(self):
        root = tempfile.mkdtemp()
        try:
            shutil.copytree(CONTENT_DIR, root, dirs_exist_ok=True)
            path = os.path.join(root, "maps", "island", "map.toml")
            with open(path, "a", encoding="utf-8") as f:
                f.write('\n[[decor]]\nkind = "spaceship"\nat = [1, 1]\n')
            with self.assertRaises(ContentError):
                load_map("island", root)
            with open(os.path.join(root, "tiles.toml"), "a", encoding="utf-8") as f:
                f.write('\n[types.oops]\nname = "x"\ncolor = "#FFFFFF"\nsymbol = "rocket"\n')
            with self.assertRaises(ContentError):
                load_tiles(root)
        finally:
            shutil.rmtree(root)


class CubeDiceTest(unittest.TestCase):
    def test_final_face_is_result(self):
        from game.render.cube import front_face, orientation
        for a in range(1, 7):
            for b in range(1, 7):
                for axis in ((1, 0, 0), (0.3, -0.5, 0.4)):
                    for turns in (1, 2):
                        self.assertEqual(front_face(orientation(a, b, 0.0, axis, turns)), a)
                        self.assertEqual(front_face(orientation(a, b, 1.0, axis, turns)), b)

    def test_cream_timing(self):
        s = load_dice_skin("cream")
        self.assertEqual(s.style, "cube")
        self.assertAlmostEqual(s.rolling_time, 0.73)
        self.assertAlmostEqual(s.reveal_time, 0.18)


class MedievalTest(unittest.TestCase):
    """中世纪小岛：三个岔路口、湖心岛、地点事件。"""

    def setUp(self):
        self.tiles = load_tiles()
        self.graph = load_map("medieval", tiles=self.tiles)

    def rules_with(self, kind, event, seed=0):
        """把某种格子的事件换成只有一条，方便测确定结果。"""
        from dataclasses import replace
        tiles = dict(self.tiles)
        tiles[kind] = replace(tiles[kind], events=[event])
        return Rules(self.graph, tiles, rng=random.Random(seed))

    def walk(self, first, stop):
        n, cur = 1, first
        while cur != stop:
            cur = self.graph.next_of(cur)
            n += 1
        return n

    def test_forks(self):
        forks = {n: self.graph.exits(n) for n in self.graph.nodes if self.graph.is_fork(n)}
        self.assertEqual(forks, {"c12": ["n00", "g00"], "n04": ["q00", "v00"], "k01": ["i00", "t00"]})
        self.assertEqual(self.walk("g00", "k00"), 6)
        self.assertEqual((self.walk("i00", "w00"), self.walk("t00", "w00")), (10, 5))

    def test_west_road_from_top_left_through_community_to_city(self):
        """左上角港口往南穿过社区和田野，在西南河口和南沙滩汇合回城。"""
        self.assertEqual(self.walk("v00", "m00"), 18)
        self.assertEqual(self.graph.next_of("s14"), "m00")
        self.assertEqual(self.walk("m00", "c00"), 6)
        xs = [self.graph.anchor(f"v{i:02d}")[0] for i in range(3, 13)]
        self.assertTrue(all(x < 590 for x in xs))     # 一直在西边河道外侧的社区地带

    def test_tiles_fit_their_place(self):
        city = [n for n in self.graph.nodes if n.startswith("c")]
        self.assertFalse(any(self.graph.node(n).type == "fishing" for n in city))
        self.assertIn("blank", {n.type for n in self.graph.nodes.values()})

    def test_every_special_place_on_the_board(self):
        types = {n.type for n in self.graph.nodes.values()}
        for kind in ("city", "harbor", "lavender", "ruins", "lake_isle", "gyroid", "witch", "field"):
            self.assertIn(kind, types)

    def test_lake_isle_reachable_by_road(self):
        self.assertIn("i01", self.graph.destinations("k01", 2))
        self.assertEqual(self.graph.node("i01").type, "lake_isle")

    def test_no_overlapping_tiles(self):
        import itertools
        import math
        for a, b in itertools.combinations(self.graph.nodes, 2):
            self.assertGreater(math.dist(self.graph.anchor(a), self.graph.anchor(b)), self.graph.tile, (a, b))

    def test_forced_move_forward_skips_wage_and_event(self):
        from game.core.tiles import TileEvent
        st = BoardState(node_id="w01", coins=5)
        landing = self.rules_with("witch", TileEvent(move=3, say="飞")).land(st)
        self.assertEqual(landing.path, ["w02", "w03", "w04"])
        self.assertEqual((st.node_id, st.coins), ("w04", 5))

    def test_forced_move_back_follows_first_road_in(self):
        from game.core.tiles import TileEvent
        st = BoardState(node_id="q06")
        landing = self.rules_with("ruins", TileEvent(move=-2)).land(st)
        self.assertEqual(landing.path, ["q05", "q04"])
        self.assertEqual(st.node_id, "q04")
        # 合流点往回退走第一条写进来的路
        self.assertEqual(self.graph.prev_of("k00"), "g04")

    def test_harbor_warp_to_lake_isle_without_wage(self):
        from game.core.tiles import TileEvent
        st = BoardState(node_id="q00", coins=1)
        landing = self.rules_with("harbor", TileEvent(warp="lake_isle")).land(st)
        self.assertEqual((landing.warp_to, st.node_id, st.coins), ("i01", "i01", 1))

    def test_coins_never_negative(self):
        from game.core.tiles import TileEvent
        st = BoardState(node_id="w01", coins=1)
        landing = self.rules_with("witch", TileEvent(coins=-2)).land(st)
        self.assertEqual((st.coins, landing.coins), (0, -1))

    def test_skip_and_expression(self):
        from game.core.tiles import TileEvent
        st = BoardState(node_id="n01")
        landing = self.rules_with("lavender", TileEvent(skip_next=True, expression="sleepy")).land(st)
        self.assertTrue(st.skip_next)
        self.assertEqual(landing.expression, "sleepy")

    def test_event_expressions_exist(self):
        from expressions import EXPRESSIONS
        for t in self.tiles.values():
            for ev in t.events:
                self.assertTrue(ev.expression in ("", "random") or ev.expression in EXPRESSIONS,
                                f"{t.id}: {ev.expression}")

    def test_bad_event_field_rejected(self):
        root = tempfile.mkdtemp()
        try:
            shutil.copytree(CONTENT_DIR, root, dirs_exist_ok=True)
            with open(os.path.join(root, "tiles.toml"), "a", encoding="utf-8") as f:
                f.write('\n[types.oops]\nname = "x"\ncolor = "#FFFFFF"\nevents = [{ teleport = "a" }]\n')
            with self.assertRaises(ContentError):
                load_tiles(root)
        finally:
            shutil.rmtree(root)
