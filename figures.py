"""从 T3.2 原始证据及正式仿真生成中文论文图。"""

import argparse
import csv
import json
from pathlib import Path
from time import perf_counter

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.patches import Circle
from matplotlib.ticker import MaxNLocator
import numpy as np

from geometry import _VERTICES
from layout_rules import A1_WAVE, REVIEW
from simulate import TOWER_STATS, simulate


PALETTE = ["#507B9C", "#A76A51", "#659582", "#937BA6", "#B29A53", "#557482",
           "#C08091", "#7F9160", "#586384", "#99685D"]
DPI = 300


def save(fig, filename):
    """保存 300 dpi PNG 并释放绘图资源。"""
    fig.savefig(filename, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def layout_plot(layout, out):
    """绘制路径、塔型符号、塔号和大塔射程圈。"""
    fig, ax = plt.subplots(figsize=(6.4, 6.0), layout="constrained")
    ax.plot(*_VERTICES.T, color="#4C4C4C", linewidth=1.7, label="道路中心线", zorder=2)
    zoom = ax.inset_axes([0.57, 0.09, 0.39, 0.37])
    zoom.plot(*_VERTICES.T, color="#4C4C4C", linewidth=1.3, zorder=2)
    centers = np.array([row[:2] for row in layout])
    lower, upper = centers.min(axis=0) - 35, centers.max(axis=0) + 35
    zoom.set(xlim=(lower[0], upper[0]), ylim=(lower[1], upper[1]), title="塔位局部放大")
    zoom.set_aspect("equal")
    zoom.tick_params(labelsize=7)
    for (x, y), label in zip(_VERTICES, "OABCEFD", strict=True):
        ax.annotate(label, (x, y), xytext=(5, 3), textcoords="offset points", fontsize=8)
    for kind, marker, color in zip(("小塔", "中塔", "大塔"), ("o", "s", "^"), PALETTE, strict=False):
        points = [(j + 1, x, y) for j, (x, y, k) in enumerate(layout) if k == kind]
        if not points:
            continue
        coord = np.array([(x, y) for _, x, y in points])
        ax.scatter(*coord.T, marker=marker, s=45, color=color, edgecolor="white", linewidth=0.5, label=kind, zorder=3)
        zoom.scatter(*coord.T, marker=marker, s=25, color=color, edgecolor="white", linewidth=0.5, zorder=3)
        for j, x, y in points:
            if kind == "大塔":
                ax.add_patch(Circle((x, y), TOWER_STATS[kind][0], color=color, alpha=0.10, zorder=1))
            zoom.annotate(str(j), (x, y), xytext=(4, -4), textcoords="offset points", fontsize=8)
    ax.set(xlim=(-45, 2070), ylim=(-45, 2070), xlabel="横坐标（米）", ylabel="纵坐标（米）", title="问题一路径与退火布局")
    ax.set_aspect("equal")
    ax.legend(frameon=False, loc="upper left")
    ax.indicate_inset_zoom(zoom, edgecolor="#7F8D9A", alpha=0.55)
    save(fig, out / "a1-layout.png")


def health_plot(result, out):
    """由正式逐步累计承伤计算血量，保存 0.5 秒采样与终局点。"""
    fig, axes = plt.subplots(2, 1, figsize=(7.8, 5.3), sharex=True, layout="constrained")
    with (out / "a1-enemy-curves.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["enemy", "time_s", "damage_hp", "remaining_hp"])
        for line in result["累计承伤曲线"]:
            identifier, samples = line["编号"], line["采样"]
            reduced = samples[::10]
            if reduced[-1] != samples[-1]:
                reduced.append(samples[-1])
            seconds, loss = np.array(reduced).T
            hp = A1_WAVE["血量"] - loss
            writer.writerows(zip([identifier] * len(seconds), seconds, loss, hp, strict=True))
            color = PALETTE[identifier - 1]
            axes[0].plot(seconds, loss, color=color, linewidth=1.05, label=f"{identifier} 号")
            axes[1].plot(seconds, hp, color=color, linewidth=1.05)
    axes[0].set(ylabel="累计承伤（HP）", title="问题一逐敌累计承伤与剩余血量")
    axes[1].set(xlabel="仿真时刻（秒）", ylabel="剩余血量（HP）")
    axes[0].legend(ncol=5, loc="upper center", fontsize=7, frameon=False)
    save(fig, out / "a1-enemy-health.png")


def convergence_plot(curve, out):
    """以分图显示退火粗筛的当前与历次最好目标。"""
    with curve.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    t = np.array([float(row["wall_seconds"]) for row in rows])
    fig, axes = plt.subplots(2, 1, figsize=(7.8, 5.1), sharex=True, layout="constrained")
    for ax, name, label in zip(axes, ("leaks", "cost_yuan"), ("漏怪数（只）", "造价（元）"), strict=True):
        ax.step(t, [int(row[f"current_{name}"]) for row in rows], where="post", color=PALETTE[0],
                alpha=0.6, linewidth=0.8, label="当前布局")
        ax.step(t, [int(row[f"best_{name}"]) for row in rows], where="post", color=PALETTE[1],
                linewidth=1.6, label="按字典序的历史最好布局")
        ax.set_ylabel(label)
    axes[0].set_title("退火搜索的粗筛目标（步长 0.25 秒）")
    axes[0].yaxis.set_major_locator(MaxNLocator(integer=True))
    axes[0].legend(frameon=False, loc="best")
    axes[1].set_xlabel("计算时间（秒）")
    save(fig, out / "a1-annealing.png")


def main():
    """生成三张论文图和图源文件，输出字体、分辨率与运行时间。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/msyh.ttc"))
    args = parser.parse_args()
    start = perf_counter()
    font_manager.fontManager.addfont(str(args.font))
    family = font_manager.FontProperties(fname=str(args.font)).get_name()
    plt.rcParams.update({"font.family": family, "font.size": 9, "axes.spines.right": False,
                        "axes.spines.top": False, "axes.unicode_minus": False})
    root = Path("results/t3.2")
    layout = json.loads((root / "best-layout.json").read_text(encoding="utf-8"))
    report = json.loads((root / "result.json").read_text(encoding="utf-8"))
    fight = simulate(layout, A1_WAVE, dt=0.05)
    assert fight["每只敌人结果"] == report["正式复核"][0]["逐敌"]
    out = Path("results/figures")
    out.mkdir(parents=True, exist_ok=True)
    layout_plot(layout, out)
    health_plot(fight, out)
    convergence_plot(root / "convergence.csv", out)
    files = sorted(str(p) for p in out.iterdir())
    handoff = {"任务": "T6.2", "图件与承伤图源": files, "绘图字体": family, "dpi": DPI,
               "布局源": str(root / "best-layout.json"), "退火曲线源": str(root / "convergence.csv"),
               "承伤逐敌源": "simulate.py，dt=0.05，结局与 T3.2 逐敌日志一致",
               "运行时间秒": perf_counter() - start, "状态": REVIEW}
    Path("handoffs/T6.2.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(handoff, ensure_ascii=False))


if __name__ == "__main__":
    main()
