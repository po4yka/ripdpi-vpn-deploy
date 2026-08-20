import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOLECULE_IMAGE = re.compile(
    r"(?P<name>geerlingguy/docker-ubuntu2404-ansible|"
    r"ghcr\.io/po4yka/ripdpi-vpn-deploy/molecule-debian13)@"
    r"sha256:(?P<digest>[0-9a-f]{64})"
)

EXPECTED_DIGESTS = {
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13": {
        "ca807cb2cbdf06021beb87a376005c78b63f11f718b32802e3b2b358c786380d"
    },
    "geerlingguy/docker-ubuntu2404-ansible": {
        "a92c929b640cd4e5cf73f67fd1e9d0466c58335449fdc37a889c0bb4bbf78e2e"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    for molecule_file in (ROOT / "ansible").glob("**/molecule.yml"):
        for match in MOLECULE_IMAGE.finditer(molecule_file.read_text()):
            observed[match.group("name")].add(match.group("digest"))

    assert observed == EXPECTED_DIGESTS
