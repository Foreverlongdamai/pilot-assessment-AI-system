"""Run the standalone scene calculator over standard input/output."""

from __future__ import annotations

import logging
import sys

from pilot_assessment.scene_assessment.server import serve


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
