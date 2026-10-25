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

    def test_unknown_node_or_other_map(self):
        st = BoardState.from_cfg({"board_node": "zz", "board_pos": 2}, self.graph)
        self.assertEqual(st.node_id, "m02")
        st = BoardState.from_cfg({"board_map": "island", "board_node": "m09"}, self.graph)
        self.assertEqual(st.node_id, "m00")


if __name__ == "__main__":
    unittest.main()
