# Offline dynamic-state comparison

Synthetic grades only. No application changes, fitted parameters, real-pilot accuracy or training-effectiveness claim.

56 deterministic runs; theta/pi/tau as PLAN.md. EAP=0*P(L)+50*P(M)+100*P(H). Raw-frame CPT is a negative control, not a recommended observation model.

## 主要发现（中文）

1. 固定能力模型有历史锁定：300 秒 D 后，5 秒 U 全段仍约 100 分；30 秒 D 后则在首次 U 降至 60.75，U+4.9 秒降至 47.42。这里比较的是相同后续轨迹，仅改变前段历史时长。
2. 动态状态改善历史锁定，但观测模型仍需调整。相关观测 DBN 的 Tskill=20 秒时，300 秒 D 后首次 U 降至 3.25；持续 U 到 4.9 秒却回升至 9.87。原因是状态预测向均匀先验漂移，而同档 U 的新证据较弱，不能把这个行为解释成飞行员已经恢复。
3. 仅逐帧使用 CPT 的真正 HMM 是负对照：100 Hz 下约 0.01 秒达到 EAP<=25，回 D 约 0.04 秒达到 EAP>=75（Tskill=20）。10/100 Hz 同时刻曲线最大差 86.07 分，暴露原始帧独立似然的采样率依赖。
4. 相关观测 DBN 在本实验所有采样对比中的最大 EAP 差为 0.1492 分；这是这些规则合成轨迹上的近似一致，不能据此宣称任意数据严格采样率不变。
5. Tskill 会实质改变含义：Tskill=5 时长期 D 稳态仅约 63.62 分，恢复后的 20 秒也未越过诊断阈值 75；Tskill=20/60 回 D 后约 14 秒越过 75。故不能把该时间常数直接命名为真实能力恢复时间。
6. 每 0.5 秒 D/U 切换 30 秒后再维持 D 20 秒，固定模型仍约 0 分；相关 DBN 的 Tskill=5/20/60 末点分别约 63.19/71.19/57.38。切换次数也是关键证据来源，必须检查噪声抖动的影响。

## Adverse interval and return to D (100 Hz)

Numbers are EAP; U+4.9s is a common timestamp before the grade returns to D. 'None' means no threshold crossing in the observed segment.

| Earlier D | Model | Tskill | pre-U | first U | U+4.9s | first return D | D+5s | D+20s | U <=25 latency | return >=75 latency |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | fixed_skill_markov | None | 99.202 | 60.747 | 47.419 | 85.214 | 92.011 | 98.873 | None | 0.0 |
| 30 | dynamic_raw_cpt | 5 | 99.970 | 66.961 | 0.001 | 0.716 | 99.970 | 99.970 | 0.01 | 0.03 |
| 30 | dynamic_raw_cpt | 20 | 99.993 | 88.945 | 0.000 | 0.180 | 99.993 | 99.993 | 0.01 | 0.04 |
| 30 | dynamic_raw_cpt | 60 | 99.998 | 96.015 | 0.000 | 0.060 | 99.998 | 99.998 | 0.01 | 0.04 |
| 30 | dynamic_correlated | 5 | 63.640 | 2.107 | 26.597 | 66.486 | 64.766 | 63.684 | 0.0 | None |
| 30 | dynamic_correlated | 20 | 84.190 | 3.290 | 9.886 | 40.995 | 57.521 | 80.254 | 0.0 | 13.79 |
| 30 | dynamic_correlated | 60 | 93.635 | 6.084 | 6.140 | 30.157 | 47.299 | 84.899 | 0.0 | 14.17 |
| 300 | fixed_skill_markov | None | 100.000 | 100.000 | 100.000 | 100.000 | 100.000 | 100.000 | None | 0.0 |
| 300 | dynamic_raw_cpt | 5 | 99.970 | 66.961 | 0.001 | 0.716 | 99.970 | 99.970 | 0.01 | 0.03 |
| 300 | dynamic_raw_cpt | 20 | 99.993 | 88.945 | 0.000 | 0.180 | 99.993 | 99.993 | 0.01 | 0.04 |
| 300 | dynamic_raw_cpt | 60 | 99.998 | 96.015 | 0.000 | 0.060 | 99.998 | 99.998 | 0.01 | 0.04 |
| 300 | dynamic_correlated | 5 | 63.616 | 2.107 | 26.597 | 66.486 | 64.766 | 63.684 | 0.0 | None |
| 300 | dynamic_correlated | 20 | 84.471 | 3.250 | 9.866 | 40.993 | 57.535 | 80.263 | 0.0 | 13.78 |
| 300 | dynamic_correlated | 60 | 94.264 | 5.912 | 6.038 | 30.297 | 47.653 | 85.156 | 0.0 | 14.0 |

