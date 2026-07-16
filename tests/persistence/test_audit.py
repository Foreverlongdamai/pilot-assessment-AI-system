from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pilot_assessment.contracts.project import AuditEvent
from pilot_assessment.persistence.audit import AuditQuery, AuditRepository
from pilot_assessment.persistence.database import ProjectDatabase

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _event(
    event_id: str,
    *,
    occurred_at: datetime,
    subject_id: str,
    transaction_id: str | None,
) -> AuditEvent:
    return AuditEvent(
        audit_event_id=event_id,
        event_type="component.version.published",
        actor_id="expert.one",
        occurred_at=occurred_at,
        subject_kind="component_version",
        subject_id=subject_id,
        transaction_id=transaction_id,
        details={"content_hash": "a" * 64},
    )


def test_audit_is_append_only_filtered_stably_paginated_and_reopenable(tmp_path) -> None:
    path = tmp_path / "project.sqlite3"
    database = ProjectDatabase.connect(path, clock=lambda: NOW)
    repository = AuditRepository(database)
    events = (
        _event(
            "audit.b",
            occurred_at=NOW,
            subject_id="evidence.alpha.v1",
            transaction_id="tx.shared",
        ),
        _event(
            "audit.a",
            occurred_at=NOW,
            subject_id="evidence.alpha.v2",
            transaction_id="tx.shared",
        ),
        _event(
            "audit.c",
            occurred_at=NOW + timedelta(minutes=1),
            subject_id="evidence.beta.v1",
            transaction_id=None,
        ),
    )
    for event in events:
        repository.append(event)
    assert [event.audit_event_id for event in repository.list_events()] == [
        "audit.a",
        "audit.b",
        "audit.c",
    ]
    assert [
        event.subject_id for event in repository.list_events(AuditQuery(transaction_id="tx.shared"))
    ] == ["evidence.alpha.v2", "evidence.alpha.v1"]
    assert repository.list_events(limit=1, offset=1)[0].audit_event_id == "audit.b"
    database.close()

    reopened_database = ProjectDatabase.connect(path, clock=lambda: NOW)
    try:
        reopened = AuditRepository(reopened_database)
        assert reopened.get("audit.c") == events[2]
        assert len(reopened.list_events(AuditQuery(subject_kind="component_version"))) == 3
    finally:
        reopened_database.close()
