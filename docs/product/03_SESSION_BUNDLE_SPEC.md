# Session Bundle 正式规范

**规范版本：** 0.1.0  
**文档状态：** 产品 v0 数据合同（已与 M4 no-quality-gate 边界协调）
**日期：** 2026-07-13
**上位文档：** [产品总览](./01_PRODUCT_OVERVIEW.md)

## 1. 目的

Session bundle 是一次实验／训练 session 的不可变数据交付单元。它必须同时表达：

- 已经导出的原始或派生数据；
- 已采集但尚未导出的正式模态；
- 缺失、无效或该任务不适用的模态；
- 所有文件的格式、单位、时钟和完整性；
- phase、event、baseline 和任务 reference；
- 多设备 stream 映射到统一 session 时间轴的方法和技术诊断。

Bundle 规范不规定具体 anchor 公式。它提供可复现计算所需的数据事实；anchor 和 BN 规则属于 model bundle。

本文中的“必须”表示 schema、完整性或时间合同要求；“建议”表示 v0 的推荐存储方式。M1–M3 可以记录 coverage、gap、clock residual、validity 与 artifact 等技术诊断，但这些诊断不得成为 M4 evidence admission gate，也不得改变 D/A/U likelihood。

## 2. 正式模态定义

| ID | 定义 | 与其他模态的关系 |
|---|---|---|
| X(t) | 飞行状态：位置、速度、姿态、角速度、加速度等 | 与 U(t) 和任务 reference 共同支持客观 anchor |
| U(t) | 飞行员操纵：yaw、longitudinal、lateral、heave 等 | 保留原始值、单位、方向和归一化说明 |
| I(t) | **随飞行员头部转动而变化的第一视角 VR scene**，即飞行员当时在头显内实际看到的动态画面 | 不是固定外部摄像机画面；必须能关联 frame timestamp 和 head pose |
| G(t) | **定义在动态 I(t) 画面上的 gaze ray、gaze point、fixation/stare 与 AOI** | 必须指明对应 scene frame、坐标空间、AOI taxonomy 和 validity |
| EEG(t) | 脑电通道信号及 validity／artifact 元数据 | 需要 channel metadata、设备时钟和 baseline；这些元数据在 M4 中只作 non-gating diagnostics |
| ECG(t) | 心电通道信号及 validity／artifact 元数据 | 需要 lead/channel metadata、设备时钟和 baseline；这些元数据在 M4 中只作 non-gating diagnostics |
| pilot_camera(t) | 可选的飞行员脸部／上半身相机图像 | 不是 I(t)；可用于行为检查、技术诊断或未来插件 |

P(t) 是 physiology 的概念分组，不作为含混的单一文件键；manifest 必须把 EEG、ECG 及未来生理模态分别声明，使采样率、时钟、单位、技术诊断和缺失状态可独立记录。极端生理数值属于 M4 的潜在负面表现 evidence，不得被这些诊断字段过滤。

I(t)、G(t)、EEG(t)、ECG(t) 和 pilot_camera 在当前实验中可以处于 `export_pending`：数据已采集并属于正式合同，但尚未形成可供 Assessment Core 读取的文件。

## 3. Bundle 目录

推荐结构：

    <session-id>/
      manifest.json
      streams/
        flight_state.parquet
        control_input.parquet
        vr_scene/
          scene.mp4
          frame_index.parquet
        gaze.parquet
        eeg.parquet | eeg.edf
        eeg_sidecar.json              # EDF 时可选/按设备要求
        ecg.parquet | ecg.edf
        ecg_sidecar.json              # EDF 时可选/按设备要求
        pilot_camera/
          pilot.mp4
          frame_index.parquet
      annotations/
        phases.json
        events.json
        baseline_intervals.json
      references/
        commanded_path.parquet
      integrity/
        checksums.sha256

Bundle 可以是目录或 zip。Zip 解压和路径解析必须防止绝对路径、`..` 和符号链接逃逸。Manifest 中所有路径均为 bundle root 下的 POSIX-style 相对路径。

### 3.1 推荐格式

