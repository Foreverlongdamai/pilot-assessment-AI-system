"""Durable, project-scoped persistence adapters for the local runtime."""

from pilot_assessment.persistence.audit import AuditQuery, AuditRepository
from pilot_assessment.persistence.database import (
    DatabaseIntegrityError,
    DatabaseMigrationError,
    DatabaseTransactionError,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.draft_repository import (
    SqliteSchemeDraftRepository,
    SqliteWorkspaceUnitOfWork,
)
from pilot_assessment.persistence.model_repository import SqliteComponentLibraryRepository
from pilot_assessment.persistence.project import (
    PROJECT_DATABASE_NAME,
    PROJECT_DIRECTORY_NAMES,
    PROJECT_LOCATOR_NAME,
    ProjectAlreadyExistsError,
    ProjectFormatError,
    ProjectIntegrityError,
    ProjectStore,
)
from pilot_assessment.persistence.transactions import (
    IdempotencyResult,
    IdempotencyStore,
    MutationResult,
    TransactionReuseMismatchError,
    transaction_request_hash,
)

__all__ = [
    "DatabaseIntegrityError",
    "DatabaseMigrationError",
    "DatabaseTransactionError",
    "AuditQuery",
    "AuditRepository",
    "PROJECT_DATABASE_NAME",
    "PROJECT_DIRECTORY_NAMES",
    "PROJECT_LOCATOR_NAME",
    "ProjectAlreadyExistsError",
    "ProjectDatabase",
    "ProjectFormatError",
    "ProjectIntegrityError",
    "ProjectStore",
    "IdempotencyResult",
    "IdempotencyStore",
    "MutationResult",
    "SqliteComponentLibraryRepository",
    "SqliteSchemeDraftRepository",
    "SqliteWorkspaceUnitOfWork",
    "TransactionReuseMismatchError",
    "decode_canonical_json",
    "encode_canonical_json",
    "transaction_request_hash",
]
