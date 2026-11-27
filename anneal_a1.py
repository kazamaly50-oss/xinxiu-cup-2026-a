"""在正式 T2.1 候选集上对 A1 布局退火，并保存双步长复核证据。"""

import argparse
import csv
import hashlib
import json
from math import exp, inf
from pathlib import Path
from time import perf_counter

import numpy as np

from layout_rules import A1_WAVE, COST, INITIAL_CASH, REVIEW, STOCK, validate_layout
from simulate import simulate


SEED = 42
SCREEN_DT = 0.25
FINE_STEPS = (0.05, 0.01)


def replay(towers):
    """按两档步长运行正式仿真，并比较编号与每只敌人的结局。"""
    validate_layout(towers, INITIAL_CASH)
    runs = []
    for dt in FINE_STEPS:
        result = simulate(towers, A1_WAVE, dt=dt)
        runs.append({"dt": dt, "漏怪数": result["漏怪数"], "逐敌": result["每只敌人结果"]})
    labels = [[(x["编号"], x["结果"]) for x in run["逐敌"]] for run in runs]
    return runs, runs[0]["漏怪数"] == runs[1]["漏怪数"] and labels[0] == labels[1]


def neighbor(state, rng, points, eligible):
    """均匀选择增塔、删塔、换塔型或迁移候选点，返回待校验的新布局。"""
    option = int(rng.integers(4))
    used = {p for p, _ in state}
    if option == 0 or not state:
        kind = int(rng.integers(len(eligible)))
        point = int(rng.choice(eligible[kind]))
        return state if point in used else tuple(sorted((*state, (point, kind))))
    index = int(rng.integers(len(state)))
    point, kind = state[index]
    remainder = state[:index] + state[index + 1:]
    if option == 1:
        return remainder
    if option == 2:
        promoted = (kind + int(rng.integers(1, len(eligible)))) % len(eligible)
        return tuple(sorted((*remainder, (point, promoted))))
    pool = eligible[kind]
    if rng.random() < 0.88:
        delta = points[pool] - points[point]
        local = pool[np.hypot(delta[:, 0], delta[:, 1]) <= 110]
        if len(local):
            pool = local
    target = int(rng.choice(pool))
    return state if target in used else tuple(sorted((*remainder, (target, kind))))


