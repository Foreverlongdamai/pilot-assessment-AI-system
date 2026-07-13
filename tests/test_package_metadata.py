from importlib.metadata import requires, version
from importlib.resources import as_file, files
from pathlib import Path

import pilot_assessment


def test_package_version_is_single_sourced() -> None:
    assert pilot_assessment.__version__ == "0.1.0"
    assert version("pilot-assessment-system") == pilot_assessment.__version__


def test_m2_runtime_dependencies_are_importable() -> None:
    import PIL
    import polars

    assert polars.__version__
    assert PIL.__version__


def test_m4_runtime_constraints_are_published_in_package_metadata() -> None:
    declared = set(requires("pilot-assessment-system") or ())

    assert {
        "numpy>=2.3.4,<2.4",
        "rfc8785>=0.1.4,<0.2",
        "scipy>=1.17,<1.18",
    } <= declared


def test_m3_temporal_binding_catalog_is_a_packaged_resource() -> None:
    resource = files("pilot_assessment.synchronization.profile_data").joinpath(
        "m3-temporal-bindings-0.1.json"
    )
    with as_file(resource) as path:
        assert Path(path).is_file()
