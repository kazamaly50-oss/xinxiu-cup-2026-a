"""复用正式仿真塔参数，检查静态布局与波间建塔的通用约束。"""

from collections import Counter
from itertools import combinations
from math import dist, isfinite

from geometry import dist_to_path


COST = {"小塔": 100, "中塔": 250, "大塔": 600}
STOCK = {"小塔": 20, "中塔": 15, "大塔": 10}
A1_WAVE = {"数量": 10, "血量": 1700, "速度": 20, "出发间隔": 10}
INITIAL_CASH = 2000
REVIEW = {"AI已运行": "已完成实测", "Hermes审核": "待 Hermes 事后复核",
          "真人复核": "待完成", "队长验收": "待完成"}


def validate_layout(towers, budget=None):
    """检查 (x, y, 塔型) 布局，返回总造价和库存；违规时抛 ValueError。

    budget 为固定开局方案的资金上限。跨波布局通过账本逐笔核算资金，
    场上塔已支付的历史造价不应再次受当前余额约束。
    """
    counts = Counter()
    for x, y, kind in towers:
        if kind not in COST:
            raise ValueError(f"未知塔型 {kind!r}")
        if not all(isfinite(q) and 10 <= q <= 1990 for q in (x, y)) or dist_to_path(x, y) < 15:
            raise ValueError(f"塔位不合法 {(x, y)}")
        counts[kind] += 1
    if any(counts[kind] > capacity for kind, capacity in STOCK.items()):
        raise ValueError("塔型库存超限")
    if any(dist(a[:2], b[:2]) < 20 for a, b in combinations(towers, 2)):
        raise ValueError("塔基重叠")
    cost = sum(COST[k] * v for k, v in counts.items())
    if budget is not None and cost > budget:
        raise ValueError(f"造价 {cost} 超过预算 {budget}")
    return cost, dict(counts)