- 表格／时序：Parquet，保留 schema 和数值类型；
- 兼容输入：CSV，由 adapter 和 manifest column mapping 明确解释；
- EEG/ECG 原始设备文件：EDF/EDF+；用 manifest 或 companion sidecar 补充设备时钟、通道、单位、事件和 session 时间映射；
- 视频：MP4 加独立 frame index；
- 图像序列：稳定 frame ID，加 frame index；
- annotations：JSON；
- 大型原始文件可使用受控外部引用，但必须声明 URI 类型、访问范围和 checksum。可移植导出时应打包为内部相对路径。

## 4. Manifest 顶层 schema

`manifest.json` 必须是 UTF-8 JSON object，至少包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `bundle_schema_version` | string | 本规范 semantic version |
| `session_id` | string | 在 project 范围内唯一且稳定 |
| `created_at` | RFC 3339 string | Bundle 创建时间 |
| `source_session` | object | 实验系统、原始 session ID 和采集批次 |
| `participant` | object | 仅含 pseudonymous ID 和允许的研究属性 |
| `task` | object | task profile、scenario、reference 和期望 phase |
| `session_timebase` | object | 统一 `t_ns` 定义和 master clock |
| `streams` | object | 所有正式模态的 StreamDescriptor |
| `annotations` | object | phase、event、baseline 路径和 revision |
| `integrity` | object | checksum algorithm 和清单 |
| `privacy` | object | 数据级别、脱敏和访问说明 |

未知扩展字段必须放在 `extensions` 下。Reader 遇到同一 major version 内不认识的可选字段时可以保留并忽略；遇到不支持的 major version 必须拒绝运行。

## 5. StreamDescriptor

每个正式模态都必须在 `streams` 中出现，即使尚未导出。Descriptor 至少包含：

| 字段 | 说明 |
|---|---|
| `modality` | X、U、I、G、EEG、ECG 或 pilot_camera |
| `status` | 正式状态枚举 |
| `required_for_import` | 缺少该 stream 是否阻止 bundle import |
| `paths` | 一个或多个相对路径；未导出时为空数组 |
| `format` | parquet、csv、edf、edf+sidecar、mp4+frame_index、image_sequence 等 |
| `schema_id` | 字段和类型合同 |
| `clock_id` | 原始设备时钟 |
| `clock_sync` | 到 session `t_ns` 的映射及质量 |
| `sample_rate_hz` | 固定采样率；可变帧率使用 null 并依赖 timestamp |
| `units` | 字段单位或 unit profile |
| `quality_summary` | 导出时生成的 coverage、gap、validity 或 artifact 技术摘要；保留兼容字段名，但不作为 M4 evidence gate |
| `checksums` | 每个文件的 sha256 |
| `metadata` | 模态专用 metadata |

### 5.1 Stream status

| 状态 | 含义 | 运行行为 |
|---|---|---|
| `present` | 文件已导出并可验证 | 进入 adapter 和 M1–M3 schema／完整性／时间合同检查 |
| `export_pending` | 实验已采集，但当前 bundle 尚无可读导出 | 保留正式接口；相关 anchor unavailable |
| `missing` | 预期存在但未采集或已丢失 | 记录数据缺口；按 task/model 决定 partial 或 fatal |
| `invalid` | 文件存在且 integrity 可验证，但内容 schema、类型或时间合同不成立 | 禁止进入下游；给出修复诊断；不得用来描述差表现 |
| `not_applicable` | 当前任务明确不要求该模态 | 不计入缺失覆盖 |

`export_pending` 不得被 adapter 自动改写为 `missing`。

完整字段矩阵如下；`format`、`schema_id`、`clock_id`、`units` 和 `metadata` 在五种状态下始终保留，用于说明接口和修复方式：

| status | paths | checksums | clock_sync | quality_summary | required_for_import |
|---|---|---|---|---|---|
| `present` | 非空 | keys 与 paths 精确一致 | 必须 | 可选 | true/false |
| `invalid` | 非空 | keys 与 paths 精确一致 | 可选 | 可选 | true/false |
| `export_pending` | 空 | 空 | 可选，仅保留已知声明 | 必须 null | true/false |
| `missing` | 空 | 空 | 必须 null | 必须 null | true/false |
| `not_applicable` | 空 | 空 | 必须 null | 必须 null | 必须 false |

`invalid` 是 M1–M3 的接口／结构状态，表示文件路径与 checksum 完整性仍可验证，但内容 schema、类型或时间合同不可用；它不是 M4 calculation status，也不得根据轨迹、控制或生理表现数值设置。checksum mismatch 是 bundle-level fatal integrity error，不能降级成可继续使用的 invalid stream。Loader 对 `present` 和 `invalid` 文件都执行路径安全与 checksum 验证。

