"""Shim: portal API client lives in the repo root. Keep CLI path working."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from portal_api_client import *  # noqa: F401,F403
from portal_api_client import main

if __name__ == "__main__":
    raise SystemExit(main())
