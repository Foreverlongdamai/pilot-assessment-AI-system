from __future__ import annotations

import json
from pathlib import Path

import pytest

from pilot_assessment.anchors import registry
from pilot_assessment.anchors.catalog import (
    REFERENCE_PREPROCESSING_IDENTITIES,
    load_packaged_catalog,
)
from pilot_assessment.anchors.fingerprint import runtime_registry_fingerprint
from pilot_assessment.contracts.anchor_execution import (
    AnchorCapabilityStatus,
    AnchorRuntimeRegistry,
    ContentMemberIdentity,
    NumericRuntimeIdentity,
    PluginRegistryEntry,
    PreprocessingProviderDefinition,
    PreprocessingRegistryEntry,
    PythonRuntimeIdentity,
)
from tests.anchors import fakes

_ANCHOR_MEMBER_PATH = "pilot_assessment/anchors/plugins/fake_reference_anchor.py"
_PROVIDER_MEMBER_PATH = "pilot_assessment/anchors/primitives/fake_reference_provider.py"


@pytest.fixture
def anchor_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PluginRegistryEntry, fakes.TrustedModuleHarness]:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_MODULE_SOURCE)
    harness.install(monkeypatch)
    entry = registry._build_plugin_entry("O1", fakes.FAKE_ANCHOR_MODULE, "create_plugin")
    return entry, harness


@pytest.fixture
def provider_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[PreprocessingRegistryEntry, fakes.TrustedModuleHarness]:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(fakes.FAKE_PROVIDER_MODULE, fakes.PROVIDER_MODULE_SOURCE)
    harness.install(monkeypatch)
    entry = registry._build_preprocessing_entry(
        "fake-reference-provider", fakes.FAKE_PROVIDER_MODULE, "create_provider"
    )
    return entry, harness


# --------------------------------------------------------------------------- #
# Packaged registry capability honesty
# --------------------------------------------------------------------------- #


def test_packaged_registry_has_fifteen_plugins_and_reports_remaining_not_implemented() -> None:
    catalog = load_packaged_catalog()
    packaged = registry.load_packaged_registry()

    for entry in catalog.entries:
        capability = packaged.capability(entry.plugin_id, entry.plugin_version)
        if entry.anchor_id in {
            "O1",
            "O2",
            "O3",
            "O4",
            "O5",
            "O6",
            "O7",
            "O8",
            "O9",
            "O10",
            "O11",
            "O12",
            "H1",
            "H2",
            "H3",
        }:
            assert capability.status is AnchorCapabilityStatus.AVAILABLE
            assert capability.entry is not None
            assert capability.entry.anchor_id == entry.anchor_id
        else:
            assert capability.status is AnchorCapabilityStatus.NOT_IMPLEMENTED
            assert capability.entry is None
        assert capability.diagnostics == ()

    assert len(catalog.entries) == 18
    for identity in REFERENCE_PREPROCESSING_IDENTITIES:
        capability = packaged.preprocessing_capability(
            str(identity["provider_id"]), str(identity["provider_version"])
        )
        if identity["provider_id"] in {
            "movement-events-v1",
            "gaze-aoi-intervals-v1",
            "fixation-intervals-v1",
        }:
            assert capability.status == "available"
            assert capability.entry is not None
            assert capability.entry.provider_id == identity["provider_id"]
        else:
            assert capability.status == "not_implemented"
            assert capability.entry is None


def test_packaged_registry_fingerprint_binds_the_canonical_model() -> None:
    fingerprint = registry.packaged_registry_fingerprint()
    model = registry._load_registry_model()
    assert [entry.anchor_id for entry in model.entries] == [
        "H1",
        "H2",
        "H3",
        "O1",
        "O10",
        "O11",
        "O12",
        "O2",
        "O3",
        "O4",
        "O5",
        "O6",
        "O7",
        "O8",
        "O9",
    ]
    assert [entry.provider_id for entry in model.preprocessors] == [
        "fixation-intervals-v1",
        "gaze-aoi-intervals-v1",
        "movement-events-v1",
    ]
    assert fingerprint == runtime_registry_fingerprint(model)
    assert fingerprint == registry.packaged_registry_fingerprint()


