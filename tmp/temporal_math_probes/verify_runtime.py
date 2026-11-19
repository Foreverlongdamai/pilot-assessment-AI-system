"""Independent Decimal/direct-product audit of runtime temporal output.

Runtime functions are never used by the oracle. The existing test factory only
provides schema-valid catalog/configuration/input scaffolding.
"""
from __future__ import annotations
import copy
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import random
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from pilot_assessment.scene_assessment.calculator import evaluate

HELPER = runpy.run_path(str(ROOT / 'tests/scene_assessment/test_demo_quantification.py'))
D = lambda value: Decimal(str(value))
RNG = random.Random(16092026)
MAXERR = 0.0
CHECKED = 0

def normalized_decimal(values):
    total = sum(values)
    return [float(x / total) for x in values]

def compare(actual, expected, where):
    global MAXERR, CHECKED
    assert actual is not None, (where, 'missing output')
    err = max(abs(a-b) for a,b in zip(actual, expected))
    MAXERR = max(MAXERR, err)
    assert err < 2e-11, (where, actual, expected, err)
    CHECKED += 1

def add_process(case, taus=None):
    model = case[1]['skill_models']['flight']
    model['process_model'] = {'method':'fixed_skill_markov_v1', 'checkpoint_time_constants_s':
        {j: (taus or [5,5,5])[:] for j in model['checkpoint_models']}}
    return case

def check_case(case, name):
    model = case[1]['skill_models']['flight']
    report = evaluate(case[1], case[2], catalog=case[0])
    analysis = report['items'][0]['skill_quantification']['temporal_analysis']
    assert analysis['status'] == 'complete', (name, analysis, report.get('issues'))
    frames = case[2]['items']['flight']['frames']
    points = case[0]['items'][0]['checkpoints']
    metric_specs = {m['metric_id']:m for m in case[0]['metrics']}
    accum = {p['checkpoint_id']:[D(1)]*3 for p in points}
    previous = {}
    with localcontext() as ctx:
        ctx.prec = 80
        for t, frame in enumerate(frames):
            for pindex, point in enumerate(points):
                key = point['checkpoint_id']
                metric = point['metric_ids'][0]
                if frame['phase_id'] not in metric_specs[metric]['phase_ids']:
                    continue
                raw = frame['values'][metric]
                theta = model['checkpoint_models'][key]['probabilities']
                label = ('D' if raw==0 else 'U') if metric_specs[metric]['rule']=='zero_events' else ('D' if abs(raw)<=1 else 'A' if abs(raw)<=3 else 'U')
                grade = model['checkpoint_models'][key]['states'].index(label)
                tau = model['process_model']['checkpoint_time_constants_s'][key]
                likelihood = []
                for state in range(3):
                    if key not in previous or previous[key][2] != frame['phase_id']:
                        value = D(theta[state][grade])
                    else:
                        oldtime, oldgrade, _ = previous[key]
                        dt = D(frame['timestamp_s'])-D(oldtime)
                        keep = (-dt/D(tau[state])).exp()
                        # Entire transition row and direct multiplication;
                        # independent of runtime's log-domain implementation.
                        row = [keep*int(oldgrade==g)+(1-keep)*D(theta[state][g]) for g in range(len(theta[state]))]
                        value = row[grade]
                    likelihood.append(value)
                    accum[key][state] *= value
                previous[key] = (frame['timestamp_s'], grade, frame['phase_id'])
                expected = normalized_decimal([D(prior)*value for prior,value in zip(model['prior'],accum[key])])
                actual = analysis['checkpoint_traces'][pindex]['timeline'][t]['posterior']
                compare(actual, expected, (name,'cp',key,t))
            combined = []
            for state, prior in enumerate(model['prior']):
                value = D(prior)
                for cp_accum in accum.values(): value *= cp_accum[state]
                combined.append(value)
            expected = normalized_decimal(combined)
            actual = analysis['item_trace']['timeline'][t]['posterior']
            compare(actual, expected, (name,'item',t))
    return analysis

def random_cases():
    for index in range(150):
        count=RNG.randint(2,60)
        seq=''.join(RNG.choice('DAU') for _ in range(count))
        seq2=''.join(RNG.choice('DAU') for _ in range(count))
        case=add_process(HELPER['make_case'](seq,second_grades=seq2))
        model=case[1]['skill_models']['flight']
        prior=[RNG.random()+.01 for _ in range(3)]
        model['prior']=[p/sum(prior) for p in prior]
        for key,cp in model['checkpoint_models'].items():
            for s in range(3):
                row=[RNG.random()+.005 for _ in range(3)]
                cp['probabilities'][s]=[p/sum(row) for p in row]
            model['process_model']['checkpoint_time_constants_s'][key]=[10**RNG.uniform(-2,2) for _ in range(3)]
        time=0.
        for frame in case[2]['items']['flight']['frames']:
            time+=10**RNG.uniform(-3,.7)
            frame['timestamp_s']=round(time,10)
        check_case(case, f'random-{index}')

