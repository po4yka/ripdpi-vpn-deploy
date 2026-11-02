#!/usr/bin/env python3
"""List test and deployed observer image references for the image scan matrix."""
from pathlib import Path
import json

import yaml


def image_references(root: Path) -> list[dict[str, str]]:
    images = set()
    for base in (root / "ansible/roles", root / "ansible/molecule"):
        for path in base.rglob("molecule.yml"):
            data = yaml.safe_load(path.read_text()) or {}
            for platform in data.get("platforms", []):
                image = platform.get("image")
                if isinstance(image, str) and image:
                    images.add(image)
    path = root / "ansible/roles/observability_kuma/defaults/main.yml"
    observer = yaml.safe_load(path.read_text())["observability_kuma"]
    matrix = [{"image": image, "category": "trivy-" + image.split("@sha256:")[0]}
              for image in sorted(images)]
    for architecture, digest in sorted(observer["image_digests"].items()):
        matrix.append({"image": observer["image_repository"] + "@" + digest,
                       "category": "trivy-observability-kuma-" + architecture})
    return matrix


if __name__ == "__main__":
    print(json.dumps(image_references(Path(__file__).resolve().parents[1])))
