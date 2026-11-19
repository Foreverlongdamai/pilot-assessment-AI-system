import sys, numpy as np, pandas as pd
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all
D=dict(task3_all())
v, run, nominal = sys.argv[1], sys.argv[2], float(sys.argv[3])
vd=pd.read_csv(f"video_{v}.csv")
for k,(dc,bc) in {"l_x":("dl_x","lo_cx"),"l_y":("dl_y","lo_cy"),"u_x":("du_x","up_cx"),"u_y":("du_y","up_cy")}.items():
    vd[k]=(vd[dc]-vd[bc])/vd.spacing
df=D[run]; t=df["Simulation time"].values; h=-df["Ze m"].values; ph=df["Phase ID"].values
a=np.radians(226.0); x,y=df["Xe m"].values,df["Ye m"].values
lat=x*np.cos(a)-y*np.sin(a); lon=x*np.sin(a)+y*np.cos(a)
vh=np.hypot(df["V_ex m/s"],df["V_ey m/s"]).values; vz=-df["V_ez m/s"].values
def fit_off(col, sig, sel_sig):
    best=None
    for off in np.arange(nominal-3, nominal+3, 0.02):
        tc=vd.t.values+off; val=vd[col].values
        m=~np.isnan(val)&(tc>t[0])&(tc<t[-1])
        s=np.interp(tc[m],t,sig); sel=np.interp(tc[m],t,sel_sig)>0.5
        m2=sel&(np.abs(val[m])<0.6)
        if m2.sum()<20: continue
        p=np.polyfit(s[m2],val[m][m2],1); r=val[m][m2]-np.polyval(p,s[m2])
        k=np.abs(r)<4*np.median(np.abs(r))+1e-9
        p=np.polyfit(s[m2][k],val[m][m2][k],1); r=val[m][m2][k]-np.polyval(p,s[m2][k])
        if best is None or np.sqrt(np.mean(r**2))<best[1]: best=(off,np.sqrt(np.mean(r**2)),p,k.sum())
    return best
climb=np.isin(ph,[3,5,7]).astype(float)
for col in ("u_y","l_y"):
    b=fit_off(col,h,climb); print(col,"offset %.2f rms %.4f slope %.5f zero h %.3f n %d"%(b[0],b[1],b[2][0],-b[2][1]/b[2][0],b[3]))
moving_lat=((np.isin(ph,[1,2]))&(vh>0.05)&(vh<2.5)).astype(float)
b=fit_off("l_x",lat,moving_lat); print("l_x offset %.2f rms %.4f slope %.5f zero lat %.3f n %d"%(b[0],b[1],b[2][0],-b[2][1]/b[2][0],b[3]))
