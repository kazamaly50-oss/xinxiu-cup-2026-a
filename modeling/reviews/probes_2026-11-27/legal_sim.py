"""Hermes 独立核对：1850 元候选合法性、center/edge 等价、候选与 M1 布局的独立参考仿真、出口同刻归零。只作验算值。"""
import sys, json, math, itertools
import numpy as np
sys.path.insert(0, r"D:\Hermes\cache\scratch\rev27\align")
from unittest.mock import patch
import geometry, simulate, coverage, verify_a1
from ref import ref
P = [(0,0),(400,200),(700,800),(1200,900),(1500,1400),(1800,1700),(2000,2000)]
def dseg(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]; t = max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx + dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)
dpath = lambda p: min(dseg(p, P[i], P[i+1]) for i in range(6))
cand = json.load(open(r"D:\Hermes\cache\scratch\rev27\align\results\a1-candidate.json", encoding="utf-8-sig"))
COST = {"小塔": 100, "中塔": 250, "大塔": 600}; STOCK = {"小塔": 20, "中塔": 15, "大塔": 10}
print("== 1. 候选逐塔合法性（本实现的点到折线距离，不调用 geometry）")
for i, (x, y, k) in enumerate(cand, 1):
    d = dpath((x, y)); nn = min((math.hypot(x-a, y-b), j) for j, (a, b, _) in enumerate(cand, 1) if j != i)
    print(f"塔{i} ({x},{y}) {k}: 距中心线 {d:.6f} m (余量 {d-15:+.6f}) | geometry 差 {abs(d-geometry.dist_to_path(x,y)):.1e} | 最近邻 塔{nn[1]} {nn[0]:.6f} m (余量 {nn[0]-20:+.6f}) | 塔心∈[10,1990]²: {10<=x<=1990 and 10<=y<=1990}")
cnt = {k: sum(t[2] == k for t in cand) for k in COST}
print("数量", cnt, "库存内", all(cnt[k] <= STOCK[k] for k in cnt), "| 花费", sum(COST[t[2]] for t in cand), "≤2000 | 恰好相切的塔对:", [(i+1, j+1) for (i, a), (j, b) in itertools.combinations(enumerate(cand), 2) if math.hypot(a[0]-b[0], a[1]-b[1]) == 20.0])
print("== 2. center 与 edge 是否逐位等价（阈值附近 20 万个浮点 + nextafter）")
rng = np.random.default_rng(42); mism = 0
vals = np.concatenate([15 + rng.uniform(-1e-9, 1e-9, 100000), 15 + rng.uniform(-2, 2, 100000), [15.0, np.nextafter(15, 0), np.nextafter(15, 99), 0.0, 1e-300, 14.999999999999998]])
for d in vals: mism += ((d - 0) < 15) != ((d - 15) < 0)
vals2 = np.concatenate([20 + rng.uniform(-1e-9, 1e-9, 100000), 20 + rng.uniform(-3, 3, 100000), [20.0, np.nextafter(20, 0), np.nextafter(20, 99)]])
for d in vals2: mism += ((d - 0) < 20) != ((d - 20) < 0)
print("表达式级不一致次数:", int(mism))
bad = 0
for _ in range(3000):
    n = int(rng.integers(1, 6)); tw = []
    for _ in range(n):
        s = rng.uniform(0, geometry.path_length()); x, y = geometry.pos(float(s)); ang = rng.uniform(0, 6.2832); r = rng.choice([15.0, 15.0, rng.uniform(5, 40)])
        tw.append((float(x + r*math.cos(ang)), float(y + r*math.sin(ang)), "小塔"))
    if rng.random() < .5: tw.append((tw[0][0] + 20.0, tw[0][1], "小塔"))
    for mb in ("base_in_map", "center_in_map"):
        a = verify_a1.validate_layout(tw, map_boundary=mb, distance_basis="center"); b = verify_a1.validate_layout(tw, map_boundary=mb, distance_basis="edge")
        bad += a["通过"] != b["通过"] or len(a["问题"]) != len(b["问题"])
    a = verify_a1.validate_layout(tw); c = verify_a1.validate_layout(tw, map_boundary="center_in_map"); bad += a["通过"] and not c["通过"]
print("validate_layout 随机布局 3000 组：center/edge 判定不一致 或 base合法而center不合法 的次数:", bad)
for d in (15.0, float(np.nextafter(15, 0))):
    with patch.object(verify_a1, "dist_to_path", return_value=d):
        print(f"  dist={d!r}: center {verify_a1.validate_layout([(500,1500,'小塔')])['通过']} edge {verify_a1.validate_layout([(500,1500,'小塔')], distance_basis='edge')['通过']}")