def phase_case():
    case=add_process(HELPER['make_case']('DDUAAUDDD',second_grades='AADUUDDDD'))
    item=case[0]['items'][0]
    item['phases']=[{'phase_id':p,'name':p,'single_frame':False,'required_duration_s':None,'minimum_frame_count':2} for p in ['a','b','c']]
    case[0]['metrics'][0]['phase_ids']=['a','b']
    case[0]['metrics'][1]['phase_ids']=['b','c']
    for i,frame in enumerate(case[2]['items']['flight']['frames']):
        frame['phase_id']='abc'[i//3]
        frame['values']={k:v for k,v in frame['values'].items() if frame['phase_id'] in case[0]['metrics'][int(k[1:])]['phase_ids']}
    return check_case(case,'phases-and-applicability')

def missing_case():
    case=add_process(HELPER['make_case']('DDUD',second_grades='AADD'))
    case[2]['items']['flight']['frames'][1]['values'].pop('m0')
    report=evaluate(case[1],case[2],catalog=case[0])
    analysis=report['items'][0]['skill_quantification']['temporal_analysis']
    for trace in [analysis['checkpoint_traces'][0],analysis['item_trace']]:
        assert trace['timeline'][0]['posterior'] is not None
        assert all(p['posterior'] is None for p in trace['timeline'][1:])
    assert all(p['posterior'] is not None for p in analysis['checkpoint_traces'][1]['timeline'])

def extreme_case():
    # Decimal precision > 700 evaluates cancellation in exp(-1e-628), so this
    # remains an independent direct transition calculation for tiny dt/tau.
    case=add_process(HELPER['make_case']('DU'),[1e308]*3)
    case[2]['items']['flight']['frames'][1]['timestamp_s']=1e-320
    report=evaluate(case[1],case[2],catalog=case[0])
    actual=report['items'][0]['skill_quantification']['temporal_analysis']['item_trace']['timeline'][-1]['posterior']
    with localcontext() as ctx:
        ctx.prec=750
        factor=1-(-D(1e-320)/D(1e308)).exp()
        assert factor>0
        model=case[1]['skill_models']['flight']
        expected=normalized_decimal([D(prior)*D(row[0])*factor*D(row[2]) for prior,row in zip(model['prior'],model['checkpoint_models']['cp0']['probabilities'])])
    compare(actual,expected,'extreme-underflow')

def tiny_cpt_retention_case():
    case=add_process(HELPER['make_case']('DD'),[1,2/3,.5])
    model=case[1]['skill_models']['flight']
    model['checkpoint_models']['cp0']['probabilities']=[[1e-50,.4,.6] for _ in range(3)]
    case[2]['items']['flight']['frames'][1]['timestamp_s']=40
    check_case(case,'tiny-cpt-retention')

def binary_case():
    case=add_process(HELPER['make_case']('DDUDDU',second_grades='UDDDUD'))
    case[1]['parameters'].clear()
    for metric in case[0]['metrics']:
        metric.update(rule='zero_events',value_type='integer',parameter_kind='event_count',comparison='zero')
    for checkpoint in case[1]['skill_models']['flight']['checkpoint_models'].values():
        checkpoint.update(states=['D','U'],probabilities=[[.35,.65],[.98,.02],[.999,.001]])
    check_case(case,'binary-and-transitions')

def absent_phase_case():
    case=add_process(HELPER['make_case']('DD'))
    case[0]['items'][0]['phases'].append({'phase_id':'absent','name':'absent','single_frame':True,'required_duration_s':None})
    case[0]['metrics'][0]['phase_ids'].append('absent')
    report=evaluate(case[1],case[2],catalog=case[0])
    analysis=report['items'][0]['skill_quantification']['temporal_analysis']
    assert analysis['status']=='partial'
    assert analysis['checkpoint_traces'][0]['status']=='partial'
    assert analysis['checkpoint_traces'][0]['timeline'][-1]['posterior'] is not None

def main():
    random_cases()
    phase_case()
    missing_case()
    extreme_case()
    tiny_cpt_retention_case()
    binary_case()
    absent_phase_case()
    source=ROOT/'src/pilot_assessment/scene_assessment/temporal_analysis.py'
    result={'status':'PASS','random_records':150,'compared_posteriors':CHECKED,'maximum_absolute_probability_error':MAXERR,'additional_checks':['mixed checkpoint phase applicability','phase stationary restart without prior reset','missing taints affected checkpoint and item only','dt/tau 1e-628 direct Decimal oracle','tiny CPT with nonzero retention after refresh rounds to one','binary D/U transitions','entire applicable phase missing marks CP partial and preserves prefix'],'runtime_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'oracle':'80-digit Decimal transition matrices and direct likelihood products, 750 digits for underflow case; no runtime inference helpers reused'}
    Path(__file__).with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
