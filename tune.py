import json, itertools, numpy as np, resync_sim as R
TS = [1001,1002,1003,1004,1005]
def evalcfg(prm, N=100, method='P'):
    rs = [R.run(N, method, s, 'S3', prm) for s in TS]
    low = np.concatenate([r['rec'][r['crit']<=0.2] for r in rs])
    return dict(peak=float(np.mean([r['peak'] for r in rs])), wcost=float(np.mean([r['wcost'] for r in rs])),
                p99=float(np.mean([r['p99'] for r in rs])), succ=float(np.mean([r['success'] for r in rs])),
                low_p99=float(np.nanpercentile(low,99)), last=float(np.mean([r['last'] for r in rs])))
def pick(rows):
    feas = [x for x in rows if x[1]['peak'] <= R.C and x[1]['succ'] >= 0.99]
    pool = feas if feas else sorted(rows, key=lambda x: x[1]['peak'])[:3]
    return min(pool, key=lambda x: x[1]['wcost']), len(feas)
out = {'stage1':[], 'stage2':[], 'stage3':[]}
rows=[]
for r_,m_,b_ in itertools.product([2,3,4,5],[8,16,32],[5,15]):
    prm=dict(r=r_,m=m_,b=b_); e=evalcfg(prm); rows.append((prm,e)); out['stage1'].append([prm,e])
best,nf = pick(rows); prm1=best[0]; print('stage1 best',prm1,best[1],'feasible',nf)
rows=[]
for (a,b2,g),tau in itertools.product([(0.6,0.3,0.1),(0.5,0.3,0.2),(0.4,0.2,0.4),(0.34,0.33,0.33)],[30.0,60.0]):
    prm=dict(prm1,alpha=a,beta=b2,gamma=g,tau=tau); e=evalcfg(prm); rows.append((prm,e)); out['stage2'].append([prm,e])
# stage 2 objective: bound the p99 recovery of low-priority nodes, then minimise weighted cost
best=min(rows,key=lambda x:(x[1]['wcost']+0.2*x[1]['low_p99'])); prm2=best[0]; print('stage2 best',prm2,best[1])
rows=[]
for J in [0.0,1.0,2.0,5.0]:
    prm=dict(prm2,J=J); e=evalcfg(prm); rows.append((prm,e)); out['stage3'].append([prm,e])
best=min(rows,key=lambda x:(x[1]['peak']>R.C, x[1]['wcost'])); final=best[0]; print('final',final,best[1])
out['final']=final
json.dump(out,open('tuning.json','w'),indent=1)
