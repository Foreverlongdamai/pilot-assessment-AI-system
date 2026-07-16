# References and Evidence Provenance

本文件提供产品设计中直接使用的公开来源入口。正式交付不依赖开发者电脑上的绝对路径，也不把受版权保护的 PDF 随意复制进安装包。页码说明以项目审查时使用的本地 PDF 页序为准；接手者可通过 DOI、出版社或机构仓储核对。

## Internal design provenance

- 18-node mapping、O2/O4/H4/H5 命名和删除 H6：由项目负责人于 2026-07-10 确认，并完整固化在 [04_REFERENCE_MODEL_V0_1.md](04_REFERENCE_MODEL_V0_1.md)。
- 初始阈值与旧 slide 14/16 只作为设计演进证据；当前文档中的公式、状态和版本规则优先。完整研究工作区若存在，可在 outputs/ai_system_framework_reading/rendered/ 中查阅旧渲染图。

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