## Sampling dependence: 10 versus 100 Hz

All metrics compare identical physical timestamps and grades. The sample paths between those timestamps differ only by the number of samples.

| Trajectory | Model | Tskill | Max EAP difference | EAP RMSE | Max state-probability difference | Final EAP difference |
|---|---|---:|---:|---:|---:|---:|
| D30_U5_D20 | fixed_skill_markov | None | 0.356874 | 0.106184 | 0.004037 | 0.015996 |
| D30_U5_D20 | dynamic_raw_cpt | 5 | 61.523402 | 3.470031 | 0.646899 | 0.265900 |
| D30_U5_D20 | dynamic_raw_cpt | 20 | 86.068065 | 4.525573 | 0.872077 | 0.066478 |
| D30_U5_D20 | dynamic_raw_cpt | 60 | 94.841681 | 5.179016 | 0.952618 | 0.022159 |
| D30_U5_D20 | dynamic_correlated | 5 | 0.115082 | 0.102300 | 0.001492 | 0.114456 |
| D30_U5_D20 | dynamic_correlated | 20 | 0.104615 | 0.064853 | 0.001298 | 0.066725 |
| D30_U5_D20 | dynamic_correlated | 60 | 0.086782 | 0.044055 | 0.001218 | 0.034406 |
| D300_U5_D20 | fixed_skill_markov | None | 0.012234 | 0.002906 | 0.000252 | 0.000000 |
| D300_U5_D20 | dynamic_raw_cpt | 5 | 61.523402 | 1.448973 | 0.646899 | 0.265900 |
| D300_U5_D20 | dynamic_raw_cpt | 20 | 86.068065 | 1.864105 | 0.872077 | 0.066478 |
| D300_U5_D20 | dynamic_raw_cpt | 60 | 94.841681 | 2.132230 | 0.952618 | 0.022159 |
| D300_U5_D20 | dynamic_correlated | 5 | 0.115218 | 0.113131 | 0.001492 | 0.114456 |
| D300_U5_D20 | dynamic_correlated | 20 | 0.104743 | 0.065632 | 0.001291 | 0.066898 |
| D300_U5_D20 | dynamic_correlated | 60 | 0.089140 | 0.031577 | 0.001163 | 0.037642 |
| all_A_60 | fixed_skill_markov | None | 0.002041 | 0.001427 | 0.000205 | 0.000781 |
| all_A_60 | dynamic_raw_cpt | 5 | 5.626637 | 0.298783 | 0.156239 | 0.141063 |
| all_A_60 | dynamic_raw_cpt | 20 | 5.617105 | 0.263532 | 0.154603 | 0.035336 |
| all_A_60 | dynamic_raw_cpt | 60 | 5.614971 | 0.260884 | 0.154238 | 0.011784 |
| all_A_60 | dynamic_correlated | 5 | 0.024619 | 0.023367 | 0.001213 | 0.024619 |
| all_A_60 | dynamic_correlated | 20 | 0.012291 | 0.011023 | 0.001186 | 0.010908 |
| all_A_60 | dynamic_correlated | 60 | 0.004858 | 0.003477 | 0.000609 | 0.002848 |
| flicker_DU_halfsec_30_then_D20 | fixed_skill_markov | None | 0.036722 | 0.005205 | 0.001344 | 0.000000 |
| flicker_DU_halfsec_30_then_D20 | dynamic_raw_cpt | 5 | 61.523395 | 20.149563 | 0.646899 | 0.265900 |
| flicker_DU_halfsec_30_then_D20 | dynamic_raw_cpt | 20 | 86.068051 | 29.816874 | 0.872077 | 0.066478 |
| flicker_DU_halfsec_30_then_D20 | dynamic_raw_cpt | 60 | 94.841675 | 36.268221 | 0.952619 | 0.022159 |
| flicker_DU_halfsec_30_then_D20 | dynamic_correlated | 5 | 0.129316 | 0.096318 | 0.001453 | 0.115679 |
| flicker_DU_halfsec_30_then_D20 | dynamic_correlated | 20 | 0.140521 | 0.079138 | 0.001481 | 0.106049 |
| flicker_DU_halfsec_30_then_D20 | dynamic_correlated | 60 | 0.149193 | 0.069022 | 0.001580 | 0.143835 |

## All-A and repeated D/U switching (100 Hz endpoints)

