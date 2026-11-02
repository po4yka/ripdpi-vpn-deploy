"""The image scan must include every pinned observer architecture."""
import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_scan_matrix_includes_production_images_and_deduplicates_test_images(tmp_path):
    spec = importlib.util.spec_from_file_location("list_container_images", ROOT / "scripts/list-container-images.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    role = tmp_path / "ansible/roles/observability_kuma/defaults"
    role.mkdir(parents=True)
    observer = {"image_repository": "example.invalid/observer", "image_digests": {"x86_64": "sha256:" + "a" * 64, "aarch64": "sha256:" + "b" * 64}}
    (role / "main.yml").write_text(yaml.safe_dump({"observability_kuma": observer}))
    for name in ("one", "two"):
        scenario = tmp_path / "ansible/roles" / name
        scenario.mkdir()
        (scenario / "molecule.yml").write_text("platforms:\n  - name: target\n    image: example.invalid/test:1\n")
    stack = tmp_path / "ansible/molecule/full-stack"
    stack.mkdir(parents=True)
    (stack / "molecule.yml").write_text("platforms:\n  - name: target\n    image: example.invalid/stack:1\n")
    assert module.image_references(tmp_path) == [
        {"image": "example.invalid/stack:1", "category": "trivy-example.invalid/stack:1"},
        {"image": "example.invalid/test:1", "category": "trivy-example.invalid/test:1"},
        {"image": "example.invalid/observer@sha256:" + "b" * 64, "category": "trivy-observability-kuma-aarch64"},
        {"image": "example.invalid/observer@sha256:" + "a" * 64, "category": "trivy-observability-kuma-x86_64"},
    ]



def test_cli_emits_the_array_required_by_the_workflow_matrix():
    import json
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(ROOT / "scripts/list-container-images.py")], capture_output=True, text=True, check=True)
    images = json.loads(result.stdout)
    assert isinstance(images, list)
    assert len(images) >= 2
    assert all(set(image) == {"image", "category"} and all(isinstance(v, str) and v for v in image.values()) for image in images)
    assert len({image["category"] for image in images}) == len(images)
