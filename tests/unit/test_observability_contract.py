from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "observability-contract.py"
CONTRACT = ROOT / "contract"


@contextmanager
def _trusted_temp_root() -> Iterator[Path]:
    root: Path | None = None
    try:
        with tempfile.TemporaryDirectory(
            prefix="ripdpi-observability-test-", dir=Path.home().resolve(strict=True)
        ) as value:
            root = Path(value)
            root.chmod(0o700)
            for ancestor in (root, *root.parents):
                metadata = os.lstat(ancestor)
                assert stat.S_ISDIR(metadata.st_mode)
                assert metadata.st_uid in {0, os.geteuid()}
                assert metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0
            yield root
    finally:
        if root is not None:
            assert not root.exists()


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    with _trusted_temp_root() as root:
        yield root


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
        "manifest_generation": manifest["generation"],
        "manifest_source_id": manifest["source_id"],
        "inventory_generation": inventory["generation"],
        "inventory_source_id": inventory["source_id"],
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
    output: Path | None = None,
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
    output = tmp_path / "observability.prom" if output is None else output
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


def _invoke_paths(
    paths: list[Path],
    output: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
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
            "1700000060",
        ]
    )
    captured = capsys.readouterr()
    return result, captured.out, captured.err


@pytest.mark.parametrize("document_index", range(3))
def test_contract_inputs_reject_duplicate_json_keys(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    document_index: int,
) -> None:
    paths: list[Path] = []
    for name, value in zip(
        ("manifest.json", "inventory.json", "evidence.json"),
        _documents(),
        strict=True,
    ):
        path = tmp_path / name
        raw = json.dumps(value)
        if len(paths) == document_index:
            raw = raw.replace(
                '"schema_version": 1',
                '"schema_version": 1, "schema_version": 1',
                1,
            )
        path.write_text(raw, encoding="utf-8")
        paths.append(path)

    output = tmp_path / "observability.prom"
    rc, stdout, stderr = _invoke_paths(paths, output, capsys)

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert not output.exists()


