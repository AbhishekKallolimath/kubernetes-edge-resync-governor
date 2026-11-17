"""Discrete-event model of reconnection storms and the Resync Governor.
Time 0 = common heal instant. All quantities in seconds / requests."""
import heapq, hashlib, math
import numpy as np

C = 1000.0        # sustainable API request rate (req/s)
LAM0 = 300.0      # background request rate (req/s)
PROBE = 20.0      # synthetic availability probes (req/s)
QMAX = 400        # server queue limit before HTTP 429
RTT = 0.04
PAR = 4           # parallel in-flight requests per agent
TOUT = 3.0        # client timeout
MAXRETRY = 8
QF, QD, QG, QV = 120, 25, 5, 2   # full / resume / failed-resume probe / verification requests
RHO = QD / QF
W_HIST = 300.0    # watch-history window (s); older outages get 410 Gone
WIN = 120.0       # measurement window after heal
SLO = 0.5
KB_FULL, KB_RES, KB_VER, KB_RETRY = 285.0, 40.0, 50.0, 1.0

METHODS = {
 #        governor  order    resume  verify retry    fallback
 'B1': (False, None,   False, False, 'fixed',  False),
 'B2': (False, None,   False, False, 'expjit', False),
 'B3': (True,  'fifo', False, False, 'expjit', True),
 'P':  (True,  'prio', True,  True,  'expjit', True),
 'A1': (True,  'fifo', True,  True,  'expjit', True),
 'A2': (True,  'prio', False, True,  'expjit', True),
 'A3': (True,  'prio', True,  False, 'expjit', True),
 'A4': (True,  'prio', True,  True,  'expjit', False),
}
DEFAULT = dict(r=4.0, b=10.0, m=32, alpha=0.5, beta=0.3, gamma=0.2, tau=60.0, J=1.0)

def digest(objs):
    return hashlib.sha256('\n'.join(sorted('|'.join(map(str, o)) for o in objs)).encode()).hexdigest()

def check_digest(inj_type, rng, nobj=40):
    """Return True if the digest comparison flags a mismatch (real SHA-256 over object tuples)."""
    D = [('Pod' if k % 2 else 'ConfigMap', 'ns', f'obj{k}', f'uid{k}', 1) for k in range(nobj)]
    O = list(D)
    k = int(rng.integers(nobj))
    if inj_type == 0: O.pop(k)                                   # deleted object
    elif inj_type == 1: O.append(('Pod', 'ns', 'extra', 'uidX', 1))   # extra object
    elif inj_type == 2: O[k] = O[k][:4] + (O[k][4] + 1,)          # stale generation
    # inj_type == 3: status-only drift -> tuples unchanged
    return digest(D) != digest(O)

class Node: pass

