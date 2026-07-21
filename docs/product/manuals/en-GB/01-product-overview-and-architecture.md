+++
document_id = "PAS-ARCH-001"
language = "en-GB"
title = "Product Overview and System Architecture"
short_title = "Product Overview and Architecture"
product_version = "0.1.0"
document_version = "0.1.0"
status = "review"
audience = ["evaluator", "expert", "developer", "maintainer", "release"]
information_types = ["explanation", "reference"]
scope = "Explains the Pilot Assessment System product boundary, roles, containers, data ownership, model structure, computation direction and extension paths."
prerequisites = []
scientific_status = "engineering-only"
related_documents = ["PAS-QUICKSTART-001", "PAS-EVALUATOR-001", "PAS-EXPERT-EVIDENCE-001", "PAS-EXPERT-BN-001", "PAS-SESSION-001", "PAS-PYTHON-EXT-001"]
support = "Retain the product version, stable error ID, Diagnostics summary and a privacy-safe description of the affected project when reporting a problem."
+++

# Product Overview and System Architecture

## 1. What this product is for

Pilot Assessment System is an offline Windows application that turns multimodal flight-simulation Session data into interpretable Evidence and then uses an expert-designed Bayesian network to quantify sub-skills and aggregate competencies. It is first and foremost an **expert-editable, traceable software framework**. It is not a scientifically calibrated pilot-assessment standard.

The current distribution includes a runnable starter template that demonstrates the engineering path from input through Evidence to BN results. Its Evidence definitions, thresholds, operator parameters, parents, states, CPTs, eleven sub-skills and four aggregate competencies may all be edited, copied, deactivated or replaced by experts. A successful engineering run does not validate that starter scientific content.

The product provides three core benefits:

- **Transparency:** raw inputs, EvidenceRecipe graphs, operators, BN parents/states/CPTs, task activation and run provenance are inspectable;
- **Editability:** routine model changes are made in the front end, while genuinely new low-level mechanisms can be added by editing the exposed Python source;
- **Reproducibility:** each run freezes the exact Session revision, model closure, source, dependencies and operator identity, so later edits cannot rewrite historical results.

## 2. Readers and responsibilities

| Role | Primary work | Usually unnecessary |
|---|---|---|
| Evaluator | Create/open a project, import a Session, select a task scheme, run and review results | Edit Python, design CPTs or judge scientific validity |
| Domain expert | Add/copy Evidence and BN nodes; edit recipes, parents, states, CPTs and task activation | Manage a SQLite service or hand-edit run snapshots |
| Algorithm extension developer | Add a Python operator or change core computation when the existing catalog cannot express a method | Publish a plugin merely to change a threshold |
| C#/protocol maintainer | Maintain WinUI, typed DTOs, sidecar lifecycle and error recovery | Reimplement Evidence or BN algorithms in C# |
| Release maintainer | Build the portable ZIP, verify checksums/SBOM/manuals and execute delivery checks | Package user Sessions or projects with the product |

The first-use path is documented in [[DOC:PAS-QUICKSTART-001]]; the evaluation workflow is documented in [[DOC:PAS-EVALUATOR-001]].

## 3. System context

[[ASSET:c4-system-context]]

This view borrows the C4 system-context level. It shows people, external data, the product and managed projects without expanding internal classes or database tables.

- A simulator may export a canonical Session Bundle or only `streams/` and `annotations/`;
- the product inspects the external directory read-only and copies usable content into managed project storage;
- evaluators operate on a current project, while domain experts edit the software copy's global model library;
- run results, Evidence traces, BN posteriors, artifacts and the exact RunSnapshot are stored in the project;
- the product ZIP never contains user Sessions, projects, results or biometric data.

## 4. One product copy, one system model library, many user projects

```text
One unpacked software copy
├── Python backend source and private runtime
│   ├── generic Evidence executor
│   ├── operators / adapters
│   └── BN inference engine
├── system/ global model library
│   ├── all Raw Input / Evidence / BN nodes
│   ├── all task schemes and active selections
│   ├── parents, states, CPTs and layout
│   └── current durable edit session
└── multiple user-selected projects (outside the software directory)
    ├── managed Session revisions
    ├── immutable RunSnapshots
    ├── runs / results
    └── content-addressed artifacts
```

