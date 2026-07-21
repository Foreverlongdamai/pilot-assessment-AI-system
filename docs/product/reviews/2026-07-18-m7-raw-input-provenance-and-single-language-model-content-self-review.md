# M7 Raw-Input Provenance and Single-Language Model Content Amendment Self-Review

| 字段 | 值 |
|---|---|
| Review ID | M7-AMENDMENT-RAW-FAMILY-LANGUAGE-SELF-REVIEW-20260718 |
| 日期 | 2026-07-18 |
| Reviewer | Codex 主代理，inline 自审 |
| 被复核文档 | `specs/2026-07-18-m7-raw-input-provenance-and-single-language-model-content-amendment.md` |
| 范围 | 五大输入族投影、来源连线、单语言模型内容、界面本地化、legacy migration |
| 不覆盖 | 代码实现、可见 WinUI 验收、科学校准、M8 packaging |
| 结论 | 无遗留 P1；规格可提交用户复核，但在批准前不得进入实施 |

## 1. 复核清单

| 检查项 | 结果 | 证据／处理 |
|---|---|---|
| 是否把五个大节点误建成第二套 backend nodes | 通过 | §3、§4.3 明确为确定性 projection，不进入 model hash 或 RunSnapshot |
| 是否把来源归属误当成第三类 canonical edge | 通过 | §4.3 明确 `family provenance link` 只属于显示层 |
| 是否保留精确 Evidence data binding | 通过 | Evidence 仍从细粒度 Raw Input node 读取，族节点不参与执行 |
| 是否按名称前缀猜来源 | 通过 | §4.2 锁定 typed family/raw modality/source dependency closure |
| pilot camera 是否被错误改写为 I(t) | 通过 | 只做 UI auxiliary visual grouping，合同 modality 保持 `pilot_camera` |
| task/reference 是否被伪装成 raw input | 通过 | 无 raw provenance 时显示独立徽标且不建立伪连接 |
| 是否改变现有节点布局数据 | 通过 | 使用 projection-time uniform offset，stored layout/revision 不变 |
| 中文／英文 UI 与模型内容是否分离 | 通过 | §5、§6 将 UI resources 与 English canonical content 分开 |
| 是否仍保留双语 current DTO | 通过 | 新 current contract 只写单字段；legacy reader 只用于迁移和 replay |
| 缺少英文内容时是否静默把中文冒充英文 | 通过 | 使用 ID-derived English placeholder + migration diagnostic，不自动翻译 |
| 是否破坏历史 RunSnapshot | 通过 | 旧 snapshot 原 bytes/hash 不重写，通过 legacy adapter 只读回放 |
| 是否引入“每次专家修改都跑重测试” | 通过 | §9.3 仅要求平台级轻量验证，不验证科学正确性 |
| 是否擅自扩展 Operator 菜单或 Python 编辑范围 | 通过 | §7 明确排除 |
| 五个 family 标签是否错误地被当成英文模型内容 | 通过 | 它们是 UI projection，X/U/I/G/P 符号固定，说明文字随界面语言切换 |

## 2. 发现与修订

### P1-01：新增连线容易与 extraction/probabilistic edge 混淆

- 风险：若 provenance 使用 `ModelGraphEdge`，会出现第三类 backend edge，并污染 scheme/hash/run。
- 修订：规格 §3 与 §4.3 将它定义为 projection-only link，禁止用户增删反转，并要求独立 legend 与视觉样式。
- 状态：关闭。

### P1-02：五类输入与独立 pilot-camera 合同存在表面冲突

- 风险：把 pilot camera 直接改成 I(t) 会破坏“VR 第一视角不是驾驶员相机”的既有数据合同。
- 修订：§4.2 只把 pilot camera 放入 I 的 UI visual-source grouping；物理 modality、clock、schema、privacy 与 Evidence binding 仍独立，并在 tooltip 明示 auxiliary camera。
- 状态：关闭。

### P1-03：删除双语字段可能破坏旧数据库和历史结果

- 风险：直接原地改字段会导致旧 canonical JSON 无法解析或旧 hash 漂移。
- 修订：§5.2 要求新 contract version、transactional current-object migration、legacy reader 和 immutable snapshot 原字节回放。
- 状态：关闭。

### P2-01：要求“内容必须英文”不能可靠自动判断

- 风险：自动语言检测会误拒技术缩写、公式、姓名或领域术语，违背 free-to-modify。
- 修订：§5.1 只通过文档和 localized field hint 规定英文 authoring，不增加语言识别 blocker。
- 状态：关闭。

### P2-02：UI fallback 会再次产生混合语言

- 风险：当前 `[EN fallback]` 机制会直接违反“中文界面全部中文”。
- 修订：§6.1 与 §9.2 把 resource parity 设为 build/packaging gate；current model display 不再使用 bilingual selector。
- 状态：关闭。

### P2-03：新增最左 lane 可能改变全部 stored coordinates

- 风险：批量写回布局会制造无意义 layout revisions，并破坏专家已有布局。
- 修订：§4.1 使用 render-time uniform offset；拖拽时继续换算为原 canonical coordinate，只有用户实际拖动才保存。
- 状态：关闭。

## 3. 一致性判断

- 与 D-037 一致：Raw Input 到 Evidence 的 extraction edge 未改变；
- 与 D-038 一致：BN canonical direction 与 inference overlay 未改变；
- 与 D-047/D-048 一致：五个 family roots 不是可激活的完整节点，不会产生另一套 task model；
- 需要正式修订 D-052：保留即时 UI 语言切换，删除 bilingual canonical metadata；
- 与 D-053 一致：真实模型编辑仍提交 Python backend canonical definitions，family projection 和语言切换除外，因为它们本来就不是模型 mutation；
- 与 M8 候选方向一致：发布系统保留单一可修改模型库和 Python backend，不在这次 M7 修订提前实施 packaging。

## 4. 最终结论

规格已经覆盖用户确认的三个视觉要求：五个更大的输入族节点统一使用绿色并与其他节点类别区分、蓝色细粒度来源节点可溯源；也覆盖新的语言要求：界面完整本地化、模型内容只存英文、没有双语重复字段。用户复核时进一步明确，X/U/I/G/P 之间不需要五套颜色，统一绿色代表共同的“原始输入族”语义；本自审已据此收口。

目前无未关闭 P1/P2。用户已批准该正式规格并补充统一绿色口径；下一步写入 D-054/D-055、同步受影响文档，并使用 `writing-plans` 形成可执行实施计划后进入产品代码修改。

## 5. D-054 实施后复核（2026-07-18）

- 五个 family roots 使用同一个 theme-aware green brush；没有为 X/U/I/G/P 再造五套颜色；
- 当前受管项目实际投影出 X=6、U=3、I=2、G=1、P=2 个来源成员，蓝色细粒度 Raw Input nodes 未改色；
- accessibility tree 同时发现五个 family groups、中文标签、说明和成员数；画布图例明确标注 provenance 为“仅展示”；
- focused `GraphProjectionTests + GraphCommandTests` 为 `12/12`，localization tests 为 `8/8`，x64 Debug build 为 `0 warning / 0 error`；
- 可见窗口确认绿色 family lane、绿色虚线来源边、蓝色 fine-grained nodes 和 canonical BN/Evidence 原有配色同时存在；
- D-055 尚未实施，旧 `[EN fallback]` 仍可见，因此不得把本次 D-054 完成误报为整份 amendment 完成。
