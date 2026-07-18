# M7B WinUI Expert Designer Implementation Plan

> **For agentic workers:** Execute INLINE, one task at a time. Do not spawn subagents. Steps use checkbox (`- [ ]`) syntax. M7A contracts and sidecar methods are the source of truth; never invent a second C# Evidence/BN engine.

**Goal:** Build the Windows desktop expert workspace that launches the local Python backend, opens managed projects/sessions, displays the global Raw Input/Evidence/BN graph, edits canonical nodes and task activation, and runs exact snapshot-based evaluations.

**Architecture:** Use an unpackaged WinUI 3 application for the M7 development cycle, backed by a testable .NET core library. The app supervises one JSON-RPC/JSONL stdio sidecar, maps M7 schemas into typed C# records, drives MVVM view models and reconciles every mutation with the backend canonical response. A task sidebar selects a `TaskScheme`; a virtualized graph shows the global node library with active/dim projection; separate top-level node windows host schema-driven editors. Resource files plus an explicitly refreshable localization service provide immediate Chinese/English switching.

**Tech Stack:** C#/.NET 10, WinUI 3, Windows App SDK, CommunityToolkit.Mvvm, Microsoft.Extensions.Hosting, System.Text.Json source generation, ItemsRepeater/custom `VirtualizingLayout`, AppWindow, xUnit, Python M7A stdio sidecar.

---

| Field | Value |
|---|---|
| Milestone | M7B |
| Date | 2026-07-17 |
| Status | Tasks 1–12 complete; Task 13 live Chinese/English switching is next |
| Parent roadmap | [M7 Implementation Roadmap](2026-07-17-m7-winui-expert-designer-implementation-roadmap.md) |
| Backend dependency | [M7A Current Model Runtime Plan](2026-07-17-m7a-current-model-runtime-implementation-plan.md) |
| Authoritative design | [M7 Design](../specs/2026-07-17-m7-winui-expert-designer-and-task-activation-workspace-design.md) |
| UI model | Current complete nodes + task activation; no normal Draft/Publish workflow |
| Distribution boundary | Development app only; final bundled distribution is M8 |

## 0. Execution and product rules

1. Do not begin normal UI integration until M7A Task 11 schemas/methods are stable and M7A Task 12 passes.
2. Work INLINE and commit after each task.
3. Before changing the machine, complete Task 1's non-mutating audit and obtain explicit user authorization for the WinUI prerequisite installation.
4. Use native WinUI controls, theme resources and Windows accessibility semantics. Add a custom graph surface only because WinUI has no complete editable graph control.
5. C# owns presentation, user intent, transport and reconciliation. Python owns canonical model state, validation, EvidenceRecipe execution, CPT operations, inference and run snapshots.
6. The client may use `JsonNode` for operator parameter values governed by backend JSON Schema. Domain identities, revisions, graph nodes, schemes, diagnostics and runs remain typed records.
7. Never run a shell command assembled from user text. Start the sidecar with `ProcessStartInfo.FileName` and `ArgumentList`.
8. Do not add a network port, arbitrary Python editor, Publish button, task-specific component-version picker or product synthetic-data generator.
9. Do not use `ApplicationData.Current` for unpackaged M7 preferences. Store non-domain UI state under `%LOCALAPPDATA%\PilotAssessmentSystem\`.
10. Unit tests cover deterministic client logic; one real sidecar contract smoke covers transport; one actual visible-window check covers launch. Do not create a large UI automation matrix.

## 1. Planned solution layout

```text
src/
  PilotAssessment.Desktop/
    PilotAssessment.Desktop.csproj
    PilotAssessment.Desktop.slnx
    App.xaml
    App.xaml.cs
    Assets/
    Controls/
      Editors/
      Graph/
    Services/
      Backend/
      Localization/
      Navigation/
      Preferences/
      Windowing/
    Styles/
    ViewModels/
    Views/
      Pages/
      Windows/
    Strings/
      en-US/Resources.resw
      zh-CN/Resources.resw
  PilotAssessment.Desktop.Core/
    PilotAssessment.Desktop.Core.csproj
    Contracts/
    Protocol/
    State/
    ViewModels/
tests/
  PilotAssessment.Desktop.UnitTests/
  PilotAssessment.Desktop.ContractTests/
```

The Core project must not reference WinUI. It holds JSON-RPC framing/client state, typed contracts, canonical reconciliation, graph projection view state, autosave coordination and localization fallback logic that can be tested without a window.

## 2. Platform source anchors

Implementation choices must remain aligned with current Microsoft platform behavior:

- multiple top-level windows and their position/size/presenter state use `Window`/`AppWindow`: [Manage app windows](https://learn.microsoft.com/en-us/windows/apps/develop/ui/manage-app-windows);
- the graph's reusable/virtualized item layer uses `ItemsRepeater`, hosted in a `ScrollViewer`: [ItemsRepeater](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/items-repeater);
- the development executable is unpackaged by setting `WindowsPackageType=None`; the Windows App SDK auto-initializer then resolves the installed runtime: [Distribute an unpackaged WinUI 3 app](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app);
- unpackaged Windows App SDK localization uses MRT Core resources: [Localize strings](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/mrtcore/localize-strings);
- `ApplicationLanguages.PrimaryLanguageOverride` may not refresh already loaded resources immediately, so runtime switching must explicitly reload the resource context and notify bindings: [ApplicationLanguages.PrimaryLanguageOverride](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.windows.globalization.applicationlanguages.primarylanguageoverride).

## Task 1: Audit, authorize and install the WinUI toolchain; scaffold the solution

**Files:**

- Create after authorization: `src/PilotAssessment.Desktop/`
- Create after authorization: `src/PilotAssessment.Desktop.Core/`
- Create after authorization: `tests/PilotAssessment.Desktop.UnitTests/`
- Create after authorization: `tests/PilotAssessment.Desktop.ContractTests/`
- Modify: `.gitignore`
- Modify: `docs/product/plans/2026-07-17-m7b-winui-expert-designer-implementation-plan.md`

Completed machine/toolchain audit on 2026-07-17:

- Windows 11 Home Chinese, version `10.0.26200`, x64;
- Visual Studio Community 2026 `18.8.0` is complete and launchable at `D:\visual_studio`;
- .NET SDK `10.0.302` and runtime `10.0.10` are installed at `C:\Program Files\dotnet`;
- the user-level `PATH` contains `C:\Program Files\dotnet` and `DOTNET_ROOT` points there (the already-running Codex host still requires the absolute executable path);
- Windows SDK `10.0.26100.0` is installed in the Windows-managed SDK location under `C:\Program Files (x86)\Windows Kits\10`;
- Developer Mode/sideloading registry flags are enabled;
- Microsoft-reserved template package `Microsoft.WindowsAppSDK.WinUI.CSharp.Templates` `0.0.6-alpha` is installed;
- Windows App Runtime `2.3.1.0` x64/x86 is registered for the unpackaged development executable.

- [x] Repeat and record the non-mutating checks:

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsArchitecture
Get-Command dotnet -ErrorAction SilentlyContinue
Get-Command vswhere -ErrorAction SilentlyContinue
Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -ErrorAction SilentlyContinue
```

