from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pilot_assessment.contracts.system import SystemDescriptor

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
SEED_HASH = "a" * 64


def test_system_descriptor_is_strict_frozen_and_portable() -> None:
    descriptor = SystemDescriptor(
        model_library_id="model-library.alpha",
        format_version="0.1.0",
        created_from_product_version="0.1.0",
        starter_seed_id="starter.hover.package.0.1.0",
        starter_seed_hash=SEED_HASH,
        created_at=NOW,
    )

    assert descriptor.contract_id == "system-descriptor"
    assert descriptor.model_dump(mode="json")["created_at"] == "2026-07-21T12:00:00Z"
    with pytest.raises(ValidationError):
        SystemDescriptor.model_validate({**descriptor.model_dump(), "absolute_root": "C:/app"})
    with pytest.raises(ValidationError):
        descriptor.model_library_id = "changed"  # type: ignore[misc]