for x in (10, 9.999999, 1990, 1990.000001, 0, 2000): print(f"  x={x}: base_in_map {verify_a1.validate_layout([(x,1000,'小塔')])['通过']} center_in_map {verify_a1.validate_layout([(x,1000,'小塔')], map_boundary='center_in_map')['通过']}")
print("== 3. 候选：独立参考仿真 (dt=0.002，本人实现) 对比 simulate.py")
tw = [tuple(t) for t in cand]
rl, rhp = ref(tw, 10, 1700, 20, 10, 0.002)
for dt in (0.05, 0.01):
    r = simulate.simulate(tw, {"数量": 10, "血量": 1700, "速度": 20, "出发间隔": 10}, dt); hp = np.array([e["剩余血量"] for e in r["每只敌人结果"]])
    print(f"simulate dt={dt}: 漏怪 {r['漏怪数']} 击杀编号 {[e['编号'] for e in r['每只敌人结果'] if e['结果']=='击杀']} | 与参考最大血量差 {np.abs(hp-rhp).max():.3f}")
print("参考: 漏怪", rl, "逐敌剩余", np.round(rhp, 2).tolist())
print("漏怪者距击杀阈值的最小剩余血量(参考):", round(float(rhp[rhp > 0].min()), 2), "HP")
print("== 4. M1 步长收敛布局：合法性与独立参考")
sys.path.insert(0, r"D:\Hermes\cache\scratch\rev27\align"); import validate_t12 as VT
ct = VT._convergence_towers(); v = verify_a1.validate_layout(ct); print("布局", [(round(x, 3), round(y, 3), k) for x, y, k in ct], "| validate_layout:", v["通过"], v["问题"], "花费", v["总花费元"])
rl, rhp = ref(ct, 10, 1700, 20, 10, 0.002); print("参考: 漏怪", rl, "逐敌剩余", np.round(rhp, 2).tolist())
print("== 5. M1 解析对拍：独立弦长")
x, y, R = 190, 120, 125; iv = coverage.cover_intervals(x, y, R)
a, b = np.array(P[0], float), np.array(P[1], float); u = (b-a)/np.hypot(*(b-a)); f = np.array([x, y]) - a; pr = f@u; perp = math.sqrt(f@f - pr*pr); half = math.sqrt(R*R - perp*perp)
print(f"OA 段: 垂距 {perp:.6f}, 垂足弧长 {pr:.6f}, 弦 [{pr-half:.6f}, {pr+half:.6f}] 长 {2*half:.9f} m；OA 长 447.2136；到 A 距离 {math.hypot(x-400,y-200):.3f}；到 AB 段距离 {dseg((x,y),P[1],P[2]):.3f}")
print("coverage.cover_intervals:", iv, "| 独立理论伤害 = 弦长/20×20 =", 2*half, "| exposure×DPS =", coverage.exposure(x, y, R, 20)*20)
for dt in (0.1, 0.05, 0.01, 0.001):
    r = simulate.simulate([(x, y, "中塔")], {"数量": 1, "血量": 10000, "速度": 20, "出发间隔": 0}, dt)["每只敌人结果"][0]; print(f"  dt={dt}: 承伤 {r['累计承伤']:.4f} 相对误差 {abs(r['累计承伤']-2*half)/(2*half)*100:.4f}% {r['结果']}")
print("== 6. 出口同刻归零 / 伤害只算到真实到达 D（合成 100 m 直路，v=40，出口 t=2.5 s，全程被 DPS10 小塔覆盖）")
with patch.object(geometry, "path_length", return_value=100.0), patch.object(geometry, "pos", side_effect=lambda s: (s, 0.0) if 0 <= s <= 100 else (_ for _ in ()).throw(AssertionError(s))):
    for dt in (0.5, 1.0, 2.5, 3.0, 0.3):
        row = []
        for H in (24.9, 25, 25.000001, 26, 29):
            r = simulate.simulate([(50, 20, "小塔")], {"数量": 1, "血量": H, "速度": 40, "出发间隔": 0}, dt)["每只敌人结果"][0]
            row.append(f"H={H}:{r['结果']}@{r['死亡时刻'] if r['结果']=='击杀' else r['漏怪时刻']} 承伤{r['累计承伤']:.6g}")
        print(f" dt={dt}: " + " | ".join(row))
