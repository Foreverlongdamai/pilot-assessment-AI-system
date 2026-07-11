# Session Bundle 正式规范

**规范版本：** 0.1.0  
**文档状态：** 产品 v0 数据合同  
**日期：** 2026-07-10  
**上位文档：** [产品总览](./01_PRODUCT_OVERVIEW.md)

## 1. 目的

Session bundle 是一次实验／训练 session 的不可变数据交付单元。它必须同时表达：

- 已经导出的原始或派生数据；
- 已采集但尚未导出的正式模态；
- 缺失、无效或该任务不适用的模态；
- 所有文件的格式、单位、时钟和完整性；
- phase、event、baseline 和任务 reference；
- 多设备 stream 映射到统一 session 时间轴的方法和质量。

Bundle 规范不规定具体 anchor 公式。它提供可复现计算所需的数据事实；anchor 和 BN 规则属于 model bundle。

本文中的“必须”表示 schema 或运行质量门要求；“建议”表示 v0 的推荐存储方式。

## 2. 正式模态定义

| ID | 定义 | 与其他模态的关系 |
|---|---|---|
| X(t) | 飞行状态：位置、速度、姿态、角速度、加速度等 | 与 U(t) 和任务 reference 共同支持客观 anchor |
| U(t) | 飞行员操纵：yaw、longitudinal、lateral、heave 等 | 保留原始值、单位、方向和归一化说明 |
| I(t) | **随飞行员头部转动而变化的第一视角 VR scene**，即飞行员当时在头显内实际看到的动态画面 | 不是固定外部摄像机画面；必须能关联 frame timestamp 和 head pose |
| G(t) | **定义在动态 I(t) 画面上的 gaze ray、gaze point、fixation/stare 与 AOI** | 必须指明对应 scene frame、坐标空间、AOI taxonomy 和 validity |
| EEG(t) | 脑电通道信号及质量／artifact 标记 | 需要 channel metadata、设备时钟和 baseline |
| ECG(t) | 心电通道信号及质量／artifact 标记 | 需要 lead/channel metadata、设备时钟和 baseline |
| pilot_camera(t) | 可选的飞行员脸部／上半身相机图像 | 不是 I(t)；可用于行为、质量审查或未来插件 |

P(t) 是 physiology 的概念分组，不作为含混的单一文件键；manifest 必须把 EEG、ECG 及未来生理模态分别声明，使采样率、时钟、单位、质量和缺失状态可独立验证。

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
| `quality_summary` | 导出时生成的覆盖、gap、validity 或 artifact 摘要 |
| `checksums` | 每个文件的 sha256 |
| `metadata` | 模态专用 metadata |

### 5.1 Stream status

| 状态 | 含义 | 运行行为 |
|---|---|---|
| `present` | 文件已导出并可验证 | 进入 adapter 和质量门 |
| `export_pending` | 实验已采集，但当前 bundle 尚无可读导出 | 保留正式接口；相关 anchor unavailable |
| `missing` | 预期存在但未采集或已丢失 | 记录数据缺口；按 task/model 决定 partial 或 fatal |
| `invalid` | 文件存在，但 schema、checksum、时钟或质量不合格 | 禁止使用；给出修复诊断 |
| `not_applicable` | 当前任务明确不要求该模态 | 不计入缺失覆盖 |

`export_pending` 不得被 adapter 自动改写为 `missing`。

## 6. 统一时间轴

### 6.1 t_ns

所有可计算 stream 必须提供：

- 原始 `source_timestamp`；
- 稳定的 `source_index` 或 `frame_id`；
- 映射后的 `t_ns`，表示相对 session origin 的 int64 纳秒。

原始时间戳不可被覆盖。若源文件暂时只有 session time，也应同时保留该列并声明其 clock。

### 6.2 Clock mapping

默认采用仿射映射：

`session_time_seconds = scale × source_time_seconds + offset_seconds`

其中：

- `offset_ns` 记录初始偏移；
- `drift_ppm = (scale - 1) × 10^6`；
- `residual_rms_ms` 和 `residual_max_ms` 记录 sync marker 拟合残差；
- `sync_method` 说明硬件触发、共享时钟、事件对齐或离线拟合；
- `sync_markers` 可引用单独文件或内嵌摘要。

Assessment Core 应根据原始 timestamp 和 mapping 生成派生 `t_ns`，并验证已导出 `t_ns` 是否一致。重同步产生新的 annotation/sync revision，不修改原文件。

### 6.3 同步要求

- 每个 stream 内 `t_ns` 必须单调非递减；重复时间戳必须有稳定 index。
- Clock mapping 的 scale、offset 和 residual 必须为有限值。
- 可接受 residual、gap 和跨模态最大时间差由 task profile／anchor definition 声明，不能硬编码为全系统同一个数值。
- 跨模态 anchor 只能使用同时满足各自质量门的重叠窗口。
- 同步报告必须列出覆盖起止、缺口、丢帧、插值比例和超容差区间。

## 7. 各模态文件合同

### 7.1 X(t)：flight state

至少包含 `source_timestamp`、`t_ns` 和 task profile 所需状态字段。字段必须明确：

