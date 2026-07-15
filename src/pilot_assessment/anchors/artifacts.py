"""Transactional, evaluation-local publication of M4 derived artifacts.

The in-memory sink deliberately owns no filesystem path or durable-storage
policy.  It proves the M4 transaction and logical-identity boundary; M6 owns
managed persistence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Literal, NoReturn, cast

import polars as pl
from pydantic import JsonValue

from pilot_assessment.anchors.fingerprint import (
    logical_table_sha256,
    schema_descriptor_sha256,
    validate_logical_artifact_ref,
)
from pilot_assessment.anchors.protocols import (
    AnchorArtifactEmitter,
    AnchorArtifactTransaction,
    ArtifactProducer,
    BlobArtifactPayload,
    EvaluationArtifactTransaction,
    PreprocessingArtifactIdentity,
    PreprocessingProducer,
    ReadOnlyBlobPayload,
    ReadOnlyTabularPayload,
    ResolvedArtifactDependency,
    ResolvedPreprocessingDependency,
    TabularArtifactPayload,
)
from pilot_assessment.contracts.anchor_execution import AnchorArtifactRecipe
from pilot_assessment.contracts.anchor_v2 import AnchorArtifactRef

_TransactionState = Literal["open", "committed", "aborted"]
_POLARS_DTYPES: Mapping[str, type[pl.DataType]] = {
    "bool": pl.Boolean,
    "i8": pl.Int8,
    "i16": pl.Int16,
    "i32": pl.Int32,
    "i64": pl.Int64,
    "u8": pl.UInt8,
    "u16": pl.UInt16,
    "u32": pl.UInt32,
    "u64": pl.UInt64,
    "f32": pl.Float32,
    "f64": pl.Float64,
    "utf8": pl.String,
}


class ArtifactTransactionError(ValueError):
    """Stable failure at the derived-artifact transaction boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> NoReturn:
    raise ArtifactTransactionError(code, message)


def _descriptor_order_keys(descriptor: Mapping[str, JsonValue]) -> tuple[str, ...]:
    raw_keys = descriptor.get("canonical_order_keys")
    if not isinstance(raw_keys, (list, tuple)) or any(type(key) is not str for key in raw_keys):
        _fail("artifact_recipe_mismatch", "artifact recipe has invalid canonical order keys")
    return tuple(cast(Sequence[str], raw_keys))


def _validate_physical_table(payload: TabularArtifactPayload) -> None:
    raw_fields = payload.schema_descriptor.get("fields")
    if not isinstance(raw_fields, (list, tuple)):
        _fail("artifact_physical_schema_mismatch", "table physical schema has no field list")

    expected_names: list[str] = []
    expected_dtypes: list[type[pl.DataType]] = []
    for raw_field in cast(Sequence[object], raw_fields):
        if not isinstance(raw_field, Mapping):
            _fail("artifact_physical_schema_mismatch", "table physical schema field is invalid")
        field = cast(Mapping[str, object], raw_field)
        name = field.get("name")
        dtype_id = field.get("dtype")
        if type(name) is not str or type(dtype_id) is not str:
            _fail("artifact_physical_schema_mismatch", "table physical schema field is invalid")
        expected_dtype = _POLARS_DTYPES.get(dtype_id)
        if expected_dtype is None:
            _fail("artifact_physical_schema_mismatch", "table physical schema dtype is invalid")
        expected_names.append(name)
        expected_dtypes.append(expected_dtype)

    if payload.frame.columns != expected_names:
        _fail(
            "artifact_physical_schema_mismatch",
            "table physical schema columns must match the declared order",
        )
    if any(
        payload.frame.schema[name] != dtype
        for name, dtype in zip(expected_names, expected_dtypes, strict=True)
    ):
        _fail(
            "artifact_physical_schema_mismatch",
            "table physical schema dtypes must match the descriptor",
        )


def _read_only_table(payload: TabularArtifactPayload) -> ReadOnlyTabularPayload:
    _validate_physical_table(payload)
    try:
        logical_hash = logical_table_sha256(
            payload.schema_id,
            payload.schema_descriptor,
            payload.frame.to_dicts(),
            payload.order_keys,
        )
    except (TypeError, ValueError) as error:
        raise ArtifactTransactionError(
            "artifact_noncanonical_table",
            "table content is not canonical under its declared logical schema",
        ) from error
    return ReadOnlyTabularPayload(
        schema_id=payload.schema_id,
        schema_descriptor=payload.schema_descriptor,
        frame=payload.frame,
        order_keys=payload.order_keys,
        artifact_kind=payload.artifact_kind,
        grid_hash=payload.grid_hash,
        start_t_ns=payload.start_t_ns,
        end_t_ns=payload.end_t_ns,
        logical_content_sha256=logical_hash,
    )


