import sys,numpy as np,matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, r"C:\Users\long\Desktop\CranfieldOffer\proj\pilot_assessment_system\tmp\bn_optimization_2026-11-12")
from load import task3_all
data=dict(task3_all())
names=["13_55_01","14_01_54_standard","14_19_06","14_23_41","14_27_11","14_30_44","14_34_41","14_37_44"]
fig,ax=plt.subplots(8,3,figsize=(18,20))
for i,n in enumerate(names):
    df=data[n]
    for j,ph in enumerate((3,5,7)):
        d=df[df["Phase ID"].isin([ph,ph+1])]
        t=d["Simulation time"].values; t=t-t[0]
        h=-d["Ze m"].values; tgt=65.92 if ph in (3,7) else 40.92
        a=ax[i,j]
        a.plot(t,-d["V_ez m/s"],label="vz up"); a.plot(t,d["Pilot Heave"]/20,label="Heave/20")
        a.plot(t,np.clip(h-tgt,-5,5),label="h-tgt (clip5)")
        a.axvline(t[d["Phase ID"].values==ph+1][0],color="k"); a.grid(); a.set_title(f"{n} ph{ph}"); a.set_ylim(-5,5)
ax[0,0].legend()
plt.tight_layout(); plt.savefig("explore/ex4.png",dpi=50)
