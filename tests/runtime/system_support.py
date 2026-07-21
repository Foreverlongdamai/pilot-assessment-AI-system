from __future__ import annotations

from pathlib import Path

from pilot_assessment.persistence.database import Clock
from pilot_assessment.runtime import SystemApplication


def open_test_system(root: Path, *, clock: Clock) -> SystemApplication:
    return SystemApplication.open_or_create(
        root,
        model_library_id="model-library.test",
        clock=clock,
    )