def test_o5_and_movement_provider_registry_closures_bind_shared_code_and_numeric_runtimes() -> None:
    model = registry._load_registry_model()
    o5 = next(entry for entry in model.entries if entry.anchor_id == "O5")
    movement = next(
        entry for entry in model.preprocessors if entry.provider_id == "movement-events-v1"
    )

    assert tuple(item.normalized_name for item in o5.numeric_runtimes) == (
        "numpy",
        "polars",
        "scipy",
    )
    assert tuple(item.package_relative_path for item in o5.implementation_members) == (
        "pilot_assessment/anchors/plugins/o5_workload_rate.py",
        "pilot_assessment/anchors/primitives/movement.py",
    )
    assert tuple(item.normalized_name for item in movement.numeric_runtimes) == (
        "numpy",
        "polars",
        "scipy",
    )
    assert tuple(item.package_relative_path for item in movement.implementation_members) == (
        "pilot_assessment/anchors/primitives/movement.py",
    )


def test_o6_registry_closure_binds_only_its_plugin_and_polars_runtime() -> None:
    model = registry._load_registry_model()
    o6 = next(entry for entry in model.entries if entry.anchor_id == "O6")

    assert tuple(item.normalized_name for item in o6.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in o6.implementation_members) == (
        "pilot_assessment/anchors/plugins/o6_control_magnitude_rms.py",
    )


def test_o7_registry_closure_binds_shared_movement_reversal_and_models() -> None:
    model = registry._load_registry_model()
    o7 = next(entry for entry in model.entries if entry.anchor_id == "O7")

    assert tuple(item.normalized_name for item in o7.numeric_runtimes) == (
        "numpy",
        "polars",
        "scipy",
    )
    assert tuple(item.package_relative_path for item in o7.implementation_members) == (
        "pilot_assessment/anchors/plugins/o7_control_reversal_rate.py",
        "pilot_assessment/anchors/primitives/models.py",
        "pilot_assessment/anchors/primitives/movement.py",
        "pilot_assessment/anchors/primitives/reversal.py",
    )


def test_o8_registry_closure_binds_only_its_plugin_and_polars_runtime() -> None:
    model = registry._load_registry_model()
    o8 = next(entry for entry in model.entries if entry.anchor_id == "O8")

    assert tuple(item.normalized_name for item in o8.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in o8.implementation_members) == (
        "pilot_assessment/anchors/plugins/o8_tpx_composite.py",
    )


def test_o9_registry_closure_binds_plugin_movement_and_numeric_runtimes() -> None:
    model = registry._load_registry_model()
    o9 = next(entry for entry in model.entries if entry.anchor_id == "O9")

    assert tuple(item.normalized_name for item in o9.numeric_runtimes) == (
        "numpy",
        "polars",
        "scipy",
    )
    assert tuple(item.package_relative_path for item in o9.implementation_members) == (
        "pilot_assessment/anchors/plugins/o9_dead_band_activity.py",
        "pilot_assessment/anchors/primitives/movement.py",
    )


def test_o10_registry_closure_binds_plugin_event_primitive_and_polars() -> None:
    model = registry._load_registry_model()
    o10 = next(entry for entry in model.entries if entry.anchor_id == "O10")

    assert tuple(item.normalized_name for item in o10.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in o10.implementation_members) == (
        "pilot_assessment/anchors/plugins/o10_recovery_time.py",
        "pilot_assessment/anchors/primitives/events.py",
    )


