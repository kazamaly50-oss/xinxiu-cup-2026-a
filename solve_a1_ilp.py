"""T2.2：按塔侧时间窗容量求双阶段 ILP，验回完整逐塔逐敌模型。"""

import argparse
import hashlib
import json
from math import fsum, isclose
from pathlib import Path
import platform
import sys
from time import perf_counter

import highspy
import numpy as np
import pulp

from anneal_a1 import replay
from layout_rules import A1_WAVE, COST, INITIAL_CASH, REVIEW, validate_layout
from simulate import TOWER_STATS


SOURCE = Path("results/t2.1/candidates.npz")
ENEMIES = A1_WAVE["数量"]
HP = A1_WAVE["血量"]
SEED = 42


def window_seconds(intervals, speed, spawn_gap, enemy_count):
    """返回首敌首次入射程至末敌最后离开射程的总时长（秒）。"""
    if len(intervals) == 0:
        return 0.0
    # 所有敌人同速走同一路径。首、末敌的整段覆盖时间只相差出生时刻。
    # 时间窗保留中间空档，不能换成覆盖长度之和或敌群在场区间并集。
    first = min(a for a, _ in intervals) / speed
    last = (enemy_count - 1) * spawn_gap + max(b for _, b in intervals) / speed
    return last - first


def load_candidates():
    """读取并复核 T2.1 系数，返回塔位、塔型、d、W 和 DPS×W。"""
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    receipt = json.loads(Path("handoffs/T2.1.json").read_text(encoding="utf-8"))
    if source_hash != receipt["文件SHA256"]["results/t2.1/candidates.npz"]:
        raise ValueError("T2.1 候选数据不匹配交接哈希")
    speed, gap = A1_WAVE["速度"], A1_WAVE["出发间隔"]
    with np.load(SOURCE, allow_pickle=False) as data:
        points, kinds, damage = data["xy_m"], data["tower_types"].tolist(), data["damage_hp"]
        offsets, spans = data["interval_offsets"], data["intervals_m"]
    if damage.shape != (1382, 3) or len(offsets) != damage.size + 1:
        raise ValueError("T2.1 候选矩阵或区间索引维度不符")
    windows = np.zeros_like(damage)
    for i, (p, t) in enumerate(np.ndindex(damage.shape)):
        intervals = spans[offsets[i]:offsets[i+1]]
        dps = TOWER_STATS[kinds[t]][1]
        expected = fsum(b - a for a, b in intervals) / speed * dps
        if not isclose(damage[p, t], expected, rel_tol=1e-13, abs_tol=1e-12):
            raise ValueError(f"候选点 {p+1} 塔型 {kinds[t]} 的单敌伤害与覆盖区间不符")
        windows[p, t] = window_seconds(intervals, speed, gap, ENEMIES)
    dps = np.array([TOWER_STATS[k][1] for k in kinds])
    return points, kinds, damage, windows, windows * dps, source_hash


def layout_variables(name, shape, kinds, sense):
    """声明建塔变量，并加预算和同点互斥两类布局约束。"""
    model = pulp.LpProblem(name, sense)
    x = {(p, t): pulp.LpVariable(f"x_{p+1}_{t+1}", cat="Binary") for p, t in np.ndindex(shape)}
    spending = pulp.lpSum(COST[kinds[t]] * var for (p, t), var in x.items())
    model += spending <= INITIAL_CASH, "budget"
    for p in range(shape[0]):
        model += pulp.lpSum(x[p, t] for t in range(shape[1])) <= 1, f"one_tower_{p+1}"
    return model, x, spending


