"""固定 PR #15 前三波，只搜索波 4 前的建塔和升级组合。"""

import argparse
from collections import Counter, deque
import csv
from datetime import datetime, timedelta, timezone
import hashlib
from itertools import product
import json
from math import hypot
from multiprocessing import get_context
from pathlib import Path
import platform
import sys
from time import perf_counter, sleep

import numpy as np
import pulp

from geometry import path_length
from layout_rules import COST, INITIAL_CASH, REVIEW, validate_layout
from simulate_a2 import configure_wave, simulate_campaign, upgrade_cost


BASE = "60d2f09bc2ddce03885cb7318ec8b3dd9a84c4f0"
BASE_PLAN = Path("results/a2-planning/best-plan.json")
BASE_RESULT = Path("results/a2-planning/result.json")
SOURCE = Path("results/t2.1/candidates.npz")
OUT = Path("results/a2-wave4")
STEPS = (0.05, 0.01)
SEED = 42
CASH = 850
EMPTY = ((), ())  # 按候选点编号排序的建塔操作，按塔号排序的升级操作。


def evaluate(prefix, actions):
    """每次只调用已有完整四波仿真，两档均从空塔、2000 元开局。"""
    start = perf_counter()
    plan = [*prefix, actions]
    results = [simulate_campaign(plan, dt=dt) for dt in STEPS]
    return results, perf_counter() - start


def fingerprint(result):
    """返回决策结果的逐波资金和逐敌结局，不用浮点时刻判定结局是否一致。"""
    ledger_keys = ("期初资金元", "支出元", "建后余额元", "赏金元", "期末资金元", "漏怪数")
    ledger, outcomes, cash = [], [], INITIAL_CASH
    for wave in result["逐波"]:
        before, spent, after, bounty, after_bounty, leaks = (wave[key] for key in ledger_keys)
        if before != cash or before - spent != after or after + bounty != after_bounty or after < 0:
            raise ValueError("仿真资金流水未对平")
        cash = after_bounty
        ledger.append((before, spent, after, bounty, after_bounty, leaks))
        enemies = [(enemy["编号"], enemy["结果"]) for enemy in wave["逐敌"]]
        if sum(status == "漏怪" for _, status in enemies) != leaks:
            raise ValueError("逐敌与逐波漏怪总数不符")
        outcomes.extend(enemies)
    if (len(ledger) != 4 or [i for i, _ in outcomes] != list(range(1, 26))
            or any(status not in ("击杀", "漏怪") for _, status in outcomes)
            or result["总漏怪"] != sum(w[-1] for w in ledger) or cash != result["最终资金元"]):
        raise ValueError("四波日志缺失或总体目标与逐波日志不一致")
    return ledger, outcomes, cash


def score(result):
    """按漏怪最少、最终现金最多排列。"""
    return result["总漏怪"], -result["最终资金元"]


