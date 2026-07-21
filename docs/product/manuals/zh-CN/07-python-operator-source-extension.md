+++
document_id = "PAS-PYTHON-EXT-001"
language = "zh-CN"
title = "Python Operator 与源码扩展开发手册"
short_title = "Python 扩展手册"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["expert", "developer", "maintainer"]
information_types = ["tutorial", "how-to", "reference"]
scope = "说明如何编辑或扩展一套已解压软件副本中真正运行的 first-party Python source。"
prerequisites = ["M8B portable product layout", "能够阅读和编辑 Python"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-PYTHON-CORE-001", "PAS-RELEASE-001"]
support = "报告故障时使用 Diagnostics workspace 与产品内 logs。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# Python Operator 与源码扩展开发手册

## 1. 先判断是否需要改 Python

普通专家工作应直接在 Windows 前端完成：

- 修改 Evidence parameters、windows、thresholds 与 scorer settings；
- 把现有 operators 组合成不同 EvidenceRecipe；
- 新增或复制 Evidence/BN nodes；
- 修改 fixed parents、states、CPT 与 task activation；
- 保存或放弃 staged system-model edit session。

只有 installed operator catalog 无法表达真正的新计算机制时才编辑 Python。重启应用后，Python 修改会作用于该已解压软件副本打开的所有 project，而不是只属于某个 project。

## 2. 识别 live paths

以解压后的产品根目录为起点：

```text
backend/src/pilot_assessment/                     当前运行的 first-party Python source
backend/src/pilot_assessment/evidence/builtins/   内置 operator implementations
backend/src/pilot_assessment/evidence/extensions/ 普通源码 extension 入口
backend/src/pilot_assessment/evidence/registry.py 共享 trusted registry
backend/pyproject.toml                             runtime dependency declarations
backend/uv.lock                                    resolved dependency lock
runtime/python/python.exe                          私有 Python interpreter
runtime/site-packages/                             私有 third-party packages
developer/examples/operator-extension/            可复制工程示例
developer/tools/manage_python_dependencies.ps1    私有依赖管理脚本
developer/tools/uv.exe                             随包 dependency resolver
```

产品没有隐藏的 first-party wheel、project-level source overlay、plugin marketplace 或 fallback implementation。`backend/src/pilot_assessment` 就是唯一 active source tree。

## 3. 关闭进程并保留可恢复副本

1. 关闭由根目录 `PilotAssessment.exe` 启动的桌面应用，等待 `app/PilotAssessment.Desktop.exe` 与其 `runtime/python/python.exe` 子进程停止；
2. 保留原始 ZIP，或把整个已解压产品目录复制到新位置；
3. 不要只复制 project，因为 project 本来就不拥有 Python source 或 system model library。

Sidecar 运行期间发生源代码修改会被检测为 `runtime.restart_required`。重启前禁止新 run，从而防止 RunSnapshot 声称使用了实际未加载的磁盘字节。

## 4. 从可复制示例开始

先直接运行示例，不进行安装：

```powershell
.\runtime\python\python.exe -I -B -X utf8 `
  .\developer\examples\operator-extension\test_example_scalar_offset.py
```

预期结果是一个 standard-library test 通过。该示例不会自动进入 starter model。

复制实现：

```powershell
Copy-Item `
  .\developer\examples\operator-extension\example_scalar_offset.py `
  .\backend\src\pilot_assessment\evidence\extensions\example_scalar_offset.py
```

然后编辑 `backend/src/pilot_assessment/evidence/extensions/__init__.py`：

```python
from pilot_assessment.evidence.extensions.example_scalar_offset import (
    register_example_scalar_offset,
)


def register_extension_operators(registry: OperatorRegistry) -> None:
    register_example_scalar_offset(registry)
```

显式 import 与 call 就是完整注册机制。重启时使用与 built-ins 相同的 composition root。重复 `(operator_id, implementation_version)` 会明确失败，不会覆盖已有实现。

## 5. Operator 的组成

Extension module 提供两个 identity 完全一致的对象：

1. `OperatorDefinition`：声明 identity、ports、parameter JSON Schema、UI hints、trace capability 与 implementation reference；
2. implementation object：暴露相同 `operator_id`、`implementation_version` 与 `implementation_ref`，并实现 `execute(inputs, parameters, context)`。

设置 `implementation_source=OperatorImplementationSource.TRUSTED_EXTENSION`。Definition 与 implementation identity 必须逐项一致。

通用前端读取：

- `name` 与 `description`：operator menu 和 node detail；
- `input_ports` 与 `output_ports`：recipe connections；
- `parameter_schema`：validation 与 field types；
- `parameter_ui`：labels、groups、control hints、help text 与 units；
- `pseudocode`：可读计算摘要。

普通表单支持 numbers、integers、strings、booleans、enums、arrays 与 objects。旧或不支持的 JSON 会只读保留，不会静默丢失。正常 schema-driven extension 不需要新增 C# switch 或 operator-specific page。

对于相同 frozen inputs 与 parameters，应保持 deterministic execution。返回 mapping keys 必须与 declared output ports 完全一致；无效输入应抛出明确异常，不能返回看似合理的 fallback number。

## 6. 在 EvidenceRecipe 中使用 operator

重启后：

1. 打开 Model Studio 与一个 Evidence node window；
2. 打开该节点的 EvidenceRecipe graph；
3. 从 operator catalog 添加新 operator；
4. 连接 compatible input/output ports；
5. 选择 operator node，修改 schema-generated parameters；
6. 使用一个小型代表性 Session preview；
7. 关闭主窗口并选择“保存全部并关闭”提交 staged model edits。

注册只表示机制可用，不会自动增加 Evidence 节点、启用任务或修改 Hover starter scheme。

## 7. 增删 third-party dependency

修改依赖前关闭应用。Helper 只使用随产品提供的 uv 与 private runtime，不使用 system Python 或 global PATH：

```powershell
# 查看 private runtime 实际可见包
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 list

# 增加 direct dependency，更新 lock 并同步 private site-packages
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 add "package-name>=1,<2"

# 删除 direct dependency 并重新同步
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 remove "package-name"

# 从 frozen lock 重建 runtime/site-packages
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 sync
```

`add`/`remove` 需要 package-index access；`list` 可离线执行；`sync` 只有在 uv cache 已包含所需 wheels 时才能离线。Helper 不会把 first-party `pilot_assessment` 安装为 wheel。

依赖操作后必须重启。下一次 backend identity 会包含新的 `pyproject.toml`、`uv.lock`、private dependency manifest 与 operator catalog。

## 8. Identity、historical runs 与 checksums

Diagnostics 会显示 source-tree/combined backend identity、release-baseline difference、private Python identity、installed dependency identity、operator-catalog identity 与 restart-required 状态。

新 run 会保存这些 identity，并生成包含准确 first-party source、`pyproject.toml` 与 `uv.lock` 的 content-addressed ZIP。修改 live source 不会改变任何旧 RunSnapshot 或旧 source artifact。

直接修改 source/dependency 会让 `manifest/checksums.sha256` 与原始 release baseline 不再一致；这是 provenance，不是审批失败。需要恢复时把原始 ZIP 解压到新目录，不要覆盖 user project folders。

## 9. 使用前最小验证

对于新机制，只做与其相关的检查：

1. 应用启动，Diagnostics 显示预期 modified identity；
2. operator catalog 显示新名称、ports 与 parameter form；
3. 一个小 recipe 得到预期工程示例值；
4. 一个小 assessment run 完成并记录新 source identity/artifact；
5. 旧 result 仍可原样打开。

这些检查只证明 wiring 与 reproducibility，不证明新 Evidence 方法、threshold 或 Bayesian interpretation 具有科学有效性。

## 10. 故障排查与恢复

| 现象 | 常见原因 | 处理 |
|---|---|---|
| app/sidecar 启动退出 | syntax/import error、duplicate identity 或 missing dependency | 查看 stderr/Diagnostics，修复命名文件或恢复产品副本 |
| `runtime.restart_required` | process 启动后 source/lock 改变 | 完整关闭并重开应用 |
| operator 未出现在 menu | module 存在但 register function 未导入/调用 | 检查 `evidence/extensions/__init__.py` 并重启 |
| parameter 缺失或只读 | JSON Schema/UI pointer 不支持或不匹配 | 修正 `parameter_schema` 与 `parameter_ui`，保持稳定 JSON paths |
| recipe connection 被拒绝 | port value type、cardinality、temporal semantics 或 unit 不兼容 | 修正 definition 或增加合适 conversion operator |
| dependency import 失败 | private runtime 未同步或缺少兼容 Windows/Python wheel | 执行 `sync`、选择兼容包或恢复旧副本 |
| 新旧算法需要并列 | 原地改实现会影响所有 future runs | 保留旧 operator，增加不同 operator ID/version，并由不同 EvidenceRecipe 选择 |

紧急恢复时关闭应用，把原始系统重新解压到新文件夹，再从干净副本打开现有 user project。Project 从未被封装在原始产品 ZIP 内。
