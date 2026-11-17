import json, pickle, numpy as np, resync_sim as R
fin = json.load(open('tuning.json'))['final']
d = pickle.load(open('raw.pkl','rb')); out = d['out']
# H3 check: strict priority without aging (gamma = 0)
out[('S3',200,'Pnoage')] = [R.run(200,'P',s,'S3',dict(fin,gamma=0.0)) for s in range(1,31)]
pickle.dump(d, open('raw.pkl','wb')); print('ok')
