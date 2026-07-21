# M7 Raw Input Family Provenance Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five larger, unified-green X/U/I/G/P input-family projections to the far-left of Model Studio and draw deterministic, read-only provenance links to the existing fine-grained Raw Input nodes.

**Architecture:** Keep the five family roots and their provenance links entirely in the C# projection layer. `GraphProjection` derives them from typed `RawInputNodeDefinition`, `SourceDescriptor.RawModality`, and dependency closure; Python canonical nodes, edges, hashes, activation, CPTs, snapshots, and persisted coordinates remain unchanged. Existing canonical coordinates receive a reversible render-only X offset.

**Tech Stack:** C# 14, .NET 10, WinUI 3, Windows App SDK, CommunityToolkit.Mvvm, xUnit.

---

| Field | Value |
|---|---|
| Milestone | M7 visual amendment |
| Approved design | [Raw Input Provenance and Single-Language Amendment](../specs/2026-07-18-m7-raw-input-provenance-and-single-language-model-content-amendment.md) |
| Decisions | D-054 |
| Execution policy | Inline, lightweight tests, no scientific golden expansion |
| Out of scope | Python model mutations, new raw data generators, operator main-canvas nodes, scientific calibration |

## Task 1: Freeze projection-only contracts

**Files:**

- Modify: `src/PilotAssessment.Desktop.Core/State/GraphProjection.cs`
- Test: `tests/PilotAssessment.Desktop.UnitTests/State/GraphProjectionTests.cs`

- [x] Add `GraphRawInputFamilyProjection` with stable `raw-family.X/U/I/G/P` identity, UI label, symbol, X/Y, diameter, member count, tooltip text, and automation name.
- [x] Add `GraphProvenanceEdgeProjection` that points from a family projection to an existing `GraphNodeProjection` without constructing `ModelGraphEdge`.
- [x] Extend `GraphProjectionResult` with `RawInputFamilies` and `ProvenanceEdges` while preserving `Nodes` and `Edges` as canonical-only collections.
- [x] Add constants for `RawInputFamilyDiameter = 148` and a render-only `CanonicalLaneOffsetX`; do not alter stored `NodeLayout` values.
- [x] Return all five family roots even when the current task has no member for one family.

Core shape:

```csharp
public sealed record GraphRawInputFamilyProjection(
    string ProjectionId,
    RawInputFamily Family,
    string Symbol,
    string DisplayName,
    string Description,
    double X,
    double Y,
    int MemberCount,
    string AutomationName)
{
    public double Diameter => GraphProjection.RawInputFamilyDiameter;
}
```

## Task 2: Derive provenance from typed descriptors

**Files:**

- Modify: `src/PilotAssessment.Desktop.Core/State/GraphProjection.cs`
- Test: `tests/PilotAssessment.Desktop.UnitTests/State/GraphProjectionTests.cs`

- [x] Map direct families `X→X`, `U→U`, `I→I`, `G→G`, `P/EEG/ECG→P`.
- [x] Map `pilot_camera` to the I family only for this visual projection; retain its canonical backend modality.
- [x] Resolve `SourceDependencies` recursively through source IDs so derived Raw Input nodes may connect to more than one family.
- [x] Treat missing, cyclic, or task/reference-only descriptors as zero-family provenance instead of guessing from node names.
- [x] Add unit tests for direct mapping, EEG/ECG aggregation, pilot-camera visual grouping, dependency closure, cycle safety, and absence of canonical graph mutations.

Expected focused test command:

```powershell
& 'C:\Program Files\dotnet\dotnet.exe' test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~GraphProjectionTests
```

Expected result: all focused projection tests pass; projected canonical node/edge counts remain unchanged.

## Task 3: Keep drag persistence reversible

**Files:**

- Modify: `src/PilotAssessment.Desktop/ViewModels/ModelStudioViewModel.cs`
- Test: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/GraphCommandTests.cs`

- [x] Expose observable `RawInputFamilies` and `ProvenanceEdges` collections.
- [x] Populate and clear them with each projection lifecycle.
- [x] When applying a pending canonical drag, update provenance endpoints but never move family roots.
- [x] Convert the rendered canonical X coordinate back to stored X before calling the backend layout mutation; prevent the display offset from accumulating after repeated drag/save/reload cycles.
- [x] Include family bounds in extent calculations.

## Task 4: Render the green family lane and provenance links

**Files:**

- Modify: `src/PilotAssessment.Desktop/App.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/ModelGraphControl.xaml`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/ModelGraphControl.xaml.cs`
- Add: `src/PilotAssessment.Desktop/Controls/Graph/RawInputFamilyNode.xaml`
- Add: `src/PilotAssessment.Desktop/Controls/Graph/RawInputFamilyNode.xaml.cs`

- [x] Add `GraphRawInputFamilyNodeBrush`, border, foreground, and provenance-edge theme resources. All five roots use the same green brush in light and dark themes.
- [x] Render the five 148-pixel family nodes above edges and below ordinary node interaction chrome.
- [x] Show the large `X/U/I/G/P` symbol and localized family label; do not expose copy/delete/activate/editor commands.
- [x] Draw read-only arrowed provenance links before canonical extraction/probabilistic edges and use a visually distinct green/neutral dashed style.
- [x] Keep ordinary fine-grained Raw Input nodes blue.

## Task 5: Localize projection UI and update the minimap

**Files:**

- Modify: `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw`
- Modify: `src/PilotAssessment.Desktop/Strings/zh-CN/Resources.resw`
- Modify: `src/PilotAssessment.Desktop/ViewModels/ModelStudioViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/ModelGraphControl.xaml.cs`

- [x] Add paired resource keys for X/U/I/G/P labels, descriptions, family kind, member-count tooltip, and provenance legend.
- [x] Refresh family labels immediately when UI language changes without backend calls or hash changes.
- [x] Draw green family dots and provenance lines in the minimap.
- [x] Provide automation names that include symbol, localized label, and member count; verify contrast in light and dark themes.

## Task 6: Verification and visible handoff

**Files:**

- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/reviews/2026-07-18-m7-raw-input-provenance-and-single-language-model-content-self-review.md`

- [x] Run `git diff --check`.
- [x] Run focused projection and graph-command tests.
- [x] Build the complete desktop solution for x64 Debug.
- [x] Launch the intended `PilotAssessment.Desktop.exe`, confirm a real top-level window, open Model Studio, and visually verify five unified-green roots at the far left with blue Raw Input children.
- [x] Leave the verified application running for user inspection.
- [x] Record exact commands/results and explicitly state that scientific Evidence/BN correctness was not tested by this visual amendment.

Final build command:

```powershell
& 'C:\Program Files\dotnet\dotnet.exe' build src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj -c Debug -p:Platform=x64
```

## Plan self-review

- The plan never creates backend family nodes or ghost edges.
- Unified green is applied to the five family projections only; existing blue Raw Input nodes remain intact.
- Provenance uses typed descriptors and dependency closure, not display-name heuristics.
- Layout offset is reversible and must not be persisted.
- Tests are lightweight and structural; no large synthetic streams or scientific golden claims are introduced.
