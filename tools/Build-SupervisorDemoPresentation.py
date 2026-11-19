"""Render the current CPT + compensation reports; old inference is retired."""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "examples" / "bayes-compensation-2026-09-23"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT)
    args = parser.parse_args()
    renderer = runpy.run_path(str(ROOT / "tools" / "Build-BayesCompensationDemo.py"))
    renderer["render_reports"](args.directory, renderer["read"](args.directory / "manifest.json"))
    (args.directory / "METHOD_CN.md").write_text(
        (ROOT / "docs/product/plans/2026-09-23-bayes-compensation.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    print(args.directory / "index.html")


if __name__ == "__main__":
    main()
