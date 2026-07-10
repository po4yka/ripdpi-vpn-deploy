"""ci-fast and validate must not silently reduce their promised coverage."""

from pathlib import Path


def test_validate_checks_every_provider_and_ci_fast_has_no_tool_skips():
    makefile = (Path(__file__).resolve().parents[2] / "Makefile").read_text()
    for provider in ("upcloud", "hetzner", "vultr"):
        assert provider in makefile
    assert "skipped: ansible-playbook" not in makefile
    assert "skipped: cargo" not in makefile
