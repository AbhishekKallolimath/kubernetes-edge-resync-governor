import json, pickle, time, numpy as np, resync_sim as R
fin = json.load(open('tuning.json'))['final']
SEEDS = list(range(1, 31)); out = {}
t0 = time.time()
def go(key, N, m, sc, seeds=SEEDS, **kw):
    out[key] = [R.run(N, m, s, sc, fin, **kw) for s in seeds]
for N in [5, 10, 20, 50, 100, 200]:
    for m in ['B1', 'B2', 'B3', 'P', 'A2']: go(('S3', N, m), N, m, 'S3')
    print('S3 N', N, round(time.time() - t0), flush=True)
for m in ['A1', 'A3']: go(('S3', 200, m), 200, m, 'S3')
for m in ['B1', 'B2', 'B3', 'P', 'A4']: go(('S6', 200, m), 200, m, 'S6')
print('S6', round(time.time() - t0), flush=True)
for m in ['B1', 'B2', 'B3', 'P']: go(('S4', 50, m), 50, m, 'S4')
print('S4', round(time.time() - t0), flush=True)
for D in [30, 120, 600]:
    for m in ['B1', 'P', 'A2']: go(('S2', D, m), 1, m, 'S3', Dmix=D)
pickle.dump(dict(out=out, params=fin), open('raw.pkl', 'wb'))
print('done', round(time.time() - t0), flush=True)
