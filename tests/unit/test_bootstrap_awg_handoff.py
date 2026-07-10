"""Day-1 bootstrap must not generate unrecoverable AWG client keys."""

from pathlib import Path


def test_bootstrap_defers_awg_peers_to_new_client_handoff():
    script = (Path(__file__).resolve().parents[2] / "scripts/bootstrap-secrets.sh").read_text()
    client_loop = script.split("for name in", 1)[1].split("# ---------------------------------------------------------------------------\n# AmneziaWG server", 1)[0]
    assert "wg genkey" not in client_loop
    assert "scripts/new-client.sh" in script
