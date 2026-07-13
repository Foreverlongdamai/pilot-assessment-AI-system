# M2 Multimodal Synthetic Foundation Design

| 字段 | 值 |
|---|---|
| 设计状态 | 已批准实施 |
| 日期 | 2026-07-11 |
| 用户批准 | 2026-07-11 |
| M3 口径修订 | 2026-07-12：session window 权威移交 M3 §7 / D-018 |
| M4 边界修订 | 2026-07-13：accepted D-021 取消 downstream residual/coverage/quality evidence gate；不改变 M2 实现或 golden |
| 上位基线 | Product design v0.1 + Backend Foundation M1 |
| 本阶段 | M2：理想多模态合同、合成 bundle、全模态 ingestion readiness inspection |
| 科学状态 | synthetic_test_only / not_supported |

## 1. 目标

M2 建立一个可以持续扩展的多模态数据基础，而不是只为当前 CSV 写一次性解析脚本。它必须同时做到：

1. 读取当前 simulator 采集格式样例 CSV，并从同一物理文件形成独立 X(t) 与 U(t) 逻辑流；
2. 为 I(t)、G(t)、EEG(t)、ECG(t) 和 pilot_camera(t) 固化第一版理想数据合同；
3. 围绕 X/U 时间范围生成确定性、格式正确但不主张真实性的 synthetic multimodal bundle；
4. 对每种正式模态执行 ingestion readiness inspection，并形成前端可消费的版本化报告；
5. 为 M3 synchronization、M4 18-anchor/evidence、M5 BN 和 M6 端到端 runner 提供可重复测试输入。

M2 不实现 anchor、evidence、BN 或飞行员评分。即使 synthetic bundle 的所有模态都可用，M2 结果也不能称为正式 assessment result。

## 2. 为什么不把所有数据追加到一个 CSV

用户允许为测试补全缺失模态，但“补全”应发生在 Session Bundle 层，而不是把图像、gaze、EEG 和 ECG 强行变成 simulator CSV 的额外列：

- 图像是 15/30 Hz 文件序列；
- gaze 适合约 120 Hz 的采样表和独立 fixation/AOI 表；
- EEG 与 ECG 是 250–256 Hz 的多通道列式信号；
- X/U 当前为 100 Hz；
- 各设备拥有独立 clock、quality 和 provenance。

因此，当前 CSV 保持原样作为 X/U 共享源，其余模态以各自理想文件加入同一 bundle。这样能够完整覆盖多采样率、missingness、clock mapping 和文件合同测试，也不会形成未来必须拆除的超宽 CSV。

## 3. 已验证的采集格式样例 CSV 基线

源文件位于产品仓库外：

`C:/Users/long/Desktop/CranfieldOffer/proj/data/S_101500_Time_2026_05_14_16_48_54_P_1.csv`

该文件只用于说明当前采集系统可能导出的列、类型、采样率和时间戳形式。它来自一次未按标准轨迹或正式任务脚本执行的随意飞行记录，没有 commanded trajectory、合格/不合格标签、专家 phase annotation 或能力 ground truth。本文和代码只能用它验证 adapter、schema、clock、row preservation 与端到端软件接口；不得用其轨迹或操纵内容验证 anchor、阈值、CPT、任务表现或飞行员能力。

| 项目 | 实测值 |
|---|---:|
| SHA-256 | `19bf804253d841de9c9de299ac96e9e1b693b2dbfae2f3eaeac5d7dc044e4f52` |
| 文件大小 | 571,224 bytes |
| 数据行 | 2,902 |
| 列 | 33 |
| 时间范围 | 0.00–29.01 s |
| 时间顺序 | 严格递增、无重复 |
| 中位 dt | 0.01 s |
| 推断采样率 | 100 Hz |
| 缺失/非数值/NaN/Inf | 0 |
| 非 33 字段行 | 0 |

Header 含不一致的前导/尾随空格。Adapter 必须同时保留 raw header，并使用版本化的 `trim_outer_ascii_whitespace_v1` 规范化后匹配；规范化后如产生碰撞则阻止 readiness inspection。

`Simulation time` 很可能以秒为单位，但原 header 未写单位；M2 将它记录为 `engineering_assumption`，等待数据字典确认。

## 4. 方案比较

### 方案 A：只完成 X/U，其他模态继续 export_pending

优点是最小；缺点是无法提前验证多时钟、Parquet、图像、gaze/physiology 合同，也不能满足完整工作流测试目标。

### 方案 B：向 simulator CSV 追加所有 synthetic 字段

实现看似直接，但图像路径、120/250/256 Hz 数据会被重复、降采样或嵌套，破坏正式 Session Bundle 与一等模态边界，不采用。

### 方案 C：多文件 synthetic bundle + 声明式 adapter profile

这是采用方案。X/U 共享原 CSV；I/G/EEG/ECG/pilot_camera 使用理想文件合同；生成器、adapter 和 readiness inspection 依赖同一套版本化 schema/profile。

