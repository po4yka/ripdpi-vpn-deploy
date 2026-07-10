"""AWG-enabled secret producers must provide immutable source pins."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AWG_GO_VERSION = "v0.2.12"
AWG_GO_COMMIT = "2e3f7d122ca8ef61e403fddc48a9db8fccd95dbf"
AWG_TOOLS_VERSION = "v1.0.20241018"
AWG_TOOLS_COMMIT = "c0b400c6dfc046f5cae8f3051b14cb61686fcf55"


def test_awg_secret_examples_and_generators_include_immutable_source_pins():
    example = yaml.safe_load((REPO_ROOT / "secrets/prod.secrets.example.yaml").read_text())
    expected = {
        "amneziawg_go_version": AWG_GO_VERSION,
        "amneziawg_go_commit": AWG_GO_COMMIT,
        "amneziawg_tools_version": AWG_TOOLS_VERSION,
        "amneziawg_tools_commit": AWG_TOOLS_COMMIT,
    }
    assert {key: example[key] for key in expected} == expected

    bootstrap = (REPO_ROOT / "scripts/bootstrap-secrets.sh").read_text()
    for variable, value in (
        ("AWG_GO_VERSION", AWG_GO_VERSION),
        ("AWG_GO_COMMIT", AWG_GO_COMMIT),
        ("AWG_TOOLS_VERSION", AWG_TOOLS_VERSION),
        ("AWG_TOOLS_COMMIT", AWG_TOOLS_COMMIT),
    ):
        assert f'{variable}="{value}"' in bootstrap
    for key, variable in (
        ("amneziawg_go_version", "AWG_GO_VERSION"),
        ("amneziawg_go_commit", "AWG_GO_COMMIT"),
        ("amneziawg_tools_version", "AWG_TOOLS_VERSION"),
        ("amneziawg_tools_commit", "AWG_TOOLS_COMMIT"),
    ):
        assert f'{key}: "${{{variable}}}"' in bootstrap

    ci_bootstrap = (REPO_ROOT / "scripts/ci-bootstrap-secrets.sh").read_text()
    for key, value in expected.items():
        assert f'{key}: "{value}"' in ci_bootstrap


def test_amneziawg_molecule_vars_model_the_immutable_pin_contract():
    converge = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/amneziawg/molecule/default/converge.yml").read_text()
    )
    vars_ = converge[0]["vars"]
    assert vars_["amneziawg_go_version"] == AWG_GO_VERSION
    assert vars_["amneziawg_go_commit"] == AWG_GO_COMMIT
    assert vars_["amneziawg_tools_version"] == AWG_TOOLS_VERSION
    assert vars_["amneziawg_tools_commit"] == AWG_TOOLS_COMMIT


def test_strict_awg_fixture_includes_immutable_source_pins():
    fixture = yaml.safe_load((REPO_ROOT / "tests/fixtures/secrets-sample.yml").read_text())
    assert fixture["amneziawg_go_version"] == AWG_GO_VERSION
    assert fixture["amneziawg_go_commit"] == AWG_GO_COMMIT
    assert fixture["amneziawg_tools_version"] == AWG_TOOLS_VERSION
    assert fixture["amneziawg_tools_commit"] == AWG_TOOLS_COMMIT
