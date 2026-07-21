+++
document_id = "PAS-PYTHON-EXT-001"
language = "en-GB"
title = "Python Operator and Source Extension Development Guide"
short_title = "Python Extension Guide"
product_version = "0.1.0"
document_version = "0.1.0"
status = "released"
audience = ["expert", "developer", "maintainer"]
information_types = ["tutorial", "how-to", "reference"]
scope = "Editing or extending the active first-party Python source in one unpacked software copy."
prerequisites = ["M8B portable product layout", "Ability to read and edit Python"]
scientific_status = "engineering-only"
related_documents = ["PAS-ARCH-001", "PAS-PYTHON-CORE-001", "PAS-RELEASE-001"]
support = "Use the Diagnostics workspace and the packaged logs when reporting a failure."
release_channel = "release-candidate"
release_label = "v0.1.0-rc.1"
user_acceptance = "pending"
+++

# Python Operator and Source Extension Development Guide

| Field | Value |
|---|---|
| Manual ID | `PA-MANUAL-PY-OPERATOR-EXTENSION` |
| Product stage | M8B-2 engineering handoff |
| Applies to | One unpacked Pilot Assessment System software copy |
| Audience | Expert developers who can read and edit Python |
| Scientific status | Engineering extension instructions only; no algorithm is scientifically endorsed |

## 1. Decide whether Python needs to change

Use the Windows front end for ordinary expert work:

- change Evidence parameters, windows, thresholds and scorer settings;
- compose existing operators into a different EvidenceRecipe;
- add/copy Evidence or BN nodes;
- change fixed parents, states, CPTs and task activation;
- save or discard the staged system-model edit session.

Edit Python only when the installed operator catalog cannot express a genuinely new calculation
mechanism. A Python change applies to every project opened by this unpacked software copy after the
application restarts. It does not belong to one project.

## 2. Know the live paths

From the unpacked product root:

```text
backend/src/pilot_assessment/                     active first-party Python source
backend/src/pilot_assessment/evidence/builtins/   packaged operator implementations
backend/src/pilot_assessment/evidence/extensions/ local ordinary-source extension entry
backend/src/pilot_assessment/evidence/registry.py shared trusted registry
backend/pyproject.toml                             runtime dependency declarations
backend/uv.lock                                    resolved dependency lock
runtime/python/python.exe                          private Python interpreter
runtime/site-packages/                             private third-party packages
developer/examples/operator-extension/            copyable engineering example
developer/tools/manage_python_dependencies.ps1    private dependency helper
developer/tools/uv.exe                             bundled dependency resolver
```

There is no installed first-party wheel, project-level source overlay, plugin marketplace or hidden
fallback implementation. `backend/src/pilot_assessment` is the one active source tree.

## 3. Back up and close the process

1. Close `PilotAssessment.Desktop.exe` and wait for its child `runtime/python/python.exe` to stop.
2. Keep the original ZIP, or copy the whole unpacked product directory to a new folder.
3. Do not copy only the project: a project intentionally does not own Python source or the system
   model library.

Editing while the sidecar is running is detected as `runtime.restart_required`; new runs are
blocked until restart so a RunSnapshot cannot claim disk bytes that were never imported.

## 4. Start from the copyable example

First run the example without installing it:

```powershell
.\runtime\python\python.exe -I -B -X utf8 `
  .\developer\examples\operator-extension\test_example_scalar_offset.py
```

Expected result: one standard-library test passes. The example is not part of the starter model.

Copy the implementation:

```powershell
Copy-Item `
  .\developer\examples\operator-extension\example_scalar_offset.py `
  .\backend\src\pilot_assessment\evidence\extensions\example_scalar_offset.py
```

Then edit
`backend/src/pilot_assessment/evidence/extensions/__init__.py`:

```python
from pilot_assessment.evidence.extensions.example_scalar_offset import (
    register_example_scalar_offset,
)


def register_extension_operators(registry: OperatorRegistry) -> None:
    register_example_scalar_offset(registry)
