# Static whole-flight model offline study plan

Recorded before numerical execution, 2026-09-21. Scope: synthetic mathematical behavior only; no application code, configuration, existing documents, or real flight results will be changed.

## Fixed interpretation and controls

- Observed grade vector is `r = [r_D, r_A, r_U]`, with scores `[100,50,0]`.
- Latent categorical state vector is `[L,M,H]`, with scores `[0,50,100]`. These are model hypotheses; they are not observed grade proportions.
- Prior is `[1/3,1/3,1/3]` throughout. Baseline CPT rows L/M/H, columns D/A/U: `[[.10,.25,.65],[.35,.63,.02],[.90,.099,.001]]`.
- Current runtime baseline is `demo_quantification.distribution_posterior`: `p_s ∝ π_s exp(k Σ_g r_g log θ_sg)`, with `k=3` and one checkpoint of weight 1. Multiple checkpoints in the app use fixed weights `1/K`; this study isolates one checkpoint to avoid adding a weighting factor. Direct runtime calls will be compared against the independent NumPy formula.
- Fixed cases: pureD; pureA; pureU; .9D/.1A; .7D/.3A; .7D/.2A/.1U; .5D/.5U; .2D/.7A/.1U; .45D/.45A/.1U; .6D/.38A/.02U.
- Exhaustive simplex grid: all triples summing to 1 with spacing .02 (1,326 points, including 3 pure vertices). Directed improvements transfer .02 from U→A, A→D, or U→D whenever possible. Score decreases below -1e-9 count as monotonicity violations. Any component strictly greater than .99 at a mixed grid point counts as saturation. Store counts by component and concrete examples.

## One-factor comparisons

1. Independent categorical likelihood evidence: baseline CPT with effective independent exposure N=10,100,10000. Formula uses k=N. Fractional N*r is an idealized effective-count sensitivity input when counts are not integers; no synthetic samples are claimed to have been collected.
2. Fixed normalized likelihood: k=.5,1,3,8,30, baseline CPT. Vary k alone; k=3 is the current baseline.
3. CPT sensitivity, holding k=3: stricter illustrative CPT `[[.005,.045,.95],[.05,.9,.05],[.95,.045,.005]]`; flatter illustrative CPT is `.5*baseline + .5*uniform`. Stricter emphasizes pure representative states; flatter reduces emission differences. Neither is fitted. Also evaluate all three CPTs at the same N=100 to test whether strictness removes or relocates concentration under accumulating independent evidence.
4. Dirichlet categorical predictive model: `q ~ Dirichlet(alpha0/3 + N*r_UAD)` with alpha0=1 or 3 and N=10,100,10000. Report posterior predictive grade probabilities `E[q_g]`, grade expected score, exact marginal 95% beta credible intervals for grade frequencies, and analytical posterior SD for expected grade score. This is a model of grade propensity under the same task conditions, not a latent L/M/H ability-class posterior.

## Preregistered expectations and diagnostics

- Repeating the same raw frames without new independent exposure leaves fixed-k results unchanged. Compare count vectors and 1000x repeats through the runtime baseline. Holding Dirichlet effective N fixed also leaves its result unchanged.
- Additional valid independent exposure can narrow credible intervals; it must not be equated with resampling an existing sequence.
- Fixed-k controls concentration but does not force mixed-grade posteriors to mirror grade proportions. Large k/N can concentrate on whichever discrete CPT row best fits a mixed distribution.
- CPT strictness may shift the winning latent state, including to M; it does not in general eliminate concentration. Flatter CPT can reduce concentration at a chosen k while weakening pure-input confidence.
- Baseline CPT may violate score monotonicity because ordering of rows alone is weaker than monotone likelihood ratios. Store up to two worst nonzero score-decrease examples per scheme and all aggregate counts.
- Dirichlet predictive means should move linearly and monotonically with the grade mixture for fixed N/alpha0. More exposure can tighten frequency uncertainty without forcing a heterogeneous mixture into one pure grade.
- Test near-pure mixtures `[1-e,e,0]` with e=.1,.02,.01,.001,.0001 to expose the impossibility of a literal discontinuous rule that all mixed cases stay below .99 but pure cases exceed .99, for these continuous models.
- No accuracy, calibration, real-pilot effectiveness, or recommended production parameter will be claimed without real labels. No arbitrary clipping is recommended.

## Execution and costs

Use the existing project `.venv/Scripts/python.exe` with its installed NumPy/SciPy, CPU only, no package installation, network, GPU, model training, or paid calls. Vectorized grid inference plus a small number of SciPy beta quantiles should complete within 30 seconds; record measured wall time, versions, command, and source hash. Outputs: `run_study.py`, `results.json`, `SUMMARY.md`. Verification will assert probability normalization, baseline runtime equivalence, repeat invariance, exact case/grid counts, analytic Dirichlet score/variance identity, and monotonicity for Dirichlet predictions.

## Prespecified follow-up after initial mathematical diagnostics

Before this supplemental run: the initial naive strict and half-uniform flat CPTs failed monotone likelihood ratios and exhibited decreasing scores on grade improvements. Add two explicit controls to avoid conflating saturation with those accidental ordering failures: (a) stricter MLR-preserving CPT `[[.001,.049,.95],[.05,.9,.05],[.95,.049,.001]]`; (b) flatter MLR-preserving CPT `sqrt(baseline)` normalized within each row. The latter preserves within-grade likelihood-ratio ordering because a positive power is monotone and each row normalizer is constant across grades. Compare each at k=3 and N=100. These are additional illustrative sensitivity controls, not fitted replacements. Expect no directional score violations, while large-N categorical concentration may remain.