- [x] Stop and obtain explicit user authorization before machine mutation. The user explicitly authorized the Visual Studio/.NET/Windows SDK setup and selected the `D:` Visual Studio installation location.
- [x] Install the prerequisites. The user installed Visual Studio through Visual Studio Installer, and the missing SDK/template/runtime pieces were then verified individually; the generic `winget configure` recipe was not run.
- [x] Verify:

```powershell
dotnet --info
dotnet --list-sdks
dotnet new list winui
```

Recorded: .NET SDK `10.0.302`; WinUI template package `0.0.6-alpha`; Windows App SDK NuGet/runtime `2.3.1`.

- [x] Scaffold an unpackaged solution. The current official Microsoft template exposes MVVM as `winui-mvvm` and does not support the older combined `-slnx -cpm -mvvm -imt -un` flags recorded in the pre-install draft. Use the supported template, create the solution separately, and apply Microsoft's documented unpackaged property:

```powershell
dotnet new winui-mvvm -n PilotAssessment.Desktop -o src/PilotAssessment.Desktop -tfm net10.0 -tpmv 10.0.19041.0 -U false -w 2.3.1 -wi 10.0.26100.7705 -p:w 0.4.0
dotnet new classlib -n PilotAssessment.Desktop.Core -o src/PilotAssessment.Desktop.Core -f net10.0
dotnet new xunit -n PilotAssessment.Desktop.UnitTests -o tests/PilotAssessment.Desktop.UnitTests -f net10.0
dotnet new xunit -n PilotAssessment.Desktop.ContractTests -o tests/PilotAssessment.Desktop.ContractTests -f net10.0
dotnet new sln -n PilotAssessment.Desktop -o src/PilotAssessment.Desktop --format slnx
dotnet sln src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx add src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj
dotnet sln src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx add src/PilotAssessment.Desktop.Core/PilotAssessment.Desktop.Core.csproj
dotnet sln src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx add tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj
dotnet sln src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx add tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj
dotnet add src/PilotAssessment.Desktop/PilotAssessment.Desktop.csproj reference src/PilotAssessment.Desktop.Core/PilotAssessment.Desktop.Core.csproj
dotnet add tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj reference src/PilotAssessment.Desktop.Core/PilotAssessment.Desktop.Core.csproj
dotnet add tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj reference src/PilotAssessment.Desktop.Core/PilotAssessment.Desktop.Core.csproj
```

- [x] Set `TargetFramework` to `net10.0-windows10.0.26100.0`, `TargetPlatformMinVersion` to `10.0.19041.0`, `WindowsPackageType` to `None`, x64 for verification, nullable enabled and warnings treated consistently with the generated template. Target SDK and minimum supported Windows version are distinct properties.
- [x] Add `bin/`, `obj/`, `.vs/`, test outputs and repository-local UI-state artifacts to `.gitignore`; do not ignore source resources or generated contract fixtures.
- [x] Run:

```powershell
dotnet restore src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -p:Platform=x64
dotnet test src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -p:Platform=x64
```

Recorded: restore succeeded for all four projects; x64 Debug build completed with `0` warnings and `0` errors; the two template smoke tests passed (`2/2`). The `.slnx` explicitly maps solution x64 to WinUI x64 and Core/test Any CPU projects.

- [x] Launch the exact unpackaged x64 executable and verify a non-zero top-level window handle whose title is `PilotAssessment.Desktop`, not the Windows App Runtime error dialog. The formal repository executable opened successfully and was left running for user inspection.

- [x] Commit:

```powershell
git add .gitignore src/PilotAssessment.Desktop src/PilotAssessment.Desktop.Core tests/PilotAssessment.Desktop.UnitTests tests/PilotAssessment.Desktop.ContractTests docs/product/plans/2026-07-17-m7b-winui-expert-designer-implementation-plan.md
git commit -m "build: scaffold M7 WinUI expert designer"
```

## Task 2: Add typed M7 contracts and source-generated JSON

**Files:**

- Create: `src/PilotAssessment.Desktop.Core/Contracts/ModelWorkspaceContracts.cs`
- Create: `src/PilotAssessment.Desktop.Core/Contracts/RunContracts.cs`
- Create: `src/PilotAssessment.Desktop.Core/Contracts/ProjectSessionContracts.cs`
- Create: `src/PilotAssessment.Desktop.Core/Contracts/JsonRpcContracts.cs`
- Create: `src/PilotAssessment.Desktop.Core/Contracts/PilotAssessmentJsonContext.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/Contracts/ContractSerializationTests.cs`
- Create: `tests/PilotAssessment.Desktop.ContractTests/Fixtures/`

