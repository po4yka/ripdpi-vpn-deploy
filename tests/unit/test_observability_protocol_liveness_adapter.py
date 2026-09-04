"""Published protocol-liveness evidence adapter tests."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

from jinja2.nativetypes import NativeEnvironment
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/observability_control_plane"
ADAPTER = ROLE / "files/observability-protocol-liveness-adapter.py"

adapter_spec = importlib.util.spec_from_file_location(
    "observability_protocol_liveness_adapter", ADAPTER
)
adapter = importlib.util.module_from_spec(adapter_spec)
sys.modules[adapter_spec.name] = adapter
adapter_spec.loader.exec_module(adapter)


def _evidence(decision: str = "healthy", observed_at: int = 1_800_000_000) -> dict:
    return {
        "schema_version": 2,
        "evaluated_at": observed_at,
        "decision": decision,
        "candidate_policies": ["vpn-path"] if decision == "rotation_candidate" else [],
        "failed_vantages": {"vpn-path": 2},
        "monitoring_errors": [],
        "evidence": [
            {
                "sentinel": "sentinel-a",
                "policy": "vpn-path",
                "control": "ok",
                "profiles": {
                    "p0-reality": "ok",
                    "p1-xhttp": "blocked",
                    "p2-hysteria2": "throttled",
                    "p2-amneziawg": "error",
                },
                "observed_at": observed_at,
                "endpoint_variants": {
                    "p0-reality": [
                        {"variant": 1, "verdict": "blocked"},
                        {"variant": 2, "verdict": "ok"},
                    ]
                },
            }
        ],
    }


def _run(
    tmp_path: Path, document: dict, *, now: int = 1_800_000_010
) -> subprocess.CompletedProcess[str]:
    evidence = tmp_path / "last-evidence.json"
    output = tmp_path / "protocol-liveness.prom"
    evidence.write_text(json.dumps(document), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--now",
            str(now),
            "--stale-after",
            "120",
            "--max-future",
            "30",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "decision",
    ["healthy", "degraded", "unknown", "rotation_candidate"],
)
def test_adapter_exports_every_canonical_decision_without_recomputing_it(
    tmp_path: Path, decision: str
) -> None:
    result = _run(tmp_path, _evidence(decision))

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    assert (
        f'role="liveness-decision-{decision.replace("_", "-")}",state="fresh"'
        in metrics
    )
    assert (
        'node="vpn-path",role="liveness-rotation-candidate",state="fresh"' in metrics
    ) is (decision == "rotation_candidate")
    assert "quorum" not in metrics


def test_adapter_exports_one_hot_profile_variant_control_and_timestamp_evidence(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, _evidence())

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    for role in (
        "liveness-control-ok",
        "liveness-p0-reality-ok",
        "liveness-p1-xhttp-blocked",
        "liveness-p2-hysteria2-throttled",
        "liveness-p2-amneziawg-error",
        "liveness-p0-reality-variant-1-blocked",
        "liveness-p0-reality-variant-2-ok",
        "liveness-evaluated-at",
        "liveness-observed-at",
    ):
        assert f'role="{role}",state="fresh"' in metrics
    assert "1800000000" in metrics
    assert "monitoring_errors" not in metrics


@pytest.mark.parametrize("verdict", ["ok", "blocked", "throttled", "error", "unknown"])
def test_adapter_preserves_each_canonical_profile_verdict_as_one_hot_evidence(
    tmp_path: Path, verdict: str
) -> None:
    document = _evidence()
    document["evidence"][0]["profiles"] = {"p0-reality": verdict}
    document["evidence"][0]["endpoint_variants"] = {}
    document["monitoring_errors"] = ["private-token-marker"]

    result = _run(tmp_path, document)

    assert result.returncode == 0, result.stderr
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    assert f'role="liveness-p0-reality-{verdict}",state="fresh"' in metrics
    assert "private-token-marker" not in metrics


@pytest.mark.parametrize(
    ("now", "expected"),
    [(1_800_000_121, "stale"), (1_799_999_969, "future")],
)
def test_adapter_fails_closed_for_stale_or_future_published_evidence(
    tmp_path: Path, now: int, expected: str
) -> None:
    result = _run(tmp_path, _evidence(), now=now)

    assert result.returncode == 2
    metrics = (tmp_path / "protocol-liveness.prom").read_text(encoding="utf-8")
    assert f'role="liveness-published-evidence",state="{expected}"' in metrics
    assert "liveness-decision-healthy" not in metrics


def test_adapter_replaces_prior_verdict_with_malformed_evidence_state(
    tmp_path: Path,
) -> None:
    output = tmp_path / "protocol-liveness.prom"
    output.write_text("stale success\n", encoding="utf-8")
    invalid = _evidence()
    invalid["evidence"][0]["sentinel"] = "not an allowed label!"

    result = _run(tmp_path, invalid)

    assert result.returncode == 2
    assert 'role="liveness-published-evidence",state="malformed"' in output.read_text(
        encoding="utf-8"
    )
    assert "stale success" not in output.read_text(encoding="utf-8")


def test_adapter_refuses_symlinked_published_evidence(tmp_path: Path) -> None:
    target = tmp_path / "published.json"
    target.write_text(json.dumps(_evidence()), encoding="utf-8")
    evidence = tmp_path / "last-evidence.json"
    evidence.symlink_to(target)
    output = tmp_path / "protocol-liveness.prom"

    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--now",
            "1800000010",
            "--stale-after",
            "120",
            "--max-future",
            "30",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert 'role="liveness-published-evidence",state="malformed"' in output.read_text(
        encoding="utf-8"
    )


def test_adapter_refuses_duplicate_sentinel_series_before_metric_publication(
    tmp_path: Path,
) -> None:
    document = _evidence()
    duplicate = dict(document["evidence"][0])
    duplicate["profiles"] = {"p2-amneziawg": "ok"}
    document["evidence"].append(duplicate)

    result = _run(tmp_path, document)

    assert result.returncode == 2
    assert 'role="liveness-published-evidence",state="malformed"' in (
        tmp_path / "protocol-liveness.prom"
    ).read_text(encoding="utf-8")


def test_adapter_sets_collector_mode_before_atomic_publication(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "protocol-liveness.prom"
    published_modes: list[int] = []
    replace = adapter.os.replace

    def observe_publication(source: Path, destination: Path) -> None:
        published_modes.append(stat.S_IMODE(source.stat().st_mode))
        replace(source, destination)

    monkeypatch.setattr(adapter.os, "replace", observe_publication)

    adapter._atomic_write(output, b"metric 1\n")
    assert published_modes == [0o640]
    assert stat.S_IMODE(output.stat().st_mode) == 0o640


def test_adapter_template_consumes_only_published_evidence() -> None:
    service = (
        ROLE / "templates/observability-protocol-liveness-adapter.service.j2"
    ).read_text()
    assert "observability-protocol-liveness-adapter.py" in service
    assert "--evidence" in service
    assert "protocol-liveness.py" not in service
    assert "vpn-protocol-liveness" not in service


def test_adapter_accepts_shared_textfile_directory_and_publishes_collector_readable_output(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    if os.geteuid() == 0:
        shared = Path(
            tempfile.mkdtemp(prefix="protocol-liveness-textfile-", dir="/tmp")
        )
        request.addfinalizer(lambda: shutil.rmtree(shared))
    else:
        shared = tmp_path / "textfile"
        shared.mkdir()
    shared.chmod(0o3775)
    evidence = tmp_path / "last-evidence.json"
    evidence.write_text(json.dumps(_evidence()), encoding="utf-8")
    output = shared / "protocol-liveness.prom"

    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--evidence",
            str(evidence),
            "--output",
            str(output),
            "--now",
            "1800000010",
            "--stale-after",
            "120",
            "--max-future",
            "30",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    output_stat = output.stat()
    assert stat.S_IMODE(output_stat.st_mode) == 0o640
    assert output_stat.st_gid == shared.stat().st_gid
    assert output_stat.st_mode & stat.S_IRGRP
    reader_uid = 65534 if output_stat.st_uid != 65534 else 65533
    reader_gid = 65534 if output_stat.st_gid != 65534 else 65533
    assert reader_uid != output_stat.st_uid
    reader = (
        "import os,sys; "
        "group=int(sys.argv[2]); uid=int(sys.argv[3]); gid=int(sys.argv[4]); "
        "\ntry: os.setgroups([group]); os.setgid(gid); os.setuid(uid)"
        "\nexcept PermissionError: "
        "print('capability-unavailable', file=sys.stderr); sys.exit(77)"
        "\nassert os.geteuid() != int(sys.argv[5])"
        "\nassert os.getegid() != group and group in os.getgroups()"
        "\nopen(sys.argv[1]).read()"
    )
    read_result = subprocess.run(
        [
            sys.executable,
            "-c",
            reader,
            str(output),
            str(output_stat.st_gid),
            str(reader_uid),
            str(reader_gid),
            str(output_stat.st_uid),
        ],
        capture_output=True,
        text=True,
    )
    if read_result.returncode == 77 and "capability-unavailable" in read_result.stderr:
        pytest.skip("root runtime lacks setgroups/setgid/setuid capability")
    assert read_result.returncode == 0, read_result.stderr


def test_role_wires_the_adapter_only_when_the_explicit_opt_in_is_enabled() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    protocol = defaults["observability_control_plane"]["protocol_liveness"]
    assert protocol["enabled"] is False
    assert (
        protocol["evidence_path"]
        == protocol["evidence_directory"] + "/last-evidence.json"
    )
    assert (
        protocol["output_path"]
        == protocol["output_directory"] + "/protocol-liveness.prom"
    )

    enable = yaml.safe_load((ROLE / "tasks/enable.yml").read_text())
    install = next(
        task for task in enable if task["name"] == "Install protocol-liveness adapter"
    )
    timer = next(
        task
        for task in enable
        if task["name"] == "Enable protocol-liveness adapter timer"
    )
    assert (
        install["when"]
        == "observability_control_plane.protocol_liveness.enabled | bool"
    )
    assert timer["ansible.builtin.systemd_service"]["enabled"] is True
    assert timer["ansible.builtin.systemd_service"]["state"] == "started"

    disable = yaml.safe_load((ROLE / "tasks/disable.yml").read_text())
    stop = next(
        task
        for task in disable
        if task["name"] == "Stop and disable protocol-liveness adapter units"
    )
    assert "failed_when" not in stop
    assert "item in ansible_facts.services" in stop["when"]
    removal = next(
        task
        for task in disable
        if task["name"] == "Remove protocol-liveness adapter owned surfaces"
    )
    assert (
        "/usr/local/libexec/observability-protocol-liveness-adapter.py"
        in removal["loop"]
    )
    assert (
        "{{ observability_control_plane.protocol_liveness.output_path }}"
        in removal["loop"]
    )
    assert all("evidence" not in path for path in removal["loop"])
    assert (
        "Remove disabled protocol-liveness adapter artifacts"
        in (ROLE / "tasks/enable.yml").read_text()
    )


def test_enabled_molecule_proves_distinct_supplementary_group_read_access() -> None:
    prepare = yaml.safe_load((ROLE / "molecule/enabled/prepare.yml").read_text())
    prepare_tasks = prepare[0]["tasks"]
    textfile_group = next(
        task
        for task in prepare_tasks
        if task["name"] == "Create the observability textfile collector group"
    )
    assert textfile_group["ansible.builtin.group"]["name"] == "observability-textfile"
    textfile_directories = next(
        task
        for task in prepare_tasks
        if task["name"]
        == "Create canonical protocol-liveness publisher and textfile paths"
    )
    textfile_item = next(
        item
        for item in textfile_directories["loop"]
        if item["path"] == "/var/lib/node_exporter/textfile"
    )
    assert textfile_item == {
        "path": "/var/lib/node_exporter/textfile",
        "group": "observability-textfile",
        "mode": "3775",
    }

    side_effect = yaml.safe_load(
        (ROLE / "molecule/enabled/side_effect.yml").read_text()
    )
    tasks = side_effect[0]["pre_tasks"]
    names = {task["name"] for task in tasks}
    assert {
        "Create a distinct observability textfile reader identity",
        "Require a distinct primary group and the textfile supplementary group",
        "Require collector-only group readability on generated textfiles",
        "Read generated observability textfiles through only the supplementary group",
    }.issubset(names)

    reader = next(
        task
        for task in tasks
        if task["name"]
        == "Read generated observability textfiles through only the supplementary group"
    )
    identity = next(
        task
        for task in tasks
        if task["name"] == "Create a distinct observability textfile reader identity"
    )
    assert identity["ansible.builtin.user"]["group"] == "observability-molecule-reader"
    assert identity["ansible.builtin.user"]["groups"] == ["observability-textfile"]
    assert identity["ansible.builtin.user"]["append"] is False
    command = reader["ansible.builtin.command"]
    assert reader["become"] is True
    assert reader["become_user"] == "observability-molecule-reader"
    assert command["argv"] == [
        "/usr/bin/cat",
        "/var/lib/node_exporter/textfile/observability-expected-targets.prom",
        "/var/lib/node_exporter/textfile/protocol-liveness.prom",
    ]
    assert reader["changed_when"] is False
    assert "ignore_errors" not in reader
    assert "failed_when" not in reader


def test_enabled_and_disabled_molecule_scenarios_prove_adapter_lifecycle() -> None:
    fixture_contract = yaml.safe_load(
        (ROLE / "molecule/enabled/tasks/fixture-contract.yml").read_text()
    )
    config = fixture_contract[-1]["ansible.builtin.set_fact"][
        "observability_control_plane"
    ]
    assert config["protocol_liveness"]["enabled"] is True
    enabled_verify = (ROLE / "molecule/enabled/verify.yml").read_text()
    assert "observability-protocol-liveness-adapter.timer" in enabled_verify
    assert "protocol-liveness.prom" in enabled_verify
    verify_tasks = yaml.safe_load(enabled_verify)[0]["tasks"]
    names = [task["name"] for task in verify_tasks]
    run_index = names.index(
        "Run protocol-liveness adapter once against canonical evidence"
    )
    clock, publication = verify_tasks[run_index - 2 : run_index]
    assert clock["ansible.builtin.command"]["argv"] == ["date", "+%s"]
    assert clock["changed_when"] is False
    copy = publication["ansible.builtin.copy"]
    assert copy["dest"] == config["protocol_liveness"]["evidence_path"]
    assert (copy["owner"], copy["group"], copy["mode"]) == ("root", "root", "0600")
    environment = NativeEnvironment(autoescape=True)
    environment.filters["to_json"] = json.dumps
    now = 1_800_000_187
    document = environment.from_string(copy["content"]).render(
        ansible_facts={"date_time": {"epoch": str(now - 187)}},
        **{clock["register"]: {"stdout": str(now)}},
    )
    assert document["evaluated_at"] == now
    bounds = {
        "now": now,
        "stale_after": config["protocol_liveness"]["stale_after_seconds"],
        "max_future": config["protocol_liveness"]["max_future_seconds"],
    }
    assert b'state="fresh"' in adapter.render(document, **bounds)
    document["evaluated_at"] -= 187
    with pytest.raises(adapter.AdapterError, match="stale evidence"):
        adapter.render(document, **bounds)

    disabled_verify = (ROLE / "molecule/default/verify.yml").read_text()
    assert "observability-protocol-liveness-adapter.service" in disabled_verify
    assert "protocol-liveness.prom" in disabled_verify
