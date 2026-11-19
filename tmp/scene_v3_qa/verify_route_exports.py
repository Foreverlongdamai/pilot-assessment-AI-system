import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
qa = root / 'tmp/scene_v3_qa'

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

for scene in ('SCN-001', 'SCN-002'):
    report = read(qa / f'route-{scene.lower().replace("-", "")}-ui-report.json')
    example = root / 'examples/scenes' / scene / 'v3'
    expected = read(example / 'engineering-demo-report.json')
    assert report['configuration'] == read(example / 'engineering-demo-configuration.json')
    assert report['input'] == read(example / 'engineering-demo-input.json')
    assert report['calculation_status'] == 'complete'
    assert report['grade'] == 'U' and report['passed'] is False
    for item, source in zip(report['items'], expected['items'], strict=True):
        assert item['grade'] == source['grade']
        assert item['frame_distribution'] == source['frame_distribution']
        assert item['skill_quantification']['score'] is None
    if scene == 'SCN-001':
        approach = report['items'][1]
        assert [p['checkpoint_id'] for p in approach['checkpoints']] == ['A-S2-23-01', 'A-S2-23-03']
        assert approach['grade'] == 'D' and approach['passed'] is True
        route = approach['checkpoints'][0]['metrics'][0]
        expected_route = expected['items'][1]['checkpoints'][0]['metrics'][0]
        assert len(route['timeline']) == 62
        for actual, target in zip(route['timeline'], expected_route['timeline'], strict=True):
            for key in ('timestamp_s', 'phase_id', 'value', 'deviation', 'nearest_route_point', 'route_segment_index', 'grade'):
                assert actual[key] == target[key], (key, actual[key], target[key])
    else:
        assert [item['item_id'] for item in report['items']] == ['A-S2-01', 'A-S2-02', 'SCENE-VERTICAL']
    print(scene, 'UI input/config snapshots, complete Fail/recovery and metric results verified')

draft = read(qa / 'route-partial-draft.json')['parameters']['approach_position_m']
assert draft['route_points'] == [
    {'x_m': 12.5, 'y_m': None, 'height_m': None},
    {'x_m': None, 'y_m': None, 'height_m': None},
]
assert draft['desired']['upper'] is None and draft['acceptable']['upper'] is None
assert read(qa / 'route-ui-input-template.json') == read(root / 'examples/scenes/SCN-001/v3/input-template.json')
graph = read(qa / 'route-global-ui.json')
assert len([node for node in graph if node['Id'].startswith('ModelNode_')]) == 29
assert not any('稳定进近与减速' in node['Name'] for node in graph)
print('UI partial draft, input-template and 29-node graph verified')