- [x] Export representative canonical fixtures from the M7A Pydantic models into the ContractTests fixture directory; fixtures are small DTOs, not session payloads.
- [x] Implement immutable C# records/enums for project/session, `ModelNode`, discriminated node definitions, `TaskScheme`, graph snapshot/diff, impact, diagnostics, current preflight/snapshot/run and result summaries.
- [x] Map snake_case JSON explicitly and preserve opaque IDs/hashes as strings; never normalize or infer them client-side.
- [x] Use `JsonDerivedType`/discriminators or custom converters only where source generation needs them. Keep `JsonNode` confined to Evidence operator parameter values and diagnostic details.
- [x] Add a source-generated `JsonSerializerContext` containing every request/response/notification DTO used by the client.
- [x] Test Python fixture → typed record → JSON round trip and strict enum/required-field behavior.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~ContractSerializationTests
```

Expected: canonical fixtures deserialize without changing IDs, ordering or hashes.

Recorded: all 10 canonical fixture files were accepted again by their originating M7A Pydantic models; focused C# contract tests passed `9/9`; the full desktop solution tests passed `10/10`; the x64 Debug solution build completed with `0` warnings and `0` errors. The first build attempt was blocked only because the Task 1 inspection process still held the executable open; after closing that exact process, the unchanged source built cleanly.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop.Core/Contracts tests/PilotAssessment.Desktop.UnitTests/Contracts tests/PilotAssessment.Desktop.ContractTests/Fixtures
git commit -m "feat: add typed M7 desktop contracts"
```

## Task 3: Implement JSONL framing and the supervised sidecar process

**Files:**

- Create: `src/PilotAssessment.Desktop.Core/Protocol/JsonLineFramer.cs`
- Create: `src/PilotAssessment.Desktop.Core/Protocol/JsonRpcClient.cs`
- Create: `src/PilotAssessment.Desktop.Core/Protocol/BackendLaunchOptions.cs`
- Create: `src/PilotAssessment.Desktop/Services/Backend/SidecarProcessHost.cs`
- Create: `src/PilotAssessment.Desktop/Services/Backend/DevelopmentBackendLocator.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/Protocol/JsonLineFramerTests.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/Protocol/JsonRpcClientTests.cs`
- Create: `tests/PilotAssessment.Desktop.ContractTests/SidecarContractTests.cs`

- [x] Implement UTF-8 JSONL framing with a 4 MiB maximum line, one JSON object per line, request-ID matching, notification dispatch and protocol-fault shutdown.
- [x] Implement a concurrency-safe pending-request map using `TaskCompletionSource`, cancellation tokens and exactly-once completion.
- [x] Start the process with `UseShellExecute=false`, redirected stdin/stdout/stderr and no visible console. Stdout goes only to the framer; stderr goes to a bounded diagnostic buffer/log sink.
- [x] For development, locate the repository root and use `.tools\uv\uv.exe` with separate arguments `run`, `python`, `-m`, `pilot_assessment.sidecar`. Allow explicit executable and argument-array configuration; never parse a shell command string.
- [x] Perform `hello`, protocol/capability validation and health check before enabling project commands. Send clean shutdown, then terminate only after a bounded timeout.
- [x] Retry an idempotent write with the same transaction ID only when the response was not received; never invent a new ID for the same logical autosave.
- [x] Unit-test split/coalesced lines, oversize frames, malformed JSON, out-of-order responses, notifications, cancellation and stderr isolation.
- [x] Contract-test a real Python subprocess: hello → capabilities → shutdown; assert every stdout line is valid JSON-RPC and no session payload is returned inline.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~Protocol
dotnet test tests/PilotAssessment.Desktop.ContractTests/PilotAssessment.Desktop.ContractTests.csproj --filter FullyQualifiedName~SidecarContractTests
```

Expected: real sidecar lifecycle passes without a network port.

Recorded: focused protocol tests passed `12/12`; the real `.tools\uv\uv.exe run python -m pilot_assessment.sidecar` contract passed `1/1` in about two seconds using only hello, capabilities, health and shutdown; full desktop tests passed Unit `21/21` and Contract `2/2`; x64 Debug build completed with `0` warnings and `0` errors. The real lifecycle did not open a project, import a session or return payload/bytes inline.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop.Core/Protocol src/PilotAssessment.Desktop/Services/Backend tests/PilotAssessment.Desktop.UnitTests/Protocol tests/PilotAssessment.Desktop.ContractTests/SidecarContractTests.cs
git commit -m "feat: supervise the local assessment sidecar"
```

## Task 4: Compose the WinUI host, navigation shell and state services

**Files:**

- Modify: `src/PilotAssessment.Desktop/App.xaml`
- Modify: `src/PilotAssessment.Desktop/App.xaml.cs`
- Create: `src/PilotAssessment.Desktop/Services/Navigation/NavigationService.cs`
- Create: `src/PilotAssessment.Desktop/Services/Preferences/LocalPreferencesStore.cs`
- Create: `src/PilotAssessment.Desktop/ViewModels/ShellViewModel.cs`
- Create: `src/PilotAssessment.Desktop/Views/MainWindow.xaml`
- Create: `src/PilotAssessment.Desktop/Views/MainWindow.xaml.cs`
- Create: `src/PilotAssessment.Desktop/Views/Pages/DiagnosticsPage.xaml`
- Create: `tests/PilotAssessment.Desktop.UnitTests/State/ShellStateTests.cs`

- [x] Compose services/view models using `Host.CreateApplicationBuilder`, dependency injection and one application lifetime owner.
- [x] Build a `NavigationView` shell with Project, Session, Model Studio, Runs/Results, Library and Diagnostics destinations.
- [x] Add a top command bar showing current project, session, task scheme, backend health, autosave state, language, theme and run status.
- [x] Disable domain commands until the sidecar handshake and project context are ready; show an actionable diagnostics page on startup failure.
- [x] Store only non-domain preferences at `%LOCALAPPDATA%\PilotAssessmentSystem\ui-state.json` using an atomic temp/write/replace sequence. Do not store current nodes/schemes outside the managed project.
- [x] Dispose windows, pending requests and the sidecar in deterministic order during app shutdown.
- [x] Unit-test shell readiness/error/reconnect command states without WinUI controls.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~ShellStateTests
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -p:Platform=x64
```

Expected: shell builds and state tests pass.

Recorded: focused shell-state tests passed `4/4`; the full desktop suite passed Unit `25/25` and Contract `2/2`; the x64 Debug solution build completed with `0` warnings and `0` errors. A normal visible launch reached a non-zero `MainWindowHandle`, displayed backend state `Ready`, exposed all planned navigation destinations, and started the supervised `uv`/Python sidecar chain. Closing the top-level window terminated the application and every recorded child process. The persisted `%LOCALAPPDATA%\PilotAssessmentSystem\ui-state.json` contained only `language`, `theme` and `lastDestination`, with no domain model state.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop/App.xaml src/PilotAssessment.Desktop/App.xaml.cs src/PilotAssessment.Desktop/Services src/PilotAssessment.Desktop/ViewModels/ShellViewModel.cs src/PilotAssessment.Desktop/Views tests/PilotAssessment.Desktop.UnitTests/State
git commit -m "feat: add the WinUI application shell"
```

