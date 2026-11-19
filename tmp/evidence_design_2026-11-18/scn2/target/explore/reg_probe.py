import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all
D=dict(task3_all())
v, run, off, t0, t1 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
vd=pd.read_csv(f"video_{v}.csv"); tc=vd.t.values+off
df=D[run]; t=df["Simulation time"].values; h=-df["Ze m"].values
a=np.radians(226.0); x,y=df["Xe m"].values,df["Ye m"].values
lat=x*np.cos(a)-y*np.sin(a); lon=x*np.sin(a)+y*np.cos(a)
for col,(dc,bc) in {"l_x":("dl_x","lo_cx"),"l_y":("dl_y","lo_cy"),"u_x":("du_x","up_cx"),"u_y":("du_y","up_cy")}.items():
    val=((vd[dc]-vd[bc])/vd.spacing).values
    m=(~np.isnan(val))&(tc>=t0)&(tc<=t1)
    if m.sum()<10: print(col,"n",m.sum()); continue
    LA=np.interp(tc[m],t,lat); LO=np.interp(tc[m],t,lon); H=np.interp(tc[m],t,h)
    A=np.c_[LA-151.5,LO-150,H-40.92,np.ones(m.sum())]
    c,res,_,_=np.linalg.lstsq(A,val[m],rcond=None)
    r=val[m]-A@c
    # robust: drop >3 sigma
    k=np.abs(r)<3*np.std(r)
    c,res,_,_=np.linalg.lstsq(A[k],val[m][k],rcond=None); r=val[m][k]-A[k]@c
    print(col,"n %d  coef lat %.4f lon %.4f h %.4f const %.4f  rms %.4f | ranges lat %.2f-%.2f lon %.2f-%.2f h %.2f-%.2f"%(k.sum(),*c,np.std(r),LA.min(),LA.max(),LO.min(),LO.max(),H.min(),H.max()))
