# 评估型贝叶斯网络怎样设计：文献调研

日期：2026-11-17。用户问题：逐帧更新、固定证据量κ都不像成熟做法，这一类根据过程表现评估能力的贝叶斯网络应该怎样设计？

方式：三条线并行检索。（1）教育测量中的评估型贝叶斯网络；（2）密集自相关证据与跨次能力追踪的统计方法；（3）飞行、外科、驾驶等模拟器技能评估系统。引文由检索者实际打开原文核对；标“未核实”的只见于二手引用或摘要。2026-11-17另抽查了Almond 2015、Almond等2013、Mislevy与Gitomer 1995三篇原文的关键句。本文在[2026-09-16文献核查](2026-09-16-sequential-bayes-literature-notes.md)（Mislevy等1999、Almond等2009、Levy 2014、Corbett与Anderson、Saada等2014、Bissiri等2016）基础上补充，不重复其内容。

## 1. 结论

1. **证据单位是“一次动作中一个检查点的结果”，不是帧。** 能核实的系统都先在单次任务内用规则把过程压缩成少量观测量（证据识别），每个观测量每次任务进入网络一次（证据累积）。更新次数由任务结构决定，即检查点数乘以动作实际发生的次数，不需要另设κ。没有找到把固定频率采样帧当作重复独立证据输入静态能力节点的系统。
2. **每个观测量的证据强度写在它的CPT参数里。** 常用等级反应模型：区分度α表示证据强度，阈值β表示达到某档的难度。教育测量中区分度约1为常见，超过2往往意味着估计有问题。现行CPT一个U对“高／低”的对数似然比为 ln(0.001/0.65) = −6.5，已是很强的单次证据。
3. **能力只设低／中／高三点，证据多了后验会塌到一个顶点。** 分数会跳到0、50或100。改用7～11个等距点的能力格或连续能力θ，报告后验均值、标准差和各档概率；证据增多只让标准差变小，均值稳定。
4. **多次训练之间能力会变化。** “本次表现分”与“能力档案”分开：前者每次从同一先验计算，后者在两次训练之间加入过程噪声（遗忘）再传递。
5. **门控保持不可补偿。** CBTA以各维度中最低者定档，FAA ACS任一任务不合格即不合格，均不以分数平均抵消。

## 2. 证据单位：证据识别与证据累积

