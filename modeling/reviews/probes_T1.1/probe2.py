import math, numpy as np, time, geometry, simulate, coverage
from ref import ref, xy, CUM, V
# ---- coverage 独立核对：逐段二次方程（审核方从零写）
P=[tuple(v) for v in V]
def mycov(p,R):
    out=[]
    for i in range(6):
        a,b=np.array(P[i]),np.array(P[i+1]); d=b-a; l=np.hypot(*d); u=d/l; f=a-p
        B=f@u; C=f@f-R*R; disc=B*B-C
        if disc<0: continue
        s1=max(0,-B-math.sqrt(disc)); s2=min(l,-B+math.sqrt(disc))
        if s2>=s1: out.append((CUM[i]+s1,CUM[i]+s2))
    m=[]
    for s in out:
        if m and s[0]<=m[-1][1]+1e-8: m[-1]=(m[-1][0],max(m[-1][1],s[1]))
        else: m.append(s)
    return m
rng=np.random.default_rng(42); worst=0
for _ in range(2000):
    p=rng.uniform(-100,2100,2); R=float(rng.choice([75,125,200]))
    a=coverage.cover_intervals(*p,R); b=mycov(p,R)
    if len(a)!=len(b): print("count mismatch",p,R,a,b); continue
    for x,y in zip(a,b): worst=max(worst,abs(x[0]-y[0]),abs(x[1]-y[1]))
print("coverage vs 独立: 2000 点最大端点差 m =",worst)
for p,R in [((722.25,770.75),75),((737.25,751.5),125),((759.25,722.25),200)]:
    print("B角最佳点",p,R,"覆盖长",round(sum(e-s for s,e in coverage.cover_intervals(*p,R)),2),"exposure@20",round(coverage.exposure(*p,R,20),3))
# ---- 阈值扫描：固定一个能杀怪的布局，二分找"漏怪数从k变到k+1"的血量阈值，对比不同 dt 与参考
tw=[(759.25,722.25,"大塔"),(737.25,700.0,"大塔"),(790.0,745.0,"大塔")]
for t in tw: assert geometry.dist_to_path(t[0],t[1])>=15
assert all(math.dist(a[:2],b[:2])>=20 for i,a in enumerate(tw) for b in tw[i+1:])
def leaks_codex(H,dt): return simulate.simulate(tw,{"数量":10,"血量":H,"速度":20,"出发间隔":10},dt)["漏怪数"]
def leaks_ref(H): return ref(tw,10,H,20,10,0.002)[0]
for H in [1000,1300,1500,1700]:
    print("H",H,"codex dt.1/.05/.01:",[leaks_codex(H,d) for d in (0.1,0.05,0.01)],"ref:",leaks_ref(H))
def thr(f,lo=500,hi=2500):
    k=f(lo)
    for _ in range(22):
        m=(lo+hi)/2
        if f(m)==k: lo=m
        else: hi=m
    return lo,k
for d in (0.1,0.05,0.01):
    t0=time.perf_counter(); h,k=thr(lambda H: leaks_codex(H,d)); print(f"codex dt={d}: 漏怪数={k} 保持到 H≈{h:.2f}  ({time.perf_counter()-t0:.1f}s)")
h,k=thr(leaks_ref); print(f"ref dt=0.002: 漏怪数={k} 保持到 H≈{h:.2f}")