@pytest.mark.parametrize("document_index", range(3))
@pytest.mark.parametrize(
    "unsafe", ["writable_file", "hard_link", "writable_ancestor", "symlink_ancestor"]
)
def test_contract_inputs_reject_untrusted_files_and_ancestry(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    document_index: int,
    unsafe: str,
) -> None:
    documents = _documents()
    trusted = tmp_path / "trusted"
    trusted.mkdir(mode=0o700)
    paths: list[Path] = []
    for index, (name, value) in enumerate(
        zip(
            ("manifest.json", "inventory.json", "evidence.json"),
            documents,
            strict=True,
        )
    ):
        parent = trusted
        if index == document_index and unsafe in {
            "writable_ancestor",
            "symlink_ancestor",
        }:
            real_parent = trusted / f"real-{index}"
            real_parent.mkdir(mode=0o700)
            if unsafe == "writable_ancestor":
                real_parent.chmod(0o770)
                parent = real_parent
            else:
                linked_parent = trusted / f"linked-{index}"
                linked_parent.symlink_to(real_parent, target_is_directory=True)
                parent = linked_parent
        path = parent / name
        path.write_text(json.dumps(value), encoding="utf-8")
        if index == document_index and unsafe == "writable_file":
            path.chmod(0o664)
        if index == document_index and unsafe == "hard_link":
            os.link(path, trusted / f"second-link-{index}")
        paths.append(path)

    output = tmp_path / "observability.prom"
    rc, stdout, stderr = _invoke_paths(paths, output, capsys)

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert not output.exists()


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
        f'vpn_observability_evidence_state{{node="vpn-p0",role="edge",state="{expected}"}} 1'
        in exposition
    )
    assert (
        'vpn_observability_expected_target{node="vpn-p0",role="edge"} 1' in exposition
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
        manifest["families"][0]["labels"].append("profile")
        inventory["targets"][0]["label_values"]["profile"] = ["primary", "secondary"]
        sample["labels"]["profile"] = "primary"
        duplicate = copy.deepcopy(sample)
        duplicate["labels"]["profile"] = "secondary"
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
    manifest["families"][0]["labels"].append("profile")
    inventory["targets"][0]["label_values"]["profile"] = ["primary", "secondary"]
    evidence["targets"][0]["samples"][0]["labels"]["profile"] = "primary"
    second = copy.deepcopy(evidence["targets"][0]["samples"][0])
    second["labels"]["profile"] = "secondary"
    evidence["targets"][0]["samples"].append(second)

    rc, _, _, output = _invoke(tmp_path, capsys, manifest, inventory, evidence)

    assert rc == 0
    assert output.read_text().count("# TYPE vpn_watchdog_collection_success gauge") == 1


def test_duplicate_series_across_targets_is_malformed_and_not_published(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, inventory, evidence = _documents()
    manifest["families"][0]["labels"] = ["role"]
    evidence["targets"][0]["samples"][0]["labels"] = {"role": "edge"}
    second_target = copy.deepcopy(inventory["targets"][0])
    second_target["target"] = "vpn-p1"
    second_target["label_values"]["node"] = ["vpn-p1"]
    inventory["targets"].append(second_target)
    second_observation = copy.deepcopy(evidence["targets"][0])
    second_observation["target"] = "vpn-p1"
    evidence["targets"].append(second_observation)

    rc, stdout, _, output = _invoke(tmp_path, capsys, manifest, inventory, evidence)

    assert rc == 0
    assert json.loads(stdout)["states"] == {"malformed": 2}
    assert "vpn_watchdog_collection_success" not in output.read_text()


def test_technical_label_value_must_be_explicitly_allowlisted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, inventory, evidence = _documents()
    manifest["families"][0]["labels"].append("profile")
    inventory["targets"][0]["label_values"]["profile"] = ["primary"]
    evidence["targets"][0]["samples"][0]["labels"]["profile"] = "secondary"

    rc, stdout, _, output = _invoke(tmp_path, capsys, manifest, inventory, evidence)

    assert rc == 0
    assert json.loads(stdout)["states"] == {"malformed": 1}
    assert "vpn_watchdog_collection_success" not in output.read_text()

    inventory["targets"][0]["label_values"]["profile"].append("secondary")
    rc, stdout, _, output = _invoke(tmp_path, capsys, manifest, inventory, evidence)
    assert rc == 0
    assert json.loads(stdout)["states"] == {"fresh": 1}
    assert 'profile="secondary"' in output.read_text()


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


def test_short_opaque_identity_is_rejected_even_when_inventory_attempts_to_allow_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    corpus = json.loads(
        (ROOT / "tests/fixtures/observability/secret-shaped-values.json").read_text()
    )
    for index, secret in enumerate(corpus["short_opaque_values"]):
        case = tmp_path / str(index)
        case.mkdir()
        manifest, inventory, evidence = _documents()
        inventory["targets"][0]["role"] = secret
        inventory["targets"][0]["label_values"]["role"] = [secret]
        evidence["targets"][0]["samples"][0]["labels"]["role"] = secret

        rc, stdout, stderr, output = _invoke(
            case, capsys, manifest, inventory, evidence
        )

        combined = stdout + stderr
        if output.exists():
            combined += output.read_text(encoding="utf-8")
        assert rc == 2
        assert stdout == ""
        assert stderr == "observability-contract: validation failed\n"
        assert secret not in combined


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


def test_manifest_declares_every_renderer_owned_family_with_bounded_labels() -> None:
    manifest = json.loads(
        (CONTRACT / "observability-metric-manifest.example.json").read_text()
    )
    families = {family["name"]: family for family in manifest["families"]}

    assert families["vpn_observability_expected_target"] == {
        "name": "vpn_observability_expected_target",
        "owner": "observability_contract",
        "type": "gauge",
        "unit": None,
        "labels": ["node", "role"],
        "max_series": 256,
        "cadence_seconds": 60,
        "stale_after_seconds": 180,
        "alert_use": True,
    }
    assert families["vpn_observability_evidence_state"] == {
        "name": "vpn_observability_evidence_state",
        "owner": "observability_contract",
        "type": "gauge",
        "unit": None,
        "labels": ["node", "role", "state"],
        "max_series": 256,
        "cadence_seconds": 60,
        "stale_after_seconds": 180,
        "alert_use": True,
    }


@pytest.mark.parametrize(
    ("mutation", "reserved_name"),
    [
        ("missing", "vpn_observability_expected_target"),
        ("changed-labels", "vpn_observability_evidence_state"),
    ],
)
def test_manifest_requires_exact_internal_metric_declarations_without_replacing_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    reserved_name: str,
) -> None:
    manifest, inventory, evidence = _documents()
    if mutation == "missing":
        manifest["families"] = [
            family for family in manifest["families"] if family["name"] != reserved_name
        ]
    else:
        family = next(
            family for family in manifest["families"] if family["name"] == reserved_name
        )
        family["labels"] = ["node", "role"]
    output = tmp_path / "observability.prom"
    output.write_text("last-known-good\n", encoding="utf-8")

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence, output=output
    )

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert output.read_text(encoding="utf-8") == "last-known-good\n"


