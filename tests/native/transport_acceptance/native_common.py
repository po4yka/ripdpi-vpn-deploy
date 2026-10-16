"""Reuse the canonical native adapters without a second configuration model."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/unit'))
spec = importlib.util.spec_from_file_location('four_transport_stack', ROOT / 'tests/integration/transport_destination_boundary/fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