## 6. 统一时间轴

### 6.1 t_ns

Raw source artifact 在 M2 必须提供：

- 原始 `source_timestamp`；
- 与其 artifact role 对应的稳定 `source_index`、sample ID、frame ID 或 interval ID。

原始时间戳不可被覆盖。若源文件暂时只有 session time，也应保留该列并明确声明其时间合同。`*-raw-v0.1` 与 `*-normalized-v0.1` schema 不得为了满足下游接口而伪造 authoritative `t_ns`。M2 的 `IngestionReadinessReport` 只验证 source timestamp、稳定 ID 与 `clock_sync` 声明，不授权运行。

M3 生成的 `*-aligned-v0.1` view 必须在保留全部 raw rows/values 的前提下增加映射后的 int64 `t_ns` 与 window flags，表示相对 session origin 的时间。若原始文件已经导出同名时间列，M3 仍应根据明确的 source timestamp 和 mapping 重算并验证，而不能直接信任。只有 aligned view 的 `t_ns` 是 v0.1 后续同步权威字段。

### 6.2 Clock mapping

默认采用以下唯一映射，所有十进制输入按其 JSON/表格字符串语义解释：

`t_ns = round_half_even(Decimal(str(source_s)) × Decimal(str(scale)) × 1_000_000_000 + Decimal(offset_ns))`

其中：

- `scale` 是映射的唯一计算权威，必须大于 0；
- `offset_ns` 记录纳秒偏移；
- `drift_ppm` 只用于审计 `drift_ppm = (scale - 1) × 10^6` 的一致性，不得再次参与计算；
- `residual_rms_ms` 和 `residual_max_ms` 记录 sync marker 拟合残差；
- `sync_method` 说明硬件触发、共享时钟、事件对齐或离线拟合；
- `sync_markers` 可引用单独文件或内嵌摘要。

同一 `clock_id` 的 present logical streams 必须共享 method、scale、offset 和 drift mapping；per-stream residual 可以不同。Assessment Core 根据原始 timestamp 和 mapping 生成派生 `t_ns`，并验证 signed int64 边界、scale/drift 一致性及 same-clock declaration。重同步产生新的 report/fingerprint，不修改原文件。

### 6.3 Session window 与同步要求

Bundle schema v0.1 只支持 `session_timebase.origin=session_start`。M3 的 canonical window 为闭区间 `[0,max(mapped X primary-table t_ns)]`，其 source 固定为 `master-clock-x-mapped-coverage-v1`。X 在这里仅提供技术时间边界，不是 commanded trajectory、任务标准、表现权威或能力 ground truth。Synthetic `duration_s` 只能作 golden cross-check；未来引入显式 window 必须通过新的 schema/decision。

- 每个 stream 内 `t_ns` 必须单调非递减；重复时间戳必须有稳定 index。
- Clock mapping 的 scale、offset 和 residual 必须为有限值。
- residual、gap 和跨模态时间差由 M3 如实报告到 diagnostics/provenance，不设置通用或逐 anchor 的数据质量 admission threshold。
- Anchor-specific temporal matching、window、interpolation 或 filter recipe 属于 `AnchorExecutionPlan` 中的计算公式定义；它们决定怎样计算，不决定原始数据“够不够好”。跨模态 overlap 指标不得用来丢弃本可计算的差表现 evidence。
- M3 保留 native-rate rows，不插值、不重采样；`SynchronizationReport` 必须列出 window、覆盖起止、缺口、重复 mapped timestamp、越界 rows、丢帧、clock residual 和 `interpolated_rows=0`。

## 7. 各模态文件合同

### 7.1 X(t)：flight state

Raw/normalized X 至少包含 `source_timestamp`、稳定 `source_index` 和 task profile 所需状态字段；M3 的 `flight-state-aligned-v0.1` 追加 authoritative `t_ns` 与 `in_session`。字段必须明确：

- 坐标系和轴方向；
- earth/body frame；
- position、velocity、attitude 和 rate 的单位；
- angle convention 和 wrapping；
- derived field 是否来自原始系统。

