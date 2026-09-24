import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOLECULE_IMAGE = re.compile(
    r"(?P<name>ghcr\.io/po4yka/ripdpi-vpn-deploy/molecule-(?:debian13|ubuntu2404))@"
    r"sha256:(?P<digest>[0-9a-f]{64})"
)

EXPECTED_DIGESTS = {
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-debian13": {
        "5c50bf51be9ac3bef7a6795f3e52dfebefa0767bf3c475226222be0fc02a2662"
    },
    "ghcr.io/po4yka/ripdpi-vpn-deploy/molecule-ubuntu2404": {
        "aac217bcf54e81524154dfab03e070fb63e83d0a86fb92bff94adf273bd9b552"
    },
}


def test_molecule_base_images_use_the_verified_scan_clean_digests() -> None:
    observed = {name: set() for name in EXPECTED_DIGESTS}

    for molecule_file in (ROOT / "ansible").glob("**/molecule.yml"):
        for match in MOLECULE_IMAGE.finditer(molecule_file.read_text()):
            observed[match.group("name")].add(match.group("digest"))

    assert observed == EXPECTED_DIGESTS
