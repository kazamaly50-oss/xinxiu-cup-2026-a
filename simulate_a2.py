"""问题二按波结算的仿真模式，战斗沿用问题一的固定步长模拟器。"""

import argparse
import json
from pathlib import Path
from time import perf_counter

from layout_rules import COST, INITIAL_CASH, REVIEW, validate_layout
from simulate import simulate


WAVES = tuple({"数量": n, "血量": hp, "速度": speed, "出发间隔": gap, "赏金": bounty}
              for n, hp, speed, gap, bounty in ((5, 1500, 20, 10, 50), (5, 1800, 15, 8, 100),
                                                (5, 2000, 12, 6, 200), (10, 2500, 10, 5, 300)))


def upgrade_cost(old, new):
    """返回 old 升到 new 的补差，禁止降级或同级重复付费。"""
    if old not in COST or new not in COST or COST[new] <= COST[old]:
        raise ValueError(f"非法升级 {old} → {new}")
    return COST[new] - COST[old]


def configure_wave(towers, cash, actions):
    """在波前按顺序建塔或升级，返回新塔表、余额和逐操作流水。

    建塔操作为 {动作: 建, x: 米, y: 米, 塔型: 类型}；升级为
    {动作: 升, 塔号: 自 1 起的稳定编号, 塔型: 升级后类型}。
    入参塔表保持不变。任何一步非法时拒绝整组方案。
    """
    draft = [list(tower) for tower in towers]
    ledger = []
    for action in actions:
        kind = action["塔型"]
        if kind not in COST:
            raise ValueError(f"未知塔型 {kind}")
        if action["动作"] == "建":
            x, y = action["x"], action["y"]
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (x, y)):
                raise ValueError("塔位坐标须为实数")
            draft.append([x, y, kind])
            index = len(draft)
            cost = COST[kind]
            old = None
        elif action["动作"] == "升":
            index = action["塔号"]
            if type(index) is not int or not 1 <= index <= len(draft):
                raise ValueError("升级目标必须是已建塔的编号")
            x, y, old = draft[index - 1]
            cost = upgrade_cost(old, kind)
            draft[index - 1][2] = kind
        else:
            raise ValueError("只允许建塔和升级")
        if cash < cost:
            raise ValueError(f"可用 {cash} 元，小于本次支出 {cost}")
        validate_layout(draft)
        cash -= cost
        ledger.append({"动作": action["动作"], "塔号": index, "坐标": [x, y], "原塔型": old,
                       "塔型": kind, "支出元": cost, "操作后余额元": cash})
    return draft, cash, ledger


def settle_wave(balance, result, wave):
    """按正式战斗日志计击杀赏金，返回奖励与波末余额。"""
    enemies = result["每只敌人结果"]
    if len(enemies) != wave["数量"] or sum(enemy["结果"] == "漏怪" for enemy in enemies) != result["漏怪数"]:
        raise ValueError("仿真逐敌结果与漏怪总数不一致")
    earned = sum(enemy["结果"] == "击杀" for enemy in enemies) * wave["赏金"]
    return earned, balance + earned


def simulate_campaign(plan, dt=0.05):
    """运行 4 个完整波次，上一波结算后再开放下一波决策。

    每波第一只敌人在账本记载的波起点出生。下一波在上波最后
    一只敌人结局后加上一波出兵间隔开始。赏金只结入一次。
    """
    if len(plan) != len(WAVES):
        raise ValueError("计划须包含四波操作，每波可以为空")
    towers, cash, wave_start, offset = [], INITIAL_CASH, 0.0, 0
    waves = []
    for index, (wave, actions) in enumerate(zip(WAVES, plan, strict=True), 1):
        before = cash
        towers, after_build, operations = configure_wave(towers, cash, actions)
        fight = simulate(towers, wave, dt=dt)
        bounty, cash = settle_wave(after_build, fight, wave)
        enemies = []
        for row in fight["每只敌人结果"]:
            absolute = {key: value + wave_start if value is not None else None for key, value in row.items()
                        if key in ("出发时刻", "死亡时刻", "漏怪时刻")}
            enemies.append({**row, **absolute, "波内编号": row["编号"], "编号": row["编号"] + offset})
        wave_end = wave_start + fight["总耗时"]
        waves.append({"波次": index, "开始仿真秒": wave_start, "结算仿真秒": wave_end,
                      "期初资金元": before, "操作": operations, "支出元": before - after_build,
                      "建后余额元": after_build, "赏金元": bounty, "期末资金元": cash,
                      "漏怪数": fight["漏怪数"], "塔布局": towers, "逐敌": enemies})
        wave_start = wave_end + wave["出发间隔"]
        offset += wave["数量"]
    total_cost = sum(wave["支出元"] for wave in waves)
    total_bounty = sum(wave["赏金元"] for wave in waves)
    assert cash == INITIAL_CASH - total_cost + total_bounty
    return {"dt秒": dt, "逐波": waves, "总漏怪": sum(wave["漏怪数"] for wave in waves),
            "总支出元": total_cost, "总赏金元": total_bounty, "最终资金元": cash}