This ownership boundary reconciles two needs: model design must apply globally to every project opened by the same product copy, while each user's Session and results must remain isolated and portable. Once an expert saves a node edit, future runs in all those projects use it. Completed historical runs still use their frozen snapshots.

Copying the entire unpacked directory copies the current `system/` and Python source, creating an independently evolving software branch. Copying or moving an individual project moves only that project's data and history; it does not copy the current global model.

## 5. Containers, runtime and data ownership

[[ASSET:c4-container]]

| Container/store | Responsibility | Authority boundary |
|---|---|---|
| WinUI Desktop | Canvas, node windows, forms, task switching, runs and result projection | Sends typed intents; does not duplicate Python computation |
| Python sidecar | Local JSON-RPC, domain services, persistence and Evidence/BN execution | Protocol only on stdout, logs on stderr, no network listener |
| Active Python Source | Adapters, operators, compiler/executor, BN engine and contracts | The only active first-party source tree in this unpacked copy; restart loads changes |
| System Model Library | All current ModelNodes, TaskSchemes, CPTs, layouts and edit session | Owned by the software copy, not by any project |
| User Project | Sessions, RunSnapshots, run/result/artifact data | User data; excluded from the generic product package |
| Versioned Manuals | Operation, expert design, interfaces, source and release guidance | DOCX is generated from Markdown; documentation does not change runtime behaviour |

Starting the front end automatically supervises its private Python sidecar. Users do not activate Conda, start a SQLite service or open a network port. SQLite is an embedded file database read and written directly by the Python process.

## 6. From raw input to competency results

The main computation follows this order:

1. Inspect and import one Session into managed storage;
2. map X/U/I/G/P and optional `pilot_camera` data into typed signals/resources through adapters;
3. execute each active Evidence node's EvidenceRecipe;
4. produce continuous values, trace data and D/A/U observations through operator graphs;
5. use Evidence observations and CPTs to calculate BN posteriors;
6. show Evidence, sub-skills, aggregate competencies, influence information and provenance;
7. store the exact RunSnapshot, result and artifacts in the project.

The five raw-input families are:

| Family | Content |
|---|---|
| X(t) | Aircraft state, attitude, position, velocity and task-related state |
| U(t) | Pilot control inputs and controller state |
| I(t) | The scene or visual frames seen by the pilot in VR |
| G(t) | Gaze, stare, fixation, AOI and view mapping |
| P(t) | EEG, ECG and other future declared physiological signals |

`pilot_camera` is an optional pilot face/body camera and is not I(t). Missing inputs are not synthesised by the product. Evidence that depends only on available modalities may still compute; Evidence that requires a missing input receives an explicit availability state. Poor trajectories, aggressive control or unusual physiological values are not automatically treated as low-quality data and are not filtered merely because performance is poor.

See [[DOC:PAS-SESSION-001]] for interface details.

## 7. Nodes, canvas layers and the correct BN direction

The persisted model has three core node kinds: Raw Input, Evidence and BN. For human understanding, the front end projects these into five layers:

1. Raw Input Family;
2. Extracted Data;
3. Evidence;
4. Sub-skill;
5. Competency.

Evidence computation depends only on raw input or typed preprocessing; an abstract skill cannot generate Evidence. The BN generative direction remains `Competency → Sub-skill → Evidence observation`: a child's CPT is conditioned on its fixed parents. During assessment, observed Evidence updates hidden-skill posteriors through the same joint probability model. This does not justify reversing the structural arrows to `Evidence → Skill`.

Operators are not main-canvas nodes. They are reusable computation steps inside an EvidenceRecipe and appear in Evidence details and the Operator menu. Expert workflows are covered by [[DOC:PAS-EXPERT-EVIDENCE-001]] and [[DOC:PAS-EXPERT-BN-001]].

## 8. Global nodes and task schemes

