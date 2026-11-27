"""Hermes 独立复核 a1_bounds 的三个单塔上界（浮点 + numpy，自己写的四叉树；与 Codex 的整数实现无共享代码）。
只作验算值，不进论文。"""
import sys, time, itertools, random
import numpy as np
sys.path.insert(0, r"D:\Hermes\cache\scratch\rev27\align")
V = np.array([(0,0),(400,200),(700,800),(1200,900),(1500,1400),(1800,1700),(2000,2000)], float)
D = np.diff(V, axis=0); SL = np.hypot(D[:,0], D[:,1]); U = D / SL[:,None]; CUM = np.r_[0, np.cumsum(SL)]
NE, GAP = 10, 200.0
def busy(cx, cy, R):
    """v×(至少一敌在射程内的总时长)，单位 m。cx,cy,R 为等长数组。"""
    n = len(cx); st = np.full((n, 6*NE), -1.0); en = np.full((n, 6*NE), -1.0)
    for i in range(6):
        fx, fy = cx - V[i,0], cy - V[i,1]
        proj = fx*U[i,0] + fy*U[i,1]; perp2 = fx*fx + fy*fy - proj*proj
        disc = R*R - perp2; ok = disc >= 0; rt = np.sqrt(np.where(ok, disc, 0))
        s1 = np.clip(proj - rt, 0, SL[i]); s2 = np.clip(proj + rt, 0, SL[i]); ok &= s2 > s1
        for e in range(NE):
            st[:, i*NE+e] = np.where(ok, CUM[i] + s1 + GAP*e, -1.0); en[:, i*NE+e] = np.where(ok, CUM[i] + s2 + GAP*e, -1.0)
    idx = np.argsort(st, axis=1); st = np.take_along_axis(st, idx, 1); en = np.take_along_axis(en, idx, 1)
    prev = np.maximum.accumulate(en, axis=1); prev = np.c_[np.full(n, -1.0), prev[:, :-1]]
    return np.clip(en - np.maximum(st, prev), 0, None).sum(axis=1)
def chunked(cx, cy, R, m=200000):
    return np.concatenate([busy(cx[i:i+m], cy[i:i+m], R[i:i+m]) for i in range(0, len(cx), m)]) if len(cx) else np.zeros(0)
def certify(R, cap, eps=1e-6):
    g = np.arange(10.0, 2000, 20.0); cx, cy = [a.ravel() for a in np.meshgrid(g, g)]; half = 10.0
    visited = leaves = 0; worst = 0.0; deepest = None
    while len(cx):
        ub = chunked(cx, cy, np.full(len(cx), R + half*np.sqrt(2) + eps)); visited += len(cx)
        ok = ub <= cap; leaves += int(ok.sum()); worst = max(worst, float(ub[ok].max(initial=0)))
        fx, fy = cx[~ok], cy[~ok]
        if len(fx): deepest = (half, len(fx), float(fx.mean()), float(fy.mean()), float(fx.min()), float(fx.max()), float(fy.min()), float(fy.max()))
        half /= 2
        if half < 5e-5 and len(fx): return dict(通过=False, 剩余未过格=len(fx), 位置=deepest)
        cx = np.concatenate([fx-half, fx-half, fx+half, fx+half]); cy = np.concatenate([fy-half, fy+half, fy-half, fy+half])
    return dict(通过=True, 检查格数=visited, 叶格数=leaves, 叶格最大上界m=round(worst, 6), 最后一层未过格=deepest)
def sup_estimate(R):
    g = np.arange(0.0, 2000.01, 2.0); X, Y = [a.ravel() for a in np.meshgrid(g, g)]
    b = chunked(X, Y, np.full(len(X), float(R))); k = int(b.argmax()); x0, y0 = X[k], Y[k]
    for h in (0.1, 0.005, 0.0002):
        g2 = np.arange(-25, 26) * h; XX, YY = [a.ravel() for a in np.meshgrid(x0 + g2, y0 + g2)]
        m = (XX >= 0) & (XX <= 2000) & (YY >= 0) & (YY <= 2000); XX, YY = XX[m], YY[m]
        bb = busy(XX, YY, np.full(len(XX), float(R))); k = int(bb.argmax()); x0, y0 = XX[k], YY[k]
    return float(bb.max()), (round(float(x0), 3), round(float(y0), 3))
