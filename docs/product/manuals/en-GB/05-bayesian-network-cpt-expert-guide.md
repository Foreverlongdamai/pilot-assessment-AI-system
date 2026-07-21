+++
document_id = "PAS-EXPERT-BN-001"
language = "en-GB"
title = "BN, Parent, State and CPT Expert Guide"
short_title = "BN and CPT Guide"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["expert", "developer"]
information_types = ["tutorial", "how-to", "reference", "explanation"]
scope = "Designing Bayesian-network topology, ordered states and conditional probability tables in the shared system model."
prerequisites = ["Basic probability concepts", "An explicit expert hypothesis for the assessment task"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-EXPERT-EVIDENCE-001", "PAS-EVALUATOR-001", "PAS-PYTHON-CORE-001"]
support = "Record the child node name, ordered parents, ordered states, failing CPT row and stable validation error."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.1"
user_acceptance = "pending"
+++

# BN, Parent, State and CPT Expert Guide

## 1. Separate extraction from probability

The product contains two typed graph relations:

- a **data/extraction dependency** says which raw or derived Session resources an EvidenceRecipe reads;
- a **probabilistic edge** says which random variables condition a child's conditional probability distribution.

Raw Input is not a Bayesian random variable and has no CPT. Evidence extraction first computes an observation from Session data. The BN then conditions latent capability distributions on that observation. Calling both relations simply “parents” would be ambiguous, so the editors and contracts keep them separate.

## 2. Use the correct BN direction

The starter model is a generative Bayesian network:

```text
Competency  ->  Sub-skill  ->  Evidence observation
```

For each probabilistic arrow `parent -> child`, the child stores `P(child | ordered parents)`. During an assessment, Evidence is observed and Bayes' rule updates the posterior of hidden Sub-skill and Competency variables through the same joint distribution. The information effect therefore travels from observed Evidence towards capability, but this does not reverse the saved arrows.

The left-to-right canvas is a human workflow layout—Raw Input, Extracted Data, Evidence, Sub-skill, Competency. Canonical probabilistic arrows may point right-to-left. Never reverse them merely to make the picture resemble the assessment computation sequence.

## 3. Complete-node parent rule

Every Evidence or BN node has one ordered probabilistic parent set as part of its complete global definition. A task scheme can activate or deactivate that node, but cannot replace its parents.

- A starter Competency is normally a root node with a prior CPT.
- A Sub-skill normally has one or more Competency parents.
- An Evidence observation normally has one or more Sub-skill parents.
- The engine also permits other acyclic Evidence/BN relations that satisfy the typed contract, so the starter hierarchy is not an engine cardinality limit.

If another task needs different parents, copy the child, edit the copy and activate it in the new scheme. Sharing a node across schemes is safe precisely because its meaning, states, parents and CPT remain identical.

## 4. Edit a BN node

[[SCREENSHOT:ui-bn-cpt-editor]]

Open the node's movable, resizable editor. Several node editors can remain open for comparison. Editable content includes:

- canonical English name, short name and description;
- role (`Sub-skill` or aggregate `Competency`);
- ordered states and their concise English labels/descriptions;
- ordered probabilistic parents;
- CPT mode, probabilities and generator metadata;
- documentation, reporting metadata, provenance and expert help text.

The same probabilistic interpretation panel exists for Evidence observation nodes. Their recipe/data bindings compute the observation; their probabilistic parents and CPT describe how that observation behaves conditional on latent BN states.

## 5. Define states before the CPT

Each variable needs at least two unique, stable state IDs. State order is semantic because it determines CPT columns and every parent's axis. Prefer a small set that experts can distinguish and calibrate, for example `LOW`, `MEDIUM`, `HIGH`; do not rely on colour or display order alone.

Before changing states:

1. document what each state means;
2. decide whether the order expresses increasing capability or another explicit axis;
3. inspect every downstream child whose CPT uses that state axis;
4. update affected CPTs as one staged change.

Renaming a display label is different from changing a state ID or its meaning. A semantic change should usually create a copied node so older task schemes remain interpretable.

## 6. Enter and verify a CPT

For child `C` with ordered parents `P1 ... Pn`, the editor materializes one row for every Cartesian product of parent states. With no parents, there is exactly one prior row. Columns follow the child state order.

Every complete row must:

- contain one finite probability for every child state;
- keep each probability in `[0, 1]`;
- sum to `1` within the engine tolerance;
- align with the displayed ordered parent-state combination.

The number of rows is:

```text
rows = product(number of states for each ordered parent)
```

Changing parent order changes row interpretation even when the parent set is unchanged. Review the row headers rather than copying a numeric block blindly. `INCOMPLETE` mode may preserve an unfinished design, but technical preflight blocks a run that requires a non-materialized CPT.

## 7. Preserve a DAG

A Bayesian network must be a directed acyclic graph (DAG): following probabilistic arrows can never return to the starting node. Self-parenting and cycles are rejected because they do not define the supported joint factorization.

When a parent edit would create a cycle, create a different modelling structure; do not work around validation by reversing unrelated arrows. Extraction dependencies are validated separately and are not inserted as raw variables into the BN.

## 8. Activation and missing observations

Activating a child automatically activates all fixed probabilistic parents and extraction inputs needed by the selected closure. Deactivating a parent with active descendants requires confirmation and, if continued, deactivates the affected downstream closure.

At runtime, an active Evidence node can still be unavailable because its Session modality is absent. That is not a new graph. The inference engine marginalizes unobserved Evidence and uses all available observations. It never turns missing Evidence into `DESIRED`, `UNACCEPTABLE` or a numeric zero.

## 9. What validation does and does not prove

The software checks types, identities, state-axis alignment, probability normalization, acyclicity, activation closure and execution readiness. It does not prove that a causal assumption is correct, a CPT reflects a target population or the posterior is suitable for an operational decision.

The supplied CPTs are starter values. Domain experts remain responsible for elicitation, data analysis, sensitivity analysis, fairness and scientific approval. Preserve `formal_run_authorized=false` until that process is completed outside this release-candidate gate.

## 10. BN expert checklist

- [ ] Extraction dependencies and probabilistic parents are not mixed;
- [ ] canonical arrows encode `P(child | parents)`;
- [ ] graph is acyclic;
- [ ] one fixed ordered parent set per complete node;
- [ ] state IDs, meaning and order are explicit;
- [ ] CPT row count and axes match the declared states;
- [ ] every materialized row sums to one;
- [ ] affected downstream CPTs reviewed after state/parent changes;
- [ ] missing observations are interpreted as missing, not poor performance;
- [ ] scientific claims remain separate from contract validation.
