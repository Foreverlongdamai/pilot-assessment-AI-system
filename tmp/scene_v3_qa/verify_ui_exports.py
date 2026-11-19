import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
for scene in ('SCN-001', 'SCN-002'):
    report = json.loads((root / 'tmp/scene_v3_qa' / f'{scene.lower().replace("-", "")}-ui-report.json').read_text(encoding='utf-8-sig'))
    example = root / 'examples/scenes' / scene / 'v3'
    config = json.loads((example / 'engineering-demo-configuration.json').read_text(encoding='utf-8'))
    data = json.loads((example / 'engineering-demo-input.json').read_text(encoding='utf-8'))
    assert report['configuration'] == config
    assert report['input'] == data
    assert report['calculation_status'] == 'complete'
    assert report['grade'] == 'U' and report['passed'] is False
    print(scene, 'UI export preserves full config/input; complete; U/Fail')
    for item in report['items']:
        print(item['item_id'], item['grade'])
        if item['item_id'] == 'A-S2-02':
            assert item['frame_distribution']['counts'] == {'D': 176, 'A': 20, 'U': 8}
            assert [p['grade'] for p in item['phase_results']] == ['A', 'U', 'U', 'A']
            assert all(p['observed_span_s'] == 5 for p in item['phase_results'])
print('PASS: both native UI export round trips')
