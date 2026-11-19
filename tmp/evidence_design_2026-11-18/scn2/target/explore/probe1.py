import sys, os, numpy as np
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all, wrap180
FT=0.3048
for n, df in task3_all():
    T=df["Simulation time"].values
    ph=df["Phase ID"].values
    s=f"{n:<18} dur {T[-1]:6.1f} phases {sorted(set(ph))[-1]} "
    for p in (2,4,6,8):
        d=df[ph==p]
        if len(d)==0: continue
        x,y,h=d["Xe m"].values,d["Ye m"].values,-d["Ze m"].values
        s+=f"| p{p} ({x[-1]:8.3f},{y[-1]:6.3f}) h {h[-1]:6.3f} "
    d=df[ph==2]; x,y=d["Xe m"].values[-1],d["Ye m"].values[-1]
    r=np.hypot(x,y); b=np.degrees(np.arctan2(x,y))%360
    s+=f"| r {r:7.3f} m = {r/FT:6.1f} ft brg {b:6.2f} rel {b-226:5.2f}"
    print(s)
    # phase start times
print()
n,df=task3_all()[1]
ph=df["Phase ID"].values; t=df["Simulation time"].values
for p in range(10):
    m=ph==p
    if m.any(): print(p, t[m][0], t[m][-1], -df["Ze m"].values[m][0], -df["Ze m"].values[m][-1])
