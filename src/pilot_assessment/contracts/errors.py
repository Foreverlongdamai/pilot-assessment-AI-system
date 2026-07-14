"""Shared structured error data used across core and runtime boundaries."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, JsonValue, StrictBool, field_validator

from pilot_assessment.contracts.common import (
    StableId,
    StrictContractModel,
    freeze_json_mapping,
)

NonEmptyMessage = Annotated[str, Field(min_length=1, max_length=4096)]


class ErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class DomainErrorData(StrictContractModel):
    error_code: StableId
    severity: ErrorSeverity
    recoverable: StrictBool
    message: NonEmptyMessage
    field_or_path: NonEmptyMessage | None = None
    node_or_anchor_id: StableId | None = None
    remediation: NonEmptyMessage
    request_id: StableId | None = None
    trace_id: StableId | None = None
    transaction_id: StableId | None = None
    diagnostics: dict[str, JsonValue] = Field(default_factory=dict)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("diagnostics", "extensions")
    @classmethod
    def freeze_json_maps(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        return freeze_json_mapping(value)


__all__ = ["DomainErrorData", "ErrorSeverity"]
