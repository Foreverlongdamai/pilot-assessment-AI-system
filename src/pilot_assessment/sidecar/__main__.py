"""Launch the local JSON-RPC sidecar over binary stdin/stdout."""

from __future__ import annotations

import logging
import sys

from pilot_assessment.sidecar.server import serve


def main() -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
