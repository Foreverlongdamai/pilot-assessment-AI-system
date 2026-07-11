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
from pilot_assessment.contracts.ingestion import IngestionReadinessReport
from pilot_assessment.contracts.session import (
    BIOMETRIC_MODALITIES,
    CORE_MODALITIES,
    SessionManifest,
)

CONTRACT_VERSION = "0.1.0"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SESSION_MANIFEST_SCHEMA_ID = "urn:cranfield:pilot-assessment:schema:session-manifest:0.1.0"
SESSION_MANIFEST_SCHEMA_TITLE = "Pilot Assessment Session Manifest 0.1.0"
ANCHOR_RESULT_SCHEMA_ID = "urn:cranfield:pilot-assessment:schema:anchor-result:0.1.0"
ANCHOR_RESULT_SCHEMA_TITLE = "Pilot Assessment Anchor Result 0.1.0"
INGESTION_READINESS_SCHEMA_ID = (
    "urn:cranfield:pilot-assessment:schema:ingestion-readiness-report:0.1.0"
)
INGESTION_READINESS_SCHEMA_TITLE = "Pilot Assessment Ingestion Readiness Report 0.1.0"

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
            "non-core optional stream map key must equal descriptor.modality",
            "present or invalid stream checksum keys must exactly match paths",
            "declared paths are unique under Windows case folding",
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
    stream_inventory["properties"] = {
        modality: {
            "properties": {"modality": {"const": modality}},
            "required": ["modality"],
        }
        for modality in sorted(CORE_MODALITIES | {"task_reference"})
    }

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
                        "const": "task_reference",
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
    pending_biometrics = privacy["properties"]["biometric_modalities_export_pending"]
    pending_biometrics["uniqueItems"] = True
    pending_biometrics["items"] = {"enum": sorted(BIOMETRIC_MODALITIES)}

    def stream_status(modality: str, statuses: tuple[str, ...]) -> dict[str, Any]:
        status_match: dict[str, Any] = (
            {"const": statuses[0]} if len(statuses) == 1 else {"enum": list(statuses)}
        )
        return {
            "properties": {
                "streams": {
                    "properties": {
                        modality: {
                            "properties": {"status": status_match},
                            "required": ["status"],
                            "type": "object",
                        }
                    },
                    "required": [modality],
                    "type": "object",
                }
            },
            "required": ["streams"],
            "type": "object",
        }

    def pending_membership(modality: str, *, present: bool) -> dict[str, Any]:
        membership: dict[str, Any] = {"contains": {"const": modality}}
        if not present:
            membership = {"not": membership}
        return {
            "properties": {
                "privacy": {
                    "properties": {
                        "biometric_modalities_export_pending": membership,
                    },
                    "required": ["biometric_modalities_export_pending"],
                    "type": "object",
                }
            },
            "required": ["privacy"],
            "type": "object",
        }

    synthetic_privacy = {
        "properties": {
            "privacy": {
                "properties": {
                    "classification": {"const": "synthetic-test-data"},
                },
                "required": ["classification"],
                "type": "object",
            }
        },
        "required": ["privacy"],
        "type": "object",
    }
    exported_biometrics = {
        "anyOf": [
            stream_status(modality, ("present", "invalid"))
            for modality in sorted(BIOMETRIC_MODALITIES)
        ]
    }
    bundle_task_reference = {
        "properties": {
            "task": {
                "properties": {
                    "reference": {
                        "properties": {"source": {"const": "bundle"}},
                        "required": ["source"],
                        "type": "object",
                    }
                },
                "required": ["reference"],
                "type": "object",
            }
        },
        "required": ["task"],
        "type": "object",
    }
    task_reference_descriptor = {
        "properties": {
            "modality": {"const": "task_reference"},
            "paths": {
                "items": {"pattern": "^references/", "type": "string"},
            },
            "checksums": {
                "propertyNames": {"pattern": "^references/"},
            },
        },
        "required": ["modality", "paths", "checksums"],
        "type": "object",
    }
    schema["allOf"] = [
        *[
            {
                "if": stream_status(modality, ("export_pending",)),
                "then": pending_membership(modality, present=True),
                "else": pending_membership(modality, present=False),
            }
            for modality in sorted(BIOMETRIC_MODALITIES)
        ],
        {
            "if": synthetic_privacy,
            "then": {
                "properties": {
                    "privacy": {
                        "properties": {
                            "contains_biometric_data": {"const": False},
                            "biometric_modalities_export_pending": {"maxItems": 0},
                        },
                        "required": [
                            "contains_biometric_data",
                            "biometric_modalities_export_pending",
                        ],
                    }
                }
            },
        },
        {
            "if": {
                "allOf": [
                    {"not": synthetic_privacy},
                    exported_biometrics,
                ]
            },
            "then": {
                "properties": {
                    "privacy": {
                        "properties": {
                            "contains_biometric_data": {"const": True},
                        },
                        "required": ["contains_biometric_data"],
                    }
                }
            },
        },
        {
            "if": bundle_task_reference,
            "then": {
                "properties": {
                    "task": {
                        "properties": {
                            "reference": {
                                "properties": {
                                    "stream_id": {"const": "task_reference"},
                                },
                                "required": ["stream_id"],
                            }
                        }
                    },
                    "streams": {
                        "properties": {
                            "task_reference": task_reference_descriptor,
                        },
                        "required": ["task_reference"],
                    },
                }
            },
            "else": {
                "properties": {
                    "streams": {"not": {"required": ["task_reference"]}},
                }
            },
        },
    ]
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


