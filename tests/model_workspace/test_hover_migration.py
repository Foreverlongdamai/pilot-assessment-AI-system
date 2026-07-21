from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.model_workspace import (
    EvidenceNodeDefinition,
    ModelNodeKind,
    ModelTechnicalStatus,
    RawInputFamily,
    RawInputNodeDefinition,
    RawResourceRole,
)
from pilot_assessment.model_library.profile import load_hover_starter_package
from pilot_assessment.model_library.repository import component_kind, component_record_id
from pilot_assessment.runtime import SystemApplication
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 17, 15, 0, tzinfo=UTC)


def _raw_by_source(application: SystemApplication) -> dict[str, RawInputNodeDefinition]:
    result: dict[str, RawInputNodeDefinition] = {}
    for node in application.current_model.list_nodes():
        if isinstance(node.definition, RawInputNodeDefinition):
            result[node.definition.source_descriptor.source_id] = node.definition
    return result


def test_hover_starter_materializes_complete_current_nodes_once_and_reopens(
    tmp_path: Path,
) -> None:
    profile = load_hover_starter_package()
    legacy_before = tuple(
        (component_kind(item), component_record_id(item), item.model_dump(mode="json"))
        for item in profile.library_items
    )
    root = tmp_path / "system"

    application = open_test_system(root, clock=lambda: NOW)
    try:
        seed = application.current_seed_result
        nodes = application.current_model.list_nodes()
        schemes = application.current_model.list_schemes()
        counts = Counter(node.node_kind for node in nodes)

        assert seed.applied is True
        assert seed.inserted_nodes == 53
        assert seed.inserted_schemes == 1
        assert seed.mapping_count == len(profile.library_items) == 141
        assert counts == {
            ModelNodeKind.RAW_INPUT: 20,
            ModelNodeKind.EVIDENCE: 18,
            ModelNodeKind.BN: 15,
        }
        assert len(schemes) == 1
        assert schemes[0].scheme_id == seed.scheme_id == application.current_starter_scheme_id
        assert len(schemes[0].explicit_active_node_ids) == 37
        assert len(schemes[0].computed_active_closure) == 52
        assert len(schemes[0].output_node_ids) == 4
        assert schemes[0].technical_status is ModelTechnicalStatus.EXECUTABLE

        raw = _raw_by_source(application)
        assert raw["X.state-vector"].family is RawInputFamily.X
        assert raw["U.channels"].family is RawInputFamily.U
        assert raw["I.frames"].family is RawInputFamily.I
        assert raw["G.frames"].family is RawInputFamily.G
        assert raw["EEG.channels"].family is RawInputFamily.P
        assert raw["ECG.channels"].family is RawInputFamily.P
        assert raw["pilot_camera.frames"].family is RawInputFamily.PILOT_CAMERA
        assert raw["pilot_camera.frames"].resource_role is RawResourceRole.STREAM
        assert raw["task-reference.commanded-path"].family is None
        assert raw["task-reference.commanded-path"].resource_role is RawResourceRole.TASK_REFERENCE
        assert raw["semantic.disturbances"].family is None
        assert raw["semantic.disturbances"].resource_role is RawResourceRole.EVENT
        assert raw["derived.flight-error"].family is None
        assert raw["derived.flight-error"].resource_role is RawResourceRole.DERIVED_RESOURCE

        rows = application.store.database.fetchall(
            """
            SELECT legacy_kind, legacy_record_id, current_object_kind,
                   current_object_id, seed_hash
            FROM model_starter_mappings WHERE seed_id = ?
            ORDER BY legacy_kind, legacy_record_id, current_object_kind, current_object_id
            """,
            (seed.seed_id,),
        )
        assert len(rows) == len(profile.library_items)
        assert {(row["legacy_kind"], row["legacy_record_id"]) for row in rows} == {
            (component_kind(item).value, component_record_id(item))
            for item in profile.library_items
        }
        # Complete nodes intentionally combine several legacy records.
        target_counts = Counter(
            (row["current_object_kind"], row["current_object_id"]) for row in rows
        )
        assert max(target_counts.values()) >= 4
        assert {row["seed_hash"] for row in rows} == {seed.seed_hash}

        node_snapshots = {node.node_id: node for node in nodes}
        scheme_snapshot = schemes[0]
    finally:
        application.close()

    reopened = open_test_system(root, clock=lambda: NOW)
    try:
        assert reopened.current_seed_result.applied is False
        assert reopened.current_seed_result.mapping_count == len(profile.library_items)
        assert {
            node.node_id: node for node in reopened.current_model.list_nodes()
        } == node_snapshots
        assert reopened.current_model.get_scheme(scheme_snapshot.scheme_id) == scheme_snapshot
        assert (
            tuple(
                (component_kind(item), component_record_id(item), item.model_dump(mode="json"))
                for item in load_hover_starter_package().library_items
            )
            == legacy_before
        )
    finally:
        reopened.close()


def test_every_evidence_binding_resolves_to_raw_nodes_and_exact_recipe_sources(
    tmp_path: Path,
) -> None:
    application = open_test_system(tmp_path / "system", clock=lambda: NOW)
    try:
        nodes = {node.node_id: node for node in application.current_model.list_nodes()}
        for node in nodes.values():
            if node.node_kind is not ModelNodeKind.EVIDENCE:
                continue
            definition = node.definition
            assert isinstance(definition, EvidenceNodeDefinition)
            recipe_sources = {item.binding_id: item.source_id for item in definition.recipe.inputs}
            for binding in definition.data_bindings:
                raw = nodes[binding.raw_input_node.node_id].definition
                assert isinstance(raw, RawInputNodeDefinition)
                assert (
                    raw.source_descriptor.source_id
                    == recipe_sources[binding.recipe_input_binding_id]
                )
    finally:
        application.close()