TT = {"小塔": (75, 10, 100, 20, 1671), "中塔": (125, 20, 250, 15, 2080), "大塔": (200, 40, 600, 10, 2250)}
print("== 1. 独立四叉树复核（全地图 [0,2000]²，不加离路/间距约束）")
for k, (R, dps, cost, stock, cap) in TT.items():
    t0 = time.perf_counter(); r = certify(R, cap); s, p = sup_estimate(R)
    print(f"{k}: cap={cap} m -> {r} | 浮点搜索到的最大值≈{s:.3f} m @ {p}（下方估计，非证明）| cap 余量≈{cap-s:.3f} m | {time.perf_counter()-t0:.1f}s")
print("== 2. Codex 整数函数 busy_distance_upper_mm 对拍本实现（种子42，30000 点，含扩张半径）")
import a1_bounds as B
seg = B.road_segments(); rng = random.Random(42); xs=[]; ys=[]; rs=[]; ub=[]
for _ in range(30000):
    s = rng.uniform(0, CUM[-1]); i = min(int(np.searchsorted(CUM, s, side="right") - 1), 5)
    px, py = V[i] + U[i]*(s - CUM[i])
    x_mm = round(1000*(px + rng.uniform(-220, 220))); y_mm = round(1000*(py + rng.uniform(-220, 220)))
    r_mm = rng.choice((75000, 125000, 200000)) + rng.choice((0, 0, rng.randrange(0, 30000)))
    xs.append(x_mm/1000); ys.append(y_mm/1000); rs.append(r_mm/1000); ub.append(B.busy_distance_upper_mm(x_mm, y_mm, r_mm, seg)/1000)
mine = busy(np.array(xs), np.array(ys), np.array(rs)); diff = np.array(ub) - mine
print(f"Codex上界 − 本实现: min={diff.min():.6f} m, max={diff.max():.6f} m, 非零覆盖点数={(mine>0).sum()}；出现 Codex<本实现−1e-6 的点数={(diff < -1e-6).sum()}")
print("== 3. 段长/里程向外取整核对")
for sg, l, c in zip(seg, SL, CUM): print(f"  len∈[{sg.length_lower_mm},{sg.length_upper_mm}] mm 真值 {l*1000:.4f} | prefix∈[{sg.prefix_lower_mm},{sg.prefix_upper_mm}] 真值 {c*1000:.4f} | 包含={sg.length_lower_mm<=l*1000<=sg.length_upper_mm and sg.prefix_lower_mm<=c*1000<=sg.prefix_upper_mm}")
print("== 4. 预算内组合独立枚举")
combos = [(a, b, c) for a in range(21) for b in range(16) for c in range(11) if 100*a + 250*b + 600*c <= 2000]
dmg = lambda k: k[0]*10*1671/20 + k[1]*20*2080/20 + k[2]*40*2250/20
top = sorted(combos, key=dmg, reverse=True)[:4]
print("组合数", len(combos), "| 前四:", [(k, dmg(k), 100*k[0]+250*k[1]+600*k[2]) for k in top])
print("超过17000的组合数:", sum(dmg(k) >= 17000 for k in combos), "| 击杀上界 floor(16710/1700) =", int(dmg(top[0]) // 1700))
need = 9*1700; feas = [(100*k[0]+250*k[1]+600*k[2], k, dmg(k)) for k in combos if dmg(k) >= need]
print("上界≥15300 的最小花费:", min(feas)[:3], "| 花费<1850 的最大上界:", max((dmg(k), k) for k in combos if 100*k[0]+250*k[1]+600*k[2] < 1850))
