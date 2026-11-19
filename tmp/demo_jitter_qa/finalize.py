from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root=Path(__file__).resolve().parents[2]
folder=root/'examples/supervisor-demo-2026-09-15'
validation=folder/'VALIDATION_CN.md'
appendix='''

## 最新：连续细节波动合成输入 v2

`continuous-multiscale-demo-v2` 在慢漂移/局部失误上叠加连续细碎修正；位置与速度共享解析函数，激光保持同帧几何关系，保速细节正负面积抵消。频率与幅度是合成演示选择，未经真实飞行数据标定。新旧数据图见 SIGNAL_PREVIEW.png 和 SIGNAL_PREVIEW.svg，每个空速面板102点、悬停X面板204点，保留原值、时间和阶段。

最终重新验证：Python场景414项通过（13.96秒）；C#六例真实后端合同通过（15秒）；生成器、预览脚本和专项测试Ruff通过。新旧两份配置字节相同，六例帧数/时间戳/phase/字段集合相同，checklist、时长、禁止事件及停止X未人为抖动。中心差分与解析速度误差最大0.0154211m/s，低于原0.03限值；激光几何检查全部通过。三类保速转折从2/2/2增加到22/22/18（含小转折，非真实性指标），偏差积分绝对值均小于3e-9m。

当前六份报告均complete且无issues，每场景保持Pass/Pass/Fail；所有累计末点均等于最终后验及分数。最终数值参见SUMMARY_CN.md；此前记录中的旧分数/旧截图是历史。原生软件检查了第一轮SCN-001勉强合格的完整空速曲线，之后最终保速细节调整经六例后端合同及静态逐点图验证；SCN-002最终熟练输入实际导入评估并展开204帧位置曲线，悬停94.7/Pass。没有宣称六例都逐一原生点击。主项目完整过程记录为docs/product/reviews/2026-09-15-demo-signal-jitter-verification.md。

本次只更新演示数据及报告，无需重新构建EXE。重新导入.input.json并评估；已打开的窗口保留旧快照。软件配置、CPT及D/A边界保持原值。
'''
text=validation.read_text(encoding='utf-8')
assert '## 最新：连续细节波动合成输入 v2' not in text
validation.write_text(text+appendix,encoding='utf-8')
archive=folder.with_suffix('.zip')
backup=root/'tmp/demo_jitter_qa/before/supervisor-demo-2026-09-15.zip'
if archive.exists() and not backup.exists(): shutil.copy2(archive,backup)
files=sorted(p for p in folder.rglob('*') if p.is_file())
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in files: z.write(p,p.relative_to(folder).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist())=={p.relative_to(folder).as_posix() for p in files}
    for p in files: assert z.read(p.relative_to(folder).as_posix())==p.read_bytes()
result={'archive':str(archive),'members':len(files),'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'all_members_equal_source':True}
(root/'tmp/demo_jitter_qa/bundle-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
