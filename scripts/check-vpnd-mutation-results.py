#!/usr/bin/env python3
"""Distinguish completed mutation findings from partial or failed execution."""

import json
import sys
from pathlib import Path

COUNTERS = (
    "killed",
    "survived",
    "no_tests",
    "skipped",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
)


def verdict(path):
    try:
        document = json.loads(path.read_text())
        if (
            not isinstance(document, dict)
            or set(document) != {*COUNTERS, "total"}
            or any(type(value) is not int or value < 0 for value in document.values())
            or document["total"] == 0
            or sum(document[name] for name in COUNTERS) != document["total"]
            or any(
                document[name]
                for name in COUNTERS
                if name not in {"killed", "survived"}
            )
        ):
            raise ValueError("incomplete mutation inventory")
    except (OSError, ValueError, TypeError):
        print(
            "Mutation results are missing, invalid, empty or incomplete",
            file=sys.stderr,
        )
        return 1
    print(
        f"Mutation results: killed={document['killed']}, survived={document['survived']}, total={document['total']}"
    )
    return 2 if document["survived"] else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Expected one mutation inventory path")
    raise SystemExit(verdict(Path(sys.argv[1])))
