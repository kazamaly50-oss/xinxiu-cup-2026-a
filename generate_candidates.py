"""T2.1：生成静态塔位候选及各塔型的覆盖区间，供后续优化选择。"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

from coverage import cover_intervals
from geometry import _LENGTHS, _SEGMENTS, _VERTICES, dist_to_path, path_length
from simulate import TOWER_STATS


ROOT = Path(__file__).resolve().parent
MAP_SIDE_M = 2000
MAP_MARGIN_M = 10
ROAD_MIN_M = 15
SPACING_M = 20
ENEMY_SPEED_MPS = 20
SEED = 42  # 本算法全用确定性采样，交接记录统一种子，不消耗随机数。
RING_RADII_M = (15, 30, 50, 75, 100, 125, 150, 200)
RING_ANGLE_DEG = 15
NORMAL_OFFSETS_M = (15, 25, 40, 60, 90, 120, 160, 190)
NORMAL_STEP_MAX_M = 20
GRID_STEP_M = 100
SOURCES = ("vertex_ring", "path_normal", "grid_100m")
TOWER_NAMES = ("小塔", "中塔", "大塔")
TOWER_KEYS = ("small", "medium", "large")


def sample_points():
    """依次生成 (x, y, 来源)，坐标以米计。交界处的重复点留给统一去重。"""
    # 顶点周围射程叠加的形状随转角改变，用多个半径采整圈，再统一过滤。
    for x, y in _VERTICES:
        for radius in RING_RADII_M:
            for degree in range(0, 360, RING_ANGLE_DEG):
                angle = math.radians(degree)
                yield x + radius * math.cos(angle), y + radius * math.sin(angle), SOURCES[0]

    # 每段沿弧长均分，法线指向两侧；端点由环带负责，法线只放内部采样点。
    for start, delta, length in zip(_VERTICES[:-1], _SEGMENTS, _LENGTHS, strict=True):
        normal = np.array([-delta[1], delta[0]]) / length
        n = math.ceil(length / NORMAL_STEP_MAX_M)
        for i in range(1, n):
            center = start + (i / n) * delta
            for offset in NORMAL_OFFSETS_M:
                for side in (-1, 1):
                    x, y = center + side * offset * normal
                    yield x, y, SOURCES[1]

    # 以地图原点为锚点铺 100 m 网格，补足远离道路的可建区域。
    for x in range(0, MAP_SIDE_M + 1, GRID_STEP_M):
        for y in range(0, MAP_SIDE_M + 1, GRID_STEP_M):
            yield x, y, SOURCES[2]


def generate():
    """返回保留塔位及逐来源计数，每个塔位含坐标、距路和三类覆盖区间。"""
    counters = {source: Counter({key: 0 for key in
                ("原始", "越界剔除", "距路剔除", "去重剔除", "保留")}) for source in SOURCES}
    legal = []
    for x, y, source in sample_points():
        stats = counters[source]
        stats["原始"] += 1
        if not all(MAP_MARGIN_M <= val <= MAP_SIDE_M - MAP_MARGIN_M for val in (x, y)):
            stats["越界剔除"] += 1
            continue
        road = dist_to_path(x, y)
        if road < ROAD_MIN_M:
            stats["距路剔除"] += 1
            continue
        intervals = [cover_intervals(x, y, TOWER_STATS[kind][0]) for kind in TOWER_NAMES]
        lengths = tuple(math.fsum(end - start for start, end in spans) for spans in intervals)
        legal.append((float(x), float(y), source, road, lengths, intervals))

    # 按大、中、小塔的覆盖长度降序。大塔最大射程决定主排序。
    # 覆盖完全相同时用坐标、来源固定顺序；点间严格小于 20 m 才去重。
    legal.sort(key=lambda row: (*(-v for v in reversed(row[4])), row[0], row[1], SOURCES.index(row[2])))
    kept = []
    coordinates = np.empty((len(legal), 2))
    for row in legal:
        x, y, source = row[:3]
        delta = coordinates[:len(kept)] - (x, y)
        if np.any(np.hypot(delta[:, 0], delta[:, 1]) < SPACING_M):
            counters[source]["去重剔除"] += 1
            continue
        coordinates[len(kept)] = (x, y)
        kept.append(row)
        counters[source]["保留"] += 1
    return kept, counters


def save_candidates(out_dir, rows):
    """写出同序的 NPZ 及 CSV，返回覆盖长度与理论伤害矩阵。"""
    coordinates = np.array([row[:2] for row in rows], dtype=float)
    sources = np.array([row[2] for row in rows])
    road_m = np.array([row[3] for row in rows], dtype=float)
    coverage_m = np.array([row[4] for row in rows], dtype=float)
    dps = np.array([TOWER_STATS[name][1] for name in TOWER_NAMES])
    # 单敌匀速通过时，射程内的时间为覆盖弧长除以速度，再乘 DPS。
    damage_hp = (coverage_m / ENEMY_SPEED_MPS) * dps
    ids = np.arange(1, len(rows) + 1, dtype=np.int64)

    # 每个 (候选点, 塔型) 可有多个区间。以扁平数组加偏移量存储，读取时无需 pickle。
    offsets = [0]
    spans = []
    for row in rows:
        for intervals in row[5]:
            spans.extend(intervals)
            offsets.append(len(spans))
    np.savez_compressed(out_dir / "candidates.npz", ids=ids, xy_m=coordinates, sources=sources,
                        distance_to_road_m=road_m, tower_types=np.array(TOWER_NAMES),
                        coverage_m=coverage_m, damage_hp=damage_hp,
                        interval_offsets=np.array(offsets, dtype=np.int64),
                        intervals_m=np.array(spans, dtype=float).reshape(-1, 2))
    with (out_dir / "candidates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["id", "x_m", "y_m", "source", "distance_to_road_m",
                         *(f"{name}_coverage_m" for name in TOWER_KEYS),
                         *(f"{name}_damage_hp" for name in TOWER_KEYS)])
        for index, point in enumerate(coordinates):
            writer.writerow([ids[index], *point, sources[index], road_m[index],
                             *coverage_m[index], *damage_hp[index]])
    return coverage_m, damage_hp


def describe(values):
    """返回全候选点的覆盖分布，统计分位数时包含零覆盖点。"""
    quantiles = np.quantile(values, [0.0, 0.25, 0.5, 0.75, 1.0])
    return {"零覆盖数": int(np.count_nonzero(values == 0)),
            "正覆盖数": int(np.count_nonzero(values > 0)),
            **dict(zip(("最小", "P25", "中位", "P75", "最大"), quantiles.tolist(), strict=True)),
            "均值": float(np.mean(values))}


def main():
    """从当前检出的代码生成数据和汇总，要求提供正式 main 基线提交。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/t2.1"), help="输出目录")
    parser.add_argument("--main-ref", default="origin/main", help="包含三模块的正式 main 基线")
    args = parser.parse_args()
    started = time.perf_counter()
    base = subprocess.check_output(["git", "rev-parse", "--verify", args.main_ref + "^{commit}"],
                                   cwd=ROOT, text=True).strip()
    cores = {}
    for path in ("geometry.py", "coverage.py", "simulate.py"):
        baseline = subprocess.check_output(["git", "cat-file", "blob", f"{base}:{path}"], cwd=ROOT)
        working = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        if baseline != working:
            parser.error(f"核心模块与 main 基线不同：{path}")
        cores[path] = hashlib.sha256(baseline).hexdigest()

    rows, counters = generate()
    args.output.mkdir(parents=True, exist_ok=True)
    length, damage = save_candidates(args.output, rows)
    totals = {key: sum(row[key] for row in counters.values()) for key in next(iter(counters.values()))}
    report = {"任务编号": "T2.1", "main基线": base,
              "日期": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
              "环境": {"Python": platform.python_version(), "解释器": sys.executable, "NumPy": np.__version__},
              "统一种子": SEED, "采样方式": "确定性，无随机抽样",
              "阈值米": {"图内闭区间": [MAP_MARGIN_M, MAP_SIDE_M - MAP_MARGIN_M],
                         "距路至少": ROAD_MIN_M, "去重距离严格小于": SPACING_M},
              "采样参数": {"环带半径米": RING_RADII_M, "环带角步长度": RING_ANGLE_DEG,
                           "法线偏移米": NORMAL_OFFSETS_M, "法线沿路最大步长米": NORMAL_STEP_MAX_M,
                           "网格步长米": GRID_STEP_M},
              "路径总长米": path_length(), "单敌速度米每秒": ENEMY_SPEED_MPS,
              "各来源计数": counters, "总计": totals,
              "硬过滤剔除总数": totals["越界剔除"] + totals["距路剔除"],
              "各塔型": {kind: {"覆盖弧长米": describe(length[:, i]), "理论伤害HP": describe(damage[:, i])}
                        for i, kind in enumerate(TOWER_NAMES)},
              "理论伤害口径": "单塔持续攻击一只匀速敌人的理论伤害，未建模目标竞争与终局血量截断。",
              "去重口径": "大、中、小塔覆盖长度依次降序，平局按坐标与来源，保留点间距至少20米。",
              "候选范围": "有限采样加近邻去重，用于后续优化，结论仅涵盖保留候选。",
              "核心模块Git内容SHA256": cores,
              "产物SHA256": {file: hashlib.sha256((args.output / file).read_bytes()).hexdigest()
                             for file in ("candidates.npz", "candidates.csv")}}
    report["生成耗时秒"] = time.perf_counter() - started
    report["计时范围"] = "命令解析后到两份数据文件写出并计算哈希，外部全进程时间见交接 JSON。"
    (args.output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(totals, ensure_ascii=False))


if __name__ == "__main__":
    main()