def test_o11_registry_closure_binds_plugin_event_primitive_and_polars() -> None:
    model = registry._load_registry_model()
    o11 = next(entry for entry in model.entries if entry.anchor_id == "O11")

    assert tuple(item.normalized_name for item in o11.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in o11.implementation_members) == (
        "pilot_assessment/anchors/plugins/o11_disturbance_latency.py",
        "pilot_assessment/anchors/primitives/events.py",
    )


def test_o12_registry_closure_binds_plugin_event_primitive_and_polars() -> None:
    model = registry._load_registry_model()
    o12 = next(entry for entry in model.entries if entry.anchor_id == "O12")

    assert tuple(item.normalized_name for item in o12.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in o12.implementation_members) == (
        "pilot_assessment/anchors/plugins/o12_envelope_drift_latency.py",
        "pilot_assessment/anchors/primitives/events.py",
    )


def test_h1_and_gaze_aoi_provider_registry_closures_bind_exact_code_and_polars() -> None:
    model = registry._load_registry_model()
    h1 = next(entry for entry in model.entries if entry.anchor_id == "H1")
    gaze = next(
        entry for entry in model.preprocessors if entry.provider_id == "gaze-aoi-intervals-v1"
    )

    assert tuple(item.normalized_name for item in h1.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in h1.implementation_members) == (
        "pilot_assessment/anchors/plugins/h1_aoi_dwell.py",
    )
    assert tuple(item.normalized_name for item in gaze.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in gaze.implementation_members) == (
        "pilot_assessment/anchors/primitives/gaze_aoi.py",
    )


def test_h2_and_fixation_provider_registry_closures_bind_exact_code_and_polars() -> None:
    model = registry._load_registry_model()
    h2 = next(entry for entry in model.entries if entry.anchor_id == "H2")
    fixation = next(
        entry for entry in model.preprocessors if entry.provider_id == "fixation-intervals-v1"
    )

    assert tuple(item.normalized_name for item in h2.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in h2.implementation_members) == (
        "pilot_assessment/anchors/plugins/h2_first_fixation_latency.py",
    )
    assert tuple(item.normalized_name for item in fixation.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in fixation.implementation_members) == (
        "pilot_assessment/anchors/primitives/fixation.py",
    )


def test_h3_registry_closure_binds_shared_h1_aggregation_contract_and_polars() -> None:
    model = registry._load_registry_model()
    h3 = next(entry for entry in model.entries if entry.anchor_id == "H3")

    assert tuple(item.normalized_name for item in h3.numeric_runtimes) == ("polars",)
    assert tuple(item.package_relative_path for item in h3.implementation_members) == (
        "pilot_assessment/anchors/plugins/h1_aoi_dwell.py",
        "pilot_assessment/anchors/plugins/h3_off_task_dwell.py",
    )


# --------------------------------------------------------------------------- #
# Test-only factory injection
# --------------------------------------------------------------------------- #


def test_from_factories_for_testing_exposes_injected_plugins() -> None:
    reg = registry.PluginRegistry.from_factories_for_testing(
        {("fake-reference-anchor", "0.1.0"): fakes.create_fake_plugin},
        {("fake-reference-provider", "1.0.0"): fakes.create_fake_provider},
    )

    assert (
        reg.capability("fake-reference-anchor", "0.1.0").status is AnchorCapabilityStatus.AVAILABLE
    )
    assert reg.preprocessing_capability("fake-reference-provider", "1.0.0").status == "available"

    plugin = reg.resolve("fake-reference-anchor", "0.1.0", "0" * 64)
    assert isinstance(plugin, fakes.FakeAnchorPlugin)
    provider = reg.resolve_preprocessor("fake-reference-provider", "1.0.0", "0" * 64)
    assert isinstance(provider, fakes.FakePreprocessingProvider)


