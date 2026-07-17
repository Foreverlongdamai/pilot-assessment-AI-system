"""Generate committed JSON Schemas from the authoritative Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from pilot_assessment.contracts.anchor import SUPPORTED_SOFT_TIE_POLICIES, AnchorResult
from pilot_assessment.contracts.anchor_execution import (
    AnchorCatalog,
    AnchorEvaluationReport,
    AnchorExecutionPlan,
    AnchorPluginDefinition,
    AnchorRuntimeRegistry,
    PreprocessingProviderDefinition,
    ResolvedReferenceSetSnapshot,
    SessionSemanticSnapshot,
)
from pilot_assessment.contracts.anchor_v2 import AnchorMeasurement, AnchorResultV2
from pilot_assessment.contracts.assessment_scheme import (
    AssessmentSchemeVersion,
    CoverageReportingPolicyVersion,
    LayoutVersion,
    SchemeDraft,
    TaskProfileVersion,
)
from pilot_assessment.contracts.bayesian import (
    InferencePlan,
    InferenceTrace,
    ObservationSet,
    PosteriorResult,
)
from pilot_assessment.contracts.common import (
    BUNDLE_RELATIVE_PATH_JSON_SCHEMA_PATTERN,
    BUNDLE_RELATIVE_PATH_PATTERN,
)
from pilot_assessment.contracts.evidence_recipe import EvidenceRecipe, OperatorDefinition
from pilot_assessment.contracts.ingestion import IngestionReadinessReport
from pilot_assessment.contracts.model_components import (
    BnNodeConcept,
    BnNodeVersion,
    CptVersion,
    EvidenceBindingVersion,
    EvidenceConcept,
    EvidenceVersion,
    SourceDescriptor,
)
from pilot_assessment.contracts.model_workspace import (
    ModelChangeEvent,
    ModelGraphSnapshot,
    ModelNode,
    TaskScheme,
)
from pilot_assessment.contracts.project import (
    ArtifactReference,
    AuditEvent,
    ManagedArtifact,
    ProjectDescriptor,
    SessionRecord,
    SessionRevision,
    TransactionReceipt,
)
from pilot_assessment.contracts.run import (
    AssessmentRun,
    AssessmentRunV2,
    CurrentModelRunPreflightReport,
    CurrentModelRunSnapshot,
    RunEvent,
    RunPreflightReport,
    RunResultEnvelope,
    RunSnapshot,
)
from pilot_assessment.contracts.session import (
    BIOMETRIC_MODALITIES,
    CORE_MODALITIES,
    SessionManifest,
    SyntheticSourceProvenance,
)
from pilot_assessment.contracts.synchronization import (
    BLOCKING_SYNCHRONIZATION_ERROR_CODES,
    MAX_SESSION_END_NS_V0_1,
    SynchronizationReport,
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
SYNCHRONIZATION_REPORT_SCHEMA_ID = (
    "urn:cranfield:pilot-assessment:schema:synchronization-report:0.1.0"
)
SYNCHRONIZATION_REPORT_SCHEMA_TITLE = "Pilot Assessment Synchronization Report 0.1.0"

_M4_SCHEMA_MODELS: tuple[
    tuple[str, type[BaseModel], str, str, str, list[str]],
    ...,
] = (
    (
        "anchor-result-0.2.0.schema.json",
        AnchorResultV2,
        "urn:cranfield:pilot-assessment:schema:anchor-result:0.2.0",
        "Pilot Assessment Anchor Result 0.2.0",
        "0.2.0",
        [
            "calculation status controls evidence, score, measurement and override fields",
            "result_fingerprint is recomputed from the canonical logical result payload",
        ],
    ),
    (
        "anchor-measurement-0.1.0.schema.json",
        AnchorMeasurement,
        "urn:cranfield:pilot-assessment:schema:anchor-measurement:0.1.0",
        "Pilot Assessment Anchor Measurement 0.1.0",
        "0.1.0",
        [
            "calculation status controls primary measurement and override-candidate fields",
            "derived artifact references exactly match the current anchor transaction",
        ],
    ),
    (
        "anchor-plugin-definition-0.1.0.schema.json",
        AnchorPluginDefinition,
        "urn:cranfield:pilot-assessment:schema:anchor-plugin-definition:0.1.0",
        "Pilot Assessment Anchor Plugin Definition 0.1.0",
        "0.1.0",
        ["projection paths, dependencies and artifact recipes are unique and typed"],
    ),
    (
        "preprocessing-provider-definition-0.1.0.schema.json",
        PreprocessingProviderDefinition,
        "urn:cranfield:pilot-assessment:schema:preprocessing-provider-definition:0.1.0",
        "Pilot Assessment Preprocessing Provider Definition 0.1.0",
        "0.1.0",
        ["projection paths and preprocessing dependency slots are unique and typed"],
    ),
    (
        "anchor-catalog-0.1.0.schema.json",
        AnchorCatalog,
        "urn:cranfield:pilot-assessment:schema:anchor-catalog:0.1.0",
        "Pilot Assessment Anchor Catalog 0.1.0",
        "0.1.0",
        ["entries use unique keys and canonical catalog order"],
    ),
    (
        "anchor-runtime-registry-0.1.0.schema.json",
        AnchorRuntimeRegistry,
        "urn:cranfield:pilot-assessment:schema:anchor-runtime-registry:0.1.0",
        "Pilot Assessment Anchor Runtime Registry 0.1.0",
        "0.1.0",
        ["plugin and preprocessing entries use canonical unique registry keys"],
    ),
    (
        "anchor-execution-plan-0.1.0.schema.json",
        AnchorExecutionPlan,
        "urn:cranfield:pilot-assessment:schema:anchor-execution-plan:0.1.0",
        "Pilot Assessment Anchor Execution Plan 0.1.0",
        "0.1.0",
        [
            "active entries, input contracts and dependency DAGs resolve exactly",
            "quality-gate parameter fields are forbidden recursively",
        ],
    ),
    (
        "session-semantic-snapshot-0.1.0.schema.json",
        SessionSemanticSnapshot,
        "urn:cranfield:pilot-assessment:schema:session-semantic-snapshot:0.1.0",
        "Pilot Assessment Session Semantic Snapshot 0.1.0",
        "0.1.0",
        ["semantic inventories, references, scopes and applicability close exactly"],
    ),
    (
        "resolved-reference-set-0.1.0.schema.json",
        ResolvedReferenceSetSnapshot,
        "urn:cranfield:pilot-assessment:schema:resolved-reference-set:0.1.0",
        "Pilot Assessment Resolved Reference Set 0.1.0",
        "0.1.0",
        ["reference descriptors are canonical and bind one exact session identity"],
    ),
    (
        "anchor-evaluation-report-0.1.0.schema.json",
        AnchorEvaluationReport,
        "urn:cranfield:pilot-assessment:schema:anchor-evaluation-report:0.1.0",
        "Pilot Assessment Anchor Evaluation Report 0.1.0",
        "0.1.0",
        [
            "inventory and results close one-to-one in canonical relative order",
            "availability and disposition are derived from terminal result statuses",
        ],
    ),
    (
        "evidence-recipe-0.1.0.schema.json",
        EvidenceRecipe,
        "urn:cranfield:pilot-assessment:schema:evidence-recipe:0.1.0",
        "Pilot Assessment Evidence Recipe 0.1.0",
        "0.1.0",
        [
            "draft recipes may contain dangling graph references until technical validation",
            "the same canonical recipe object is used for display, persistence and execution",
        ],
    ),
    (
        "operator-definition-0.1.0.schema.json",
        OperatorDefinition,
        "urn:cranfield:pilot-assessment:schema:operator-definition:0.1.0",
        "Pilot Assessment Operator Definition 0.1.0",
        "0.1.0",
        [
            "operator identity binds portable metadata to one trusted implementation",
            "parameter schema and UI paths are part of the portable definition",
        ],
    ),
)

_M5_SCHEMA_MODELS: tuple[
    tuple[str, type[BaseModel], str, str, str, list[str]],
    ...,
] = (
    (
        "evidence-concept-0.1.0.schema.json",
        EvidenceConcept,
        "urn:cranfield:pilot-assessment:schema:evidence-concept:0.1.0",
        "Pilot Assessment Evidence Concept 0.1.0",
        "0.1.0",
        ["concept IDs are immutable and tags are unique"],
    ),
    (
        "evidence-version-0.1.0.schema.json",
        EvidenceVersion,
        "urn:cranfield:pilot-assessment:schema:evidence-version:0.1.0",
        "Pilot Assessment Evidence Version 0.1.0",
        "0.1.0",
        ["each version binds one exact EvidenceRecipe and canonical content hash"],
    ),
    (
        "bn-node-concept-0.1.0.schema.json",
        BnNodeConcept,
        "urn:cranfield:pilot-assessment:schema:bn-node-concept:0.1.0",
        "Pilot Assessment BN Node Concept 0.1.0",
        "0.1.0",
        ["concept IDs are immutable and node role is explicit"],
    ),
    (
        "bn-node-version-0.1.0.schema.json",
        BnNodeVersion,
        "urn:cranfield:pilot-assessment:schema:bn-node-version:0.1.0",
        "Pilot Assessment BN Node Version 0.1.0",
        "0.1.0",
        ["state and probabilistic-parent order is canonical and ID references are exact"],
    ),
    (
        "evidence-binding-version-0.1.0.schema.json",
        EvidenceBindingVersion,
        "urn:cranfield:pilot-assessment:schema:evidence-binding-version:0.1.0",
        "Pilot Assessment Evidence Binding Version 0.1.0",
        "0.1.0",
        [
            "observation state and parent order is canonical",
            "modality attribution weights are reporting-only and sum to one",
        ],
    ),
    (
        "cpt-version-0.1.0.schema.json",
        CptVersion,
        "urn:cranfield:pilot-assessment:schema:cpt-version:0.1.0",
        "Pilot Assessment CPT Version 0.1.0",
        "0.1.0",
        ["parent variables and state spaces use declared stable order"],
    ),
    (
        "task-profile-version-0.1.0.schema.json",
        TaskProfileVersion,
        "urn:cranfield:pilot-assessment:schema:task-profile-version:0.1.0",
        "Pilot Assessment Task Profile Version 0.1.0",
        "0.1.0",
        ["task semantics and required source IDs are immutable version content"],
    ),
    (
        "coverage-reporting-policy-version-0.1.0.schema.json",
        CoverageReportingPolicyVersion,
        "urn:cranfield:pilot-assessment:schema:coverage-reporting-policy-version:0.1.0",
        "Pilot Assessment Coverage Reporting Policy Version 0.1.0",
        "0.1.0",
        ["reporting policy cannot act as a scientific or raw-data quality gate"],
    ),
    (
        "layout-version-0.1.0.schema.json",
        LayoutVersion,
        "urn:cranfield:pilot-assessment:schema:layout-version:0.1.0",
        "Pilot Assessment Layout Version 0.1.0",
        "0.1.0",
        ["node positions and groups use unique stable IDs"],
    ),
    (
        "assessment-scheme-version-0.1.0.schema.json",
        AssessmentSchemeVersion,
        "urn:cranfield:pilot-assessment:schema:assessment-scheme-version:0.1.0",
        "Pilot Assessment Scheme Version 0.1.0",
        "0.1.0",
        ["all scheme dependencies are exact ID and content-hash pins"],
    ),
    (
        "source-descriptor-0.1.0.schema.json",
        SourceDescriptor,
        "urn:cranfield:pilot-assessment:schema:source-descriptor:0.1.0",
        "Pilot Assessment Source Descriptor 0.1.0",
        "0.1.0",
        ["source kind, declared type, and provenance dependencies are explicit"],
    ),
    (
        "scheme-draft-0.1.0.schema.json",
        SchemeDraft,
        "urn:cranfield:pilot-assessment:schema:scheme-draft:0.1.0",
        "Pilot Assessment Scheme Draft 0.1.0",
        "0.1.0",
        ["drafts may be incomplete while retaining typed edges and finite canonical JSON"],
    ),
    (
        "inference-plan-0.1.0.schema.json",
        InferencePlan,
        "urn:cranfield:pilot-assessment:schema:inference-plan:0.1.0",
        "Pilot Assessment Inference Plan 0.1.0",
        "0.1.0",
        ["variables, state order, CPT pins, and scheme identity are exact"],
    ),
    (
        "observation-set-0.1.0.schema.json",
        ObservationSet,
        "urn:cranfield:pilot-assessment:schema:observation-set:0.1.0",
        "Pilot Assessment Observation Set 0.1.0",
        "0.1.0",
        ["each variable has at most one explicit hard, virtual, or omitted observation"],
    ),
    (
        "posterior-result-0.1.0.schema.json",
        PosteriorResult,
        "urn:cranfield:pilot-assessment:schema:posterior-result:0.1.0",
        "Pilot Assessment Posterior Result 0.1.0",
        "0.1.0",
        ["prior and posterior distributions use identical query-variable order"],
    ),
    (
        "inference-trace-0.1.0.schema.json",
        InferenceTrace,
        "urn:cranfield:pilot-assessment:schema:inference-trace:0.1.0",
        "Pilot Assessment Inference Trace 0.1.0",
        "0.1.0",
        ["inference influence edges are read-only leave-one-observation-out overlays"],
    ),
)

_M6_SCHEMA_MODELS: tuple[
    tuple[str, type[BaseModel], str, str, str, list[str]],
    ...,
] = (
    (
        "project-descriptor-0.1.0.schema.json",
        ProjectDescriptor,
        "urn:cranfield:pilot-assessment:schema:project-descriptor:0.1.0",
        "Pilot Assessment Project Descriptor 0.1.0",
        "0.1.0",
        ["project identity is portable and does not contain an absolute storage path"],
    ),
    (
        "session-record-0.1.0.schema.json",
        SessionRecord,
        "urn:cranfield:pilot-assessment:schema:session-record:0.1.0",
        "Pilot Assessment Session Record 0.1.0",
        "0.1.0",
        ["a session points to one exact current managed revision"],
    ),
    (
        "session-revision-0.1.0.schema.json",
        SessionRevision,
        "urn:cranfield:pilot-assessment:schema:session-revision:0.1.0",
        "Pilot Assessment Session Revision 0.1.0",
        "0.1.0",
        ["managed bundle paths are project relative and bound to exact content hashes"],
    ),
    (
        "managed-artifact-0.1.0.schema.json",
        ManagedArtifact,
        "urn:cranfield:pilot-assessment:schema:managed-artifact:0.1.0",
        "Pilot Assessment Managed Artifact 0.1.0",
        "0.1.0",
        ["the managed relative path is derived from the artifact SHA-256 digest"],
    ),
    (
        "artifact-reference-0.1.0.schema.json",
        ArtifactReference,
        "urn:cranfield:pilot-assessment:schema:artifact-reference:0.1.0",
        "Pilot Assessment Artifact Reference 0.1.0",
        "0.1.0",
        ["artifact ownership and semantic role are explicit"],
    ),
    (
        "transaction-receipt-0.1.0.schema.json",
        TransactionReceipt,
        "urn:cranfield:pilot-assessment:schema:transaction-receipt:0.1.0",
        "Pilot Assessment Transaction Receipt 0.1.0",
        "0.1.0",
        ["prepared and completed transactions use mutually exclusive field shapes"],
    ),
    (
        "audit-event-0.1.0.schema.json",
        AuditEvent,
        "urn:cranfield:pilot-assessment:schema:audit-event:0.1.0",
        "Pilot Assessment Audit Event 0.1.0",
        "0.1.0",
        ["audit events are immutable metadata and do not embed managed payload bytes"],
    ),
    (
        "run-preflight-report-0.1.0.schema.json",
        RunPreflightReport,
        "urn:cranfield:pilot-assessment:schema:run-preflight-report:0.1.0",
        "Pilot Assessment Run Preflight Report 0.1.0",
        "0.1.0",
        [
            "technical readiness is independent of scientific calibration",
            "formal authorization requires ready non-synthetic input",
        ],
    ),
    (
        "run-snapshot-0.1.0.schema.json",
        RunSnapshot,
        "urn:cranfield:pilot-assessment:schema:run-snapshot:0.1.0",
        "Pilot Assessment Run Snapshot 0.1.0",
        "0.1.0",
        ["session, scheme, component, source, operator, engine, and runtime identities are exact"],
    ),
    (
        "assessment-run-0.1.0.schema.json",
        AssessmentRun,
        "urn:cranfield:pilot-assessment:schema:assessment-run:0.1.0",
        "Pilot Assessment Run 0.1.0",
        "0.1.0",
        ["run states, stages, and lifecycle timestamps use one consistent shape"],
    ),
    (
        "run-event-0.1.0.schema.json",
        RunEvent,
        "urn:cranfield:pilot-assessment:schema:run-event:0.1.0",
        "Pilot Assessment Run Event 0.1.0",
        "0.1.0",
        ["event sequence is positive and completed units never exceed frozen total units"],
    ),
    (
        "run-result-envelope-0.1.0.schema.json",
        RunResultEnvelope,
        "urn:cranfield:pilot-assessment:schema:run-result-envelope:0.1.0",
        "Pilot Assessment Run Result Envelope 0.1.0",
        "0.1.0",
        ["result artifacts are exact SHA-256 references and use unique semantic roles"],
    ),
)

_M7_SCHEMA_MODELS: tuple[
    tuple[str, type[BaseModel], str, str, str, list[str]],
    ...,
] = (
    (
        "model-node-0.1.0.schema.json",
        ModelNode,
        "urn:cranfield:pilot-assessment:schema:model-node:0.1.0",
        "Pilot Assessment Current Model Node 0.1.0",
        "0.1.0",
        [
            "node kind determines the discriminated definition shape",
            "semantic and layout revisions are independent current-object revisions",
            "evidence definitions bind raw inputs and BN definitions bind probabilistic parents",
        ],
    ),
    (
        "task-scheme-0.1.0.schema.json",
        TaskScheme,
        "urn:cranfield:pilot-assessment:schema:task-scheme:0.1.0",
        "Pilot Assessment Current Task Scheme 0.1.0",
        "0.1.0",
        [
            "explicit activation is a subset of the canonical active closure",
            "run outputs are active BN nodes",
            "scheme layout overrides do not change shared node semantics",
        ],
    ),
    (
        "model-graph-snapshot-0.1.0.schema.json",
        ModelGraphSnapshot,
        "urn:cranfield:pilot-assessment:schema:model-graph-snapshot:0.1.0",
        "Pilot Assessment Current Model Graph Snapshot 0.1.0",
        "0.1.0",
        [
            "nodes and derived typed edges use canonical order",
            "graph revision and content hash identify one current projection",
        ],
    ),
    (
        "model-change-event-0.1.0.schema.json",
        ModelChangeEvent,
        "urn:cranfield:pilot-assessment:schema:model-change-event:0.1.0",
        "Pilot Assessment Current Model Change Event 0.1.0",
        "0.1.0",
        [
            "change events record before and after revisions and hashes without creating versions",
        ],
    ),
    (
        "current-model-run-preflight-report-0.1.0.schema.json",
        CurrentModelRunPreflightReport,
        "urn:cranfield:pilot-assessment:schema:current-model-run-preflight-report:0.1.0",
        "Pilot Assessment Current Model Run Preflight Report 0.1.0",
        "0.1.0",
        [
            "technical readiness binds one current scheme and its exact active node closure",
            "scientific calibration is reported separately from executable readiness",
        ],
    ),
    (
        "current-model-run-snapshot-0.1.0.schema.json",
        CurrentModelRunSnapshot,
        "urn:cranfield:pilot-assessment:schema:current-model-run-snapshot:0.1.0",
        "Pilot Assessment Current Model Run Snapshot 0.1.0",
        "0.1.0",
        [
            "a run freezes the full current scheme, exact active nodes, "
            "operator identities and runtime identity",
            "the embedded legacy execution snapshot remains a compatibility replay detail",
        ],
    ),
    (
        "assessment-run-0.2.0.schema.json",
        AssessmentRunV2,
        "urn:cranfield:pilot-assessment:schema:assessment-run:0.2.0",
        "Pilot Assessment Current Model Run 0.2.0",
        "0.2.0",
        [
            "run lifecycle timestamps and stages use one consistent shape",
            "the current-model snapshot is immutable after run creation",
        ],
    ),
)

_QUALITY_GATE_FIELD_NAMES = frozenset(
    {
        "quality",
        "quality_gate",
        "quality_gates",
        "quality_transform",
        "min_valid_coverage",
        "failed_quality",
        "invalid_quality",
        "binary_quality_v1",
    }
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIRECTORY = _PROJECT_ROOT / "schemas"
_DEFAULT_PACKAGE_OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "schema_resources"


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
    contract_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    _replace_runtime_only_path_patterns(schema)
    schema["$schema"] = SCHEMA_DIALECT
    schema["$id"] = schema_id
    schema["title"] = title
    schema["x-contract-version"] = contract_version
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
            "synthetic-test-data requires complete D-012 provenance in extensions.synthetic",
        ],
    )
    synthetic_provenance_schema = SyntheticSourceProvenance.model_json_schema(mode="validation")
    _replace_runtime_only_path_patterns(synthetic_provenance_schema)
    synthetic_provenance_schema["additionalProperties"] = True
    schema["$defs"]["SyntheticSourceProvenance"] = synthetic_provenance_schema
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
                    "extensions": {
                        "properties": {
                            "synthetic": {
                                "$ref": "#/$defs/SyntheticSourceProvenance",
                            }
                        },
                        "required": ["synthetic"],
                        "type": "object",
                    },
                    "privacy": {
                        "properties": {
                            "contains_biometric_data": {"const": False},
                            "biometric_modalities_export_pending": {"maxItems": 0},
                        },
                        "required": [
                            "contains_biometric_data",
                            "biometric_modalities_export_pending",
                        ],
                    },
                },
                "required": ["extensions"],
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


def _synchronization_report_schema() -> dict[str, Any]:
    schema = _base_schema(
        SynchronizationReport,
        schema_id=SYNCHRONIZATION_REPORT_SCHEMA_ID,
        title=SYNCHRONIZATION_REPORT_SCHEMA_TITLE,
        runtime_invariants=[
            "artifact map keys equal artifact_role values",
            "point and interval row partitions equal total_rows",
            "mapped bounds, spans, duplicates, and gap statistics are internally consistent",
            "session window end is at most the v0.1 exact-metrics bound",
            "source and synchronization fingerprints are recomputed from canonical inputs",
        ],
    )

    session_window = schema["$defs"]["SessionWindow"]
    session_window["properties"]["end_t_ns"]["minimum"] = 1
    session_window["properties"]["end_t_ns"]["maximum"] = MAX_SESSION_END_NS_V0_1

    stream_results = schema["properties"]["stream_results"]
    stream_results.pop("patternProperties", None)
    stream_results.pop("propertyNames", None)
    stream_results["additionalProperties"] = False
    stream_results["required"] = sorted(CORE_MODALITIES)
    stream_results["properties"] = {
        modality: {
            "allOf": [
                {"$ref": "#/$defs/StreamSynchronizationResult"},
                {
                    "properties": {"modality": {"const": modality}},
                    "required": ["modality"],
                    "type": "object",
                },
            ]
        }
        for modality in sorted(CORE_MODALITIES)
    }

    aligned_schema_rule = {
        "pattern": r"-aligned-v0\.1$",
        "type": "string",
    }
    consistent_clock_rule = {
        "allOf": [
            {"$ref": "#/$defs/ClockMappingSummary"},
            {
                "properties": {"declaration_consistent": {"const": True}},
                "required": ["declaration_consistent"],
                "type": "object",
            },
        ]
    }
    stream_result = schema["$defs"]["StreamSynchronizationResult"]
    stream_result["allOf"] = [
        {
            "not": {
                "properties": {
                    "synchronization_status": {"const": "deferred_model_bundle_resolution"}
                },
                "required": ["synchronization_status"],
                "type": "object",
            }
        },
        {
            "if": {
                "properties": {"synchronization_status": {"const": "aligned"}},
                "required": ["synchronization_status"],
                "type": "object",
            },
            "then": {
                "allOf": [
                    {
                        "properties": {
                            "declared_status": {"const": "present"},
                            "input_readiness": {"const": "ready"},
                            "clock": consistent_clock_rule,
                            "source_schema_id": {"type": "string"},
                            "aligned_schema_id": aligned_schema_rule,
                            "artifacts": {"minProperties": 1},
                        },
                        "required": [
                            "declared_status",
                            "input_readiness",
                            "clock",
                            "source_schema_id",
                            "aligned_schema_id",
                            "artifacts",
                        ],
                        "type": "object",
                    },
                    {
                        "if": {
                            "properties": {"modality": {"const": "G"}},
                            "required": ["modality"],
                            "type": "object",
                        },
                        "then": {
                            "properties": {
                                "scene_gaze_metrics": {"$ref": "#/$defs/SceneGazeMetrics"}
                            },
                            "required": ["scene_gaze_metrics"],
                        },
                        "else": {"properties": {"scene_gaze_metrics": {"type": "null"}}},
                    },
                ]
            },
            "else": {
                "allOf": [
                    {
                        "properties": {
                            "aligned_schema_id": {"type": "null"},
                            "artifacts": {"maxProperties": 0},
                        },
                        "type": "object",
                    },
                    {
                        "if": {
                            "properties": {
                                "modality": {"const": "G"},
                                "synchronization_status": {"const": "invalid"},
                            },
                            "required": ["modality", "synchronization_status"],
                            "type": "object",
                        },
                        "else": {"properties": {"scene_gaze_metrics": {"type": "null"}}},
                    },
                ]
            },
        },
    ]

    for metrics_name in (
        "PointTemporalArtifactMetrics",
        "IntervalTemporalArtifactMetrics",
    ):
        schema["$defs"][metrics_name]["properties"]["aligned_schema_id"]["pattern"] = (
            r"-aligned-v0\.1$"
        )

    reference_result = schema["$defs"]["TaskReferenceSynchronizationResult"]
    reference_result["allOf"] = [
        {
            "if": {
                "properties": {"source": {"const": "model_bundle"}},
                "required": ["source"],
                "type": "object",
            },
            "then": {
                "properties": {
                    "declared_status": {"type": "null"},
                    "required_for_import": {"type": "null"},
                    "input_readiness": {"type": "null"},
                    "synchronization_status": {"const": "deferred_model_bundle_resolution"},
                    "clock": {"type": "null"},
                    "source_schema_id": {"type": "null"},
                    "aligned_schema_id": {"type": "null"},
                    "source_checksums": {"maxProperties": 0},
                    "artifacts": {"maxProperties": 0},
                },
                "type": "object",
            },
            "else": {
                "allOf": [
                    {
                        "not": {
                            "properties": {
                                "synchronization_status": {
                                    "const": "deferred_model_bundle_resolution"
                                }
                            },
                            "required": ["synchronization_status"],
                            "type": "object",
                        }
                    },
                    {
                        "properties": {
                            "declared_status": {"not": {"type": "null"}},
                            "required_for_import": {"type": "boolean"},
                            "input_readiness": {"not": {"type": "null"}},
                        },
                        "required": [
                            "declared_status",
                            "required_for_import",
                            "input_readiness",
                        ],
                        "type": "object",
                    },
                    {
                        "if": {
                            "properties": {"synchronization_status": {"const": "aligned"}},
                            "required": ["synchronization_status"],
                            "type": "object",
                        },
                        "then": {
                            "properties": {
                                "declared_status": {"const": "present"},
                                "input_readiness": {"const": "ready"},
                                "clock": consistent_clock_rule,
                                "source_schema_id": {"type": "string"},
                                "aligned_schema_id": aligned_schema_rule,
                                "source_checksums": {"minProperties": 1},
                                "artifacts": {"minProperties": 1},
                            },
                            "required": [
                                "clock",
                                "source_schema_id",
                                "aligned_schema_id",
                                "source_checksums",
                                "artifacts",
                            ],
                            "type": "object",
                        },
                        "else": {
                            "properties": {
                                "aligned_schema_id": {"type": "null"},
                                "artifacts": {"maxProperties": 0},
                            },
                            "type": "object",
                        },
                    },
                ]
            },
        }
    ]

    annotation_result = schema["$defs"]["AnnotationSynchronizationResult"]
    annotation_result["properties"]["synchronization_status"] = {
        "enum": ["aligned", "not_attempted", "invalid", "unsupported"],
        "type": "string",
    }
    annotation_result["allOf"] = [
        {
            "if": {
                "properties": {"synchronization_status": {"const": "aligned"}},
                "required": ["synchronization_status"],
                "type": "object",
            },
            "then": {
                "properties": {
                    "revision": {"type": "string"},
                    "phase_schema_id": {"type": "string"},
                    "event_schema_id": {"type": "string"},
                    "baseline_schema_id": {"type": "string"},
                    "phase_count": {"minimum": 0, "type": "integer"},
                    "event_count": {"minimum": 0, "type": "integer"},
                    "baseline_count": {"minimum": 0, "type": "integer"},
                    "synthetic_semantics_unvalidated": {"type": "boolean"},
                },
                "required": [
                    "revision",
                    "phase_schema_id",
                    "event_schema_id",
                    "baseline_schema_id",
                    "phase_count",
                    "event_count",
                    "baseline_count",
                    "synthetic_semantics_unvalidated",
                ],
                "type": "object",
            },
            "else": {
                "properties": {
                    "phase_count": {"type": "null"},
                    "event_count": {"type": "null"},
                    "baseline_count": {"type": "null"},
                    "unannotated_intervals": {"maxItems": 0},
                    "synthetic_semantics_unvalidated": {"type": "null"},
                },
                "type": "object",
            },
        }
    ]

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

    required_non_aligned = {
        "properties": {
            "required_for_import": {"const": True},
            "synchronization_status": {"not": {"const": "aligned"}},
        },
        "required": ["required_for_import", "synchronization_status"],
        "type": "object",
    }
    optional_degraded = {
        "properties": {
            "required_for_import": {"const": False},
            "synchronization_status": {
                "enum": ["not_attempted", "unavailable", "invalid", "unsupported"]
            },
        },
        "required": ["required_for_import", "synchronization_status"],
        "type": "object",
    }
    annotation_failed = {
        "properties": {
            "annotation_result": {
                "anyOf": [
                    {"type": "null"},
                    {
                        "properties": {"synchronization_status": {"not": {"const": "aligned"}}},
                        "required": ["synchronization_status"],
                        "type": "object",
                    },
                ]
            }
        },
        "required": ["annotation_result"],
        "type": "object",
    }
    reference_blocked = task_reference_matches(
        {
            "properties": {
                "source": {"const": "bundle"},
                "required_for_import": {"const": True},
                "synchronization_status": {"not": {"const": "aligned"}},
            },
            "required": ["source", "required_for_import", "synchronization_status"],
            "type": "object",
        }
    )
    reference_degraded = task_reference_matches(
        {
            "properties": {
                "source": {"const": "bundle"},
                "required_for_import": {"const": False},
                "synchronization_status": {
                    "enum": ["not_attempted", "unavailable", "invalid", "unsupported"]
                },
            },
            "required": ["source", "required_for_import", "synchronization_status"],
            "type": "object",
        }
    )
    blocking_global_issue = {
        "properties": {
            "global_issues": {
                "contains": {
                    "properties": {
                        "error_code": {"enum": sorted(BLOCKING_SYNCHRONIZATION_ERROR_CODES)}
                    },
                    "required": ["error_code"],
                    "type": "object",
                }
            }
        },
        "required": ["global_issues"],
        "type": "object",
    }
    missing_window = {
        "properties": {"session_window": {"type": "null"}},
        "required": ["session_window"],
        "type": "object",
    }
    blocked = {
        "anyOf": [
            missing_window,
            *[
                core_result_matches(modality, required_non_aligned)
                for modality in sorted(CORE_MODALITIES)
            ],
            annotation_failed,
            reference_blocked,
            blocking_global_issue,
        ]
    }
    degraded = {
        "anyOf": [
            *[
                core_result_matches(modality, optional_degraded)
                for modality in sorted(CORE_MODALITIES)
            ],
            reference_degraded,
        ]
    }

    schema["properties"]["formal_run_authorized"] = {"const": False}
    schema["allOf"] = [
        {
            "if": {
                "properties": {"source_classification": {"const": "synthetic-test-data"}},
                "required": ["source_classification"],
                "type": "object",
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
                        "can_continue_to_anchor_availability": {"const": False},
                    },
                    "required": [
                        "disposition",
                        "can_continue_to_anchor_availability",
                    ],
                    "type": "object",
                },
                {
                    "allOf": [{"not": blocked}, degraded],
                    "properties": {
                        "session_window": {"not": {"type": "null"}},
                        "disposition": {"const": "ready_partial"},
                        "can_continue_to_anchor_availability": {"const": True},
                    },
                    "required": [
                        "session_window",
                        "disposition",
                        "can_continue_to_anchor_availability",
                    ],
                    "type": "object",
                },
                {
                    "allOf": [{"not": blocked}, {"not": degraded}],
                    "properties": {
                        "session_window": {"not": {"type": "null"}},
                        "disposition": {"const": "ready"},
                        "can_continue_to_anchor_availability": {"const": True},
                    },
                    "required": [
                        "session_window",
                        "disposition",
                        "can_continue_to_anchor_availability",
                    ],
                    "type": "object",
                },
            ]
        },
    ]
    return schema


def _quality_gate_free_json_schema() -> dict[str, Any]:
    """Describe arbitrary JSON while excluding M4 quality-gate vocabulary recursively."""

    recursive_reference = {"$ref": "#/$defs/QualityGateFreeJsonValue"}
    return {
        "anyOf": [
            {"type": "null"},
            {"type": "boolean"},
            {"type": "integer"},
            {"type": "number"},
            {"type": "string"},
            {"items": recursive_reference, "type": "array"},
            {
                "additionalProperties": recursive_reference,
                "propertyNames": {
                    "not": {"enum": sorted(_QUALITY_GATE_FIELD_NAMES)},
                },
                "type": "object",
            },
        ]
    }


def _exclude_quality_gate_parameters(schema: dict[str, Any]) -> None:
    """Mirror the runtime's recursive quality-field rejection in JSON Schema."""

    schema["$defs"]["QualityGateFreeJsonValue"] = _quality_gate_free_json_schema()
    for definition_name, field_names in {
        "AnchorExecutionEntry": ("parameters", "temporal_recipe"),
        "ResolvedAlgorithmProfile": ("parameters",),
        "ResolvedPreprocessingRecipe": ("parameters",),
        "ScorerPolicy": ("parameters",),
    }.items():
        definition = schema["$defs"][definition_name]
        for field_name in field_names:
            mapping = definition["properties"][field_name]
            property_name_rule = mapping.get("propertyNames", {})
            mapping["propertyNames"] = {
                "allOf": [
                    property_name_rule,
                    {"not": {"enum": sorted(_QUALITY_GATE_FIELD_NAMES)}},
                ]
            }
            mapping["patternProperties"] = {
                pattern: {"$ref": "#/$defs/QualityGateFreeJsonValue"}
                for pattern in mapping.get("patternProperties", {})
            }
            mapping["additionalProperties"] = False


