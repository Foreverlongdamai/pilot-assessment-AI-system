# 容差如何适用：考官是否“任何一次超出容差就判不合格”（调研）

日期：2026-11-17 立题，2026-11-18 完成，2026-11-18 按“不用代称缩写”的规定修订文字（内容不变）。用途：为过程型证据的判档规则提供依据，客观呈现两方面证据。该规则已确认为“过程型检查点容许短暂超差、不容许持续超差”（D-015），以及“长窗口中判期望的条件”（D-016）。本文只是调研，不新增决定。

原文下载在 `pilot_assessment_system/tmp/evidence_design_2026-11-18/scn1/review_sources/`。项目原有官方文件在 `current_stage_objectives_2026-07-30/08_assessment_item_design/sources/`。页码写法：“印刷第 x 页”是文件上印的页码；“PDF y”是 PDF 阅读器的页序。所有引文都打开原文核对过，未能核实的见第 7 节。

**本文用到的机构与文件全称（首次出现时）：**

- 美国联邦航空管理局（Federal Aviation Administration，下称 FAA）；其飞行员考试标准为“机组认证标准”（Airman Certification Standards，下称 ACS），旧版为“实践考试标准”（Practical Test Standards，下称 PTS）。
- 欧洲航空安全局（European Union Aviation Safety Agency，下称 EASA）；“可接受的符合性方法”（Acceptable Means of Compliance，下称 AMC）。
- 英国民航局（UK Civil Aviation Authority，下称英国 CAA）。
- 加拿大交通部（Transport Canada，下称 TC）。
- 澳大利亚民航安全局（Civil Aviation Safety Authority，下称 CASA）；其第 61 部“标准手册”（Manual of Standards，下称 MOS）。
- 国际航空运输协会（International Air Transport Association，下称 IATA）；国际民航组织（International Civil Aviation Organization，下称 ICAO）；“基于能力的训练与评估”（Competency-Based Training and Assessment，下称 CBTA）；“循证训练”（Evidence-Based Training，下称 EBT）。
- 美国陆军旋翼机操纵品质规范 ADS-33E-PRF（Aeronautical Design Standard，下称 ADS-33）。
- 期刊 Journal of Guidance, Control, and Dynamics（下称 JGCD）。
- 飞行安全基金会（Flight Safety Foundation，下称 FSF）；“飞行运行品质保证”（Flight Operational Quality Assurance，下称 FOQA）；“咨询通告”（Advisory Circular，下称 AC）。
- 档位：期望（Desired）、可接受（Adequate）、不可接受（Unacceptable）。“期望边界”“可接受边界”指逐帧判断两档的数值界限。

## 1. 结论

1. **飞行考试的容差一般不是“一次超出即不合格”。** FAA、EASA、英国 CAA、TC 的考试标准都把容差写成良好条件下的期望表现。它们都允许考官对不可避免的偏差酌情宽容。典型不合格情形写的是“持续超差”“未及时修正”“反复”“过大”。
2. **也有偏严的一面，而且确有“一次即判”的情形：**
   - 偏差过大。TC 把“超过容差两倍”直接列为严重偏差。
   - 失去控制，或结果令人怀疑。
   - 超出飞机限制。
   - 考官问自己“是否毫无保留地在容差内”。
   - 航空运行中的稳定进近准则：任一条件不满足即复飞。
   - 驾考中的个别项目：压线即不合格。
   但这些是安全门槛或任务完成条件，不是精度分档。
3. **能力评价（IATA、ICAO 的 CBTA）按“多少、多频繁、结果如何”分档，取各维度最低者。** 一次偏差不决定档位，反复出现才降档。
4. **对本项目的含义：**
   - 精度类的过程型证据按“持续多久、是否及时修正”分档。这与“过程型检查点容许短暂超差、不容许持续超差”（D-015）一致。
   - 安全限制、任务未完成、偏差过大（超出可接受边界且持续）可以一次判不可接受，并据此判科目不通过。
   - 长窗口里按“每次超出期望边界不超过 1 s，且期望边界内时间不少于 90%”判期望（第 6 节，已确认为 D-016）。

## 2. 支持“容许短暂超差，看持续与修正”的原文

