import pickle, json, numpy as np
from scipy import stats
import resync_sim as R
d = pickle.load(open('raw.pkl','rb')); O = d['out']; prm = d['params']
rng = np.random.default_rng(0)
def col(key, f): return np.array([f(r) for r in O[key]])
def ms(x, k=1): return (float(np.mean(x)), float(np.std(x, ddof=1)))
def boot_ci(a, b, n=4000):  # CI of mean percent change of a vs b (paired)
    idx = rng.integers(0, len(a), (n, len(a)))
    v = (a[idx].mean(1) / b[idx].mean(1) - 1) * 100
    return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))
def cliff(a, b):
    a = np.asarray(a); b = np.asarray(b)
    gt = (a[:, None] > b[None, :]).sum(); lt = (a[:, None] < b[None, :]).sum()
    return float((gt - lt) / (len(a) * len(b)))
def wil(a, b):
    try: return float(stats.wilcoxon(a, b).pvalue)
    except Exception: return 1.0
def holm(ps):
    o = np.argsort(ps); m = len(ps); adj = np.empty(m); run = 0
    for rank, i in enumerate(o):
        run = max(run, (m - rank) * ps[i]); adj[i] = min(1.0, run)
    return adj.tolist()
A = {'params': prm}
NS = [5, 10, 20, 50, 100, 200]; M4 = ['B1', 'B2', 'B3', 'P']
# ---- RQ1: storm severity vs N ----
A['rq1'] = {m: {N: dict(peak=ms(col(('S3',N,m), lambda r: r['peak'])), p99=ms(col(('S3',N,m), lambda r: r['p99'])),
            n429=ms(col(('S3',N,m), lambda r: r['n429'])), avail=ms(col(('S3',N,m), lambda r: r['avail'])),
            qpeak=ms(col(('S3',N,m), lambda r: r['qpeak']))) for N in NS} for m in M4 + ['A2']}
# ---- RQ2: Table V at N=200 ----
tv = {}; comps = []; ps = []
for m in M4:
    tv[m] = dict(peak=ms(col(('S3',200,m), lambda r: r['peak'])), p99=ms(col(('S3',200,m), lambda r: r['p99'])),
                 qpeak=ms(col(('S3',200,m), lambda r: r['qpeak'])), n429=ms(col(('S3',200,m), lambda r: r['n429'])),
                 req=ms(col(('S3',200,m), lambda r: r['req'])), avail=ms(col(('S3',200,m), lambda r: r['avail'])))
P_peak = col(('S3',200,'P'), lambda r: r['peak'])
for m in ['B1','B2','B3']:
    b = col(('S3',200,m), lambda r: r['peak'])
    chg = (P_peak.mean()/b.mean()-1)*100; ci = boot_ci(P_peak, b); p = wil(P_peak, b)
    comps.append(dict(vs=m, chg=float(chg), ci=ci, p=p, delta=cliff(P_peak, b))); ps.append(p)
adj = holm(ps)
for c, a_ in zip(comps, adj): c['p_holm'] = a_
A['tableV'] = tv; A['h1'] = comps
# p99 latency comparisons
A['h1_p99'] = []
for m in ['B1','B2','B3']:
    a = col(('S3',200,'P'), lambda r: r['p99']); b = col(('S3',200,m), lambda r: r['p99'])
    A['h1_p99'].append(dict(vs=m, chg=float((a.mean()/b.mean()-1)*100), ci=boot_ci(a,b), p=wil(a,b), delta=cliff(a,b)))
# ---- RQ3: recovery time ----
def pooled(key, mask=None):
    xs = []
    for r in O[key]:
        x = r['rec'].copy(); 
        if mask == 'low': x = x[r['crit'] <= 0.2]
        xs.append(x)
    return np.concatenate(xs)
def pct(x, q): x = x[~np.isnan(x)]; return float(np.percentile(x, q))
rt = {}
for m in M4 + ['A1', 'A2', 'A3', 'Pnoage']:
    k = ('S3',200,m); x = pooled(k); lo = pooled(k, 'low')
    rt[m] = dict(median=pct(x,50), p95=pct(x,95), p99=pct(x,99), last=ms(col(k, lambda r: r['last'])), low_p99=pct(lo,99), low_median=pct(lo,50),
                 med_runs=col(k, lambda r: np.nanmedian(r['rec'])), succ=ms(col(k, lambda r: r['success'])), low_max=ms(col(k, lambda r: np.nanmax(r['rec'][r['crit']<=0.2]))))