def _ingestion_readiness_schema() -> dict[str, Any]:
    schema = _base_schema(
        IngestionReadinessReport,
        schema_id=INGESTION_READINESS_SCHEMA_ID,
        title=INGESTION_READINESS_SCHEMA_TITLE,
        runtime_invariants=[
            "source_snapshot_fingerprint is recomputed from canonical source identity",
            "source paths and checksums remain stable throughout content inspection",
        ],
    )
    stream_results = schema["properties"]["stream_results"]
    stream_results["required"] = sorted(CORE_MODALITIES)
    stream_results["propertyNames"] = {"enum": sorted(CORE_MODALITIES)}
    stream_results["properties"] = {
        modality: {
            "properties": {"modality": {"const": modality}},
            "required": ["modality"],
        }
        for modality in sorted(CORE_MODALITIES)
    }

    readiness_result = schema["$defs"]["StreamReadinessResult"]
    readiness_result["allOf"] = [
        {
            "if": {
                "properties": {"readiness": {"const": "ready"}},
                "required": ["readiness"],
            },
            "then": {
                "properties": {
                    "adapter_id": {"type": "string"},
                    "adapter_version": {"type": "string"},
                    "normalized_schema_id": {"type": "string"},
                    "row_count": {"type": "integer", "minimum": 0},
                }
            },
        },
        {
            "if": {
                "properties": {
                    "readiness": {"enum": ["unavailable", "unsupported", "not_applicable"]}
                },
                "required": ["readiness"],
            },
            "then": {
                "properties": {
                    "adapter_id": {"type": "null"},
                    "adapter_version": {"type": "null"},
                    "normalized_schema_id": {"type": "null"},
                    "row_count": {"type": "null"},
                    "artifact_row_counts": {"maxProperties": 0},
                    "source_time_start_s": {"type": "null"},
                    "source_time_end_s": {"type": "null"},
                    "observed_sample_rate_hz": {"type": "null"},
                }
            },
        },
    ]

    task_reference = schema["properties"]["task_reference_result"]
    task_reference["anyOf"][0] = {
        "allOf": [
            {"$ref": "#/$defs/StreamReadinessResult"},
            {
                "properties": {"modality": {"const": "task_reference"}},
                "required": ["modality"],
            },
        ]
    }

    def core_result_matches(modality: str, result_rule: dict[str, Any]) -> dict[str, Any]:
        return {
            "properties": {
                "stream_results": {
                    "properties": {modality: result_rule},
                    "required": [modality],
                    "type": "object",
                }
            },
            "required": ["stream_results"],
            "type": "object",
        }

    def task_reference_matches(result_rule: dict[str, Any]) -> dict[str, Any]:
        return {
            "properties": {
                "task_reference_result": result_rule,
            },
            "required": ["task_reference_result"],
            "type": "object",
        }

    required_non_ready = {
        "properties": {
            "required_for_import": {"const": True},
            "readiness": {"not": {"const": "ready"}},
        },
        "required": ["required_for_import", "readiness"],
        "type": "object",
    }
    degraded_core = {
        "properties": {
            "readiness": {
                "enum": ["unavailable", "invalid", "unsupported"],
            }
        },
        "required": ["readiness"],
        "type": "object",
    }
    non_ready_reference = {
        "properties": {"readiness": {"not": {"const": "ready"}}},
        "required": ["readiness"],
        "type": "object",
    }
    blocked = {
        "anyOf": [
            *[
                core_result_matches(modality, required_non_ready)
                for modality in sorted(CORE_MODALITIES)
            ],
            task_reference_matches(required_non_ready),
        ]
    }
    degraded = {
        "anyOf": [
            *[core_result_matches(modality, degraded_core) for modality in sorted(CORE_MODALITIES)],
            task_reference_matches(non_ready_reference),
        ]
    }

    schema["allOf"] = [
        {
            "if": {
                "properties": {"source_classification": {"const": "synthetic-test-data"}},
                "required": ["source_classification"],
            },
            "then": {
                "properties": {
                    "synthetic_provenance": {"$ref": "#/$defs/SyntheticSourceProvenance"}
                }
            },
            "else": {"properties": {"synthetic_provenance": {"type": "null"}}},
        },
        {
            "oneOf": [
                {
                    "allOf": [blocked],
                    "properties": {
                        "disposition": {"const": "blocked"},
                        "can_continue_to_synchronization": {"const": False},
                    },
                    "required": [
                        "disposition",
                        "can_continue_to_synchronization",
                    ],
                },
                {
                    "allOf": [{"not": blocked}, degraded],
                    "properties": {
                        "disposition": {"const": "ready_partial"},
                        "can_continue_to_synchronization": {"const": True},
                    },
                    "required": [
                        "disposition",
                        "can_continue_to_synchronization",
                    ],
                },
                {
                    "allOf": [{"not": blocked}, {"not": degraded}],
                    "properties": {
                        "disposition": {"const": "ready"},
                        "can_continue_to_synchronization": {"const": True},
                    },
                    "required": [
                        "disposition",
                        "can_continue_to_synchronization",
                    ],
                },
            ]
        },
    ]
    return schema


def _render_json(schema: dict[str, Any]) -> bytes:
    return (json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_schemas() -> dict[str, bytes]:
    """Return canonical schema bytes keyed by their committed filenames."""

    return {
        "anchor-result-0.1.0.schema.json": _render_json(_anchor_result_schema()),
        "ingestion-readiness-report-0.1.0.schema.json": _render_json(_ingestion_readiness_schema()),
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
    "INGESTION_READINESS_SCHEMA_ID",
    "INGESTION_READINESS_SCHEMA_TITLE",
    "SCHEMA_DIALECT",
    "SESSION_MANIFEST_SCHEMA_ID",
    "SESSION_MANIFEST_SCHEMA_TITLE",
    "export_schemas",
    "render_schemas",
]
