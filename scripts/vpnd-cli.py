#!/usr/bin/env python3
"""Execute the checkout's Python operator CLI."""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vpnd/src"))
if __name__ == "__main__":
    runpy.run_module("vpnd", run_name="__main__", alter_sys=True)