| 文件 | 条款／位置 | 原文 | 性质 |
|---|---|---|---|
| FAA-S-ACS-13 Private Pilot – Powered-Lift（Nov 2023），即 FAA 动力升力航空器私照 ACS | 附录 1 “Satisfactory/Unsatisfactory Performance”，印刷第 67 页（PDF 72） | 典型不合格情形包括 “Consistently exceeding tolerances stated in the skill elements of the Task.” “Failure to take prompt corrective action when tolerances are exceeded.” | 官方考试标准 |
| FAA-S-ACS-13 | 附录 3 慢速飞行说明，印刷第 72 页（PDF 77） | 短暂触发失速警告而及时修正，“a momentary activation does not constitute unsatisfactory performance on this Task. As with other Tasks, unsatisfactory performance would arise from an applicant's continual deviation from the standard, lack of correction, and/or lack of recognition.” | 官方考试标准 |
| FAA-S-ACS-17 ATP/Type Rating – Powered-Lift，即 FAA 动力升力航空器航线运输驾驶员与型别等级 ACS | 附录 1，印刷第 56 页（PDF 61）；附录 3，印刷第 64 页（PDF 69） | 与 FAA-S-ACS-13 同文 | 官方考试标准 |
| FAA-S-8081-4E Instrument Rating PTS（含 Change 5），即 FAA 仪表等级 PTS | “Unsatisfactory Performance”，印刷第 13 页（PDF 28） | “The tolerances represent the performance expected in good flying conditions.” 不合格理由含 “3. Consistently exceeding tolerances stated in the Objectives. 4. Failure to take prompt corrective action when tolerances are exceeded.” | 旧版官方考试标准（PTS） |
| FAA-S-8081-16B（Feb 2013） | 印刷第 9–10 页（PDF 25–26） | 与 FAA-S-8081-4E 同文 | 旧 PTS |
| FAA-S-8081-15A（Jul 2005） | 印刷第 8 页（PDF 20） | 同上 | 旧 PTS |
| FAA Order 8900.2C（2018-06-26；FAA 目录显示已于 2025-03-10 注销） | 图 7-10 Pilot Examiner Test Guide，第 7-168 页（PDF 278） | “Advise the applicant that: … Perfection is not the standard” | 考官指南（已注销） |
| FAA-H-8083-9B Aviation Instructor's Handbook，即 FAA 航空教员手册 | 第 6-6 页（PDF 137） | Perform 级：“The learner will identify and correct errors and deviations in an expeditious manner.” | 官方教学手册 |
| EASA Easy Access Rules for Aircrew（Nov 2025），即 EASA 机组规章汇编 | AMC2 FCL.1015(o)，第 1215 页 | “Although test or checks may specify flight test tolerances, an applicant should not be expected to achieve these at the expense of smoothness or stable flight. An examiner should make due allowance for unavoidable deviations due to turbulence, ATC instructions, etc.” | 符合性指导（AMC） |
| 同上 | Part-FCL Appendix 9 Section C（直升机）仪表飞行容差，第 1391 页 | 2D/3D 线性横向偏差 “shall normally be limited to ± ½ of the RNP value … Brief deviations from this standard up to a maximum of one time the RNP value are allowable.”（RNP 指所需导航性能） | 法规附录 |
| 同上 | Appendix 9 Section D（动力升力航空器）第 3 条，第 1401 页 | “The following limits shall apply, corrected to make allowance for turbulent conditions and the handling qualities and performance of the powered-lift aircraft used.” | 法规附录 |
| 同上 | AMC2 FCL.235(d)（直升机私照），第 211 页 | “The following limits are for general guidance. The FE should make allowance for turbulent conditions and the handling qualities and performance of the helicopter used.” | AMC |
| 英国 CAA Standards Document 19(H) V7（Feb 2026），即直升机考官标准文件 | 附录 2 “PPL Skill Test Tolerances to be Applied”，印刷第 31 页 | “The tolerances for operation are given as guidance to applicants but do not necessarily indicate that a 'failure' will result if any skill test limit is exceeded. Similarly, flight within the tolerances should not be achieved at the expense of smoothness and co-ordination.” | 国家考官标准 |
| TC TP 13462E Flight Test Guide – CPL Aeroplane（6th ed., Jan 2021），即飞机商照飞行考试指南 | “Conditions”，印刷第 10 页 | “Consideration will be given to unavoidable deviations from the published criteria due to weather, traffic or other situations beyond the reasonable control of the candidate.” | 国家考试指南 |
| 同上 | “Deviations”，印刷第 11 页 | “A minor deviation is defined as a deviation that does not exceed a specified tolerance.” “A major deviation is defined as a deviation that exceeds a specified tolerance or repeated minor deviations without achieving stability.” “A critical deviation is defined as a major deviation that is repeated, excessive or not corrected, such as: Repeated non-adherence to specified tolerance limits; or More than doubling the specified value of a tolerance limit; or Not identifying and correcting major deviations.” | 同上 |
| 同上 | “4-Point Marking Scale”，印刷第 12 页 | “award the mark that best describes the weakest element(s)”。3 分：“Aircraft handling with appropriate control input but includes minor deviations”；2 分：“major deviations and/or an occasional lack of stability, over/under control or abrupt control input”；1 分：“critical deviations and/or a lack of stability, rough use of controls or control of the aircraft is lost or in doubt” | 同上 |
| CASA Part 61 MOS（Compilation 6，2024-11-19） | Schedule 7 Appendix L 第 1.5 条，第 727 页（第 4 卷 PDF 129）；Appendix N、O、Q 同类条款 | “a sustained deviation outside of the applicable flight tolerance is not permitted.”（飞行复训审查标准） | 法规性标准 |
| IATA Competency Assessment and Evaluation for Pilots, Instructors and Evaluators – Guidance Material（4th ed., 2025） | §8.2，印刷第 17–18 页；§8.2.4，印刷第 22 页 | 维度为 “How many OBs … How often … outcome”；“The "HOW OFTEN" dimension provides evidence related to the robustness of the competency.”；“the "HOW WELL" terminology which reflects the lowest level of each dimension” | 行业指导材料 |
| IATA EBT Implementation Guide（Ed. 2, 2024） | 印刷第 57 页（PDF 70） | 五档 “ineffectively/minimal acceptable/adequately/effectively/exemplary manner”，“graded 3 or above on a 5-point scale” | 行业指导材料 |
| 美国陆军 TC 1-240 Aircrew Training Manual CH-47D/F（2007-10-24），即 CH-47 机组训练手册 | 3-2b(2)，第 3-2 页 | “Task standards are based on an ideal situation. … If other than ideal conditions exist, such as high winds, turbulence, or poor visibility, the evaluator should consider those conditions while grading the maneuvers.” | 军方训练手册 |
| ADS-33（2000） | §3.11 性能标准，印刷第 25 页 | “These performance limits are set primarily to drive the level of aggressiveness and precision to which the maneuver is to be performed.” | 操纵品质规范（评飞机，不评飞行员） |
| 同上 | 印刷第 26 页 | 未达标时 “it is acceptable for the evaluation pilot to make as many repeat runs as necessary to insure that this is a consistent result.” | 同上 |
| Perfect、Jump、White（2015），JGCD 38(12) | 第 2387 页 | “precision is measured as the proportion of task time spent within the desired performance boundaries” | 学术文献 |
| 同上 | 第 2392 页 | “If a requirement for safe PAV flight was for a pilot to be able to remain within the desired performance tolerances of the tasks for 90% of the time …”；“achieving 90% time spent within desired performance”（PAV 指个人飞行器） | 学术文献（作者设定的判据） |
| Hoefinger、Blanken、Strecker（美国直升机学会第 62 届年会 2006，德国宇航中心） | PDF 第 9 页（无印刷页码） | 分析评分分散时：“Minor discrepancies are acceptable. But if there are striking differences (e.g. pilot rates "clearly within desired", but large parts of the measured track are outside desired or even adequate) …” | 学术文献（ADS-33 试飞评价） |

