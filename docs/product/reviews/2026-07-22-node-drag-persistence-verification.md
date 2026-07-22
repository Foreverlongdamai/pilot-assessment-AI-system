# Node Drag Persistence Verification

| Field | Value |
|---|---|
| Date | 2026-07-22 |
| Scope | Post-RC.3 source correction on `main` |
| Decision | D-089 |
| Result | PASS |
| Candidate impact | No existing RC tag or package was rewritten; a later candidate must be rebuilt |

## 1. Reported failures

User acceptance found two observable defects in the Model Studio canvas:

1. a canonical ModelNode followed the pointer during drag but returned to its original position after release;
2. the five green Raw Input Family roots could not be dragged at all.

## 2. Root cause and correction

The canonical node control calculated movement relative to the moving control itself. More importantly, the `ItemsRepeater` could virtualize the bound item during the gesture, leaving the visible control with `Node == null` at release. The release path therefore reset the preview transform without queueing a layout mutation.

The correction uses XamlRoot coordinates, captures the target projection on pointer press, and sends normal release and pointer cancellation through one idempotent completion path. The five family controls now use the same gesture lifecycle. Their IDs are restricted to `raw-family.X`, `raw-family.U`, `raw-family.I`, `raw-family.G`, and `raw-family.P`; the backend accepts these IDs only as TaskScheme layout targets, and graph projection applies the saved coordinates to both the family roots and provenance-edge origins.

These family roots remain display-only. They are not ModelNodes and do not participate in Evidence extraction, BN inference, activation closure, CPTs, or RunSnapshot semantics.

## 3. Automated verification

- Desktop Unit: `113 passed`.
- Desktop real-sidecar Contract: `4 passed`.
- `tests/model_workspace/test_copy_and_batch.py`: `4 passed`.
- `tests/sidecar/test_methods.py`: `4 passed`.
- Ruff on the changed Python service and tests: PASS.
- x64 self-contained desktop publish: `0 warnings / 0 errors`.

The added regressions verify stable pointer tracking, target capture before virtualization, raw-family pointer support, projection of a family layout override, provenance origin rebinding, and backend persistence without inventing a corresponding ModelNode.

## 4. Visible Windows verification

A disposable portable RC.3 extraction was overlaid with the post-RC.3 source build and started through the root launcher. In the real WinUI window:

- in the final source build, `G.frames` moved from `(1069, 730)` to `(1041, 706)` and remained there after the debounce interval;
- in the same build, the visible portion of `X(t)` moved from `(816, 585)` to `(793, 571)` and remained there after the debounce interval;
- the staging database recorded the canonical node layout and `raw-family.X` layout while incrementing only the TaskScheme layout revision;
- “保存全部” completed with `已保存到系统模型`;
- after an earlier save/restart cycle, both canonical-node and family-root positions were reconstructed from the system model rather than returning to defaults.

The final verified application instance was left open and responsive. The verification copy is disposable and is not a replacement release candidate.

## 5. Boundary

This PASS closes the two reported drag defects in source. It does not alter the immutable `v0.1.0-rc.3` tag, ZIP, checksum, screenshots, or acceptance status. Any candidate delivered for renewed user acceptance must use a new candidate sequence and regenerate affected release evidence.
