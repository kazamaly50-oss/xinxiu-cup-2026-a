"""问题二按波滚动贪心与局部搜索，输出正式仿真流水。"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from geometry import path_length, pos
from layout_rules import COST, INITIAL_CASH, REVIEW, STOCK
from simulate import TOWER_STATS, simulate
from simulate_a2 import WAVES, configure_wave, settle_wave, simulate_campaign


SEED = 42
SCREEN_DT = 0.5
FINAL_DT = 0.05


def damage_proxy(points, wave, kinds):
    """计算单塔对各敌人的步首最近分配近似；只用于提议操作。"""
    end = path_length()
    births = np.arange(wave["数量"]) * wave["出发间隔"]
    travel = end / wave["速度"]
    ticks = np.arange(0, travel + births[-1], SCREEN_DT)
    age = ticks[:, None] - births
    active = (age >= 0) & (age < travel)
    arc = np.clip(age * wave["速度"], 0, end)
    positions = np.array([pos(float(s)) for s in arc.ravel()]).reshape((*arc.shape, 2))
    duration = np.minimum(SCREEN_DT, np.maximum(0, travel - age))
    block = np.empty((len(points), len(kinds), len(births)))
    time_index = np.arange(len(ticks))
    for start in range(0, len(points), 48):
        offsets = points[start:start+48, None, None, :] - positions
        distances = np.where(active, np.hypot(offsets[..., 0], offsets[..., 1]), np.inf)
        target = distances.argmin(axis=-1)
        closest = np.take_along_axis(distances, target[..., None], axis=-1)[..., 0]
        for local, enemies in enumerate(target):
            for j, kind in enumerate(kinds):
                radius, dps = TOWER_STATS[kind]
                rates = (closest[local] <= radius) * dps * duration[time_index, enemies]
                block[start + local, j] = np.bincount(enemies, weights=rates, minlength=len(births))
    return block


def propose_batches(towers, cash, wave, points, kinds, proxy, rng):
    """用不同权重和资金留存值提出操作组，包含成组跨过零击杀门槛。"""
    id_by_position = {tuple(point): i for i, point in enumerate(points)}
    original = {id_by_position[tuple(t[:2])]: (i + 1, kinds.index(t[2])) for i, t in enumerate(towers)}
    prices = np.array([COST[k] for k in kinds])
    inventory = np.array([STOCK[k] for k in kinds])
    base = sum((proxy[p, j] for p, (_, j) in original.items()), np.zeros(wave["数量"]))
    hp = wave["血量"]
    hit = np.ones(wave["数量"])
    edges = hit.copy()
    edges[[0, -1]] = 2.7
    middle = hit.copy()
    middle[1:-1] = 2.1
    configurations = [(edges, 3, 0.72), (hit, 1, 0.76), (middle, 1, 0.8),
                      (edges[::-1], 3, 0.92), (hit, 3, 1.0), (middle, 3, 0.6)]
    result = {}
    positive = np.any(proxy > 0, axis=-1)
    for trial_index, (weights, power, bias) in enumerate(configurations):
        for savings in (0, min(350, cash // 4)):
            cumulative = base.copy()
            used = set()
            counts = np.bincount([j for _, j in original.values()], minlength=len(kinds))
            increments = proxy.copy()
            price = np.tile(prices, (len(points), 1))
            for point, (_, old) in original.items():
                increments[point] -= proxy[point, old]
                price[point] -= prices[old]
            budget = cash - savings
            sequence = []
            while budget >= 100:
                allowed = positive & (price > 0) & (price <= budget) & (counts < inventory)
                if used:
                    allowed[list(used)] = False
                after = np.minimum(np.maximum(0, cumulative + increments), hp) / hp
                before = np.minimum(cumulative, hp) / hp
                utility = (after**power - before**power) @ weights
                utility += (increments / hp) @ (0.06 * weights)
                gains = np.where(allowed, utility / (np.maximum(1, price) / 100)**bias, -np.inf)
                ranking = np.argsort(-gains.ravel(), kind="stable")
                flat = int(ranking[0])
                if not sequence and trial_index % 2:
                    pool = [int(r) for r in ranking[:12] if gains.ravel()[r] > 0]
                    if pool:
                        flat = int(rng.choice(pool))
                p, new = (int(value) for value in np.unravel_index(flat, gains.shape))
                if gains[p, new] <= 0:
                    break
                if p in original:
                    serial, old = original[p]
                    counts[old] -= 1
                    sequence.append({"动作": "升", "塔号": serial, "塔型": kinds[new]})
                else:
                    sequence.append({"动作": "建", "x": float(points[p, 0]),
                                     "y": float(points[p, 1]), "塔型": kinds[new]})
                counts[new] += 1
                used.add(p)
                budget -= int(price[p, new])
                cumulative += increments[p, new]
            for i in {len(sequence), max(0, len(sequence) - 1)}:
                if i:
                    batch = sequence[:i]
                    result[json.dumps(batch, sort_keys=True)] = batch
    return list(result.values())


def rolling(points, kinds, proxies):
    """逐波最大化操作组的单位成本新增击杀，在边际无益时停建。"""
    rng = np.random.default_rng(SEED)
    plan, towers, cash = [], [], INITIAL_CASH
    for wave_index, wave in enumerate(WAVES):
        wave_plan = []
        current = simulate(towers, wave, FINAL_DT)
        while cash >= 100 and current["漏怪数"]:
            scored = []
            for batch in propose_batches(towers, cash, wave, points, kinds, proxies[wave_index], rng):
                try:
                    trial, left, _ = configure_wave(towers, cash, batch)
                except ValueError:
                    continue
                rough = simulate(trial, wave, SCREEN_DT)["漏怪数"]
                spent = cash - left
                scored.append(((current["漏怪数"] - rough) / spent, -rough, -spent, batch, trial, left))
            scored.sort(key=lambda row: row[:3], reverse=True)
            verified = []
            for _, _, _, batch, trial, left in scored[:5]:
                run = simulate(trial, wave, FINAL_DT)
                gain = current["漏怪数"] - run["漏怪数"]
                if gain > 0:
                    verified.append(((gain / (cash - left), gain, left), batch, trial, left, run))
            if not verified:
                break
            _, batch, towers, cash, current = max(verified, key=lambda row: row[0])
            wave_plan.extend(batch)
        _, cash = settle_wave(cash, current, wave)
        plan.append(wave_plan)
        print(f"滚动贪心第 {wave_index+1} 波：漏 {current['漏怪数']}，结余 {cash} 元。", flush=True)
    return plan


def variants(plan, index, points, kinds):
    """对一波换点、换型或保留资金留待下一波升级。"""
    built = sum(action["动作"] == "建" for wave in plan[:index] for action in wave)
    used = {(action["x"], action["y"]) for wave in plan for action in wave if action["动作"] == "建"}
    for j, action in enumerate(plan[index]):
        if action["动作"] == "建":
            built += 1
            origin = action["x"], action["y"]
            deltas = points - origin
            order = np.argsort(np.hypot(deltas[:, 0], deltas[:, 1]), kind="stable")
            available = [p for p in order[:15] if tuple(points[p]) not in used]
            for p in available[:2]:
                adjusted = deepcopy(plan)
                adjusted[index][j]["x"], adjusted[index][j]["y"] = map(float, points[p])
                yield adjusted
            old = action["塔型"]
            for kind in kinds:
                if kind == old:
                    continue
                adjusted = deepcopy(plan)
                adjusted[index][j]["塔型"] = kind
                yield adjusted
                if index < len(WAVES) - 1 and COST[kind] < COST[old]:
                    delayed = deepcopy(adjusted)
                    delayed[index + 1].insert(0, {"动作": "升", "塔号": built, "塔型": old})
                    yield delayed
        else:
            for kind in kinds:
                if kind != action["塔型"]:
                    adjusted = deepcopy(plan)
                    adjusted[index][j]["塔型"] = kind
                    yield adjusted
    # 延后本波最后一次建塔，仍保持塔号顺序；最后一波则允许省下这笔支出。
    if plan[index] and plan[index][-1]["动作"] == "建":
        adjusted = deepcopy(plan)
        action = adjusted[index].pop()
        if index < len(WAVES) - 1:
            adjusted[index + 1].insert(0, action)
        yield adjusted


def improve(plan, initial, points, kinds):
    """按全程总漏怪和最终资金择优，粗筛提议后用 0.05 秒复核。"""
    objective = lambda result: (result["总漏怪"], -result["最终资金元"])
    best = initial
    counts = []
    for wave_index in range(len(WAVES)):
        shortlist = []
        for trial in variants(plan, wave_index, points, kinds):
            try:
                result = simulate_campaign(trial, SCREEN_DT)
            except ValueError:
                continue
            shortlist.append((objective(result), trial))
        shortlist.sort(key=lambda row: row[0])
        counts.append(len(shortlist))
        for _, trial in shortlist[:5]:
            try:
                actual = simulate_campaign(trial, FINAL_DT)
            except ValueError:
                continue
            if objective(actual) < objective(best):
                plan, best = trial, actual
        print(f"改进第 {wave_index+1} 波：比较 {len(shortlist)} 个可行邻域，全程漏 {best['总漏怪']}，余 {best['最终资金元']} 元。", flush=True)
    return plan, best, counts


def main():
    """执行基线、改进和较小步长复核，保存逐波计划及交接。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/a2-planning"))
    args = parser.parse_args()
    start = perf_counter()
    source = Path("results/t2.1/candidates.npz")
    with np.load(source, allow_pickle=False) as data:
        points, kinds = data["xy_m"], data["tower_types"].tolist()
    proxies = [damage_proxy(points, wave, kinds) for wave in WAVES]
    build_time = perf_counter() - start
    phase = perf_counter()
    baseline_plan = rolling(points, kinds, proxies)
    baseline = simulate_campaign(baseline_plan, FINAL_DT)
    baseline_time = perf_counter() - phase
    phase = perf_counter()
    plan, best, tried = improve(baseline_plan, baseline, points, kinds)
    improved_time = perf_counter() - phase
    variants_report = {}
    for name, current_plan, logged, elapsed in (("滚动贪心", baseline_plan, baseline, baseline_time),
                                                ("局部改进", plan, best, improved_time)):
        phase = perf_counter()
        try:
            fine = simulate_campaign(current_plan, 0.01)
            left = [(e["编号"], e["结果"]) for wave in logged["逐波"] for e in wave["逐敌"]]
            right = [(e["编号"], e["结果"]) for wave in fine["逐波"] for e in wave["逐敌"]]
            check = {"逐敌一致": left == right, "资金一致": fine["最终资金元"] == logged["最终资金元"], "实测": fine}
        except ValueError as exc:
            check = {"逐敌一致": False, "失败项": str(exc)}
        variants_report[name] = {"计划": current_plan, "正式结果": logged, "运行时间秒": elapsed,
                                "缩步复核秒": perf_counter() - phase, "缩步复核": check}
    report = {"任务": "A2 滚动规划", "种子": SEED, "候选SHA256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "粗筛dt": SCREEN_DT, "正式dt": FINAL_DT, "预计算耗时秒": build_time,
              "改进邻域数": tried, "版本": variants_report, "运行时间秒": perf_counter() - start,
              "范围": "只在上波结束结算后的波前决策，原题任意时刻的全局最优性未证。", "状态": REVIEW}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "best-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    handoff = {key: value for key, value in report.items() if key != "版本"}
    handoff["结果"] = {key: {"逐波漏怪": [row["漏怪数"] for row in v["正式结果"]["逐波"]],
                             "总漏怪": v["正式结果"]["总漏怪"], "最终资金元": v["正式结果"]["最终资金元"],
                             "运行时间秒": v["运行时间秒"], "复核一致": v["缩步复核"]["逐敌一致"]}
                       for key, v in variants_report.items()}
    Path("handoffs/A2-planning.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(handoff, ensure_ascii=False))


if __name__ == "__main__":
    main()