def test_from_factories_for_testing_reports_unknown_keys_not_implemented() -> None:
    reg = registry.PluginRegistry.from_factories_for_testing({}, {})

    assert reg.capability("missing", "0.1.0").status is AnchorCapabilityStatus.NOT_IMPLEMENTED
    assert reg.preprocessing_capability("missing", "0.1.0").status == "not_implemented"
    with pytest.raises(registry.RegistryResolutionError):
        reg.resolve("missing", "0.1.0", "0" * 64)
    with pytest.raises(registry.RegistryResolutionError):
        reg.resolve_preprocessor("missing", "0.1.0", "0" * 64)


# --------------------------------------------------------------------------- #
# Trusted verification round trips
# --------------------------------------------------------------------------- #


def test_build_and_verify_trusted_plugin_entry_round_trips(
    anchor_entry: tuple[PluginRegistryEntry, fakes.TrustedModuleHarness],
) -> None:
    entry, _harness = anchor_entry

    assert registry.verify_implementation_closure(entry) is None
    assert entry.anchor_id == "O1"
    assert entry.plugin_id == "fake-reference-anchor"
    assert tuple(member.package_relative_path for member in entry.implementation_members) == (
        _ANCHOR_MEMBER_PATH,
    )
    assert entry.numeric_runtimes == ()
    assert entry.resource_members == ()


def test_build_and_verify_trusted_provider_entry_round_trips(
    provider_entry: tuple[PreprocessingRegistryEntry, fakes.TrustedModuleHarness],
) -> None:
    entry, _harness = provider_entry

    assert registry.verify_preprocessing_closure(entry) is None
    assert entry.provider_id == "fake-reference-provider"
    assert tuple(member.package_relative_path for member in entry.implementation_members) == (
        _PROVIDER_MEMBER_PATH,
    )


def test_trusted_registry_resolve_binds_the_exact_build(
    anchor_entry: tuple[PluginRegistryEntry, fakes.TrustedModuleHarness],
) -> None:
    entry, _harness = anchor_entry
    reg = registry.PluginRegistry._from_model(
        AnchorRuntimeRegistry(entries=(entry,), preprocessors=())
    )

    capability = reg.capability("fake-reference-anchor", "0.1.0")
    assert capability.status is AnchorCapabilityStatus.AVAILABLE
    assert capability.entry == entry

    plugin = reg.resolve("fake-reference-anchor", "0.1.0", entry.implementation_digest)
    assert plugin.definition().anchor_id == "O1"

    with pytest.raises(registry.RegistryResolutionError):
        reg.resolve("fake-reference-anchor", "0.1.0", "b" * 64)


def test_trusted_capability_distinguishes_unavailable_from_not_implemented(
    anchor_entry: tuple[PluginRegistryEntry, fakes.TrustedModuleHarness],
) -> None:
    entry, _harness = anchor_entry
    reg = registry.PluginRegistry._from_model(
        AnchorRuntimeRegistry(entries=(entry,), preprocessors=())
    )

    assert (
        reg.capability("fake-reference-anchor", "9.9.9").status
        is AnchorCapabilityStatus.PLUGIN_UNAVAILABLE
    )
    assert (
        reg.capability("unregistered-plugin", "0.1.0").status
        is AnchorCapabilityStatus.NOT_IMPLEMENTED
    )


def test_trusted_capability_reports_incompatible_with_diagnostics(
    anchor_entry: tuple[PluginRegistryEntry, fakes.TrustedModuleHarness],
) -> None:
    entry, _harness = anchor_entry
    tampered = entry.model_copy(update={"definition_fingerprint": "c" * 64})
    reg = registry.PluginRegistry._from_model(
        AnchorRuntimeRegistry(entries=(tampered,), preprocessors=())
    )

    capability = reg.capability("fake-reference-anchor", "0.1.0")
    assert capability.status is AnchorCapabilityStatus.INCOMPATIBLE
    assert capability.diagnostics
    assert capability.diagnostics[0].error_code == "anchor.plugin.incompatible"


