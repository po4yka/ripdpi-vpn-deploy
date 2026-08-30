import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOLECULE_IMAGE = re.compile(
    r"(?P<name>ghcr\.io/po4yka/ripdpi-vpn-deploy/molecule-(?:debian13|ubuntu2404))@"
    r"sha256:(?P<digest>[0-9a-f]{64})"
)

EXPECTED_DIGESTS = {
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13": {
        "ad92a972bfd235e4577bf6b56e9ab82d5ab259d6a3e627f6ebfab7c2b2bfeb7e"
    },
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404": {
        "48e1ab7caa1e28148148576cd2f15e46fcd9d44601125bbce7f3056306f40cf1"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    for molecule_file in (ROOT / "ansible").glob("**/molecule.yml"):
        for match in MOLECULE_IMAGE.finditer(molecule_file.read_text()):
            observed[match.group("name")].add(match.group("digest"))

    assert observed == EXPECTED_DIGESTS