## Task 5: Implement project launcher and managed session workspace

**Files:**

- Create: `src/PilotAssessment.Desktop/Views/Pages/ProjectLauncherPage.xaml`
- Create: `src/PilotAssessment.Desktop.Core/ViewModels/ProjectLauncherViewModel.cs`
- Create: `src/PilotAssessment.Desktop/Views/Pages/SessionExplorerPage.xaml`
- Create: `src/PilotAssessment.Desktop.Core/ViewModels/SessionExplorerViewModel.cs`
- Create: `src/PilotAssessment.Desktop/Services/Backend/ProjectSessionClient.cs`
- Create: `src/PilotAssessment.Desktop/Services/Preferences/FolderPickerService.cs`
- Create: `src/PilotAssessment.Desktop/Services/Preferences/RecentProjectStore.cs`
- Modify: `src/pilot_assessment/sidecar/methods.py`
- Create: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/ProjectSessionViewModelTests.cs`

- [x] Support Create Project and Open Project using folder pickers and backend canonical descriptors.
- [x] Maintain a local recent-project list as convenience only; do not copy or move projects outside explicit backend operations.
- [x] Support Inspect then Import Session. Explain that import copies the session bundle into managed project storage; display source path and managed revision separately.
- [x] List sessions/revisions, modality availability, ingestion/synchronization reports and artifact references without loading large image/timeseries payloads into UI memory.
- [x] Show visual/gaze/EEG/ECG as first-class input families even when the selected session marks them missing/export pending.
- [x] Do not provide a Generate Synthetic Data product action.
- [x] Test picker cancellation, inspect diagnostics, import response reconciliation and reopen state.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~ProjectSessionViewModelTests
```

Expected: project/session view models use IDs and artifact references, not raw data arrays.

Recorded: the pure Core view models were placed under the §1 testable-Core boundary rather than the original Desktop file-list draft. Focused project/session tests passed `4/4`; the canonical Python ingestion fixture raised contract serialization coverage to `10/10`; the full desktop suite passed Unit `30/30` and Contract `2/2`; x64 Debug built with `0` warnings and `0` errors. A single existing real-sidecar vertical test passed with the new bounded `session.report.get` checks in `28.71s`; it added no new dataset. The final executable opened a visible Project Launcher with backend `Ready`, create/open/recent controls, a non-zero window handle, and no residual application or sidecar process after normal close.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop.Core/ViewModels src/PilotAssessment.Desktop/Views/Pages/ProjectLauncherPage.xaml src/PilotAssessment.Desktop/Views/Pages/SessionExplorerPage.xaml src/PilotAssessment.Desktop/Services/Backend/ProjectSessionClient.cs src/PilotAssessment.Desktop/Services/Preferences src/pilot_assessment/sidecar/methods.py tests/PilotAssessment.Desktop.UnitTests/ViewModels/ProjectSessionViewModelTests.cs
git commit -m "feat: add managed project and session workspace"
```

## Task 6: Implement the task-scheme sidebar

**Files:**

- Create: `src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml.cs`
- Create: `src/PilotAssessment.Desktop.Core/ViewModels/TaskSchemeListViewModel.cs`
- Create: `src/PilotAssessment.Desktop/Services/Backend/ModelWorkspaceClient.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/TaskSchemeListViewModelTests.cs`

- [x] Load schemes through `model.scheme.list`; select one scheme context without mutating it.
- [x] Provide search, tags/group filters, sort and archived visibility.
- [x] Provide Create, Copy, Rename and Archive. Copy must immediately add/select the new parallel scheme and retain shared node IDs.
- [x] Do not show Draft, Published, Apply or Publish fields/actions.
- [x] Keep scheme selection synchronized through the shared shell scheme context consumed by graph/editor/run workspaces.
- [x] Reconcile create/copy/update from backend canonical responses, including new revision/hash/status.
- [x] Test rapid switching, copy insertion, selection persistence and stale-response suppression.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~TaskSchemeListViewModelTests
```

Expected: scheme UX is a parallel editable task list, not a publication workflow.

- [x] Verification: focused `TaskSchemeListViewModelTests` `6/6`; full desktop Unit `36/36`; Contract `2/2`; x64 Debug build `0 warning / 0 error`; visible process PID `23528` reached non-zero `MainWindowHandle=13436790`, then normal close left no app or sidecar process.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml src/PilotAssessment.Desktop/Controls/TaskSchemeSidebar.xaml.cs src/PilotAssessment.Desktop.Core/ViewModels/TaskSchemeListViewModel.cs src/PilotAssessment.Desktop/Services/Backend/ModelWorkspaceClient.cs tests/PilotAssessment.Desktop.UnitTests/ViewModels/TaskSchemeListViewModelTests.cs
git commit -m "feat: add task scheme navigation"
```

## Task 7: Build the global active/dim model graph surface

**Files:**

- Create: `src/PilotAssessment.Desktop/Views/Pages/ModelStudioPage.xaml`
- Create: `src/PilotAssessment.Desktop/ViewModels/ModelStudioViewModel.cs`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/ModelGraphControl.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/ModelGraphControl.xaml.cs`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/GraphNodeButton.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/GraphNodeButton.xaml.cs`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/GraphVirtualizingLayout.cs`
- Create: `src/PilotAssessment.Desktop.Core/State/GraphProjection.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/State/GraphProjectionTests.cs`