def test_every_emitted_metric_family_and_label_is_manifest_declared(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, inventory, evidence = _documents()

    rc, _stdout, _stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 0
    declarations = {
        family["name"]: set(family["labels"]) for family in manifest["families"]
    }
    for line in output.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        head = line.split(" ", 1)[0]
        family_name, _, encoded_labels = head.partition("{")
        label_names = {
            item.split("=", 1)[0]
            for item in encoded_labels.removesuffix("}").split(",")
            if item
        }
        assert family_name in declarations
        assert label_names == declarations[family_name]


def test_empty_expected_inventory_refuses_and_preserves_last_known_good(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, inventory, evidence = _documents()
    inventory["targets"] = []
    evidence["targets"] = []
    output = tmp_path / "observability.prom"
    output.write_text("last-known-good\n", encoding="utf-8")

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence, output=output
    )

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert output.read_text(encoding="utf-8") == "last-known-good\n"


@pytest.mark.parametrize(
    "binding",
    [
        "manifest_generation",
        "manifest_source_id",
        "inventory_generation",
        "inventory_source_id",
    ],
)
def test_evidence_binding_mismatch_is_malformed_and_drops_producer_samples(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    binding: str,
) -> None:
    manifest, inventory, evidence = _documents()
    evidence[binding] = "wrong-source-v1"

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 0
    assert stderr == ""
    assert json.loads(stdout)["states"] == {"malformed": 1}
    exposition = output.read_text(encoding="utf-8")
    assert "vpn_watchdog_collection_success" not in exposition
    assert 'state="malformed"' in exposition


def test_evidence_binding_mismatch_precedes_lifecycle_classification(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, inventory, evidence = _documents()
    inventory["targets"][0]["lifecycle"] = "disabled"
    evidence["manifest_source_id"] = "wrong-source-v1"

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 0
    assert stderr == ""
    assert json.loads(stdout)["states"] == {"malformed": 1}
    assert "vpn_watchdog_collection_success" not in output.read_text()


@pytest.mark.parametrize("violation", ["family", "label", "unknown_label"])
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
    elif violation == "label":
        manifest["families"][0]["labels"].append("destination")
        evidence["targets"][0]["samples"][0]["labels"]["destination"] = "sink"
    else:
        manifest["families"][0]["labels"] = ["cohort"]
        evidence["targets"][0]["samples"][0]["labels"] = {"cohort": "baseline"}

    rc, stdout, stderr, output = _invoke(
        tmp_path, capsys, manifest, inventory, evidence
    )

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert not output.exists()


@pytest.mark.parametrize(
    "unsafe",
    ["world_writable", "group_writable", "ancestor_symlink", "target_symlink"],
)
def test_atomic_output_refuses_unsafe_paths_and_preserves_last_known_good(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    unsafe: str,
) -> None:
    manifest, inventory, evidence = _documents()
    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    if unsafe in {"world_writable", "group_writable"}:
        parent = safe / "writable"
        parent.mkdir(mode=0o700)
        parent.chmod(0o777 if unsafe == "world_writable" else 0o770)
        output = parent / "observability.prom"
        output.write_text("last-known-good\n", encoding="utf-8")
    elif unsafe == "ancestor_symlink":
        real = safe / "real"
        real.mkdir(mode=0o700)
        output = real / "observability.prom"
        output.write_text("last-known-good\n", encoding="utf-8")
        linked = safe / "linked"
        linked.symlink_to(real, target_is_directory=True)
        output = linked / "observability.prom"
    else:
        parent = safe / "textfile"
        parent.mkdir(mode=0o700)
        real = parent / "last-known-good.prom"
        real.write_text("last-known-good\n", encoding="utf-8")
        output = parent / "observability.prom"
        output.symlink_to(real.name)

    rc, stdout, stderr, _ = _invoke(
        tmp_path, capsys, manifest, inventory, evidence, output=output
    )

    assert rc == 2
    assert stdout == ""
    assert stderr == "observability-contract: validation failed\n"
    assert output.read_text(encoding="utf-8") == "last-known-good\n"


def test_atomic_output_fences_parent_replacement_and_preserves_both_namespaces(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, inventory, evidence = _documents()
    parent = tmp_path / "textfile"
    parent.mkdir(mode=0o700)
    output = parent / "observability.prom"
    output.write_text("last-known-good\n", encoding="utf-8")
    moved = tmp_path / "textfile-original"
    real_fsync = os.fsync
    replaced = False

    def replace_parent_on_temp_fsync(descriptor: int) -> None:
        nonlocal replaced
        if not replaced and stat.S_ISREG(os.fstat(descriptor).st_mode):
            parent.rename(moved)
            parent.mkdir(mode=0o700)
            replaced = True
        real_fsync(descriptor)

    module = _module()
    monkeypatch.setattr(module.os, "fsync", replace_parent_on_temp_fsync)
    paths = []
    for name, value in (
        ("manifest.json", manifest),
        ("inventory.json", inventory),
        ("evidence.json", evidence),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)

    rc = module.main(
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
    captured = capsys.readouterr()

    assert replaced is True
    assert rc == 2
    assert captured.out == ""
    assert captured.err == "observability-contract: validation failed\n"
    assert not output.exists()
    assert (moved / "observability.prom").read_text() == "last-known-good\n"
    assert not list(moved.glob(".observability.prom.*"))


def test_atomic_output_refuses_parent_replacement_during_relative_replace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, inventory, evidence = _documents()
    parent = tmp_path / "textfile"
    parent.mkdir(mode=0o700)
    output = parent / "observability.prom"
    output.write_text("last-known-good\n", encoding="utf-8")
    moved = tmp_path / "textfile-original"
    real_replace = os.replace
    replaced = False

    def replace_parent_during_relative_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int,
        dst_dir_fd: int,
    ) -> None:
        nonlocal replaced
        parent.rename(moved)
        parent.mkdir(mode=0o700)
        replaced = True
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    module = _module()
    monkeypatch.setattr(module.os, "replace", replace_parent_during_relative_replace)
    paths = []
    for name, value in (
        ("manifest.json", manifest),
        ("inventory.json", inventory),
        ("evidence.json", evidence),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)

    rc = module.main(
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
    captured = capsys.readouterr()

    assert replaced is True
    assert rc == 2
    assert captured.out == ""
    assert captured.err == "observability-contract: validation failed\n"
    assert not output.exists()
    assert "last-known-good" not in (moved / "observability.prom").read_text()
    assert not list(parent.glob(".observability.prom.*"))
    assert not list(moved.glob(".observability.prom.*"))


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
