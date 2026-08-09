"""The local and hosted zizmor gates must share one exact offline contract."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.29.0"
SHA256 = "dd96df044a6e8538d5f423790f453bdd03d49e5b2bcc38214acc41a2f1297839"


def test_mise_and_make_pin_one_strict_offline_zizmor_gate():
    mise = (ROOT / "mise.toml").read_text()
    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("zizmor-check:", 1)[1].split(
        "\n\ncloud-init-schema:", 1
    )[0]

    assert f'"pipx:zizmor" = "{VERSION}"' in mise
    assert f"ZIZMOR_VERSION := {VERSION}" in makefile
    assert 'test "$$(zizmor --version)" = "zizmor $(ZIZMOR_VERSION)"' in target
    for flag in (
        "--offline",
        "--strict-collection",
        "--no-config",
        "--persona=regular",
        '--format="$${ZIZMOR_FORMAT:-plain}"',
        "--collect=workflows",
        "--collect=actions",
        "--collect=dependabot",
        "--collect=pre-commit",
    ):
        assert flag in target
    assert ".github .pre-commit-config.yaml" in target


def test_ci_installs_verified_release_and_calls_the_make_gate():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["zizmor"]

    assert job["permissions"] == {"contents": "read"}
    assert job["env"] == {"ZIZMOR_VERSION": VERSION, "ZIZMOR_SHA256": SHA256}
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["persist-credentials"] is False
    install = job["steps"][1]["run"]
    assert f"zizmor/releases/download/v${{ZIZMOR_VERSION}}" in install
    assert 'echo "${ZIZMOR_SHA256}  ${archive}" | sha256sum -c -' in install
    assert 'tar -xzf "$archive" -C "$bin_dir"' in install
    assert job["steps"][2]["run"] == "make zizmor-check ZIZMOR_FORMAT=github"
    assert "zizmor" in workflow["jobs"]["required"]["needs"]
