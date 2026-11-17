# -*- coding: utf-8 -*-
import numpy as np, matplotlib, json
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.decomposition import PCA
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, roc_curve, precision_recall_fscore_support
plt.rcParams['axes.unicode_minus']=False
rng=np.random.default_rng(11)
N=3000; t=np.arange(N)
load=0.5+0.35*(np.sin(2*np.pi*t/1300)+1)/2 + 0.05*np.sin(2*np.pi*t/210)
n=lambda s: s*rng.standard_normal(N)
Ir=load*(1+0.06*rng.standard_normal(N)); Is=load*(1+0.06*rng.standard_normal(N)); It=load*(1+0.06*rng.standard_normal(N))
V=1.0-0.05*load+0.02*rng.standard_normal(N); PF=0.95-0.02*load+0.012*rng.standard_normal(N)
P=np.sqrt(3)*V*((Ir+Is+It)/3)*PF*(1+0.02*rng.standard_normal(N))
X=np.column_stack([Ir,Is,It,V,PF,P]); y=np.zeros(N,int)
def w(a,b): y[a:b]=1
# 미묘한 이상 4종
X[600:665,0]+=np.linspace(0,0.22,65); w(600,665)          # (1) Ir 완만한 드리프트
X[1150:1215,1]=load[1150:1215].mean()+0.06*n(1)[1150:1215]; w(1150,1215)  # (2) 상관 붕괴(Is 디커플)
X[1800:1865,4]-=0.055; w(1800,1865)                        # (3) PF 소폭 급락
X[2400:2455,5]*=1.12; w(2400,2455)                         # (4) 물리 위반(P만 이탈)
Pres=X[:,5]-np.sqrt(3)*X[:,3]*(X[:,0]+X[:,1]+X[:,2])/3*X[:,4]
Xf=np.column_stack([X,Pres])
Z=StandardScaler().fit_transform(Xf); ni=np.where(y==0)[0]
s_if=-IsolationForest(n_estimators=300,contamination=0.07,random_state=11).fit(Z).score_samples(Z)
pca=PCA(n_components=4).fit(Z[ni]); s_pca=np.mean((Z-pca.inverse_transform(pca.transform(Z)))**2,axis=1)
ae=MLPRegressor(hidden_layer_sizes=(24,4,24),activation='relu',max_iter=900,random_state=11).fit(Z[ni],Z[ni])
s_ae=np.mean((Z-ae.predict(Z))**2,axis=1)
def M(s):
    auc=roc_auc_score(y,s); thr=np.quantile(s[ni],0.95); pr=(s>thr).astype(int)
    p,r,f,_=precision_recall_fscore_support(y,pr,average='binary',zero_division=0); return auc,p,r,f
res={'Isolation Forest':M(s_if),'PCA (linear)':M(s_pca),'Autoencoder':M(s_ae)}
for k,(a,p,r,f) in res.items(): print(f'{k}: AUC={a:.3f} P={p:.3f} R={r:.3f} F1={f:.3f}')
json.dump({k:[round(v,3) for v in v2] for k,v2 in res.items()},open('metrics.json','w'))
# Figure (English labels)
fig,(ax1,ax2)=plt.subplots(1,2,figsize=(12,4.2),gridspec_kw={'width_ratios':[1.7,1]})
ax1.plot(s_ae,color='#185FA5',lw=0.9,label='Anomaly score (AE recon. error)')
thr=np.quantile(s_ae[ni],0.95); ax1.axhline(thr,color='#D85A30',lw=1.2,ls='--',label='Threshold (normal 95th pct)')
f=True
for a,b in [(600,665),(1150,1215),(1800,1865),(2400,2455)]:
    ax1.axvspan(a,b,color='#EF9F27',alpha=0.32,label='True anomaly window' if f else None); f=False
ax1.set_title('Anomaly Score Timeline (Autoencoder)',fontsize=12,fontweight='bold')
ax1.set_xlabel('Time (sample)'); ax1.set_ylabel('Anomaly score'); ax1.legend(fontsize=8,loc='upper right'); ax1.set_ylim(0,max(s_ae)*1.15)
for name,s,c in [('Isolation Forest',s_if,'#1D9E75'),('PCA (linear)',s_pca,'#7F77DD'),('Autoencoder',s_ae,'#185FA5')]:
    fpr,tpr,_=roc_curve(y,s); ax2.plot(fpr,tpr,lw=1.9,color=c,label=f'{name} (AUC={roc_auc_score(y,s):.3f})')
ax2.plot([0,1],[0,1],ls=':',color='#9aa0a6',lw=1); ax2.set_title('ROC Curve',fontsize=12,fontweight='bold')
ax2.set_xlabel('False Positive Rate'); ax2.set_ylabel('True Positive Rate'); ax2.legend(fontsize=8,loc='lower right')
for ax in (ax1,ax2):
    for sp in ['top','right']: ax.spines[sp].set_visible(False)
plt.tight_layout(); plt.savefig('baseline_result.png',dpi=200,bbox_inches='tight',facecolor='white'); print('fig ok')
