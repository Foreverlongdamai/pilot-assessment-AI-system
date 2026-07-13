from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
M4_FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "m4"
M4_RECIPE_PATH = M4_FIXTURE_ROOT / "m4-workflow-smoke-recipe-v0.1.json"
M4_BUILDER_PATH = REPOSITORY_ROOT / "tests" / "m4_support" / "fixture_builder.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module spec: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def m4_workflow_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert M4_RECIPE_PATH.is_file(), f"lightweight M4 recipe is not implemented: {M4_RECIPE_PATH}"
    assert M4_BUILDER_PATH.is_file(), (
        f"lightweight M4 builder is not implemented: {M4_BUILDER_PATH}"
    )
    builder = _load_module(M4_BUILDER_PATH, "m4_lightweight_fixture_builder")
    output_root = tmp_path_factory.mktemp("m4-workflow-smoke") / "bundle"
    return builder.build_fixture(
        M4_RECIPE_PATH,
        case_id="m4-workflow-smoke-v0.1",
        output_root=output_root,
    )
