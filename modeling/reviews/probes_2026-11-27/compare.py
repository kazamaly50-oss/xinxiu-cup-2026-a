"""把 Hermes 本机复跑输出与仓库里 Codex 的记录逐项比较。"""
import json, os
A = r"D:\Hermes\cache\scratch\rev27\align"; O = r"D:\Hermes\cache\scratch\rev27\out"
J = lambda p: json.load(open(p, encoding="utf-8-sig"))
T = lambda p: open(p, encoding="utf-8").read()
av = J(os.path.join(A, "results/alignment-validation.json"))
# --- a1_bounds
mine = json.loads(T(os.path.join(O, "a1_bounds.stdout.txt")))
theirs = json.loads(av["执行"]["A1上界"]["标准输出"])
print("a1_bounds JSON == Codex记录:", mine == theirs)
for k in ["预算内数量组合数", "上界最大组合", "总伤害上界HP", "全杀需要伤害HP", "击杀数上界", "漏怪数下界", "达到击杀数上界的花费下界元"]:
    print("  ", k, mine[k])
for k, v in mine["单塔证明"].items(): print("  ", k, v)
# --- candidate
mine = json.loads(T(os.path.join(O, "a1_candidate.stdout.txt")))
theirs = json.loads(av["执行"]["1850元候选"]["标准输出"])
print("candidate JSON == Codex对齐复跑stdout:", mine == theirs)
al = J(os.path.join(A, "results/a1-verification-aligned.json")); hist = J(os.path.join(A, "results/a1-verification.json"))
print("aligned.json 顶层键:", list(al)); print("历史.json 顶层键:", list(hist))
print("合法性:", json.dumps(mine["合法性"], ensure_ascii=False)); print("状态:", mine["状态"])
runs = {r["步长秒"]: r for r in mine["复跑"]}
print("比较:", json.dumps(mine["比较"], ensure_ascii=False))
print("编号 | dt.05 结果 剩余 死亡/漏怪时刻 | dt.01 结果 剩余 | 血量差")
for a, b in zip(runs[0.05]["逐敌结果"], runs[0.01]["逐敌结果"]):
    ta = a["死亡时刻"] if a["结果"] == "击杀" else a["漏怪时刻"]
    print(f'{a["编号"]:>2} | {a["结果"]} {a["剩余血量"]:.4f} t={ta:.4f} 承伤={a["累计承伤"]:.3f} | {b["结果"]} {b["剩余血量"]:.4f} | {abs(a["剩余血量"]-b["剩余血量"]):.4f}')
def find_runs(o):
    if isinstance(o, dict):
        if "复跑" in o and "合法性" in o: yield o
        for v in o.values(): yield from find_runs(v)
    elif isinstance(o, list):
        for v in o: yield from find_runs(v)
for name, doc in [("aligned", al), ("历史", hist)]:
    for rep in find_runs(doc):
        same = [ [ (e["编号"], e["结果"], e["剩余血量"]) for e in r["逐敌结果"] ] for r in rep["复跑"] ] == [ [ (e["编号"], e["结果"], e["剩余血量"]) for e in r["逐敌结果"] ] for r in mine["复跑"] ]
        print(f"{name}: 找到复跑报告，口径={rep['合法性'].get('口径')}, 逐敌(编号,结果,剩余血量)与本机复跑完全一致:", same)
m2 = json.loads(T(os.path.join(O, "a1_candidate_center_edge.stdout.txt")))
print("center_in_map+edge: 合法", m2["合法性"]["通过"], "| 逐敌与默认口径一致:", m2["复跑"] == mine["复跑"])
# --- M1
mine = J(os.path.join(O, "T1.2-hermes.json")); theirs = J(os.path.join(A, "results/T1.2-aligned.json")); old = J(os.path.join(A, "results/T1.2.json"))
def strip(d):
    d = json.loads(json.dumps(d))
    for k in ["日期", "环境", "验证内部耗时秒", "运行前SHA256", "运行后SHA256"]: d.pop(k, None)
    return d
print("M1 报告(去掉日期/环境/耗时/哈希) == Codex aligned:", strip(mine) == strip(theirs))
print("M1 校验明细 == 历史 T1.2.json:", mine["校验"] == old["校验"])
print("M1 基线一致:", mine["基线一致"], "源码未变:", mine["源码未变"], "全部通过:", mine["全部通过"], "失败项:", mine["失败项"])
c = mine["校验"]
a = c["解析对拍"]; print("解析对拍:", {k: a[k] for k in ["理论伤害", "仿真伤害", "相对误差百分数", "场景有效", "通过"]}, a["场景"]["输出"]["每只敌人结果"][0]["结果"], a["场景"]["输出"]["每只敌人结果"][0]["剩余血量"])
s = c["步长收敛"]; print("步长收敛: 漏怪", s["dt=0.1"]["输出"]["漏怪数"], s["dt=0.05"]["输出"]["漏怪数"], "状态不同:", s["状态不同的敌人编号"], "最大终局血量绝对差:", s["最大终局血量绝对差"], "布局:", s["dt=0.1"]["输入"]["towers"])
for r in s["逐敌差异"]: print("   ", r["编号"], r["粗步长结果"], r["细步长结果"], round(r["粗步长剩余血量"], 3), round(r["细步长剩余血量"], 3), "Δ", round(r["终局剩余血量差"], 3))
n = c["极端无塔"]; print("无塔: 漏怪", n["场景"]["输出"]["漏怪数"], "漏怪时刻", [round(e["漏怪时刻"], 4) for e in n["场景"]["输出"]["每只敌人结果"]], "承伤", {e["累计承伤"] for e in n["场景"]["输出"]["每只敌人结果"]})
f = c["极端全覆盖"]; print("全覆盖:", {k: f[k] for k in ["塔数", "总造价元", "用途", "纳入问题一结果汇总", "全程覆盖", "覆盖区间并集米", "通过", "最小提前出口秒", "布局限定"]}, "漏怪", f["场景"]["输出"]["漏怪数"])
print("   死亡时刻", [round(e["死亡时刻"], 3) for e in f["场景"]["输出"]["每只敌人结果"]])