A['rt'] = {m: {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in d_.items()} for m, d_ in rt.items()}
def pc(a, b): return float((a.mean()/b.mean()-1)*100)
mP, mB2, mA2 = rt['P']['med_runs'], rt['B2']['med_runs'], rt['A2']['med_runs']
A['h2'] = dict(P_vs_B2=dict(chg=pc(mP,mB2), ci=boot_ci(mP,mB2), p=wil(mP,mB2), delta=cliff(mP,mB2)),
               A2_vs_B2=dict(chg=pc(mA2,mB2), ci=boot_ci(mA2,mB2), p=wil(mA2,mB2), delta=cliff(mA2,mB2)),
               P_vs_B1=dict(chg=pc(mP,rt['B1']['med_runs']), ci=boot_ci(mP,rt['B1']['med_runs']), p=wil(mP,rt['B1']['med_runs'])))
# per-N median recovery P vs B2 and A2 vs B2
A['h2_byN'] = {}
for N in NS:
    f = lambda m: col(('S3',N,m), lambda r: np.nanmedian(r['rec']))
    A['h2_byN'][N] = {m: float(np.mean(f(m))) for m in ['B1','B2','B3','A2','P']}
    A['h2_byN'][N]['A2_vs_B2_pct'] = pc(f('A2'), f('B2')); A['h2_byN'][N]['P_vs_B2_pct'] = pc(f('P'), f('B2'))
# H3
lowP = col(('S3',200,'P'), lambda r: np.nanpercentile(r['rec'][r['crit']<=0.2], 99))
lowNA = col(('S3',200,'Pnoage'), lambda r: np.nanpercentile(r['rec'][r['crit']<=0.2], 99))
lowA1 = col(('S3',200,'A1'), lambda r: np.nanpercentile(r['rec'][r['crit']<=0.2], 99))
lowB3 = col(('S3',200,'B3'), lambda r: np.nanpercentile(r['rec'][r['crit']<=0.2], 99))
A['h3'] = dict(P=ms(lowP), noage=ms(lowNA), A1=ms(lowA1), B3=ms(lowB3),
               P_vs_noage=dict(chg=pc(lowP,lowNA), ci=boot_ci(lowP,lowNA), p=wil(lowP,lowNA)),
               P_vs_A1=dict(chg=pc(lowP,lowA1), ci=boot_ci(lowP,lowA1), p=wil(lowP,lowA1)))
# H4: detection and overhead
det = {}
for tname, tid in [('deleted',0),('extra',1),('stale_gen',2),('status_only',3)]:
    tot = 0; hit = 0
    for r in O[('S3',200,'P')] + O[('S3',100,'P')] + O[('S3',50,'P')]:
        for (ty, dd) in r['det']:
            if ty == tid: tot += 1; hit += int(bool(dd))
    det[tname] = (hit, tot)
A['h4'] = dict(det=det, P_vs_A3=dict(chg=pc(mP, rt['A3']['med_runs']), ci=boot_ci(mP, rt['A3']['med_runs']), p=wil(mP, rt['A3']['med_runs']), delta=cliff(mP, rt['A3']['med_runs'])),
               P_vs_A3_last=dict(chg=pc(col(('S3',200,'P'), lambda r: r['last']), col(('S3',200,'A3'), lambda r: r['last']))))
# ---- RQ4: consistency & availability tables ----
t6 = {}
for sc, N, key in [('S3',200,'S3'), ('S4',50,'S4'), ('S6',200,'S6')]:
    t6[sc] = {}
    for m in M4 + (['A4'] if sc == 'S6' else []):
        k = (key, N, m)
        t6[sc][m] = dict(succ=ms(col(k, lambda r: r['success'])), viol=ms(col(k, lambda r: r['viol'])), inj=ms(col(k, lambda r: r['inj'])),
                         avail=ms(col(k, lambda r: r['avail'])), n429=ms(col(k, lambda r: r['n429'])), aborts=ms(col(k, lambda r: r['aborts'])),
                         req=ms(col(k, lambda r: r['req'])), peak=ms(col(k, lambda r: r['peak'])), last=ms(col(k, lambda r: r['last'] if r['last']==r['last'] else 0)))
