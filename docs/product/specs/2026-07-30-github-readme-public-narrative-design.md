# GitHub README Public Narrative Design

| Field | Value |
|---|---|
| Status | Approved |
| Approved by | Product owner, 2026-07-30 |
| Scope | Repository-root `README.md`, supporting public references, and product-document index |
| Out of scope | Assessment algorithms, starter parameters/CPTs, application code, model library, and building/uploading a new release package in this documentation change |

## 1. Goal

Rewrite the repository entry point so that a classmate, supervisor, researcher, or prospective collaborator can understand the problem before encountering the implementation. The README must explain why pilot-skill assessment matters, how representative adjacent domains currently train and assess people, what the two 2015 PAV handling-qualities studies contributed, and how this project extends that foundation into an expert-editable VR assessment platform.

The approved narrative is problem/value first:

```text
motivation -> current practice -> research foundation -> unresolved gap
-> VR assessment idea -> product workflow -> expert extension -> engineering details
```

## 2. Audience and first-screen promise

The primary first-time reader is not assumed to know EvidenceRecipe, CPT, JSON-RPC, M7, or M8. The first screen shall answer:

1. this is a system for evaluating eVTOL pilot training in VR;
2. it turns multimodal simulator behaviour into interpretable evidence and skill estimates;
3. experts can change the evidence rules, Bayesian network, and task-specific emphasis;
4. it assists research and training design and is not yet a scientifically validated licensing standard.

The project title remains `Pilot Assessment System`. A concise Chinese value proposition appears immediately below it. The formal research title, *Development of AI-Based System for Evaluating eVTOL Pilot Training Effectiveness*, remains visible without leading the reader into implementation jargon.

## 3. Representative current-practice comparison

The README shall use a short, explicitly non-exhaustive comparison rather than claim a universal industry workflow.

### 3.1 Road driving

Use the United Kingdom as one understandable official example:

- training combines instructor-led lessons and practice;
- the licensing path separates knowledge and hazard perception from an on-road practical test;
- the practical test observes vehicle safety knowledge, general/independent driving, manoeuvres, and faults;
- simulator-based intelligent instructors are an emerging complementary direction, not the normal licensing authority.

### 3.2 VTOL and powered-lift

Use the FAA Powered-Lift Airman Certification Standards as an official example:

- training and evaluation are organised around Areas of Operation and Tasks;
- Knowledge, Risk Management, and Skill are evaluated together;
- instructors/evaluators still interpret demonstrated performance against defined standards;
- approved simulation can support training, but the README must not imply that this project replaces certification, instructors, or evaluators.

### 3.3 Research transition

The comparison must end with the actual gap addressed here: a VR session can produce dense synchronized telemetry, controls, visual, gaze, EEG/ECG, and camera data, but data alone are not a competency model. Experts still need a transparent, reusable way to define which observations count as Evidence, how tasks select that Evidence, and how uncertain Evidence updates skill beliefs.

## 4. Research attribution and lineage

The two direct 2015 foundations are both authored by Philip Perfect, Michael Jump, and Mark D. White:

1. *Methods to Assess the Handling Qualities Requirements for Personal Aerial Vehicles*, DOI `10.2514/1.G000862`;
2. *Handling Qualities Requirements for Future Personal Aerial Vehicles*, DOI `10.2514/1.G001073`.

The README shall say that the present project is being developed under Professor Linghai Lu's guidance and continues the HELIFLIGHT/PAV handling-qualities research line. It shall not describe either 2015 paper as authored by Professor Lu.

The 2015 studies provide the closest methodological basis: mission-task-element trials with participants of varied flight experience, desired/adequate task boundaries, objective performance, control activity/workload, TPX, and subjective workload. The project inherits the task-centred and multi-measurement approach, not the numerical thresholds as immutable pilot-competency truth.

Lu et al. (2016), *Development of Occupant-Preferred Landing Profiles for Personal Aerial Vehicles*, belongs in the related lineage because it studies landing profiles, naturalness, comfort, workload, and acceptability. It is not presented as the main foundation of the general pilot-skill model.

## 5. Proposed VR assessment explanation

The README shall explain the executable idea in plain language before introducing graph-theory details:

