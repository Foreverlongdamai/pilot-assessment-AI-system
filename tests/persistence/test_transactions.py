from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pilot_assessment.contracts.project import AuditEvent
from pilot_assessment.persistence.audit import AuditRepository
from pilot_assessment.persistence.database import ProjectDatabase
from pilot_assessment.persistence.transactions import (
    IdempotencyStore,
    MutationResult,
    TransactionReuseMismatchError,
    transaction_request_hash,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def _event(event_id: str, transaction_id: str) -> AuditEvent:
    return AuditEvent(
        audit_event_id=event_id,
        event_type="scheme.draft.changed",
        actor_id="expert.one",
        occurred_at=NOW,
        subject_kind="scheme_draft",
        subject_id="draft.alpha",
        transaction_id=transaction_id,
        details={"graph_version": 1},
    )


def test_request_hash_is_canonical_and_transaction_replay_is_exactly_once(tmp_path) -> None:
    assert transaction_request_hash("graph.operations.apply", {"b": 2, "a": 1}) == (
        transaction_request_hash("graph.operations.apply", {"a": 1, "b": 2})
    )
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    database.execute("CREATE TABLE mutation_probe (value TEXT NOT NULL)")
    audit = AuditRepository(database)
    store = IdempotencyStore(database, audit, clock=lambda: NOW)
    calls = 0

    def mutation(connection):
        nonlocal calls
        calls += 1
        connection.execute("INSERT INTO mutation_probe(value) VALUES ('once')")
        return MutationResult(
            response_payload={"draft_id": "draft.alpha", "graph_version": 1},
            audit_event=_event("audit.tx-alpha", "tx.alpha"),
        )

    try:
        first = store.execute(
            transaction_id="tx.alpha",
            method="graph.operations.apply",
            params={"draft_id": "draft.alpha", "operation": {"type": "SetOutputNodes"}},
            mutation=mutation,
        )
        replay = store.execute(
            transaction_id="tx.alpha",
            method="graph.operations.apply",
            params={"operation": {"type": "SetOutputNodes"}, "draft_id": "draft.alpha"},
            mutation=mutation,
        )

        assert first.replayed is False
        assert replay.replayed is True
        assert replay.receipt == first.receipt
        assert calls == 1
        assert database.fetchone("SELECT COUNT(*) FROM mutation_probe")[0] == 1
        assert len(audit.list_events()) == 1
        with pytest.raises(TransactionReuseMismatchError):
            store.execute(
                transaction_id="tx.alpha",
                method="graph.operations.apply",
                params={"draft_id": "draft.beta"},
                mutation=mutation,
            )
        assert calls == 1
    finally:
        database.close()


def test_failed_mutation_leaves_no_prepared_receipt_or_audit_and_can_retry(tmp_path) -> None:
    database = ProjectDatabase.connect(tmp_path / "project.sqlite3", clock=lambda: NOW)
    database.execute("CREATE TABLE mutation_probe (value TEXT NOT NULL)")
    audit = AuditRepository(database)
    store = IdempotencyStore(database, audit, clock=lambda: NOW)

    def fail(connection):
        connection.execute("INSERT INTO mutation_probe(value) VALUES ('rollback')")
        raise RuntimeError("injected mutation failure")

    try:
        with pytest.raises(RuntimeError, match="injected"):
            store.execute(
                transaction_id="tx.retry",
                method="session.import",
                params={"source": "bundle.alpha"},
                mutation=fail,
            )
        assert database.fetchone("SELECT COUNT(*) FROM mutation_probe")[0] == 0
        assert database.fetchone("SELECT COUNT(*) FROM idempotency_transactions")[0] == 0
        assert audit.list_events() == ()

        success = store.execute(
            transaction_id="tx.retry",
            method="session.import",
            params={"source": "bundle.alpha"},
            mutation=lambda connection: MutationResult(
                response_payload={"session_revision_id": "session.alpha.rev1"},
                audit_event=_event("audit.tx-retry", "tx.retry"),
            ),
        )
        assert success.replayed is False
        assert success.receipt.response_payload == {"session_revision_id": "session.alpha.rev1"}
    finally:
        database.close()