内部列式引擎选用 Polars，原因是显式 schema、CSV/Parquet 原生支持和后续信号/anchor 列式计算能力。Polars 仅存在于 ingestion 内部，Pydantic DTO 与 JSON Schema 不暴露 Polars 类型。M2 使用 eager 读取和显式 dtype；未来可切换 lazy/streaming 而不改变 adapter 合同。官方能力参考：[read_csv](https://docs.pola.rs/api/python/stable/reference/api/polars.read_csv.html)、[read_parquet](https://docs.pola.rs/api/python/stable/reference/api/polars.read_parquet.html)、[write_parquet](https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_parquet.html)。

运行依赖范围锁定为 `polars>=1,<2` 与 `Pillow>=11,<13`，实际版本由 `uv.lock` 固定。M2 不引入 pandas、PyArrow 或 ffmpeg。

## 5. 已接受的跨模块决策

### D-011：一个物理 artifact 可以支撑多个逻辑 stream view

- X 与 U 可以引用完全相同的 canonical relative path。
- 相同 path 在 `checksums.sha256` 中只有一行，并且只读取/哈希一次。
- 所有引用必须使用完全相同的 path 拼写、SHA-256、format、schema_id 和 shared_source_id。
- `Simulator.csv` 与 `simulator.csv` 之类 case-fold collision 继续拒绝。
- v0.1 只允许 X 与 U 共享；其他 stream sharing，以及同一路径由两个独立声明赋予 stream/annotation/reference/integrity 跨角色所有权均拒绝。`task_reference` descriptor 是 reference 的唯一 owner，不属于 sharing。
- declared reference count 与 unique artifact count 分别报告；哈希预算按 unique artifact 计算。

这修正 `03_SESSION_BUNDLE_SPEC.md` 中“legacy CSV 可同时映射 X/U”和“路径唯一”之间的歧义。路径唯一应解释为物理 artifact identity 唯一，而不是禁止多个逻辑 view。

### D-012：Synthetic full bundle 永远不是科学证据

- manifest `source_session.system = synthetic-multimodal-generator-v0.1`，并在 provenance 保留采集格式样例 X/U 文件 hash；这是 captured-format-sample X/U + synthetic modalities 的混合软件测试 bundle，不是有效任务 session；
- privacy 固定为 `classification=synthetic-test-data`、`direct_identifiers_removed=true`、`contains_biometric_data=false`、`biometric_modalities_export_pending=[]`、`permitted_use=software-testing-only`；
- `extensions.synthetic.scientific_validation_status = not_supported`；
- 所有未来结果显示 `SYNTHETIC TEST DATA`；
- synthetic run 不可转换为 formal pilot assessment result。

### D-013：M2 只产生 IngestionReadinessReport

M2 `IngestionReadinessReport` 的 scope 是 `inspect_only_ingestion_content_v1`。它可以允许进入 M3 synchronization，但 `formal_run_authorized` 永远为 false。原始 source artifact 在 M2 可以只含 source timestamp 与声明的 `clock_sync`；`03_SESSION_BUNDLE_SPEC.md` 要求的 authoritative `t_ns` 解释为 M3 产出的 aligned view 字段，不由 M2 adapter 伪造。完成 M3 与 model/plan compatibility 检查后，`run.preflight` 才产生独立的 `RunPreflightReport`；M4 不按 residual、coverage 或所谓采集质量过滤表现 evidence。

- M2 physical/profile schema 使用 `*-raw-v0.1`，内部产物为 `RawStream`/`PreparedSession`，不承诺 authoritative `t_ns`；
- M3 产物为 `AlignedSession`，其中各 aligned schema 使用 `*-aligned-v0.1` 并包含严格递增或带稳定 index 的 int64 `t_ns`；
- M2 generator 可以生成 phase/event/reference fixture，但 M2 只验证路径、JSON/Parquet 结构与 provenance；其 session-time 语义、重叠窗口和 reference 可用性首次由 M3 验证。

这些规则已作为 D-011–D-014 写入 `DECISIONS.md`；reference-model-v0.1 的图能力边界另由 D-015 锁定。

## 6. Bundle 结构

~~~text
synthetic-multimodal-session/
  manifest.json
  streams/
    simulator.csv                         # X/U 共享源
    vr_scene/
      frame_index.parquet
      aoi_instances.parquet
      frames/*.png
    gaze/
      gaze_samples.parquet
      fixations.parquet
    eeg/
      eeg_samples.parquet
      eeg_sidecar.json
    ecg/
      ecg_samples.parquet
      r_peaks.parquet
    pilot_camera/
      frame_index.parquet
      frames/*.png
  references/
    commanded_path.parquet
  annotations/
    phases.json
    events.json
    baseline_intervals.json
  integrity/
    checksums.sha256
~~~

所有 PNG 都作为所属 descriptor 的显式 path 出现在 manifest/checksum 中。当前约 29 秒测试规模低于 M1 默认 10,000 项上限；这种逐 PNG 表示只用于 synthetic/micro-test。正式长 session 的首选合同仍是 `mp4+frame_index`，未来也可以增加受控的 chunked image collection manifest，二者均归一化为同一内部 `FrameStream`。M2 generator 在预计 declared paths 超限时直接拒绝，而不静默截断。

`task_reference` 是同一 major version 下的可选逻辑 stream，不属于七个 core modalities。它的 descriptor 位于 `streams.task_reference`，但 artifact path 固定在 `references/commanded_path.parquet`；`task.reference` 使用 `source=bundle`、`stream_id=task_reference` 指向该 descriptor。它通过普通 adapter/readiness gate 进入 session context，并在报告中作为独立 reference result 展示。

## 7. 各模态理想合同

### 7.0 共通列式约定

每个 Parquet schema 都由 package 内的版本化 profile 精确定义列名、物理类型、单位、可空性、值域和 `schema_id`，并把 schema ID/version 写入 Parquet metadata。共通约定如下：

- sample/frame/fixation/peak index 使用 `UInt64`，同一 artifact 内稳定且唯一；
- source timestamp 使用 finite `Float64` seconds，保留设备原值，不提前对齐；
- 连续信号、坐标、ray、bbox 和 confidence 使用 finite `Float32`；confidence 与 normalized coordinate 的值域为 `[0,1]`；
- path、ID、enum、unit 和 generator version 使用非空 UTF-8 string；image path 还必须满足 `BundleRelativePath`；
- validity/blink 等二元状态使用 Boolean；类别缺失使用明确的 nullable string/code；
- 无效连续样本使用 null 加 validity/artifact code 表达，不使用 NaN/Infinity 代替缺失；
- profile 未声明的列默认拒绝，只有 profile 显式允许的 provenance extension columns 可以保留。

复合 stream 的顶层 `schema_id` 描述整个 source bundle，`metadata.artifact_roles` 再为每类文件声明 `matcher`、`media_type`、`schema_id` 和 `required`。Matcher 只允许受控的 `exact_paths` 或单一 canonical `path_prefix`；每个 descriptor path 必须且只能命中一个 role，每个 required role 必须至少命中一个 path，adapter 禁止按文件名猜测角色。

~~~json
{
  "artifact_roles": {
    "frame_index": {
      "matcher": {"kind": "exact_paths", "paths": ["streams/vr_scene/frame_index.parquet"]},
      "media_type": "application/vnd.apache.parquet",
      "schema_id": "vr-frame-index-raw-v0.1",
      "required": true
    },
    "frame_images": {
      "matcher": {"kind": "path_prefix", "path_prefix": "streams/vr_scene/frames/"},
      "media_type": "image/png",
      "schema_id": "png-rgb8-v0.1",
      "required": true
    }
  }
}
~~~

首版 artifact schema registry：

| Stream/role | Schema ID | Non-null sort key | 主要单位 |
|---|---|---|---|
| X/U combined source | `cranfield-simulator-combined-csv-raw-v0.1` | `source_row_index` | profile per channel |
| I/frame_index | `vr-frame-index-raw-v0.1` | `source_timestamp_s, frame_id` | s、m、unit quaternion、degree |
| I/aoi_instances | `vr-aoi-instance-raw-v0.1` | `frame_id, aoi_id` | normalized `[0,1]` |
| I/frame_images | `png-rgb8-v0.1` | path in frame index | RGB8 pixels |
| G/gaze_samples | `gaze-sample-raw-v0.1` | `source_timestamp_s, gaze_sample_id` | s、mm、normalized/ray |
| G/fixations | `gaze-fixation-raw-v0.1` | `start_source_timestamp_s, fixation_id` | s、ms、normalized/ray |
| EEG/samples | `eeg-sample-raw-v0.1` | `source_timestamp_s, sample_index` | s、µV |
| EEG/sidecar | `eeg-sidecar-v0.1` | n/a | Hz、µV |
| ECG/samples | `ecg-sample-raw-v0.1` | `source_timestamp_s, sample_index` | s、mV |
| ECG/r_peaks | `ecg-r-peak-raw-v0.1` | `source_timestamp_s, peak_id` | s、ms |
| pilot_camera/frame_index | `pilot-camera-frame-index-raw-v0.1` | `source_timestamp_s, frame_id` | s、pixel/normalized bbox |
| pilot_camera/frame_images | `png-rgb8-v0.1` | path in frame index | RGB8 pixels |
| references/commanded_path | `task-reference-path-raw-v0.1` | `source_timestamp_s, reference_sample_id` | profile per state channel |

所有 sort-key、ID、path 和 required relationship 字段不可为空。测量字段只有在同一行 validity flag 为 false 或 `artifact_code` 非空时才允许为空。上述 profile 文件是实现时的规范来源；本节字段清单不得由 adapter 自由扩展。

顶层 composite schema 分别为 `vr-scene-source-bundle-v0.1`、`gaze-source-bundle-v0.1`、`eeg-source-bundle-v0.1`、`ecg-source-bundle-v0.1` 与 `pilot-camera-source-bundle-v0.1`。每个 composite descriptor 的 artifact roles 必须与 registry 完全一致；task_reference 只有一个 Parquet artifact，descriptor 直接使用 `task-reference-path-raw-v0.1`，不增加空壳 composite schema。

### 7.1 X(t) 与 U(t)：共享 legacy simulator CSV

两个 descriptor 使用：

~~~json
{
  "paths": ["streams/simulator.csv"],
  "format": "csv",
  "schema_id": "cranfield-simulator-combined-csv-raw-v0.1",
  "metadata": {
    "adapter_profile_id": "cranfield-simulator-combined-csv-raw-v0.1",
    "shared_source_id": "simulator-main",
    "view_id": "X"
  }
}
~~~

U descriptor 仅把 `view_id` 改为 `U`。

Profile 将 stripped source header 映射到 canonical channel：

| Source | Canonical channel | Unit/status |
|---|---|---|
| Simulation time | `source_time_s` | seconds, engineering_assumption |
| Xe/Ye/Ze m | `position.earth.x/y/z_m` | m；frame convention unconfirmed |
| Ground Elevation m | `environment.ground_elevation_m` | m；vertical datum unconfirmed |
| V_ex/V_ey/V_ez m/s | `velocity.earth.x/y/z_m_s` | m/s |
| V_bx/V_by/V_bz m/s | `velocity.body.x/y/z_m_s` | m/s |
| phi/theta/psi deg | `attitude.roll/pitch/yaw_deg` | degree；Euler convention unconfirmed |
| p/q/r deg/s | `angular_rate.body.p/q/r_deg_s` | degree/s |
| ax/ay/az m/s² | `acceleration.source.x/y/z_m_s2` | m/s²；frame/gravity convention unconfirmed |
| alpha/beta deg | `aero.alpha/beta_deg` | degree；sign convention unconfirmed |
| Pilot Yaw/Lon/Lat/Heave | `control.yaw/longitudinal/lateral/heave_raw` | unknown_raw；不除以 100 |

`V_e* kts` 只用于 m/s↔kt 一致性检查，容差为 0.002 kt，不产生第二组 canonical state channel。

以下列必须在容差内恒定后提升为 session context，不进入 X/U 时序 channels：

- `Control_Mode` → `context.control_mode_raw`；
- `Time Delay s` → `context.time_delay_s`；
- `Lon Frequency rad/s` → `context.longitudinal_frequency_rad_s`；
- `Long Damping` → `context.longitudinal_damping_ratio`。

### 7.2 I(t)：pilot first-person VR scene

M2 synthetic profile 使用 `image_sequence+parquet_index`，默认 30 Hz、64×36 RGB8 PNG；生产 profile 首选 `mp4+frame_index`。两种表示进入同一 `FrameStream`。每个 frame-index row 包含：

- `frame_id`、`source_timestamp_s`、`image_path`；
- width、height；
- head position xyz 与 quaternion xyzw；
- horizontal/vertical FOV；
- phase ID、validity、generator version。

`aoi_instances.parquet` 每个 frame/AOI 一行，包含 `frame_id`、`aoi_id`、taxonomy version、normalized bbox x/y/w/h、visibility 和 confidence。PNG 使用 synthetic-phase-token-dependent background 与稳定 AOI 色块，目的是验证 scene/gaze binding，不追求视觉真实性。

### 7.3 G(t)：gaze、fixation 与 AOI

`gaze_samples.parquet` 默认 120 Hz，字段包括：

- `gaze_sample_id`、`source_timestamp_s`、最近的 `scene_frame_id`；
- normalized viewport x/y；
- gaze origin xyz 与 unit ray direction xyz；
- left/right pupil diameter、binocular validity、confidence、blink flag；
- assigned AOI ID 与 assignment confidence。

`fixations.parquet` 包含 fixation ID、start/end timestamp、duration、centroid viewport/ray、scene frame range、AOI ID、validity/confidence 和 detector version。

### 7.4 EEG(t)

`eeg_samples.parquet` 默认 256 Hz，使用 8 个 synthetic 10–20 labels：Fp1、Fp2、F3、F4、C3、C4、P3、P4。字段包括 sample index、source timestamp、每通道 microvolt、signal_valid 和 artifact_code。

`eeg_sidecar.json` 记录 montage ID、reference、channel order/unit、sample rate、device clock、generator/seed 和明确的 `synthetic_not_neurophysiological=true`。

### 7.5 ECG(t)

`ecg_samples.parquet` 默认 250 Hz，包含 sample index、source timestamp、`synthetic_lead_ii_mv`、signal_valid 和 artifact_code。

`r_peaks.parquet` 包含 peak ID、timestamp、RR interval、detection confidence 和 generator version。它是派生 artifact，原始 synthetic ECG 仍保留。

### 7.6 pilot_camera(t)

M2 synthetic profile 使用 15 Hz、48×48 RGB8 PNG image sequence；生产 profile 首选 `mp4+frame_index`。Frame index 包含 frame ID、source timestamp、image path、head bbox、left/right eye bbox、validity、privacy class 和 generator version。内容是几何占位头像，不生成或模仿真实个人身份。

### 7.7 task reference 与 annotations

下列 phase 名称和比例只是 synthetic interface tokens，由 generator 人工写入；它们不是从样例 CSV 检测出来的实际飞行阶段，也不是专家 annotation：

- 三个 phase 按 session duration 比例生成：translation `[0, 0.35T)`、deceleration `[0.35T, 0.70T)`、hover stabilization `[0.70T, T]`；
- baseline 为 `[0, min(5 s, 0.15T)]`；
- disturbance event 位于 `0.45T`，critical-monitoring event 位于 `0.62T`；
- `commanded_path.parquet` 仅复用样例 X 的时间轴和部分数值形状来生成格式正确的 reference fixture；它不是实验真实 commanded trajectory，也不表示该随意飞行符合轨迹标准，禁止据此解释 tracking error 或飞行能力；
- phase/event/reference 参数进入 generator version 与 provenance；M2 仅生成并做结构检查，M3 负责 session-time 语义与 reference 对齐，M4 可替换评分参数而不改变 M2 文件合同。

### 7.8 首版物理列字典

以下是 M2 profile 必须导出的有序物理列。类型记号为 `u64/u32/f64/f32/bool/utf8`；`?` 表示可空，其他列不可空。Adapter 按精确列名与类型校验，不进行 dtype 猜测。

| Artifact | Ordered columns |
|---|---|
| I/frame_index | `frame_id:u64`, `source_timestamp_s:f64`, `image_path:utf8`, `width:u32`, `height:u32`, `head_x_m:f32`, `head_y_m:f32`, `head_z_m:f32`, `head_qx:f32`, `head_qy:f32`, `head_qz:f32`, `head_qw:f32`, `horizontal_fov_deg:f32`, `vertical_fov_deg:f32`, `phase_id:utf8`, `frame_valid:bool`, `generator_version:utf8` |
| I/aoi_instances | `frame_id:u64`, `aoi_id:utf8`, `taxonomy_version:utf8`, `bbox_x_norm:f32`, `bbox_y_norm:f32`, `bbox_w_norm:f32`, `bbox_h_norm:f32`, `visible:bool`, `confidence:f32` |
| G/gaze_samples | `gaze_sample_id:u64`, `source_timestamp_s:f64`, `scene_frame_id:u64`, `viewport_x_norm:f32?`, `viewport_y_norm:f32?`, `origin_x_m:f32?`, `origin_y_m:f32?`, `origin_z_m:f32?`, `ray_x:f32?`, `ray_y:f32?`, `ray_z:f32?`, `left_pupil_mm:f32?`, `right_pupil_mm:f32?`, `binocular_valid:bool`, `confidence:f32`, `blink:bool`, `assigned_aoi_id:utf8?`, `assignment_confidence:f32?` |
| G/fixations | `fixation_id:u64`, `start_source_timestamp_s:f64`, `end_source_timestamp_s:f64`, `duration_ms:f32`, `centroid_x_norm:f32`, `centroid_y_norm:f32`, `ray_x:f32`, `ray_y:f32`, `ray_z:f32`, `first_scene_frame_id:u64`, `last_scene_frame_id:u64`, `aoi_id:utf8?`, `fixation_valid:bool`, `confidence:f32`, `detector_version:utf8` |
| EEG/samples | `sample_index:u64`, `source_timestamp_s:f64`, `Fp1_uV:f32?`, `Fp2_uV:f32?`, `F3_uV:f32?`, `F4_uV:f32?`, `C3_uV:f32?`, `C4_uV:f32?`, `P3_uV:f32?`, `P4_uV:f32?`, `signal_valid:bool`, `artifact_code:utf8?` |
| ECG/samples | `sample_index:u64`, `source_timestamp_s:f64`, `synthetic_lead_ii_mV:f32?`, `signal_valid:bool`, `artifact_code:utf8?` |
| ECG/r_peaks | `peak_id:u64`, `source_timestamp_s:f64`, `rr_interval_ms:f32?`, `detection_confidence:f32`, `generator_version:utf8` |
| pilot_camera/frame_index | `frame_id:u64`, `source_timestamp_s:f64`, `image_path:utf8`, `width:u32`, `height:u32`, `head_bbox_x_norm:f32`, `head_bbox_y_norm:f32`, `head_bbox_w_norm:f32`, `head_bbox_h_norm:f32`, `left_eye_bbox_x_norm:f32`, `left_eye_bbox_y_norm:f32`, `left_eye_bbox_w_norm:f32`, `left_eye_bbox_h_norm:f32`, `right_eye_bbox_x_norm:f32`, `right_eye_bbox_y_norm:f32`, `right_eye_bbox_w_norm:f32`, `right_eye_bbox_h_norm:f32`, `frame_valid:bool`, `privacy_class:utf8`, `generator_version:utf8` |
| references/commanded_path | `reference_sample_id:u64`, `source_timestamp_s:f64`, `target_x_m:f32`, `target_y_m:f32`, `target_z_m:f32`, `target_vx_m_s:f32`, `target_vy_m_s:f32`, `target_vz_m_s:f32`, `target_roll_deg:f32`, `target_pitch_deg:f32`, `target_yaw_deg:f32`, `envelope_profile_id:utf8` |

`eeg_sidecar.json` 必需键为 `schema_id`、`montage_id`、`reference`、`channel_order`、`channel_units`、`sample_rate_hz`、`clock_id`、`generator_id`、`seed`、`synthetic_not_neurophysiological=true`。Annotation fixture JSON 必须携带自己的 `schema_id`、`generator_id`、`seed` 与 `synthetic_semantics_unvalidated=true`；M2 不把它升级为已验证 annotation revision。

## 8. Synthetic generator

生成器 ID 为 `synthetic-multimodal-generator-v0.1`，默认 seed `20260711`。它接受：

~~~text
--xu-csv <path>
--output <local_data path>
--seed 20260711
--duration-mode source
~~~

处理规则：

1. 原始 X/U CSV 按字节复制，不修改 header、换行或数值；
2. 读取 `Simulation time` 与 `Pilot Lon` 只用于确定 synthetic timeline 和测试耦合；
3. 定义内部变量 `control_activity(t)=min(1, abs(Pilot Lon raw)/100)` 作为无科学语义的 `synthetic_control_driver`；它不是驾驶员活动水平、控制质量、工作负荷、任务表现、生理反应 ground truth，也不是对控制单位的归一化结论；
4. scene/head/gaze 由 phase 和固定正弦项产生；
5. gaze 在已知窗口切换至 off-task AOI，以便 H1–H3 后续有可计算 golden cases；
6. ECG nominal heart rate 使用 `70 + 20*control_activity` bpm 加固定小扰动；
7. EEG 使用固定频率分量、seeded noise 和 control-activity modulation；
8. 所有 noise 来自固定 seed，无系统时间、随机 UUID 或主机信息进入文件内容；
9. generator 完成后写 manifest/checksum，并再次通过 M1 loader 与 M2 readiness inspection；
10. 生成目录在 `local_data/` 或测试临时目录，永不提交生成 bundle。

确定性规则：

- 每个模态使用 `source_timestamp_s = k / sample_rate_hz`，保留所有满足 `source_timestamp_s <= source_duration_s` 的 sample/frame；
- `session_id` 由 source SHA-256、generator ID 与 seed 的稳定摘要派生；默认 `created_at=2000-01-01T00:00:00Z`，测试者也可显式传入固定 RFC 3339 值；
- noise 使用 `sha256-counter-prng-v0.1`，不依赖 Python/NumPy 的隐式全局 RNG。Seed 限制为 `0..2^63-1`；每个 lane 的输入 bytes 精确为 `b"pilot-assessment|sha256-counter-prng-v0.1\0" + ascii(seed) + b"\0" + ascii(modality) + b"\0" + ascii(channel) + b"\0" + index.to_bytes(8,"big") + lane.to_bytes(4,"big")`。令 `digest=SHA256(bytes)`、`m=int.from_bytes(digest[0:8],"big") >> 11`、`u=(m+0.5)/2^53`；使用 lane 0/1 得到 bounded triangular noise `z=u0+u1-1`。通道公式应用自己的固定 amplitude 后，以 IEEE-754 round-to-nearest-even 打包为 little-endian Float32，写入 Parquet 的就是该值；
- manifest 使用 canonical key order；文件名使用 zero-padded stable index；Parquet 固定 zstd level 3、row group 65,536、statistics enabled 和 schema column order；PNG 固定 RGB8、compression level 9、`optimize=false` 且不写 ancillary metadata；
- 同一 lockfile、Windows x86-64、输入 hash 与 seed 下要求 byte-identical bundle；跨平台或依赖版本只要求 canonical logical content 相同，并通过 generator version/lock fingerprint 显式区分；
- source hash、seed、generator version、依赖 lock fingerprint 和所有参数都写入 provenance。

对 duration `T` 与 rate `f`，raw sample count 固定为 `floor(T×f)+1`，source grid 为 `s_k=k/f`。Synthetic device clocks 带入已知 offset/drift。Generator 按 `session_time = scale × source_time + offset` 写入每个 present descriptor 的 `clock_sync`，其中 `scale=1+drift_ppm×10^-6`、residual 为 0、method=`synthetic-declared-truth-v0.1`：

| Stream | Offset | Drift |
|---|---:|---:|
| X/U | 0 ms | 0 ppm |
| I | +4 ms | 0 ppm |
| G | +7 ms | +20 ppm |
| EEG | -12 ms | -15 ppm |
| ECG | +9 ms | +10 ppm |
| pilot_camera | +15 ms | 0 ppm |

Source grid 始终从 0 开始，因此 source timestamp 非负；offset 可使映射后的 session time 落在 session window 之外。本文最初以 `0 <= t_ns <= round(T×10^9)` 描述 M3 synthetic golden mask；自 2026-07-12 批准的 M3 规格 §7 与 D-018 起，权威规则改为 `0 <= t_ns <= max(mapped X primary-table t_ns)`，window source 固定为 `master-clock-x-mapped-coverage-v1`，且不删除 RawStream。当前 2.0 s micro 与 29.01 s captured-format-sample X/U golden 中，X 末样本恰好等于 T，所以两种表达得到完全相同的 frozen counts；未来 `T×f` 非整数时必须以 M3 §7 为准，不再使用 `round(T×10^9)` 推断 session end。

这满足 M1 对 present stream 必须声明 `clock_sync` 的结构要求。M2 只验证并保留 source timestamp 与 mapping，不执行对齐，也不生成最终 authoritative `t_ns`；M3 负责应用 mapping、生成统一 session timebase，并与上述 declared synthetic clock fixture 做 software golden comparison。

## 9. Ingestion 架构

~~~text
contracts/ingestion.py
  IngestionReadinessReport / StreamReadinessResult / status enums

ingestion/models.py
  immutable RawStream / NormalizedStream / PreparedSession

ingestion/profiles.py
  versioned profile loading and validation

ingestion/adapters/base.py
  Adapter protocol

ingestion/adapters/registry.py
  trusted registry keyed by format + schema_id

ingestion/adapters/profiled_csv.py
  combined X/U CSV

ingestion/adapters/parquet_timeseries.py
  G/EEG/ECG/frame/reference tables

ingestion/adapters/image_sequence.py
  PNG dimensions, references and checksum validation

ingestion/readiness.py
  orchestration and deterministic report

synthetic/generator.py
  deterministic full-bundle generation
~~~

Registry 只从受信代码注册，不从 manifest 动态 import Python。Profile 位于 package resources，并由自己的 Pydantic schema 验证。

同一个 shared source 先按 `(path, digest, format, schema_id, shared_source_id)` 分组，只读一次，再生成 X 与 U 两个 logical views。Context 列保存在 PreparedSession context，不复制到每个 stream。

Polars DataFrame 只存在于 adapter/prepared-session 内部。RPC、审计和 Schema 只暴露 Pydantic report 或受管 artifact 引用。

## 10. M2 合同

### 10.1 Stream readiness

~~~text
ready
unavailable
invalid
unsupported
not_applicable
~~~

### 10.2 Readiness disposition

~~~text
ready
ready_partial
blocked
~~~

规则：

- present + adapter success → ready；
- export_pending → unavailable，保留原状态，不调用 adapter；
- missing/invalid required stream → blocked；
- missing/invalid optional stream → ready_partial；
- not_applicable → 不计缺失；
- unregistered required adapter → blocked；
- synthetic full bundle 的七个 core streams 全 ready → ready；
- 只有 X/U ready 且其余 export_pending → ready_partial。

`IngestionReadinessReport` 至少包含：

- contract version、session ID、manifest version；
- scope=`inspect_only_ingestion_content_v1`；
- disposition、`can_continue_to_synchronization`；
- `formal_run_authorized=false`；
- 七个 core modalities 的 deterministic results map，以及独立的 `task_reference_result`；
- 每个 stream 的 declared status、adapter/version、source paths/checksum、row count、timestamp range、observed rate、canonical fields/units、quality summary、assumptions 和 issues；
- deferred checks：synchronization、annotation semantics、anchor availability、BN inference；
- source snapshot fingerprint，用于发现 readiness inspection 期间文件变化。

大数组不进入 report。内部 `IngestionReadinessOutcome` 组合 report 与 PreparedSession；协议层只发送 report。

新增 `ingestion-readiness-report-0.1.0.schema.json`，并与 Pydantic 进行正反例对称测试。

## 11. CSV/stream 质量规则

Profile-driven 默认工程值：

- UTF-8/UTF-8-SIG strict decode；
- CSV delimiter `,`，每行字段数必须一致；
- header 规范化后不得碰撞；
- 必需列必须存在，额外列保留 provenance 但不猜测语义；
- 时间必须有限、非负且严格递增；
- legacy X/U CSV expected sample rate 100 Hz，允许 1% 偏差；其余模态按各自 descriptor/profile 的 15/30/120/250/256 Hz 校验；
- gap threshold = 1.5×median dt；
- required numeric cell 必须有限；单元格错误使用 explicit null/validity，不制造 NaN；
- profile `min_valid_fraction=0.98`，低于门限则 stream invalid；
- constant control/state channel 只产生 info，不判 invalid；
- condition 列若不恒定则 `STREAM_CONTEXT_NOT_CONSTANT` 并阻止该 profile；
- m/s↔kt 残差超过 0.002 kt 则 warning，超过 0.02 kt 则 invalid；
- PNG adapter 禁止动画和 ancillary payload，要求 RGB8、实际尺寸与 frame index 一致；synthetic profile 只接受 64×36 或 48×48，通用安全上限为单图 16 megapixels，Pillow decompression-bomb warning/error 一律阻止 readiness inspection；
- 所有 bytes/rows/columns/string length 使用 adapter resource limits；
- source 在 inspect 与 adapter read 之间变化则 `SOURCE_CHANGED_DURING_READINESS`。

稳定错误码包括：

~~~text
ADAPTER_NOT_FOUND
ADAPTER_CONFIG_INVALID
STREAM_FORMAT_INVALID
STREAM_SCHEMA_MISMATCH
STREAM_TYPE_INVALID
STREAM_UNIT_ASSUMED
STREAM_UNIT_MISMATCH
STREAM_EMPTY
STREAM_TIMESTAMP_INVALID
SAMPLE_RATE_MISMATCH
STREAM_CONTEXT_NOT_CONSTANT
SOURCE_CHANGED_DURING_READINESS
REQUIRED_STREAM_UNAVAILABLE
ADAPTER_EXECUTION_FAILED
~~~

Issue 继续复用 `DomainErrorData`；stream-specific path/column/row 放在 `field_or_path` 与 diagnostics，不复制第二套错误模型。

## 12. 测试策略

### 12.1 Committed fixtures

Git 只保存小型 synthetic fixtures：

- 2 秒、低分辨率、完整 multimodal micro bundle；
- 缺列、header collision、ragged row、非法 UTF-8、null、NaN/Inf；
- duplicate/out-of-order timestamp、rate mismatch、context drift；
- shared X/U path 同/异 checksum；
- Parquet schema/type/unit 错误；
- missing image、frame/gaze binding 错误；
- export_pending/optional/required 状态矩阵。

### 12.2 Local captured-format validation

采集格式样例 CSV 不进入 Git。测试命令显式传入源路径，在 `local_data/` 生成 full bundle，只验证：

- 2,902×33；
- 0–29.01 s、100 Hz；
- X/U 映射、context 提升、kt 一致性；
- synthetic I/G/EEG/ECG/pilot_camera 全 ready；
- manifest/checksum round trip；
- report deterministic；
- 原始 CSV hash 保持不变。

### 12.3 Property 与 contract tests

- 各采样率的 sample count/time bounds；
- seed 相同且 lock/platform 相同则 bundle bytes 相同；seed 不同时允许 signal/image、seed provenance、session ID、checksums/fingerprint 与对应 report 字段变化，但 schema、sample count、phase/event 位置和文件角色不变；
- JSON Schema 与 Pydantic 同时接受 canonical fixture、拒绝 invalid fixture；
- report issue 顺序稳定；
- adapter 不修改 source；
- shared artifact 只读取/哈希一次；
- formal_run_authorized 永远 false。

## 13. 从 M2 到完整网络闭环

完整目标拆成独立可验收里程碑：

| 里程碑 | 交付 | 退出条件 |
|---|---|---|
| M2 | 理想多模态合同、generator、全模态 ingestion readiness | synthetic full bundle 七个 core modalities ready |
| M3 | clock mapping、aligned t_ns、phase/event/baseline/reference | 已知 offset/drift golden tests 通过 |
| M4 | O1–O13、H1–H5 plugin 与 evidence scoring | 18 AnchorResult v0.2 + raw availability/golden trace；差表现仍为 computed evidence |
| M5 | reference graph、CPT、missing/virtual evidence BN | 手算网络与 full synthetic posterior 通过 |
| M6 | pipeline/CLI/report/provenance/replay | bundle→ingestion readiness→synchronization→run preflight→anchors→BN→report 一键跑通 |
| M7 | JSON-RPC sidecar | Python contract 与 .NET fake-client tests 通过 |
| M8 | WinUI 前端 | 编辑、发布、运行和结果页端到端通过 |

M6 的 synthetic result 仍带 `SYNTHETIC TEST DATA`，只能证明软件工作流，不证明评估模型有效。

## 14. Git、隐私与交付

- 当前 Git 仓库只提交代码、profile、schema、小型 synthetic fixtures 和文档；
- 采集格式样例 CSV 与生成 bundle 继续位于仓库外或 `local_data/`；
- 私有 GitHub 仓库不改变“真实 session 不提交”的规则；
- synthetic pilot camera 不包含真人；
- diagnostics 默认不嵌入图像或长信号；
- generator 不读取网络、不使用系统时间、不上传数据。

## 15. M2 验收条件

1. D-011–D-015 写入 DECISIONS，且本规格标记为已批准；
2. M1 全套测试保持通过；
3. shared X/U artifact 的安全与 checksum tests 通过；
4. profile-driven format-sample CSV adapter 在本地实测得到 2,902 rows、100 Hz、X/U/context 正确映射；
5. full synthetic generator 生成七个 core modalities 均 present 的 bundle；
6. 所有 descriptor path/checksum、Parquet schema、image reference 和 clock metadata 通过；
7. `IngestionReadinessReport` Schema 完成并确定性导出；
8. full synthetic report 为 ready、可进入 M3、formal_run_authorized=false；
9. 采集格式样例 CSV 与生成 bundle 未出现在 Git tracked files；
10. pytest、Ruff、ty、build、wheel smoke 与独立 P0/P1 review 全部通过。

## 16. 规格自审

- 规格中的实现决策均已具体化并明确归属；
- M2 与 M3–M8 边界明确，未把 BN/anchor 偷塞进 ingestion；
- 用户要求的五类缺失模态均有理想文件合同与 synthetic 生成方式；
- 当前采集格式样例 CSV 的路径、hash、行列数和时间统计均已复核，但其任务/轨迹/能力语义明确为未提供；
- 所有未知航空/设备语义标为 engineering assumption，不伪装成专家结论；
- synthetic workflow 与 scientific validation 明确分离；
- Git/隐私边界与现有 `.gitignore` 一致。
