# Fixed item state with correlated categorical observations: implementation review

2026-09-16. Scope: standalone calculations only. `probe.py` and `probe.json` do not import or modify runtime. Parameters are uncalibrated examples, not aviation-standard values.

## Minimal closed model

For each checkpoint j, item state s in Low/Middle/High, and observable grade g:

- Existing CPT row theta[j,s] is assumed to be the stationary grade distribution. This is an additional model constraint, not something implied by an arbitrary marginal CPT.
- Uniform prior remains the current configured prior; introduce it once per checkpoint-only view and once per item view.
- Same illustrative correlation time tau = 5 seconds across skill states. Do not invent distinct recovery rates by class before calibration.
- Pi_s has all rows equal to theta_s. Q_s = (Pi_s - I)/tau and T_s(dt) = exp(-dt/tau) I + (1-exp(-dt/tau)) Pi_s. Since Pi_s is idempotent, this is the exact matrix exponential. It is stochastic, stationary with theta_s, and satisfies the semigroup property.
- First valid frame of an observation segment contributes log theta_s[current_grade]. Subsequent same-segment frames contribute log T_s(dt)[previous_grade,current_grade]. Do not also multiply theta on subsequent frames.
- A phase boundary starts a new stationary observation segment but retains cumulative state evidence. This explicitly assumes independently restarted observable chains conditional on S; it is not the same as resetting the skill prior. If later phase-specific rates are introduced, a piecewise transition model needs a separate contract.
- Item inference assumes checkpoint observation chains are independent given its common S. log item posterior = log prior + sum of all checkpoint cumulative log likelihoods. No subjective weight or kappa is required for this exact-under-assumptions model. Reusing kappa 3 or equal 1/J turns it into a power/composite posterior and must receive a different method identifier.
- Checkpoint chart: posterior using only that checkpoint's evidence and the same configured prior. Do not multiply checkpoint posteriors for item inference because this would repeat the prior.
- Score remains posterior expectation of the configured state values. This is a cumulative fixed-state inference trace, not an instantaneous state or the existing final normalized score.

Suggested metadata: `method=demo_fixed_skill_ctmc_v1`, `calibration_status=uncalibrated`, `initial_observation=stationary_cpt`, `phase_boundary=restart_observation_chain_keep_skill_posterior`, `checkpoint_dependency=conditional_independence_assumed`, `tau_s=5`.

## What tau means

Tau is a relaxation / observation correlation timescale. It is not the average time to recover from U. In this model the mean dwell time in grade g is tau/(1-theta_s[g]). With current CPT and tau 5, U dwell means are about 5.005 seconds for High and 5.102 seconds for Middle; they barely differ. The model mostly distinguishes occurrence of deviations, desired persistence, and destination probabilities, not a separately calibrated recovery skill.

## Responsiveness probes

Single checkpoint, current ordinal CPT, uniform prior, state scores 0/50/100, 10 Hz, 30 seconds D followed by 1 second U and then D:

| tau | score before U | minimum during U | final at 59.9 seconds |
|---:|---:|---:|---:|
| 1 | 99.999998 | 99.999964 | 100.000000 |
| 3 | 99.913491 | 95.587162 | 99.996536 |
| 5 | 99.188565 | 58.133701 | 99.688226 |
| 10 | 95.597317 | 18.441616 | 88.553480 |
| 20 | 90.113485 | 10.075194 | 54.471731 |

Tau 5 is a practical *illustrative* baseline. Choosing it for visual response is not evidence of measurement validity. For a 600-second run with U only at 300.0–300.9 seconds, tau 5 still gives approximately 100 -> 100 -> 100. Fixed S can still saturate from long evidence. Do not promise every failure produces a visibly falling posterior.

Keep a per-step evidence strip such as log likelihood ratio High/Low or High/Middle. It records the new evidence even if the posterior is saturated. Display it as evidence support, not another ability score. Always retain raw values, D/A/U and Fail.

Sampling: the tau 5 minimum is 58.133701 at 10 Hz and 58.217129 at 100 Hz for the same nominal signal. A constant 30-second D segment sampled with dt 1, .1, .01, .001 seconds gives scores 99.139274, 99.197736, 99.202964, 99.203481. Repeated same-grade observations converge to a finite residence-time likelihood as dt tends to zero; they do not create unbounded evidence solely from sampling density. Observing additional real transitions can legitimately change evidence.

Same D/A/U counts with different transition counts produce different final results: 70D->20A->10U yields 15.026610; interleaving (7D->2A->1U) ten times yields 0.000158. These are consequences of the illustrative CPT and Markov assumption, not validated rankings of actual pilots.

## Missingness and numerical safeguards

- A checkpoint outside its configured phase contributes no likelihood, rather than D. Do not invent an observation in an unobserved phase.
- Existing complete-record contract can taint posterior output from the first applicable missing observation onward. Return null thereafter for affected checkpoint and item inference, preserving raw valid grades. This avoids silently treating missingness as ignorable. If single-step evidence after a new phase is shown, explicitly distinguish it from unavailable cumulative inference.
- Within a homogeneous phase a CTMC *could* marginalize unobserved intermediate states through T(total dt), but doing so assumes ignorable missingness. Do not quietly add that semantics while the product requires complete records.
- Strictly increasing timestamps. An identical-time identical-grade duplicate has likelihood 1; an identical-time contradictory grade has probability zero and should be rejected, not patched with epsilon.
- Numerically use refresh = -expm1(-dt/tau). Changed grade: log(refresh)+log(theta[current]); same grade: log1p(-refresh*(1-theta[current])). Avoid multiplying tiny factors before taking logs.
- If dt/tau overflows to infinity, refresh=1 gives a valid stationary limit. If the positive ratio underflows to zero, use log(dt)-log(tau) for log(refresh), valid to floating point precision in that regime. Do not impose arbitrary probability floors.
- A point-sample boolean checklist has no meaningful sequential physical dwell information; preserve its existing true/false rule. Do not fabricate timestamps to claim every static checklist now has temporal inference.

Probe assertions passed: transition row sums, stationary CPT, semigroup, and zero-time duplicate semantics. No formal calibration or real-flight effectiveness was evaluated.