def anneal(seed, points, names, eligible, iterations, seconds):
    """在时间预算内搜索，返回正式复核后按漏怪、造价排序的最好布局。"""
    start = perf_counter()
    rng = np.random.default_rng(SEED)
    towers = lambda state: [[*points[i].tolist(), names[j]] for i, j in state]
    seed_runs, stable = replay(towers(seed))
    if not stable:
        raise RuntimeError("原贪心种子两档逐敌结局不一致")
    verified = [(seed_runs[-1]["漏怪数"], validate_layout(towers(seed))[0], seed, seed_runs)]
    state = seed
    initial = simulate(towers(seed), A1_WAVE, SCREEN_DT)["漏怪数"]
    scores = {seed: (initial, verified[0][1])}
    best = seed
    moves = 0
    # 一只漏怪的权重严格大于整个可用预算。SA 允许按温度暂时接受劣解。
    weight = INITIAL_CASH + 1
    trace = [[0, 0.0, initial, verified[0][1], initial, verified[0][1]]]
    ranked = []
    cutoff = start + seconds
    for tick in range(1, iterations + 1):
        if perf_counter() > cutoff - min(85, seconds * 0.25):
            break
        if tick % 175 == 1:
            state = best
        trial = neighbor(state, rng, points, eligible)
        if trial == state:
            continue
        if trial not in scores:
            layout = towers(trial)
            counts = np.bincount([j for _, j in trial], minlength=len(names))
            if any(n > STOCK[k] for n, k in zip(counts, names)):
                continue
            try:
                cost, _ = validate_layout(layout, INITIAL_CASH)
            except ValueError:
                continue
            leaks = simulate(layout, A1_WAVE, SCREEN_DT)["漏怪数"]
            scores[trial] = (leaks, cost)
        now, new = scores[state], scores[trial]
        delta = (new[0] - now[0]) + (new[1] - now[1]) / weight
        temperature = 0.23 * (0.008 / 0.23) ** ((tick - 1) % 175 / 174)
        if delta <= 0 or rng.random() < exp(-delta / temperature):
            state = trial
            moves += 1
        if new < scores[best]:
            best = trial
        trace.append([tick, perf_counter() - start, *scores[state], *scores[best]])
    search_elapsed = perf_counter() - start
    for trial, score in sorted(scores.items(), key=lambda row: (row[1], row[0])):
        if trial == seed:
            continue
        if len(ranked) >= 9 or perf_counter() > cutoff - min(18, seconds * 0.18):
            break
        runs, stable = replay(towers(trial))
        ranked.append({"布局": towers(trial), "粗筛目标": score, "逐敌一致": stable, "复核": runs})
        if stable:
            verified.append((runs[-1]["漏怪数"], score[1], trial, runs))
    # 两目标相同则按队内塔间距平局规则，最后由候选编号确定稳定顺序。
    from itertools import combinations
    from math import dist

    def rank(item):
        layout = towers(item[2])
        margin = min((dist(a[:2], b[:2]) - 20 for a, b in combinations(layout, 2)), default=inf)
        return item[0], item[1], -margin, item[2]

    leaks, spent, picked, runs = min(verified, key=rank)
    return {"布局": towers(picked), "漏怪数": leaks, "造价元": spent,
            "剩余元": INITIAL_CASH - spent, "正式复核": runs, "逐敌一致": True,
            "种子复核": seed_runs, "复核前列明细": ranked, "粗筛唯一仿真布局数": len(scores),
            "接受移动数": moves, "粗筛耗时秒": search_elapsed,
            "总耗时秒": perf_counter() - start, "限时秒": seconds, "最大提议数": iterations}, trace


def main():
    """读取固定候选数据与贪心种子，写出布局、时间曲线和交接 JSON。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--iterations", type=int, default=730)
    parser.add_argument("--output", type=Path, default=Path("results/t3.2"))
    args = parser.parse_args()
    if not 60 <= args.seconds <= 1800 or args.iterations < 1:
        parser.error("运行上限应为 60 至 1800 秒，提议数至少 1")
    source = Path("results/t2.1/candidates.npz")
    seed_file = Path("results/t3.2/greedy-seed.json")
    with np.load(source, allow_pickle=False) as data:
        points, names = data["xy_m"], data["tower_types"].tolist()
        eligible = [np.flatnonzero(values > 0) for values in data["damage_hp"].T]
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    point_ids = {tuple(point): i for i, point in enumerate(points)}
    seed = tuple(sorted((point_ids[x, y], names.index(kind)) for x, y, kind in seed))
    result, trace = anneal(seed, points, names, eligible, args.iterations, args.seconds)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "convergence.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["iteration", "wall_seconds", "current_leaks", "current_cost_yuan", "best_leaks", "best_cost_yuan"])
        writer.writerows(trace)
    (args.output / "best-layout.json").write_text(json.dumps(result["布局"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    handoff = {"任务": "T3.2", "种子": SEED, "粗筛dt": SCREEN_DT, "正式dt": FINE_STEPS,
               "漏怪数": result["漏怪数"], "造价元": result["造价元"], "逐敌一致": result["逐敌一致"],
               "运行时间秒": result["总耗时秒"], "计时范围": "含种子复核、退火、正式复核；不含启动导入与写盘",
               "范围": "候选集上的有限时启发式搜索，曲线是粗筛值，正式逐敌结果见 result.json",
               "候选SHA256": hashlib.sha256(source.read_bytes()).hexdigest(), "状态": REVIEW}
    Path("handoffs/T3.2.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(handoff, ensure_ascii=False))


if __name__ == "__main__":
    main()
