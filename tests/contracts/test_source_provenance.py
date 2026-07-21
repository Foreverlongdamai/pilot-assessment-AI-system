from __future__ import annotations

from pydantic import ValidationError

from pilot_assessment.contracts.source_provenance import SourceChangeSummary


def test_source_change_summary_requires_canonical_unique_paths() -> None:
    value = SourceChangeSummary(
        added=("backend/src/pilot_assessment/a.py",),
        modified=("backend/src/pilot_assessment/b.py",),
    )

    assert value.added == ("backend/src/pilot_assessment/a.py",)

    try:
        SourceChangeSummary(
            added=("backend/src/pilot_assessment/B.py",),
            modified=("backend/src/pilot_assessment/b.py",),
        )
    except ValidationError:
        pass
    else:  # pragma: no cover - contract guard
        raise AssertionError("case-insensitive duplicate path must be rejected")
