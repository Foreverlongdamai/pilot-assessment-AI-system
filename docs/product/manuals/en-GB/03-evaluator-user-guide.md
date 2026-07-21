+++
document_id = "PAS-EVALUATOR-001"
language = "en-GB"
title = "Evaluator User Guide"
short_title = "Evaluator Guide"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["evaluator"]
information_types = ["tutorial", "how-to", "reference"]
scope = "Project, Session, run, result and diagnostic workflows for an evaluator using the Windows application."
prerequisites = ["A complete unpacked product", "A writable project location", "A simulator export or canonical Session Bundle"]
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-SESSION-001", "PAS-EXPERT-EVIDENCE-001", "PAS-PORTABILITY-001"]
support = "Report the release label, concise project name, run state, stable error code and privacy-safe Diagnostics summary."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# Evaluator User Guide

## 1. Evaluation boundary

This guide covers ordinary operation: create or open a project, import a Session, select a task scheme, run the engineering pipeline and review results. It does not ask the evaluator to edit Python, design Evidence algorithms or calibrate CPTs.

The release candidate is an interpretable engineering framework. Its starter model has `formal_run_authorized=false`; outputs must not be presented as a scientifically validated pilot qualification result.

## 2. Open or create a project

At startup, choose one action:

- **Create project** creates a new empty project in a user-selected directory.
- **Open project** opens an existing complete project root.
- **Recent projects** reopens a known project only if its root still exists.

Use a concise project name that does not contain sensitive participant details. The application creates the technical project ID. A project stores managed Session revisions, immutable RunSnapshots, runs, results and artifacts. Global Evidence/BN definitions live in the software copy's `system\` and therefore apply to every project opened by that copy.

## 3. Import a Session

Open **Sessions** and select the external source. The source may be a canonical bundle with `manifest.json` or a raw simulator export containing `streams\` and optional `annotations\`.

The import has two explicit stages:

1. **Inspect external source** is read-only. Review detected files, mapped modalities, annotations, time columns and diagnostics.
2. **Import to managed project** copies accepted content into the project and records a canonical revision and receipt.

The original directory is never used as mutable working storage. Repeating the same import is idempotent: the backend reconciles the existing managed revision instead of silently duplicating it.

Missing modalities do not invalidate the whole Session. The application does not synthesize missing data. Evidence supported by available modalities can run; unsupported Evidence becomes explicitly unavailable and BN inference proceeds with the observations that exist.

## 4. Choose the task scheme

A task scheme is a saved selection of globally shared complete nodes and edges. It decides which Raw Input, Extracted Data, Evidence, Sub-skill and Competency nodes participate in this assessment.

Select the intended scheme in **Model Studio** or the run workspace. Active nodes appear bright; inactive library nodes remain visible but dim. Selection does not create a temporary model version and does not rewrite another scheme. If a child is active, the backend activates its fixed ancestor closure automatically.

Do not alter the scheme merely to make preflight pass unless you are acting as the responsible domain expert. See [[DOC:PAS-EXPERT-EVIDENCE-001]].

## 5. Run technical preflight

Open **Runs**, select one managed Session revision and one task scheme, choose a purpose, then select **Technical preflight**. Preflight freezes no result and performs no scientific quality judgement. It checks whether the selected snapshot can be executed by the installed engine.

Review:

- Session revision and task-scheme identity;
- active node closure and current model content hashes;
- installed operator availability and parameter contracts;
- available and missing modalities;
- schema/runtime compatibility;
- scientific boundary and exact blocking diagnostics.

Unusual flight behaviour, large trajectory error, aggressive control or abnormal physiological values are assessment observations, not reasons to discard otherwise parseable data. Structural absence or an impossible execution contract is reported separately as unavailable or blocked.

Assessment purpose and scientific authorization are separate fields. When technical disposition is ready, an Assessment-purpose run can start and complete. If the exact model or Session is not formally authorized, preflight shows the `run.assessment_not_authorized` warning and the run's frozen preflight provenance retains `formal_run_authorized=false`. The warning does not block engineering computation and must not be ignored as if it were a scientific-validity claim.

## 6. Start, monitor or cancel a run

Select **Start run** only after preflight is ready. Assessment purpose is not disabled solely by false scientific authorization; real structure, dependency, dirty/stale source or runtime problems still block execution. The backend creates an immutable RunSnapshot before computation. The usual stages are snapshot validation, ingestion, synchronization, Evidence extraction, Bayesian inference, reporting and completion.

Closing and reopening the application does not rewrite a durable run. The backend reconciles queued, interrupted or completed state from the project. A cancellation request is also reconciled with the canonical backend run; wait for its final state before copying the project.

## 7. Review results

[[SCREENSHOT:ui-run-results-diagnostics]]

Open **Results** and select a completed run. Read results from specific to general:

1. Evidence continuous value, D/A/U observation and availability;
2. Evidence trace, parameters, source modality and operator identity;
3. Sub-skill posterior distribution;
4. aggregate competency posterior distribution;
5. missing-Evidence and influence information;
6. frozen model, Session and backend-source provenance.

`DESIRED`, `ACCEPTABLE` and `UNACCEPTABLE` are model states, not a legal or clinical judgement. A posterior is conditional on the expert-authored graph, CPTs and available Evidence. Missing observations are marginalized by the BN; they are not silently replaced by ideal values or zeros.

## 8. Use Diagnostics

Open **Diagnostics** when startup, import, run recovery or source identity is unclear. Useful sections include backend/runtime status, current system model identity and counts, project compatibility, run recovery, schema identities, JSON-RPC capabilities, Python source identity, installed dependencies and operator catalog.

Ordinary views intentionally hide long UUIDs and hashes. Diagnostics and provenance retain them for support and reproducibility. Copy only the privacy-safe summary unless an authorized process explicitly requests Session content.

## 9. End the work safely

Finish or cancel active operations, then close the main window normally. If model edits were staged by an expert, the close dialog offers save all and close, discard all and close, or cancel. Evaluator project data is durable independently of that global model edit session.

To move the work, close the app and copy the complete project root. Do not copy only its SQLite file. See [[DOC:PAS-PORTABILITY-001]].

## 10. Evaluator checklist

- [ ] Correct product release and intended system model confirmed;
- [ ] correct project opened;
- [ ] external source inspected before import;
- [ ] managed Session revision selected;
- [ ] intended task scheme selected;
- [ ] technical preflight reviewed;
- [ ] run reached a durable final state;
- [ ] missing Evidence and scientific boundary reviewed;
- [ ] provenance retained with any exported conclusion.