当前 simulator CSV 可由 legacy adapter 同时映射为 X(t) 和 U(t)，但 manifest 必须记录 column mapping，且不能把 experiment condition 列当作时序传感器。

### 7.2 U(t)：control input

Raw/normalized U 至少包含各有效 control channel、`source_timestamp` 和稳定 `source_index`；M3 的 `control-input-aligned-v0.1` 追加 authoritative `t_ns` 与 `in_session`。必须声明：

- raw unit；
- sign convention；
- physical range；
- full-deflection normalization；
- deadband、saturation 和 control mode。

### 7.3 I(t)：第一视角 VR scene

I(t) 是飞行员头显内随头部姿态变化的动态第一视角画面。每个 frame index 至少包含：

- `frame_id`；
- `source_timestamp`；
- 视频 frame number 或图像相对路径；
- head pose（position 可选，orientation 必须按设备能力声明）；
- render resolution、field of view 和坐标约定；
- frame validity 和 dropped-frame 标记。

M3 的 `vr-frame-index-aligned-v0.1` 在上述原始列后追加 authoritative `t_ns` 与 `in_session`；AOI instance 通过稳定 `frame_id` 继承同一时间和 window flag。

如果 VR 系统可导出 scene graph、object ID buffer 或 AOI mask，应作为 I(t) 的辅助文件登记，但不能用它替代实际呈现给飞行员的画面。

### 7.4 G(t)：gaze、stare/fixation 与 AOI

G(t) 必须说明 gaze 是在何种空间表达，并与动态 I(t) 建立联系。Stream present 时，raw gaze 至少包含：

- `source_timestamp` 与稳定 `gaze_sample_id`；
- 左／右／融合 gaze validity；
- gaze ray origin 与 direction，或 normalized viewport point；
- `scene_frame_id`；
- blink、tracking loss 和 calibration quality。

M3 的 `gaze-sample-aligned-v0.1` 追加 authoritative `t_ns` 与 `in_session`；fixation interval 由明确的 start/end source time 映射为 start/end `t_ns` 和 window overlap/full flags。Raw gaze/fixation schema 不预先要求 aligned 字段。

fixation/stare 与 AOI 是派生表。Raw fixation 至少包含 fixation_id、start/end source timestamp、duration_ms、centroid ray/point、scene frame range、validity/confidence、AOI ID、taxonomy version 和 assignment confidence；aligned fixation 另含 start/end `t_ns` 与 window flags。原始 gaze point/ray 与派生结果必须分开保存；不得只保留烧录了注视区域的图片。

reference-model-v0.1 的 fixation_source_mode 固定为 recompute_from_raw_v1，并产生 fixation-v1 artifact：

1. 用 I(t) 的 head pose/FOV 把 viewport point 或 headset-relative ray 转成统一 scene/world unit ray；
2. 先按 t_ns 排序；重复 t_ns 按 gaze_sample_id 稳定排序并保留最后一个有效 fused/valid sample，同时记录 duplicate flag。之后只连接 delta_t_ns>0 的相邻有效 samples；gap >50 ms、blink 或 tracking loss 会切段；
3. angular_velocity_deg_s = acos(clamp(dot(ray_i,ray_i-1),-1,1)) × (180/pi) / (delta_t_ns × 1e-9)；
4. angular velocity <100 deg/s 的连续片段持续 ≥100 ms 才是 fixation；短片段为 unclassified；
5. fixation centroid 是片段 unit rays 的 normalized vector mean，起止时间取首末有效 sample。

设备若同时提供自己的 fixation，必须保留 detector_id/version/parameters；reference v0.1 仍从 raw gaze 重算。未来改用设备 detector 必须形成新的 model revision 与 golden tests。

### 7.5 EEG(t)

至少声明：

- device、channel names、electrode montage 和 reference；
- sample rate、单位和量程；
- raw/filtered/derived 状态；
- filter、notch、resampling 和 artifact pipeline 的 provenance；
- 每样本或每窗口的 quality/artifact 标记；
- baseline interval。

优先保存 raw 或最接近 raw 的数据；频带特征作为派生 stream 或 anchor result。

EEG 可以使用 Parquet 或 EDF/EDF+。使用 EDF 时，StreamDescriptor.paths 指向原始 EDF，并在 metadata 或 eeg_sidecar.json 中补齐 EDF 未可靠表达的匿名设备起始时间、clock_id、channel unit/montage、event marker 与到 session t_ns 的 clock mapping。Ingestion adapter 保留原始 EDF，只生成可缓存的内部 aligned view，不覆盖源文件。

