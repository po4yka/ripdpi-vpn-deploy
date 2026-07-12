"""ci-fast and validate must not silently reduce their promised coverage."""

from pathlib import Path


def test_validate_checks_every_provider_and_ci_fast_has_no_tool_skips():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    ci = (root / ".github" / "workflows" / "ci.yml").read_text()
    for provider in ("upcloud", "hetzner", "vultr", "scaleway"):
        assert provider in makefile
    assert "skipped: ansible-playbook" not in makefile
    assert "skipped: cargo" not in makefile

    ci_fast = makefile.split("ci-fast:", 1)[1].split("\n\n# Union gate", 1)[0]
    for target in (
        "actionlint-check",
        "cloud-init-schema",
        "tf-test",
        "yamllint-check",
        "shellcheck",
        "vpnd-deny",
        "vpnd-msrv",
    ):
        assert f"$(MAKE) {target}" in ci_fast
    assert "python3 scripts/render-cloud-init-ci.py" in ci