A['t6'] = t6
# ---- scalability + model ----
sc = {}
for m in M4:
    sc[m] = {N: dict(peak=ms(col(('S3',N,m), lambda r: r['peak'])), last=ms(col(('S3',N,m), lambda r: r['last']))) for N in NS}
A['scal'] = sc
model = {}
r_, m_, J = prm['r'], prm['m'], prm['J']
for N in NS:
    runs = O[('S3',N,'P')]
    # mean sync duration s_bar: unknown per node in output -> use mean recovery minus mean wait approx; recompute from rec of low-queue run (N=5)
    model[N] = None
base = O[('S3',5,'P')]
# s_bar: per-node sync duration when the queue is short (N=5): recovery minus jitter/tick overhead; use mean(rec) at N=5 minus J/2
s_bar = float(np.mean(np.concatenate([r['rec'] for r in base])) - J/2)
for N in NS:
    runs = O[('S3',N,'P')]
    cbar = float(np.mean([ (r['n_res']*R.RHO + r['n_full']*1.0 + 0.0)/N for r in runs ]))
    paper = max(N/r_, N*s_bar/m_) + J
    refined = max(N*cbar/r_, N*s_bar/m_) + J
    meas = float(np.mean([r['last'] for r in runs]))
    model[N] = dict(paper=paper, refined=refined, meas=meas, cbar=cbar, err_paper=(paper-meas)/meas*100, err_ref=(refined-meas)/meas*100)
A['model'] = dict(by_N=model, s_bar=s_bar,
                  mape_paper=float(np.mean([abs(v['err_paper']) for v in model.values()])), mape_ref=float(np.mean([abs(v['err_ref']) for v in model.values()])))
# fits peak vs N (linear on N>=20)
fit = {}
for m in M4:
    xs = np.array([N for N in NS if N >= 20]); ys = np.array([sc[m][N]['peak'][0] for N in xs])
    sl, ic = np.polyfit(xs, ys, 1); fit[m] = (float(sl), float(ic))
A['peak_fit'] = fit
# ---- ablations ----
ab = {}
def rowfor(key):
    return dict(peak=ms(col(key, lambda r: r['peak'])), p95=float(np.nanpercentile(pooled(key), 95)), viol=ms(col(key, lambda r: r['viol'])),
                succ=ms(col(key, lambda r: r['success'])), p99lat=ms(col(key, lambda r: r['p99'])))
for nm, key in [('P',('S3',200,'P')), ('A1',('S3',200,'A1')), ('A2',('S3',200,'A2')), ('A3',('S3',200,'A3')), ('Pnoage',('S3',200,'Pnoage')), ('P_S6',('S6',200,'P')), ('A4_S6',('S6',200,'A4'))]:
    ab[nm] = rowfor(key)
A['ablation'] = ab
# ---- bytes ----
by = {}
for m in M4:
    runs = O[('S3',200,m)]
    by[m] = dict(kb_node=ms(np.array([r['kb']/200 for r in runs])), res_share=float(np.mean([r['n_res']/200 for r in runs])), full_share=float(np.mean([r['n_full']/200 for r in runs])))
A['bytes'] = by
# ---- S2 / small N ----
s2 = {}
for D in [30,120,600]:
    s2[D] = {m: ms(col(('S2',D,m), lambda r: r['rec'][0])) for m in ['B1','A2','P']}
A['s2'] = s2
json.dump(A, open('analysis.json','w'), indent=1, default=float)
print(json.dumps({k: A[k] for k in ['h1','h2','h3','h4']}, indent=1, default=float)[:4000])
print('tableV', {m: (round(v['peak'][0]), round(v['p99'][0]), round(v['n429'][0])) for m, v in tv.items()})
print('rt', {m: (round(v['median'],1), round(v['p95'],1), round(v['p99'],1), round(v['low_p99'],1)) for m, v in rt.items()})
print('t6', json.dumps(t6, default=float)[:3000])
print('model', {N: (round(v['paper'],1), round(v['refined'],1), round(v['meas'],1)) for N, v in model.items()}, A['model']['mape_paper'], A['model']['mape_ref'])
print('ab', {k: (round(v['peak'][0]), round(v['p95'],1), round(v['viol'][0],2), round(v['succ'][0],3)) for k, v in ab.items()})
print('s2', s2); print('h2byN', A['h2_byN'])
