from pathlib import Path

root = Path(__file__).resolve().parents[2]
guide = root / 'docs/product/SCENE_CALCULATOR_GUIDE_CN.md'
text = guide.read_text(encoding='utf-8')
text = text.replace('“后验期望”和“本帧新增证据”两张图', '“后验期望”曲线和“逐帧 D/A/U”色带')
text = text.replace('两个过程图的含义', '曲线与色带的含义')
text = text.replace('| 本帧新增证据 · log BF（高 / 低） |', '| 高级折叠明细中的 log BF（高 / 低） |')
text = text.replace('应结合本帧新增证据、实际原值和 D/A/U 查看操作变化。', '应结合逐帧色带和实际原值查看操作变化。')
text = text.replace('两图覆盖完整真实时间范围，阶段边界和缺测处断线；', '曲线和色带覆盖完整真实时间范围，阶段边界和缺测处断线；')
marker = '| 高级折叠明细中的 log BF'
at = text.index(marker)
text = text[:at] + '| 逐帧表现色带 | 绿 D、黄 A、红 U；缺失或无判定灰色，不适用与长时间空档留白。item 采用报告的当前帧综合档位：任一 U 优先；无 U 但必需观测缺失则灰；完整时取适用检查点中最差档。 |\n' + text[at:]
text = text.replace('阶段改变，或检查点经历不适用帧后，', '色块仅为逐帧显示占位，不能按其宽度解释观测时长或评分权重。已知档位不因历史缺测导致后验无效而隐藏；悬停显示最近真实帧的精确时刻、阶段和档位。\n\n阶段改变，或检查点经历不适用帧后，')
guide.write_text(text, encoding='utf-8')

generator = (root / 'tools/Generate-SupervisorDemo.py').read_text(encoding='utf-8')
for name in ['supervisor-demo-2026-09-15', 'process-model-run-2026-09-16']:
    path = root / 'examples' / name / 'README_CN.md'
    contents = path.read_text(encoding='utf-8')
    for prefix in ['先在软件运行下面的演示步骤。', '结果窗口新增“时序证据推断（累计判断）”：']:
        replacement = next(line for line in generator.splitlines() if line.startswith(prefix))
        contents = '\n'.join(replacement if line.startswith(prefix) else line for line in contents.split('\n'))
    path.write_text(contents, encoding='utf-8')

read = root / 'examples/process-model-run-2026-09-16/READ_RESULTS_CN.md'
text = read.read_text(encoding='utf-8')
text = text.replace('| 本帧新增证据 `log BF (High/Low)` |', '| 高级明细中的 `log BF (High/Low)` |')
text = text.replace('原值曲线和新增证据图', '原值曲线和逐帧 D/A/U 色带')
read.write_text(text, encoding='utf-8')
