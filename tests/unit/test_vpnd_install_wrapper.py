"""Exercise the download/checksum/provenance boundary before installer execution."""

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("verification_status,corrupt", [(0, False), (23, False), (0, True)])
def test_shell_installer_requires_expected_provenance(tmp_path, verification_status, corrupt):
    fixture = tmp_path / "release.tar.gz"
    payload = b"import os, pathlib\npathlib.Path(os.environ['INSTALL_RECEIPT']).write_text('executed')\n"
    with tarfile.open(fixture, "w:gz") as archive:
        member = tarfile.TarInfo("install.py")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "python3").symlink_to(sys.executable)
    curl = binary / "curl"
    curl.write_text(
        f"#!{sys.executable}\n"
        "import hashlib, os, pathlib, shutil, sys\n"
        "target = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "source = pathlib.Path(os.environ['RELEASE_FIXTURE'])\n"
        "if target.name == 'SHA256SUMS':\n"
        "    digest = '0' * 64 if os.environ['CORRUPT'] == '1' else hashlib.sha256(source.read_bytes()).hexdigest()\n"
        "    target.write_text(digest + '  ' + os.environ['ASSET'] + '\\n')\n"
        "else: shutil.copyfile(source, target)\n"
    )
    gh = binary / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['VERIFY_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        "expected = ['--repo', 'po4yka/ripdpi-vpn-deploy', '--signer-workflow',\n"
        "            'po4yka/ripdpi-vpn-deploy/.github/workflows/release-vpnd.yml']\n"
        "assert sys.argv[1:3] == ['attestation', 'verify']\n"
        "assert sys.argv[4:] == expected\n"
        "sys.exit(int(os.environ['VERIFY_STATUS']))\n"
    )
    curl.chmod(0o755)
    gh.chmod(0o755)
    system = {"Darwin": "apple-darwin", "Linux": "unknown-linux-gnu"}[platform.system()]
    arch = {"x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}[platform.machine()]
    receipt = tmp_path / "installed"
    verify_log = tmp_path / "verify.json"
    environment = {key: value for key, value in os.environ.items()
                   if key != "VPND_SKIP_ATTESTATION"}
    environment.update(PATH=f"{binary}{os.pathsep}{environment['PATH']}", ALLOW_ROOT="1",
                       RELEASE_FIXTURE=str(fixture), ASSET=f"vpnd-{arch}-{system}.tar.gz",
                       CORRUPT=str(int(corrupt)), VERIFY_STATUS=str(verification_status),
                       INSTALL_RECEIPT=str(receipt), VERIFY_LOG=str(verify_log),
                       PREFIX=str(tmp_path / "prefix"))
    result = subprocess.run(["bash", str(ROOT / "scripts/install-vpnd.sh")],
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == (1 if corrupt else verification_status), result.stderr
    assert receipt.exists() is (not corrupt and verification_status == 0)
    assert verify_log.exists() is not corrupt
    if not corrupt:
        assert Path(json.loads(verify_log.read_text())[2]).name == environment["ASSET"]