class Options:
    """将全精度候选点、现有塔号及预算模式转换成波 4 操作。"""

    def __init__(self, source, towers):
        with np.load(source, allow_pickle=False) as data:
            self.ids = data["ids"].astype(int)
            self.xy = data["xy_m"]
            self.kinds = data["tower_types"].tolist()
            coverage = data["coverage_m"]
            intervals, offsets = data["intervals_m"], data["interval_offsets"]
        if len(self.ids) != 1382 or set(self.kinds) != set(COST):
            raise ValueError("波 4 候选点维度或塔型与 T2.1 不一致")
        self.points = {int(i): tuple(point) for i, point in zip(self.ids, self.xy, strict=True)}
        self.pos_index = {point: i for i, point in self.points.items()}
        self.towers = towers
        self.rng = np.random.default_rng(SEED)
        self.upgrade_patterns = []
        upgrades_by_tower = [[None, *[(i, kind) for kind in self.kinds if COST[kind] > COST[old]]]
                             for i, (_, _, old) in enumerate(towers, 1)]
        for choices in product(*upgrades_by_tower):
            upgrades = tuple(choice for choice in choices if choice is not None)
            spent = self.cost(((), upgrades))
            if spent <= CASH:
                self.upgrade_patterns.append((spent, upgrades))

        # 覆盖和距离仅用于生成点位，所有目标值都由 evaluate 返回的仿真产生。
        eligible = np.array([all(hypot(x - a, y - b) >= 20 for a, b, _ in towers) for x, y in self.xy])
        self.positions = [(700, 800), (400, 200), (1200, 900), (1500, 1400), (1800, 1700),
                          (775, 725), (675, 865)]
        self.profiles = {}
        for j, kind in enumerate(self.kinds):
            arc = np.array([(intervals[offsets[p*len(self.kinds)+j], 0]
                             + intervals[offsets[p*len(self.kinds)+j+1]-1, 1]) / 2
                            if offsets[p*len(self.kinds)+j+1] > offsets[p*len(self.kinds)+j] else -1
                            for p in range(len(self.xy))])
            active = np.flatnonzero(eligible & (coverage[:, j] > 0))
            longest = max(coverage[active, j])
            strength = coverage[:, j] / longest
            rank = lambda values, rows=active: tuple(int(self.ids[i]) for i in rows[np.argsort(values[rows], kind="stable")])
            self.profiles[kind] = [rank(-strength)]
            for position in self.positions:
                distance = np.linalg.norm(self.xy - position, axis=1)
                self.profiles[kind].append(rank(distance / 160.0 - 1.15 * strength))
            by_arc = []
            for cut in range(8):
                left, right = cut * path_length()/8, (cut+1) * path_length()/8
                regional = active[(arc[active] >= left) & (arc[active] < right)]
                by_arc.append(rank(-strength, regional))
            self.profiles[kind].extend(by_arc)
        self.profile_count = len(next(iter(self.profiles.values())))

    def cost(self, state):
        """计算这批波 4 操作新增支付的现金。"""
        builds, upgrades = state
        return sum(COST[k] for _, k in builds) + sum(upgrade_cost(self.towers[i-1][2], k) for i, k in upgrades)

    def actions(self, state):
        """按确定顺序生成正式账本操作，保留候选点完整浮点坐标。"""
        builds, upgrades = state
        return ([{"动作": "升", "塔号": i, "塔型": kind} for i, kind in upgrades]
                + [{"动作": "建", "x": float(self.points[p][0]), "y": float(self.points[p][1]), "塔型": kind}
                   for p, kind in builds])

    def fill(self, kinds, upgrades, profile, sample=0, existing=()):
        """给定购买的塔型序列，在指定路段或布局邻域生成一组点位。"""
        builds = list(existing)
        for offset, kind in enumerate(kinds):
            preferences = self.profiles[kind]
            index = (profile + offset) % len(preferences) if profile >= 8 else profile
            look = []
            for p in (*preferences[index][:36], *preferences[0][:36]):
                x, y = self.points[p]
                if p not in look and all(hypot(x-self.points[q][0], y-self.points[q][1]) >= 20 for q, _ in builds):
                    look.append(p)
                if len(look) >= max(1, sample):
                    break
            if not look:
                return None
            builds.append((int(self.rng.choice(look)) if sample else look[0], kind))
        return tuple(sorted(builds)), upgrades

    def starters(self, baseline):
        """先试原大塔的补强与仅升级，随后进入广域预算模式。"""
        yield EMPTY
        double_medium = [u for _, u in self.upgrade_patterns
                         if (len(u) >= 2 and sum(kind == "大塔" for _, kind in u) >= 2)]
        for upgrades in double_medium:
            yield (), upgrades
        # 原大塔成本 600 元。补 1 中、1 或 2 小，或为已有小塔升中并可补 1 小。
        existing, _ = baseline
        one_small_upgrade = next(u for _, u in self.upgrade_patterns if len(u) == 1 and u[0][1] == "中塔")
        for profile in (1, 6, 7, 0, 2, 3, 4, 5, 8, 10, 14):
            for kinds in (("中塔",), ("小塔", "小塔"), ("小塔",)):
                yield self.fill(kinds, (), profile, existing=existing)
            if profile in (1, 6, 7, 0, 10):
                yield self.fill(("小塔",), one_small_upgrade, profile, existing=existing)
        yield existing, one_small_upgrade
        for _, upgrades in sorted(self.upgrade_patterns, key=lambda x: (-x[0], x[1])):
            if upgrades:
                yield (), upgrades

    def patterns(self):
        """按每个可支付的新建塔数与原塔升级组合，分轮安排点位。"""
        patterns = []
        for upgrade_cost_yuan, upgrades in self.upgrade_patterns:
            caps = [range((CASH-upgrade_cost_yuan)//COST[k] + 1) for k in self.kinds]
            for counts in product(*caps):
                kinds = tuple(k for k, n in reversed(list(zip(self.kinds, counts, strict=True))) for _ in range(n))
                paid = upgrade_cost_yuan + sum(COST[k] for k in kinds)
                if kinds and paid <= CASH:
                    patterns.append((paid, kinds, upgrades))
        # 先比较用足预算的各种组合。轮换点位特征，首轮也能覆盖不同空间位置。
        order = (1, 6, 7, 0, 2, 3, 4, 5) + tuple(range(8, self.profile_count))
        patterns.sort(key=lambda row: (-row[0], len(row[1]), row[2], row[1]))
        for round_number in range(4):
            for i, (_, kinds, upgrades) in enumerate(patterns):
                profile = order[(i + round_number * 3) % len(order)]
                yield self.fill(kinds, upgrades, profile, sample=0 if round_number == 0 else 16)

    def neighbors(self, state):
        """从实测前列方案产生增、删、换型、移位和升级邻域。"""
        builds, upgrades = state
        for profile in (1, 7, 0, 6):
            for kind in self.kinds:
                if self.cost(state) + COST[kind] <= CASH:
                    yield self.fill((kind,), upgrades, profile, sample=5, existing=builds)
        for i, (p, kind) in enumerate(builds):
            others = builds[:i] + builds[i+1:]
            yield others, upgrades
            for new in self.kinds:
                if kind != new:
                    yield tuple(sorted((*others, (p, new)))), upgrades
            x, y = self.points[p]
            # 优先选择最近不同点，也允许跨到全路覆盖或对侧候选。
            close = sorted(self.profiles[kind][0], key=lambda q: hypot(x-self.points[q][0], y-self.points[q][1]))[:5]
            for q in (*close, *self.profiles[kind][7][:2]):
                if q != p:
                    yield tuple(sorted((*others, (q, kind)))), upgrades
        upgrade_sets = (u for _, u in self.upgrade_patterns if len(set(u) ^ set(upgrades)) <= 2)
        for u in upgrade_sets:
            if u != upgrades:
                yield builds, u


def dispatch(pool, prefix, tasks, deadline):
    """并行等待一批方案，超出统一截止点的双档结果不进入排名。"""
    jobs = [(state, origin, pool.apply_async(evaluate, (prefix, actions))) for state, origin, actions in tasks]
    complete = []
    while jobs and perf_counter() < deadline:
        pending = []
        for state, origin, job in jobs:
            if perf_counter() >= deadline:
                pending.append((state, origin, job))
                continue
            if job.ready():
                complete.append((state, origin, job.get()))
            else:
                pending.append((state, origin, job))
        jobs = pending
        if jobs:
            sleep(min(0.10, max(0, deadline - perf_counter())))
    return sorted(complete, key=lambda item: item[0]), len(jobs)


def record(result, path):
    """写出 UTF-8 JSON，原子替换以保留可读的最佳结果。"""
    pending = path.with_suffix(".pending")
    pending.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def export_table(runs):
    """提供实际使用的逐波决策账和逐笔全精度塔位。"""
    waves = runs[0]["逐波"]
    columns = ("波次", "开始仿真秒", "期初资金元", "支出元", "建后余额元", "赏金元", "期末资金元", "漏怪数")
    with (OUT / "wave-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, columns + ("建塔", "升级"), lineterminator="\n")
        writer.writeheader()
        for wave in waves:
            counted = Counter(action["塔型"] for action in wave["操作"] if action["动作"] == "建")
            writer.writerow({**{key: wave[key] for key in columns},
                             "建塔": "、".join(f"{name}×{n}" for name, n in counted.items()),
                             "升级": "、".join(f"{a['塔号']}号 {a['原塔型']}→{a['塔型']}" for a in wave["操作"] if a["动作"] == "升")})
    with (OUT / "actions.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["波次", "开始仿真秒", "动作", "塔号", "x米", "y米", "原塔型", "塔型", "支出元", "操作后余额元"])
        for wave in waves:
            for a in wave["操作"]:
                writer.writerow([wave["波次"], wave["开始仿真秒"], a["动作"], a["塔号"], *a["坐标"], a["原塔型"],
                                 a["塔型"], a["支出元"], a["操作后余额元"]])


def main():
    """复现基线、限时搜索、写入双步长结果与交接。"""
    started = perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=1680, help="计算上限，至多 28 分钟")
    parser.add_argument("--workers", type=int, default=8, help="本机并行进程数")
    args = parser.parse_args()
    if not 45 <= args.seconds <= 1680 or not 1 <= args.workers <= 8 or pulp.__version__ != "2.8.0":
        parser.error("计算上限 45 至 1680 秒，并行数 1 至 8，PuLP 锁定 2.8.0")
    deadline = started + args.seconds
    OUT.mkdir(parents=True, exist_ok=True)
    base_plan = json.loads(BASE_PLAN.read_text(encoding="utf-8"))
    archived = json.loads(BASE_RESULT.read_text(encoding="utf-8"))["版本"]["局部改进"]
    if base_plan != archived["计划"]:
        raise ValueError("未取得原 PR #15 的精确建造计划")
    prefix = base_plan[:3]
    result, best, stop = None, None, "搜索队列已遍历"
    counts = Counter()
    seen = set()
    pool = get_context("spawn").Pool(args.workers)
    try:
        histories, pending = dispatch(pool, prefix, [(EMPTY, "原方案", base_plan[3])], deadline)
        if pending:
            raise TimeoutError("原方案双步长复跑未在限时内完成")
        _, _, (baseline, duration) = histories[0]
        expected = [archived["正式结果"], archived["缩步复核"]["实测"]]
        if (any(fingerprint(new) != fingerprint(old) for new, old in zip(baseline, expected, strict=True))
                or fingerprint(baseline[0]) != fingerprint(baseline[1])
                or [w["漏怪数"] for w in baseline[0]["逐波"]] != [0, 2, 2, 7]
                or score(baseline[0]) != (11, -1150)):
            record({"错误": "基线未复现", "实测": baseline, "原回执": expected}, OUT / "baseline-failure.json")
            raise ValueError("基线未复现，详情见 baseline-failure.json")
        towers = baseline[0]["逐波"][2]["塔布局"]
        if (baseline[1]["逐波"][2]["塔布局"] != towers or validate_layout(towers)[1] != {"大塔": 2, "中塔": 4, "小塔": 1}
                or any(run["逐波"][3]["期初资金元"] != CASH for run in baseline)):
            raise ValueError("波 4 起点与已确认的布局或资金不符")
        space = Options(SOURCE, towers)
        base_state = (tuple(sorted((space.pos_index[(a["x"], a["y"])], a["塔型"]) for a in base_plan[3])), ())
        seen.add(base_state)
        best = (base_state, base_plan, baseline)
        record({"计划": base_plan, "两档": baseline}, OUT / "incumbent.json")
        print(f"基线两档复现：总漏 11、剩 1150 元，完整评估 {duration:.1f}s。", flush=True)
        leaders, expanded = [], set()
        first = (state for state in space.starters(base_state) if state is not None)
        global_queue = (state for state in space.patterns() if state is not None)
        local_queue = deque()
        exhausted = False
        def next_plan():
            """优先补强原方案，之后交替从全局模式与局部邻域提议。"""
            item = next(first, None)
            if item is not None:
                return item, "先验组合"
            nonlocal exhausted
            if local_queue and (exhausted or len(seen) % 3 == 0):
                return local_queue.popleft(), "前列邻域"
            item = next(global_queue, None)
            if item is not None:
                return item, "预算模式"
            exhausted = True
            return (local_queue.popleft(), "前列邻域") if local_queue else (None, "结束")

        with (OUT / "evaluations.jsonl").open("w", encoding="utf-8", newline="\n") as evidence:
            while perf_counter() < deadline:
                batch = []
                while len(batch) < args.workers * 2 and perf_counter() < deadline:
                    state, origin = next_plan()
                    if state is None:
                        break
                    if state in seen:
                        counts["重复剔除"] += 1
                        continue
                    seen.add(state)
                    actions = space.actions(state)
                    try:
                        layout, remaining, _ = configure_wave(towers, CASH, actions)
                        validate_layout(layout)
                    except ValueError:
                        counts["不合法或超预算"] += 1
                        continue
                    if remaining < 0 or space.cost(state) != CASH - remaining:
                        raise ValueError("波 4 支出复算不一致")
                    batch.append((state, origin, actions))
                if not batch:
                    break
                histories, pending = dispatch(pool, prefix, batch, deadline)
                counts["到时未完成双档"] += pending
                for state, origin, (runs, elapsed) in histories:
                    stamps = [fingerprint(run) for run in runs]
                    if any(run["逐波"][:3] != reference["逐波"][:3]
                           for run, reference in zip(runs, baseline, strict=True)):
                        raise ValueError("前三波完整流水与原方案不一致")
                    agreed = stamps[0] == stamps[1]
                    counts["完成双档"] += 1
                    counts["一致并入排名" if agreed else "双档不一致"] += 1
                    counts[f"来源:{origin}"] += 1
                    evidence.write(json.dumps({"组合": state, "来源": origin, "双档一致": agreed,
                                               "两档目标": [score(r) for r in runs],
                                               "两档波4结局": [stamp[1][15:] for stamp in stamps],
                                               "评估耗时秒": elapsed}, ensure_ascii=False) + "\n")
                    evidence.flush()
                    if not agreed:
                        continue
                    leaders.append((score(runs[0]), state))
                    if score(runs[0]) < score(best[2][0]):
                        best = (state, [*prefix, space.actions(state)], runs)
                        record({"计划": best[1], "两档": runs}, OUT / "incumbent.json")
                        print(f"新最好：总漏 {runs[0]['总漏怪']}、剩 {runs[0]['最终资金元']} 元。", flush=True)
                leaders = sorted(leaders)[:8]
                for _, state in leaders[:2]:
                    if state not in expanded:
                        local_queue.extend(candidate for candidate in space.neighbors(state) if candidate is not None)
                        expanded.add(state)
                # 若两个最优已展开，逐个扩展其他当前前列布局。
                if not local_queue:
                    for _, state in leaders[2:]:
                        if state not in expanded:
                            local_queue.extend(candidate for candidate in space.neighbors(state) if candidate is not None)
                            expanded.add(state)
                print(f"{perf_counter()-started:.0f}s，完成 {counts['完成双档']} 组，"
                      f"一致 {counts['一致并入排名']} 组，最好 {score(best[2][0])}。", flush=True)
                if pending:
                    stop = "达到计算截止点"
                    break
        if perf_counter() >= deadline:
            stop = "达到计算截止点"
        _, plan, selected = best
        improved = score(selected[0]) < score(baseline[0])
        result = {"任务": "A2 波4独立搜索", "基线PR": 15, "基线提交": BASE,
                  "候选SHA256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "种子": SEED, "两档步长秒": STEPS,
                  "上限秒": args.seconds, "并行数": args.workers, "终止原因": stop, "实测计数": dict(counts),
                  "结论": "波4方案严格改善" if improved else "无改进、维持 PR #15 方案",
                  "字典序目标": "先总漏怪最少，再最终剩余资金最多",
                  "搜索范围": "T2.1 候选点，先原方案增补和已有塔升级，再按可支付组合与前列布局邻域提议。",
                  "波4期初元": CASH, "原目标": score(baseline[0]), "最终目标": score(selected[0]),
                  "选择的四波计划": plan, "正式双档": selected, "原方案双档": baseline,
                  "双档逐敌结局和资金一致": True, "前三波逐步长与原方案一致": True,
                  "环境": {"Python": platform.python_version(), "解释器": sys.executable,
                            "NumPy": np.__version__, "PuLP": pulp.__version__}, "状态": REVIEW}
    finally:
        # 截止后只终止本次 Pool 的子进程，不等待尚未完成的第二档评估。
        pool.terminate()
        pool.join()
    if result is not None:
        result["日期"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        result["运行时间秒"] = perf_counter() - started
        record(result, OUT / "result.json")
        record(result["选择的四波计划"], OUT / "best-plan.json")
        export_table(result["正式双档"])
        summary = {k: v for k, v in result.items() if k not in ("正式双档", "原方案双档")}
        chosen = result["正式双档"][0]
        summary["逐波漏怪"] = [w["漏怪数"] for w in chosen["逐波"]]
        summary["最终资金元"] = chosen["最终资金元"]
        summary["总漏怪"] = chosen["总漏怪"]
        summary["波4操作明细"] = chosen["逐波"][3]["操作"]
        summary["文件"] = [f"results/a2-wave4/{name}" for name in ("result.json", "best-plan.json", "wave-summary.csv", "actions.csv", "evaluations.jsonl")]
        record(summary, Path("handoffs/A2-wave4.json"))
        print(json.dumps({k: summary[k] for k in ("结论", "逐波漏怪", "最终资金元", "运行时间秒")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
