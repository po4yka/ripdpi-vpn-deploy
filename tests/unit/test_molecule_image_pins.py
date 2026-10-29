import os
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MOLECULE_IMAGE = re.compile(
    r"(?P<name>ghcr\.io/po4yka/ripdpi-vpn-deploy/molecule-(?:debian13|ubuntu2404))@"
    r"sha256:(?P<digest>[0-9a-f]{64})"
)

EXPECTED_DIGESTS = {
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13": {
        "b3f2db18b8a6f53891196f7a166e36896f9200357d453a0129be09fa9bf94e84"
    },
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404": {
        "c9277039a651a9a211ab0d1676c7001c78cf95a5ea83d46e1542c386cfe6f040"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    consumers = [
        *(ROOT / "ansible").glob("**/molecule.yml"),
        *(ROOT / ".github/workflows").glob("*.yml"),
    ]
    for consumer in consumers:
        for match in MOLECULE_IMAGE.finditer(consumer.read_text()):
            observed[match.group("name")].add(match.group("digest"))

    assert observed == EXPECTED_DIGESTS


def test_image_scan_sarif_category_survives_a_digest_repin(tmp_path: Path) -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/image-scan.yml").read_text())
    steps = {step.get("name"): step for step in workflow["jobs"]["scan"]["steps"]}
    derive = steps["Derive digest-free SARIF category"]
    upload = steps["Upload Trivy SARIF results"]
    assert (
        upload["with"]["category"] == "${{ steps.%s.outputs.category }}" % derive["id"]
    )

    categories = set()
    for digest in (next(iter(digests)) for digests in EXPECTED_DIGESTS.values()):
        for image in EXPECTED_DIGESTS:
            output = tmp_path / "github-output"
            subprocess.run(
                ["bash", "-c", derive["run"]],
                check=True,
                env={
                    **os.environ,
                    "IMAGE": f"{image}@sha256:{digest}",
                    "GITHUB_OUTPUT": str(output),
                },
            )
            categories.add(output.read_text())
            output.unlink()

    assert categories == {f"category=trivy-{image}\n" for image in EXPECTED_DIGESTS}