def run(N, method, seed, scenario='S3', prm=None, Dmix=None):
    p = dict(DEFAULT); p.update(prm or {})
    gov, order, resume_first, verify, retry, fallback = METHODS[method]
    ra = np.random.default_rng(seed * 1009 + N)      # attributes: same across methods (paired)
    rb = np.random.default_rng(seed * 7919 + 17)      # background arrivals
    rr = np.random.default_rng(seed * 104729 + hash(method) % 9973)  # behaviour randomness
    S4 = scenario == 'S4'
    T_FLAP = 240.0
    T_CUT = (T_FLAP + 120.0) if S4 else 300.0
    # ---- node attributes ----
    nodes = []
    crit_levels = ra.choice([0.9, 0.5, 0.1], size=N, p=[0.15, 0.35, 0.50])
    for i in range(N):
        n = Node(); n.id = i; n.c = float(crit_levels[i])
        n.d = float(ra.uniform(30, 600)) if Dmix is None else float(Dmix)
        n.jit = float(ra.uniform(0, 1.0)); n.w = 1 + 4 * n.c
        n.inj = int(ra.integers(4)) if ra.random() < 0.05 else -1
        n.up = True; n.epoch = 0; n.ready = None; n.pass_ = 1; n.attempt = 0
        n.bad = False; n.req = 0; n.n429 = 0; n.mode = None; n.heal_t = None; n.grant_t = None
        n.hold = False; n.gone = False; n.detected = None; n.sync_fail = 0; n.aborts = 0
        n.flaps = []
        nodes.append(n)
    # background + probes
    nb = int((LAM0 + PROBE) * T_CUT * 1.2) + 100
    arr = np.cumsum(rb.exponential(1.0 / (LAM0 + PROBE), nb)); arr = arr[arr < T_CUT]
    isprobe = rb.random(len(arr)) < PROBE / (LAM0 + PROBE)
    bg_i = 0
    st = dict(free=0.0, qpk=0.0)
    bins = np.zeros(int(T_CUT) + 3)
    lat_win = []   # latencies of accepted requests in window
    probes = [0, 0]  # ok, total
    WEND = T_CUT if S4 else WIN

    def arrive(t, agent=None):
        backlog = max(0.0, (st['free'] - t) * C)
        if t < T_CUT: bins[int(t)] += 1
        if backlog > st['qpk'] and t < WEND: st['qpk'] = backlog
        if backlog >= QMAX: return None
        st['free'] = max(st['free'], t) + 1.0 / C
        lat = st['free'] - t + RTT
        if t < WEND: lat_win.append(lat)
        return lat

    def adv_bg(t):
        nonlocal bg_i
        while bg_i < len(arr) and arr[bg_i] <= t:
            ta = arr[bg_i]; lat = arrive(ta)
            if isprobe[bg_i] and ta < WEND:
                probes[1] += 1
                if lat is not None and lat <= SLO: probes[0] += 1
            bg_i += 1

    ev = []; seq = [0]
    def push(t, typ, *a):
        seq[0] += 1; heapq.heappush(ev, (t, seq[0], typ, a))
    # governor state
    G = dict(alive=True, bucket=p['b'], active=0, queue=[], tick=False, tokens_used=0.0)
    gone_extra = [0]

    def rdelay(k):
        if retry == 'fixed': return 1.0
        return float(rr.uniform(0, min(30.0, 0.5 * 2 ** k)))

    # ---- agent logic ----
    def start_recovery(n, t):
        if not n.up or n.ready is not None: return
        if n.heal_t is None: n.heal_t = t
        if gov and G['alive']:
            push(t + float(rr.uniform(0, p['J'])) + 0.02, 'enq', n.id, n.epoch)
        elif gov and not G['alive'] and fallback:
            push(t + float(rr.uniform(0, 2.0)), 'begin', n.id, n.epoch, 'FB')
        elif gov:
            pass  # waits forever (no fallback)
        else:
            push(t, 'begin', n.id, n.epoch, 'NG')

    def begin_sync(n, t, how):
        n.grant_t = t if n.grant_t is None else n.grant_t
        if n.pass_ == 2: total = QF + (QV if verify else 0); n.mode = 'full'; n.gone = False
        elif resume_first and n.d < W_HIST: total = QD + (QV if verify else 0); n.mode = 'resume'; n.gone = False
        elif resume_first: total = QG + QF + (QV if verify else 0); n.mode = 'full'; n.gone = True
        else: total = QF + (QV if verify else 0); n.mode = 'full'; n.gone = False
        n.total = total; n.done = 0; n.fresh = total
        for _ in range(min(PAR, total)):
            n.fresh -= 1; issue(n, t, 0)

    def issue(n, t, k):
        if not n.up: return
        n.req += 1
        lat = arrive(t)
        if lat is None: n.n429 += 1; push(t + RTT, 'resp', n.id, n.epoch, False, k)
        elif lat > TOUT: push(t + TOUT, 'resp', n.id, n.epoch, False, k)
        else: push(t + lat, 'resp', n.id, n.epoch, True, k)

    def release(n, outcome, t):
        if gov and n.hold:
            n.hold = False; G['active'] -= 1
            if outcome == 'GONE': G['bucket'] -= (1 - RHO)

    def finish(n, t, outcome):
        n.ready = t
        release(n, 'GONE' if n.gone else 'OK', t)

    def sync_done(n, t):
        if n.pass_ == 1 and n.inj >= 0: n.bad = True
        if verify and n.bad:
            mism = check_digest(n.inj, rr)
            if n.detected is None: n.detected = bool(mism)
            if mism:
                n.bad = False; n.pass_ = 2
                release(n, 'GONE' if n.gone else 'OK', t); n.epoch += 1
                if gov and G['alive']: push(t + 1.0, 'enq', n.id, n.epoch)
                elif gov and fallback: push(t + 1.0, 'begin', n.id, n.epoch, 'FB')
                return
        finish(n, t, 'OK')

    def sync_fail(n, t):
        n.sync_fail += 1; n.epoch += 1; n.attempt += 1
        release(n, 'FAIL', t)
        d = float(rr.uniform(0, min(30.0, 1.0 * 2 ** n.attempt)))
        if gov and G['alive']: push(t + d, 'enq', n.id, n.epoch)
        elif gov and fallback: push(t + d, 'begin', n.id, n.epoch, 'FB')
        elif not gov: push(t + d, 'begin', n.id, n.epoch, 'NG')

    def score(n, t, enq):
        if order == 'fifo': return -enq
        return p['alpha'] * n.c + p['beta'] * min(1.0, n.d / p['tau']) + p['gamma'] * (t - enq) / p['tau']

    def tick(t):
        G['tick'] = False
        if not G['alive']: return
        G['bucket'] = min(p['b'], G['bucket'] + p['r'] * 0.1)
        q = G['queue']
        while q and G['active'] < p['m']:
            cost = RHO if (resume_first and nodes[q[0][0]].pass_ == 1) else 1.0
            # choose best by score
            best = max(range(len(q)), key=lambda j: score(nodes[q[j][0]], t, q[j][1]))
            n = nodes[q[best][0]]
            cost = RHO if (resume_first and n.pass_ == 1) else 1.0
            if G['bucket'] < cost: break
            q.pop(best)
            G['bucket'] -= cost; G['active'] += 1; n.hold = True
            push(t + 0.02, 'begin', n.id, n.epoch, 'GR')
        if q and not G['tick']:
            G['tick'] = True; push(t + 0.1, 'tick')

    # ---- initial events ----
    for n in nodes:
        push(n.jit, 'heal', n.id)
    if scenario == 'S6':
        push(5.0, 'kill')
    if S4:
        for n in nodes:
            t = n.jit
            while t < T_FLAP:
                up = float(ra.uniform(10, 30)); dn = float(ra.uniform(10, 30))
                if t + up >= T_FLAP: break
                push(t + up, 'down', n.id); push(t + up + dn, 'up', n.id, dn)
                t += up + dn

    # ---- main loop ----
    while ev:
        t, _, typ, a = heapq.heappop(ev)
        if t > T_CUT: break
        adv_bg(t)
        if typ == 'heal': start_recovery(nodes[a[0]], t)
        elif typ == 'enq':
            n = nodes[a[0]]
            if a[1] != n.epoch or not n.up or n.ready is not None: continue
            if not G['alive']:
                if fallback: push(t, 'begin', n.id, n.epoch, 'FB')
                continue
            G['queue'].append((n.id, t))
            if not G['tick']: G['tick'] = True; push(t + 0.1, 'tick')
        elif typ == 'tick': tick(t)
        elif typ == 'begin':
            n = nodes[a[0]]
            if a[1] != n.epoch or not n.up or n.ready is not None: continue
            begin_sync(n, t, a[2])
        elif typ == 'resp':
            n = nodes[a[0]]
            if a[1] != n.epoch or not n.up: continue
            if a[2]:
                n.done += 1
                if n.done == n.total: sync_done(n, t)
                elif n.fresh > 0: n.fresh -= 1; issue(n, t, 0)
            else:
                if a[3] + 1 > MAXRETRY: sync_fail(n, t)
                else: push(t + rdelay(a[3] + 1), 'retry', n.id, n.epoch, a[3] + 1)
        elif typ == 'retry':
            n = nodes[a[0]]
            if a[1] != n.epoch or not n.up: continue
            issue(n, t, a[2])
        elif typ == 'kill':
            G['alive'] = False
            if fallback:
                for (i, enq) in G['queue']:
                    push(t + 6.0 + float(rr.uniform(0, 2.0)), 'begin', i, nodes[i].epoch, 'FB')
            G['queue'] = []
        elif typ == 'down':
            n = nodes[a[0]]; n.up = False; n.epoch += 1; n.aborts += 1
            if n.ready is None: pass
            n.ready = None; n.pass_ = 1; n.attempt = 0
            if n.hold: n.hold = False; G['active'] -= 1
            G['queue'] = [(i, e) for (i, e) in G['queue'] if i != n.id]
            n.bad = False
        elif typ == 'up':
            n = nodes[a[0]]; n.up = True; n.d = a[1]; n.heal_t = t; n.grant_t = None
            start_recovery(n, t)
    adv_bg(min(T_CUT, WEND))
    # ---- metrics ----
    hi = int(WEND) + 1
    peak = float(bins[:hi].max()); lat = np.array(lat_win) if lat_win else np.array([0.0])
    rec = np.array([ (n.ready - (n.heal_t if not S4 else n.heal_t)) if n.ready is not None else np.nan for n in nodes])
    if not S4:
        rec = np.array([(n.ready - n.jit) if n.ready is not None else np.nan for n in nodes])
    ok = ~np.isnan(rec)
    viol = sum(1 for n in nodes if n.ready is not None and n.bad)
    inj_total = sum(1 for n in nodes if n.inj >= 0)
    det = [(n.inj, n.detected) for n in nodes if n.inj >= 0 and n.detected is not None]
    req_total = sum(n.req for n in nodes)
    n_res = sum(1 for n in nodes if n.mode == 'resume'); n_full = sum(1 for n in nodes if n.mode == 'full')
    retries = req_total - sum(n.total for n in nodes if hasattr(n, 'total'))
    kb = n_res * KB_RES + n_full * KB_FULL + (sum(1 for n in nodes if hasattr(n,'total') and verify) * KB_VER) + max(0, retries) * KB_RETRY
    return dict(N=N, method=method, seed=seed, scenario=scenario, peak=peak, p99=float(np.percentile(lat, 99) * 1000),
                qpeak=st['qpk'], n429=sum(n.n429 for n in nodes), avail=(probes[0] / probes[1] if probes[1] else float('nan')),
                rec=rec, crit=np.array([n.c for n in nodes]), w=np.array([n.w for n in nodes]), d=np.array([n.d for n in nodes]),
                success=float(ok.mean()), viol=viol, inj=inj_total, det=det, req=req_total, kb=kb, n_res=n_res, n_full=n_full,
                last=float(np.nanmax(rec)) if ok.any() else float('nan'), sync_fail=sum(n.sync_fail for n in nodes),
                aborts=sum(n.aborts for n in nodes),
                wcost=float(np.mean(np.where(ok, rec, T_CUT) * np.array([n.w for n in nodes]))))
