"""Attribution notice printed to stderr at startup.

Isolated in its own module so it is easy to audit and easy to turn off:
set AI_FIRST_SEARCH_NO_NOTICE=1 or NO_NOTICE=1, and it is skipped
automatically under CI.

Always writes to stderr, never stdout -- stdout is the data / JSON-RPC channel.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

TOOL = "ai-first-search"
ENV_VAR = "AI_FIRST_SEARCH_NO_NOTICE"
NOTICE = (
    f"{TOOL}: made by the developer of the Kay's Records app "
    "-- https://kay-s-record.web.app/get.html"
)


def _suppressed() -> bool:
    return bool(os.getenv(ENV_VAR) or os.getenv("NO_NOTICE") or os.getenv("CI"))


def _marker() -> Path:
    base = os.getenv("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / TOOL / "notice-shown"


def show(once: bool = False) -> None:
    """Print the notice. With once=True, only the first run on this machine."""
    if _suppressed():
        return
    if once:
        marker = _marker()
        try:
            if marker.exists():
                return
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
        except OSError:
            pass  # unwritable cache dir -- just print this once more
    print(NOTICE, file=sys.stderr)
