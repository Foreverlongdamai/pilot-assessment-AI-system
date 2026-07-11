from importlib.metadata import version

import pilot_assessment


def test_package_version_is_single_sourced() -> None:
    assert pilot_assessment.__version__ == "0.1.0"
    assert version("pilot-assessment-system") == pilot_assessment.__version__


def test_m2_runtime_dependencies_are_importable() -> None:
    import PIL
    import polars

    assert polars.__version__
    assert PIL.__version__
