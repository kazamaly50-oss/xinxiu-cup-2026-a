# 独立参考仿真（审核方编写，不调用被审代码的选敌/扣血逻辑）：小步长 + 每步重选最近 + 同时扣血
import numpy as np
V=np.array([(0,0),(400,200),(700,800),(1200,900),(1500,1400),(1800,1700),(2000,2000)],float)
SL=np.hypot(*np.diff(V,axis=0).T); CUM=np.r_[0,np.cumsum(SL)]; LTOT=CUM[-1]
ST={"小塔":(75,10),"中塔":(125,20),"大塔":(200,40)}
def xy(s): return np.c_[np.interp(s,CUM,V[:,0]),np.interp(s,CUM,V[:,1])]
def ref(towers,N,H,v,gap,dt=0.002):
    T=np.array([(x,y) for x,y,_ in towers],float).reshape(-1,2); R=np.array([ST[k][0] for *_,k in towers],float); D=np.array([ST[k][1] for *_,k in towers],float)
    birth=np.arange(N)*gap; hp=np.full(N,float(H)); state=np.zeros(N,int) # 0 alive,1 kill,2 leak
    t=0.0; k=0; tend=birth[-1]+LTOT/v+dt
    while k*dt<=tend and (state==0).any():
        t=k*dt
        s=(t-birth)*v
        for i in np.where((state==0)&(s>=LTOT))[0]: state[i]=2
        alive=np.where((state==0)&(s>=0))[0]
        if len(alive) and len(T):
            P=xy(s[alive]); d=np.hypot(P[:,None,0]-T[None,:,0],P[:,None,1]-T[None,:,1])  # enemy x tower
            d=np.where(d<=R[None,:],d,np.inf); j=np.argmin(d,axis=0); ok=np.isfinite(d[j,np.arange(len(T))])
            dmg=np.zeros(len(alive)); np.add.at(dmg,j[ok],D[ok]*dt)
            hp[alive]-=dmg
            state[alive[hp[alive]<=1e-9]]=1
        k+=1
    state[state==0]=2
    return int((state==2).sum()), hp.clip(0)
