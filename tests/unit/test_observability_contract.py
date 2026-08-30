from __future__ import annotations

import importlib.util
import ast
import copy
import json
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "observability-contract.py"
CONTRACT = ROOT / "contract"


def _module():
    spec = importlib.util.spec_from_file_location("observability_contract", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_examples_validate_against_versioned_schemas() -> None:
    module = _module()
    import jsonschema

    for stem in (
        "observability-metric-manifest",
        "observability-expected-inventory",
    ):
        schema = json.loads((CONTRACT / f"{stem}.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        example = json.loads((CONTRACT / f"{stem}.example.json").read_text())
        module.validate_document(schema, example)
    evidence_schema = json.loads(
        (CONTRACT / "observability-evidence.schema.json").read_text()
    )
    jsonschema.Draft202012Validator.check_schema(evidence_schema)


def _documents() -> tuple[dict, dict, dict]:
    manifest = json.loads(
        (CONTRACT / "observability-metric-manifest.example.json").read_text()
    )
    inventory = json.loads(
        (CONTRACT / "observability-expected-inventory.example.json").read_text()
    )
    evidence = {
        "schema_version": 1,
        "generation": "evidence-v1",
        "targets": [
            {
                "target": "vpn-p0",
                "status": "valid",
                "observed_at": 1_700_000_000,
                "samples": [
                    {
                        "family": "vpn_watchdog_collection_success",
                        "labels": {"node": "vpn-p0", "role": "edge"},
                        "value": 1,
                    }
                ],
            }
        ],
    }
    return copy.deepcopy(manifest), copy.deepcopy(inventory), copy.deepcopy(evidence)


@pytest.mark.parametrize("document", ["manifest", "inventory", "evidence"])
def test_contracts_reject_unknown_fields_and_future_schema_versions(
    document: str,
) -> None:
    module = _module()
    manifest, inventory, evidence = _documents()
    values = {"manifest": manifest, "inventory": inventory, "evidence": evidence}
    schema_names = {
        "manifest": "observability-metric-manifest.schema.json",
        "inventory": "observability-expected-inventory.schema.json",
        "evidence": "observability-evidence.schema.json",
    }
    schema = json.loads((CONTRACT / schema_names[document]).read_text())
    value = values[document]

    value["schema_version"] = 2
    with pytest.raises(module.ContractError):
        module.validate_document(schema, value)

    value["schema_version"] = 1
    value["unexpected"] = True
    with pytest.raises(module.ContractError):
        module.validate_document(schema, value)


def _invoke(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    manifest: dict,
    inventory: dict,
    evidence: dict,
    *,
    now: int = 1_700_000_060,
) -> tuple[int, str, str, Path]:
    paths = []
    for name, value in (
        ("manifest.json", manifest),
        ("inventory.json", inventory),
        ("evidence.json", evidence),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)
    output = tmp_path / "observability.prom"
    result = _module().main(
        [
            "render",
            "--manifest",
            str(paths[0]),
            "--inventory",
            str(paths[1]),
            "--evidence",
            str(paths[2]),
            "--output",
            str(output),
            "--now",
            str(now),
        ]
    )
    captured = capsys.readouterr()
    return result, captured.out, captured.err, output


@pytest.mark.parametrize(
    ("lifecycle", "ever_seen", "evidence_change", "now", "expected"),
    [
        ("enabled", True, "keep", 1_700_000_060, "fresh"),
        ("enabled", True, "keep", 1_700_000_181, "stale"),
        ("enabled", True, "remove", 1_700_000_060, "absent"),
        ("enabled", False, "remove", 1_700_000_060, "never-seen"),
        ("enabled", True, "future", 1_700_000_060, "future"),
        ("enabled", True, "malformed", 1_700_000_060, "malformed"),
        ("disabled", True, "remove", 1_700_000_060, "disabled"),
        ("retired", True, "remove", 1_700_000_060, "retired"),
    ],
)
def test_render_classifies_every_inventory_and_freshness_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    lifecycle: str,
    ever_seen: bool,
    evidence_change: str,
    now: int,
    expected: str,
) -> None:
    manifest, inventory, evidence = _documents()
    inventory["targets"][0]["lifecycle"] = lifecycle
    inventory["targets"][0]["ever_seen"] = ever_seen
    if evidence_change == "remove":
        evidence["targets"] = []
    elif evidence_change == "future":
        evidence["targets"][0]["observed_at"] = now + 31
    elif evidence_change == "malformed":
        evidence["targets"][0]["status"] = "malformed"
        evidence["targets"][0]["samples"] = []

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence, now=now
    )

    assert rc == 0
    assert stderr == ""
    summary = json.loads(stdout)
    assert summary["states"] == {expected: 1}
    assert summary["targets"] == 1
    exposition = output.read_text(encoding="utf-8")
    assert (
        f'vpn_observability_evidence_state{{role="edge",state="{expected}",target="vpn-p0"}} 1'
        in exposition
    )
    assert (
        'vpn_observability_expected_target{role="edge",target="vpn-p0"} 1' in exposition
    )
    assert ("vpn_watchdog_collection_success" in exposition) is (expected == "fresh")


@pytest.mark.parametrize("violation", ["family", "label", "series"])
def test_unlisted_family_label_or_series_overflow_is_malformed_and_dropped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    violation: str,
) -> None:
    manifest, inventory, evidence = _documents()
    sample = evidence["targets"][0]["samples"][0]
    if violation == "family":
        sample["family"] = "vpn_unlisted_metric"
    elif violation == "label":
        sample["labels"]["destination"] = "bounded-alias"
    else:
        manifest["families"][0]["max_series"] = 1
        duplicate = copy.deepcopy(sample)
        duplicate["labels"]["role"] = "secondary"
        evidence["targets"][0]["samples"].append(duplicate)

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 0
    assert stderr == ""
    assert json.loads(stdout)["states"] == {"malformed": 1}
    exposition = output.read_text(encoding="utf-8")
    assert "vpn_watchdog_collection_success" not in exposition


