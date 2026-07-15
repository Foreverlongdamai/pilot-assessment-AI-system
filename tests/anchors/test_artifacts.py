from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from pathlib import Path

import polars as pl
import pytest
from pydantic import JsonValue

from pilot_assessment.anchors.artifacts import (
    ArtifactTransactionError,
    InMemoryDerivedArtifactSink,
    commit_anchor_artifacts,
)
from pilot_assessment.anchors.fingerprint import schema_descriptor_sha256
from pilot_assessment.anchors.protocols import (
    AnchorArtifactTransaction,
    ArtifactProducer,
    BlobArtifactPayload,
    EvaluationArtifactTransaction,
    PreprocessingProducer,
    ReadOnlyTabularPayload,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor_execution import AnchorArtifactRecipe

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _descriptor(*, unit: str = "ratio") -> dict[str, JsonValue]:
    return {
        "type": "table",
        "fields": [
            {"name": "t_ns", "dtype": "i64", "unit": "ns", "nullable": False},
            {"name": "value", "dtype": "f64", "unit": unit, "nullable": False},
        ],
        "canonical_order_keys": ["t_ns"],
    }


def _blob_descriptor() -> dict[str, JsonValue]:
    return {
        "type": "blob",
        "media_type": "application/octet-stream",
        "content_encoding": "identity",
    }


def _recipe(
    artifact_id: str = "mask-a",
    *,
    kind: str = "sample_mask",
    schema_id: str = "trace-v0.1",
) -> AnchorArtifactRecipe:
    return AnchorArtifactRecipe(
        artifact_id=artifact_id,
        kind=kind,
        schema_id=schema_id,
        schema_descriptor=_descriptor(),
        payload_kind="table",
    )


def _blob_recipe(artifact_id: str = "opaque-a") -> AnchorArtifactRecipe:
    return AnchorArtifactRecipe(
        artifact_id=artifact_id,
        kind="opaque_blob",
        schema_id="opaque-v0.1",
        schema_descriptor=_blob_descriptor(),
        payload_kind="blob",
    )


def _producer(anchor_id: str = "O1") -> ArtifactProducer:
    return ArtifactProducer(
        anchor_id=anchor_id,
        plugin_id=f"{anchor_id.lower()}-plugin",
        plugin_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_hash=SHA_B,
        dependency_fingerprints=(SHA_C,),
    )


def _table_payload(
    *,
    schema_id: str = "trace-v0.1",
    kind: str = "sample_mask",
    descriptor: dict[str, JsonValue] | None = None,
    order_keys: tuple[str, ...] = ("t_ns",),
    frame: pl.DataFrame | None = None,
) -> TabularArtifactPayload:
    return TabularArtifactPayload(
        schema_id=schema_id,
        schema_descriptor=descriptor or _descriptor(),
        frame=(
            frame
            if frame is not None
            else pl.DataFrame(
                {"t_ns": [0, 1], "value": [0.25, 0.75]},
                schema={"t_ns": pl.Int64, "value": pl.Float64},
            )
        ),
        order_keys=order_keys,
        artifact_kind=kind,
        grid_hash=SHA_D,
        start_t_ns=0,
        end_t_ns=2,
    )


def _blob_payload(payload_bytes: bytes = b"opaque-content") -> BlobArtifactPayload:
    return BlobArtifactPayload(
        schema_id="opaque-v0.1",
        payload_bytes=payload_bytes,
        artifact_kind="opaque_blob",
        start_t_ns=None,
        end_t_ns=None,
    )


def _preprocessing_producer(*, scope_id: str = "phase-1") -> PreprocessingProducer:
    descriptor = _descriptor()
    return PreprocessingProducer(
        recipe_id="trace-provider-v1",
        recipe_version="0.1.0",
        provider_id="trace-provider",
        provider_version="0.1.0",
        implementation_digest=SHA_A,
        parameter_schema_id="trace-provider-parameters-v0.1",
        parameter_schema_sha256=SHA_B,
        parameter_hash=SHA_C,
        output_schema_id="trace-v0.1",
        output_schema_sha256=schema_descriptor_sha256("trace-v0.1", descriptor),
        artifact_kind="sample_mask",
        output_payload_kind="table",
        scope_kind="phase",
        scope_id=scope_id,
        scope_start_t_ns=0,
        scope_end_t_ns=2,
        phase_id=scope_id,
        event_id=None,
        window_id=None,
        dependency_fingerprints=(SHA_D,),
    )


def _open_anchor(
    recipes: tuple[AnchorArtifactRecipe, ...] = (_recipe(),),
    *,
    key: str = "evaluation-1",
    producer: ArtifactProducer | None = None,
    sink: InMemoryDerivedArtifactSink | None = None,
) -> tuple[
    InMemoryDerivedArtifactSink,
    EvaluationArtifactTransaction,
    AnchorArtifactTransaction,
]:
    actual_sink = sink or InMemoryDerivedArtifactSink()
    evaluation = actual_sink.begin_evaluation(key)
    anchor = evaluation.begin_anchor(producer or _producer(), recipes)
    return actual_sink, evaluation, anchor


def test_emitter_is_staging_only_and_anchor_commit_enables_read_after_commit() -> None:
    _, evaluation, anchor = _open_anchor()
    emitter = anchor.emitter()
    public_callables = {
        name
        for name, member in inspect.getmembers(emitter, predicate=callable)
        if not name.startswith("_")
    }
    assert public_callables == {"stage_blob", "stage_table"}

    ref = emitter.stage_table("mask-a", _table_payload())
    with pytest.raises(ArtifactTransactionError, match="not committed"):
        evaluation.resolve(ref)

    assert commit_anchor_artifacts(anchor, (ref,)) == (ref,)
    resolved = evaluation.resolve(ref)
    assert isinstance(resolved.payload, ReadOnlyTabularPayload)
    exposed = resolved.payload.frame
    exposed.insert_column(2, pl.Series("mutated", [1, 2]))
    resolved_again = evaluation.resolve(ref)
    assert isinstance(resolved_again.payload, ReadOnlyTabularPayload)
    assert resolved_again.payload.frame.columns == ["t_ns", "value"]


def test_aborting_one_anchor_keeps_an_independent_committed_anchor() -> None:
    sink = InMemoryDerivedArtifactSink()
    evaluation = sink.begin_evaluation("evaluation-independent")
    first = evaluation.begin_anchor(_producer("O1"), (_recipe("first"),))
    first_ref = first.emitter().stage_table("first", _table_payload())
    first.commit()

    second = evaluation.begin_anchor(_producer("O2"), (_recipe("second"),))
    second_ref = second.emitter().stage_table("second", _table_payload())
    second.abort()

    assert evaluation.resolve(first_ref).ref == first_ref
    with pytest.raises(ArtifactTransactionError, match="not committed"):
        evaluation.resolve(second_ref)
    evaluation.commit()


def test_emitter_rejects_unknown_duplicate_and_declaration_order_violations() -> None:
    recipes = (_recipe("first"), _recipe("second"))
    _, _, anchor = _open_anchor(recipes)
    emitter = anchor.emitter()
    with pytest.raises(ArtifactTransactionError, match="unknown artifact"):
        emitter.stage_table("unknown", _table_payload())

    emitter.stage_table("first", _table_payload())
    with pytest.raises(ArtifactTransactionError, match="duplicate artifact"):
        emitter.stage_table("first", _table_payload())

    _, _, out_of_order = _open_anchor(recipes, key="evaluation-order")
    ordered_emitter = out_of_order.emitter()
    ordered_emitter.stage_table("second", _table_payload())
    with pytest.raises(ArtifactTransactionError, match="declaration order"):
        ordered_emitter.stage_table("first", _table_payload())


@pytest.mark.parametrize(
    "payload",
    [
        _table_payload(schema_id="other-v0.1"),
        _table_payload(kind="window_trace"),
        _table_payload(descriptor=_descriptor(unit="m")),
        _table_payload(order_keys=("value",)),
    ],
    ids=("schema", "kind", "descriptor", "order-keys"),
)
def test_table_staging_rejects_recipe_contract_mismatch(
    payload: TabularArtifactPayload,
) -> None:
    _, _, anchor = _open_anchor()
    with pytest.raises(ArtifactTransactionError, match="recipe"):
        anchor.emitter().stage_table("mask-a", payload)


def test_staging_rejects_payload_kind_physical_schema_and_noncanonical_rows() -> None:
    _, _, table_anchor = _open_anchor()
    with pytest.raises(ArtifactTransactionError, match="payload kind"):
        table_anchor.emitter().stage_blob("mask-a", _blob_payload())

    _, _, blob_anchor = _open_anchor((_blob_recipe(),), key="evaluation-blob-kind")
    with pytest.raises(ArtifactTransactionError, match="payload kind"):
        blob_anchor.emitter().stage_table("opaque-a", _table_payload())

    reversed_columns = pl.DataFrame(
        {"value": [0.25, 0.75], "t_ns": [0, 1]},
        schema={"value": pl.Float64, "t_ns": pl.Int64},
    )
    _, _, columns_anchor = _open_anchor(key="evaluation-columns")
    with pytest.raises(ArtifactTransactionError, match="physical schema"):
        columns_anchor.emitter().stage_table("mask-a", _table_payload(frame=reversed_columns))

    wrong_dtype = pl.DataFrame(
        {"t_ns": [0, 1], "value": [0.25, 0.75]},
        schema={"t_ns": pl.Int32, "value": pl.Float64},
    )
    _, _, dtype_anchor = _open_anchor(key="evaluation-dtype")
    with pytest.raises(ArtifactTransactionError, match="physical schema"):
        dtype_anchor.emitter().stage_table("mask-a", _table_payload(frame=wrong_dtype))

    noncanonical = pl.DataFrame(
        {"t_ns": [1, 0], "value": [0.75, 0.25]},
        schema={"t_ns": pl.Int64, "value": pl.Float64},
    )
    _, _, order_anchor = _open_anchor(key="evaluation-row-order")
    with pytest.raises(ArtifactTransactionError, match="canonical"):
        order_anchor.emitter().stage_table("mask-a", _table_payload(frame=noncanonical))


def test_two_declared_ids_with_one_schema_remain_separately_addressable() -> None:
    recipes = (_recipe("mask-a"), _recipe("mask-b"))
    _, evaluation, anchor = _open_anchor(recipes)
    first = anchor.emitter().stage_table("mask-a", _table_payload())
    second = anchor.emitter().stage_table("mask-b", _table_payload())
    commit_anchor_artifacts(anchor, (first, second))

    assert first.artifact_id != second.artifact_id
    assert first.logical_content_sha256 == second.logical_content_sha256
    assert evaluation.resolve(first).ref == first
    assert evaluation.resolve(second).ref == second


@pytest.mark.parametrize(
    "mode",
    ("unstaged", "unreturned", "reordered", "duplicate", "altered"),
)
def test_returned_refs_must_equal_the_staged_order_exactly(mode: str) -> None:
    recipes = (_recipe("first"), _recipe("second"))
    _, evaluation, anchor = _open_anchor(recipes, key=f"evaluation-return-{mode}")
    first = anchor.emitter().stage_table("first", _table_payload())
    second = anchor.emitter().stage_table("second", _table_payload())
    returned = {
        "unstaged": (first.model_copy(update={"artifact_id": "other"}), second),
        "unreturned": (first,),
        "reordered": (second, first),
        "duplicate": (first, first),
        "altered": (first.model_copy(update={"logical_content_sha256": SHA_A}), second),
    }[mode]

    with pytest.raises(ArtifactTransactionError, match="returned artifact"):
        commit_anchor_artifacts(anchor, returned)
    with pytest.raises(ArtifactTransactionError, match="not committed"):
        evaluation.resolve(first)


def test_table_identity_is_storage_independent_and_blob_hashes_raw_bytes(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "session-bundle"
    bundle.mkdir()
    manifest = bundle / "manifest.json"
    manifest.write_text('{"session_id":"session-1"}', encoding="utf-8")
    before = {path.name: path.read_bytes() for path in bundle.iterdir()}

    first_sink, first_evaluation, first_anchor = _open_anchor(key="storage-a")
    first_ref = first_anchor.emitter().stage_table("mask-a", _table_payload())
    first_anchor.commit()
    first_evaluation.commit()

    second_sink, second_evaluation, second_anchor = _open_anchor(key="storage-b")
    second_ref = second_anchor.emitter().stage_table("mask-a", _table_payload())
    second_anchor.commit()
    second_evaluation.commit()

    assert first_ref == second_ref
    assert first_ref.storage_file_sha256 is None
    assert not any("path" in name or "compression" in name for name in type(first_ref).model_fields)
    assert first_sink is not second_sink

    _, blob_evaluation, blob_anchor = _open_anchor((_blob_recipe(),), key="storage-blob")
    payload = _blob_payload()
    blob_ref = blob_anchor.emitter().stage_blob("opaque-a", payload)
    blob_anchor.commit()
    blob_evaluation.commit()
    expected = hashlib.sha256(payload.payload_bytes).hexdigest()
    assert blob_ref.logical_content_sha256 == expected
    assert blob_ref.storage_file_sha256 == expected
    assert {path.name: path.read_bytes() for path in bundle.iterdir()} == before


def test_preprocessing_staging_binds_scope_schema_and_immutable_content() -> None:
    sink = InMemoryDerivedArtifactSink()
    evaluation = sink.begin_evaluation("preprocessing")
    first = evaluation.stage_preprocessing(_preprocessing_producer(), _table_payload())
    second = evaluation.stage_preprocessing(
        _preprocessing_producer(scope_id="phase-2"), _table_payload()
    )

    assert first.identity.logical_content_sha256 == second.identity.logical_content_sha256
    assert first.identity != second.identity
    assert first.identity.scope_id == "phase-1"
    assert isinstance(first.payload, ReadOnlyTabularPayload)
    exposed = first.payload.frame
    exposed.insert_column(2, pl.Series("mutated", [1, 2]))
    assert first.payload.frame.columns == ["t_ns", "value"]

    wrong_schema = replace(_preprocessing_producer(), output_schema_id="other-v0.1")
    with pytest.raises(ArtifactTransactionError, match="preprocessing recipe"):
        evaluation.stage_preprocessing(wrong_schema, _table_payload())


def test_evaluation_abort_and_publish_failure_invalidate_all_resolution() -> None:
    _, evaluation, anchor = _open_anchor(key="explicit-abort")
    ref = anchor.emitter().stage_table("mask-a", _table_payload())
    anchor.commit()
    evaluation.abort()
    with pytest.raises(ArtifactTransactionError, match="aborted"):
        evaluation.resolve(ref)

    class FailingSink(InMemoryDerivedArtifactSink):
        def _publish(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated final publication failure")

    failing = FailingSink()
    _, failed_evaluation, failed_anchor = _open_anchor(key="failed-publish", sink=failing)
    failed_ref = failed_anchor.emitter().stage_table("mask-a", _table_payload())
    failed_anchor.commit()
    with pytest.raises(ArtifactTransactionError, match="publication failed"):
        failed_evaluation.commit()
    with pytest.raises(ArtifactTransactionError, match="aborted"):
        failed_evaluation.resolve(failed_ref)


def test_evaluation_commit_rejects_an_open_anchor_and_aborts_globally() -> None:
    _, evaluation, anchor = _open_anchor(key="open-child")
    ref = anchor.emitter().stage_table("mask-a", _table_payload())
    with pytest.raises(ArtifactTransactionError, match="open anchor"):
        evaluation.commit()
    with pytest.raises(ArtifactTransactionError, match="aborted"):
        evaluation.resolve(ref)
