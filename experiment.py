"""T5.1 单因素机制和选址对照，输出可追溯的逐敌实测与图源 CSV。"""

import csv
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

import numpy as np

from coverage import cover_intervals
from geometry import _CUMULATIVE, _VERTICES, dist_to_path
from layout_rules import A1_WAVE, INITIAL_CASH, REVIEW, validate_layout
from simulate import TOWER_STATS, _self_checks, simulate


SEED = 42  # 固定配对场景；没有随机扰动。
STEPS = (0.05, 0.01)


def straight_pair(bend, data):
    """在 BC 直线内匹配同塔型对照，优先接近弯道组的相对塔位和距路。"""
    b, c = _VERTICES[2:4]
    mid = (b + c) / 2
    length = float(_CUMULATIVE[3] - _CUMULATIVE[2])
    along = (c - b) / length
    normal = np.array([-along[1], along[0]])
    positions, kinds = data["xy_m"], data["tower_types"].tolist()
    starts, ends = data["interval_offsets"], data["intervals_m"]
    road = data["distance_to_road_m"]
    taken, layout = set(), []
    for x, y, name in bend:
        k = kinds.index(name)
        radius, _ = TOWER_STATS[name]
        original = np.array([x, y])
        offset = original - b
        # 控制纵向在中段，横向保留同侧与相近距路，防止直道组射程跨到拐角。
        stretch = np.clip(offset @ along, -0.5 * length + radius, 0.5 * length - radius)
        expected = mid + along * stretch + normal * np.sign(offset @ normal) * dist_to_path(x, y)
        error = np.linalg.norm(positions - expected, axis=1) + np.abs(road - dist_to_path(x, y))
        for p in np.argsort(error, kind="stable"):
            if p in taken:
                continue
            i = len(kinds)*p + k
            intervals = ends[starts[i]:starts[i+1]]
            if (len(intervals) and np.any(intervals[:, 1] > intervals[:, 0])
                    and np.min(intervals) > _CUMULATIVE[2] and np.max(intervals) < _CUMULATIVE[3]):
                taken.add(p)
                layout.append([*positions[p].tolist(), name])
                break
        else:
            raise RuntimeError(f"找不到 {name} 的 BC 直道对应候选")
    return layout


def run(label, towers, mode):
    """记录关卡战斗结果，平均击杀时刻按关卡起点计，资金按造价占预算计。"""
    cost, counts = validate_layout(towers, INITIAL_CASH)
    fights = []
    for dt in STEPS:
        fight = simulate(towers, A1_WAVE, dt, targeting=mode)
        enemies = fight["每只敌人结果"]
        deaths = [row["死亡时刻"] for row in enemies if row["结果"] == "击杀"]
        fights.append({"dt": dt, "漏怪数": fight["漏怪数"], "击杀数": len(deaths),
                       "平均击杀时刻秒": mean(deaths) if deaths else None,
                       "资金利用率": cost / INITIAL_CASH, "逐敌": enemies})
    agreement = [e["结果"] for e in fights[0]["逐敌"]] == [e["结果"] for e in fights[1]["逐敌"]]
    return {"场景": label, "机制": mode, "塔布局": towers, "塔型数量": counts, "造价元": cost,
            "双步长逐敌一致": agreement, "实测": fights}


def main():
    """执行两组对照，附原规则参考、结果表及绘图数据。"""
    start = perf_counter()
    anneal = json.loads(Path("results/t3.2/result.json").read_text(encoding="utf-8"))
    bend = anneal["布局"]
    candidates = Path("results/t2.1/candidates.npz")
    with np.load(candidates, allow_pickle=False) as data:
        straight = straight_pair(bend, data)
    assert [x[2] for x in straight] == [x[2] for x in bend]
    assert any(a < _CUMULATIVE[2] < b for x, y, k in bend for a, b in cover_intervals(x, y, TOWER_STATS[k][0]))
    # 同一批塔、波次和预算只切换目标机制；位置对照保留原机制和塔型。
    nearest = run("弯道原规则（两组参照）", bend, "nearest")
    assert nearest["实测"][0]["逐敌"] == anneal["正式复核"][0]["逐敌"]
    distributed = run("弯道分散（机制组 A）", bend, "spread")
    concentrated = run("弯道集火（机制组 B）", bend, "focus")
    line = run("直道原规则（位置组 B）", straight, "nearest")
    cases = [nearest, distributed, concentrated, line]
    checks = _self_checks()
    assert all(check["通过"] for check in checks)
    out = Path("results/t5.1")
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    with (out / "enemy-plot-source.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["场景", "步长秒", "敌人", "结局", "终局秒", "剩余HP", "承伤HP"])
        for case in cases:
            for trial in case["实测"]:
                summary.append({"场景": case["场景"], "造价元": case["造价元"],
                                **{key: value for key, value in trial.items() if key != "逐敌"}})
                for enemy in trial["逐敌"]:
                    when = enemy["死亡时刻"] if enemy["结果"] == "击杀" else enemy["漏怪时刻"]
                    writer.writerow([case["场景"], trial["dt"], enemy["编号"], enemy["结果"], when,
                                     enemy["剩余血量"], enemy["累计承伤"]])
    with (out / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, list(summary[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary)
    handoff = {"任务": "T5.1", "种子": SEED, "波次": A1_WAVE, "运行时间秒": perf_counter() - start,
               "机制对照": {"A": "每塔优先选择本步已分配 DPS 最少的目标，等值择最近再择编号",
                        "B": "每塔优先选择射程内当前血量最低的目标，等值择编号", "原规则对照": nearest["场景"]},
               "位置对照": {"A": "B 弯道", "B": "BC 直道，覆盖严格不越过 BC 两端",
                        "控制": "塔型、数量、预算、波次和最近目标机制相同；塔心与距离为匹配的近似几何条件。"},
               "原战斗自检通过项": len(checks), "原规则逐敌对拍通过": True,
               "汇总": summary, "数据": [str(out / name) for name in ("comparison.csv", "enemy-plot-source.csv", "result.json")],
               "候选SHA256": hashlib.sha256(candidates.read_bytes()).hexdigest(), "状态": REVIEW}
    (out / "result.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path("handoffs/T5.1.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(handoff, ensure_ascii=False))


if __name__ == "__main__":
    main()
