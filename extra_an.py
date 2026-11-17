import pickle, json, numpy as np
d = pickle.load(open('raw.pkl','rb')); O = d['out']
A = json.load(open('analysis.json'))
res = {}
for m in ['B3','P','A1','Pnoage','B2']:
    crit = np.concatenate([r['rec'][r['crit'] >= 0.9] for r in O[('S3',200,m)]])
    low = np.concatenate([r['rec'][r['crit'] <= 0.2] for r in O[('S3',200,m)]])
    res[m] = dict(crit_med=float(np.nanmedian(crit)), crit_p95=float(np.nanpercentile(crit,95)), low_med=float(np.nanmedian(low)), low_p95=float(np.nanpercentile(low,95)))
A['prio'] = res
json.dump(A, open('analysis.json','w'), indent=1)
print(json.dumps(res, indent=1))
print('S6 t6', json.dumps({m:(round(v['succ'][0],3), round(v['viol'][0],2), round(v['avail'][0],3), round(v['peak'][0])) for m,v in A['t6']['S6'].items()}))
print('S4', json.dumps({m:(round(v['succ'][0],3), round(v['viol'][0],2), round(v['avail'][0],3), round(v['req'][0]), round(v['peak'][0])) for m,v in A['t6']['S4'].items()}))
print('rq1 B1', {N:(round(v['peak'][0]), round(v['p99'][0]), round(v['n429'][0])) for N,v in A['rq1']['B1'].items()})
print('bytes', A['bytes'])
print('fit', A['peak_fit'])
