"""以向外取整的整数区间验证 A1 连续地图的总伤害上界。"""

import json
from itertools import product
from math import isqrt
from typing import NamedTuple


# 独立从题面录入，验证时和仿真器参数及路径对拍，避免浮点几何进入证明。
ROAD = ((0, 0), (400, 200), (700, 800), (1200, 900),
        (1500, 1400), (1800, 1700), (2000, 2000))
MAP_SIDE = 2000
BUDGET = 2000
ENEMY_COUNT = 10
HP = 1700
SPEED = 20
SPAWN_INTERVAL = 10
MM_PER_M = 1000
TOWER_TYPES = {
    # 射程（m），DPS，价格，库存，待验证的累计忙碌时长乘速度的上界（m）。
    "小塔": (75, 10, 100, 20, 1671),
    "中塔": (125, 20, 250, 15, 2080),
    "大塔": (200, 40, 600, 10, 2250),
}


class Segment(NamedTuple):
    """精确的线段几何和向外取整的弧长边界。"""

    x_mm: int
    y_mm: int
    dx_m: int
    dy_m: int
    norm_squared: int
    length_lower_mm: int
    length_upper_mm: int
    prefix_lower_mm: int
    prefix_upper_mm: int


def ceil_div(numerator, denominator):
    return -(-numerator // denominator)


def ceil_sqrt(value):
    root = isqrt(value)
    return root + (root * root != value)


def road_segments():
    """将每个段长和累计段首里程分别向下、向上取整到毫米。"""
    segments = []
    prefix_lower = prefix_upper = 0
    for (x0, y0), (x1, y1) in zip(ROAD, ROAD[1:]):
        dx, dy = x1 - x0, y1 - y0
        norm_squared = dx * dx + dy * dy
        length_squared_mm = norm_squared * MM_PER_M**2
        lower = isqrt(length_squared_mm)
        upper = ceil_sqrt(length_squared_mm)
        segments.append(Segment(x0 * MM_PER_M, y0 * MM_PER_M, dx, dy, norm_squared,
                                lower, upper, prefix_lower, prefix_upper))
        prefix_lower += lower
        prefix_upper += upper
    return segments


def busy_distance_upper_mm(x_mm, y_mm, radius_mm, segments):
    """返回至少有一只敌人在射程内的累计时间乘速度的上界，单位毫米。"""
    intervals = []
    for segment in segments:
        px, py = x_mm - segment.x_mm, y_mm - segment.y_mm
        a = px * segment.dx_m + py * segment.dy_m
        b = px * segment.dy_m - py * segment.dx_m
        q = segment.norm_squared
        # 线段比例 t 对应圆内区间 (a ± sqrt(qR²-b²))/(q·1000)。
        # 根号向上取整扩大该区间，再与 [0, 1] 相交。
        discriminant = q * radius_mm**2 - b * b
        if discriminant < 0:
            continue
        root = ceil_sqrt(discriminant)
        denominator = q * MM_PER_M
        lo, hi = max(0, a - root), min(denominator, a + root)
        if lo > hi:
            continue
        start = segment.prefix_lower_mm + lo * segment.length_lower_mm // denominator
        end = segment.prefix_upper_mm + ceil_div(hi * segment.length_upper_mm, denominator)
        # 用 u=v·t 表示共同时间轴。后出生的敌人将整段覆盖区间向右平移。
        # 即使敌人途中死亡也保留这些区间，只会增加可用攻击时长。
        for enemy in range(ENEMY_COUNT):
            shift = enemy * SPEED * SPAWN_INTERVAL * MM_PER_M
            intervals.append((start + shift, end + shift))

    # 每塔同一时刻至多打一个敌人，因此取时间区间的并集。
    covered = latest_end = 0
    for start, end in sorted(intervals):
        if end > latest_end:
            covered += end - max(start, latest_end)
            latest_end = end
    return covered


def certify_tower(radius_m, cap_m, segments):
    """递归覆盖整张闭地图，逐格验证给定塔型的候选上界。"""
    side_mm = MAP_SIDE * MM_PER_M
    cells = [(0, 0, side_mm, side_mm)]
    visited = leaves = max_leaf_mm = 0
    while cells:
        x0, y0, x1, y1 = cells.pop()
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        dx, dy = max(cx - x0, x1 - cx), max(cy - y0, y1 - cy)
        # 三角不等式。格内任何塔位的射程圆都包含在该扩张圆内。
        radius_mm = radius_m * MM_PER_M + ceil_sqrt(dx * dx + dy * dy)
        upper_mm = busy_distance_upper_mm(cx, cy, radius_mm, segments)
        visited += 1
        if upper_mm <= cap_m * MM_PER_M:
            leaves += 1
            max_leaf_mm = max(upper_mm, max_leaf_mm)
            continue
        if x1 - x0 < 2 or y1 - y0 < 2:
            raise ValueError(f"射程 {radius_m} m 的候选上界 {cap_m} m 未能通过验证")
        cells.extend((xa, ya, xb, yb)
                     for xa, xb in ((x0, cx), (cx, x1))
                     for ya, yb in ((y0, cy), (cy, y1)))
    return {"检查格数": visited, "通过的叶格数": leaves,
            "叶格最大忙碌弧长上界mm": max_leaf_mm, "认证忙碌弧长上界m": cap_m}


def damage_bounds():
    """返回整数区间验证结果、预算枚举和可证明的最少漏怪下界。"""
    segments = road_segments()
    tower_caps = {}
    for kind, (radius, dps, _, _, cap) in TOWER_TYPES.items():
        tower_caps[kind] = certify_tower(radius, cap, segments)
        tower_caps[kind]["单塔伤害上界HP"] = cap * dps / SPEED

    combinations = []
    for counts in product(*(range(spec[3] + 1) for spec in TOWER_TYPES.values())):
        cost = sum(count * spec[2] for count, spec in zip(counts, TOWER_TYPES.values()))
        if cost <= BUDGET:
            damage_times_speed = sum(count * spec[1] * spec[4]
                                     for count, spec in zip(counts, TOWER_TYPES.values()))
            combinations.append((damage_times_speed, cost, counts))
    best, _, counts = max(combinations)
    kills_upper = min(ENEMY_COUNT, best // (SPEED * HP))
    min_cost = min(cost for damage, cost, _ in combinations
                   if damage >= kills_upper * HP * SPEED)
    return {
        "输入": {"道路顶点m": ROAD, "地图边长m": MAP_SIDE, "预算元": BUDGET,
                   "敌人数": ENEMY_COUNT, "单敌血量HP": HP, "速度m每秒": SPEED,
                   "出兵间隔秒": SPAWN_INTERVAL, "单塔参数": TOWER_TYPES},
        "单塔证明": tower_caps, "预算内数量组合数": len(combinations),
        "上界最大组合": dict(zip(TOWER_TYPES, counts)),
        "总伤害上界HP": best / SPEED, "全杀需要伤害HP": ENEMY_COUNT * HP,
        "击杀数上界": kills_upper, "漏怪数下界": ENEMY_COUNT - kills_upper,
        "达到击杀数上界的花费下界元": min_cost,
    }


if __name__ == "__main__":
    print(json.dumps(damage_bounds(), ensure_ascii=False, indent=2, allow_nan=False))
