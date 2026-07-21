# Copyable Python operator extension example

This directory is a developer example, not an installed operator and not scientific assessment
content. It demonstrates the ordinary-source extension path used by one unpacked product copy.

## Try the example without changing the product

From the product root:

```powershell
.\runtime\python\python.exe -I -B -X utf8 `
  .\developer\examples\operator-extension\test_example_scalar_offset.py
```

## Install it into this software copy

1. Close `PilotAssessment.Desktop.exe`; keep the original ZIP or copy the whole product directory.
2. Copy `example_scalar_offset.py` into
   `backend/src/pilot_assessment/evidence/extensions/example_scalar_offset.py`.
3. Open `backend/src/pilot_assessment/evidence/extensions/__init__.py` and add:

   ```python
   from .example_scalar_offset import register_example_scalar_offset
   ```

4. Inside `register_extension_operators(registry)`, replace the clean-distribution
   `del registry` line with:

   ```python
   register_example_scalar_offset(registry)
   ```

5. Restart the desktop application. Diagnostics will show a changed source/operator identity, and
   the EvidenceRecipe operator catalog will contain `Example scalar offset`.

`parameter_schema` and `parameter_ui` drive the existing generic parameter form. No C# page or
operator-specific switch is required. Give a genuinely different implementation a different
operator ID or implementation version; duplicate identities fail visibly at startup.

If the implementation needs a package that is not already present, use
`developer/tools/manage_python_dependencies.ps1` as documented in
`backend/README-DEVELOPMENT.md`. Normal thresholds, recipe composition, parents, CPTs and task
activation remain front-end edits and should not be moved into Python.