1. the expert defines the task, reference, phases/events, and expected regions or tolerances;
2. the VR simulator records X(t), U(t), I(t), G(t), P(t), and optional pilot-camera data;
3. EvidenceRecipe and typed operators calculate observable Evidence such as tracking deviation, recovery time, control activity, AOI dwell, or physiological variation;
4. the active TaskScheme selects the Evidence and BN nodes relevant to that task;
5. observed Evidence is entered into a static expert-authored Bayesian network to infer sub-skill and aggregate competency posteriors;
6. every result retains its source data, recipe, parameters, CPT, model identity, and immutable RunSnapshot.

Missing modalities remain missing. Evidence that can still be computed continues through inference; poor performance remains valid negative Evidence and is never discarded merely for being poor.

## 6. Product positioning

The README shall consistently describe the product as:

- an offline Windows assessment-model designer and execution environment;
- interpretable and traceable rather than an opaque single-score model;
- task-adaptive through parallel TaskSchemes and a shared global node library;
- editable through the UI for normal Evidence/BN/task changes;
- source-extensible through the exposed Python backend when a genuinely new operator is required.

It shall not claim:

- that starter Evidence, thresholds, CPTs, or competencies are scientifically validated;
- that the system replaces an instructor, examiner, regulator, or certification process;
- that the sample CSV represents a standard trajectory or ground truth;
- that engineering verification equals user acceptance or scientific calibration.

## 7. Public distribution entry

The README shall reserve a clear download section for the final product. The intended final delivery mechanism is the GitHub Releases area of `Foreverlongdamai/pilot-assessment-AI-system`, containing at minimum:

- one versioned Windows portable ZIP;
- its SHA-256 checksum;
- concise release notes, system requirements, launch instructions, and known scientific limitations;
- a link to the detailed manuals in the same repository.

The release must contain the application, editable backend source, system model library, private runtime, developer extension material, and documentation, but no local user Project, Session, RunSnapshot, result, or artifact data. A private repository cannot provide an anonymous public download; before a release is advertised as available to everyone, the owner must deliberately make this repository public or use a separate public distribution repository.

RC.4 remains an engineering candidate with user acceptance pending. This README revision may describe the intended final distribution path but must not upload, relabel, or advertise RC.4 as the final public product.

## 8. Information architecture

The repository README shall use this order:

1. value proposition;
2. motivation;
3. representative automotive/VTOL practice;
4. the two 2015 PAV foundations and the project's extension;
5. VR assessment workflow;
6. current product capabilities;
7. detailed computational and Bayesian semantics;
8. operating workflow and portable layout;
9. nodes, task schemes, expert editing, and Python extension;
10. data interfaces, missing data, implementation status, documentation navigation, development, and boundaries.

Existing technically correct material should be preserved after the newcomer-oriented entry sections. Repetition may be removed, but ownership, staged-save, RunSnapshot, missing-data, release, and scientific-boundary wording must not regress.

## 9. Sources

Public-facing claims shall link to primary or official sources:

- GOV.UK/DVSA theory, hazard-perception, and practical-test pages;
- FAA Powered-Lift ACS and active AC 194-2 guidance;
- the original AAAI 2024 Virtual Driving Instructor paper;
- the University of Liverpool repository and DOI pages for both 2015 PAV papers;
- the existing project reference record for Lu et al. 2016.

`docs/product/REFERENCES.md` remains the detailed provenance index. The README uses short descriptive links rather than academic-reference boilerplate in the opening narrative.

## 10. Acceptance criteria

The change is complete when:

- a reader can identify the project's purpose and value before encountering EvidenceRecipe/CPT terminology;
- road-driving, simulator-intelligence, powered-lift, and PAV research are distinguished rather than conflated;
- both 2015 PAV papers are named and accurately attributed;
- Professor Lu's role and the 2016 paper's narrower relevance are stated accurately;
- the VR input-to-Evidence-to-BN-to-skill workflow is visible in prose and Mermaid;
- the expert-editable/task-specific architecture and scientific limitations remain explicit;
- a reader can distinguish the future public GitHub Release from the current not-yet-accepted RC candidate;
- all new relative Markdown links resolve locally and all external links use stable official or primary-source URLs;
- no application code, model database, release ZIP, or current release status is altered.