- [x] Consume one backend `ModelGraphSnapshot`; do not reconstruct parents from display edges or old component versions.
- [x] Use `ScrollViewer` for pan/zoom and an `ItemsRepeater` with position-aware `VirtualizingLayout` for node realization. Render edges in a separate lightweight layer clipped to the visible viewport.
- [x] Draw normal nodes as circles with clear two/three-line short names. Distinguish Raw Input, Evidence, BN sub-skill and aggregate competency through graph theme resources, label and icon; do not rely on color alone.
- [x] Active nodes/edges use normal contrast; inactive global nodes/edges remain real but dim. Provide Active only, Active + Inactive and All Global Nodes views.
- [x] Distinguish extraction and probabilistic edges by line/arrow pattern and legend. The editable canvas renders canonical edges only, so inference influence remains a separate read-only result concern.
- [x] Add search/filter by bilingual name, node kind, group, tags and scheme usage; include Fit, zoom controls and minimap.
- [x] Make nodes keyboard-focusable buttons with automation name, kind, active state and status. Support selection/multi-selection and context menu.
- [x] Test projection/filter/active-edge logic on a 7-node DTO; do not snapshot-test pixels.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~GraphProjectionTests
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -p:Platform=x64
```

Expected: graph view builds and deterministic projection tests pass.

- [x] Verification: focused `GraphProjectionTests` `3/3`; full desktop Unit `39/39`; Contract `2/2`; x64 Debug build `0 warning / 0 error`. A real M7A sidecar project loaded `53` global nodes, `67` canonical edges and `52` active nodes; the visible WinUI window realized `39` viewport-buffer node buttons, displayed extraction/probabilistic edges, selected `Trajectory tracking`, and contained no temporary layout diagnostics. App and sidecar were then stopped with no residual process.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop/Views/Pages/ModelStudioPage.xaml src/PilotAssessment.Desktop/ViewModels/ModelStudioViewModel.cs src/PilotAssessment.Desktop/Controls/Graph src/PilotAssessment.Desktop.Core/State/GraphProjection.cs tests/PilotAssessment.Desktop.UnitTests/State/GraphProjectionTests.cs
git commit -m "feat: add the active task model graph"
```

## Task 8: Add graph editing, activation, deactivation and copy/paste

**Files:**

- Modify: `src/PilotAssessment.Desktop/ViewModels/ModelStudioViewModel.cs`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/ModelGraphControl.xaml.cs`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/DeactivationImpactDialog.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Graph/NodeCreationDialog.xaml`
- Create: `src/PilotAssessment.Desktop.Core/State/ModelClipboard.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/GraphCommandTests.cs`

- [x] Add New Node actions for Raw Input, Evidence and BN. Create a minimally valid/incomplete backend node then open its editor; never generate Python code. Task 8 raises the editor-window request boundary; Task 9 supplies the actual independent window.
- [x] Enable a node by calling `model.scheme.activate` and immediately apply the returned closure/diff. Do not show a parent confirmation.
- [x] For deactivation, call preview. If another node is impacted, show the full canonical inactive-set list and Continue/Cancel. Continue sends expected revision plus `impact_hash`; Cancel sends no write. A single-node change proceeds without an unnecessary cascade prompt.
- [x] Map Delete on the task canvas to current-scheme deactivation. Put global archive only in Library/node usage UI with a distinct label.
- [x] Implement Ctrl+C/Ctrl+V and context-menu copy using an in-app typed clipboard containing project ID/source node IDs. Paste calls backend node copy/batch operation; it never locally duplicates definitions.
- [x] Default paste copies only selected nodes and retains original fixed parents; source nodes remain active until explicitly deactivated.
- [x] Implement drag layout with transient local movement and a debounced `model.layout.update`; canonical layout response wins.
- [x] Implement typed connect/remove-edge gestures that open the CPT or EvidenceRecipe-binding migration choice and submit one backend atomic operation.
- [x] Test Continue/Cancel, stale impact hash, scheme isolation, copy parent retention and Delete semantics.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~GraphCommandTests
```

Expected: tests assert backend requests and canonical response reconciliation, not local fake mutations.

Verification: focused `GraphCommandTests` passed `7/7`; full desktop Unit passed `46/46`; Contract passed `3/3`; focused Python current-edge regression passed `4/4`; x64 Debug build completed with `0` warnings and `0` errors. One temporary real-sidecar contract created all three node kinds, kept an incrementally edited Evidence technically incomplete, added its exact Raw Input extraction binding, activated the backend parent closure, copied a starter Evidence while retaining its fixed parents, then previewed and applied deactivation using the exact impact hash. A visible WinUI check loaded the existing `53`-node/`67`-edge/`52`-active project, opened the creation form and node menu, mapped Delete to a 14-node canonical impact dialog, and proved Cancel retained `52` active with no pending write. App, sidecar and temporary project were cleaned up. Extraction operations were corrected to permit recipe/CPT-incomplete expert work-in-progress while preserving diagnostics and run blocking.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop src/PilotAssessment.Desktop.Core src/pilot_assessment/model_workspace/service.py tests/PilotAssessment.Desktop.UnitTests tests/PilotAssessment.Desktop.ContractTests/SidecarContractTests.cs
git commit -m "feat: edit task activation from the model graph"
```

Recorded commit: `ab7b9d5`.

## Task 9: Implement multiple independent node windows

**Files:**

- Create: `src/PilotAssessment.Desktop/Views/Windows/NodeEditorWindow.xaml`
- Create: `src/PilotAssessment.Desktop/Views/Windows/NodeEditorWindow.xaml.cs`
- Create: `src/PilotAssessment.Desktop/Services/Windowing/NodeWindowRegistry.cs`
- Create: `src/PilotAssessment.Desktop/Services/Windowing/WindowPlacementStore.cs`
- Create: `src/PilotAssessment.Desktop.Core/State/NodeWindowKey.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/State/NodeWindowRegistryTests.cs`

- [x] Key windows by `(project_id, scheme_id, node_id)`. Opening the same key focuses the existing window; other nodes/task contexts may open concurrently.
- [x] Use top-level `Window` and `AppWindow` for Move, Resize, presenter/maximize state and Changed events.
- [x] Keep the main graph interactive while node windows are open; windows are non-modal.
- [x] Persist bounds/maximized state in `%LOCALAPPDATA%\PilotAssessmentSystem\ui-state.json`, validate restored bounds against current displays and recover off-screen windows.
- [x] Title each window with bilingual node name, node kind, current task context, shared-scheme count, revision and save/conflict state.
- [x] Route canonical node change notifications to all windows displaying the same node. A window with unsaved text shows a conflict action instead of being silently overwritten.
- [x] Unit-test key uniqueness, focus-existing, independent contexts, close cleanup and placement normalization without creating a real window.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~NodeWindowRegistryTests
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -p:Platform=x64
```

Expected: registry tests pass and WinUI window code builds.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop/Views/Windows src/PilotAssessment.Desktop/Services/Windowing src/PilotAssessment.Desktop.Core/State/NodeWindowKey.cs tests/PilotAssessment.Desktop.UnitTests/State/NodeWindowRegistryTests.cs
git commit -m "feat: add independent node editor windows"
```