### 7.6 ECG(t)

至少声明：

- device、lead/channel 和单位；
- sample rate；
- raw/filtered 状态；
- R-peak 或 HR 等派生数据的算法版本；
- quality/artifact 标记；
- baseline interval。

ECG 同样可以使用 Parquet 或 EDF/EDF+。EDF companion metadata 至少补齐 lead/unit、设备起始 timestamp、clock_id、event/R-peak 派生 provenance 和到 session t_ns 的映射。若导入时规范化为 Parquet，原始 EDF 及 checksum 仍必须留在 provenance 中。

### 7.7 pilot_camera(t)

pilot_camera 是可选模态，保存飞行员脸部或上半身画面。Frame index 与 I(t) 相似，但使用独立 `clock_id`、camera calibration 和 privacy classification。它不能被标记为 VR scene。

## 8. Annotations 与 task reference

M3 v0.1 明确区分两种 annotation 时间合同：M2 synthetic schema 的 `start_s`、`end_s`、`time_s` 是相对 `session_start` 的 seconds，由 M3 使用同一 Decimal round-half-even seconds→ns 规则转换，但不应用 device clock；正式 `*-session-time-v0.1` schema 直接声明 int64 `t_ns`、`start_t_ns` 或 `end_t_ns`，M3 只重验结构、window 和内部自洽性，不再次映射。Unknown schema 不得按字段名猜测时间语义。

### 8.1 phases.json

每个 phase 至少包含：

- stable phase ID；
- label；
- 按 schema 声明的 start/end source-relative seconds 或 session `t_ns`；
- annotation source：scripted、manual、detected 或 reviewed；
- revision 和 reviewer；
- confidence 或 quality。

M3 aligned phase 统一使用 `start_t_ns`/`end_t_ns`，并验证 expected phase ID/order、非重叠与 fully-in-session。Synthetic phase 通过这些结构检查仍不等于专家 phase annotation 或真实任务阶段。

### 8.2 events.json

包含 command、disturbance、critical event、envelope exit 等事件。每个事件记录 stable event_id、type、按 schema 声明的 source-relative `time_s` 或 session `t_ns`、duration（如适用）、source 和 confidence。Point event 必须位于 session window；一旦声明 duration，必须严格为正并与 window 相交。用于 O10/O11/H2 的事件还必须通过 task profile 或 event metadata 解析：

- required observation horizon；
- recovery_start_mode；
- expected_response_channels；
- 每通道 expected direction；
- response_aggregation；
- event-relevant AOI（如适用）；
- response_mapping_id 与版本。

缺少所需 mapping 时 anchor 返回 not_computable，不得让实现自行猜测响应通道或起点。

### 8.3 baseline_intervals.json

EEG/ECG normalization 所需 baseline 必须声明按 schema 解释的 start/end、条件、是否有效和 exclusion reason。M3 aligned baseline 统一使用 `start_t_ns`/`end_t_ns` 并要求 fully-in-session；M3 不判断其生理或科学适用性。

### 8.4 Commanded/reference path

O2 Peak Tracking Excursion 等 anchor 需要 commanded/reference path。来源必须明确为：

- bundle 内 `references/` 文件，由可选 `streams.task_reference` descriptor 声明；或
- model bundle 中固定的 task profile reference。

结果 provenance 必须记录实际使用的 reference hash。

Bundle-local reference 使用以下间接合同（示例只展开 reference 相关关键字段，其余 StreamDescriptor 必填字段仍按第 5 节提供），避免 `TaskReference` 与 `StreamDescriptor` 各自维护一套 checksum：

~~~json
{
  "task": {
    "reference": {
      "source": "bundle",
      "reference_id": "commanded-path-v0.1",
      "stream_id": "task_reference"
    }
  },
  "streams": {
    "task_reference": {
      "modality": "task_reference",
      "status": "present",
      "paths": ["references/commanded_path.parquet"],
      "format": "parquet",
      "schema_id": "task-reference-path-raw-v0.1",
      "checksums": {
        "references/commanded_path.parquet": "<sha256>"
      }
    }
  }
}
~~~