def verify_original(selected, kills, kinds, damage, capacity):
    """将投影解展开成完整 x、leak、dmg，并逐条核验原始 PuLP 约束。"""
    model, x, spending = layout_variables("a1_full_capacity", damage.shape, kinds, pulp.LpMinimize)
    leak = [pulp.LpVariable(f"leak_{e+1}", cat="Binary") for e in range(ENEMIES)]
    dmg = {(p, t, e): pulp.LpVariable(f"dmg_{p+1}_{t+1}_{e+1}", lowBound=0)
           for p, t in x for e in range(ENEMIES)}
    selected = set(selected)
    effective = {pair: min(damage[pair], capacity[pair] / kills) for pair in selected} if kills else {}
    available = fsum(effective.values())
    if kills and available < HP - 1e-8:
        raise ValueError("投影解无法展开为足额逐敌伤害")
    scale = min(1.0, HP / available) if kills else 0.0
    for (p, t), build in x.items():
        build.varValue = int((p, t) in selected)
        model += pulp.lpSum(dmg[p, t, e] for e in range(ENEMIES)) <= float(capacity[p, t]), f"capacity_{p+1}_{t+1}"
        for e in range(ENEMIES):
            hit = dmg[p, t, e]
            hit.varValue = float(effective.get((p, t), 0.0) * scale) if e < kills else 0.0
            model += hit <= float(damage[p, t]) * build, f"individual_{p+1}_{t+1}_{e+1}"
    for e, escaped in enumerate(leak):
        escaped.varValue = int(e >= kills)
        model += pulp.lpSum(dmg[p, t, e] for p, t in x) >= HP*(1 - escaped), f"enemy_{e+1}"
    model.setObjective(pulp.lpSum(leak))
    if not model.valid(1e-7) or round(pulp.value(model.objective)) != ENEMIES - kills:
        raise ValueError("完整模型逐条验回失败")
    model += pulp.lpSum(leak) == ENEMIES - kills, "fixed_first_stage"
    model.sense = pulp.LpMaximize
    model.setObjective(INITIAL_CASH - spending)
    if not model.valid(1e-7):
        raise ValueError("固定第一阶段漏怪最优值后验回失败")
    return {"完整模型变量数": model.numVariables(), "完整模型约束数（含固定第一阶段）": model.numConstraints(),
            "预算余量元": round(pulp.value(model.objective)),
            "逐敌伤害HP": [fsum(dmg[p, t, e].value() for p, t in selected) for e in range(ENEMIES)],
            "已选塔分配": [{"点": p+1, "塔型": kinds[t], "单敌上限HP": float(damage[p, t]),
                           "容量HP": float(capacity[p, t]), "每敌实际分配HP": [dmg[p, t, e].value() for e in range(ENEMIES)]}
                          for p, t in sorted(selected)], "完整模型验回通过": True}