def _m4_schema(
    model: type[BaseModel],
    *,
    schema_id: str,
    title: str,
    contract_version: str,
    runtime_invariants: list[str],
) -> dict[str, Any]:
    schema = _base_schema(
        model,
        schema_id=schema_id,
        title=title,
        runtime_invariants=runtime_invariants,
        contract_version=contract_version,
    )
    if model is AnchorExecutionPlan:
        _exclude_quality_gate_parameters(schema)
    if model is AnchorEvaluationReport:
        schema["properties"]["formal_run_authorized"]["const"] = False
    return schema


def _render_json(schema: dict[str, Any]) -> bytes:
    return (json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_schemas() -> dict[str, bytes]:
    """Return canonical schema bytes keyed by their committed filenames."""

    schemas = {
        "anchor-result-0.1.0.schema.json": _render_json(_anchor_result_schema()),
        "ingestion-readiness-report-0.1.0.schema.json": _render_json(_ingestion_readiness_schema()),
        "session-manifest-0.1.0.schema.json": _render_json(_session_manifest_schema()),
        "synchronization-report-0.1.0.schema.json": _render_json(_synchronization_report_schema()),
    }
    schemas.update(
        {
            name: _render_json(
                _m4_schema(
                    model,
                    schema_id=schema_id,
                    title=title,
                    contract_version=contract_version,
                    runtime_invariants=runtime_invariants,
                )
            )
            for (
                name,
                model,
                schema_id,
                title,
                contract_version,
                runtime_invariants,
            ) in (
                *_M4_SCHEMA_MODELS,
                *_M5_SCHEMA_MODELS,
                *_M6_SCHEMA_MODELS,
                *_M7_SCHEMA_MODELS,
            )
        }
    )
    return schemas


def export_schemas(
    output_directory: str | Path = _DEFAULT_OUTPUT_DIRECTORY,
    package_output_directory: str | Path | None = None,
) -> tuple[Path, ...]:
    """Write one target compatibly, or publish two byte-identical targets with rollback."""

    outputs = (Path(output_directory),)
    if package_output_directory is not None:
        package_output = Path(package_output_directory)
        if package_output.resolve() == outputs[0].resolve():
            raise ValueError("schema export targets must be distinct")
        outputs += (package_output,)
    for output in outputs:
        output.mkdir(parents=True, exist_ok=True)

    rendered = render_schemas()
    staged: list[tuple[Path, Path]] = []
    rollback_temporaries: list[Path] = []
    previous_bytes: dict[Path, bytes | None] = {}
    try:
        for output in outputs:
            for name, payload in rendered.items():
                destination = output / name
                temporary = output / f".{name}.tmp"
                staged.append((temporary, destination))
                previous_bytes[destination] = (
                    destination.read_bytes() if destination.exists() else None
                )
                temporary.write_bytes(payload)
        for temporary, destination in staged:
            temporary.replace(destination)
    except BaseException as publish_error:
        rollback_errors: list[BaseException] = []
        for destination, previous in previous_bytes.items():
            try:
                if previous is None:
                    destination.unlink(missing_ok=True)
                    continue
                rollback = destination.with_name(f".{destination.name}.rollback.tmp")
                rollback_temporaries.append(rollback)
                rollback.write_bytes(previous)
                rollback.replace(destination)
            except BaseException as rollback_error:  # pragma: no cover - catastrophic I/O path
                rollback_errors.append(rollback_error)
        if rollback_errors:
            raise RuntimeError(
                "schema export failed and rollback was incomplete"
            ) from publish_error
        raise
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        for temporary in rollback_temporaries:
            temporary.unlink(missing_ok=True)

    return tuple(destination for _, destination in staged)


def main() -> None:
    for path in export_schemas(
        _DEFAULT_OUTPUT_DIRECTORY,
        _DEFAULT_PACKAGE_OUTPUT_DIRECTORY,
    ):
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
    "SYNCHRONIZATION_REPORT_SCHEMA_ID",
    "SYNCHRONIZATION_REPORT_SCHEMA_TITLE",
    "export_schemas",
    "render_schemas",
]
