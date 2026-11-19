# Offline dynamic-state comparison — preregistered before execution

Date: 2026-09-21. Scope: synthetic calculation only, isolated from application code and saved assessment data. Python: the project's existing `.venv/Scripts/python.exe`; no installation, GPU, API, real-flight data, or training claim.

## Question and separate roles

Can a dynamic latent ability state respond to a five-second adverse interval and subsequent recovery without allowing a long earlier history to dominate indefinitely? How sensitive is that behavior to observation sampling rate? This study does not choose or change the separate static whole-attempt Bayesian score.

The proposed dynamic state is a modelling hypothesis, not measured pilot ability. The observed synthetic D/A/U grade is not ground-truth latent ability. “Failure” and “recovery” below refer only to the prescribed adverse and return-to-D portions of these synthetic trajectories. Numerical thresholds are diagnostic, not official assessment gates.

## Fixed inputs and model definitions

Three state rows L/M/H and observation columns D/A/U:

```
theta = [[0.10, 0.25, 0.65],
         [0.35, 0.63, 0.02],
         [0.90, 0.099, 0.001]]
pi = [1/3, 1/3, 1/3]
state_scores = [0, 50, 100]
tau_observation = [5, 5, 5] seconds
```

1. **fixed_skill_markov:** implemented fixed latent S; use the application's `_transition_log` directly. Initial likelihood theta; later likelihood `exp(-dt/tau)*I[g_t=g_previous] + (1-exp(-dt/tau))*theta[S,g_t]`. No latent prediction drift.
2. **dynamic_raw_cpt:** true HMM `S_previous -> S_t -> g_t`; predict with `A(dt)=(1-h)I+h*1*pi`, `h=1-exp(-dt/Tskill)`, then multiply by theta for every raw sample. This is a negative control: independent raw-frame observations are expected to make inference depend strongly on sample rate.
3. **dynamic_correlated:** dynamic S using the same A(dt), plus `g_previous -> g_t` and `S_t -> g_t`. Conditional observation likelihood is the existing transition form, with current latent state S_t indexing theta and tau. It is an explicit new DBN assumption. In particular, the old observation model may give weak incremental evidence during a sustained U interval; adding state dynamics does not establish that the observation model is appropriate.

Prediction is explicit: `q_t(s) = (1-h)*posterior_previous(s) + h*pi(s)`. Update: `posterior_t(s) proportional q_t(s)*product_k likelihood_k(s)`. All accumulation and prediction use log-space calculations.

## Experimental matrix

Use one checkpoint in the main comparison, holding theta/pi/tau/scores and trajectory fixed. The two-checkpoint example is only for the log-odds attribution identity, not an extra quantitative performance benchmark.

| Factor | Levels | Everything else held fixed |
|---|---|---|
| Model | fixed skill, dynamic raw CPT, dynamic correlated | Tskill=20 for the primary contrast |
| Tskill | 5, 20, 60 seconds | Compare within each dynamic model, one factor at a time |
| Sampling | 10, 100 Hz | Same exact piecewise-constant continuous-time trajectory |
| Earlier D history | 30, 300 seconds | Same following U=5 seconds and D=20 seconds |

Additional trajectories: all A for 60 seconds; D/U flicker switching every 0.5 seconds for 30 seconds, then D for 20 seconds. All switches fall on both sampling grids. At a switch time the new grade is observed. The terminal time is included and follows the last segment. There are seven model/parameter configurations x four trajectories x two rates = **56 deterministic runs**. No random sampling or seeds are involved.

## Expectations before execution

- Fixed-S evidence can retain a stronger earlier-history effect as D history increases.
- Raw-frame CPT HMM should react very fast and show sampling dependence even though latent prediction uses physical time.
- Correlated-observation DBN may be less sampling-sensitive, but exact rate invariance is not assumed; discretized state prediction and conditional observation updates need not commute.
- Smaller Tskill means faster drift back toward pi in the absence of diagnostic evidence; it is not a learned recovery time.
- Repeated D/U switches may dominate the correlated model because every switch supplies a likelihood ratio, while persistent same-grade observations supply much smaller increments. This may be undesirable and must be reported rather than tuned away.

## Metrics and interpretation

Report posterior and EAP at last pre-U observation, first U, U elapsed 0.1/1/4.9 seconds, first return to D, D elapsed 0.1/1/5/20 seconds. The 4.9-second U point is shared by both rates and avoids comparing a different elapsed time near the switch.

Diagnostic response latencies: first EAP <=25 and first P(L)>=0.5 during U; first EAP >=75 and P(H)>=0.5 after return to D. No crossing is JSON null, not an infinite observed latency. A zero latency means the threshold is already met at the first new observation. None of these thresholds is a validated pilot-performance criterion.

For 10 versus 100 Hz, compare posterior vectors and EAP at the same 0.1-second timestamps: maximum absolute score difference, score RMSE, maximum per-state probability difference, and final score difference. Export 10 Hz common-time traces while computing every raw sample.

Explain dynamic item log odds exactly:

```
log[p_t(H)/p_t(L)] = log[p_previous(H)/p_previous(L)]
                      + log[q_t(H)/q_t(L)] - log[p_previous(H)/p_previous(L)]
                      + sum_k log[likelihood_k(H)/likelihood_k(L)]
```

The middle term is prediction drift; each checkpoint contributes a conditional log-likelihood ratio. These are model evidence terms, not causal effects, point deductions, or additive EAP contributions. Conditional independence across checkpoints remains an assumption.

## Verification and resources

Before accepting output: check posterior normalization and finiteness; verify row-stochastic A and its semigroup identity; compare the imported fixed-S transition against its direct formula; check the log-odds decomposition; verify both sample grids see identical grades at common timestamps; verify 56 completed runs and no application-code changes. Failed checks stop the script with an error.

Expected cost: CPU only, minutes at most, zero GPU hours/API spend; JSON summary plus common-time CSV traces expected below 15 MB. Deliver `study.py`, `results.json`, `traces_common_10hz.csv`, and `SUMMARY.md`. Run from any working directory with `pilot_assessment_system/.venv/Scripts/python.exe .../dynamic/study.py`.
