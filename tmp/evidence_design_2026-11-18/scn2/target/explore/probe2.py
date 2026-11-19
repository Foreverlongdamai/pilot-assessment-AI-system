import sys, numpy as np
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all
D=dict(task3_all())
def hms(n):
    p=n.split("_"); return int(p[0])*3600+int(p[1])*60+int(p[2])
vids={"142010":(14*3600+20*60+10,146.3),"143450":(14*3600+34*60+50,188.0),"145543":(14*3600+55*60+43,74.3)}
for v,(s,dur) in vids.items():
    for n,df in D.items():
        T=df["Simulation time"].values[-1]; end=hms(n); st=end-T
        ov=min(end,s+dur)-max(st,s)
        if ov>0: print(v,"overlaps",n,f"csv start {st-s:+.1f}s rel video start, csv end {end-s:+.1f}, overlap {ov:.1f}")
for n in ("14_23_41","14_37_44","14_57_09","14_55_53","14_19_06"):
    df=D[n]; ph=df["Phase ID"].values; t=df["Simulation time"].values
    vh=np.hypot(df["V_ex m/s"],df["V_ey m/s"]).values
    s=n+": "+" ".join(f"p{p}@{t[ph==p][0]:.1f}" for p in range(10) if (ph==p).any())
    mv=np.where(vh>0.3)[0]
    s+=f" | first move {t[mv[0]]:.1f} last move {t[mv[-1]]:.1f}"
    print(s)
