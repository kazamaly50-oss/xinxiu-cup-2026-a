"""固定退火最好布局，对问题一预算、初始血量逐项扰动。"""

import csv
import json
from pathlib import Path
from time import perf_counter

from layout_rules import A1_WAVE, REVIEW, validate_layout
from simulate import simulate


def main():
    """写出预算可行性、同布局的战斗反事实，以及血量扰动结果。"""
    start = perf_counter()
    layout = json.loads(Path("results/t3.2/best-layout.json").read_text(encoding="utf-8"))
    cost, _ = validate_layout(layout)
    rows = []
    for axis, choices in (("预算", (1800, 2000, 2200)), ("血量", (1600, 1700, 1800))):
        for value in choices:
            budget = value if axis == "预算" else 2000
            hp = value if axis == "血量" else A1_WAVE["血量"]
            result = simulate(layout, {**A1_WAVE, "血量": hp}, dt=0.05)
            feasible = budget >= cost
            rows.append({"扰动": axis, "预算元": budget, "初始HP": hp, "布局造价元": cost,
                         "布局可行": feasible, "预算余量元": budget - cost,
                         "可行漏怪": result["漏怪数"] if feasible else None,
                         "固定布局战斗漏怪": result["漏怪数"], "逐敌": result["每只敌人结果"]})
    root = Path("results/sensitivity")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "sensitivity.csv").open("w", newline="", encoding="utf-8") as stream:
        columns = [key for key in rows[0] if key != "逐敌"]
        writer = csv.DictWriter(stream, columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    handoff = {"任务": "T6.1", "数据": str(root / "sensitivity.csv"), "步长秒": 0.05,
               "结果": rows, "运行时间秒": perf_counter() - start,
               "说明": "固定布局复跑。资金不足的场景只列同布局的战斗反事实，可行漏怪留空。", "状态": REVIEW}
    Path("handoffs/T6.1.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps([{key: value for key, value in row.items() if key != "逐敌"} for row in rows], ensure_ascii=False))


if __name__ == "__main__":
    main()
