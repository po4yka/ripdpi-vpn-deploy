import asyncio
import time
import json
import pytest
from hypothesis import given, settings, strategies as st
from artifact_helpers import private
from vpnd.commands import probe_matrix as matrix


def matrix_cells(verdict):
    protocols = ["mtproto", "xhttp-vless"]
    cells = []
    for index, cls in enumerate(matrix.CLASSES):
        for topology in matrix.TOPOLOGIES:
            for protocol in protocols:
                target = dict(
                    id=f"target-{index}-"
                    + ("dual" if topology == matrix.TOPOLOGIES[0] else "split"),
                    comparison_set=f"pair-{index}",
                    destination_class=cls,
                    topology=topology,
                )
                value = matrix.cell_error(
                    0, 1, protocol, target, verdict(protocol, cls, topology), ""
                )
                value.pop("error_kind")
                cells.append(value)
    return protocols, cells


# Rust test: vpnd/src/commands/probe_matrix.rs::json_summary_reports_path_and_counts
def test_json_summary_reports_path_and_counts():
    report = matrix.synthetic_report_for_snapshot()
    summary = json.loads(matrix.json_summary(report, "/tmp/report.json"))
    assert summary["report_path"] == "/tmp/report.json"
    assert (
        summary["completed"] == report["completed"]
        and summary["interrupted"] == report["interrupted"]
    )
    assert summary["cells"] == len(report["cells"]) and summary["observations"] == len(
        report["observations"]
    )


@settings(max_examples=256)
@given(st.text(max_size=80), st.integers(min_value=1, max_value=65534))
# Rust test: vpnd/src/commands/probe_matrix.rs::fingerprint_ignores_only_identity_and_credentials
def test_fingerprint_ignores_only_identity_and_credentials(secret, port):
    def profile(credential, endpoint, p):
        return dict(
            schema_version=1,
            target_id=credential,
            endpoint=endpoint,
            protocols={
                "mtproto": dict(secret=credential, uuid=credential, password=credential, port=p)
            },
            expected_xray_version="v26.3.27",
        )

    fingerprint = matrix.transport_fingerprint(profile(secret, "192.0.2.1", port))
    assert fingerprint == matrix.transport_fingerprint(profile("other", "192.0.2.2", port))
    assert fingerprint != matrix.transport_fingerprint(profile(secret, "192.0.2.1", port + 1))


# Rust test: vpnd/src/commands/probe_matrix.rs::durations_parse_valid_units
def test_durations_parse_valid_units():
    for value, seconds in [("1", 1), ("2s", 2), ("3m", 180), ("4h", 14400), ("1d", 86400)]:
        assert matrix.parse_duration(value) == seconds


# Rust test: vpnd/src/commands/probe_matrix.rs::durations_reject_malformed_units
def test_durations_reject_malformed_units():
    for value in ["-1s", "2ms", "", "1w", "s"]:
        with pytest.raises(ValueError):
            matrix.parse_duration(value)


# Rust test: vpnd/src/commands/probe_matrix.rs::durations_reject_zero_and_multiplication_overflow
def test_durations_reject_zero_and_multiplication_overflow():
    for value in ["0", "0s", "0m", "0h", "0d", "18446744073709551615d"]:
        with pytest.raises(ValueError):
            matrix.parse_duration(value)


# Rust test: vpnd/src/commands/probe_matrix.rs::windows_exclude_local_failures_and_do_not_bridge_indeterminate_gaps
def test_windows_exclude_local_failures_and_do_not_bridge_indeterminate_gaps():
    _, template = matrix_cells(lambda *args: "ok")
    for verdicts, expected in [
        (["ok", "unknown", "error", "ok"], []),
        (["unknown", "throttled", "ok"], [(100, 200)]),
        (["blocked", "unknown", "ok"], [(0, None)]),
        (["blocked", "error", "throttled", "ok"], [(0, None)]),
        (["blocked", "throttled", "ok", "blocked"], [(0, 200)]),
    ]:
        cells = [
            dict(template[0], tick=tick, timestamp_unix_ms=tick * 100, verdict=verdict)
            for tick, verdict in enumerate(verdicts)
        ]
        actual = [(w["onset_unix_ms"], w["recovery_unix_ms"]) for w in matrix.windows(cells)]
        assert actual == expected


