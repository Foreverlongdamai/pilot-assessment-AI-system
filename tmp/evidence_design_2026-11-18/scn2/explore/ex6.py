import sys,numpy as np
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all, runs, first_sustained, KT
XT,YT=-213.17,4.675
for name,df in task3_all():
    d=df[df["Phase ID"].isin([1,2])].reset_index(drop=True)
    t=d["Simulation time"].values; t=t-t[0]
    x,y=d["Xe m"].values,d["Ye m"].values
    vh=np.hypot(d["V_ex m/s"],d["V_ey m/s"]).values
    st=first_sustained(t,vh>1.0,1.0)
    s=st+first_sustained(t[st:],vh[st:]<=0.5,0.5)
    mv=[(a+s,b+s) for a,b in runs(vh[s:]>0.5) if t[b+s]-t[a+s]>=0.5]
    seg=vh[s:(mv[0][0] if mv else len(vh))]
    bl=np.where(seg<=0.2)[0]; s1=s+(bl[0] if len(bl) else int(np.argmin(seg)))
    k6=np.where(vh[:s1]>=6*KT)[0][-1]
    L=np.hypot(XT,YT); ux,uy=XT/L,YT/L
    xt=(x*uy-y*ux)*-1
    # own line
    ex,ey=x[s1],y[s1]; L2=np.hypot(ex,ey); xo=(x*ey/L2-y*ex/L2)*-1
    win=slice(0,k6+1)
    segs=[(a,b) for a,b in runs(vh[s1:]>0.2) ]
    info=[]
    for a,b in segs:
        a+=s1;b+=s1
        disp=np.hypot(x[b]-x[a],y[b]-y[a]); info.append("%.1fs/%.2fm/%.2f"%(t[b]-t[a],disp,vh[a:b+1].max()))
    print("%-18s k6 %.1f s1 %.1f |xt|max %.2f |xo|max %.2f  segs: %s"%(name,t[k6],t[s1],np.abs(xt[win]).max(),np.abs(xo[win]).max()," ".join(info)))