def _read_only_blob(payload: BlobArtifactPayload) -> ReadOnlyBlobPayload:
    logical_hash = hashlib.sha256(payload.payload_bytes).hexdigest()
    return ReadOnlyBlobPayload(
        schema_id=payload.schema_id,
        payload_bytes=payload.payload_bytes,
        artifact_kind=payload.artifact_kind,
        start_t_ns=payload.start_t_ns,
        end_t_ns=payload.end_t_ns,
        logical_content_sha256=logical_hash,
    )


class _AnchorEmitter:
    """Least-capability view passed to one plugin invocation."""

    __slots__ = ("_transaction",)

    def __init__(self, transaction: _AnchorTransaction) -> None:
        self._transaction = transaction

    def stage_table(self, artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef:
        return self._transaction._stage_table(artifact_id, payload)

    def stage_blob(self, artifact_id: str, payload: BlobArtifactPayload) -> AnchorArtifactRef:
        return self._transaction._stage_blob(artifact_id, payload)


class _AnchorTransaction:
    __slots__ = (
        "_emitter_view",
        "_parent",
        "_producer",
        "_recipe_by_id",
        "_recipe_index",
        "_recipes",
        "_resolved",
        "_staged_ids",
        "_state",
    )

    def __init__(
        self,
        parent: _EvaluationTransaction,
        producer: ArtifactProducer,
        recipes: tuple[AnchorArtifactRecipe, ...],
    ) -> None:
        recipe_ids = tuple(recipe.artifact_id for recipe in recipes)
        if len(recipe_ids) != len(set(recipe_ids)):
            _fail("artifact_recipe_duplicate", "artifact recipes contain duplicate IDs")
        self._parent = parent
        self._producer = producer
        self._recipes = recipes
        self._recipe_by_id = {recipe.artifact_id: recipe for recipe in recipes}
        self._recipe_index = {recipe.artifact_id: index for index, recipe in enumerate(recipes)}
        self._staged_ids: set[str] = set()
        self._resolved: list[ResolvedArtifactDependency] = []
        self._state: _TransactionState = "open"
        self._emitter_view = _AnchorEmitter(self)

    def _require_open(self) -> None:
        self._parent._require_open()
        if self._state != "open":
            _fail(
                "artifact_transaction_not_open",
                f"anchor artifact transaction is {self._state}, not open",
            )

    def emitter(self) -> AnchorArtifactEmitter:
        self._require_open()
        return self._emitter_view

    def staged_refs(self) -> tuple[AnchorArtifactRef, ...]:
        if self._state == "aborted" or self._parent._state == "aborted":
            _fail("artifact_transaction_aborted", "anchor artifact transaction was aborted")
        return tuple(item.ref for item in self._resolved)

    def _recipe_for(
        self, artifact_id: str, payload_kind: Literal["table", "blob"]
    ) -> AnchorArtifactRecipe:
        self._require_open()
        recipe = self._recipe_by_id.get(artifact_id)
        if recipe is None:
            _fail("artifact_unknown", f"unknown artifact ID: {artifact_id}")
        if artifact_id in self._staged_ids:
            _fail("artifact_duplicate", f"duplicate artifact ID: {artifact_id}")
        if (
            self._resolved
            and self._recipe_index[artifact_id]
            <= self._recipe_index[self._resolved[-1].ref.artifact_id]
        ):
            _fail(
                "artifact_declaration_order",
                "artifact staging violates declaration order",
            )
        if recipe.payload_kind != payload_kind:
            _fail(
                "artifact_payload_kind_mismatch",
                "artifact payload kind does not match its recipe",
            )
        return recipe

    def _validate_common_recipe(
        self,
        recipe: AnchorArtifactRecipe,
        *,
        schema_id: str,
        artifact_kind: str,
    ) -> None:
        if recipe.schema_id != schema_id or recipe.kind != artifact_kind:
            _fail(
                "artifact_recipe_mismatch",
                "artifact schema or kind does not match its recipe",
            )

    def _append(
        self,
        recipe: AnchorArtifactRecipe,
        payload: ReadOnlyTabularPayload | ReadOnlyBlobPayload,
    ) -> AnchorArtifactRef:
        is_table = isinstance(payload, ReadOnlyTabularPayload)
        ref = AnchorArtifactRef(
            artifact_id=recipe.artifact_id,
            kind=recipe.kind,
            schema_id=recipe.schema_id,
            logical_content_sha256=payload.logical_content_sha256,
            storage_file_sha256=None if is_table else payload.logical_content_sha256,
            row_count=payload.frame.height if is_table else 0,
            start_t_ns=payload.start_t_ns,
            end_t_ns=payload.end_t_ns,
            grid_hash=payload.grid_hash if is_table else None,
            producer_anchor_id=self._producer.anchor_id,
            producer_plugin_id=self._producer.plugin_id,
            producer_plugin_version=self._producer.plugin_version,
            parameter_hash=self._producer.parameter_hash,
            dependency_fingerprints=self._producer.dependency_fingerprints,
        )
        resolved = ResolvedArtifactDependency(ref=ref, payload=payload)
        validate_logical_artifact_ref(ref, resolved)
        self._resolved.append(resolved)
        self._staged_ids.add(recipe.artifact_id)
        return ref

    def _stage_table(self, artifact_id: str, payload: TabularArtifactPayload) -> AnchorArtifactRef:
        if not isinstance(payload, TabularArtifactPayload):
            _fail("artifact_payload_kind_mismatch", "table staging requires a table payload")
        recipe = self._recipe_for(artifact_id, "table")
        self._validate_common_recipe(
            recipe,
            schema_id=payload.schema_id,
            artifact_kind=payload.artifact_kind,
        )
        try:
            recipe_descriptor_hash = schema_descriptor_sha256(
                recipe.schema_id, recipe.schema_descriptor
            )
            payload_descriptor_hash = schema_descriptor_sha256(
                payload.schema_id, payload.schema_descriptor
            )
        except (TypeError, ValueError) as error:
            raise ArtifactTransactionError(
                "artifact_recipe_mismatch",
                "artifact table descriptor does not satisfy its recipe",
            ) from error
        if (
            payload_descriptor_hash != recipe_descriptor_hash
            or payload.order_keys != _descriptor_order_keys(recipe.schema_descriptor)
        ):
            _fail(
                "artifact_recipe_mismatch",
                "artifact table descriptor or order keys do not match its recipe",
            )
        return self._append(recipe, _read_only_table(payload))

    def _stage_blob(self, artifact_id: str, payload: BlobArtifactPayload) -> AnchorArtifactRef:
        if not isinstance(payload, BlobArtifactPayload):
            _fail("artifact_payload_kind_mismatch", "blob staging requires a blob payload")
        recipe = self._recipe_for(artifact_id, "blob")
        self._validate_common_recipe(
            recipe,
            schema_id=payload.schema_id,
            artifact_kind=payload.artifact_kind,
        )
        return self._append(recipe, _read_only_blob(payload))

    def commit(self) -> tuple[AnchorArtifactRef, ...]:
        self._require_open()
        for resolved in self._resolved:
            validate_logical_artifact_ref(resolved.ref, resolved)
        self._parent._commit_anchor(self)
        self._state = "committed"
        return tuple(item.ref for item in self._resolved)

    def abort(self) -> None:
        if self._state == "committed":
            _fail("artifact_transaction_committed", "committed anchor transaction cannot abort")
        if self._state == "aborted":
            return
        self._resolved.clear()
        self._staged_ids.clear()
        self._state = "aborted"

    def _force_abort(self) -> None:
        self._resolved.clear()
        self._staged_ids.clear()
        self._state = "aborted"


class _EvaluationTransaction:
    __slots__ = (
        "_anchors",
        "_committed_artifacts",
        "_evaluation_key",
        "_preprocessing",
        "_sink",
        "_state",
    )

    def __init__(self, sink: InMemoryDerivedArtifactSink, evaluation_key: str) -> None:
        self._sink = sink
        self._evaluation_key = evaluation_key
        self._anchors: dict[str, _AnchorTransaction] = {}
        self._committed_artifacts: dict[tuple[str, str], ResolvedArtifactDependency] = {}
        self._preprocessing: list[ResolvedPreprocessingDependency] = []
        self._state: _TransactionState = "open"

    def _require_open(self) -> None:
        if self._state != "open":
            _fail(
                "artifact_evaluation_not_open",
                f"evaluation artifact transaction is {self._state}, not open",
            )

    def begin_anchor(
        self,
        producer: ArtifactProducer,
        artifact_recipes: tuple[AnchorArtifactRecipe, ...],
    ) -> AnchorArtifactTransaction:
        self._require_open()
        if not isinstance(producer, ArtifactProducer):
            raise TypeError("producer must be an ArtifactProducer")
        if not isinstance(artifact_recipes, tuple) or any(
            not isinstance(recipe, AnchorArtifactRecipe) for recipe in artifact_recipes
        ):
            raise TypeError("artifact_recipes must be a typed tuple")
        if producer.anchor_id in self._anchors:
            _fail(
                "artifact_anchor_duplicate",
                f"anchor transaction already exists for {producer.anchor_id}",
            )
        transaction = _AnchorTransaction(self, producer, artifact_recipes)
        self._anchors[producer.anchor_id] = transaction
        return transaction

    def _commit_anchor(self, transaction: _AnchorTransaction) -> None:
        self._require_open()
        for resolved in transaction._resolved:
            key = (resolved.ref.producer_anchor_id, resolved.ref.artifact_id)
            if key in self._committed_artifacts:
                _fail("artifact_duplicate", "committed artifact identity is duplicated")
            self._committed_artifacts[key] = resolved

    def resolve(self, ref: AnchorArtifactRef) -> ResolvedArtifactDependency:
        if self._state == "aborted":
            _fail("artifact_evaluation_aborted", "evaluation artifact transaction was aborted")
        if not isinstance(ref, AnchorArtifactRef):
            raise TypeError("ref must be an AnchorArtifactRef")
        key = (ref.producer_anchor_id, ref.artifact_id)
        resolved = self._committed_artifacts.get(key)
        if resolved is None or resolved.ref != ref:
            _fail("artifact_not_committed", "artifact is not committed in this evaluation")
        validate_logical_artifact_ref(ref, resolved)
        return resolved

    def stage_preprocessing(
        self,
        producer: PreprocessingProducer,
        payload: TabularArtifactPayload | BlobArtifactPayload,
    ) -> ResolvedPreprocessingDependency:
        self._require_open()
        if not isinstance(producer, PreprocessingProducer):
            raise TypeError("producer must be a PreprocessingProducer")
        payload_kind: Literal["table", "blob"]
        read_only: ReadOnlyTabularPayload | ReadOnlyBlobPayload
        if isinstance(payload, TabularArtifactPayload):
            payload_kind = "table"
            read_only = _read_only_table(payload)
            try:
                descriptor_hash = schema_descriptor_sha256(
                    payload.schema_id, payload.schema_descriptor
                )
            except (TypeError, ValueError) as error:
                raise ArtifactTransactionError(
                    "preprocessing_recipe_mismatch",
                    "preprocessing recipe has an invalid table descriptor",
                ) from error
            if descriptor_hash != producer.output_schema_sha256:
                _fail(
                    "preprocessing_recipe_mismatch",
                    "preprocessing recipe schema descriptor does not match the payload",
                )
        elif isinstance(payload, BlobArtifactPayload):
            payload_kind = "blob"
            read_only = _read_only_blob(payload)
        else:
            raise TypeError("preprocessing payload must be a table or blob payload")
        if (
            producer.output_payload_kind != payload_kind
            or producer.output_schema_id != payload.schema_id
            or producer.artifact_kind != payload.artifact_kind
        ):
            _fail(
                "preprocessing_recipe_mismatch",
                "preprocessing recipe kind or schema does not match the payload",
            )
        identity = PreprocessingArtifactIdentity(
            recipe_id=producer.recipe_id,
            recipe_version=producer.recipe_version,
            provider_id=producer.provider_id,
            provider_version=producer.provider_version,
            implementation_digest=producer.implementation_digest,
            parameter_schema_id=producer.parameter_schema_id,
            parameter_schema_sha256=producer.parameter_schema_sha256,
            parameter_hash=producer.parameter_hash,
            scope_kind=producer.scope_kind,
            scope_id=producer.scope_id,
            scope_start_t_ns=producer.scope_start_t_ns,
            scope_end_t_ns=producer.scope_end_t_ns,
            phase_id=producer.phase_id,
            event_id=producer.event_id,
            window_id=producer.window_id,
            schema_id=producer.output_schema_id,
            schema_sha256=producer.output_schema_sha256,
            artifact_kind=producer.artifact_kind,
            payload_kind=producer.output_payload_kind,
            logical_content_sha256=read_only.logical_content_sha256,
            input_fingerprints=producer.input_fingerprints,
            dependency_fingerprints=producer.dependency_fingerprints,
        )
        resolved = ResolvedPreprocessingDependency(identity=identity, payload=read_only)
        self._preprocessing.append(resolved)
        return resolved

    def commit(self) -> None:
        self._require_open()
        if any(anchor._state == "open" for anchor in self._anchors.values()):
            self._abort_internal()
            _fail(
                "artifact_open_anchor",
                "evaluation commit cannot proceed with an open anchor transaction",
            )
        try:
            self._sink._publish(
                self._evaluation_key,
                dict(self._committed_artifacts),
                tuple(self._preprocessing),
            )
        except Exception as error:
            self._abort_internal()
            raise ArtifactTransactionError(
                "artifact_publication_failed",
                "evaluation artifact publication failed atomically",
            ) from error
        self._state = "committed"

    def abort(self) -> None:
        if self._state == "aborted":
            return
        if self._state == "committed":
            _fail(
                "artifact_evaluation_committed",
                "committed evaluation artifact transaction cannot abort",
            )
        self._abort_internal()

    def _abort_internal(self) -> None:
        for anchor in self._anchors.values():
            anchor._force_abort()
        self._committed_artifacts.clear()
        self._preprocessing.clear()
        self._state = "aborted"
        self._sink._discard(self._evaluation_key)


class InMemoryDerivedArtifactSink:
    """Evaluation-local test/smoke implementation of ``DerivedArtifactSink``."""

    def __init__(self) -> None:
        self._used_keys: set[str] = set()
        self._active: dict[str, _EvaluationTransaction] = {}
        self._published_artifacts: dict[str, dict[tuple[str, str], ResolvedArtifactDependency]] = {}
        self._published_preprocessing: dict[str, tuple[ResolvedPreprocessingDependency, ...]] = {}

    def begin_evaluation(self, evaluation_key: str) -> EvaluationArtifactTransaction:
        if (
            type(evaluation_key) is not str
            or not evaluation_key
            or evaluation_key.strip() != evaluation_key
        ):
            raise ValueError("evaluation_key must be a non-empty canonical string")
        if evaluation_key in self._used_keys:
            _fail("artifact_evaluation_duplicate", "evaluation key has already been used")
        self._used_keys.add(evaluation_key)
        transaction = _EvaluationTransaction(self, evaluation_key)
        self._active[evaluation_key] = transaction
        return transaction

    def _publish(
        self,
        evaluation_key: str,
        artifacts: dict[tuple[str, str], ResolvedArtifactDependency],
        preprocessing: tuple[ResolvedPreprocessingDependency, ...],
    ) -> None:
        if evaluation_key not in self._active:
            _fail("artifact_evaluation_unknown", "evaluation transaction is not active")
        self._published_artifacts[evaluation_key] = dict(artifacts)
        self._published_preprocessing[evaluation_key] = tuple(preprocessing)
        del self._active[evaluation_key]

    def _discard(self, evaluation_key: str) -> None:
        self._active.pop(evaluation_key, None)
        self._published_artifacts.pop(evaluation_key, None)
        self._published_preprocessing.pop(evaluation_key, None)


def commit_anchor_artifacts(
    transaction: AnchorArtifactTransaction,
    returned_refs: tuple[AnchorArtifactRef, ...],
) -> tuple[AnchorArtifactRef, ...]:
    """Commit only when plugin-returned refs equal staged refs byte-for-byte and in order."""

    if not isinstance(returned_refs, tuple) or any(
        not isinstance(ref, AnchorArtifactRef) for ref in returned_refs
    ):
        transaction.abort()
        _fail(
            "artifact_return_mismatch",
            "returned artifact references must be a typed ordered tuple",
        )
    staged = transaction.staged_refs()
    if returned_refs != staged:
        transaction.abort()
        _fail(
            "artifact_return_mismatch",
            "returned artifact references do not exactly equal staged artifacts",
        )
    return transaction.commit()


__all__ = [
    "ArtifactTransactionError",
    "InMemoryDerivedArtifactSink",
    "commit_anchor_artifacts",
]
