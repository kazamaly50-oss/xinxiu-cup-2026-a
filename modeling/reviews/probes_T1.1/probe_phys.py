import time, numpy as np, geometry, simulate
from ref import ref
# --- P2 toy_check（rules.md 训练例；连续时间手算: E1 剩80, E2 剩80，0 杀）
tw=[(169.941166289984,219.13466179497937,"大塔")]
for dt in [0.5,0.05,0.001]:
    r=simulate.simulate(tw,{"数量":2,"血量":600,"速度":20,"出发间隔":10},dt)
    print("toy dt",dt,[(e["结果"],round(e["剩余血量"],3)) for e in r["每只敌人结果"]])
print("toy ref", ref(tw,2,600,20,10,0.001))
# --- P4 Q1 口径随机合法布局（集中在 B 角附近），Codex dt 收敛 vs 独立参考
rng=np.random.default_rng(42)
B=np.array([700.,800.]); COST={"小塔":100,"中塔":250,"大塔":600}
mixes=[["大塔"]*3+["小塔"]*2,["大塔"]*2+["中塔"]*3,["中塔"]*8,["大塔"]*3,["大塔"]*2+["中塔"]*2+["小塔"]*3,["小塔"]*20,["中塔"]*4+["大塔"]*1+["小塔"]*4]
rows=[]
for mix in mixes:
  assert sum(COST[k] for k in mix)<=2000
  for rep in range(3):
    pts=[]
    while len(pts)<len(mix):
        p=B+rng.uniform(-260,260,2)
        if not(10<=p[0]<=1990 and 10<=p[1]<=1990): continue
        if geometry.dist_to_path(*p)<15: continue
        if any(np.hypot(*(p-q))<20 for q in pts): continue
        pts.append(p)
    tw=[(float(p[0]),float(p[1]),k) for p,k in zip(pts,mix)]
    out={}
    for dt in [0.1,0.05,0.01]:
        t0=time.perf_counter(); r=simulate.simulate(tw,{"数量":10,"血量":1700,"速度":20,"出发间隔":10},dt); el=time.perf_counter()-t0
        out[dt]=(r["漏怪数"],np.array([e["剩余血量"] for e in r["每只敌人结果"]]),el)
    rl,rhp=ref(tw,10,1700,20,10,0.002)
    rows.append(("+".join(f"{mix.count(k)}{k[0]}" for k in COST if mix.count(k)),rep,[out[d][0] for d in out],rl,max(abs(out[0.05][1]-rhp)),max(abs(out[0.01][1]-rhp)),out[0.05][2]))
print("布局 | 漏怪(dt=.1,.05,.01) | 参考漏怪 | max|Δhp| dt.05 vs ref | dt.01 vs ref | 单次simulate耗时(dt=.05)")
for r in rows: print(r[0],r[1],r[2],r[3],round(r[4],2),round(r[5],2),f"{r[6]:.3f}s")
mis=[r for r in rows if r[2][1]!=r[3]]; print("dt=0.05 与参考漏怪不一致:",len(mis),"/",len(rows))