# --------------------------------------------------------------------------- #
# Per-field tamper rejection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "update",
    [
        {"parameter_schema_sha256": "a" * 64},
        {"measurement_schema_sha256": "a" * 64},
        {"definition_fingerprint": "a" * 64},
        {"artifact_schema_hashes": {"fake-trace-v0.1": "a" * 64}},
        {"implementation_members": ()},
        {
            "implementation_members": (
                ContentMemberIdentity(
                    package_relative_path=_ANCHOR_MEMBER_PATH, content_sha256="0" * 64
                ),
                ContentMemberIdentity(
                    package_relative_path="pilot_assessment/anchors/plugins/other.py",
                    content_sha256="0" * 64,
                ),
            )
        },
        {"implementation_digest": "a" * 64},
        {
            "python_runtime": PythonRuntimeIdentity(
                implementation_name="cpython",
                version=(0, 0, 0),
                cache_tag="tampered",
                soabi="tampered",
            )
        },
        {"plugin_version": "0.2.0"},
    ],
)
def test_verify_rejects_tampered_plugin_entry(
    anchor_entry: tuple[PluginRegistryEntry, fakes.TrustedModuleHarness],
    update: dict[str, object],
) -> None:
    entry, _harness = anchor_entry
    tampered = entry.model_copy(update=update)
    with pytest.raises(registry.RegistryError):
        registry.verify_implementation_closure(tampered)


def test_build_rejects_anchor_id_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_MODULE_SOURCE)
    harness.install(monkeypatch)
    with pytest.raises(registry.RegistryError):
        registry._build_plugin_entry("O2", fakes.FAKE_ANCHOR_MODULE, "create_plugin")


# --------------------------------------------------------------------------- #
# Factory binding rejection
# --------------------------------------------------------------------------- #


def test_build_rejects_external_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(registry.RegistryError):
        registry._build_plugin_entry("O1", "os", "create_plugin")


def test_build_rejects_missing_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_MODULE_SOURCE)
    harness.install(monkeypatch)
    with pytest.raises(registry.RegistryError):
        registry._build_plugin_entry("O1", fakes.FAKE_ANCHOR_MODULE, "missing_symbol")


def test_build_rejects_non_callable_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(
        fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_MODULE_SOURCE + "\ncreate_plugin = 5\n"
    )
    harness.install(monkeypatch)
    with pytest.raises(registry.RegistryError):
        registry._build_plugin_entry("O1", fakes.FAKE_ANCHOR_MODULE, "create_plugin")


# --------------------------------------------------------------------------- #
# Static import closure
# --------------------------------------------------------------------------- #


def test_static_closure_collects_helper_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_source(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_WITH_HELPER_SOURCE)
    harness.add_source(fakes.FAKE_ANCHOR_HELPER_MODULE, fakes.HELPER_MODULE_SOURCE)
    harness.install(monkeypatch)

    closure = registry._static_import_closure(fakes.FAKE_ANCHOR_MODULE)

    assert {member.package_relative_path for member in closure.members} == {
        _ANCHOR_MEMBER_PATH,
        "pilot_assessment/anchors/plugins/fake_reference_helper.py",
    }


def test_o1_static_closure_includes_only_its_shared_scientific_primitives() -> None:
    closure = registry._static_import_closure(
        "pilot_assessment.anchors.plugins.o1_phase_state_precision"
    )

    assert tuple(member.package_relative_path for member in closure.members) == (
        "pilot_assessment/anchors/plugins/o1_phase_state_precision.py",
        "pilot_assessment/anchors/primitives/__init__.py",
        "pilot_assessment/anchors/primitives/envelopes.py",
        "pilot_assessment/anchors/primitives/models.py",
    )
    assert closure.numeric_distribution_names == ("polars",)


def test_static_closure_rejects_dynamic_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_source(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_DYNAMIC_IMPORT_SOURCE)
    harness.install(monkeypatch)
    with pytest.raises(registry.RegistryError):
        registry._static_import_closure(fakes.FAKE_ANCHOR_MODULE)


