import math, geometry, simulate
from unittest.mock import patch
L=geometry.path_length(); real_pos=geometry.pos; calls=[]
def strict(s):
    calls.append(s)
    if not (0<=s<=L): raise AssertionError(f"C1 violated: pos({s!r})")
    return real_pos(s)
print("== C1 real path")
with patch.object(geometry,"pos",side_effect=strict):
    for name,dt in [("恰达终点 dt=L/20 (exit=1*dt)",L/20),("越过终点 dt=100",100.0),("越过终点 dt=7",7.0),("默认 dt=0.05",0.05),("dt=0.1",0.1)]:
        calls.clear()
        r=simulate.simulate([(190,120,"中塔")],{"数量":3,"血量":1e6,"速度":20,"出发间隔":10},dt)
        e=r["每只敌人结果"]
        print(f"{name}: 漏怪数={r['漏怪数']} 漏怪时刻={[x['漏怪时刻'] for x in e]} pos调用={len(calls)} max_s={max(calls) if calls else None} (L={L})")
print("== C1 synthetic 100 m road, speed 40, exit 2.5 s, tower DPS10 full cover")
with patch.object(geometry,"path_length",return_value=100.0), patch.object(geometry,"pos",side_effect=lambda s: (s,0.0) if 0<=s<=100 else (_ for _ in ()).throw(AssertionError(s))):
    for dt in [0.5,1.0,2.5,3.0]:
        for H in [24,25,26]:
            r=simulate.simulate([(50,20,"小塔")],{"数量":1,"血量":H,"速度":40,"出发间隔":0},dt)["每只敌人结果"][0]
            print(f" dt={dt} H={H}: {r['结果']} 死亡={r['死亡时刻']} 漏怪={r['漏怪时刻']} 承伤={r['累计承伤']}")
