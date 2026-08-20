import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOLECULE_IMAGE = re.compile(
    r"(?P<name>ghcr\.io/po4yka/ripdpi-vpn-deploy/molecule-(?:debian13|ubuntu2404))@"
    r"sha256:(?P<digest>[0-9a-f]{64})"
)

EXPECTED_DIGESTS = {
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13": {
        "ca807cb2cbdf06021beb87a376005c78b63f11f718b32802e3b2b358c786380d"
    },
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404": {
        "c85d002450dc2ad94c21b05dd6410fb3d37c13365bc958fcd679d7cca5e7b90d"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    for molecule_file in (ROOT / "ansible").glob("**/molecule.yml"):
        for match in MOLECULE_IMAGE.finditer(molecule_file.read_text()):
            observed[match.group("name")].add(match.group("digest"))

    assert observed == EXPECTED_DIGESTS