Each visible node has one current definition containing its name, fixed parents and complete recipe or states/CPT. If two tasks need different computation or parents, they use two independent nodes rather than hidden versions of one node.

A task scheme selects which global nodes and edges are active:

- active nodes and edges are bright; real global nodes not used by the current task are dimmed;
- enabling a child recursively enables every fixed parent;
- deactivating a parent with active downstream nodes asks the expert to continue with cascading deactivation or cancel;
- copying a node copies only that node and continues to reference its original fixed parents by default;
- multiple tasks may share exactly the same node; a task that needs custom behaviour can copy, rename and edit it, then deactivate the old node in that scheme.

The library can therefore accumulate similar but independent nodes such as base `Precise`, later expert-created `hover.Precise` and `straight.Precise`. Task schemes choose among them; users never need to overwrite one algorithm and manually change it back for another task.

## 9. Two levels of modification

### 9.1 Routine expert editing

Parameters, windows, thresholds, scorers, recipe composition, nodes, parents, states, CPTs, task activation and layout are edited in the front end. Changes enter a durable Python-managed edit session. When the main window closes, the user chooses Save all, Discard all or Cancel. No plugin release or developer test suite is required for an ordinary parameter change.

### 9.2 A new computation mechanism

Only when the installed operator catalog cannot express a new method does a developer edit:

```text
backend/src/pilot_assessment/
```

The new operator is registered through the explicit extension entry point. If needed, the bundled dependency tool updates the private runtime. Restarting the application loads the change for all projects and future runs in that software copy; historical RunSnapshots remain unchanged. See [[DOC:PAS-PYTHON-EXT-001]] for exact steps.

## 10. Run identity and historical immutability

Preflight freezes:

- the exact managed Session revision;
- the clean TaskScheme and active-node closure;
- ModelNode, recipe and CPT hashes;
- the loaded source tree, private Python, dependency manifest and operator catalog identity.

If source files change on disk after the Python process has started, the system requires a restart. This prevents a run from recording the new file hash while executing an old import. Divergence from the shipped baseline is reported as `locally_modified` but does not block an expert-modified system. The first run with a new source identity stores a content-addressed source snapshot artifact for future explanation of historical results.

## 11. Startup, shutdown and migration facts

- The first delivery is a Windows x64 portable ZIP; use a reasonably short writable path such as `D:\PilotAssessment`;
- double-click `PilotAssessment.Desktop.exe` to start the front end and supervised sidecar;
- do not start SQLite separately or activate Python manually;
- create projects in a user-selected location outside the product directory;
- when model edits exist, closing the main window asks whether to save all, discard all or cancel;
- unpack a new product version beside the old one; it does not overwrite a modified older copy;
- the generic product backup covers the system, while user-project backup and migration are a separate workflow.

## 12. Current status and scientific boundary

At this document version, engineering gates M1–M8B are complete and the M8C documentation system is in progress. Full M7 hands-on user acceptance and the D-055 single-English canonical-model migration are not closed. M8D backup/migration and the M8E final clean-machine handoff are also unfinished.

Every starter/synthetic run remains `formal_run_authorized=false`. The product demonstrates that contracts, editing, persistence, inference and provenance can operate end to end. It does not prove that current Anchors/Evidence, task structure, thresholds or CPTs assess pilot competency accurately. Domain experts will design, calibrate and validate the scientific method within this framework.

## 13. Recommended reading routes

- First run: [[DOC:PAS-QUICKSTART-001]];
- import and evaluate: [[DOC:PAS-EVALUATOR-001]];
- design Evidence/tasks: [[DOC:PAS-EXPERT-EVIDENCE-001]];
- design BN/CPT: [[DOC:PAS-EXPERT-BN-001]];
- connect captured data: [[DOC:PAS-SESSION-001]];
- add a low-level algorithm: [[DOC:PAS-PYTHON-EXT-001]].

## 14. Change history

| Document version | Date | Change |
|---|---|---|
| 0.1.0 | 2026-07-21 | Established the bilingual M8C architecture baseline, including system/project/source ownership, task nodes, BN direction and the scientific boundary |