`source=bundle` 时 `stream_id` 必填，必须解析到 modality=`task_reference` 的 descriptor。该 descriptor 可以使用五种 stream status：`present/invalid` 的非空路径全部位于 `references/`；`export_pending/missing/not_applicable` 按第 5.1 节矩阵保持 fileless，由 readiness 与 M3 明确报告 reference 不可用或不适用。Bundle-local reference 在 M3 使用 descriptor 自身 clock 和受信 temporal binding 对齐，并单独进入 `SynchronizationReport`。

`source=model_bundle` 时禁止 `stream_id`，M3 不在 model revision 尚未锁定时猜测或读取 reference artifact，而是返回 `deferred_model_bundle_resolution`；锁定 model revision 后由 Run Preflight 根据 `reference_id` 解析 hash 与 task compatibility。该状态不是 missing/invalid。七个 core modality 清单和 per-modality coverage 都不包含 task_reference。

## 9. 合同、完整性与计算前提

### 9.1 Bundle integrity check

- Manifest 可由支持的 schema 解析；
- session ID 与 stream ID 唯一；每个物理 artifact identity 唯一；
- D-011 允许 X/U 两个逻辑 view 引用同一 canonical path，但 checksum、format、schema_id 和 shared_source_id 必须一致；其他 path sharing 与 case-fold alias 均拒绝；
- 路径不逃逸 bundle root；
- 所有 `present` 文件存在且 checksum 匹配；
- 所有正式模态均有 descriptor；
- privacy 和 participant pseudonymization 字段存在。

### 9.2 Stream structure check

- Schema、类型和单位匹配；
- timestamp 有限且次序合法；
- 声明的 sample/frame 范围与 manifest 自洽；
- gap、drop、validity 和 artifact 摘要可计算并作为 non-gating diagnostics 保留；
- `invalid` stream 因接口／结构／时间合同不成立而不得进入 M3/M4；有限但极差的表现值不得据此标记为 `invalid`。

### 9.3 Synchronization contract check

- Clock mapping 可重现；
- scale/offset/drift 声明、same-clock mapping 与 int64 结果结构合法；
- M3 报告 residual、gap、overlap 和 association metrics；这些指标进入 diagnostics/provenance，不在锁定 model revision 后变成 M4 availability 或 evidence quality gate；
- v0.1 session window 使用 `master-clock-x-mapped-coverage-v1`，point/interval 越界状态可审计；
- phase、event、baseline 分别满足其 fully-in-session、point-in-window 或 positive-duration-overlap 合同；
- M3 计算跨模态重叠范围但不判断未锁定 anchor 的专用容差；
- VR frame、head pose 和 gaze frame association 可验证。

### 9.4 M4 calculation 与 M5 assessment 前提

M4 假定输入已经通过上述接口、结构和时间合同。锁定 execution plan 后，系统逐 anchor 检查：

- required modality 是否 `present`；
- 当前任务是否适用；
- 必需 annotation/reference、公式参数和上游依赖是否存在；
- plugin、schema、unit、DAG 与 artifact recipe 是否兼容。

上述前提成立就必须执行公式，不再判断原始数据质量。轨迹偏差大、控制剧烈、生理数值极端、未响应、未注视或未稳定悬停应产生 `AnchorResult v0.2` 的 `computed + Unacceptable`，raw availability 为 1；M4 不生成 `invalid_quality`。只有输入缺失、任务不适用、配置不足、依赖缺失或提取器错误才使用 `missing_input`、`not_applicable`、`not_computable`、`dependency_missing` 或 `extractor_error`。

M5 根据 M4 的 per-anchor availability 计算 competency coverage 和 `assessable`、`partial`、`insufficient` 或 `prior_only`；D、A、U 的 `computed` evidence 均计为 available。fatal pre-request closure 错误抛稳定 validation error、不生成 M4 report 或 posterior；有效 request 之后的 plan/registry/DAG/global inventory/atomic commit 错误才使用 M4 blocked report，同样不生成 posterior。

Import 成功不代表所有 competency 都可评估。

## 10. 示例 manifest