def self_checks():
    """执行空方案、第一波赏金、升级差价及满额赏金对账。"""
    import numpy as np

    start = perf_counter()
    empty = simulate_campaign([[], [], [], []], dt=0.05)
    assert empty["总漏怪"] == 25 and empty["最终资金元"] == INITIAL_CASH
    assert [wave["漏怪数"] for wave in empty["逐波"]] == [5, 5, 5, 10]
    assert [row["编号"] for wave in empty["逐波"] for row in wave["逐敌"]] == list(range(1, 26))
    # 用 T2.1 已核验的八个合法点实打第一波，确保 250 元确实来自战斗日志。
    first_ids = [10, 22, 5, 9, 34, 33, 36, 51]
    with np.load("results/t2.1/candidates.npz", allow_pickle=False) as data:
        point_by_id = dict(zip(data["ids"].tolist(), data["xy_m"].tolist(), strict=True))
    actions = [{"动作": "建", "x": x, "y": y, "塔型": "中塔"}
               for x, y in (point_by_id[index] for index in first_ids)]
    tested = simulate_campaign([actions, [], [], []], dt=0.05)
    first = tested["逐波"][0]
    assert first["漏怪数"] == 0 and first["期末资金元"] - first["建后余额元"] == 250
    assert tested["逐波"][1]["期初资金元"] == first["期末资金元"]
    upgrades = [("小塔", "中塔", 150), ("中塔", "大塔", 350), ("小塔", "大塔", 500)]
    for old, new, expected in upgrades:
        towers = [[100, 300, old]]
        upgraded, cash, ledger = configure_wave(towers, 600, [{"动作": "升", "塔号": 1, "塔型": new}])
        assert upgraded == [[100, 300, new]] and towers == [[100, 300, old]]
        assert ledger[0]["支出元"] == expected and cash == 600 - expected
    all_rewards = []
    balance = INITIAL_CASH
    for wave in WAVES:
        # 满额资金测试的逐敌输入来自全杀账本夹具，检验波间累计而非战斗可达性。
        all_killed = {"漏怪数": 0, "每只敌人结果": [{"结果": "击杀"}] * wave["数量"]}
        earned, after = settle_wave(balance, all_killed, wave)
        assert after - balance == earned
        balance = after
        all_rewards.append(earned)
    assert all_rewards == [250, 500, 1000, 3000] and balance - INITIAL_CASH == 4750
    return {"无操作逐波漏怪": [5, 5, 5, 10], "无操作最终资金元": empty["最终资金元"],
            "第一波全杀实测": first, "第一波全杀实测增资元": first["赏金元"],
            "全杀总赏金账本对账元": balance - INITIAL_CASH,
            "升级差价逐项通过": upgrades, "运行时间秒": perf_counter() - start}


def main():
    """复跑四波计划，或独立运行问题二模式的基础自检。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    start = perf_counter()
    if args.plan is None:
        report = {"任务": "A2 仿真", "自检": self_checks(), "状态": REVIEW}
    else:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        report = simulate_campaign(plan, args.dt)
    report["运行时间秒"] = perf_counter() - start
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
