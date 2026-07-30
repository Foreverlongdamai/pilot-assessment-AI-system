# References and Evidence Provenance

本文件提供产品设计中直接使用的公开来源入口。正式交付不依赖开发者电脑上的绝对路径，也不把受版权保护的 PDF 随意复制进安装包。页码说明以项目审查时使用的本地 PDF 页序为准；接手者可通过 DOI、出版社或机构仓储核对。

## Internal design provenance

- 18-node mapping、O2/O4/H4/H5 命名和删除 H6：由项目负责人于 2026-07-10 确认，并完整固化在 [04_REFERENCE_MODEL_V0_1.md](04_REFERENCE_MODEL_V0_1.md)。
- 初始阈值与旧 slide 14/16 只作为设计演进证据；当前文档中的公式、状态和版本规则优先。完整研究工作区若存在，可在 outputs/ai_system_framework_reading/rendered/ 中查阅旧渲染图。

## Documentation and architecture references

以下资料只用于 M8 文档信息架构与架构表达，不构成产品认证或对标准正文的替代：

- [ISO/IEC/IEEE 26514:2022 — Design and development of information for users](https://www.iso.org/standard/77451.html)：参考用户信息的受众、任务、结构、内容和维护原则。
- [ISO/IEC/IEEE 42010:2022 — Architecture description](https://www.iso.org/standard/74393.html)：参考 stakeholder、concern、viewpoint 和 architecture view 的表达。
- [Diátaxis](https://diataxis.fr/)：区分 tutorial、how-to、reference 与 explanation。
- [C4 model diagrams](https://c4model.com/diagrams)：以 system context/container 为主、按价值添加 component 的架构图层级。

## R1 Perfect et al. 2015

Perfect, P., Jump, M., & White, M. D. (2015). Methods to Assess the Handling Qualities Requirements for Personal Aerial Vehicles. *Journal of Guidance, Control, and Dynamics, 38*(11), 2161–2172. DOI: 10.2514/1.G000862.

- [DOI](https://doi.org/10.2514/1.G000862)
- [AIAA publisher](https://arc.aiaa.org/doi/10.2514/1.G000862)
- [University of Liverpool repository](https://livrepository.liverpool.ac.uk/id/eprint/2033159/)
- 本设计用途：P、W、W_min、TPX、control movement threshold 与 PIO 构念。

## R2 Lu et al. 2016

Lu, L., Jump, M., White, M., & Perfect, P. (2016). Development of Occupant-Preferred Landing Profiles for Personal Aerial Vehicles. *Journal of Guidance, Control, and Dynamics, 39*(8), 1805–1819. DOI: 10.2514/1.G001608.

- [DOI](https://doi.org/10.2514/1.G001608)
- [AIAA publisher](https://arc.aiaa.org/doi/10.2514/1.G001608)
- [LJMU Research Online](https://researchonline.ljmu.ac.uk/id/eprint/7388/)
- 本设计用途：control RMS、control attack 与 guidance-following deviation。

## R3 White and Padfield 2004

White, M. D., & Padfield, G. D. (2004). Flight Simulation in Academia: Progress with HELIFLIGHT at the University of Liverpool. In *Flight Simulation 1929–2029: A Centennial Perspective*, Royal Aeronautical Society Flight Simulation Conference, London, 26–27 May 2004, Paper 0421.

- [Royal Aeronautical Society conference record](https://raes-fsg.org.uk/conference/58/FLIGHT_SIMULATION_1929-2029%3A_A_CENTENNIAL_PERSPECTIVE/?cid=58&return=%2F13%2FPast_Conferences%2F&rtitle=Past+Conferences+-+2000+-+2009)
- [University of Liverpool author outputs](https://www.liverpool.ac.uk/people/mark-white/research-outputs)
- 未发现可靠 DOI。
- 本设计用途：eye-tracking scene point-of-regard、stabilisation、overshoot 与 control activity。

## R4 Park et al. 2024

Park, J. H., Chen, L., Higgins, I., Zheng, Z., Mehrotra, S., Salubre, K., Mousaei, M., Willits, S., Levedahl, B., Buker, T., Xing, E., Misu, T., Scherer, S. A., & Oh, J. (2024). How is the Pilot Doing: VTOL Pilot Workload Estimation by Multimodal Machine Learning on Psycho-physiological Signals. In *2024 33rd IEEE International Conference on Robot and Human Interactive Communication (RO-MAN)*, 2311–2318. DOI: 10.1109/RO-MAN60168.2024.10731202.

- [DOI](https://doi.org/10.1109/RO-MAN60168.2024.10731202)
- [IEEE Xplore](https://ieeexplore.ieee.org/document/10731202)
- [Open arXiv version](https://arxiv.org/abs/2406.06448)
- 本设计用途：动态 scene-aware gaze 与多模态 workload 处理。

## R5 Wang et al. 2025

Wang, Y., Guo, X., Guo, S., Jiang, F., Liang, Z., Peng, L., & Chai, Y. (2025). Machine learning evaluation model of pilot workload in a low-visibility environment. *Scientific Reports, 15*, Article 20518. DOI: 10.1038/s41598-025-05759-7.

- [DOI](https://doi.org/10.1038/s41598-025-05759-7)
- [Scientific Reports](https://www.nature.com/articles/s41598-025-05759-7)
- 本设计用途：ECG R-peak、HR/HRV features 和 subject baseline。

## R6 van Weelden et al. 2026

van Weelden, E., Prinsen, J. M., Ceccato, C., Pruss, E., Vrins, A., Alimardani, M., Wiltshire, T. J., & Louwerse, M. M. (2026). Prototyping and Evaluating a Real-Time Neuroadaptive Virtual Reality Flight Training System. In *2026 IEEE International Conference on Artificial Intelligence and eXtended and Virtual Reality (AIxVR)*, 11–20. DOI: 10.1109/AIxVR67263.2026.00011.

- [DOI](https://doi.org/10.1109/AIxVR67263.2026.00011)
- [IEEE Xplore](https://ieeexplore.ieee.org/document/11271567)
- [VU Amsterdam research record](https://research.vu.nl/en/publications/prototyping-and-evaluating-a-real-time-neuroadaptive-virtual-real/)
- [Open arXiv version](https://arxiv.org/abs/2512.09014)
- 本设计用途：EEG engagement index、VR flight training 与 pilot-specific calibration。
- 这是 2026 年已发表会议论文；旧本地文件名中的 2025/arXiv 字样不作为正式元数据。

## R7 Heckerman 1995

Heckerman, D. (1995). *A Tutorial on Learning With Bayesian Networks*. Microsoft Research Technical Report MSR-TR-95-06.

- [Microsoft Research publication](https://www.microsoft.com/en-us/research/publication/a-tutorial-on-learning-with-bayesian-networks/)
- 本设计用途：BN 的 directed acyclic graph、local conditional probability distributions、joint factorization 与 posterior inference 基础语义。

## R8 Stanford CS228 course notes

Stanford University. *CS228: Probabilistic Graphical Models — Course Notes*.

- [Stanford course notes PDF](https://web.stanford.edu/~lindrew/cs228.pdf)
- 本设计用途：明确 BN arrow 定义 `P(node | parents)` 的 factorization，而 observation 后可以计算与 arrow 方向不同的 posterior query；用于区分 canonical graph 与 inference information flow。

## R9 Mislevy et al. 2000

Mislevy, R. J., Almond, R. G., Yan, D., & Steinberg, L. S. (2000). *Bayes Nets in Educational Assessment: Where Do the Numbers Come From?* CSE Technical Report 518.

- [ERIC full-text PDF](https://files.eric.ed.gov/fulltext/ED443881.pdf)
- 本设计用途：区分从 work product/session 中提取 observable evidence 的 evidence rules 与用 `P(observable evidence | proficiency/task variables)` 解释证据的 probability model，并由观测反推 proficiency posterior。

## R10 Perfect et al. 2015 — companion PAV study

Perfect, P., Jump, M., & White, M. D. (2015). Handling Qualities Requirements for Future Personal Aerial Vehicles. *Journal of Guidance, Control, and Dynamics, 38*(12), 2386–2398. DOI: 10.2514/1.G001073.

- [DOI](https://doi.org/10.2514/1.G001073)
- [AIAA publisher](https://arc.aiaa.org/doi/10.2514/1.G001073)
- [University of Liverpool repository](https://livrepository.liverpool.ac.uk/2039159/)
- 本设计用途：flight-naive participants、PAV response types、mission-task-element performance，以及安全、精确且可重复操纵所需的 handling-qualities context。
- 署名边界：本论文与 R1 均由 Perfect、Jump 和 White 署名；本项目在吕老师指导下承接这一研究脉络，但不能把两篇 2015 论文写成吕老师署名成果。

## R11 UK road-driver training and testing context

Driver and Vehicle Standards Agency / GOV.UK. Official car theory, hazard-perception, and practical-driving-test guidance.

- [Theory test: multiple-choice questions](https://www.gov.uk/theory-test/multiple-choice-questions)
- [Theory test: hazard perception](https://www.gov.uk/theory-test/hazard-perception-test)
- [Practical driving test: what happens during the test](https://www.gov.uk/driving-test/what-happens-during-test)
- [Practical driving test: marking, faults and results](https://readytopass.campaign.gov.uk/driving-test/driving-test-marking-faults-results/)
- 本设计用途：作为普通读者容易理解的官方实例，说明驾驶评估怎样结合知识、危险感知、真实任务表现和考官记录；它不是世界各地驾驶培训制度的统一描述。

## R12 Rehm et al. 2024

Rehm, J., Reshodko, I., Børresen, S. Z., & Gundersen, O. E. (2024). The Virtual Driving Instructor: Multi-Agent System Collaborating via Knowledge Graph for Scalable Driver Education. *Proceedings of the AAAI Conference on Artificial Intelligence, 38*(21), 22806–22814. DOI: 10.1609/aaai.v38i21.30315.

- [DOI and AAAI proceedings record](https://ojs.aaai.org/index.php/AAAI/article/view/30315)
- [Open conference PDF](https://ojs.aaai.org/index.php/AAAI/article/download/30315/32330)
- 本设计用途：模拟器、事件/时序数据、知识图谱、Bayesian student model 与个性化反馈相结合的相邻领域实例。
- 使用边界：这是已部署的智能驾驶教学研究案例，不代表驾驶执照考试已经普遍采用 Bayesian assessment。

## R13 FAA powered-lift training and certification context

Federal Aviation Administration. *Private Pilot for Powered-Lift Category Airman Certification Standards* and AC 194-2, *Pilot Training and Certification for Powered-Lift Operations*.

- [Private Pilot for Powered-Lift Category ACS](https://www.faa.gov/training_testing/testing/acs/private_pl_acs_13.pdf)
- [AC 194-2 document page](https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentID/1042955)
- [Powered-lift pilot certification and operations final-rule page](https://www.faa.gov/newsroom/integration-powered-lift-pilot-certification-and-operations-miscellaneous-amendments)
- 本设计用途：以官方实例说明 powered-lift 训练/评价按 Areas of Operation 和 Tasks 组织，并结合 Knowledge、Risk Management 与 Skill；不表示本产品获得 FAA 认可，也不表示本产品能替代教员、考官、批准课程或认证程序。
