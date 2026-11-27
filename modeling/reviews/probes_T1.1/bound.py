# 审核方验算：单塔"射程内有敌"总时长上界（10 敌、间距 200 m、v=20），只作验算值
import math
P=[(0,0),(400,200),(700,800),(1200,900),(1500,1400),(1800,1700),(2000,2000)]
S=[(P[i],P[i+1]) for i in range(6)]; L=[math.dist(a,b) for a,b in S]; CUM=[0]
for l in L: CUM.append(CUM[-1]+l)
def dseg(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]; t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)
def dpath(p): return min(dseg(p,a,b) for a,b in S)
def cov(p,R):
    iv=[]
    for i,(a,b) in enumerate(S):
        l=L[i]; ux,uy=(b[0]-a[0])/l,(b[1]-a[1])/l; fx,fy=a[0]-p[0],a[1]-p[1]
        B=fx*ux+fy*uy; disc=B*B-(fx*fx+fy*fy-R*R)
        if disc<=0: continue
        s1=max(0,-B-math.sqrt(disc)); s2=min(l,-B+math.sqrt(disc))
        if s2>s1: iv.append((CUM[i]+s1,CUM[i]+s2))
    return iv
def ulen(iv):
    iv=sorted(iv); tot=0; cs=ce=None
    for a,b in iv:
        if cs is None: cs,ce=a,b
        elif a<=ce: ce=max(ce,b)
        else: tot+=ce-cs; cs,ce=a,b
    return tot+(ce-cs if cs is not None else 0)
def up(iv): return ulen([(a+200*i,b+200*i) for i in range(10) for a,b in iv])
res={}
for name,R,dps,cost in [("小",75,10,100),("中",125,20,250),("大",200,40,600)]:
    best=(0,None)
    for xi in range(10,1991,4):
        for yi in range(10,1991,4):
            p=(xi,yi)
            if dpath(p)<15: continue
            iv=cov(p,R)
            if iv:
                u=up(iv)
                if u>best[0]: best=(u,p)
    p0=best[1]
    for dx in range(-20,21):
        for dy in range(-20,21):
            p=(p0[0]+dx*0.2,p0[1]+dy*0.2)
            if dpath(p)<15 or not(10<=p[0]<=1990 and 10<=p[1]<=1990): continue
            u=up(cov(p,R))
            if u>best[0]: best=(u,p)
    u,p=best; iv=cov(p,R); res[name]=u/20*dps
    print(f"{name}塔 sup在场路程={u:.2f} m 位置=({p[0]:.1f},{p[1]:.1f}) 覆盖区间={[(round(a,1),round(b,1)) for a,b in iv]} 总伤害上界={u/20*dps:.1f} 每元={u/20*dps/cost:.3f}")
C={"小":100,"中":250,"大":600}
cands=[(a,b,c) for a in range(21) for b in range(16) for c in range(11) if 100*a+250*b+600*c<=2000]
bb=max(cands,key=lambda k:k[0]*res["小"]+k[1]*res["中"]+k[2]*res["大"])
D=bb[0]*res["小"]+bb[1]*res["中"]+bb[2]*res["大"]
print("预算2000+数量上限下 总伤害上界最大组合 (小,中,大)=",bb,f"上界={D:.1f}  总血量=17000  => 至多击杀 {int(D//1700)} 只, 漏怪下界 {10-int(D//1700)}")
