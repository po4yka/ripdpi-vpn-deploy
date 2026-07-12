"""ci-fast and validate must not silently reduce their promised coverage."""

import tomllib
from pathlib import Path


def test_validate_checks_every_provider_and_ci_fast_has_no_tool_skips():
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text()
    ci = (root / ".github" / "workflows" / "ci.yml").read_text()
    mise_text = (root / "mise.toml").read_text()
    mise = tomllib.loads(mise_text)
    tools = mise["tools"]
    assert tools["actionlint"] == "1.7.12"
    assert tools["age"] == "1.3.1"
    assert tools["bats"] == "1.13.0"
    assert tools["cargo:cargo-deny"] == {"version": "0.19.0", "locked": True}
    assert tools["jq"] == "1.8.2"
    assert tools["shellcheck"] == "0.11.0"
    assert tools["sops"] == "3.13.2"
    assert mise_text.index('rust = "1.96.0"') < mise_text.index('"cargo:cargo-deny"')

    assert "bootstrap-dev" in makefile.split(".PHONY:", 1)[1].split("\n\nhelp:", 1)[0]
    assert "bootstrap-dev              Install pinned dev tools" in makefile
    bootstrap = makefile.split("bootstrap-dev:", 1)[1].split("\n\ncheck-prereqs:", 1)[0]
    operations = (
        "mise install --jobs=1",
        "mise exec -- $(MAKE) install-hooks",
        "mise exec -- rustup toolchain install 1.88.0 --profile minimal",
        "mise exec -- $(MAKE) check-prereqs CI_PARITY=1",
    )
    assert all(operation in bootstrap for operation in operations)
    assert [bootstrap.index(operation) for operation in operations] == sorted(
        bootstrap.index(operation) for operation in operations
    )

    prereqs = makefile.split("check-prereqs:", 1)[1].split("\n\ninit:", 1)[0]
    for tool in (
        "terraform",
        "ansible",
        "ansible-playbook",
        "ansible-lint",
        "sops",
        "age",
        "gitleaks",
        "jq",
        "openssl",
        "ssh",
        "python3",
        "actionlint",
        "cloud-init",
        "shellcheck",
        "bats",
        "cargo-deny",
        "cargo",
        "yamllint",
    ):
        assert tool in prereqs
    for module in ("yaml", "jinja2", "jsonschema", "pytest"):
        assert f"import {module}" in prereqs or module in prereqs
    assert "cargo +1.88.0 --version" in prereqs
    assert "missing=0" in prereqs and "missing=1" in prereqs
    assert "Ubuntu VM/environment or CI (never skip it)" in prereqs
    assert "exit 1; };" not in prereqs
    for provider in ("upcloud", "hetzner", "vultr"):
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