## 3. 偏严的一面

| 文件 | 位置 | 原文 | 说明 |
|---|---|---|---|
| FAA Order 8900.2C | 图 7-10，第 7-169 页（PDF 279） | “If you can answer YES to each of these questions without reservation, the applicant has satisfactorily completed the task.” 同页：“No second chance when maneuver is unsatisfactory” | 问题之一是“是否在容差内完成”。同页仍列 “Consistently exceeding tolerances”“Failure to take prompt corrective action” 为不合格情形 |
| FAA-S-8081-4E | “Satisfactory Performance”，印刷第 12 页（PDF 27） | “successful outcome of each Task performed never seriously in doubt” | 出自旧 PTS。现行美国联邦法规第 14 篇 61.43(a) 没有这句话，见下一行 |
| 美国联邦法规第 14 篇 61.43(a)（现行；经康奈尔大学法律信息研究所转载的电子版文本核对） | (a)(2)–(3) | “Demonstrating mastery of the aircraft by performing each task … successfully; (3) Demonstrating proficiency and competency of the tasks … within the approved standards” | 法规只写“在批准的标准内”，没有说明容差如何适用 |
| EASA Appendix 9 Section D | 第 2(e) 条，第 1401 页 | “maintain control of the powered-lift aircraft at all times in such a manner that the successful outcome of a procedure or manoeuvre is never in doubt” | 失控或结果存疑是一次性失败 |
| EASA AMC2 FCL.1015 | (o) 后列的不合格条件 (i)，第 1216 页 | “the flight test tolerances have been exceeded after the examiner has made due allowance for turbulence or ATC instructions” | 考官酌情宽容之后仍超出，就构成不合格理由 |
| TC TP 13462E | 印刷第 11 页 | “More than doubling the specified value of a tolerance limit” | 一次超过两倍容差即为严重偏差，不论持续多久 |
| CASA Part 61 MOS | Schedule 8 Table 1 第 2.1 条，第 736 页 | “A person is required to perform flight manoeuvres within the flight tolerances mentioned in this table to be assessed as competent” | 考试标准写成必须在容差内。“sustained deviation” 的宽限只出现在 Schedule 7 的复训审查标准里；在 MOS 全文中检索不到 “momentary deviations” 一类的写法 |
| 美国陆军 TC 1-240 | 4-1d，第 4-3 页 | “The terms "without error," "properly," and "correctly" apply to all standards. The standards are based on ideal conditions.” | 同一手册 3-2b(2) 又要求考虑非理想条件 |

