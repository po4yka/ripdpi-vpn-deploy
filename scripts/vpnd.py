#!/usr/bin/env python3
"""Execute the checkout's Python operator CLI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vpnd/src"))
from vpnd.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
