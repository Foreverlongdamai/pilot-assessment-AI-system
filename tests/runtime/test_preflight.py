from __future__ import annotations

import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.assessment_scheme import AssessmentSchemeVersion, TaskProfileVersion
from pilot_assessment.contracts.model_components import ComponentKind
from pilot_assessment.contracts.run import (
    RunPurpose,
    TechnicalDisposition,
)
from pilot_assessment.persistence.database import encode_canonical_json
from pilot_assessment.runtime import ProjectApplication
from pilot_assessment.runtime.sources import (
    RuntimeSourceResolver,
    SourceResolutionContext,
    SourceResolutionStatus,
)
from tests.runtime.system_support import open_test_system

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_preflight_locks_dynamic_closure_and_keeps_scientific_status_separate_from_execution(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external-bundle"
    shutil.copytree(m4_workflow_bundle, external)
    system = open_test_system(tmp_path / "system", clock=lambda: NOW)
    application = ProjectApplication.create(
        tmp_path / "project",
        system=system,
        project_id="project.alpha",
        name="Alpha project",
        created_at=NOW,
        clock=lambda: NOW,
    )
    try:
        imported = application.sessions.import_bundle(
            external,
            transaction_id="tx.preflight-session",
            imported_by="expert.one",
        )
        application.system_execution.ensure_available(application.starter_scheme_id)
        service = application.preflight
        ready = service.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_version_id=application.starter_scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={
                "observed_peak_error": 1_000_000.0,
                "control_reversal_rate": 999_999.0,
                "physiology_value": -999_999.0,
            },
        )

        assert ready.report.technical_disposition is TechnicalDisposition.READY
        assert ready.report.synthetic_data is True
        assert ready.report.formal_run_authorized is False
        assert len(ready.report.locked_component_refs) > 20
        assert len(ready.lock.locked_operator_identities) > 0
        snapshot = service.build_snapshot(ready.report.preflight_id, run_id="run.preflight")
        payload = encode_canonical_json(snapshot.model_dump(mode="json"))
        assert str(application.project.root).encode() not in payload
        assert platform.node().encode() not in payload
        # Check process-specific field names rather than the decimal PID text: a short
        # PID can occur by chance inside one of the snapshot's hexadecimal hashes.
        assert b'"pid"' not in payload
        assert b'"process_id"' not in payload

        synchronized = service.synchronization_outcome(ready.report.preflight_id)
        assert synchronized.aligned_session is not None
        scheme = application.components.get_exact(
            ComponentKind.ASSESSMENT_SCHEME_VERSION,
            application.starter_scheme_id,
        )
        assert isinstance(scheme, AssessmentSchemeVersion)
        task = application.components.get_exact(
            ComponentKind.TASK_PROFILE_VERSION,
            scheme.task_profile.version_id,
        )
        assert isinstance(task, TaskProfileVersion)
        resolver = RuntimeSourceResolver(
            application.source_catalog,
            application.source_provider_registry,
            SourceResolutionContext(
                aligned_session=synchronized.aligned_session,
                task_profile=task,
                runtime_parameters={},
            ),
        )
        resolved = tuple(
            resolver.resolve(descriptor.source_id)
            for descriptor in application.source_catalog.descriptors()
        )
        assert all(item.status is SourceResolutionStatus.AVAILABLE for item in resolved)

        formal = service.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_version_id=application.starter_scheme_id,
            purpose=RunPurpose.ASSESSMENT,
            runtime_parameters={},
        )
        assert formal.report.technical_disposition is TechnicalDisposition.READY
        assert formal.report.formal_run_authorized is False
        authorization = next(
            diagnostic
            for diagnostic in formal.report.diagnostics
            if diagnostic.code == "run.assessment_not_authorized"
        )
        assert authorization.severity.value == "warning"
        assessment_snapshot = service.build_snapshot(
            formal.report.preflight_id,
            run_id="run.assessment-engineering",
        )
        assert assessment_snapshot.purpose is RunPurpose.ASSESSMENT

        manifest_path = (
            application.sessions.managed_bundle_path(imported.revision.session_revision_id)
            / "manifest.json"
        )
        original_manifest = manifest_path.read_bytes()
        manifest_path.write_bytes(original_manifest + b"\n")
        changed = service.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_version_id=application.starter_scheme_id,
            purpose=RunPurpose.SOFTWARE_TEST,
            runtime_parameters={},
        )
        assert changed.report.technical_disposition is TechnicalDisposition.BLOCKED
        assert "MANAGED_SESSION_CHANGED" in {
            diagnostic.code for diagnostic in changed.report.diagnostics
        }
        manifest_path.write_bytes(original_manifest)

        assert service.get(ready.report.preflight_id) == ready
    finally:
        application.close()
        system.close()
