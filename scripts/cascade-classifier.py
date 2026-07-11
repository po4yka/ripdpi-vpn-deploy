#!/usr/bin/env python3
"""Classify one destination against the unchanged V2Ray geoip.dat contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cascade_classifier_lib import DatasetUnavailable, classify, load_ru_networks


DATASET_UNAVAILABLE_EXIT = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--destination")
    mode.add_argument("--check-dataset", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check_dataset:
            load_ru_networks(args.dataset)
            result = {"state": "ready"}
        else:
            result = classify(args.dataset, args.destination)
    except DatasetUnavailable as exc:
        print(json.dumps({"reason": str(exc), "state": "dataset-unavailable"}, sort_keys=True))
        return DATASET_UNAVAILABLE_EXIT
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
