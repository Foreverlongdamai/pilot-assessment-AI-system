import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[2]
folder = root / 'examples/supervisor-demo-2026-09-15'
before = Path(__file__).parent / 'before/supervisor-demo-2026-09-15'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))

def turns(values):
    diffs = [b-a for a, b in zip(values, values[1:]) if abs(b-a)>1e-7]
    return sum(a*b<0 for a,b in zip(diffs, diffs[1:]))

results=[]
for scene in ('SCN-001', 'SCN-002'):
    assert (folder/scene/'configuration.json').read_bytes() == (before/scene/'configuration.json').read_bytes()
    for case in ('01-proficient','02-marginal','03-unqualified'):
        old,new=[read(p/scene/f'{case}.input.json') for p in (before,folder)]
        assert old.keys()==new.keys() and old['items'].keys()==new['items'].keys()
        for key,item in new['items'].items():
            oldframes=old['items'][key]['frames']
            assert len(item['frames'])==len(oldframes)
            for a,b in zip(oldframes,item['frames']):
                assert a['timestamp_s']==b['timestamp_s'] and a['phase_id']==b['phase_id']
                assert a['values'].keys()==b['values'].keys()
                for metric,val in b['values'].items():
                    if type(val)==bool or metric.endswith(('_duration_s','_event_count')) or metric=='stop_x_m':
                        assert val==a['values'][metric]
        report=read(folder/scene/f'{case}.report.json')
        assert report['calculation_status']=='complete' and report['issues']==[]
        assert report['passed']==(case!='03-unqualified')
        for item in report['items']:
            quant=item['skill_quantification']
            if quant.get('score') is not None:
                endpoint=quant['cumulative_trace']['timeline'][-1]
                assert endpoint['score']==quant['score'] and endpoint['posterior']==quant['posterior']
        detail=read(folder/scene/f'{case}.diagnostics.json')
        result={'scene':scene,'case':case,'passed':report['passed'],
                'scores':{i['item_id']:i['skill_quantification'].get('score') for i in report['items']},
                'maximum_derivative_error_mps':max(detail['motion_checks']['central_difference_vs_exported_velocity_max_error_mps'].values())}
        if scene=='SCN-001':
            speeds=[]
            for data in (old,new):
                frames=[f for f in data['items']['A-S2-05']['frames'] if f['phase_id']=='hold']
                speeds.append([f['values']['speed_hold_airspeed_mps'] for f in frames])
            result['hold_turns_before_after']=[turns(s) for s in speeds]
            result['hold_speed_deviation_integral_m']=sum((a+b-20)*.05 for a,b in zip(speeds[-1],speeds[-1][1:]))
            assert abs(result['hold_speed_deviation_integral_m'])<1e-7
        results.append(result)
(Path(__file__).parent/'audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
