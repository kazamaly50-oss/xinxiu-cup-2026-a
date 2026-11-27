"""T1.2：独立执行 M1 三件套，不修改仿真器、塔属性或队内规则。

执行流程：核对 PR #4 基线 -> 固定场景执行五次仿真 -> 独立判定 ->
保存逐敌结果与差异 -> 返回退出码。某项失败仍保留其余项目的结果。
本文件中的解析潜在伤害只作对拍或参考，不替代战斗仿真的漏怪结果。
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np

import geometry
from coverage import cover_intervals, exposure
from simulate import simulate


ROOT = Path(__file__).resolve().parent
BASE_COMMIT = "09577be19375b24a3f0d80905f042e8392386d44"
# 按 LF 换行归一化后比较，兼容 Windows Git 的 CRLF 工作副本。
# 这些是被验证源码的版本锁，不是把预检结果硬编码成验收答案。
BASELINE_LF = {
    "geometry.py": "c2d40cff460e3a725381133a79ed9102deae603dbf55a18f2392268301df71da",
    "coverage.py": "20206fdeed7b4c1f5e06d19008e59b5e3cc7174de14d2c39e0a1d99a79c2a79e",
    "simulate.py": "2b0e80ace3a9ff4210c5e86770c075925415c55e5e588e26e181a2207622d551",
    # 已先验证归档与原文件逐字节相同；哈希值不变，只迁移路径。
    "docs/sim_rules_T1.1.md": "5ec746d55ef771233f65f16593c4be9819ea2b7d47200370d7c42a9227caea25",
}
A1_WAVE = {"数量": 10, "血量": 1700, "速度": 20, "出发间隔": 10}
COVERAGE_TOL_M = 1e-8  # 沿用 coverage.py 的区间合并容差，单位米。


def _hashes():
    """无参数；返回基线文件与验证脚本的原始、LF 归一化 SHA-256。"""
    result = {}
    # 统一规则独立留痕；不得拿新规则替换原T1.1实现说明的版本锁。
    for name in [*BASELINE_LF, "modeling/rules.md", "validate_t12.py"]:
        raw = (ROOT / name).read_bytes()
        result[name] = {
            "原始字节": hashlib.sha256(raw).hexdigest(),
            "LF归一化": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
        }
    return result


def _scene(towers, wave, dt):
    """运行给定塔列表、波参数及秒步长；返回输入、逐敌结果或异常记录。

    不截断/修正任何仿真数值。结果完整性仅检查编号、状态与计数对应关系；
    累计承伤曲线不重复保存，最终逐敌伤害和事件时刻全部保留。
    """
    record = {"输入": {"towers": towers, "wave": wave, "dt": dt}}
    try:
        raw = simulate(towers, wave, dt)
        output = {key: raw[key] for key in ["漏怪数", "每只敌人结果", "总耗时"]}
        record["输出"] = output
        enemies = output["每只敌人结果"]
        checks = [
            [enemy["编号"] for enemy in enemies] == list(range(1, wave["数量"] + 1)),
            all(enemy["结果"] in ("击杀", "漏怪") for enemy in enemies),
            output["漏怪数"] == sum(enemy["结果"] == "漏怪" for enemy in enemies),
        ]
        record["运行成功"] = all(checks)
        if not record["运行成功"]:
            record["初步定位"] = "逐敌编号、状态或漏怪计数不一致，需队长复核输出契约。"
    except Exception as exc:
        # 单场景异常不阻止另一种步长或其他场景运行；失败必须进入交接报告。
        record.update({"运行成功": False, "异常类型": type(exc).__name__,
                       "异常信息": str(exc), "异常堆栈": traceback.format_exc(),
                       "初步定位": "现有接口执行或输出读取异常；未修改被验证模块。"})
    return record


def _analytic():
    """返回单塔单敌的解析对拍；伤害单位为血量，误差以比例与百分数记录。"""
    wave = {"数量": 1, "血量": 10000, "速度": 20, "出发间隔": 0}
    scene = _scene([(190, 120, "中塔")], wave, 0.05)
    theory = exposure(190, 120, 125, 20) * 20
    record = {"判据": "完整存活穿越覆盖区，理论伤害>0，相对误差严格<1%",
              "场景": scene, "理论伤害": theory, "通过": False}
    if scene["运行成功"]:
        enemy = scene["输出"]["每只敌人结果"][0]
        actual = enemy["累计承伤"]
        # 提前死亡会使累计承伤被初血截断，不能拿截断量与完整暴露伤害对拍。
        valid = bool(np.isfinite(theory) and 0 < theory < wave["血量"]
                     and enemy["结果"] == "漏怪" and enemy["剩余血量"] > 0
                     and np.isfinite(actual))
        error = abs(actual - theory) / theory if valid else None
        record.update({"场景有效": valid, "仿真伤害": actual, "相对误差": error,
                       "相对误差百分数": None if error is None else error * 100,
                       "通过": bool(valid and error < 0.01)})
    if not record["通过"]:
        record["初步定位"] = "先核对是否完整穿越且未死亡，再核对暴露区间与步首射程采样；未放宽1%门槛。"
    return record


def _convergence_towers():
    """无参数；返回预先固定的三座大塔，沿道路左法向偏移20米。"""
    towers = []
    for s in [400.0, 1400.0, 2400.0]:
        # 累计弧长定位所在直线段，单位切向量旋转90度即左单位法向量。
        index = int(np.searchsorted(geometry._CUMULATIVE, s, side="right") - 1)
        tangent = geometry._SEGMENTS[index] / geometry._LENGTHS[index]
        point = np.asarray(geometry.pos(s)) + 20 * np.array([-tangent[1], tangent[0]])
        towers.append((float(point[0]), float(point[1]), "大塔"))
    return towers


def _event_time(enemy):
    """返回单个逐敌结果 enemy 的终局游戏时刻（秒）。"""
    return enemy["死亡时刻"] if enemy["结果"] == "击杀" else enemy["漏怪时刻"]


def _convergence():
    """返回固定布局的两步长结果和逐敌差异；差值一律为细步长减粗步长。"""
    towers = _convergence_towers()
    coarse = _scene(towers, dict(A1_WAVE), 0.1)
    fine = _scene(towers, dict(A1_WAVE), 0.05)
    record = {"判据": "同一布局与问题一波参数，两次漏怪数一致",
              "布局构造": "弧长400/1400/2400米处向左法向偏移20米，三座大塔，总价1800",
              "dt=0.1": coarse, "dt=0.05": fine, "通过": False,
              "差值方向": "dt=0.05 减 dt=0.1；血量为终局剩余血量，不是同一中间时刻的血量"}
    if coarse["运行成功"] and fine["运行成功"]:
        differences = []
        for a, b in zip(coarse["输出"]["每只敌人结果"], fine["输出"]["每只敌人结果"]):
            differences.append({
                "编号": a["编号"], "粗步长结果": a["结果"], "细步长结果": b["结果"],
                "状态一致": a["结果"] == b["结果"],
                "粗步长剩余血量": a["剩余血量"], "细步长剩余血量": b["剩余血量"],
                "终局剩余血量差": b["剩余血量"] - a["剩余血量"],
                "累计承伤差": b["累计承伤"] - a["累计承伤"],
                "粗步长终局时刻": _event_time(a), "细步长终局时刻": _event_time(b),
                "终局时刻差秒": _event_time(b) - _event_time(a),
            })
        record.update({"逐敌差异": differences,
                       "状态不同的敌人编号": [row["编号"] for row in differences if not row["状态一致"]],
                       "最大终局血量绝对差": max(abs(row["终局剩余血量差"]) for row in differences),
                       "通过": coarse["输出"]["漏怪数"] == fine["输出"]["漏怪数"]})
    if not record["通过"]:
        record["初步定位"] = "按逐敌差异定位结局改变者，再检查射程进出、最近目标切换及下一步重选时机；未更改布局或规则。"
    return record


def _no_towers():
    """返回空塔列表、问题一波参数的极端验证，要求全部敌人漏怪。"""
    scene = _scene([], dict(A1_WAVE), 0.05)
    passed = scene["运行成功"] and scene["输出"]["漏怪数"] == A1_WAVE["数量"]
    record = {"判据": "无塔时全部10只敌人漏怪", "场景": scene, "通过": passed}
    if not passed:
        record["初步定位"] = "检查无塔时是否误扣血、漏记出兵或未正确登记出口事件；未改仿真器。"
    return record


def _full_coverage():
    """返回正式路径25座大塔的覆盖证据及极端战斗结果，不代表A1合法方案。"""
    length = geometry.path_length()
    towers = [(*geometry.pos(float(s)), "大塔") for s in np.linspace(0, length, 25)]
    # 先求每塔覆盖区间，再取并集，不能把重叠覆盖长度相加冒充全程覆盖。
    intervals = sorted(pair for x, y, _ in towers for pair in cover_intervals(x, y, 200))
    merged = []
    for low, high in intervals:
        if merged and low <= merged[-1][1] + COVERAGE_TOL_M:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    covers_all = (len(merged) == 1 and abs(merged[0][0]) <= COVERAGE_TOL_M
                  and abs(merged[0][1] - length) <= COVERAGE_TOL_M)
    potential = sum(exposure(x, y, 200, A1_WAVE["速度"]) * 40 for x, y, _ in towers)
    scene = _scene(towers, dict(A1_WAVE), 0.05)
    passed = bool(covers_all and scene["运行成功"] and scene["输出"]["漏怪数"] == 0)
    record = {"判据": "覆盖区间并集包含全路径且实际0漏怪", "场景": scene,
              "塔数": len(towers), "总造价元": len(towers) * 600,
              "用途": "非问题一可行方案", "纳入问题一结果汇总": False,
              "通过": passed, "路径总长米": length, "覆盖区间并集米": merged,
              "全程覆盖": bool(covers_all), "合并容差米": COVERAGE_TOL_M,
              "单敌解析潜在伤害": potential, "潜在伤害与初血之比": potential / A1_WAVE["血量"],
              "潜在伤害解释": "忽略目标竞争和提前死亡的单敌参考上限，不能据此推出零漏怪。",
              "布局限定": "队长已允许的测试输入：25大塔、价格15000、塔心在道路上；超出A1预算/库存/布塔限制，不是可行解。"}
    if scene["运行成功"]:
        # 真实出口时刻减实际死亡时刻，量化余量；漏怪者用 None，禁止伪造击杀。
        margins = [{"编号": enemy["编号"], "提前出口秒":
                    enemy["出发时刻"] + length / A1_WAVE["速度"] - enemy["死亡时刻"]
                    if enemy["结果"] == "击杀" else None}
                   for enemy in scene["输出"]["每只敌人结果"]]
        record["逐敌击杀余量"] = margins
        if passed:
            record["最小提前出口秒"] = min(row["提前出口秒"] for row in margins)
    if not passed:
        record["初步定位"] = "先核对覆盖并集是否存在空隙，再检查漏怪者承伤与集火竞争；不以解析伤害上限替代实测。"
    return record


def run_validation():
    """无参数；执行固定M1场景并返回JSON可序列化报告，不写文件。

    返回包含基线哈希、环境、逐项判据、逐敌明细、失败定位和总通过状态。
    单个项目异常会记录并继续其他项目。内部计时不含解释器启动和导入；
    正式交接的完整进程运行时间由调用方在进程外另测。
    """
    started = time.perf_counter()
    before = _hashes()
    cases = {}
    for name, check in [("解析对拍", _analytic), ("步长收敛", _convergence),
                        ("极端无塔", _no_towers), ("极端全覆盖", _full_coverage)]:
        try:
            cases[name] = check()
        except Exception as exc:
            cases[name] = {"通过": False, "异常类型": type(exc).__name__,
                           "异常信息": str(exc), "异常堆栈": traceback.format_exc(),
                           "初步定位": "验证计算或结果对比异常；保留其他项目，交队长裁定。"}
    after = _hashes()
    baseline_ok = all(before[name]["LF归一化"] == value for name, value in BASELINE_LF.items())
    unchanged = before == after
    failed = [{"项目": name, "初步定位": value["初步定位"]}
              for name, value in cases.items() if not value["通过"]]
    if not baseline_ok or not unchanged:
        failed.append({"项目": "源码版本锁", "初步定位": "文件不匹配PR #4基线或运行期间发生变化；不得据此验收原版本。"})
    return {
        "任务编号": "T1.2", "模块": "validate_t12.py", "基础提交": BASE_COMMIT,
        "日期": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "环境": {"Python解释器": sys.executable, "Python版本": platform.python_version(),
                 "NumPy版本": np.__version__, "系统": platform.platform()},
        "随机种子": 42, "随机性说明": "固定场景，无随机采样，也不按结果搜索或调整布局。",
        "运行前SHA256": before, "运行后SHA256": after,
        "规则归档核验证据": "handoffs/rules-archive-proof.json",
        "当前统一规则": "modeling/rules.md",
        "基线一致": baseline_ok, "源码未变": unchanged,
        "校验": cases, "失败项": failed, "全部通过": not failed,
        "验证内部耗时秒": time.perf_counter() - started,
        "验收状态": "已实际执行，队员复核与队长验收待完成；失败时等待裁定，不自动修规则。",
        "适用范围": "仅固定场景下的M1验证；漏怪数一致不表示轨迹完全相同或全局收敛，也不证明A1零漏怪可达。",
    }


def _summary(report):
    """将 report 压缩为终端摘要，详细逐敌数据仍保存在报告中。"""
    cases = report["校验"]
    summary = {"模块": "validate_t12.py", "全部通过": report["全部通过"],
               "失败项": report["失败项"], "验证内部耗时秒": report["验证内部耗时秒"]}
    for name, case in cases.items():
        summary[name] = "通过" if case["通过"] else "失败，详见报告"
    return summary


def main(argv=None):
    """参数 argv 为可选命令行参数列表；写报告后返回0（通过）或1（失败）。

    --output 默认为脚本所在目录的 results/T1.2.json。参数错误由 argparse
    返回2；无法写报告时同样返回2并说明原因，不把写入失败报告为验证通过。
    """
    parser = argparse.ArgumentParser(description="T1.2 M1三件套：只验证现有simulate规则")
    parser.add_argument("--output", type=Path, default=ROOT / "results/T1.2.json",
                        help="完整JSON报告路径，默认 results/T1.2.json")
    args = parser.parse_args(argv)
    # 防止误把报告输出指向既有源码；结果文件须为JSON且不占用已有模块。
    protected = {ROOT / name for name in BASELINE_LF} | {Path(__file__).resolve()}
    if args.output.resolve() in protected or args.output.suffix.lower() != ".json":
        parser.error("报告必须写入独立的 .json 文件")
    report = run_validation()
    try:
        content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8", newline="\n")
    except (OSError, ValueError) as exc:
        print(f"报告写入失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps({**_summary(report), "报告": str(args.output.resolve())},
                     ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["全部通过"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