def budget_check(coeff, kinds):
    """按点枚举可达预算，独立复算阈值与最小成本。"""
    from math import gcd

    unit = gcd(*[COST[kind] for kind in kinds])
    price_steps = [COST[kind] // unit for kind in kinds]
    supply = np.full(INITIAL_CASH // unit + 1, -np.inf)
    supply[0] = 0.0
    decisions = np.full((len(coeff), len(supply)), -1, dtype=np.int8)
    for p, row in enumerate(coeff):
        previous = supply
        supply = previous.copy()
        for t, price in enumerate(price_steps):
            candidate = previous[:-price] + row[t]
            improved = candidate > supply[price:]
            supply[price:][improved] = candidate[improved]
            decisions[p, price:][improved] = t
    reached = np.flatnonzero(supply >= HP)
    chosen = []
    min_price = None
    below = None
    if reached.size:
        index = int(reached[0])
        min_price = index * unit
        below = float(max(supply[:index])) if index else None
        for p in range(len(coeff)-1, -1, -1):
            t = int(decisions[p, index])
            if t >= 0:
                chosen.append((p, t))
                index -= price_steps[t]
        if index != 0 or fsum(coeff[pair] for pair in chosen) < HP:
            raise ValueError("独立预算枚举的回溯结果未达到逐敌阈值")
    return {"预算单位元": unit, "预算内每敌可分配上限HP": float(max(supply)),
            "最小可行造价元": min_price, "低于最小造价时上限HP": below}


def solve_projected(coeff, kinds, folder, stage, deadline, *, second=False):
    """用精确投影求一阶段子问题，保存 HiGHS 日志和可行解。"""
    model, x, spending = layout_variables(stage, coeff.shape, kinds, pulp.LpMaximize)
    attainable = pulp.lpSum(float(coeff[p, t]) * var for (p, t), var in x.items())
    model += attainable >= HP, "can_supply_k_enemies"
    # 第一阶段只问固定 k 是否可行。最大化多余伤害对漏怪目标没有帮助。
    model.setObjective(INITIAL_CASH - spending if second else pulp.LpAffineExpression())
    # 给写盘和完整验回留出时间。所有子问题共用一个 45 分钟截止点。
    limit = deadline - perf_counter() - 30
    if limit <= 0:
        return {"状态": "时间用尽", "已证明最优": False}, []
    log = folder / f"{stage}.highs.log"
    # 成本是 50 元的整数倍，剩余绝对间隙小于 50 元即可证明没有更优整数成本。
    solver = pulp.HiGHS(msg=False, threads=1, timeLimit=limit, random_seed=SEED,
                        log_to_console=False, log_file=log.as_posix(), gapAbs=49.0 if second else None)
    start = perf_counter()
    model.solve(solver)
    elapsed = perf_counter() - start
    lines = log.read_text(encoding="utf-8").splitlines()
    log.write_text("\n".join(line.rstrip() for line in lines).rstrip() + "\n", encoding="utf-8")
    optimal = model.status == pulp.LpStatusOptimal and model.sol_status == pulp.LpSolutionOptimal
    chosen = [(p, t) for (p, t), var in x.items() if var.value() is not None and var.value() > 0.5]
    valid = model.valid(1e-6)
    if optimal and not valid:
        raise ValueError(f"{stage} 最优解未通过约束验回")
    if not valid:
        chosen = []
    return {"状态": pulp.LpStatus[model.status], "终止说明": pulp.LpSolution.get(model.sol_status),
            "已证明不可行": model.status == pulp.LpStatusInfeasible,
            "已证明最优": optimal, "可行解已回读": valid,
            "每敌可分配HP": fsum(coeff[pair] for pair in chosen) if valid else None,
            "剩余资金元": INITIAL_CASH - sum(COST[kinds[t]] for _, t in chosen) if valid else None,
            "运行时间秒": elapsed, "日志": log.as_posix(), "求解器": solver.name}, chosen


def main():
    """先确定最少漏怪，再固定该值并最大化余额，最后单独复跑仿真。"""
    start = perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/t2.2"))
    parser.add_argument("--seconds", type=float, default=2700)
    args = parser.parse_args()
    if not 60 <= args.seconds <= 2700 or pulp.__version__ != "2.8.0":
        parser.error("时间限额 60 至 2700 秒，PuLP 锁定 2.8.0")
    args.output.mkdir(parents=True, exist_ok=True)
    points, kinds, damage, windows, capacity, source_hash = load_candidates()
    deadline = start + args.seconds
    first, second, solution, simulation = [], None, None, None
    model_bound, kills = None, None
    # 固定 k 只未漏。每座塔在每个目标上限 min(d, capacity/k)。
    # 必要性：对 k 个未漏目标加总，单塔至多 min(k*d, capacity)。
    # 充分性：每座塔把相同的合法伤害均摊至这 k 个敌人，多余部分同比缩小。
    for k in range(ENEMIES, 0, -1):
        coeff = np.minimum(damage, capacity/k)
        audited = budget_check(coeff, kinds)
        record, selected = solve_projected(coeff, kinds, args.output, f"capacity-stage1-k{k}", deadline)
        first.append({"拟击杀数": k, **record, "独立预算枚举": audited})
        supply = record.get("每敌可分配HP")
        # 因为更大的击杀数均已被证明不可行，此处只需一个可核验的可行布局。
        if supply is not None and supply >= HP:
            if audited["最小可行造价元"] is None:
                raise ValueError("独立预算枚举与 HiGHS 可行性判断不一致")
            kills, model_bound = k, ENEMIES-k
            break
        if not record.get("已证明不可行", False):
            break
        if audited["最小可行造价元"] is not None:
            raise ValueError("独立预算枚举与 HiGHS 不可行性判断不一致")
    else:
        kills, model_bound, selected = 0, ENEMIES, []
        coeff = np.zeros_like(damage)
    if kills is not None:
        if kills > 0:
            second, cheapest = solve_projected(coeff, kinds, args.output, "capacity-stage2", deadline, second=True)
            second["独立预算枚举"] = audited
            second["求解器绝对间隙阈值元"] = 49.0
            if second.get("已证明最优") and INITIAL_CASH - second["剩余资金元"] != audited["最小可行造价元"]:
                raise ValueError("独立预算枚举与 HiGHS 第二阶段造价不一致")
            if second.get("可行解已回读"):
                selected = cheapest
        else:
            second = {"状态": "最优", "已证明最优": True, "剩余资金元": INITIAL_CASH,
                      "依据": "空布局花费 0 达到预算余量上限"}
        solution = verify_original(selected, kills, kinds, damage, capacity)
        for tower in solution["已选塔分配"]:
            tower["时间窗秒"] = float(windows[tower["点"]-1, kinds.index(tower["塔型"])])
        towers = [[*points[p].tolist(), kinds[t]] for p, t in selected]
        cost, _ = validate_layout(towers, INITIAL_CASH)
        if deadline - perf_counter() > 15:
            runs, agrees = replay(towers)
            simulation = {"布局": towers, "造价元": cost, "正式复跑": runs, "逐敌一致": agrees}
        else:
            simulation = {"布局": towers, "造价元": cost, "状态": "达到计时保留点，未开展双步长复跑"}
    if model_bound == 1:
        decision = "容量修正后模型界仍为 1，问题一下界以解析界为准"
    elif model_bound is None:
        decision = "限时内未确定容量模型最优值，问题一仍以解析界至少漏 1 只为准"
    else:
        decision = "容量模型结果仅在 T2.1 候选点集合内成立"
    report = {"任务": "T2.2 塔侧容量修正", "计算时间上限秒": args.seconds, "种子": SEED,
              "环境": {"Python": platform.python_version(), "可执行文件": sys.executable,
                       "PuLP": pulp.__version__, "NumPy": np.__version__, "HiGHS": highspy.Highs().version()},
              "容量口径": "W=(最后覆盖端点−最早覆盖端点)/20+90 秒，无覆盖为 0；每塔容量 DPS×W。",
              "第一阶段": first, "容量模型界": model_bound, "第二阶段": second,
              "完整模型验回": solution, "仿真值": simulation, "报告口径": decision,
              "独立解析界": {"连续战斗总伤害上界HP": 16710, "至少漏怪": 1, "引用": "PR #5"},
              "旧池化模型": {"状态": "近似失真案例，0 漏结论作废，不进入任何下界引用",
                              "旧模型漏怪": 0, "旧布局双步长仿真漏怪": [10, 10],
                              "历史原始记录": "results/t2.2/legacy-pooled.json"},
              "求解说明": "用固定击杀数的精确投影分解两阶段，求解后构造 dmg、leak 并验回每条完整约束。",
              "候选SHA256": source_hash, "运行时间秒": perf_counter() - start, "状态": REVIEW}
    Path("handoffs/T2.2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"模型界": model_bound, "仿真漏怪": [r["漏怪数"] for r in simulation.get("正式复跑", [])] if simulation else None,
                      "运行时间秒": report["运行时间秒"], "报告口径": decision}, ensure_ascii=False))


if __name__ == "__main__":
    main()
