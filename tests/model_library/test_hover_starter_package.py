from __future__ import annotations

import shutil
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import pytest

from pilot_assessment.bayesian.inference import InferenceEngine
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceVersion,
)
from pilot_assessment.evidence.builtins import register_builtin_operators
from pilot_assessment.evidence.registry import OperatorRegistry
from pilot_assessment.model_library.migration import load_hover_evidence_inventory
from pilot_assessment.model_library.profile import (
    ProfilePackageError,
    load_hover_starter_package,
    load_model_profile_directory,
)
from pilot_assessment.model_library.profile_data.generate_hover_starter import (
    render_hover_starter_resources,
)
from pilot_assessment.schemes.validation import (
    SchemeValidationDisposition,
    validate_executable_scheme,
)

NOW = datetime(2026, 7, 16, 19, 0, tzinfo=UTC)


def _registry() -> OperatorRegistry:
    registry = OperatorRegistry()
    register_builtin_operators(registry)
    return registry


def _count(profile, item_type: type[object]) -> int:
    return sum(isinstance(item, item_type) for item in profile.library_items)


def test_generator_is_deterministic_and_matches_packaged_resources() -> None:
    first = render_hover_starter_resources()
    second = render_hover_starter_resources()
    root = files("pilot_assessment.model_library.profile_data").joinpath("hover")

    assert first == second
    for filename, payload in first.items():
        assert root.joinpath(filename).read_bytes() == payload


def test_package_selects_exact_active_evidence_and_keeps_starter_counts_local() -> None:
    profile = load_hover_starter_package()
    scheme = profile.scheme

    assert profile.profile_id == "hover-starter-v0.1"
    assert _count(profile, BnNodeConcept) == 15
    assert _count(profile, BnNodeVersion) == 15
    assert _count(profile, EvidenceVersion) == 18
    assert _count(profile, EvidenceBindingVersion) == 18
    assert _count(profile, CptVersion) == 33
    assert len(scheme.bn_node_versions) == 15
    assert len(scheme.evidence_versions) == 18
    assert len(scheme.evidence_binding_versions) == 18
    assert len(scheme.cpt_versions) == 33
    assert len(scheme.output_node_ids) == 4

    selected_evidence_ids = {reference.version_id for reference in scheme.evidence_versions}
    assert "evidence-version.m5.O8.raw-task-v1" in selected_evidence_ids
    assert not any("starter.o8" in version_id for version_id in selected_evidence_ids)


def test_starter_package_is_technically_executable_and_compiles_33_variables() -> None:
    profile = load_hover_starter_package()
    repository = profile.to_repository(recorded_at=NOW)

    outcome = validate_executable_scheme(
        profile.scheme,
        repository,
        profile.source_catalog,
        _registry(),
    )
    plan = InferenceEngine(repository).compile(profile.scheme)

    assert outcome.disposition is SchemeValidationDisposition.EXECUTABLE
    assert not [diagnostic for diagnostic in outcome.diagnostics if diagnostic.blocking]
    assert len(plan.variables) == 33


def test_generic_directory_loader_rejects_manifest_checksum_drift(tmp_path: Path) -> None:
    source_root = Path(str(files("pilot_assessment.model_library.profile_data").joinpath("hover")))
    copied_root = tmp_path / "another-profile-directory"
    shutil.copytree(source_root, copied_root)
    cpt_resource = copied_root / "cpts.json"
    cpt_resource.write_bytes(cpt_resource.read_bytes() + b"\n")

    with pytest.raises(ProfilePackageError, match="checksum"):
        load_model_profile_directory(
            copied_root,
            external_items=load_hover_evidence_inventory().active_versions,
        )