## 4. “一次即判”的反例：它们用于运行安全门槛或任务完成，不用于分档

| 领域 | 文件与原文 | 用途 |
|---|---|---|
| 稳定进近 | FSF 进近着陆事故预防简报 7.1（Flight Safety Digest, Aug–Nov 2000）第 134 页表 1：“An approach is stabilized when all of the following criteria are met”。原文排版中这句与右栏交错，连起来读是 “An approach that becomes unstabilized below 1,000 feet above airport elevation in IMC or below 500 feet above airport elevation in VMC requires an immediate go-around.”（IMC、VMC 指仪表、目视气象条件） | 运行决策：任一条件不满足就复飞，与飞行员技能分档无关 |
| 同上 | FAA AC 120-71B（2017-01-10）§1.3：“The stabilized approach criteria has been removed from this AC and can be found in AC 91-79A” | AC 91-79A 本次未下载核对 |
| 飞行数据监控 | FAA AC 120-82 FOQA（2004）第 6(3)(a) 段，第 9–10 页：“Exceedence Analysis. This involves setting a specific limit … to detect each time the aircraft roll angle exceeds 45 degrees. This data can be trended over multiple flights …”。第 24 页：“protective provisions to its pilots against disciplinary or other pejorative action” | 超限事件逐次检测，但用于趋势监控，不用于处分或考核 |
| 英国驾考 | gov.uk “Driving test faults and your result”（2026-11-18 访问）：“a driving fault - this is not potentially dangerous, but if you keep making the same fault, it could become a serious fault.” “You'll pass … if you make: no more than 15 driving faults … no serious or dangerous faults” | 小错累计，重复同一错误会升级为严重错误；危险错误一次即不合格 |
| 中国驾考科目二 | GA 1026—2022《机动车驾驶人考试内容和方法》（第三方托管副本，封面注“以正式出版稿为准”）6.2.3.5 曲线行驶、6.2.3.6 直角转弯：“车轮轧道路边缘线的，不合格”。对照 6.2.3.4 侧方停车：“行驶中车轮触轧道路边缘线或库位边线的，每次扣 10 分” | 同一标准里，压线在某些项目一次即不合格，在另一些项目只扣分。区别在于这条线在该项目中是否代表不可越过的边界 |

