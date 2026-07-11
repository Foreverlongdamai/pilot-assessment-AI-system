"""Generate committed JSON Schemas from the authoritative Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from pilot_assessment.contracts.anchor import SUPPORTED_SOFT_TIE_POLICIES, AnchorResult
from pilot_assessment.contracts.common import (
    BUNDLE_RELATIVE_PATH_JSON_SCHEMA_PATTERN,
    BUNDLE_RELATIVE_PATH_PATTERN,
)
from pilot_assessment.contracts.session import CORE_MODALITIES, SessionManifest

CONTRACT_VERSION = "0.1.0"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SESSION_MANIFEST_SCHEMA_ID = "urn:cranfield:pilot-assessment:schema:session-manifest:0.1.0"
SESSION_MANIFEST_SCHEMA_TITLE = "Pilot Assessment Session Manifest 0.1.0"
ANCHOR_RESULT_SCHEMA_ID = "urn:cranfield:pilot-assessment:schema:anchor-result:0.1.0"
ANCHOR_RESULT_SCHEMA_TITLE = "Pilot Assessment Anchor Result 0.1.0"

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIRECTORY = _PROJECT_ROOT / "schemas"


def _replace_runtime_only_path_patterns(value: object) -> None:
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        if mapping.get("pattern") == BUNDLE_RELATIVE_PATH_PATTERN:
            mapping["pattern"] = BUNDLE_RELATIVE_PATH_JSON_SCHEMA_PATTERN
        for child in mapping.values():
            _replace_runtime_only_path_patterns(child)
    elif isinstance(value, list):
        for child in value:
            _replace_runtime_only_path_patterns(child)


def _base_schema(
    model: type[BaseModel],
    *,
    schema_id: str,
    title: str,
    runtime_invariants: list[str],
) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    _replace_runtime_only_path_patterns(schema)
    schema["$schema"] = SCHEMA_DIALECT
    schema["$id"] = schema_id
    schema["title"] = title
    schema["x-contract-version"] = CONTRACT_VERSION
    schema["x-runtime-invariants"] = runtime_invariants
    return schema


def _session_manifest_schema() -> dict[str, Any]:
    schema = _base_schema(
        SessionManifest,
        schema_id=SESSION_MANIFEST_SCHEMA_ID,
        title=SESSION_MANIFEST_SCHEMA_TITLE,
        runtime_invariants=[
            "stream map key must equal descriptor.modality",
            "present stream checksum keys must exactly match paths",
            "declared paths are unique under Windows case folding",
            "bundle_schema_version major must be supported by the reader",
        ],
    )
    stream_inventory = schema["properties"]["streams"]
    stream_inventory["allOf"] = [
        {"required": sorted(CORE_MODALITIES)},
        {"not": {"required": ["P"]}},
    ]
    stream_inventory["x-core-modalities"] = sorted(CORE_MODALITIES)
    stream_inventory["x-optional-stream-policy"] = (
        "same-major optional stable stream IDs are preserved"
    )

    descriptor = schema["$defs"]["StreamDescriptor"]
    descriptor["allOf"] = [
        {
            "if": {
                "properties": {"status": {"const": "present"}},
                "required": ["status"],
            },
            "then": {
                "properties": {
                    "paths": {"minItems": 1},
                    "clock_sync": {"not": {"type": "null"}},
                }
            },
        },
        {
            "if": {
                "properties": {"status": {"const": "invalid"}},
                "required": ["status"],
            },
            "then": {
                "properties": {
                    "paths": {"minItems": 1},
                }
            },
        },
        *[
            {
                "if": {
                    "properties": {"status": {"const": status}},
                    "required": ["status"],
                },
                "then": {
                    "properties": {
                        "paths": {"maxItems": 0},
                        "checksums": {"maxProperties": 0},
                        "quality_summary": {"type": "null"},
                    }
                },
            }
            for status in ("export_pending", "missing", "not_applicable")
        ],
        *[
            {
                "if": {
                    "properties": {"status": {"const": status}},
                    "required": ["status"],
                },
                "then": {"properties": {"clock_sync": {"type": "null"}}},
            }
            for status in ("missing", "not_applicable")
        ],
        {
            "if": {
                "properties": {"status": {"const": "not_applicable"}},
                "required": ["status"],
            },
            "then": {"properties": {"required_for_import": {"const": False}}},
        },
    ]

    task_reference = schema["$defs"]["TaskReference"]
    task_reference["allOf"] = [
        {
            "if": {
                "properties": {"source": {"const": "bundle"}},
                "required": ["source"],
            },
            "then": {
                "required": ["stream_id"],
                "properties": {
                    "stream_id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 128,
                        "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
                    }
                },
            },
            "else": {"properties": {"stream_id": {"type": "null"}}},
        }
    ]
    privacy = schema["$defs"]["PrivacyDefinition"]
    privacy["properties"]["biometric_modalities_export_pending"]["uniqueItems"] = True
    return schema


def _anchor_result_schema() -> dict[str, Any]:
    schema = _base_schema(
        AnchorResult,
        schema_id=ANCHOR_RESULT_SCHEMA_ID,
        title=ANCHOR_RESULT_SCHEMA_TITLE,
        runtime_invariants=[
            "likelihood values sum to one within absolute tolerance 1e-9",
            "computed continuous_score equals ordinal_expectation_v1",
            "hard_threshold_v1 likelihood is one-hot and matches evidence_state",
            "soft likelihood ties declare an explicit tie_policy",
            "non-computed results omit all evidence observation fields",
            "binary_quality_v1 computed results have passed=true and score=1",
        ],
    )
    schema["allOf"] = [
        {
            "if": {
                "properties": {"calculation_status": {"const": "computed"}},
                "required": ["calculation_status"],
            },
            "then": {
                "properties": {
                    "evidence_state": {"$ref": "#/$defs/EvidenceState"},
                    "continuous_score": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "evidence_likelihood": {"$ref": "#/$defs/EvidenceLikelihood"},
                }
            },
            "else": {
                "properties": {
                    "evidence_state": {"type": "null"},
                    "continuous_score": {"type": "null"},
                    "evidence_likelihood": {"type": "null"},
                }
            },
        }
    ]
    schema["x-soft-tie-policies"] = sorted(SUPPORTED_SOFT_TIE_POLICIES)

    artifact = schema["$defs"]["DerivedArtifact"]
    artifact["allOf"] = [
        {
            "if": {
                "properties": {"kind": {"const": "window_metric_trace"}},
                "required": ["kind"],
            },
            "then": {
                "required": [
                    "window_grid_id",
                    "window_length_s",
                    "step_s",
                    "alignment",
                    "min_valid_fraction",
                    "partial_window_policy",
                ],
                "properties": {
                    "window_grid_id": {"type": "string"},
                    "window_length_s": {"type": "number", "exclusiveMinimum": 0.0},
                    "step_s": {"type": "number", "exclusiveMinimum": 0.0},
                    "alignment": {"type": "string"},
                    "min_valid_fraction": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                    "partial_window_policy": {"type": "string"},
                },
            },
        }
    ]
    return schema


def _render_json(schema: dict[str, Any]) -> bytes:
    return (json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_schemas() -> dict[str, bytes]:
    """Return canonical schema bytes keyed by their committed filenames."""

    return {
        "anchor-result-0.1.0.schema.json": _render_json(_anchor_result_schema()),
        "session-manifest-0.1.0.schema.json": _render_json(_session_manifest_schema()),
    }


def export_schemas(output_directory: str | Path = _DEFAULT_OUTPUT_DIRECTORY) -> tuple[Path, ...]:
    """Write all schemas atomically enough for deterministic development export."""

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, payload in render_schemas().items():
        destination = output / name
        temporary = output / f".{name}.tmp"
        temporary.write_bytes(payload)
        temporary.replace(destination)
        written.append(destination)
    return tuple(written)


def main() -> None:
    for path in export_schemas():
        print(path)


if __name__ == "__main__":
    main()


__all__ = [
    "ANCHOR_RESULT_SCHEMA_ID",
    "ANCHOR_RESULT_SCHEMA_TITLE",
    "CONTRACT_VERSION",
    "SCHEMA_DIALECT",
    "SESSION_MANIFEST_SCHEMA_ID",
    "SESSION_MANIFEST_SCHEMA_TITLE",
    "export_schemas",
    "render_schemas",
]