def test_family_type_is_emitted_once_for_multiple_series(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, inventory, evidence = _documents()
    second = copy.deepcopy(evidence["targets"][0]["samples"][0])
    second["labels"]["role"] = "secondary"
    evidence["targets"][0]["samples"].append(second)

    rc, _, _, output = _invoke(tmp_path, capsys, manifest, inventory, evidence)

    assert rc == 0
    assert output.read_text().count("# TYPE vpn_watchdog_collection_success gauge") == 1


def test_duplicate_series_across_targets_is_malformed_and_not_published(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, inventory, evidence = _documents()
    second_target = copy.deepcopy(inventory["targets"][0])
    second_target["target"] = "vpn-p1"
    inventory["targets"].append(second_target)
    second_observation = copy.deepcopy(evidence["targets"][0])
    second_observation["target"] = "vpn-p1"
    evidence["targets"].append(second_observation)

    rc, stdout, _, output = _invoke(tmp_path, capsys, manifest, inventory, evidence)

    assert rc == 0
    assert json.loads(stdout)["states"] == {"malformed": 2}
    assert "vpn_watchdog_collection_success" not in output.read_text()


def test_secret_endpoint_identity_and_path_shaped_values_are_redacted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    corpus = json.loads(
        (ROOT / "tests/fixtures/observability/secret-shaped-values.json").read_text()
    )
    for index, secret in enumerate(corpus["values"]):
        case = tmp_path / str(index)
        case.mkdir()
        manifest, inventory, evidence = _documents()
        evidence["targets"][0]["samples"][0]["labels"]["role"] = secret

        rc, stdout, stderr, output = _invoke(
            case, capsys, manifest, inventory, evidence
        )

        assert rc == 0
        combined = stdout + stderr + output.read_text(encoding="utf-8")
        assert secret not in combined
        assert json.loads(stdout)["states"] == {"malformed": 1}


def test_render_is_deterministic_atomic_and_owner_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, inventory, evidence = _documents()
    output = tmp_path / "observability.prom"
    output.write_text("previous-complete-state\n", encoding="utf-8")
    first_inode = output.stat().st_ino

    rc, first_stdout, _, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )
    first_bytes = output.read_bytes()
    assert rc == 0
    assert output.stat().st_ino != first_inode
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(first_stdout)["digest"].startswith("sha256:")
    assert len(first_stdout) < 512

    rc, second_stdout, _, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )
    assert rc == 0
    assert output.read_bytes() == first_bytes
    assert second_stdout == first_stdout
    assert not list(tmp_path.glob(".observability.prom.*"))

    module = _module()
    monkeypatch.setattr(
        module.os, "replace", lambda *_: (_ for _ in ()).throw(OSError())
    )
    paths = [
        tmp_path / name for name in ("manifest.json", "inventory.json", "evidence.json")
    ]
    assert (
        module.main(
            [
                "render",
                "--manifest",
                str(paths[0]),
                "--inventory",
                str(paths[1]),
                "--evidence",
                str(paths[2]),
                "--output",
                str(output),
                "--now",
                "1700000060",
            ]
        )
        == 2
    )
    assert output.read_bytes() == first_bytes
    assert not list(tmp_path.glob(".observability.prom.*"))
    capsys.readouterr()


@pytest.mark.parametrize("duplicate", ["family", "target", "evidence"])
def test_duplicate_semantic_identity_refuses_without_replacing_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    duplicate: str,
) -> None:
    manifest, inventory, evidence = _documents()
    if duplicate == "family":
        manifest["families"].append(copy.deepcopy(manifest["families"][0]))
    elif duplicate == "target":
        inventory["targets"].append(copy.deepcopy(inventory["targets"][0]))
    else:
        evidence["targets"].append(copy.deepcopy(evidence["targets"][0]))
    output = tmp_path / "observability.prom"
    output.write_text("last-known-good\n", encoding="utf-8")

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert output.read_text() == "last-known-good\n"


@pytest.mark.parametrize("violation", ["family", "label"])
def test_manifest_refuses_secret_or_destination_shaped_output_identifiers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    violation: str,
) -> None:
    manifest, inventory, evidence = _documents()
    if violation == "family":
        old_name = manifest["families"][0]["name"]
        manifest["families"][0]["name"] = "vpn_secret_token"
        inventory["targets"][0]["required_families"] = ["vpn_secret_token"]
        evidence["targets"][0]["samples"][0]["family"] = "vpn_secret_token"
        assert old_name != "vpn_secret_token"
    else:
        manifest["families"][0]["labels"].append("destination")
        evidence["targets"][0]["samples"][0]["labels"]["destination"] = "sink"

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert not output.exists()


def test_runtime_has_no_network_or_subprocess_imports() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"socket", "subprocess", "urllib", "http", "requests"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden)
