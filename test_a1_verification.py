"""回归检查 A1 上界、布局合法性和缩步触发。"""

import random
import unittest
from unittest.mock import patch

import a1_bounds as bounds
import geometry
import simulate
import verify_a1 as verify
from coverage import cover_intervals


class DamageBoundTests(unittest.TestCase):
    def test_certificate(self):
        # 独立录入的证明参数应与仓库仿真数据一致。
        self.assertEqual(tuple(map(tuple, geometry._VERTICES)), bounds.ROAD)
        self.assertEqual(simulate.TOWER_STATS, {k: v[:2] for k, v in bounds.TOWER_TYPES.items()})
        report = bounds.damage_bounds()
        self.assertEqual(report["预算内数量组合数"], 171)
        self.assertEqual(report["总伤害上界HP"], 16710)
        self.assertEqual(report["漏怪数下界"], 1)
        self.assertEqual(report["达到击杀数上界的花费下界元"], 1850)

    def test_outward_interval_bounds(self):
        rng = random.Random(42)
        segments = bounds.road_segments()
        step_distance = bounds.SPEED * bounds.SPAWN_INTERVAL
        # 用 coverage.py 的浮点覆盖区间另算并集，检查取整方向。
        # 塔位向折线附近采样，避免大量测试只覆盖零区间。
        for _ in range(500):
            x, y = geometry.pos(rng.uniform(0, geometry.path_length()))
            x_mm = round(1000 * (x + rng.uniform(-200, 200)))
            y_mm = round(1000 * (y + rng.uniform(-200, 200)))
            radius = rng.choice((75, 125, 200))
            covered = cover_intervals(x_mm / 1000, y_mm / 1000, radius)
            intervals = sorted((lo + i * step_distance, hi + i * step_distance)
                               for lo, hi in covered for i in range(bounds.ENEMY_COUNT))
            union = end = 0.0
            for lo, hi in intervals:
                if hi > end:
                    union += hi - max(lo, end)
                    end = hi
            upper_mm = bounds.busy_distance_upper_mm(x_mm, y_mm, radius * 1000, segments)
            self.assertGreaterEqual(upper_mm, union * 1000 - 1e-7)


class LayoutTests(unittest.TestCase):
    def test_boundaries_and_invalid_inputs(self):
        cases = (
            ([], True),
            ([(10, 1000, "小塔"), (30, 1000, "小塔")], True),
            ([(9.999, 1000, "小塔")], False),
            ([(10, 1000, "小塔"), (29.999, 1000, "小塔")], False),
            ([(400, 200, "小塔")], False),
            ([(float("nan"), 1000, "小塔")], False),
            ([(True, 1000, "小塔")], False),
            ([(10, 1000, [])], False),
        )
        for towers, expected in cases:
            with self.subTest(towers=towers):
                self.assertEqual(verify.validate_layout(towers)["通过"], expected)
        towers = [(10 + 20 * i, 1700, "小塔") for i in range(21)]
        self.assertEqual(len(verify.validate_layout(towers)["问题"]), 2)  # 超预算、超库存
        with patch.object(verify, "dist_to_path", return_value=15):
            self.assertTrue(verify.validate_layout([(10, 1000, "小塔")])["通过"])

    def test_invalid_layout_stops_before_simulation(self):
        with patch.object(verify, "simulate") as simulation:
            self.assertFalse(verify.verify_layout([(400, 200, "小塔")])["合法性"]["通过"])
        simulation.assert_not_called()

    def test_map_boundary_switch(self):
        for basis in ("center", "edge"):
            for x in (0, 2000):
                with self.subTest(basis=basis, x=x):
                    towers = [(x, 1000, "小塔")]
                    self.assertTrue(verify.validate_layout(towers, map_boundary="center_in_map",
                                                           distance_basis=basis)["通过"])
                    self.assertFalse(verify.validate_layout(towers, map_boundary="base_in_map",
                                                            distance_basis=basis)["通过"])
            towers = [(-0.001, 1000, "小塔")]
            self.assertFalse(verify.validate_layout(towers, map_boundary="center_in_map",
                                                    distance_basis=basis)["通过"])

    def test_distance_measurement_switch(self):
        for basis in ("center", "edge"):
            with self.subTest(basis=basis):
                with patch.object(verify, "dist_to_path", return_value=15):
                    towers = [(10, 1000, "小塔"), (30, 1000, "小塔")]
                    self.assertTrue(verify.validate_layout(towers, distance_basis=basis)["通过"])
                    overlapping = [(10, 1000, "小塔"), (29.999, 1000, "小塔")]
                    result = verify.validate_layout(overlapping, distance_basis=basis)
                    self.assertFalse(result["通过"])
                    self.assertIn("塔心距离" if basis == "center" else "塔基边缘净距",
                                  result["问题"][0])
                with patch.object(verify, "dist_to_path", return_value=14.999):
                    result = verify.validate_layout(towers[:1], distance_basis=basis)
                    self.assertFalse(result["通过"])
                    self.assertIn("道路中心线" if basis == "center" else "道路边缘",
                                  result["问题"][0])

    def test_report_records_requested_convention(self):
        with patch.object(verify, "simulate") as simulation:
            report = verify.verify_layout([(400, 200, "小塔")],
                                          map_boundary="center_in_map", distance_basis="edge")
        self.assertEqual(report["合法性"]["口径"], {
            "地图边界": "center_in_map", "距离基准": "edge", "允许相切": True,
            "道路模型": "中心折线半径5m缓冲区域", "状态": "未采用的对照口径",
        })
        simulation.assert_not_called()
        # 只核验报告状态更新；既有距离、边界及相切判据保持不变。
        for basis in ("center", "edge"):
            confirmed = verify.validate_layout([], distance_basis=basis)["口径"]
            self.assertEqual(confirmed["状态"], "已确认（队长裁定）")

    @staticmethod
    def snapshot(step, leaked):
        # 两次总漏怪数始终相同，仅交换发生漏怪的敌人编号。
        return {"步长秒": step, "漏怪数": 1, "逐敌结果": [
            {"编号": i, "结果": "漏怪" if i == leaked else "击杀", "剩余血量": int(i == leaked)}
            for i in (1, 2)
        ]}

    def test_same_count_different_enemy_triggers_refinement(self):
        runs = [self.snapshot(.05, 1), self.snapshot(.01, 2), self.snapshot(.005, 2)]
        with patch.object(verify, "_snapshot", side_effect=runs) as simulation:
            report = verify.verify_layout([])
        self.assertEqual([call.args[1] for call in simulation.call_args_list], [.05, .01, .005])
        self.assertEqual([x["逐敌结局一致"] for x in report["比较"]], [False, True])

    def test_unresolved_instability(self):
        steps = (.05, .01, .005, .0025)
        runs = [self.snapshot(step, enemy) for step, enemy in zip(steps, (1, 2, 1, 2))]
        with patch.object(verify, "_snapshot", side_effect=runs):
            self.assertEqual(verify.verify_layout([])["状态"], "步长不稳定，需进一步复核")


if __name__ == "__main__":
    unittest.main()