- 坐标系和轴方向；
- earth/body frame；
- position、velocity、attitude 和 rate 的单位；
- angle convention 和 wrapping；
- derived field 是否来自原始系统。

当前 simulator CSV 可由 legacy adapter 同时映射为 X(t) 和 U(t)，但 manifest 必须记录 column mapping，且不能把 experiment condition 列当作时序传感器。

### 7.2 U(t)：control input

至少包含各有效 control channel、`source_timestamp` 和 `t_ns`。必须声明：

- raw unit；
- sign convention；
- physical range；
- full-deflection normalization；
- deadband、saturation 和 control mode。

### 7.3 I(t)：第一视角 VR scene

I(t) 是飞行员头显内随头部姿态变化的动态第一视角画面。每个 frame index 至少包含：

- `frame_id`；
- `source_timestamp`；
- `t_ns`；
- 视频 frame number 或图像相对路径；
- head pose（position 可选，orientation 必须按设备能力声明）；
- render resolution、field of view 和坐标约定；
- frame validity 和 dropped-frame 标记。

如果 VR 系统可导出 scene graph、object ID buffer 或 AOI mask，应作为 I(t) 的辅助文件登记，但不能用它替代实际呈现给飞行员的画面。

### 7.4 G(t)：gaze、stare/fixation 与 AOI

G(t) 必须说明 gaze 是在何种空间表达，并与动态 I(t) 建立联系。Stream present 时，raw gaze 至少包含：

- `source_timestamp`、`t_ns`；
- `gaze_sample_id`；
- 左／右／融合 gaze validity；
- gaze ray origin 与 direction，或 normalized viewport point；
- `scene_frame_id`；
- blink、tracking loss 和 calibration quality。

fixation/stare 与 AOI 是派生表，至少包含 fixation_id、start/end t_ns、duration_ms、centroid ray/point、scene frame range、validity/confidence、AOI ID、taxonomy version 和 assignment confidence。原始 gaze point/ray 与派生结果必须分开保存；不得只保留烧录了注视区域的图片。

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

### 8.1 phases.json

每个 phase 至少包含：

- stable phase ID；
- label；
- start/end `t_ns`；
- annotation source：scripted、manual、detected 或 reviewed；
- revision 和 reviewer；
- confidence 或 quality。

### 8.2 events.json

包含 command、disturbance、critical event、envelope exit 等事件。每个事件记录 stable event_id、type、`t_ns`、duration（如适用）、source 和 confidence。用于 O10/O11/H2 的事件还必须通过 task profile 或 event metadata 解析：

- required observation horizon；
- recovery_start_mode；
- expected_response_channels；
- 每通道 expected direction；
- response_aggregation；
- event-relevant AOI（如适用）；
- response_mapping_id 与版本。

缺少所需 mapping 时 anchor 返回 not_computable，不得让实现自行猜测响应通道或起点。

### 8.3 baseline_intervals.json

EEG/ECG normalization 所需 baseline 必须声明 start/end、条件、是否有效和 exclusion reason。

### 8.4 Commanded/reference path

O2 Peak Tracking Excursion 等 anchor 需要 commanded/reference path。来源必须明确为：

- bundle 内 `references/` 文件；或
- model bundle 中固定的 task profile reference。

结果 provenance 必须记录实际使用的 reference hash。

## 9. 质量门

### 9.1 Bundle gate

- Manifest 可由支持的 schema 解析；
- session ID、stream ID 和路径唯一；
- 路径不逃逸 bundle root；
- 所有 `present` 文件存在且 checksum 匹配；
- 所有正式模态均有 descriptor；
- privacy 和 participant pseudonymization 字段存在。

### 9.2 Stream gate

- Schema、类型和单位匹配；
- timestamp 有限且次序合法；
- sample/frame coverage 与 manifest 一致；
- gap、drop、validity 和 artifact 摘要可计算；
- `invalid` stream 不得进入 anchor。

### 9.3 Synchronization gate

- Clock mapping 可重现；
- offset/drift/residual 在 task/anchor 容差内；
- phase/event/baseline 位于 session 范围内；
- 跨模态重叠窗口满足 anchor 要求；
- VR frame、head pose 和 gaze frame association 可验证。

### 9.4 Assessment gate

系统按 model bundle 逐 anchor 和逐 competency 计算：

- required modality 是否 `present`；
- 数据质量是否达标；
- 必需 annotation/reference 是否存在；
- evidence coverage；
- `assessable`、`partial`、`insufficient` 或 `prior_only`；fatal validation 使用 blocked run 状态，不生成 posterior。

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

Bundle validator 应输出结构化报告，而不是只返回 true/false：

- bundle、stream 和 annotation 的 validation status；
- 每项错误的 path、code、severity 和 remediation；
- offset、drift、residual、coverage、gap 和 artifact 摘要；
- 每个 anchor 的 data readiness；
- 每个 competency 的 evidence coverage；
- 明确列出 `export_pending` 模态。

Validator 不能执行 BN inference；只有通过 run preflight 后 pipeline 才能创建 AssessmentRun。

## 12. 数据安全与隐私

- participant 只使用 pseudonymous ID；
- 原始姓名、联系方式和无关身份字段不得进入 manifest；
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
