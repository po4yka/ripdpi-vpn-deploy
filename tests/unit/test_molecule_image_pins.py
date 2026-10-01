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
        "3eaa352852855158e752c94f2ea9b47aa03ba014d5ea3e51c06e74c45a57ad08"
    },
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404": {
        "e9dfdf3cc37d8d098ef7e036e716abba78980333522ccbf7504a79189755a267"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    for molecule_file in (ROOT / "ansible").glob("**/molecule.yml"):
        for match in MOLECULE_IMAGE.finditer(molecule_file.read_text()):
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