```

This explicit import and call are the complete registration mechanism. Restarting the app executes
the same composition root used by built-ins. A duplicate `(operator_id, implementation_version)`
fails visibly instead of replacing an existing implementation.

## 5. Anatomy of an operator

An extension module supplies two matching objects:

1. an `OperatorDefinition` describing identity, ports, parameter JSON Schema, UI hints, trace
   capability and implementation reference;
2. an implementation object exposing the same `operator_id`, `implementation_version` and
   `implementation_ref`, plus `execute(inputs, parameters, context)`.

Set `implementation_source=OperatorImplementationSource.TRUSTED_EXTENSION`. The definition and
implementation identities must match exactly.

The generic front end uses:

- `name` and `description` for the operator menu and node detail;
- `input_ports` and `output_ports` for recipe connections;
- `parameter_schema` for validation and field types;
- `parameter_ui` for labels, groups, control hints, help text and units;
- `pseudocode` for an understandable calculation summary.

Supported ordinary form values include numbers, integers, strings, booleans, enums, arrays and
objects. Unsupported or old JSON is preserved read-only rather than silently dropped. No C# switch
or operator-specific page is needed for a normal schema-driven extension.

Keep execution deterministic for the same frozen inputs and parameters. Return a mapping whose
keys exactly match declared output ports. Raise a clear exception for invalid input instead of
returning a plausible fallback number.

## 6. Load the operator in an EvidenceRecipe

After restart:

1. open Model Studio and an Evidence node window;
2. open its EvidenceRecipe graph;
3. add the new operator from the operator catalog;
4. connect compatible input/output ports;
5. select the operator node and edit its schema-generated parameters;
6. preview with a small representative Session;
7. close the main window and choose **Save all and close** to commit the staged model edits.

Registration only makes a mechanism available. It does not automatically add an Evidence node,
activate it in a task, or modify the Hover starter scheme.

## 7. Add or remove a third-party dependency

Close the app before changing dependencies. The helper always uses the product's bundled uv and
private runtime, not a system Python or global PATH:

```powershell
# Show the packages actually visible to the private runtime
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 list

# Add one declared dependency, update backend/uv.lock, and synchronize runtime/site-packages
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 add "package-name>=1,<2"

# Remove a direct dependency and synchronize again
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 remove "package-name"

# Reproduce runtime/site-packages from the current frozen lock
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 sync
```

`add` and `remove` need package-index access; `list` is offline. `sync` is offline only when all
required wheel files are already in uv's cache. The helper does not install the first-party
`pilot_assessment` package as a wheel.

Restart after any dependency operation. The next backend identity includes the updated
`pyproject.toml`, `uv.lock`, private dependency manifest and operator catalog.

## 8. Identities, historical runs and checksums

Diagnostics shows:

- source-tree and combined backend identity;
- release-baseline difference;
- private Python identity;
- installed dependency-manifest identity;
- operator-catalog identity;
- whether the currently running process requires restart.

A new run stores these identities and a content-addressed ZIP of the exact first-party source,
`pyproject.toml` and `uv.lock`. An older RunSnapshot and its source artifact never change when the
live source changes.

Direct source/dependency edits intentionally make `manifest/checksums.sha256` and the original
release baseline differ. This is provenance, not an approval failure. Re-extract the original ZIP
to recover the delivered baseline; do not overwrite user project folders while doing so.

## 9. Minimal verification before use

For a new mechanism, check only what is relevant:

1. the app starts and Diagnostics reports the intended modified identity;
2. the operator catalog shows the new name, ports and parameter form;
3. one small recipe produces the expected engineering example value;
4. one small assessment run completes and records the new source identity/artifact;
5. an older result still opens unchanged.

These checks prove wiring and reproducibility. They do not prove the new evidence method, threshold
or Bayesian interpretation is scientifically valid; domain experts own that later work.

## 10. Troubleshooting and recovery

| Symptom | Likely cause | Action |
|---|---|---|
| App/sidecar exits during startup | Syntax error, import error, duplicate operator identity or missing dependency | Read stderr/Diagnostics, fix the named file, or restore the backed-up product directory |
| `runtime.restart_required` | Source, `pyproject.toml` or `uv.lock` changed after this process loaded | Close the full app and reopen it |
| Operator absent from menu | Module exists but its registration function was not imported/called | Check `evidence/extensions/__init__.py`, then restart |
| Parameter absent or read-only | JSON Schema/UI pointer is missing, unsupported or mismatched | Correct `parameter_schema` and `parameter_ui`; preserve stable JSON paths |
| Recipe compile rejects a connection | Port value type, cardinality, temporal semantics or unit is incompatible | Correct the definition or insert an appropriate conversion operator |
| Dependency import fails | Private runtime was not synchronized or package has no compatible Windows/Python wheel | Run the helper's `sync`, choose a compatible dependency, or restore the previous product copy |
| Need old and new algorithms in parallel | Editing one implementation in place changes it globally for future runs | Keep the old operator and add a different operator ID/version; select the desired one per EvidenceRecipe |

When recovery is urgent, close the app and re-extract the original system to a new folder. Open the
existing user project from that clean copy; the project was never packaged into or stored inside
the original ZIP.
