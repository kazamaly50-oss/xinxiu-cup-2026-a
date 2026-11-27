"""先校验正式 A1 的静态布局，再复跑逐敌结果。"""

import argparse
import json
from collections import Counter
from itertools import combinations
from math import hypot
from numbers import Real
from pathlib import Path

from a1_bounds import BUDGET, ENEMY_COUNT, HP, MAP_SIDE, SPEED, SPAWN_INTERVAL, TOWER_TYPES
from geometry import dist_to_path
from simulate import simulate


BASE_RADIUS = 10
ROAD_HALF_WIDTH = 5
# 口径待裁定。默认保留既有布局检查，两个开关可独立选择。
MAP_BOUNDARIES = ("center_in_map", "base_in_map")
DISTANCE_BASES = ("center", "edge")
DEFAULT_MAP_BOUNDARY = "base_in_map"
DEFAULT_DISTANCE_BASIS = "center"
WAVE = {"数量": ENEMY_COUNT, "血量": HP, "速度": SPEED, "出发间隔": SPAWN_INTERVAL}
CORE_STEPS = (0.05, 0.01)
EXTRA_STEPS = (0.005, 0.0025)


def validate_layout(towers, *, map_boundary=DEFAULT_MAP_BOUNDARY,
                    distance_basis=DEFAULT_DISTANCE_BASIS):
    """按直径 20 m 塔基、10 m 道宽和静态预算返回布局检查结果。"""
    if map_boundary not in MAP_BOUNDARIES:
        raise ValueError("地图边界口径必须是 center_in_map 或 base_in_map")
    if distance_basis not in DISTANCE_BASES:
        raise ValueError("距离基准必须是 center 或 edge")

    boundary_margin = BASE_RADIUS if map_boundary == "base_in_map" else 0
    boundary_label = "完整塔基" if map_boundary == "base_in_map" else "塔心"
    # center 用塔心到道路中心线、塔心之间的距离。edge 用有符号净距，
    # 从上述距离减去相应半径。两种量法的阈值表示同一不压占条件，均允许相切。
    road_center_min = BASE_RADIUS + ROAD_HALF_WIDTH
    tower_center_min = 2 * BASE_RADIUS
    if distance_basis == "edge":
        road_offset, tower_offset = road_center_min, tower_center_min
        road_message = "的塔基边缘与道路边缘的净距小于 0 m"
        pair_message = "的塔基边缘净距小于 0 m"
    else:
        road_offset = tower_offset = 0
        road_message = f"的塔心距道路中心线小于 {road_center_min} m"
        pair_message = f"的塔心距离小于 {tower_center_min} m"
    road_min = road_center_min - road_offset
    pair_min = tower_center_min - tower_offset

    violations = []
    valid_rows = []
    counts = Counter()
    if not isinstance(towers, (list, tuple)):
        raise ValueError("布局必须是由 [x, y, 塔型] 组成的列表")
    for index, row in enumerate(towers, 1):
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            violations.append(f"塔 {index} 需要提供 [x, y, 塔型]")
            continue
        x, y, kind = row
        if not isinstance(kind, str) or kind not in TOWER_TYPES:
            violations.append(f"塔 {index} 的塔型无效")
            continue
        counts[kind] += 1
        if any(isinstance(v, bool) or not isinstance(v, Real) for v in (x, y)):
            violations.append(f"塔 {index} 的坐标须为有限实数")
            continue
        # 先拒绝过界坐标，避免对过大的数值执行距离运算。
        if not all(boundary_margin <= v <= MAP_SIDE - boundary_margin for v in (x, y)):
            violations.append(f"塔 {index} 的{boundary_label}超出地图或坐标无效")
            continue
        x, y = float(x), float(y)
        if dist_to_path(x, y) - road_offset < road_min:
            violations.append(f"塔 {index} {road_message}")
        valid_rows.append((index, x, y))

    # 开局一次性建造，逐塔计价并同时检查每种塔的库存。
    cost = sum(counts[kind] * spec[2] for kind, spec in TOWER_TYPES.items())
    if cost > BUDGET:
        violations.append(f"总花费 {cost} 元超过 {BUDGET} 元预算")
    for kind, spec in TOWER_TYPES.items():
        if counts[kind] > spec[3]:
            violations.append(f"{kind}数量 {counts[kind]} 超过库存 {spec[3]}")
    for (i, x1, y1), (j, x2, y2) in combinations(valid_rows, 2):
        if hypot(x1 - x2, y1 - y2) - tower_offset < pair_min:
            violations.append(f"塔 {i} 和塔 {j} {pair_message}")
    return {"通过": not violations, "问题": violations, "总花费元": cost,
            "剩余资金元": BUDGET - cost, "数量": dict(counts),
            "口径": {"地图边界": map_boundary, "距离基准": distance_basis,
                     "允许相切": True, "状态": "口径待裁定"}}


