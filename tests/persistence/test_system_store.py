from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from pilot_assessment.persistence.system import (
    SYSTEM_DATABASE_NAME,
    SYSTEM_LOCATOR_NAME,
    SystemStore,
    SystemStoreIntegrityError,
    SystemStoreLockedError,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
SEED_HASH = "a" * 64


def _create(root, *, clock=lambda: NOW) -> SystemStore:
    return SystemStore.create(
        root,
        model_library_id="model-library.alpha",
        created_from_product_version="0.1.0",
        starter_seed_id="starter.hover.package.0.1.0",
        starter_seed_hash=SEED_HASH,
        created_at=NOW,
        clock=clock,
    )


def test_system_store_create_close_move_and_reopen_is_relative(tmp_path) -> None:
    original = tmp_path / "system"
    store = _create(original)
    assert store.model_edit_root == original.resolve() / "staging" / "model-edit"
    locator = json.loads((original / SYSTEM_LOCATOR_NAME).read_text(encoding="utf-8"))
    assert locator["database_path"] == SYSTEM_DATABASE_NAME
    assert "absolute_root" not in locator
    assert store.database.fetchone("SELECT COUNT(*) FROM project_metadata")[0] == 0
    store.close()

    moved = tmp_path / "copy" / "system"
    moved.parent.mkdir()
    shutil.move(original, moved)
    reopened = SystemStore.open(moved, clock=lambda: NOW + timedelta(minutes=1))
    try:
        assert reopened.descriptor.model_library_id == "model-library.alpha"
        assert reopened.recovery_diagnostics == ()
    finally:
        reopened.close()

    database_bytes = (moved / SYSTEM_DATABASE_NAME).read_bytes()
    assert str(original.resolve()).encode() not in database_bytes
    assert str(moved.resolve()).encode() not in database_bytes


def test_system_store_rejects_a_second_writer(tmp_path) -> None:
    store = _create(tmp_path / "system")
    try:
        with pytest.raises(SystemStoreLockedError):
            SystemStore.open(store.root, clock=lambda: NOW)
    finally:
        store.close()

    reopened = SystemStore.open(store.root, clock=lambda: NOW)
    reopened.close()


def test_system_store_detects_locator_database_identity_mismatch(tmp_path) -> None:
    store = _create(tmp_path / "system")
    store.close()
    raw = sqlite3.connect(store.root / SYSTEM_DATABASE_NAME)
    try:
        raw.execute(
            "UPDATE system_metadata SET model_library_id = ? WHERE singleton = 1",
            ("model-library.changed",),
        )
        raw.commit()
    finally:
        raw.close()

    with pytest.raises(SystemStoreIntegrityError, match="identity disagree"):
        SystemStore.open(store.root, clock=lambda: NOW)


def test_open_or_create_reuses_existing_store(tmp_path) -> None:
    root = tmp_path / "system"
    created = SystemStore.open_or_create(
        root,
        model_library_id="model-library.alpha",
        created_from_product_version="0.1.0",
        starter_seed_id="starter.hover.package.0.1.0",
        starter_seed_hash=SEED_HASH,
        clock=lambda: NOW,
    )
    created.close()

    opened = SystemStore.open_or_create(
        root,
        created_from_product_version="9.9.9",
        starter_seed_id="different.seed",
        starter_seed_hash="b" * 64,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    try:
        assert opened.descriptor.model_library_id == "model-library.alpha"
        assert opened.descriptor.created_from_product_version == "0.1.0"
        assert opened.descriptor.starter_seed_hash == SEED_HASH
    finally:
        opened.close()
