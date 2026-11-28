"""从已留档的第一阶段继续，固定漏 1，只重解资金目标并复跑仿真。"""

import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from anneal_a1 import replay
from layout_rules import INITIAL_CASH, REVIEW, validate_layout
from solve_a1_ilp import ENEMIES, HP, load_candidates, solve_projected, verify_original


CHECKPOINT = "da9e67bf9c5247fdc8db69e8efe31e3c0b6236a2"
LIMIT_SECONDS = 1200


def main():
    """校验第一阶段留档，保存续跑日志、最省钱塔位和双步长逐敌对照。"""
    started = perf_counter()
    handoff = Path("handoffs/T2.2.json")
    previous = json.loads(handoff.read_text(encoding="utf-8"))
    first = {row["拟击杀数"]: row for row in previous["第一阶段"]}
    if (previous["容量模型界"] != 1 or not first[10]["已证明不可行"]
            or not first[9]["可行解已回读"] or first[9]["每敌可分配HP"] < HP):
        raise ValueError("检查点缺少固定 1 漏的第一阶段证据")
    proof_files = [handoff, *(Path(row["日志"]) for row in first.values())]
    proofs = {path.as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in proof_files}
    points, kinds, damage, windows, capacity, candidate_hash = load_candidates()
    if candidate_hash != previous["候选SHA256"]:
        raise ValueError("候选数据与检查点不一致")

    # 仅构造固定 k=9 的等价投影，成本目标直接复用原第二阶段实现。
    kills = ENEMIES - 1
    coeff = np.minimum(damage, capacity / kills)
    stage, selected = solve_projected(coeff, kinds, Path("results/t2.2"),
                                      "capacity-stage2-resume", started + LIMIT_SECONDS, second=True)
    report = {"任务": "T2.2 塔侧容量修正续跑", "checkpoint": CHECKPOINT,
              "复跑命令": "python -X utf8 -B resume_a1_ilp_stage2.py",
              "环境": previous["环境"], "种子": previous["种子"], "候选SHA256": candidate_hash,
              "第一阶段重跑": False, "第一阶段记录SHA256": proofs,
              "容量模型界": 1, "独立解析界": previous["独立解析界"],
              "独立预算枚举": {str(k): first[k]["独立预算枚举"] for k in (10, 9)},
              "第二阶段": stage, "旧池化模型": previous["旧池化模型"], "状态": REVIEW,
              "报告口径": "容量修正后模型界仍为 1，问题一下界以解析界为准"}
    if stage.get("已证明最优"):
        towers = [[*points[p].tolist(), kinds[t]] for p, t in selected]
        cost, counts = validate_layout(towers, INITIAL_CASH)
        expected_cost = first[9]["独立预算枚举"]["最小可行造价元"]
        if cost != expected_cost or INITIAL_CASH - cost != stage["剩余资金元"]:
            raise ValueError("第二阶段最优造价与预算枚举或求解器余额不一致")
        allocation = verify_original(selected, kills, kinds, damage, capacity)
        if not allocation["完整模型验回通过"]:
            raise ValueError("固定 1 漏后，逐敌伤害分配验回失败")
        for tower in allocation["已选塔分配"]:
            tower["时间窗秒"] = float(windows[tower["点"] - 1, kinds.index(tower["塔型"])])
        runs, same = replay(towers)
        report["模型可行分配"] = allocation
        report["第二阶段布局"] = {"成本元": cost, "预算余量元": INITIAL_CASH - cost, "塔数": counts,
                                   "塔位": [{"点": p+1, "塔型": kinds[t], "坐标米": points[p].tolist()}
                                            for p, t in selected]}
        report["正式仿真"] = {"双步长逐敌一致": same, "实测轮次": runs,
                               "仿真漏怪减模型漏怪": [run["漏怪数"] - 1 for run in runs]}
        report["证据范围"] = "模型允许把火力分给任意未漏敌人。其 9 杀分配只证明模型可行，实战按最近目标及实际在场时间结算。"
    else:
        report["第二阶段说明"] = "限时内未得到完整求解器证明，第一阶段及原检查点证据保留。"
    report["运行时间秒"] = perf_counter() - started
    Path("handoffs/T2.2-resume.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("容量模型界", "第二阶段布局", "运行时间秒")}, ensure_ascii=False))
    return 0 if report.get("正式仿真", {}).get("双步长逐敌一致") else 1


if __name__ == "__main__":
    raise SystemExit(main())
