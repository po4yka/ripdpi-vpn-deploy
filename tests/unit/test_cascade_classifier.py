"""Tri-state classifier contract over the unchanged V2Ray geoip.dat format."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = ROOT / "scripts" / "cascade-classifier.py"


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        encoded.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(encoded)


def _field(number: int, payload: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def _synthetic_geoip_dat() -> bytes:
    # Hand-built GeoIPList protobuf: RU contains one documentation-only IPv4 /24.
    cidr = _field(1, bytes([192, 0, 2, 0])) + _varint(2 << 3) + _varint(24)
    geoip = _field(1, b"RU") + _field(2, cidr)
    return _field(1, geoip)


def _run(dataset: Path, destination: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLASSIFIER), "--dataset", str(dataset), "--destination", destination],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def _check_dataset(dataset: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLASSIFIER), "--dataset", str(dataset), "--check-dataset"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_ru_destination_is_ru(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_synthetic_geoip_dat())

    result = _run(dataset, "192.0.2.7")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "ru"


def test_non_ru_destination_is_foreign(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_synthetic_geoip_dat())

    result = _run(dataset, "198.51.100.9")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "foreign"


def test_unknown_destination_never_falls_through_to_foreign(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_synthetic_geoip_dat())

    result = _run(dataset, "not-an-ip")

    assert result.returncode != 0
    assert json.loads(result.stdout)["state"] == "dataset-unavailable"


def test_missing_dataset_hard_blocks(tmp_path: Path) -> None:
    result = _run(tmp_path / "missing.dat", "192.0.2.7")

    assert result.returncode != 0
    assert json.loads(result.stdout)["state"] == "dataset-unavailable"


def test_forced_empty_dataset_hard_blocks(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(b"")

    result = _run(dataset, "192.0.2.7")

    assert result.returncode != 0
    assert json.loads(result.stdout)["state"] == "dataset-unavailable"


def test_populated_dataset_preflight_is_ready(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(_synthetic_geoip_dat())

    result = _check_dataset(dataset)

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"state": "ready"}


def test_empty_dataset_preflight_hard_blocks(tmp_path: Path) -> None:
    dataset = tmp_path / "geoip.dat"
    dataset.write_bytes(b"")

    result = _check_dataset(dataset)

    assert result.returncode != 0
    assert json.loads(result.stdout)["state"] == "dataset-unavailable"
