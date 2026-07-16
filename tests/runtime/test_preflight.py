from __future__ import annotations

import os
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path

from pilot_assessment.contracts.run import (
    RunPurpose,
    TechnicalDisposition,
)
from pilot_assessment.persistence.database import encode_canonical_json
from pilot_assessment.runtime import ProjectApplication
from pilot_assessment.runtime.preflight import RunPreflightService

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def test_preflight_locks_dynamic_closure_allows_bad_performance_and_blocks_formal_use(
    tmp_path: Path,
    m4_workflow_bundle: Path,
) -> None:
    external = tmp_path / "external-bundle"
    shutil.copytree(m4_workflow_bundle, external)
    application = ProjectApplication.create(
        tmp_path / "project",
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
        service = RunPreflightService(
            application.project.database,
            application.components,
            application.sessions,
            source_catalog=application.source_catalog,
            operator_registry=application.operator_registry,
            clock=lambda: NOW,
        )
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
        assert str(os.getpid()).encode() not in payload

        formal = service.prepare(
            session_revision_id=imported.revision.session_revision_id,
            scheme_version_id=application.starter_scheme_id,
            purpose=RunPurpose.ASSESSMENT,
            runtime_parameters={},
        )
        assert formal.report.technical_disposition is TechnicalDisposition.BLOCKED
        assert "run.assessment_not_authorized" in {
            diagnostic.code for diagnostic in formal.report.diagnostics
        }

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
