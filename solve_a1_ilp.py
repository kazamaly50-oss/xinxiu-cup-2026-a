"""按队长给定的乐观伤害模型分两阶段求解，并单独复跑真实战斗。"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

import numpy as np
import pulp

from anneal_a1 import replay
from layout_rules import COST, INITIAL_CASH, REVIEW, validate_layout


def main():
    """保存两个求解日志、模型界、真实仿真与运行时间。"""
    start = perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/t2.2"))
    args = parser.parse_args()
    if pulp.__version__ != "2.8.0":
        raise RuntimeError(f"需要 PuLP 2.8.0，实测 {pulp.__version__}")
    args.output.mkdir(parents=True, exist_ok=True)
    source = Path("results/t2.1/candidates.npz")
    with np.load(source, allow_pickle=False) as data:
        points, kinds, damage = data["xy_m"], data["tower_types"].tolist(), data["damage_hp"]
    if damage.shape != (1382, 3):
        raise ValueError(f"候选矩阵维度不符：{damage.shape}")

    model = pulp.LpProblem("A1_optimistic_damage", pulp.LpMinimize)
    x = {(p, t): pulp.LpVariable(f"x_{p+1}_{t+1}", cat="Binary")
         for p in range(len(points)) for t in range(len(kinds))}
    leak = [pulp.LpVariable(f"leak_{e}", cat="Binary") for e in range(1, 11)]
    spending = pulp.lpSum(COST[kinds[t]] * var for (p, t), var in x.items())
    damage_sum = pulp.lpSum(float(damage[p, t]) * var for (p, t), var in x.items())
    model += spending <= INITIAL_CASH, "budget"
    for p in range(len(points)):
        model += pulp.lpSum(x[p, t] for t in range(len(kinds))) <= 1, f"one_tower_{p+1}"
    for e, variable in enumerate(leak, 1):
        # 队长口径：每只敌人使用同一组单敌理论伤害系数。
        model += damage_sum >= 1700 * (1 - variable), f"enemy_{e}_optimistic_damage"

    def solve(name):
        """执行 CBC 单线程，保存日志并核验最优性证明状态。"""
        log = args.output / f"{name}.cbc.log"
        solver = pulp.PULP_CBC_CMD(threads=1, timeLimit=100, logPath=str(log),
                                   options=["randomSeed 42", "randomCbcSeed 42"])
        stage_started = perf_counter()
        model.solve(solver)
        seconds = perf_counter() - stage_started
        # 去除 CBC 自带的行末空格，保留日志内容和全部求解数值。
        lines = log.read_text(encoding="utf-8").splitlines()
        log.write_text("\n".join(line.rstrip() for line in lines).rstrip() + "\n", encoding="utf-8")
        if model.status != pulp.LpStatusOptimal or model.sol_status != pulp.LpSolutionOptimal:
            raise RuntimeError(f"{name} 未证明最优：{pulp.LpStatus[model.status]}，见 {log}")
        return {"状态": pulp.LpStatus[model.status], "运行时间秒": seconds, "日志": str(log),
                "求解器": solver.name, "求解器路径": solver.path}

    model.setObjective(pulp.lpSum(leak))
    first = solve("stage1")
    leak_bound = int(round(pulp.value(pulp.lpSum(leak))))
    model += pulp.lpSum(leak) == leak_bound, "fixed_first_stage"
    model.sense = pulp.LpMaximize
    model.setObjective(INITIAL_CASH - spending)
    second = solve("stage2")

    chosen = [(p, t) for (p, t), var in x.items() if var.value() > 0.5]
    towers = [[*points[p].tolist(), kinds[t]] for p, t in chosen]
    cost, _ = validate_layout(towers, INITIAL_CASH)
    optimistic_damage = sum(float(damage[p, t]) for p, t in chosen)
    assert cost == round(pulp.value(spending)) and cost <= INITIAL_CASH
    assert all(optimistic_damage + 1e-7 >= 1700 * (1 - var.value()) for var in leak)
    real, agrees = replay(towers)
    report = {"任务": "T2.2", "环境": {"Python": platform.python_version(), "可执行文件": sys.executable,
              "PuLP": pulp.__version__, "NumPy": np.__version__}, "种子": 42,
              "模型界": {"最少漏怪": leak_bound, "剩余资金元": INITIAL_CASH - cost,
                       "每敌乐观可用伤害HP": optimistic_damage, "第一阶段": first, "第二阶段": second},
              "仿真值": {"布局": towers, "候选点与塔型": [[p+1, kinds[t]] for p, t in chosen],
                        "造价元": cost, "正式复跑": real, "逐敌一致": agrees},
              "定位": "固定候选集上的乐观下界。单敌理论伤害重复给每敌使用，忽略火力分摊与超杀；仿真漏怪只取实测。",
              "独立连续模型界": "解析总伤害上界 16710 HP 对连续场地给出至少漏 1 只，证据见 PR #5。二者分别给出下界，解析界可更强。",
              "候选SHA256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "运行时间秒": perf_counter() - start, "状态": REVIEW}
    Path("handoffs/T2.2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"模型界": leak_bound, "最小造价元": cost, "仿真漏怪": [r["漏怪数"] for r in real],
                      "运行时间秒": report["运行时间秒"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