以下示例展示结构；示例 checksum 为合法长度的说明值，正式 bundle 必须使用实际文件 SHA-256。

    {
      "bundle_schema_version": "0.1.0",
      "session_id": "session-p001-20260710-001",
      "created_at": "2026-07-10T14:00:00Z",
      "source_session": {
        "system": "cranfield-vr-simulator",
        "source_id": "S_101500_P_1",
        "campaign": "longitudinal-deceleration-hover"
      },
      "participant": {
        "pseudonymous_id": "P001"
      },
      "task": {
        "task_profile_id": "hover-deceleration-v0",
        "scenario_id": "longitudinal-01",
        "expected_phases": [
          "translation",
          "deceleration",
          "hover_stabilization"
        ],
        "reference": {
          "source": "model_bundle",
          "reference_id": "hover-deceleration-commanded-path-v0"
        }
      },
      "session_timebase": {
        "origin": "session_start",
        "unit": "ns",
        "master_clock_id": "sim_clock"
      },
      "streams": {
        "X": {
          "modality": "X",
          "status": "present",
          "required_for_import": true,
          "paths": ["streams/flight_state.parquet"],
          "format": "parquet",
          "schema_id": "flight-state-v0",
          "clock_id": "sim_clock",
          "sample_rate_hz": 100.0,
          "units": "flight-state-units-v0",
          "clock_sync": {
            "method": "master_clock",
            "scale": 1.0,
            "offset_ns": 0,
            "drift_ppm": 0.0,
            "residual_rms_ms": 0.0,
            "residual_max_ms": 0.0
          },
          "quality_summary": {
            "coverage_ratio": 1.0,
            "gap_count": 0
          },
          "checksums": {
            "streams/flight_state.parquet": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
          },
          "metadata": {
            "coordinate_frame": "earth-fixed",
            "attitude_convention": "3-2-1-euler-degrees"
          }
        },
        "U": {
          "modality": "U",
          "status": "present",
          "required_for_import": true,
          "paths": ["streams/control_input.parquet"],
          "format": "parquet",
          "schema_id": "control-input-v0",
          "clock_id": "sim_clock",
          "sample_rate_hz": 100.0,
          "units": "percent-full-deflection",
          "clock_sync": {
            "method": "master_clock",
            "scale": 1.0,
            "offset_ns": 0,
            "drift_ppm": 0.0,
            "residual_rms_ms": 0.0,
            "residual_max_ms": 0.0
          },
          "quality_summary": {
            "coverage_ratio": 1.0,
            "gap_count": 0
          },
          "checksums": {
            "streams/control_input.parquet": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
          },
          "metadata": {
            "active_channels": ["longitudinal"]
          }
        },
        "I": {
          "modality": "I",
          "status": "export_pending",
          "required_for_import": false,
          "paths": [],
          "format": "mp4+frame_index",
          "schema_id": "vr-first-person-scene-v0",
          "clock_id": "vr_clock",
          "sample_rate_hz": null,
          "units": "pixels-and-head-pose",
          "clock_sync": null,
          "quality_summary": null,
          "checksums": {},
          "metadata": {
            "view": "pilot-first-person-head-coupled"
          }
        },
        "G": {
          "modality": "G",
          "status": "export_pending",
          "required_for_import": false,
          "paths": [],
          "format": "parquet",
          "schema_id": "gaze-ray-point-aoi-v0",
          "clock_id": "eye_tracker_clock",
          "sample_rate_hz": null,
          "units": "normalized-viewport-and-metre-ray",
          "clock_sync": null,
          "quality_summary": null,
          "checksums": {},
          "metadata": {
            "scene_binding": "I.frame_id",
            "aoi_taxonomy_id": "hover-deceleration-aoi-v0"
          }
        },
        "EEG": {
          "modality": "EEG",
          "status": "export_pending",
          "required_for_import": false,
          "paths": [],
          "format": "parquet",
          "schema_id": "eeg-multichannel-v0",
          "clock_id": "eeg_clock",
          "sample_rate_hz": null,
          "units": "microvolt",
          "clock_sync": null,
          "quality_summary": null,
          "checksums": {},
          "metadata": {}
        },
        "ECG": {
          "modality": "ECG",
          "status": "export_pending",
          "required_for_import": false,
          "paths": [],
          "format": "parquet",
          "schema_id": "ecg-v0",
          "clock_id": "ecg_clock",
          "sample_rate_hz": null,
          "units": "millivolt",
          "clock_sync": null,
          "quality_summary": null,
          "checksums": {},
          "metadata": {}
        },
        "pilot_camera": {
          "modality": "pilot_camera",
          "status": "export_pending",
          "required_for_import": false,
          "paths": [],
          "format": "mp4+frame_index",
          "schema_id": "pilot-camera-v0",
          "clock_id": "pilot_camera_clock",
          "sample_rate_hz": null,
          "units": "pixels",
          "clock_sync": null,
          "quality_summary": null,
          "checksums": {},
          "metadata": {
            "privacy_class": "sensitive-biometric-imagery"
          }
        }
      },
      "annotations": {
        "revision": "annotations-v1",
        "phases": "annotations/phases.json",
        "events": "annotations/events.json",
        "baseline_intervals": "annotations/baseline_intervals.json"
      },
      "integrity": {
        "algorithm": "sha256",
        "manifest_canonicalization": "json-canonicalization-v1",
        "checksum_file": "integrity/checksums.sha256"
      },
      "privacy": {
        "classification": "restricted-research",
        "direct_identifiers_removed": true,
        "contains_biometric_data": false,
        "biometric_modalities_export_pending": ["G", "EEG", "ECG", "pilot_camera"],
        "permitted_use": "approved-cranfield-research"
      }
    }