证据中心设计（Evidence-Centered Design，ECD）把评估分成两步：证据规则在**单个任务内**识别并概括证据，形成观测量；测量模型在**任务之间**累积证据。观测量的权重（weights of evidence）是测量模型的参数，例如IRT的题目参数。[Mislevy、Almond、Lukas 2004，CSE Report 632，pp.10–11、15–16，术语表](https://files.eric.ed.gov/fulltext/ED483399.pdf)

证据识别总在单个情境内进行，目的是把工作成果压缩成少量变量；不同情境的观测量在给定潜在能力时条件独立，网络因此可以分解为能力模型与各证据模型。[Almond、Kim、Shute、Ventura 2013，Debugging the Evidence Chain，UAI 2013应用研讨会，CEUR Vol-1024，pp.1–10](https://myweb.fsu.edu/vshute/pdf/Debugging.pdf)

| 系统 | 观测量从哪来 | 每次任务进入几次 | 重复与相关 |
|---|---|---|---|
| HYDRIVE，F-15液压故障排查 [Mislevy、Gitomer 1995，CSE TR 413](https://cresst.org/wp-content/uploads/TECH413.pdf) | 约25条规则把原始操作解释为“系统排除”“冗余”等 | 每识别出一个情境计一次；情境“could arise many times or not at all” | CPT来自专家意见并用轨迹核对；学习“only at problem boundaries”更新 |
| DISC，牙科模拟（CSE 632，pp.10–11） | 每个病例5个评分观测量 | 每个病例一次 | 用情境变量处理同一表现多个方面之间的相关 |
| NetPASS，网络工程 [Levy、Mislevy，CSE Report 619](https://files.eric.ed.gov/fulltext/ED483385.pdf) | 每个设计任务2个观测量 | 每个任务一次 | 同一任务的观测量加情境变量；CPT为等级反应模型，先专家赋值再用预试数据（MCMC）修正 |
| Physics Playground（[Rahimi、Almond、Shute，架构章节](https://myweb.fsu.edu/vshute/pdf/architecture.pdf)） | 每关的金／银／无奖杯、计数和计时 | 一关结束时生成一条观测记录送入网络 | 同一场次同一关的所有尝试作为一个任务 |
| SimCityEDU [Mislevy 2024，Psychometrika 89(1):64–83，pp.77–79](https://www.cambridge.org/core/services/aop-cambridge-core/content/view/92754CC0D0A38C63C6A2152D5F131142/S0033312300000466a.pdf/sociocognitive_and_argumentation_perspectives_on_psychometric_modeling_in_educational_assessment.pdf) | 原始事件 → 游戏动作 → 策略模式 → 计数、多样性、有效性 | 每个挑战一个观测向量 | θ在一个挑战内不变，进入下一挑战时更新；直接从最底层观测建到最高层构念“usually does not work well” |
| 虚拟驾驶教员VDI [Rehm等2024，AAAI-24 38(21):22806–22814]（本地全文 `outputs/ppt_ai_assessment/rehm_vdi_text.txt`） | 70多个规则智能体按驾驶情境（路口、超车）记录表现，A–F评分 | 每场训练结束后更新学员贝叶斯网络（165项技能，掌握／学习中／困难） | CPT来自教员生成的数据；上次后验作为下次先验；同一场次内同一情境多次出现如何合并未说明 |
| IATA CBTA指导材料 [第3.1、8.2、9.2节](https://www.iata.org/contentassets/c0f61fc821dc4f62bb6441d7abedb076/competency-assessment-and-evaluation-for-pilots-instructors-and-evaluators-gm.pdf) | 按可观察行为逐事件记录 | 评估计划规定“the number of observations required” | 维度中最低者定档；同一能力连续两次2级触发补训；无概率模型 |

外科模拟器把整段轨迹作为一个序列交给HMM，转移矩阵承担帧间相关，不把帧当作独立证据：Rosen等2001（IEEE TBME 48(5):579–591）、Reiley与Hager 2009（MICCAI，pp.435–442）、JIGSAWS（[Ahmidi等2017，IEEE TBME 64(9)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5559351/)）都需要按熟练度分组的标注数据；[Leong等2007，Computer Aided Surgery 12(6):335–346](https://europepmc.org/article/MED/18066949)以留一法的群体模型计算相似度，不需要技能标签。Mackel等2007（[MMVR 15，pp.316–318](http://bionics.seas.ucla.edu/publications/CP_27.pdf)）15名专家对15名新手分类只有约60%，提示小样本风险。

## 3. 证据强度：CPT参数化

Almond提出的IRT式CPT：父节点各状态映射到“有效θ”（三状态为 Φ⁻¹(1/6)、0、Φ⁻¹(5/6)，约 −0.97、0、0.97），再经连接函数得到概率。等级反应模型为 P(X ≥ s | θ) = logit⁻¹(1.7·α(θ − β_s))，α为区分度，β_s为各档阈值。专家给定的参数作为CPT的Dirichlet先验，再用广义EM在数据上修正；先验权重约10个虚拟样本是常用折中。[Almond 2015，BMAW 2015，CEUR Vol-1565，pp.14–23](https://ceur-ws.org/Vol-1565/bmaw2015_paper4.pdf)

区分度“measures of the strength of the association between the observable and the proficiency variable”；高利害考试中约1为常见，低于0.5偏低，高于2常提示估计困难。Newton's Playground的专家参数与后测相关偏低，后来用前后测成绩作为能力代理重新拟合，这一步属于外部效标。（Almond等2013，pp.5–6）

现行CPT按该框架反推，“D”的区分度约1.0～1.7，“至少A”约1.8～2.7；单个U对高／低的对数似然比 −6.5。每次动作计一次已属强证据；按100 Hz逐帧计入，相当于每秒数百个强证据。

## 4. 能力尺度与分数

固定一组档位分布，证据量N变化时三类潜变量的分数（现行CPT，表现为70% D、20% A、10% U，2026-11-17复算）：

| N | 0 | 1 | 3 | 10 | 30 | 100 | 300 | ≥1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 分数 | 50 | 60.1 | 70.5 | 73.9 | 71.8 | 64.9 | 53.6 | 50.0 |

分数先升后降，最终落在与观测最接近的那一行CPT（此例为“中”，KL散度最小）。原因有两个，需要分开处理：（A）帧间自相关导致重复计数，造成100 Hz与10 Hz不一致；（B）三点能力与观测分布不匹配，导致后验塌到顶点。

- 离散能力格：Haberman、von Davier、Lee 2008比较潜变量分布的选择，7、9或11个等距点与正态潜变量的拟合差异很小。[ETS RR-08-45，p.1、pp.18–19](https://files.eric.ed.gov/fulltext/EJ1111283.pdf)
- 连续θ：长测验下给定作答的能力后验近似正态。[Chang、Stout 1993，Psychometrika 58:37–52](https://link.springer.com/article/10.1007/BF02294469)。模型有偏差时后验集中在KL最优点附近（Kleijn、van der Vaart 2012，经Wu、Martin转引）。均值随表现平滑变化，证据增多只让方差缩小。
- 报告方式：BN评估工具Peanut提供后验期望、后验标准差和各档边际概率（[PnodeEAP等说明](https://raw.githubusercontent.com/ralmond/Peanut/master/man/Statistic.Rd)）。

## 5. 同一次动作内检查点之间的相关

三种做法：（1）情境变量，作为同一次表现所有观测量的共同父节点，不报告（DISC、NetPASS）；（2）题组随机效应（Bradlow、Wainer、Wang 1999，未核实原文）；（3）把整组观测量合成一个多级观测量（Sireci、Thissen、Wainer 1991，未核实原文；忽略相关会高估信度）。估计相关强度需要大量受测者，NetPASS因此用MCMC。本项目数据量下，相关结构只能按设计固定。

## 6. 过程型检查点怎样变成一个观测量

Rahimi等给出时长类观测量的做法：落在可接受范围外记0、范围内记1、低于范围记2，评分后即交给证据累积。[Rahimi、Almond、Shute、Sun，Psychometrics of Stealth Assessment，章节预印本p.23](https://myweb.fsu.edu/vshute/pdf/psychometrics.pdf)

Sun等2023把仪表飞行的泪滴程序分成5个阶段，每阶段对俯仰、横滚、航迹等可观察行为打分，再汇总成CBTA等级。[Cognition, Technology & Work 25:345–356](https://d-nb.info/1315493349/34)

本项目对应做法：过程型检查点按规则把整段D/A/U过程概括为一次动作的一个档位，例如结合持续超差时长与是否及时修正（讨论稿8.1已引用FAA-S-ACS-2附录1关于持续超差与及时修正的要求）。

整段序列直接建模（HMM或连续时间马尔可夫链）也是可选方案。文献中的版本都需要分组标注；一种不需要标注的构造是令各能力类的转移矩阵为 A_s = ρI + (1−ρ)·1·θ_sᵀ，平稳分布等于该类CPT行，ρ由全部记录的切换率估计。该构造为调研者推导，未见文献。它消除采样率影响，但证据仍随时长增长。

## 7. 若保留“加权”方式的统计依据（备查）

| 方法 | 作用 | 来源 |
|---|---|---|
| 粗化后验 π(θ)Πp_θ(x_i)^{α/(α+n)} | n很大时证据量饱和于α，相当于固定证据预算；α可按预期偏差大小选取 | [Miller、Dunson 2019，JASA 114(527)，eqs.2.2–2.3，Supplement p.S6](https://jwmi.github.io/publications/C-posterior-extended.pdf) |
| 复合似然幅度调整 k = p/Σλ_i（H⁻¹J的特征值） | 单参数时等价于权重 = 1/积分自相关时间，修正帧间重复计数 | [Ribatet、Cooley、Davison 2012，Statistica Sinica 22，§2.1](https://www3.stat.sinica.edu.tw/statistica/oldpdf/A22n217.pdf)；[Pauli等2011](https://www3.stat.sinica.edu.tw/sstest/oldpdf/A21n16.pdf)；[Varin等2011](https://www3.stat.sinica.edu.tw/sstest/oldpdf/A21n11.pdf) |
| 学习率选择：信息匹配、SafeBayes、GPC | 选择似然的幂；比较研究认为GPC总体最适用，但都只在独立同分布数据上比较 | [Holmes、Walker 2017](https://arxiv.org/pdf/1701.08515)；[Lyddon等2019](https://arxiv.org/pdf/1709.07616)；[Grünwald、van Ommen 2017](https://arxiv.org/pdf/1412.3730)；[Wu、Martin](https://arxiv.org/pdf/2012.11349) |

现行第9节的κ在数学上可解释为粗化后验的α；按其“预期偏差”取值法估算约2.4，与κ=3接近（调研者推算，非原文）。1/自相关时间的权重能消除采样率影响，但证据仍随时长增长，也不解决三点能力的塌缩。这些方法回答“怎样给一串相关数据定权”，不改变“证据应按任务计入”这一测量学做法。

## 8. 跨动作与跨训练

- HYDRIVE在问题之间把当时后验与无信息分布混合，表示学习带来的变化；SimCityEDU的θ在挑战内不变、挑战之间更新。
- BKT标准版不含遗忘；Khajah、Lindsey、Mozer 2016：“Without forgetting, once BKT infers that the student has learned, even a long run of poorly performing trials cannot alter the inferred knowledge state.”[arXiv:1604.02416，§2.1](https://arxiv.org/pdf/1604.02416)
- Glicko：未参赛期间评分不确定度按 √(RD² + c²t) 增大，c按“多久后回到未评级的不确定程度”设定。[Glickman，glicko.pdf，p.6](https://www.glicko.net/glicko/glicko.pdf)
- TrueSkill：区分单次表现p与技能s，p ~ N(s, β²)；技能在两次之间加方差τ²。[Herbrich、Minka、Graepel 2006，NIPS，pp.2–3](https://papers.nips.cc/paper/2006/hash/f44ee263952e65b3610b8ba51229d1f9-Abstract.html)
- “上次后验作为下次先验”只在能力不变时精确；能力变化时应先做预测步（离散：乘转移矩阵；连续：方差加 q·Δt）。

## 9. 航空领域现状

直接以模拟器飞行数据更新飞行员潜在能力贝叶斯网络、并公开证据模型的研究，本次未找到。相关工作：

- 刘浩等2021用动态贝叶斯网络识别飞行动作，再按动作选指标、组合赋权、灰色模糊评价。[航空学报42(8):525838](https://hkxb.buaa.edu.cn/CN/10.7527/S1000-6893.2021.25838)
- 沈一超等2017用贝叶斯网络分类飞行动作。[计算机工程与应用53(24)](http://cea.ceaj.org/CN/10.3778/j.issn.1002-8331.1707-0156)
- Chen、Huang 2018以484份事故报告构建机组表现贝叶斯网络，非模拟器数据（Entropy 20(3):178）。
- Ernstsen、Nazir 2020用贝叶斯网络加层次分析法评估海事引航模拟器表现，作者称尚未获得构念效度证据（Safety Science 129:104775）。
- STI SimAssist、Frasca SimAssist未公开推断模型。

国内文献中贝叶斯网络主要用于动作识别与分段，评分仍由指标加权完成。

## 10. 对本系统的设计启示

| 层级 | 做法 | 是否需要标注数据 |
|---|---|---|
| 证据识别 | 每个检查点每次动作产出一个D/A/U观测量；过程型检查点用规则概括整段过程（持续超差、及时修正） | 否 |
| 更新时机 | 检查点结果形成时更新一次；每次动作共更新K次（K为检查点数）；逐帧D/A/U色带与原始曲线保留作复盘 | 否 |
| 证据强度 | 等级反应模型CPT，每个检查点设区分度α_k与阈值β_k，取代κ与等权；区分度以约1为常规锚点 | 否（设计值）；用数据修正时为无监督 |
| 能力尺度 | 7～11点能力格或连续θ；报告后验均值、标准差、低／中／高档概率 | 否 |
| 检查点相关 | 按设计固定（情境变量或合成观测量），不从数据估计 | 否 |
| 参数修正 | 可在65趟场景一记录上用边际极大似然／EM修正β（先验权重约10）；单一飞行员、含学习过程，作核对而非定论 | 否 |
| 多次动作 | 悬停4次、升降3次各作为一次任务计入，同一场次共享θ | 否 |
| 跨次训练 | 本次表现分从共同先验计算；能力档案在两次训练之间加入随间隔增大的过程噪声后传递，噪声参数可由65趟时间序列估计 | 否 |
| 门控 | 维持不可补偿规则，与分数分开 | 否 |
| 内部检验 | 100 Hz与10 Hz结果一致；前2/3预测后1/3；跨实例折半一致；参数敏感性 | 否 |

声称“与教员评分一致”“预测效度”等结论需要外部标注，本项目按D-008不获取，因此不作此类表述。

## 11. 文献没有解决的问题

- 检查点阈值、区分度取值属于设计工作；文献的做法是把这些选择写成明确的CPT参数并用数据核对，而不是免除这些选择。
- 学习率选择方法都只在独立同分布数据上比较，未直接处理自相关帧。
- 除粗化后验的经验法外，没有每次任务固定证据预算的通用规则。
- HMM技能分类的已发表版本都使用分组标注。
- 单一飞行员数据估计的追踪参数能否推广到其他飞行员，没有依据。
