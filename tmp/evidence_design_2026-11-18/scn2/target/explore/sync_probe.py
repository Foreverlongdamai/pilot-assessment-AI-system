import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all
D=dict(task3_all())
v, run, nominal = sys.argv[1], sys.argv[2], float(sys.argv[3])
vd=pd.read_csv(f"video_{v}.csv")
df=D[run]; t=df["Simulation time"].values; h=-df["Ze m"].values
a=np.radians(226.0)
x,y=df["Xe m"].values,df["Ye m"].values
lat=x*np.cos(a)-y*np.sin(a); lon=x*np.sin(a)+y*np.cos(a)
for col,ref in (("u_y",None),("l_y",None),("u_x",None),("l_x",None)):
    pass
vd["u_y"]=(vd.du_y-vd.up_cy)/vd.spacing; vd["l_y"]=(vd.dl_y-vd.lo_cy)/vd.spacing
vd["u_x"]=(vd.du_x-vd.up_cx)/vd.spacing; vd["l_x"]=(vd.dl_x-vd.lo_cx)/vd.spacing
for col, sig in (("u_y",h),("l_y",h),("l_x",lat),("u_x",lat)):
    m=vd[col].notna().values
    best=None
    for off in np.arange(nominal-6, nominal+6, 0.05):
        tc=vd.t.values[m]+off
        ok=(tc>=t[0])&(tc<=t[-1])
        if ok.sum()<30: continue
        s=np.interp(tc[ok], t, sig)
        r=np.corrcoef(vd[col].values[m][ok], s)[0,1]
        res=np.polyfit(s, vd[col].values[m][ok],1)
        rms=np.std(vd[col].values[m][ok]-np.polyval(res,s))
        if best is None or rms<best[1]: best=(off,rms,r,res,ok.sum())
    print(col, "best offset %.2f rms %.4f r %.3f slope %.5f icpt %.4f n %d"%(best[0],best[1],best[2],best[3][0],best[3][1],best[4]), "zero at", -best[3][1]/best[3][0])