def test_static_closure_rejects_namespace_crossing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_source(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_NAMESPACE_CROSSING_SOURCE)
    harness.install(monkeypatch)
    with pytest.raises(registry.RegistryError):
        registry._static_import_closure(fakes.FAKE_ANCHOR_MODULE)


# --------------------------------------------------------------------------- #
# Runtime lock
# --------------------------------------------------------------------------- #


def _python_identity() -> PythonRuntimeIdentity:
    return PythonRuntimeIdentity(
        implementation_name="cpython",
        version=(3, 11, 9),
        cache_tag="cpython-311",
        soabi="cp311-win_amd64",
    )


def _numpy_identity() -> NumericRuntimeIdentity:
    return NumericRuntimeIdentity(
        normalized_name="numpy", version="2.3.4", record_content_sha256="a" * 64
    )


def test_runtime_lock_accepts_matching_identities(monkeypatch: pytest.MonkeyPatch) -> None:
    python_identity = _python_identity()
    numpy_identity = _numpy_identity()
    monkeypatch.setattr(registry, "python_runtime_identity", lambda: python_identity)
    monkeypatch.setattr(
        registry, "distribution_content_identity", lambda name: {"numpy": numpy_identity}[name]
    )

    assert (
        registry._verify_runtime_lock(
            python_identity, (numpy_identity,), expected_distribution_names=("numpy",)
        )
        is None
    )


def test_runtime_lock_rejects_python_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "python_runtime_identity", _python_identity)
    other = _python_identity().model_copy(update={"soabi": "cp312-win_amd64"})
    with pytest.raises(registry.RegistryError):
        registry._verify_runtime_lock(other, (), expected_distribution_names=())


@pytest.mark.parametrize(
    ("declared", "expected"),
    [
        ((), ("numpy",)),
        (("numpy",), ()),
    ],
)
def test_runtime_lock_rejects_numeric_allowlist_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    declared: tuple[str, ...],
    expected: tuple[str, ...],
) -> None:
    python_identity = _python_identity()
    numpy_identity = _numpy_identity()
    monkeypatch.setattr(registry, "python_runtime_identity", lambda: python_identity)
    monkeypatch.setattr(
        registry, "distribution_content_identity", lambda name: {"numpy": numpy_identity}[name]
    )
    declared_runtimes = tuple(numpy_identity for _ in declared)
    with pytest.raises(registry.RegistryError):
        registry._verify_runtime_lock(
            python_identity, declared_runtimes, expected_distribution_names=expected
        )


def test_runtime_lock_rejects_install_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    python_identity = _python_identity()
    declared = _numpy_identity()
    installed = declared.model_copy(update={"record_content_sha256": "f" * 64})
    monkeypatch.setattr(registry, "python_runtime_identity", lambda: python_identity)
    monkeypatch.setattr(
        registry, "distribution_content_identity", lambda name: {"numpy": installed}[name]
    )
    with pytest.raises(registry.RegistryError):
        registry._verify_runtime_lock(
            python_identity, (declared,), expected_distribution_names=("numpy",)
        )


# --------------------------------------------------------------------------- #
# Provider definition dependency slots (contract guard)
# --------------------------------------------------------------------------- #


def test_provider_definition_rejects_duplicate_dependency_slots() -> None:
    with pytest.raises(ValueError):
        PreprocessingProviderDefinition(
            provider_id="dup-provider",
            provider_version="1.0.0",
            api_version="0.1.0",
            required_streams=("U",),
            required_context_paths=(),
            required_semantic_paths=(),
            required_reference_ids=(),
            dependencies=(
                {
                    "dependency_id": "dep",
                    "expected_schema_id": "s-v0.1",
                    "expected_artifact_kind": "event_trace",
                },
                {
                    "dependency_id": "dep",
                    "expected_schema_id": "s-v0.1",
                    "expected_artifact_kind": "event_trace",
                },
            ),
            parameter_schema_id="movement-events-v1-parameters-0.1",
            output_schema_id="dup-output-v0.1",
            output_schema_descriptor=fakes._PROVIDER_OUTPUT_DESCRIPTOR,
            artifact_kind="event_trace",
            output_payload_kind="table",
        )