def _snapshot(towers, step):
    """提取每步长的结局日志和目标值，避免保存整条伤害采样曲线。"""
    result = simulate(towers, WAVE, dt=step)
    return {"步长秒": step, "漏怪数": result["漏怪数"],
            "逐敌结果": result["每只敌人结果"], "游戏耗时秒": result["总耗时"]}


def _compare(coarse, fine):
    pairs = tuple(zip(coarse["逐敌结果"], fine["逐敌结果"], strict=True))
    flipped = [a["编号"] for a, b in pairs if a["结果"] != b["结果"]]
    # 同时检查逐敌结果，避免两只敌人交换结局导致总漏怪数恰好一致。
    return {"步长秒": [coarse["步长秒"], fine["步长秒"]], "结局变化的敌人": flipped,
            "逐敌结局一致": coarse["漏怪数"] == fine["漏怪数"] and not flipped,
            "最大剩余血量差HP": max(abs(a["剩余血量"] - b["剩余血量"]) for a, b in pairs)}


def verify_layout(towers, *, map_boundary=DEFAULT_MAP_BOUNDARY,
                  distance_basis=DEFAULT_DISTANCE_BASIS):
    """合法后才进入仿真。粗细步有分歧时继续细化并保留全部差异。"""
    legality = validate_layout(towers, map_boundary=map_boundary, distance_basis=distance_basis)
    report = {"题目": "A1", "布局": towers, "波次": WAVE, "合法性": legality,
              "复跑": [], "比较": []}
    if not legality["通过"]:
        return {**report, "状态": "布局未通过合法性检查"}

    runs = report["复跑"]
    comparisons = report["比较"]
    runs.extend(_snapshot(towers, step) for step in CORE_STEPS)
    comparisons.append(_compare(*runs))
    for step in EXTRA_STEPS:
        if comparisons[-1]["逐敌结局一致"]:
            break
        runs.append(_snapshot(towers, step))
        comparisons.append(_compare(*runs[-2:]))
    return {**report, "状态": "最细两档结局一致" if comparisons[-1]["逐敌结局一致"]
            else "步长不稳定，需进一步复核"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path, help="UTF-8 JSON 文件，根节点为 [x, y, 塔型] 列表")
    parser.add_argument("--map-boundary", choices=MAP_BOUNDARIES,
                        default=DEFAULT_MAP_BOUNDARY, help="地图边界口径（默认 %(default)s）")
    parser.add_argument("--distance-basis", choices=DISTANCE_BASES,
                        default=DEFAULT_DISTANCE_BASIS, help="距离基准（默认 %(default)s）")
    args = parser.parse_args()
    try:
        towers = json.loads(args.layout.read_text(encoding="utf-8-sig"))
        report = verify_layout(towers, map_boundary=args.map_boundary,
                               distance_basis=args.distance_basis)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    # 遇到非标准 JSON 浮点数会在合法性阶段拦截。错误报告省略非法原始输入。
    if not report["合法性"]["通过"]:
        report.pop("布局")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["状态"] == "最细两档结局一致" else 1


if __name__ == "__main__":
    raise SystemExit(main())
