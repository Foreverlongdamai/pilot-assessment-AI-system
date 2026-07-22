+++
document_id = "PAS-SESSION-001"
language = "zh-CN"
title = "Session Bundle 与原始输入接口手册"
short_title = "Session 与输入接口"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator", "expert", "developer", "maintainer"]
information_types = ["how-to", "reference", "explanation"]
scope = "说明 canonical Session Bundle、仿真器原始导入、七类物理模态、annotations、时间、单位、隐私和缺失输入行为。"
prerequisites = ["能够访问仿真器导出目录或 canonical bundle", "理解导出列与时间戳的含义"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-EVALUATOR-001", "PAS-PYTHON-EXT-001", "PAS-PORTABILITY-001"]
support = "提供不含隐私的目录树、adapter diagnostic 与 manifest 片段；禁止通过未授权渠道发送生理数据文件。"
release_channel = "release-candidate"
release_label = "v0.1.0-rc.4"
user_acceptance = "pending"
+++

# Session Bundle 与原始输入接口手册

## 1. 两种可接受来源

应用接受：

1. 带 UTF-8 `manifest.json` 的 **canonical Session Bundle**；
2. 公开有效内容只有 `streams\` 与可选 `annotations\` 的 **仿真器原始导出目录**。

仿真器不需要生成本产品的 manifest、checksums、canonical annotation 或内部 index。对于原始导出，应用只读检查来源、选择可信 adapter，在 project staging 中生成这些记录，并把接受的文件复制为受管 Session revision。外部目录保持不变。

因此 import 是 adaptation 与 provenance 过程，而不是强迫所有仿真器采用本仓库内部布局。

## 2. 为什么需要 `manifest.json`

Manifest 让进入受管存储后的 Session 可以自描述并可复现，至少记录：

- Session/contract identity 与 duration declaration；
- 每种正式模态的 descriptor；
- file paths、formats、schema IDs 与 checksums；
- clock IDs 与 source-to-session time mappings；
- units 或明确的空单位声明；
- annotation/reference descriptors；
- privacy classification 与 provenance；
- missing/export-pending/not-applicable status。

它不会发明传感器含义。自动生成 manifest 是否可靠，取决于所选 adapter 是否正确映射仿真器文件和列；导入前检查页面必须把该映射展示给用户。

## 3. 原始输入家族与物理模态

五个大圆为专家提供稳定词汇：

| Family | 物理内容 | 常见用途 |
|---|---|---|
| `X(t)` | 飞行状态：位置、速度、姿态、角速度、加速度 | 轨迹、包线与扰动响应 Evidence |
| `U(t)` | 飞行员操纵：yaw、longitudinal、lateral、heave 和设备轴 | workload、reversal、smoothness 与 control-coupling Evidence |
| `I(t)` | 随头部姿态变化、真正显示在头显中的第一视角 VR scene | 可见 scene/object/AOI context |
| `G(t)` | 动态 `I(t)` 上的 gaze ray/point、fixation/stare 与 AOI 关系 | attention allocation 与 first-fixation Evidence |
| `P(t)` | physiology 概念分组 | EEG/ECG 派生 Evidence |

Canonical manifest 声明七个物理 modality descriptors：`X`、`U`、`I`、`G`、`EEG`、`ECG` 与 `pilot_camera`。`P(t)` 是画布分组，不是含混的单一 stream key；EEG 与 ECG 分别保留采样率、单位、时钟和状态。`pilot_camera` 是独立的可选飞行员相机，不是第一视角 VR scene。

第二层细粒度 Raw Input nodes 绑定上述 family 下的具体字段/资源。Recipe 使用 typed bindings，不猜测 CSV 列位置。

## 4. 推荐物理形式

- 数值时序：优先 Parquet，也支持有明确 adapter 的 CSV；
- EEG/ECG：Parquet 或 EDF/EDF+，并用 companion metadata 补充 clock、channel/lead、unit 与 Session mapping；
- `I(t)` 与 `pilot_camera`：frame files 或 video，加带 stable frame ID 与 source timestamp 的 frame index；
- `G(t)`：包含 source timestamp、gaze origin/direction 或 viewport point、validity、关联 scene frame，以及可用 AOI/fixation 字段的表；
- `annotations`：含 stable IDs 和 time boundaries 的 task events/segments；
- `references`：所选方案需要的 commanded path 或其他 task reference。

图片和密集时序不会进入 JSON-RPC，而是保留在受管 project files 中，通过 Session/artifact identities 引用。

## 5. 各模态最小语义

### 5.1 `X(t)` 与 `U(t)`

保留 raw numeric values、timestamps、axis direction 以及任何已声明 units/normalisation。Legacy combined simulator CSV 可以把不同列映射成两个 logical streams；managed manifest 会记录 column mapping 和 physical artifact identity，避免意外复制文件。

### 5.2 `I(t)`

`I(t)` 是飞行员在 VR 中实际看到的动态第一视角图像，不是外部追踪或座舱摄像机。Frame index 应识别 image/video frame、timestamp、dimensions、head pose/FOV，以及连接 gaze 所需 calibration 或 scene metadata。Scene graph、object-ID buffer 或 AOI mask 可以作为辅助资源，但不能替代实际呈现画面。

### 5.3 `G(t)`

Gaze 必须声明 coordinate space 及其与动态 `I(t)` 的关系：viewport point、headset-relative ray 或 world/scene ray。保存 source validity 作为技术元数据，并在采集系统提供时保留 fixation/stare segments 与 AOI taxonomy。评估层不会因为 gaze 处于 off-task 区域就丢弃可解析的差表现。

### 5.4 EEG 与 ECG

应保存 raw 或 nearest-to-raw channels 和稳定元数据。EEG 声明 channels/montage；ECG 声明 lead/channel；已知时都声明 source clock 与 unit。Baseline、frequency bands 与 R-peaks 是带 provenance 的明确 derived products。极端但 finite 的值可能是有意义的负面 Evidence，不能被通用“质量”评分过滤。

### 5.5 `pilot_camera`

Pilot camera 保存脸部或上半身画面，有独立 clock 与 privacy classification。它是可选模态，不能标成 `I(t)`，任务也可以完全不使用它。

## 6. Stream status 与缺失模态

每个正式 descriptor 使用以下接口状态之一：

| Status | 含义 | 运行影响 |
|---|---|---|
| `present` | 有可读文件和完整接口声明 | 可进入 ingestion/synchronization |
| `invalid` | 文件存在，但 structural/schema/time contract 不可用 | 明确技术诊断并排除 |
| `export_pending` | 实验包含该数据，但尚未导出 | 无文件；依赖 Evidence unavailable |
| `missing` | 应有数据未采集或未提供 | 无文件；依赖 Evidence unavailable |
| `not_applicable` | 任务明确不适用该模态 | 无文件；依赖 Evidence not applicable/unavailable |

`invalid` 不是对飞行表现差或生理异常的判断。Finite poor performance 仍属于数据，应按配置方法产生差 Evidence。

只有 `X` 和 `U` 的 Session 也可以导入和评估。Active graph 会计算输入齐全的 Evidence；缺失 Evidence 保持 unavailable，并在 BN inference 中边缘化。产品不会自动阻断整个 run，也不会生成理想/合成测量来填空。

## 7. 时间戳与同步

每个 present stream 声明 source clock。同步层把 native timestamps 映射为 signed-int64 Session `t_ns`，同时保留 native rows 和稳定 duplicate-time order。它不会重写源文件，也不会把所有模态强制塞进一张 dense table。

Clock mapping 可包含 scale、offset 与 drift。共享 clock 的 streams 必须共享声明。Synchronization report 输出 coverage 与 residual diagnostics；Evidence recipes 按定义使用 deterministic aligned views 或 native-rate segments。

## 8. 单位与 undeclared values

`units` 字段始终存在，但可以为空 object。如果原始导出和可信 adapter profile 都未声明单位，importer 会保持数值不变，记录为 `undeclared-pass-through-v1`；不会要求用户猜单位、根据数值大小推断或进行隐藏换算。

固定 Evidence 方法仍可按其已记录的 adapter assumption 使用字段。Provenance 必须显示 undeclared 状态；获得真实含义后，专家应修正 adapter/profile 或方法。

## 9. 完整性、隐私与生命周期

所有 managed paths 都是 project-relative，并检查 traversal/case collision。Checksums 保护导入字节；mismatch 属于 fatal integrity error，不能降级成普通 stream status。Derived artifacts 永远不覆盖 Session Bundle。

Manifest 不应包含姓名、联系方式或无关身份字段。Gaze、EEG、ECG 与 pilot-camera 属于敏感研究数据。产品安装包不包含这些数据；每位用户自行提供和治理自己的 Session。

需要迁移已导入 Session 时，关闭应用并复制完整 project 根目录，见 [[DOC:PAS-PORTABILITY-001]]。

## 10. Adapter 扩展检查单

- [ ] external source 只读检查；
- [ ] file/column mappings 确定且可见；
- [ ] raw bytes 使用前已复制并校验 checksum；
- [ ] 每种正式模态都有明确 descriptor/status；
- [ ] timestamps/clocks 未被静默猜测；
- [ ] 未知 units 保持 undeclared；
- [ ] privacy fields 不含直接身份；
- [ ] 缺失模态不会触发产品合成数据；
- [ ] 新格式通过 adapter 实现，而不是人工一次性改写。