# Rust test: vpnd/src/commands/probe_matrix.rs::windows_record_blocked_onset_and_ok_recovery
def test_windows_record_blocked_onset_and_ok_recovery():
    _, template = matrix_cells(lambda *args: "ok")
    cells = [
        dict(template[0], tick=tick, timestamp_unix_ms=tick * 100, verdict=verdict)
        for tick, verdict in enumerate(["ok", "blocked", "ok"])
    ]
    windows = matrix.windows(cells)
    assert (
        len(windows) == 1
        and windows[0]["onset_unix_ms"] == 100
        and windows[0]["recovery_unix_ms"] == 200
    )


def config(targets):
    return dict(
        schema_version=2,
        vantage="filtered-path-a",
        poll_interval_seconds=300,
        control=dict(
            url="https://control.example/probe",
            expected_status=204,
            timeout_seconds=15,
            degraded_after_ms=3000,
        ),
        protocols=["mtproto"],
        targets=targets,
    )


# Rust test: vpnd/src/commands/probe_matrix.rs::paired_targets_are_required
def test_paired_targets_are_required():
    target = dict(
        id="only-dual",
        comparison_set="pair-a",
        destination_class="neutral-pattern",
        topology="single-ip-dual-role",
        profile_file="/tmp/profile.json",
    )
    with pytest.raises(ValueError):
        matrix.validate_config(config([target]))


# Rust test: vpnd/src/commands/probe_matrix.rs::paired_profiles_require_matching_transport_parameters
def test_paired_profiles_require_matching_transport_parameters(tmp_path):
    targets = []
    for id, topology, port in [
        ("pair-dual", matrix.TOPOLOGIES[0], 443),
        ("pair-split", matrix.TOPOLOGIES[1], 8443),
    ]:
        path = private(
            tmp_path / (id + ".json"),
            json.dumps(
                dict(
                    schema_version=1,
                    target_id=id,
                    endpoint="192.0.2.1",
                    expected_xray_version="v26.3.27",
                    expected_mtg_version="v2.2.8",
                    expected_mtproto_helper_version="gotd-v0.160.0",
                    protocols={"mtproto": {"port": port, "secret": id}},
                )
            ),
        )
        targets.append(
            dict(
                id=id,
                comparison_set="pair-a",
                destination_class="neutral-pattern",
                topology=topology,
                profile_file=str(path),
            )
        )
    with pytest.raises(ValueError, match="identical runtime and transport"):
        matrix.validate_profiles(config(targets))


# Rust test: vpnd/src/commands/probe_matrix.rs::fixed_rate_schedule_does_not_accumulate_sweep_time
def test_fixed_rate_schedule_does_not_accumulate_sweep_time():
    assert matrix.scheduled_tick(10, 5, 3) == 25
    assert matrix.scheduled_tick(10, 2**64 - 1, 0) == 10
    assert matrix.scheduled_tick(10, 2**64 - 1, 2) is None
    assert matrix.scheduled_tick(10, 2**64 - 1, 1) is None


# Rust test: vpnd/src/commands/probe_matrix.rs::synthetic_report_detects_dual_role_candidate
def test_synthetic_report_detects_dual_role_candidate():
    report = matrix.synthetic_report_for_snapshot()
    assert report["schema_version"] == 3 and any(
        o["kind"] == "dual-role-targeting-candidate" for o in report["observations"]
    )


# Rust test: vpnd/src/commands/probe_matrix.rs::analyzer_detects_protocol_specific_in_two_of_three_classes
def test_analyzer_detects_protocol_specific_in_two_of_three_classes():
    protocols, cells = matrix_cells(
        lambda protocol, cls, topology: (
            "blocked" if protocol == "mtproto" and cls != "non-allowlist-pattern" else "ok"
        )
    )
    assert any(
        o["kind"] == "protocol-specific" and o["protocol"] == "mtproto"
        for o in matrix.analyze(protocols, cells)
    )


