import sys,numpy as np
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all, runs, first_sustained
XT,YT=-213.17,4.675
psi0=np.radians(226.0)
for name,df in task3_all():
    d=df[df["Phase ID"].isin([1,2])].reset_index(drop=True)
    t=d["Simulation time"].values; t=t-t[0]; T1=t[(d["Phase ID"]==1).values][-1]
    x,y=d["Xe m"].values,d["Ye m"].values
    vh=np.hypot(d["V_ex m/s"],d["V_ey m/s"]).values
    s=first_sustained(t,vh<=0.5,0.5)
    # skip until moving first
    st=first_sustained(t,vh>1.0,1.0)
    s=st+first_sustained(t[st:],vh[st:]<=0.5,0.5)
    mv=[(a+s,b+s) for a,b in runs(vh[s:]>0.5) if t[b+s]-t[a+s]>=0.5]
    seg=vh[s:(mv[0][0] if mv else len(vh))]
    bl=np.where(seg<=0.2)[0]; s1=s+(bl[0] if len(bl) else int(np.argmin(seg)))
    # last time vh>0.2 (stabilized after)
    mov=np.where(vh>0.2)[0]; tst=t[mov[-1]+1] if mov[-1]+1<len(t) else np.nan
    # decel initiation: last local max of smoothed vh before s1 with vh>=0.8*max over preceding 5 s
    k=s1
    while k>0 and vh[k-1]>=vh[k]-1e-4: k-=1
    # body-axis errors at initial stop and final
    def err(i):
        dx,dy=x[i]-XT,y[i]-YT
        # heading 226: nose direction in world: from scene-1 convention 270 -> -X. psi measured so that 270 => (-1,0); assume 180=> -Y? use compass: north=+X? test: dir=(cos psi, sin psi): 270 -> (0,-1) wrong.
        return np.hypot(dx,dy)
    # moves in body axes after s1
    vbx,vby=d["V_bx m/s"].values,d["V_by m/s"].values
    nmx=len([1 for a,b in runs(np.abs(vbx[s1:])>0.5) if t[b+s1]-t[a+s1]>=0.5]); nmy=len([1 for a,b in runs(np.abs(vby[s1:])>0.5) if t[b+s1]-t[a+s1]>=0.5])
    nm2=len([1 for a,b in runs(vh[s1:]>0.2) if t[b+s1]-t[a+s1]>=0.5])
    path=np.sum(np.hypot(np.diff(x[s1:]),np.diff(y[s1:])))
    print("%-18s T1 %5.1f t_dec %5.1f t_s1 %5.1f v_dec %.2f decdur %.1f d_s1 %5.2f d_end %4.2f | t_stab %5.1f stab-dec %5.1f | moves bx%d by%d vh0.2:%d path %.1f"%(name,T1,t[k],t[s1],vh[k],t[s1]-t[k],err(s1),err(len(t)-1),tst,tst-t[k],nmx,nmy,nm2,path))