## 11. Validation result

M2 bundle/content validator 应输出 `IngestionReadinessReport`，而不是只返回 true/false：

- bundle、七个 core stream 和 task reference 的 validation status；
- 每项错误的 path、code、severity 和 remediation；
- source timestamp、declared offset/drift、coverage、gap 和 artifact 摘要；
- 明确列出 `export_pending` 模态。

该报告不验证 aligned `t_ns`、anchor applicability 或 competency coverage，并且 `formal_run_authorized=false`。

M3 在同一 M1/M2 snapshot 上输出独立的 `SynchronizationReport`：包含七个 core modality 的完整 inventory、单独的 task-reference/annotation 结果、session window、clock/coverage/gap/duplicate/越界指标、policy/catalog/alignment fingerprints 与 `ready|ready_partial|blocked` disposition。M3 不插值或重采样，报告中的 `interpolated_rows=0`；该报告只证明结构／时间合同并提供 non-gating diagnostics，不评价 M4 evidence 质量，`formal_run_authorized=false`。

锁定 model revision 并解析 model-bundle reference 后，`run.preflight` 的 `RunPreflightReport` 检查 frozen inputs、任务前提、execution plan、plugin 和版本兼容性；只有通过该运行门，pipeline 才能创建 AssessmentRun。实际 per-anchor raw availability 由 M4 结果给出，model-weighted competency coverage 由 M5 计算。

## 12. 数据安全与隐私

- participant 只使用 pseudonymous ID；
- 原始姓名、联系方式和无关身份字段不得进入 manifest；
- `contains_biometric_data` 只说明当前 bundle 文件是否实际包含真实或伪匿名参与者来源的敏感人体数据，不说明原实验是否曾经采集；
- `biometric_modalities_export_pending` 只列已采集但当前 bundle 尚无文件的 G/EEG/ECG/pilot_camera，必须去重并与对应 descriptor 的 `export_pending` 状态一致；
- 因此 `contains_biometric_data=false` 可以与非空 pending 列表并存；非 synthetic bundle 若这些真实人体 stream 为 `present` 或 `invalid`，则该字段必须为 true；synthetic-test-data 即使生成这些 stream 也保持 false 且 pending 为空；
- pilot_camera、gaze、EEG 和 ECG 按敏感研究数据处理；
- 日志不得写入原始图像、完整信号或直接身份信息；
- 导出 support bundle 时默认只包含 schema、错误、版本和脱敏摘要；
- Session 文件删除、移动或外部引用失效后，历史 result 仍保留 checksum 和不可复现原因，但不得假装输入仍可用；
- Bundle 使用范围和保留策略由项目伦理和数据管理要求决定。

## 13. 版本与扩展

- Schema 使用 semantic version。
- 新增可选字段或新可选 stream 可以增加 minor version。
- 删除字段、改变字段语义或时间映射规则必须增加 major version。
- 新模态放入 `streams` 并提供独立 schema 和 ingestion adapter。
- Reader 必须保留未知 `extensions`，避免无意破坏第三方 metadata。
- Bundle migration 产生新 bundle 或新 manifest revision；不得静默重写原始交付物。
