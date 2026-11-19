import sys, numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all
D=dict(task3_all())
v, run, off = sys.argv[1], sys.argv[2], float(sys.argv[3])
vd=pd.read_csv(f"video_{v}.csv"); tc=vd.t+off
df=D[run]; t=df["Simulation time"].values; h=-df["Ze m"].values
a=np.radians(226.0); x,y=df["Xe m"].values,df["Ye m"].values
lat=x*np.cos(a)-y*np.sin(a); lon=x*np.sin(a)+y*np.cos(a)
fig,ax=plt.subplots(5,1,figsize=(14,14),sharex=True)
ax[0].plot(t,h); ax[0].set_ylabel("h"); a0=ax[0].twinx(); a0.plot(t,df["Phase ID"],'k:')
ax[1].plot(t,lat,label='lat'); ax[1].plot(t,lon,label='lon'); ax[1].set_ylim(140,160); ax[1].legend()
ax[2].plot(tc,(vd.du_y-vd.up_cy)/vd.spacing,'.',ms=2,label='u_y'); ax[2].plot(tc,(vd.dl_y-vd.lo_cy)/vd.spacing,'.',ms=2,label='l_y'); ax[2].legend(); ax[2].set_ylim(-1.5,1.5); ax[2].grid()
ax[3].plot(tc,(vd.du_x-vd.up_cx)/vd.spacing,'.',ms=2,label='u_x'); ax[3].plot(tc,(vd.dl_x-vd.lo_cx)/vd.spacing,'.',ms=2,label='l_x'); ax[3].legend(); ax[3].set_ylim(-0.5,0.5); ax[3].grid()
ax[4].plot(tc,vd.spacing,'.',ms=2,label='spacing'); ax[4].plot(tc,vd.lo_w,'.',ms=2,label='lo_w'); ax[4].legend()
plt.tight_layout(); plt.savefig(f"ts_{v}.png",dpi=70)
