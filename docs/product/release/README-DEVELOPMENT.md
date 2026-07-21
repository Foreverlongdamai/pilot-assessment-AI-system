# Editing the live Python backend

The running first-party backend is exactly:

```text
backend\src\pilot_assessment\
```

There is no installed `pilot-assessment-system` wheel and no per-project Python overlay. Changes to
this tree apply globally to this extracted software copy after the desktop app is fully closed and
restarted.

## Choose the least invasive modification

1. Change Evidence/BN/CPT/task parameters and graph structure in the front end whenever the
   existing operators and inference engine can express the requirement.
2. Edit or add an operator under `backend\src\pilot_assessment\evidence\extensions` only when a
   genuinely new extraction mechanism is needed. Register it in
   `extensions\__init__.py::register_extension_operators()` and expose a parameter schema so the
   front end can render its form.
3. Edit core ingestion, synchronization, persistence, protocol or inference modules only when the
   platform contract itself must change.

## Safe source workflow

1. Close the desktop application started by root `PilotAssessment.exe` and confirm both
   `app/PilotAssessment.Desktop.exe` and its private `python.exe` child have stopped.
2. Copy the whole software directory as a rollback point, or keep the original ZIP.
3. Edit ordinary `.py` and JSON resource files with any local text editor or IDE.
4. Preserve public DTO/schema compatibility unless you also update both Python and C# protocol
   contracts.
5. Restart the desktop app and inspect Diagnostics before using the changed mechanism. The new
   source identity is allowed to differ from the release baseline and will be frozen into future
   RunSnapshots.
6. Run a small representative Session before relying on a new operator or core change.

## Operator template and private dependencies

The copyable example is under `developer\examples\operator-extension`. Test it without installing:

```powershell
.\runtime\python\python.exe -I -B -X utf8 `
  .\developer\examples\operator-extension\test_example_scalar_offset.py
```

The complete extension steps are in `docs\python-operator-extension-development.md`. Normal
extensions use the same `OperatorDefinition`, registry, compiler, executor and schema-generated
WinUI form as built-ins; they do not require a C# page or plugin package.

If new code needs another Python package, close the application and use only the bundled helper:

```powershell
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 list
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 add "package-name>=1,<2"
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 remove "package-name"
powershell -ExecutionPolicy Bypass -File `
  .\developer\tools\manage_python_dependencies.ps1 sync
```

`add`/`remove` update `backend\pyproject.toml` and `backend\uv.lock`, then synchronize
`runtime\site-packages`. Restart afterward. The changed dependency and operator identities are
included in future RunSnapshots.

The original hashes are in `manifest\source-baseline.json`. A hash difference is evidence of a
local modification, not an automatic reason to block the software. Editing source while the app
is open produces `runtime.restart_required`; this only prevents a run from claiming bytes that the
current Python process did not import. Close and reopen the app to load the edited source.

The C#/WinUI source delivered for reference is under `developer\desktop-source`. C# changes require
a new desktop build with the .NET SDK and Windows development tools; Python changes do not.

The broader core-maintenance and C#/protocol manuals are M8C deliverables. The bundled operator
extension manual is the completed M8B-2 operational handoff.
