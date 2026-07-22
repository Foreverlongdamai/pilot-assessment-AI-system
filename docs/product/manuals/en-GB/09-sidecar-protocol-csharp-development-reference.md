+++
document_id = "PAS-PROTOCOL-CSHARP-001"
language = "en-GB"
title = "Sidecar Protocol and C# Development Reference"
short_title = "Sidecar and C# Reference"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["developer", "maintainer"]
information_types = ["how-to", "reference", "explanation"]
scope = "Local JSON-RPC sidecar lifecycle, typed protocol rules and WinUI/C# maintenance boundaries."
prerequisites = ["C# and .NET knowledge", "JSON-RPC familiarity", "Understanding of the Python domain boundary"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-PYTHON-CORE-001", "PAS-RELEASE-001", "PAS-PORTABILITY-001"]
support = "Record the UI action, protocol/method version, transaction ID, trace ID, stderr diagnostic and reproducible state."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.4"
user_acceptance = "pending"
+++

# Sidecar Protocol and C# Development Reference

## 1. Process topology

The WinUI desktop application starts exactly one private Python sidecar child process. Communication is local and private:

```text
WinUI/C# process
    stdin  -> JSON-RPC 2.0 request, one JSON object per line
    stdout <- JSON-RPC 2.0 response/event, one JSON object per line
    stderr <- backend logs and diagnostics only
Python sidecar process
```

The product does not listen on a TCP/HTTP port and has no separately started SQLite service. Stdout is a protocol channel: ordinary logging there is a framing defect. Large images, videos, time-series files and artifacts remain on disk; protocol messages carry stable project/Session/run/artifact identities and compact DTOs.

## 2. Startup handshake and shutdown

The desktop resolves its private runtime and active source relative to the product root, starts the sidecar with an isolated Python invocation and performs a version/capability handshake before enabling backend-owned actions.

The handshake identifies protocol versions, product/backend identity, method catalog, schemas and capabilities. Do not infer support from the frontend build number alone. On normal desktop close, pending model-edit choices are resolved first, the protocol shuts down and the child process exits. A crash or timeout must be surfaced in Diagnostics rather than silently launching a second writer against the same roots.

## 3. JSON-RPC framing and errors

Each physical line is one UTF-8 JSON object conforming to JSON-RPC 2.0. Requests have an ID, method and object `params`; notifications have no request ID. Responses contain exactly one `result` or `error` for the matching ID.

Domain failures use stable machine-readable error codes plus localized UI presentation. Keep traceback and detailed backend context on stderr/diagnostic payloads; never put arbitrary log text between protocol lines. Reject oversize or malformed messages deterministically and leave the server able to process the next valid frame where safe.

The UI must not parse English error sentences to decide behaviour. Map typed status/error fields to localized resources.

## 4. Mutation contract

Every externally initiated write carries:

- a unique transaction ID for idempotent retry;
- the expected optimistic revision of the targeted aggregate/edit session;
- a typed intent payload;
- caller/protocol metadata needed for audit.

The Python domain service validates and commits once. Repeating the same transaction returns the canonical prior outcome; reusing its ID with different intent is rejected. Revision conflicts require reload/rebase, not last-writer-wins.

The protocol transports edit intent. It does not contain a second implementation of Evidence recipes, activation closure, DAG validation, CPT semantics or BN inference.

## 5. Read and run boundaries

Use compact query methods for project/system summaries, lists, node details, task schemes, edit-session state, preflight, run status, results, diagnostics and provenance. Return stable IDs for selection but let ordinary UI cards display concise names.

Run methods request backend preflight/start/cancel/recovery. The C# client does not create a local shadow RunSnapshot or calculate progress by guessing. Polling/reconciliation follows the durable backend state so restart and interrupted-run behaviour remain consistent.

## 6. C# solution map

| Location | Responsibility |
|---|---|
| `src/PilotAssessment.Desktop.Core/Contracts/` | typed JSON DTOs and source-generation context |
| `src/PilotAssessment.Desktop.Core/State/` | graph projections, drafts, undo/redo-facing state and display resolution |
| `src/PilotAssessment.Desktop.Core/ViewModels/` | UI-independent view models and projections |
| `src/PilotAssessment.Desktop/Services/Backend/` | sidecar process/client composition and RPC mapping |
| `src/PilotAssessment.Desktop/ViewModels/` | WinUI screen/editor behaviour |
| `src/PilotAssessment.Desktop/Controls/` | graph, editors, task-scheme/sidebar components |
| `src/PilotAssessment.Desktop/Strings/` | localized UI resources only |
| `tests/PilotAssessment.Desktop.UnitTests/` | fast C# behaviour/serialization tests |
| `tests/PilotAssessment.Desktop.ContractTests/` | real-sidecar protocol compatibility tests |

Model names/descriptions are canonical English data. UI labels, prompts and validation messages are localized resources. Switching language must never rewrite model content.

## 7. Add or change a protocol method

1. Define or version the Python contract and JSON Schema if serialized meaning changes.
2. Implement the domain service operation independently of the sidecar.
3. Expose a thin method in `sidecar/methods.py` and register it in the negotiated method catalog.
4. Add matching C# records with explicit JSON property names and source-generation registration.
5. Add one method to the backend client; map typed domain errors without parsing prose.
6. Add focused Python dispatcher/method tests, C# serialization tests and a real-sidecar contract test.
7. Update Diagnostics/capability documentation.

Do not make a C# DTO permissive merely to hide backend drift. Version intentionally and keep explicit legacy DTOs when historical payloads must remain readable.

## 8. Build and test from a source checkout

Common development commands are:

```powershell
dotnet build src\PilotAssessment.Desktop\PilotAssessment.Desktop.csproj `
  -c Debug -p:Platform=x64 --nologo

dotnet test tests\PilotAssessment.Desktop.UnitTests\PilotAssessment.Desktop.UnitTests.csproj `
  -c Debug --nologo

dotnet test tests\PilotAssessment.Desktop.ContractTests\PilotAssessment.Desktop.ContractTests.csproj `
  -c Debug -p:Platform=x64 --nologo
```

The portable release is self-contained for end users; Visual Studio and an SDK are build-machine requirements only. Launch a visible smoke after material XAML/process-lifecycle changes and close it normally so no sidecar or SQLite lock remains.

## 9. UI interaction rules

- The five-layer graph is a projection of backend complete nodes, typed edges and scheme activation.
- Node editors stage commands; they do not directly update database files.
- Multiple floating editors can be open, but **Save all** is one system-level commit.
- `Ctrl+Z`/redo operate on the staged command history.
- Enabling a child requests backend ancestor closure; disabling a parent requests an impact preview before confirmation.
- Copying creates a new node identity while retaining original fixed parents by default.
- Long IDs/hashes stay in Diagnostics/provenance rather than ordinary labels.

## 10. Security and privacy boundary

Never add TCP just to simplify debugging. Do not pass arbitrary filesystem paths from UI to execution without backend containment checks. Do not echo Session rows, gaze, physiology or images into logs. Keep project/system roots explicit and close handles before whole-directory copying.

## 11. Developer checklist

- [ ] One sidecar child and zero listeners;
- [ ] stdout contains protocol JSON only;
- [ ] request/response DTOs are typed and versioned;
- [ ] writes carry transaction ID and expected revision;
- [ ] C# sends intent and does not duplicate domain computation;
- [ ] large data stays in managed files;
- [ ] language switching affects resources, not canonical content;
- [ ] unit and real-sidecar contract tests cover the changed method;
- [ ] visible desktop smoke closes without leftover processes/locks.
