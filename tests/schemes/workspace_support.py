from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pilot_assessment.contracts.model_components import ComponentKind
from pilot_assessment.schemes.repository import (
    InMemorySchemeDraftRepository,
    InMemoryWorkspaceUnitOfWork,
)
from pilot_assessment.schemes.service import SchemeWorkspaceService
from tests.schemes.support import NOW, SchemeFixture


class FrozenClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class SequenceIdFactory:
    def __init__(self, *values: str) -> None:
        self.values = deque(values)
        self.requested_kinds: list[ComponentKind] = []

    def new_id(self, kind: ComponentKind) -> str:
        self.requested_kinds.append(kind)
        return self.values.popleft()


@dataclass(frozen=True, slots=True)
class WorkspaceFixture:
    service: SchemeWorkspaceService
    drafts: InMemorySchemeDraftRepository
    uow: InMemoryWorkspaceUnitOfWork


def build_workspace(
    fixture: SchemeFixture,
    *,
    ids: SequenceIdFactory | None = None,
    failure_hook: Callable[[str], None] | None = None,
) -> WorkspaceFixture:
    fixture.repository.add(fixture.scheme, recorded_at=NOW)
    drafts = InMemorySchemeDraftRepository(clock=FrozenClock().now)
    uow = InMemoryWorkspaceUnitOfWork(
        fixture.repository,
        drafts,
        failure_hook=failure_hook,
    )
    service = SchemeWorkspaceService(
        fixture.repository,
        drafts,
        uow,
        source_catalog=fixture.source_catalog,
        operator_registry=fixture.operator_registry,
        clock=FrozenClock(),
        ids=ids or SequenceIdFactory(),
    )
    return WorkspaceFixture(service=service, drafts=drafts, uow=uow)