# Rust test: vpnd/src/commands/probe_matrix.rs::analyzer_detects_destination_class_collateral
def test_analyzer_detects_destination_class_collateral():
    protocols, cells = matrix_cells(
        lambda protocol, cls, topology: "blocked" if cls == "neutral-pattern" else "ok"
    )
    assert any(
        o["kind"] == "destination-class-wide-collateral"
        and o["destination_class"] == "neutral-pattern"
        for o in matrix.analyze(protocols, cells)
    )


# Rust test: vpnd/src/commands/probe_matrix.rs::unknown_evidence_is_indeterminate_and_suppresses_positive_results
def test_unknown_evidence_is_indeterminate_and_suppresses_positive_results():
    protocols, cells = matrix_cells(
        lambda protocol, cls, topology: (
            "unknown"
            if protocol == "mtproto"
            and cls == "neutral-pattern"
            and topology == "single-ip-dual-role"
            else "blocked"
        )
    )
    observations = matrix.analyze(protocols, cells)
    assert len(observations) == 1 and observations[0]["kind"] == "indeterminate"


# Rust test: vpnd/src/commands/probe_matrix.rs::concurrent_collection_is_ordered_and_isolates_timeout
def test_concurrent_collection_is_ordered_and_isolates_timeout():
    async def collect():
        async def delayed(delay, value):
            await asyncio.sleep(delay)
            return value

        async def timeout():
            try:
                return await asyncio.wait_for(delayed(0.2, "unexpected"), 0.02)
            except TimeoutError:
                return "timeout"

        start = time.monotonic()
        result = await asyncio.gather(delayed(0.08, "slow"), timeout(), delayed(0.01, "fast"))
        assert result == ["slow", "timeout", "fast"]
        assert time.monotonic() - start < 0.15

    asyncio.run(collect())


def test_profile_schema_rejects_boolean_and_output_rejects_parent(tmp_path):
    from pathlib import Path

    targets = []
    for index, topology in enumerate(matrix.TOPOLOGIES):
        id = f"target-{index}"
        path = private(
            tmp_path / (id + ".json"),
            json.dumps(
                dict(schema_version=True, target_id=id, protocols={"mtproto": {"port": 443}})
            ),
        )
        targets.append(
            dict(
                id=id,
                comparison_set="pair",
                destination_class="neutral-pattern",
                topology=topology,
                profile_file=str(path),
            )
        )
    with pytest.raises(ValueError, match="identity or schema"):
        matrix.validate_profiles(config(targets))
    with pytest.raises(ValueError, match="name a file"):
        matrix.validate_output_path(Path(".."))


def test_duration_trim_accepts_only_unicode_white_space():
    from vpnd.text import WHITE_SPACE

    assert matrix.parse_duration(WHITE_SPACE + "1s" + WHITE_SPACE) == 1
    for character in ["\x1c", "\x1d", "\x1e", "\x1f"]:
        for value in [character + "1s", "1s" + character]:
            with pytest.raises(ValueError):
                matrix.parse_duration(value)


def test_matrix_schema_is_integer_not_float(tmp_path):
    value = config([])
    value["schema_version"] = 2.0
    with pytest.raises(ValueError, match="schema_version"):
        matrix.validate_config(value)


def test_probe_output_framing_uses_unicode_white_space():
    from types import SimpleNamespace
    from vpnd.text import WHITE_SPACE

    output = '{"verdict":"ok","rtt_ms":1}'
    assert matrix.capture(SimpleNamespace(stdout=WHITE_SPACE + output + WHITE_SPACE)) == {
        "verdict": "ok",
        "rtt_ms": 1,
    }
    for character in ["\x1c", "\x1d", "\x1e", "\x1f"]:
        for raw in [character + output, output + character]:
            assert matrix.capture(SimpleNamespace(stdout=raw)) == {
                "verdict": "error",
                "error_kind": "invalid-output",
            }
