import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
for scene in ('SCN-001', 'SCN-002'):
    report = json.loads((root / 'tmp/scene_v3_qa' / f'refined-{scene.lower().replace("-", "")}-ui-report.json').read_text(encoding='utf-8-sig'))
    example = root / 'examples/scenes' / scene / 'v3'
    assert report['configuration'] == json.loads((example / 'engineering-demo-configuration.json').read_text(encoding='utf-8'))
    assert report['input'] == json.loads((example / 'engineering-demo-input.json').read_text(encoding='utf-8'))
    assert report['calculation_status'] == 'complete'
    assert report['grade'] == 'U' and report['passed'] is False
    assert all(item['item_id'] != 'SCENE-START' for item in report['items'])
    if scene == 'SCN-001':
        approach = next(item for item in report['items'] if item['item_id'] == 'A-S2-23')
        assert approach['grade'] == 'D' and approach['passed'] is True
        assert approach['frame_distribution']['valid_frame_count'] == 93
        speed = next(metric for cp in approach['checkpoints'] for metric in cp['metrics'] if metric['metric_id'] == 'approach_airspeed_mps')
        assert speed['timeline'][0]['expected'] == 12
        assert speed['timeline'][-1]['expected'] == 0
        assert all(abs(point['deviation']) < 1e-12 for point in speed['timeline'])
    else:
        assert [item['item_id'] for item in report['items']] == ['A-S2-01', 'A-S2-02', 'SCENE-VERTICAL']
    print(scene, 'UI input/configuration snapshots match; grades and frame profiles verified')

draft = json.loads((root / 'tmp/scene_v3_qa/refined-empty-profile-draft.json').read_text(encoding='utf-8-sig'))
profiles = draft['parameters']['approach_airspeed_mps']['reference_profiles']
assert profiles == {'approach': [{'elapsed_s': 0, 'expected': None}, {'elapsed_s': None, 'expected': None}], 'approach_deceleration': []}
print('UI partial profile draft preserves empty values and empty phases')
