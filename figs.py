import pickle, json, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
d = pickle.load(open('raw.pkl','rb')); O = d['out']; A = json.load(open('analysis.json'))
plt.rcParams.update({'font.family':'serif','font.serif':['Liberation Serif','Times New Roman','DejaVu Serif'],'font.size':7.5,'axes.labelsize':7.5,
    'legend.fontsize':6.5,'xtick.labelsize':7,'ytick.labelsize':7,'axes.grid':True,'grid.alpha':.3})
NS = [5,10,20,50,100,200]; COL = {'B1':'#7f7f7f','B2':'#9467bd','B3':'#ff7f0e','P':'#d62728'}
LAB = {'B1':'B1 default','B2':'B2 backoff+jitter','B3':'B3 fixed-rate','P':'P Governor'}
def ci(key, f):
    x = np.array([f(r) for r in O[key]]); return x.mean(), 2.045*x.std(ddof=1)/np.sqrt(len(x))
# Fig 2
fig, ax = plt.subplots(figsize=(3.45,2.25))
for m in COL:
    mu = np.array([ci(('S3',N,m), lambda r: r['peak'])[0] for N in NS]); h = np.array([ci(('S3',N,m), lambda r: r['peak'])[1] for N in NS])
    ax.plot(NS, mu, 'o-', ms=3, c=COL[m], label=LAB[m]); ax.fill_between(NS, mu-h, mu+h, color=COL[m], alpha=.25)
ax.axhline(1000, c='k', ls=':', lw=.9); ax.text(5.2, 1030, 'sustainable rate C = 1000 req/s', fontsize=6)
ax.set_xscale('log'); ax.set_xticks(NS); ax.set_xticklabels(NS); ax.set_xlabel('Reconnecting nodes N'); ax.set_ylabel('Peak API request rate (req/s)'); ax.legend(loc='upper left', fontsize=6)
plt.tight_layout(); plt.savefig('figs/fig2.png', dpi=300); plt.close()
# Fig 3 CDF
fig, ax = plt.subplots(figsize=(3.45,2.2))
for m in COL:
    x = np.concatenate([r['rec'] for r in O[('S3',200,m)]]); x = np.sort(x[~np.isnan(x)])
    ax.plot(x, np.arange(1, len(x)+1)/len(x), c=COL[m], label=LAB[m], lw=1.3)
ax.set_xlabel('Per-node recovery time (s), N = 200'); ax.set_ylabel('CDF'); ax.legend(loc='lower right', fontsize=6)
plt.tight_layout(); plt.savefig('figs/fig3.png', dpi=300); plt.close()
# Fig 4
fig, axs = plt.subplots(1, 2, figsize=(3.5,2.2))
for m in COL:
    mu = [ci(('S3',N,m), lambda r: r['last'])[0] for N in NS]; axs[0].plot(NS, mu, 'o-', ms=2.5, c=COL[m], label=m)
mod = A['model']['by_N']
axs[0].plot(NS, [mod[str(N)]['refined'] for N in NS], 'k--', lw=1, label='model (refined)')
axs[0].plot(NS, [mod[str(N)]['paper'] for N in NS], 'k:', lw=1, label='model (N/r)')
axs[0].set_xscale('log'); axs[0].set_yscale('log'); axs[0].set_xlabel('N'); axs[0].set_ylabel('Last-node recovery (s)'); axs[0].legend(fontsize=5.2, loc='upper left')
for m in COL:
    mu = [max(ci(('S3',N,m), lambda r: r['n429'])[0], 0.5) for N in NS]; axs[1].plot(NS, mu, 'o-', ms=2.5, c=COL[m])
