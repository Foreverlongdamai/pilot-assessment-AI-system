"""Read-only analytical CTMC probes; does not import or modify runtime."""
from __future__ import annotations
import json
import math
from pathlib import Path

THETA = ((.10, .25, .65), (.35, .63, .02), (.90, .099, .001))
PRIOR = (1/3, 1/3, 1/3)
SCORES = (0, 50, 100)

def transition(theta, tau, dt):
    stay = math.exp(-dt / tau)
    refresh = -math.expm1(-dt / tau)
    return [[stay * (a == b) + refresh * theta[b] for b in range(3)] for a in range(3)]

def posterior(logs):
    weights = [math.exp(x - max(logs)) for x in logs]
    den = math.fsum(weights)
    p = [x / den for x in weights]
    return p, math.fsum(x*y for x,y in zip(p, SCORES))

def infer(sequence, tau):
    logp = [math.log(x) for x in PRIOR]
    out = []
    previous = None
    for timestamp, grade in sequence:
        likelihood = [row[grade] for row in THETA] if previous is None else [transition(row, tau, timestamp-previous[0])[previous[1]][grade] for row in THETA]
        for s in range(3):
            logp[s] += math.log(likelihood[s])
        p, score = posterior(logp)
        out.append(dict(timestamp_s=timestamp, grade=grade, posterior=p, score=score, log_bf_high_middle=math.log(likelihood[2]/likelihood[1])))
        previous = (timestamp, grade)
    return out

def signal(dt, duration=60, bad_start=30, bad_end=31):
    return [(round(i*dt, 9), 2 if bad_start <= round(i*dt, 9) < bad_end else 0) for i in range(round(duration/dt))]

def multiply(a,b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def main():
    checks = []
    for theta in THETA:
        a=transition(theta,5,.07); b=transition(theta,5,.13); c=transition(theta,5,.20)
        assert max(abs(sum(row)-1) for row in c)<1e-14
        assert max(abs(sum(theta[i]*c[i][j] for i in range(3))-theta[j]) for j in range(3))<1e-14
        prod=multiply(a,b)
        assert max(abs(prod[i][j]-c[i][j]) for i in range(3) for j in range(3))<1e-14
    checks += ['row sums', 'stationary CPT', 'semigroup']
    table=[]
    for tau in (1,3,5,10,20):
        for dt in (.1,.01):
            trace=infer(signal(dt),tau)
            before=[x for x in trace if x['timestamp_s']<30][-1]
            inside=[x for x in trace if 30<=x['timestamp_s']<31]
            after=[x for x in trace if x['timestamp_s']>=31]
            table.append(dict(tau_s=tau,dt=dt,before=before['score'],bad_min=min(x['score'] for x in inside),first_recovery=after[0]['score'],final=trace[-1]['score'],first_bad_log_bf=inside[0]['log_bf_high_middle']))
    long=[]
    for duration in (60,600,3600):
        onset=duration/2
        tr=infer(signal(.1,duration,onset,onset+1),5)
        long.append(dict(duration=duration,before=[x for x in tr if x['timestamp_s']<onset][-1]['score'],bad_min=min(x['score'] for x in tr if onset<=x['timestamp_s']<onset+1),final=tr[-1]['score']))
    # Identical timestamp+grade likelihood is 1; contradictory grade impossible.
    assert all(transition(row,5,0)[1][1]==1 for row in THETA)
    assert all(transition(row,5,0)[1][2]==0 for row in THETA)
    checks.append('zero-time duplicate semantics')
    # If same-state intermediate samples added, log-likelihood approaches finite
    # residence-time likelihood, rather than growing with frame count.
    constants=[]
    for dt in (1,.1,.01,.001):
        tr=infer([(round(i*dt,9),0) for i in range(round(30/dt)+1)],5)
        constants.append(dict(dt=dt,score=tr[-1]['score'],posterior=tr[-1]['posterior']))
    # Transition count changes order-sensitive likelihood, even same grade counts.
    sequence_a=[(i*.1,g) for i,g in enumerate([0]*70+[1]*20+[2]*10)]
    sequence_b=[(i*.1,g) for i,g in enumerate(([0]*7+[1]*2+[2])*10)]
    order=[dict(name=n,score=infer(seq,5)[-1]['score']) for n,seq in [('clustered',sequence_a),('interleaved',sequence_b)]]
    result=dict(checks=checks,tau_sweep=table,long_duration_saturation=long,same_state_sampling_convergence=constants,same_counts_different_order=order,semantics='Fixed S, stationary first observation, CTMC subsequent conditional likelihood. All illustrative, uncalibrated.')
    Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