# --------------------------------------------------------------------------- #
# Module CLI
# --------------------------------------------------------------------------- #


def _empty_registry_file(tmp_path: Path) -> Path:
    path = tmp_path / "registry-v1.json"
    path.write_text(
        json.dumps(
            {
                "contract_id": "anchor-runtime-registry",
                "contract_version": "0.1.0",
                "entries": [],
                "preprocessors": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_cli_verify_reports_fingerprint_for_packaged_registry(
    capsys: pytest.CaptureFixture[str],
) -> None:
    return_code = registry.main(["verify"])
    captured = capsys.readouterr()

    assert return_code == 0
    expected = f"registry_fingerprint={registry.packaged_registry_fingerprint()}"
    assert captured.out.strip() == expected
    assert captured.err == ""


def test_cli_rejects_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert registry.main(["bogus"]) == 2
    assert capsys.readouterr().err


def test_cli_refresh_absent_entry_requires_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_file = _empty_registry_file(tmp_path)
    monkeypatch.setattr(registry, "_registry_resource_path", lambda: registry_file)

    assert registry.main(["refresh", "--anchor", "O1"]) == 2
    assert capsys.readouterr().err


def test_cli_refresh_writes_and_reports_plugin_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_file = _empty_registry_file(tmp_path)
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(fakes.FAKE_ANCHOR_MODULE, fakes.ANCHOR_MODULE_SOURCE)
    harness.install(monkeypatch)
    monkeypatch.setattr(registry, "_registry_resource_path", lambda: registry_file)

    first = registry.main(
        [
            "refresh",
            "--anchor",
            "O1",
            "--factory-module",
            fakes.FAKE_ANCHOR_MODULE,
            "--factory-symbol",
            "create_plugin",
        ]
    )
    first_out = capsys.readouterr().out
    assert first == 0
    assert "old_digest=absent" in first_out

    model = AnchorRuntimeRegistry.model_validate_json(registry_file.read_bytes())
    assert len(model.entries) == 1
    assert model.entries[0].anchor_id == "O1"
    assert registry.verify_implementation_closure(model.entries[0]) is None
    new_digest = model.entries[0].implementation_digest
    assert f"new_digest={new_digest}" in first_out

    second = registry.main(["refresh", "--anchor", "O1"])
    second_out = capsys.readouterr().out
    assert second == 0
    assert f"old_digest={new_digest}" in second_out
    assert f"new_digest={new_digest}" in second_out


def test_cli_refresh_preprocessor_writes_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry_file = _empty_registry_file(tmp_path)
    harness = fakes.TrustedModuleHarness(tmp_path)
    harness.add_module(fakes.FAKE_PROVIDER_MODULE, fakes.PROVIDER_MODULE_SOURCE)
    harness.install(monkeypatch)
    monkeypatch.setattr(registry, "_registry_resource_path", lambda: registry_file)

    return_code = registry.main(
        [
            "refresh-preprocessor",
            "--provider",
            "fake-reference-provider",
            "--factory-module",
            fakes.FAKE_PROVIDER_MODULE,
            "--factory-symbol",
            "create_provider",
        ]
    )
    out = capsys.readouterr().out
    assert return_code == 0
    assert "provider=fake-reference-provider" in out

    model = AnchorRuntimeRegistry.model_validate_json(registry_file.read_bytes())
    assert len(model.preprocessors) == 1
    assert model.entries == ()
    assert registry.verify_preprocessing_closure(model.preprocessors[0]) is None