axs[1].set_xscale('log'); axs[1].set_yscale('log'); axs[1].set_xlabel('N'); axs[1].set_ylabel('HTTP 429 responses (log, 0 shown as 0.5)')
plt.tight_layout(); plt.savefig('figs/fig4.png', dpi=300); plt.close()
# Fig 5
fig, axs = plt.subplots(1, 2, figsize=(3.5,2.1), gridspec_kw={'width_ratios':[1.6,1]})
ms_ = list(COL); vals = [A['bytes'][m]['kb_node'][0] for m in ms_]; errs = [A['bytes'][m]['kb_node'][1] for m in ms_]
axs[0].bar(range(4), vals, yerr=errs, color=[COL[m] for m in ms_], capsize=2); axs[0].set_xticks(range(4)); axs[0].set_xticklabels(ms_); axs[0].set_ylabel('KiB per node (modelled)')
for i, v in enumerate(vals): axs[0].text(i, v+8, f'{v:.0f}', ha='center', fontsize=6.5)
rs, fs = A['bytes']['P']['res_share'], A['bytes']['P']['full_share']
axs[1].bar([0], [rs*100], color='#2ca02c', label='resume'); axs[1].bar([0], [fs*100], bottom=[rs*100], color='#1f77b4', label='full sync')
axs[1].set_xticks([0]); axs[1].set_xticklabels(['P']); axs[1].set_ylabel('Share of syncs (%)'); axs[1].legend(fontsize=6, loc='upper center', bbox_to_anchor=(0.5,1.28), ncol=1)
plt.tight_layout(); plt.savefig('figs/fig5.png', dpi=300); plt.close()
# Fig 1 architecture (single column)
fig, ax = plt.subplots(figsize=(3.45,3.5)); ax.set_xlim(0,10); ax.set_ylim(0,10.2); ax.axis('off')
def box(x,y,w,h,t,fc='#e8f0fe',ec='#1a3d7c',fs=6.5,lw=1):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.03,rounding_size=0.18',fc=fc,ec=ec,lw=lw)); ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=fs)
def arr(x1,y1,x2,y2,c='k',st='-|>'): ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle=st,mutation_scale=7,lw=.9,color=c))
ax.add_patch(FancyBboxPatch((0.2,7.7),9.6,2.3,boxstyle='round,pad=0.03',fc='#f4f4f4',ec='#555',ls='--')); ax.text(5,9.7,'Stock Kubernetes control plane',ha='center',fontsize=7,weight='bold')
box(0.5,8.0,3.2,1.2,'kube-apiserver\n(APF)'); box(4.1,8.0,2.3,1.2,'etcd'); box(6.8,8.0,2.8,1.2,'Node lifecycle\ncontroller, Leases')
ax.add_patch(FancyBboxPatch((0.2,3.6),9.6,3.6,boxstyle='round,pad=0.03',fc='#eef7ee',ec='#2e7d32',ls='--')); ax.text(5,6.9,'Resync Governor (new)',ha='center',fontsize=7,weight='bold')
box(0.5,5.0,2.8,1.5,'Partition\ndetector',fc='#dcedc8',ec='#2e7d32'); box(3.6,5.0,2.9,1.5,'Priority queue\nS$_i$ = αc+βd+γu',fc='#dcedc8',ec='#2e7d32'); box(6.8,5.0,2.8,1.5,'Token bucket (r, b)\n+ cap m',fc='#dcedc8',ec='#2e7d32')
box(3.6,3.85,6.0,0.9,'Consistency verifier (SHA-256 digest)',fc='#dcedc8',ec='#2e7d32',fs=6.3); box(0.5,3.85,2.8,0.9,'Metrics',fc='#eeeeee',ec='#777',fs=6.3)
ax.add_patch(FancyBboxPatch((0.2,0.2),9.6,2.9,boxstyle='round,pad=0.03',fc='#fff8e1',ec='#b8860b',ls='--')); ax.text(5,2.8,'Edge nodes 1..N (agent + Resync Gate)',ha='center',fontsize=7,weight='bold')
for k,x in enumerate([0.6,3.7,6.8]): box(x,0.5,2.6,1.7,['Agent 1\n(local workloads\nkeep running)','Agent 2','Agent N'][k],fc='#fff3c4',ec='#b8860b',fs=6.2)
arr(2.0,3.1,2.0,3.6,'#b8860b'); ax.text(2.1,3.28,'1 request grant',fontsize=5.5)
arr(5.2,3.6,5.2,3.1,'#2e7d32'); ax.text(5.35,3.28,'2 grant',fontsize=5.5,ha='left')
arr(9.9,2.0,9.9,8.4,'k'); ax.text(9.75,3.28,'3 LIST/WATCH',fontsize=5.5,ha='right')
arr(2.1,7.7,2.1,6.5,'#555','<|-|>'); ax.text(2.3,7.35,'Lease gaps',fontsize=5.5)
plt.tight_layout(pad=0.2); plt.savefig('figs/fig1.png', dpi=300); plt.close()
print('ok')