| Trajectory | Model | Tskill | Final P(L), P(M), P(H) | Final EAP |
|---|---|---:|---|---:|
| all_A_60 | fixed_skill_markov | None | 0.004131, 0.995602, 0.000267 | 49.806789 |
| all_A_60 | dynamic_raw_cpt | 5 | 0.000439, 0.999437, 0.000124 | 49.984288 |
| all_A_60 | dynamic_raw_cpt | 20 | 0.000110, 0.999859, 0.000031 | 49.996071 |
| all_A_60 | dynamic_raw_cpt | 60 | 0.000037, 0.999953, 0.000010 | 49.998690 |
| all_A_60 | dynamic_correlated | 5 | 0.295032, 0.444781, 0.260187 | 48.257738 |
| all_A_60 | dynamic_correlated | 20 | 0.167701, 0.703924, 0.128375 | 48.033656 |
| all_A_60 | dynamic_correlated | 60 | 0.070122, 0.880149, 0.049729 | 48.980344 |
| flicker_DU_halfsec_30_then_D20 | fixed_skill_markov | None | 1.000000, 0.000000, 0.000000 | 0.000000 |
| flicker_DU_halfsec_30_then_D20 | dynamic_raw_cpt | 5 | 0.000083, 0.000424, 0.999492 | 99.970454 |
| flicker_DU_halfsec_30_then_D20 | dynamic_raw_cpt | 20 | 0.000021, 0.000106, 0.999873 | 99.992614 |
| flicker_DU_halfsec_30_then_D20 | dynamic_raw_cpt | 60 | 0.000007, 0.000035, 0.999958 | 99.997538 |
| flicker_DU_halfsec_30_then_D20 | dynamic_correlated | 5 | 0.230479, 0.275185, 0.494335 | 63.192780 |
| flicker_DU_halfsec_30_then_D20 | dynamic_correlated | 20 | 0.204187, 0.167775, 0.628039 | 71.192600 |
| flicker_DU_halfsec_30_then_D20 | dynamic_correlated | 60 | 0.375892, 0.100544, 0.523564 | 57.383609 |

## Log-odds explanation

For H versus L: new posterior log odds = previous posterior log odds + prediction drift + sum of checkpoint conditional log-likelihood ratios. The score is a nonlinear posterior summary, so those terms are not additive EAP points. They are model evidence terms, not causal contributions. Combining checkpoints assumes their conditional independence under the specified state/observation history.

Two-checkpoint correlated DBN example, Tskill=20s, dt=0.1s:

| Time | CP grades | Previous log odds | Prediction drift | CP1 log LR | CP2 log LR | New log odds |
|---:|---|---:|---:|---:|---:|---:|
| 0.0 | D/A | 0.000000 | 0.000000 | 2.197225 | -0.926341 | 1.270884 |
| 0.1 | D/A | 1.270884 | -0.015861 | 0.016000 | -0.003040 | 1.267982 |
| 0.2 | U/A | 1.267982 | -0.015760 | -6.476972 | -0.003040 | -5.227789 |
| 0.3 | U/D | -5.227789 | 0.331503 | -0.013025 | 2.197225 | -2.712087 |
| 0.4 | D/D | -2.712087 | 0.045593 | 2.197225 | 0.016000 | -0.453269 |

## Limits and parameter meaning

- The dynamic state is an explicit added modelling assumption. A(dt) refreshes toward the uniform pi; it describes neither monotonic skill improvement nor a learned flight-skill transition law.
- A true DBN alone does not repair an observation model. With the correlated likelihood, a D->U switch is much more informative than another U frame; persistent U can coexist with prediction drift toward pi. Inspect both first-U and end-U posteriors.
- Sampling-rate agreement on these four noiseless piecewise-constant trajectories is not proof of invariance for arbitrary noisy trajectories. Flicker is a deliberately adverse observation-history test.
- 30s versus 300s is a history-length comparison within one synthetic session, not cross-session inheritance.
- No parameter is selected as calibrated or validated. The static whole-attempt BN is a separate study.

## Verification

All 56 runs completed with finite normalized posteriors. The run script asserted source-transition agreement, a direct linear reference, independently enumerated joint latent-state paths for both dynamic models, A row sums and semigroup, and log-odds identity. Grade alignment was asserted at every common timestamp.

```json
{
  "transition_formula_max_error": 1.1102230246251565e-16,
  "A_semigroup_max_error": 2.220446049250313e-16,
  "fixed_short_sequence_linear_reference_max_error": 3.3306690738754696e-16,
  "dynamic_enumerated_joint_reference_max_error": 5.551115123125783e-16,
  "completed_runs": 56,
  "sampling_pairs": 28,
  "max_log_odds_identity_error": 1.4210854715202004e-14,
  "application_transition_source_unchanged": true
}
```

Run: the existing project `.venv/Scripts/python.exe` with the absolute path to `dynamic/study.py`. Outputs: results.json (parameters, snapshots, latencies, comparisons, provenance), traces_common_10hz.csv (all models at shared timestamps), SUMMARY.md (this file).