## 5. 综合判断

1. **精度容差：** 主流飞行考试把它当作良好条件下的期望表现。考官需要酌情宽容，不合格看“持续、反复、未修正”。D-015 的“连续超出可接受边界超过 1 s 为不可接受、短暂超出为可接受”与此一致。TC 的三级偏差在结构上与期望、可接受、不可接受三档对应：minor 在容差内，major 超出容差，critical 为反复、过大或未修正。
2. **“过大”可以一次即判。** TC 的界限是两倍容差。本项目的可接受边界大约是期望边界的两倍：速度 5→10 节，航向 5°→10°，横向 10→20 英尺（3.05→6.10 m，D-017）。所以“越过可接受边界且持续”判不可接受，与 TC 的 critical deviation 在结构上相符。
3. **安全门槛与任务完成条件按“一次即判”。** 包括失去控制、超出飞机限制、任务目标未达成（例如最终停点不在停止区内）、稳定进近类的运行门槛。这些在本项目中用于判科目通过与否，不作为精度分档。
4. **能力分档按频率与结果取最低者（IATA）。** 适合把多次事件汇总为一个档位。例如减速平顺性证据中的来回推拉次数、末端修正证据中的无效修正与反复修正次数。

## 6. 对本项目的具体建议（已按 D-016、D-019～D-021 确认）

| 情形 | 判法 | 例子 |
|---|---|---|
| 安全限制、失控 | 一次即判不可接受，科目不通过 | 本场景 CSV 没有飞机限制字段。以后加入限制字段时适用 |
| 任务未完成 | 一次即判不可接受，科目不通过 | “直线飞行与速度变换”中记录完整而始终未达到 25 节；“受控减速与定点停止”的检查点一 最终停点精度（phase 2 结束仍在移动，或最终在停止区外） |
| 精度类过程 | 按持续时间判档（D-015），长窗口按下文（D-016） | “直线飞行与速度变换”的速度建立与保持、横向航迹与航向；“受控减速与定点停止”的减速航迹与航向（检查点二） |
| 操纵与修正 | 按次数和类别汇总，取各维度最低者（IATA） | 减速平顺性的来回推拉次数、末端修正 |

**长窗口的写法（已确认，D-016）。** 判期望的条件为：“每次超出期望边界不超过 1 s，且期望边界内时间不少于 90%”。判不可接受与判可接受的前两条不变。这样短窗口与长窗口都容许零星的短暂超差，但不容许超差占用太多时间。

- 90% 来自 Perfect 等（2015，第 2387、2392 页）。该文以期望边界内的时间比例度量精度，并用“90% time spent within desired performance”作判据。原文这一判据是作者以假设语气提出的（“If a requirement … was …”），不是法规。
- 场景一三条过程型证据在 65 趟上用 D-016 与 D-015 原写法相比：速度建立与保持、横向航迹与航向结果完全相同；减速航迹与航向（检查点二）在 D-017 的横向边界下有 1 趟不同（16_06_54：两次超出期望边界各不超过 1 s、累计 1.18 s，D-015 原写法为可接受，D-016 为期望）。复算：`pilot_assessment_system/tmp/evidence_design_2026-11-18/scn1/run_all.py`，见[场景一证据设计](../plans/2026-11-18-evidence-scn1.md)第 2.1 节。

## 7. 未能核实或未找到的引用

- FAA Order 8900.1 Vol 5 Ch 3 Sec 2 中 “deviate briefly … should be considered to have met the standard” 一类的写法：FAA 飞行标准信息管理系统网站无法访问，**未核实**，本文不使用。
- ICAO Doc 9995（Manual of Evidence-based Training）的分级原文：下载被拦截，**未核实**。CBTA 分级改用已核实的 IATA 文件。
- CASA Part 61 MOS 中关于 “momentary deviations” 的说法：全文检索**未找到**。已核实的只有 Schedule 7 的 “sustained deviation … is not permitted”。
- FAA AC 91-79A（稳定进近准则的现行位置）：未下载核对。
- 加拿大直升机飞行考试指南：未检索。本文用的是飞机商照指南 TP 13462E。
