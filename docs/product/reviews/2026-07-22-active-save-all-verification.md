# Active Save All Verification

| Field | Value |
|---|---|
| Date | 2026-07-22 |
| Decision | D-088 |
| Scope | Post-RC.3 source correction on `main` |
| Candidate status | Not tagged or packaged |
| Scientific status | Engineering workflow only; no scientific claim changed |

## Verified behaviour

The main CommandBar now exposes one localised and accessible **Save all** action. `Ctrl+S`
invokes the same path. The action flushes floating node editors and pending graph layout, reads the
software-owned edit-session status, skips a clean workspace, commits a dirty workspace through
`model.edit.commit`, reloads system task schemes/current graph, and keeps the application open.

All successful model mutations mark the shell as having staged changes. A canonical commit shows
**Saved to system model** rather than the obsolete project-owned wording. Save failure preserves
the staged session. A post-commit presentation refresh failure is reported separately so that an
already successful canonical write is never described as failed. The existing close-time
Save/Discard/Cancel prompt remains in place, and close/save operations share one serial gate.

## Fresh automated evidence

```text
Desktop Unit Release:       112 passed, 0 failed
Real-sidecar Contract x64:    4 passed, 0 failed
x64 Release build:            0 warnings, 0 errors
```

No Python production code changed, so the 1,760-test Python release suite was not repeated for
this focused WinUI correction. The real-sidecar contract run retained coverage of the existing
JSON-RPC model-edit commit boundary.

## Visible Windows evidence

A disposable extraction of the immutable RC.3 package supplied the private runtime, backend and
system store; the current desktop publish was overlaid only in that temporary copy.

1. O6 was deactivated in Model Studio, producing a dirty edit session.
2. **Save all** committed it; the graph reloaded with O6 inactive and the application stayed open.
3. A normal `WM_CLOSE` then exited without a dirty-edit dialog, proving that active save left the
   edit session clean.
4. The latest desktop build was overlaid and reopened. O6 was reactivated, immediately showing
   **Staged changes pending**.
5. **Save all** changed the status to **Saved to system model**; the refreshed graph retained O6
   active and the same desktop window remained responsive.
6. UI Automation reported a visible Save button rectangle of `96 x 48` logical pixels and a
   non-zero main-window handle. Visual inspection confirmed that the button label and saved-state
   text were not clipped.

The final verified disposable application instance was intentionally left open for user inspection.
No user project, Session, result or artifact was placed in a product package.

## Release boundary

The annotated `v0.1.0-rc.3` tag and its ZIP remain unchanged. This verification does not declare a
new release candidate or user acceptance. Once the current inspection round is complete, a new
candidate sequence must rebuild the bilingual manuals, screenshots, manifest, package and external
verification evidence from the accepted source.