Recorded commit: `fdd7772`. Fresh verification: desktop Unit `52/52`, Contract `3/3`, x64 Debug build `0 warning / 0 error`, and `git diff --check` clean. Visible WinUI verification kept the main graph interactive while two node windows were open, reused the existing window for an identical key, and restored both ordinary bounds and maximized state after close/reopen. The implementation also works around a Windows App SDK 2.3 projection issue by indexing `DisplayArea.FindAll()` rather than enumerating it through LINQ.

## Task 10: Build Raw Input and Evidence node editors

**Files:**

- Create: `src/PilotAssessment.Desktop/Controls/Editors/RawInputEditor.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Editors/EvidenceEditor.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Editors/OperatorGraphEditor.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Editors/SchemaParameterForm.xaml`
- Create: `src/PilotAssessment.Desktop/ViewModels/RawInputEditorViewModel.cs`
- Create: `src/PilotAssessment.Desktop/ViewModels/EvidenceEditorViewModel.cs`
- Create: `src/PilotAssessment.Desktop.Core/State/JsonSchemaFormModel.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/EvidenceEditorTests.cs`

- [x] Raw Input editor: bilingual identity, X/U/I/G/P family, source/schema/adapter/profile, fields/units/clock binding, session availability and help text.
- [x] Evidence tabs: General; Raw Input bindings; EvidenceRecipe/operator graph; Parameters; Windows/Aggregation/Scoring/D-A-U; Observation states; Probabilistic parents/CPT summary; Preview/Trace; Used by schemes; History.
- [x] Generate parameter controls from backend `OperatorDefinition.parameter_schema` and `ui` hints: text, numeric, enum, boolean, list/object and unit/help metadata. Preserve unsupported JSON fields read-only instead of dropping them.
- [x] Operator graph edits use operator IDs/ports from the backend catalog and submit the complete typed recipe update. C# never evaluates formulas/operators.
- [x] Show missing operator as a technical run blocker while still allowing the node definition to be inspected/saved.
- [x] Preview calls `model.preview.node` with the selected managed session and renders the backend's current frozen snapshot metadata, technical trace and artifact references. Actual executed Evidence measurements/results remain Task 14 run-workspace scope.
- [x] Used-by view lists every scheme sharing the node and explains that edits affect future runs for all of them.
- [x] Test schema-form generation, parameter preservation, recipe request mapping and preview cancellation with small fixtures.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~EvidenceEditorTests
```

Expected: form/view-model tests pass without implementing an Evidence calculation in C#.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop/Controls/Editors src/PilotAssessment.Desktop/ViewModels/RawInputEditorViewModel.cs src/PilotAssessment.Desktop/ViewModels/EvidenceEditorViewModel.cs src/PilotAssessment.Desktop.Core/State/JsonSchemaFormModel.cs tests/PilotAssessment.Desktop.UnitTests/ViewModels/EvidenceEditorTests.cs
git commit -m "feat: add raw input and Evidence node editors"
```

Recorded commit: `59396ee`. Fresh verification: desktop Unit `57/57`, Contract `3/3`, focused Python node-service regression `4/4`, x64 Debug build `0 warning / 0 error`, and `git diff --check` clean. Visible WinUI verification loaded the managed `53`-node/`67`-edge/`52`-active project, proved text input no longer triggers graph copy/paste accelerators, opened Raw Input through the new direct double-click entry, and showed a clean `Canonical · rev 0` editor rather than a false dirty state. Evidence metadata loading was visibly checked with `45` trusted operators, one task usage and one history event. Editors construct typed update intent and local dirty state; durable autosave/reconciliation is intentionally Task 12. `model.preview.node` remains a current frozen snapshot preview, not an executed-measurement claim; Task 14 owns run execution/results.

## Task 11: Build BN state, parent and CPT editors

**Files:**

- Create: `src/PilotAssessment.Desktop/Controls/Editors/BnNodeEditor.xaml`
- Create: `src/PilotAssessment.Desktop/Controls/Editors/CptGridEditor.xaml`
- Create: `src/PilotAssessment.Desktop/ViewModels/BnNodeEditorViewModel.cs`
- Create: `src/PilotAssessment.Desktop.Core/State/CptGridModel.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/BnNodeEditorTests.cs`

- [x] BN tabs: General; fixed parents/children; states; CPT/generator; current posterior/influence; Used by schemes; History.
- [x] Render CPT axes from the backend materialized grid, virtualize rows, support keyboard cell navigation, paste rectangular numeric blocks and display row-sum/finite/shape diagnostics.
- [x] Make CPT maximizable within the node window while retaining one canonical editor state.
- [x] Parent/state changes first request backend migration/materialization choices, then send one atomic operation. Never locally save an edge while leaving CPT axes stale.
- [x] Display canonical BN direction and a separate read-only inference influence overlay; do not offer a command that converts influence arrows into edges.
- [x] Reconcile submitted cells with backend canonical probabilities and revision.
- [x] Test axes/order mapping, rectangular paste validation, atomic request composition and canonical response replacement.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~BnNodeEditorTests
```

Expected: CPT/state/parent view-model tests pass and no probability calculation is duplicated.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop/Controls/Editors/BnNodeEditor.xaml src/PilotAssessment.Desktop/Controls/Editors/CptGridEditor.xaml src/PilotAssessment.Desktop/ViewModels/BnNodeEditorViewModel.cs src/PilotAssessment.Desktop.Core/State/CptGridModel.cs tests/PilotAssessment.Desktop.UnitTests/ViewModels/BnNodeEditorTests.cs
git commit -m "feat: add BN and CPT node editors"
```

Recorded commit: `d034442`. Fresh verification: focused `BnNodeEditorTests` passed `4/4`; complete desktop Unit passed `61/61`; Contract passed `3/3`; x64 Debug build completed with `0` warnings and `0` errors; `git diff --check` was clean apart from Git's existing line-ending notice. Visible WinUI verification opened the selected `Task Control Proficiency` BN node in an independent top-level window, loaded canonical revision `0` with `0` fixed parents, `4` children, one task usage and one history event, and displayed the backend-owned `1`-row / `3`-state CPT with finite/shape/row-sum status, rectangular paste, normalization, complete-row save, expand/collapse and backend generator controls. The toolbar now also exposes a discoverable **Open details** command while double-click and the node menu remain available.

