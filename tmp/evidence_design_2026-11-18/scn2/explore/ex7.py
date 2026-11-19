import sys,numpy as np
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all, runs, first_sustained
HL,HU=40.92,65.92
for name,df in task3_all():
    if 9 not in set(df["Phase ID"]): continue
    for ph in (3,5,7):
        d=df[df["Phase ID"]==ph].reset_index(drop=True)
        t=d["Simulation time"].values; t=t-t[0]; h=-d["Ze m"].values; vz=-d["V_ez m/s"].values; u=d["Pilot Heave"].values
        sg=1 if ph in (3,7) else -1; ht=HU if sg>0 else HL
        i_in=np.where(np.abs(u)>5)[0][0]
        # wrong-direction
        wrong=max(0,-(sg*(h-h[0])).min())
        mr=first_sustained(t,sg*vz>=0.5,0.5)
        s=mr+first_sustained(t[mr:],np.abs(vz[mr:])<=0.5,0.5)
        mv=[(a+s,b+s) for a,b in runs(np.abs(vz[s:])>0.5) if t[b+s]-t[a+s]>=0.5]
        seg=np.abs(vz[s:(mv[0][0] if mv else len(vz))]); bl=np.where(seg<=0.2)[0]; s1=s+(bl[0] if len(bl) else int(np.argmin(seg)))
        mov=np.where(np.abs(vz)>0.2)[0]; tf=mov[-1]+1
        segs=[(a+s1,b+s1) for a,b in runs(np.abs(vz[s1:])>0.2)]
        info=" ".join("%.2fs/%.2fm"%(t[b]-t[a],h[b]-h[a]) for a,b in segs)
        over=max(0,sg*(h[s1:].max() if sg>0 else h[s1:].min())*1 - sg*h[-1]) if True else 0
        over=max(0.0, sg*((h[s1:] if True else h)).max()*0) 
        ext=(h.max() if sg>0 else h.min()); over=sg*(ext-h[-1])
        print("%-18s ph%d in@%.2f wrong %.2f  t_s1 %.2f e_s1 %+.2f e_end %+.2f over %.2f tf %.2f T %.2f | %s"%(name,ph,t[i_in],wrong,t[s1],h[s1]-ht,h[-1]-ht,over,t[tf] if tf<len(t) else np.nan,t[-1],info))
