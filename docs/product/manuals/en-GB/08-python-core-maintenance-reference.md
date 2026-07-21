+++
document_id = "PAS-PYTHON-CORE-001"
language = "en-GB"
title = "Python Core Maintenance Reference"
short_title = "Python Core Reference"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["developer", "maintainer"]
information_types = ["how-to", "reference", "explanation"]
scope = "Maintaining the Python contracts, ingestion, synchronization, Evidence execution, BN inference, persistence, runtime and sidecar layers."
prerequisites = ["Python 3.11 knowledge", "Understanding of the product architecture and immutable run boundary"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-PYTHON-EXT-001", "PAS-PROTOCOL-CSHARP-001", "PAS-RELEASE-001"]
support = "Record the source-tree identity, failing contract/schema ID, command, traceback and smallest privacy-safe reproduction."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.3"
user_acceptance = "pending"
+++

# Python Core Maintenance Reference

## 1. Scope and authority

The Python backend is the canonical execution implementation for project/session management, model persistence, Evidence execution and Bayesian inference. “Canonical” means it owns durable state transitions and computation; it does not mean its starter algorithms are scientifically authoritative or difficult to change.

Ordinary model content belongs in the system model library and is edited through the front end. Modify core Python when changing a general engine rule, data adapter, operator mechanism, inference capability, persistence contract or protocol service. One unpacked product has one exposed live source tree, so a core change affects future runs from every project opened by that copy after restart.

## 2. Source map

| Package | Responsibility |
|---|---|
| `contracts/` | strict Pydantic DTOs and versioned immutable payload shapes |
| `schemas/` and `schema_resources/` | deterministic JSON Schema export and packaged schemas |
| `ingestion/` | canonical bundle validation, raw-source adapters and readiness |
| `synchronization/` | native-clock mapping and aligned views without rewriting source |
| `evidence/` | operator definitions, registry, recipes, compiler and executor |
| `anchors/` | legacy/starter anchor compatibility and result contracts |
| `bayesian/` | DAG validation, factors and posterior inference |
| `model_workspace/` | global complete nodes, task schemes, staged edit operations and execution projection |
| `model_library/` and `schemes/` | model assets and legacy/current scheme support |
| `persistence/` | SQLite migrations, repositories, transactions, audit and content-addressed artifacts |
| `runtime/` | system/project application composition, preflight and run lifecycle |
| `sidecar/` | JSON-RPC method boundary and stdin/stdout server |

In a source checkout these live under `src/pilot_assessment/`. In a portable product the same active tree is `backend/src/pilot_assessment/`.

## 3. Preserve ownership boundaries

Keep three durable scopes distinct:

- **software/system scope** — global model library, nodes, recipes, parents, CPTs, task schemes and staged edits;
- **project scope** — managed Sessions, RunSnapshots, runs, results, artifacts and audit records;
- **release/source scope** — Python code, dependencies, UI, manuals and integrity manifests.

Do not move current model rows into a project merely to simplify a query. Do not store user Sessions inside the product directory. Do not make live source fall back silently to an installed wheel. These boundaries are what make whole-software and whole-project copying predictable.

## 4. Contracts and schema evolution

Current domain payloads are strict and versioned. Add a new schema/contract version when serialized meaning changes. Keep explicit legacy readers for historical RunSnapshots and results; do not reinterpret or rewrite their stored bytes.

Recommended sequence:

1. define the new current contract beside the legacy type;
2. add a deterministic decoder/migration for live current rows if required;
3. make migration append-only and idempotent, retaining old payload/hash lineage;
4. export the additive JSON Schema under a new versioned filename;
5. route new writes to the new contract while old readers continue to discriminate by ID/version;
6. verify an old run still round-trips unchanged.

Never delete a historical schema only because the current UI no longer creates it.

## 5. Persistence and transactions

SQLite is embedded and opened by the backend. Migration numbers are monotonic. A migration must either commit completely or leave the previous database usable. Store paths relative to the owning project/system root, validate containment and avoid storing machine-specific absolute paths.

All externally initiated mutations use a transaction ID, expected optimistic revision and idempotent replay semantics. Domain services perform validation and one atomic commit; the JSON-RPC layer must not duplicate the mutation in a second store. Change journals support undo/redo and traceability but are not a scientific approval workflow.

Do not edit a live SQLite database with an ad hoc SQL patch. Implement a normal migration or service operation, test on a complete disposable copy, then let the application open the selected root normally.

## 6. Ingestion and synchronization changes

Add new simulator formats as adapters that inspect the external source read-only and materialize a canonical managed bundle. Keep file/column mapping explicit. A new physical modality receives its own contract, stream descriptor, clock and adapter rather than being hidden in an unrelated CSV column.

Synchronization preserves native rows and maps timestamps deterministically to Session `t_ns`. It reports technical coverage but does not filter poor pilot performance. Never turn an extreme finite flight or physiological value into missing/invalid merely because it looks undesirable.

## 7. Evidence execution changes

Prefer adding an operator through the ordinary extension path described in [[DOC:PAS-PYTHON-EXT-001]]. Change the generic compiler/executor only for capabilities shared across operators, such as a new port type, temporal semantic, trace contract or deterministic artifact rule.

Evidence computation must close to raw/session/task resources. It cannot read inferred Sub-skill/Competency scores to manufacture an observation. Missing required data produces a typed unavailable outcome; poor available data is computed normally. Keep output, status, trace, parameter hash, operator identity and input artifact identities together.

## 8. Bayesian inference changes

The current generic engine evaluates a typed DAG and materialized discrete CPTs. Node count, task name and starter hierarchy are data, not hard-coded engine constants. A graph edit normally changes model rows—not Python—because the engine derives factors from parents, states and CPTs.

Modify the BN engine only to add a general inference/model family capability. Preserve the canonical `P(child | parents)` interpretation, stable state order, probability normalization and missing-observation marginalization. Any new inference backend must freeze its implementation identity and exact graph snapshot in the run provenance.

## 9. Runtime and historical reproducibility

Before a run, preflight resolves one managed Session revision, one clean current task scheme, its complete active closure, operator implementations, Python/dependency identity and scientific boundary. Run creation freezes those facts. Later source/model edits must never update a completed RunSnapshot or result.

The runtime detects source changes after startup and requires restart before another run. This prevents provenance from claiming current disk bytes while the process still executes old imported modules.

## 10. Lightweight change workflow

The project deliberately welcomes expert modification. Use verification proportional to the change rather than a large fixed approval ceremony:

1. make the smallest coherent source change;
2. run the focused contract/unit test nearest the changed module;
3. run one lightweight end-to-end workflow when execution behaviour changes;
4. confirm one historical result still opens for compatibility-sensitive work;
5. restart and inspect Diagnostics/source identity;
6. record the change in the software copy's maintenance notes.

From a source checkout, common commands are:

```powershell
.\.tools\uv\uv.exe run pytest path\to\focused_test.py -q
.\.tools\uv\uv.exe run ruff check src\pilot_assessment path\to\focused_test.py
.\.tools\uv\uv.exe run ty check src\pilot_assessment
.\.tools\uv\uv.exe run python -m pilot_assessment.schemas.export
```

Do not run massive synthetic datasets merely to prove wiring. Add targeted numerical tests only for the mechanism being changed.

## 11. Recovery

If source edits prevent startup, read stderr/Diagnostics for the exact import or contract failure. Restore the modified files from version control or re-extract the original ZIP into a separate directory. Open the existing project from the recovered software; do not overwrite its root. If the system model itself was modified, recover it only by copying the complete intended software directory or by applying a deliberate model edit—not by copying one database file while the app runs.

## 12. Maintainer checklist

- [ ] Correct durable scope identified;
- [ ] current model content change kept out of core code when possible;
- [ ] new serialized meaning receives a new contract/schema version;
- [ ] historical payloads remain byte-stable and readable;
- [ ] transaction and idempotency semantics preserved;
- [ ] paths remain relative and contained;
- [ ] poor performance is not treated as missing data;
- [ ] focused tests and one relevant lightweight workflow pass;
- [ ] source identity and restart behaviour verified.
