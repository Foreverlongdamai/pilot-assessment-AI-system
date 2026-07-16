"""Durable, project-scoped persistence adapters for the local runtime."""

from pilot_assessment.persistence.database import (
    DatabaseIntegrityError,
    DatabaseMigrationError,
    DatabaseTransactionError,
    ProjectDatabase,
    decode_canonical_json,
    encode_canonical_json,
)
from pilot_assessment.persistence.project import (
    PROJECT_DATABASE_NAME,
    PROJECT_DIRECTORY_NAMES,
    PROJECT_LOCATOR_NAME,
    ProjectAlreadyExistsError,
    ProjectFormatError,
    ProjectIntegrityError,
    ProjectStore,
)

__all__ = [
    "DatabaseIntegrityError",
    "DatabaseMigrationError",
    "DatabaseTransactionError",
    "PROJECT_DATABASE_NAME",
    "PROJECT_DIRECTORY_NAMES",
    "PROJECT_LOCATOR_NAME",
    "ProjectAlreadyExistsError",
    "ProjectDatabase",
    "ProjectFormatError",
    "ProjectIntegrityError",
    "ProjectStore",
    "decode_canonical_json",
    "encode_canonical_json",
]