C# performs only presentation-side technical checks, row editing/normalization and typed request composition. Python remains the sole implementation of CPT materialization, state/parent migration, canonical persistence and Bayesian inference. The posterior/influence tab explains this direction and exposes read-only result references; actual run execution and posterior/result rendering remain Task 14. Ordinary General-field autosave and durable conflict reconciliation remain Task 12, while discrete state/parent/CPT transactions already commit atomically and reload the canonical graph.

## Task 12: Implement autosave, canonical reconciliation and conflict recovery

**Files:**

- Create: `src/PilotAssessment.Desktop.Core/State/AutosaveCoordinator.cs`
- Create: `src/PilotAssessment.Desktop.Core/State/CanonicalObjectStore.cs`
- Create: `src/PilotAssessment.Desktop/Controls/SaveConflictBanner.xaml`
- Modify: node/scheme editor view models
- Create: `tests/PilotAssessment.Desktop.UnitTests/State/AutosaveCoordinatorTests.cs`

- [x] Serialize writes per canonical node/scheme with an async queue or `SemaphoreSlim`; allow independent objects to save concurrently.
- [x] Debounce text/continuous numeric edits for 350 ms. Save discrete activation, edge, CPT batch, copy and archive commands immediately.
- [x] Assign one transaction ID per logical save and reuse it for safe retry. Include expected semantic/layout revision.
- [x] On success, replace local canonical state with the backend response, then reapply only edits typed after that request began.
- [x] On revision conflict, retain pending user input and show Reload or Reapply. Reapply creates a new request against the returned current revision; never silently overwrite.
- [x] Show Saving, Saved, Offline/Retry, Conflict and Blocked status in each editor and the shell.
- [x] Keep scientific warnings visible but non-blocking. Prevent Preview/Run only for backend technical blockers.
- [x] Test debounce collapse, ordered saves, same-ID retry, late response, conflict/reapply and shutdown flush/cancel.
- [x] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~AutosaveCoordinatorTests
```

Expected: deterministic concurrency tests pass with an injected short debounce and no long-running sleeps or large workflow fixture.

- [x] Commit:

```powershell
git add src/PilotAssessment.Desktop.Core/State src/PilotAssessment.Desktop/Controls/SaveConflictBanner.xaml src/PilotAssessment.Desktop/ViewModels tests/PilotAssessment.Desktop.UnitTests/State/AutosaveCoordinatorTests.cs
git commit -m "feat: autosave canonical model edits"
```

Recorded commit: `b9376ea`. The shared canonical store serializes writes for one object while preserving concurrency across independent objects; ordinary text/form intent uses a 350 ms debounce, and existing activation, edge, copy/archive, parent/state and CPT commands remain immediate typed backend transactions. Each logical save carries a caller-owned transaction ID, retries reuse that ID, late canonical responses rebase only newer local intent, and revision conflicts retain input behind explicit **Reload** / **Reapply** actions. Editor and shell surfaces expose Pending/Saving/Saved, Offline/Retry, Conflict and Blocked states; node-window shutdown flushes queued intent.

Fresh verification: desktop Unit `67/67`, Contract `3/3`, x64 Debug build `0 warning / 0 error`, and `git diff --check` clean apart from Git's existing line-ending notice. Visible WinUI verification edited the `Task Control Proficiency` English description, observed canonical revision `0 → 1`, restored the original text at revision `2`, closed the independent editor, and reopened it with revision `2` and the restored backend value. This proves the normal form path writes Python-owned canonical state rather than keeping a C#-only copy. No Evidence/BN scientific algorithm, CPT value or task activation was changed. Task 14 remains the owner of actual run/posterior/result execution.

## Task 13: Add immediate Chinese/English switching

**Files:**

- Create: `src/PilotAssessment.Desktop/Strings/en-US/Resources.resw`
- Create: `src/PilotAssessment.Desktop/Strings/zh-CN/Resources.resw`
- Create: `src/PilotAssessment.Desktop/Services/Localization/LocalizationService.cs`
- Create: `src/PilotAssessment.Desktop.Core/State/BilingualTextSelector.cs`
- Modify: all visible shell/page/control XAML and view models
- Create: `tests/PilotAssessment.Desktop.UnitTests/State/LocalizationTests.cs`

- [ ] Put all product-owned visible strings, status labels, errors and accessibility names in resource files with one-to-one keys.
- [ ] Implement a resource indexer/service that explicitly reloads the selected MRT Core resource context and raises binding notifications. Do not rely only on already-loaded `x:Uid` resources after `PrimaryLanguageOverride` changes.
- [ ] Switch visible shell, open node windows, dialogs and graph labels immediately; newly opened windows inherit the selected language.
- [ ] Select model `name_zh/name_en` and descriptions client-side with a visible fallback marker when one translation is absent. Do not mutate backend metadata during language switch.
- [ ] Persist language as a local UI preference only. Assert IDs, revisions, hashes, parameter values and results do not change.
- [ ] Test resource parity, fallback, live change notification and identity invariance.
- [ ] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~LocalizationTests
```

Expected: both resource sets have equal keys and switching changes presentation only.

- [ ] Commit:

```powershell
git add src/PilotAssessment.Desktop/Strings src/PilotAssessment.Desktop/Services/Localization src/PilotAssessment.Desktop.Core/State/BilingualTextSelector.cs src/PilotAssessment.Desktop tests/PilotAssessment.Desktop.UnitTests/State/LocalizationTests.cs
git commit -m "feat: add live Chinese and English UI"
```

## Task 14: Add preview, runs, results, trace and diagnostics pages

**Files:**

- Create: `src/PilotAssessment.Desktop/Views/Pages/RunsPage.xaml`
- Create: `src/PilotAssessment.Desktop/Views/Pages/ResultsPage.xaml`
- Create: `src/PilotAssessment.Desktop/ViewModels/RunsViewModel.cs`
- Create: `src/PilotAssessment.Desktop/ViewModels/ResultsViewModel.cs`
- Create: `src/PilotAssessment.Desktop/Services/Backend/RunClient.cs`
- Create: `tests/PilotAssessment.Desktop.UnitTests/ViewModels/RunResultViewModelTests.cs`

