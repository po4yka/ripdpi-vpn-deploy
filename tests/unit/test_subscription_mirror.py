"""The real rsync mirror must preserve configured local revocation state."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("mirror_renderer", REPO_ROOT / "scripts/check-templates-render.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.mark.parametrize("revoked_name", ["revoked", "revocations.txt", "local-state/revoked hashes"])
def test_pull_preserves_configured_revocations_and_known_hosts(tmp_path: Path, revoked_name: str) -> None:
    source, dest = tmp_path / "source", tmp_path / "destination"
    (source / "sub").mkdir(parents=True)
    (source / "sub/payload").write_text("new payload")
    (dest / "sub").mkdir(parents=True)
    (dest / "sub/stale").write_text("old payload")
    (dest / ".ssh").mkdir()
    known_hosts = dest / ".ssh/known_hosts"
    known_hosts.write_text("pinned synthetic host key")
    revoked = dest / revoked_name
    revoked.parent.mkdir(parents=True, exist_ok=True)
    revoked.write_text("synthetic revoked hash")
    variables = renderer.merge_render_vars()
    variables["subscription"].update({
        "subscription_dir": str(dest) + "/",
        "revoked_file": str(revoked),
        "mirror": {"backend": "rsync", "source": str(source) + "/"},
    })
    script = tmp_path / "mirror.sh"
    script.write_text(renderer.render_template(REPO_ROOT / "ansible/roles/subscription-host/templates/vpn-sub-mirror.sh.j2", variables))
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert revoked.read_text() == "synthetic revoked hash"
    assert known_hosts.read_text() == "pinned synthetic host key"
    assert (dest / "sub/payload").read_text() == "new payload"
    assert not (dest / "sub/stale").exists()
