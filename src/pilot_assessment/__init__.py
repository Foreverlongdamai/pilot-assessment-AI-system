"""Core package for the Cranfield pilot assessment system."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tomllib import load


def _source_tree_version() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject.open("rb") as stream:
            value = load(stream)["project"]["version"]
    except (FileNotFoundError, KeyError, OSError, TypeError):
        return "0.0.0+source"
    return value if isinstance(value, str) and value else "0.0.0+source"


try:
    __version__ = version("pilot-assessment-system")
except PackageNotFoundError:
    # Portable releases intentionally execute backend/src directly and do not
    # install a second first-party wheel into private site-packages.
    __version__ = _source_tree_version()

__all__ = ["__version__"]