- [ ] Build run setup from selected managed session revision and current scheme; call `model.run.preflight` and show exact technical errors/warnings.
- [ ] Start a run without Publish. Display the frozen scheme revision/node hashes and explicit scientific-status banner.
- [ ] Consume progress notifications/events, allow cancellation and recover queued/running/interrupted state after app or sidecar restart.
- [ ] Show Evidence D/A/U observations, competency/sub-skill posterior distributions, inference trace/influence, coverage/provenance and artifact links from result DTOs.
- [ ] Keep canonical BN edges visually separate from inference influence in every result view.
- [ ] Open large artifacts through backend artifact references/managed paths; do not deserialize video/images/timeseries into JSON-RPC.
- [ ] Diagnostics page shows backend version/capabilities, stderr tail, project recovery, schema identities and audit events without exposing secrets.
- [ ] Test preflight blocking, automatic snapshot identity, progress ordering, cancellation and result mapping.
- [ ] Run:

```powershell
dotnet test tests/PilotAssessment.Desktop.UnitTests/PilotAssessment.Desktop.UnitTests.csproj --filter FullyQualifiedName~RunResultViewModelTests
```

Expected: run/result state tests pass and normal flow contains no publication step.

- [ ] Commit:

```powershell
git add src/PilotAssessment.Desktop/Views/Pages/RunsPage.xaml src/PilotAssessment.Desktop/Views/Pages/ResultsPage.xaml src/PilotAssessment.Desktop/ViewModels/RunsViewModel.cs src/PilotAssessment.Desktop/ViewModels/ResultsViewModel.cs src/PilotAssessment.Desktop/Services/Backend/RunClient.cs tests/PilotAssessment.Desktop.UnitTests/ViewModels/RunResultViewModelTests.cs
git commit -m "feat: add assessment runs and results workspace"
```

## Task 15: Close accessibility, performance, contract and visible-launch gates

**Files:**

- Modify: `src/PilotAssessment.Desktop/Styles/`
- Modify: `src/PilotAssessment.Desktop/Controls/Graph/`
- Modify: `src/PilotAssessment.Desktop/Views/`
- Create: `tests/PilotAssessment.Desktop.ContractTests/CurrentModelWorkflowTests.cs`
- Modify: `docs/product/11_IMPLEMENTATION_STATUS.md`
- Modify: `docs/product/README.md`
- Modify: this plan and the M7 roadmap

- [ ] Verify keyboard navigation, focus visibility, automation names, high contrast, light/dark themes, 100/150/200% scaling and screen-reader state text on the main workflow.
- [ ] Verify graph virtualization/viewport culling with a generated in-memory DTO of 1,000 nodes; this is a UI projection benchmark, not a backend dataset or scientific test. Record realization count and interaction responsiveness without saving those fake nodes to a product project.
- [ ] Run the complete .NET tests and build:

```powershell
dotnet test src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -p:Platform=x64
dotnet build src/PilotAssessment.Desktop/PilotAssessment.Desktop.slnx -c Debug -p:Platform=x64
```

- [ ] Run `CurrentModelWorkflowTests` against a real M7A subprocess: create/open project → list/copy scheme → copy/edit node → activation/deactivation → preflight/run → result → close/reopen. Use the smallest existing managed fixture.
- [ ] Launch the unpackaged executable visibly. Locate the exact built executable, start it with a normal visible window and poll for a non-zero `MainWindowHandle` for at most 15 seconds. Do not count process existence alone as success.
- [ ] Keep the successfully launched application open for user inspection at the end of the verification turn unless the user asks for headless completion.
- [ ] Manually verify two simultaneous node windows, task switching active/dim state, copy/paste, cascade Continue/Cancel, autosave/conflict banner, Chinese/English switch and one result view.
- [ ] Confirm no TCP listener is opened by the application/backend and stdout remains protocol-only.
- [ ] Update status documents with exact SDK/template versions, test counts, build output, contract smoke and visible-window evidence. State M8 packaging and scientific validation remain undone.
- [ ] Record actual task commit hashes in this plan.
- [ ] Commit:

```powershell
git add src/PilotAssessment.Desktop src/PilotAssessment.Desktop.Core tests/PilotAssessment.Desktop.UnitTests tests/PilotAssessment.Desktop.ContractTests docs/product
git commit -m "test: close M7 WinUI expert designer"
```

## 3. Planned commit ledger

| Task | Planned commit | Actual commit |
|---:|---|---|
| 1 | `build: scaffold M7 WinUI expert designer` | `6809bcc` |
| 2 | `feat: add typed M7 desktop contracts` | `5f64ca3` |
| 3 | `feat: supervise the local assessment sidecar` | `b039d46` |
| 4 | `feat: add the WinUI application shell` | `6e1974e` (`fd15c2b` removes the generated Core placeholder) |
| 5 | `feat: add managed project and session workspace` | `296622f` |
| 6 | `feat: add task scheme navigation` | `5761b63` |
| 7 | `feat: add the active task model graph` | `974e8c1` |
| 8 | `feat: edit task activation from the model graph` | `ab7b9d5` |
| 9 | `feat: add independent node editor windows` | `fdd7772` |
| 10 | `feat: add raw input and Evidence node editors` | `59396ee` |
| 11 | `feat: add BN and CPT node editors` | `d034442` |
| 12 | `feat: autosave canonical model edits` | `b9376ea` |
| 13 | `feat: add live Chinese and English UI` | Not executed |
| 14 | `feat: add assessment runs and results workspace` | Not executed |
| 15 | `test: close M7 WinUI expert designer` | Not executed |

## 4. M7B completion definition

M7B is complete only after Task 15 records fresh unit, real-sidecar, build and visible-window evidence. A XAML mock, a successfully compiled process with no window, or a client that still calls Draft/Publish does not complete M7B.

Until then the status must distinguish:

- M7A backend readiness;
- M7B scaffold/feature progress;
- actual visible WinUI launch;
- M8 packaged distribution;
- scientific calibration/validation.

Only the first three belong to M7. M8 must later bundle the backend runtime, code and front end while excluding each user's local session data.
