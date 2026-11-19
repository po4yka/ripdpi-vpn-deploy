"""Field-report ingest on the subscription host (SEC-1795086333272606).

The service runs as a subprocess on loopback with the shared contract
validator, so status codes, metrics output and logs are observed directly.
"""
from __future__ import annotations

import copy
import http.client
import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ROLE = ROOT / "ansible/roles/subscription-host"
SERVICE = ROLE / "files/vpn-field-report.py"
GOLDEN = json.loads((ROOT / "contract/client-field-report.golden.json").read_text())
TOKEN = "cohortTokenCurrent_0000000001"
PREVIOUS = "cohortTokenPrevious_000000002"
FIELD_REPORT_PATH = "/v1/field-report"


def _config(tmp_path: Path, **overrides) -> dict:
    textfile_dir = tmp_path / "textfile"
    textfile_dir.mkdir(exist_ok=True)
    config = {
        "listen": "127.0.0.1",
        "path": FIELD_REPORT_PATH,
        "max_body_bytes": 65536,
        "rate_per_second": 100,
        "rate_burst": 100,
        "min_attempts": 5,
        "asn_top_n": 20,
        "country_top_n": 10,
        "window_seconds": 3600,
        "max_series": 400,
        "server_refs": ["p0-reality-upcloud-prod", "p2-hysteria2-upcloud-prod"],
        "textfile": str(textfile_dir / "vpn_field_report.prom"),
        "schema": str(ROOT / "contract/client-field-report.schema.json"),
        "validator": str(ROOT / "scripts/validate-field-report.py"),
    }
    config.update(overrides)
    return config


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def ingest(tmp_path):
    processes = []

    def start(tokens: dict | None = None, **overrides):
        config = _config(tmp_path, port=_free_port(), **overrides)
        (tmp_path / "config.json").write_text(json.dumps(config))
        (tmp_path / "tokens.json").write_text(json.dumps(tokens or {"current": TOKEN}))
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(SERVICE), "--config", str(tmp_path / "config.json"),
             "--tokens", str(tmp_path / "tokens.json")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        processes.append(process)
        deadline = time.monotonic() + 10
        while not Path(config["textfile"]).exists():
            assert process.poll() is None, process.stderr.read()
            assert time.monotonic() < deadline
            time.sleep(0.05)
        for _ in range(100):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", config["port"])) == 0:
                    break
            time.sleep(0.05)
        return process, config

    yield start
    for process in processes:
        process.terminate()
        process.wait(timeout=5)


def _post(config: dict, body: bytes, token: str | None = TOKEN, length: int | None = None, path: str = FIELD_REPORT_PATH) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", config["port"], timeout=5)
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body) if length is None else length)}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    try:
        connection.request("POST", path, body=body if length is None else b"", headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


def _metrics(config: dict) -> str:
    return Path(config["textfile"]).read_text()


def _samples(text: str) -> dict[str, float]:
    return {line.rsplit(" ", 1)[0]: float(line.rsplit(" ", 1)[1]) for line in text.splitlines() if line and not line.startswith("#")}


def test_status_codes_and_only_an_accepted_report_changes_metrics(ingest):
    _, config = ingest(rate_per_second=0.001, rate_burst=4)
    empty = _metrics(config)
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    accepted = _metrics(config)
    assert accepted != empty
    assert _samples(accepted)['vpn_field_report_attempts_total{protocol="vless-reality",asn="other",country="other"}'] == 49

    extra = copy.deepcopy(GOLDEN)
    extra["device_id"] = "x"
    assert _post(config, json.dumps(extra).encode()) == 400
    assert _post(config, json.dumps(GOLDEN).encode(), token="wrongTokenValue_00000000000") == 401
    assert _post(config, b"", length=config["max_body_bytes"] + 1) == 413
    # 413 is refused before the limiter; this request takes the fourth and last burst token.
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    assert _post(config, json.dumps(GOLDEN).encode()) == 429
    assert _post(config, b"{}", path="/other") == 404


def test_rejections_leave_metrics_unchanged(ingest):
    _, config = ingest()
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    accepted = _metrics(config)
    bad_histogram = copy.deepcopy(GOLDEN)
    bad_histogram["buckets"][0]["latency_ms_histogram"][0] += 1
    for body, token in ((b"not json", TOKEN), (json.dumps(bad_histogram).encode(), TOKEN),
                        (json.dumps(GOLDEN).encode(), None), (json.dumps(GOLDEN).encode(), PREVIOUS)):
        assert _post(config, body, token=token) in (400, 401)
    assert _metrics(config) == accepted


def test_no_address_or_token_reaches_logs_metrics_or_state(ingest, tmp_path):
    process, config = ingest()
    assert _post(config, json.dumps(GOLDEN).encode()) == 202
    assert _post(config, b"{", token=TOKEN) == 400
    assert _post(config, json.dumps(GOLDEN).encode(), token="wrongTokenValue_00000000000") == 401
    process.terminate()
    stdout, stderr = process.communicate(timeout=5)
    textfile_dir = Path(config["textfile"]).parent
    stored = "".join(path.read_text() for path in textfile_dir.iterdir())
    for needle in ("127.0.0.1", TOKEN, "wrongTokenValue"):
        assert needle not in stdout + stderr
        assert needle not in stored
    assert [path.name for path in textfile_dir.iterdir()] == ["vpn_field_report.prom"]


def test_previous_token_is_accepted_only_during_its_overlap(ingest):
    _, config = ingest({"current": TOKEN, "previous": PREVIOUS, "previous_valid_until": "2999-01-01T00:00:00Z"})
    assert _post(config, json.dumps(GOLDEN).encode(), token=PREVIOUS) == 202
    assert _post(config, json.dumps(GOLDEN).encode(), token=TOKEN) == 202


def test_previous_token_is_rejected_after_its_overlap(ingest):
    _, config = ingest({"current": TOKEN, "previous": PREVIOUS, "previous_valid_until": "2000-01-01T00:00:00Z"})
    assert _post(config, json.dumps(GOLDEN).encode(), token=PREVIOUS) == 401
    assert _post(config, json.dumps(GOLDEN).encode(), token=TOKEN) == 202


def _bucket(attempts: int, protocol: str = "xhttp") -> dict:
    return {"server_ref": "p0-reality-upcloud-prod", "protocol": protocol, "outcome": "success", "attempts": attempts,
            "latency_ms_histogram": [attempts, 0, 0, 0, 0, 0, 0, 0]}


def test_buckets_under_the_configured_floor_are_dropped_and_counted(ingest):
    _, config = ingest(min_attempts=10)
    report = copy.deepcopy(GOLDEN)
    report["buckets"] = [_bucket(7), _bucket(10)]
    assert _post(config, json.dumps(report).encode()) == 202
    samples = _samples(_metrics(config))
    assert samples['vpn_field_report_attempts_total{protocol="xhttp",asn="other",country="other"}'] == 10
    assert samples['vpn_field_report_endpoint_attempts_total{protocol="xhttp",server_ref="p0-reality-upcloud-prod"}'] == 10
    assert samples["vpn_field_report_dropped_buckets_total"] == 1
    assert samples["vpn_field_report_reports_total"] == 1


@pytest.mark.parametrize("buckets", [[_bucket(4), _bucket(5)], [_bucket(4)]], ids=["mixed", "all-under"])
def test_a_bucket_under_the_contract_floor_rejects_the_report_without_counting(ingest, buckets):
    _, config = ingest()
    before = _metrics(config)
    report = copy.deepcopy(GOLDEN)
    report["buckets"] = buckets
    assert _post(config, json.dumps(report).encode()) == 400
    assert _metrics(config) == before


@pytest.mark.parametrize("field", ["country", "server_ref", "protocol", "failure_stage"])
@pytest.mark.parametrize("suffix", ["\n", '"'])
def test_label_strings_with_a_newline_or_quote_are_rejected(ingest, field, suffix):
    _, config = ingest()
    before = _metrics(config)
    report = copy.deepcopy(GOLDEN)
    target = report["network"] if field == "country" else report["buckets"][1]
    target[field] += suffix
    assert _post(config, json.dumps(report).encode()) == 400
    assert _metrics(config) == before


def test_rendered_label_values_are_escaped(tmp_path):
    aggregate = _module().Aggregate(_config(tmp_path), [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"])
    aggregate.attempts[("xhttp", "64500", 'Z"\\\n')] = 5
    assert 'vpn_field_report_attempts_total{protocol="xhttp",asn="64500",country="Z\\"\\\\\\n"} 5' in aggregate.render()


def _module():
    spec = importlib.util.spec_from_file_location("vpn_field_report_service", SERVICE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_labels_stay_bounded_for_many_networks_and_unknown_endpoints(tmp_path):
    module = _module()
    max_series = 120
    config = _config(tmp_path, max_series=max_series)
    aggregate = module.Aggregate(config, [50, 100, 250, 500, 1000, 2500, 5000, "+Inf"])
    protocols = ["vless-reality", "xhttp", "hysteria2", "amneziawg", "naiveproxy", "local-desync"]
    for window in (0, 3600):
        for index in range(1000):
            report = copy.deepcopy(GOLDEN)
            report["network"] = {"asn": 64000 + index, "country": "ZZ" if index % 2 else "ZY", "network_type": "wifi"}
            report["buckets"] = [
                {"server_ref": f"unknown-{index}", "protocol": protocols[index % 6], "outcome": "failure",
                 "failure_stage": "tcp_reset", "attempts": 5 + index, "latency_ms_histogram": [0, 0, 0, 0, 0, 0, 0, 5 + index]},
            ]
            aggregate.add(report, window + index * 0.001)
    samples = _samples(aggregate.render())
    asns = {key.split('asn="')[1].split('"')[0] for key in samples if 'asn="' in key}
    # The 20 networks with the most attempts in the first window, and "other".
    assert asns == {str(64000 + index) for index in range(980, 1000)} | {"other"}
    assert {key.split('server_ref="')[1].split('"')[0] for key in samples if "server_ref=" in key} == {"other"}
    # Label-bearing counters: the budget plus one overflow set per protocol for
    # attempts, failures per stage and both endpoint families; then 6 latency
    # series of 9 samples and the two unlabelled counters.
    counters = [key for key in samples if "latency" not in key and "{" in key]
    assert len(counters) <= max_series + 6 * (1 + 11 + 2)
    assert len(samples) <= max_series + 6 * (1 + 11 + 2) + 6 * 9 + 2


def _rendered(name: str, **field_report) -> str:
    spec = importlib.util.spec_from_file_location("field_report_renderer", ROOT / "scripts/check-templates-render.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    variables = renderer.merge_render_vars()
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]
    variables["subscription_field_report"] = {**defaults, "enabled": True, **field_report}
    return renderer.render_template(ROLE / "templates" / name, variables)


def test_nginx_location_limits_size_and_rate_and_keeps_body_in_memory():
    vhost = _rendered("subscription.conf.j2", max_body_bytes=32768)
    location = vhost.split("location = /v1/field-report {", 1)[1].split("\n    }", 1)[0]
    assert "limit_except POST { deny all; }" in location
    assert "limit_req zone=vpn_field_report_per_ip burst=20 nodelay;" in location
    assert "limit_req_status 429;" in location
    assert "client_max_body_size 32768;" in location
    assert "client_body_buffer_size 32768;" in location
    assert "access_log /var/log/nginx/vpn-sub.categorical.log vpn_sub_category;" in location
    assert "error_log /dev/null crit;" in location
    assert "remote_addr" not in location and "X-Real-IP" not in location and "X-Forwarded-For" not in location
    assert "limit_req_zone $binary_remote_addr zone=vpn_field_report_per_ip:10m rate=30r/m;" in _rendered("rate-limit.conf.j2")
    assert "field-report" not in _rendered("subscription.conf.j2", enabled=False)


def test_unit_delivers_tokens_as_credential_and_keeps_the_hardening_floor():
    unit = _rendered("vpn-field-report.service.j2")
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "LoadCredential=cohort-tokens:/etc/vpn-field-report/cohort-tokens.json" in unit
    assert "--tokens %d/cohort-tokens" in exec_start and "Environment=" not in unit
    for directive in ("User=vpn-field-report", "NoNewPrivileges=true", "ProtectSystem=strict", "PrivateTmp=true",
                      "ProtectHome=true", "ProtectKernelTunables=true", "ProtectKernelModules=true",
                      "ProtectControlGroups=true", "RestrictNamespaces=true", "LockPersonality=true",
                      "RestrictRealtime=true", "RestrictSUIDSGID=true", "SystemCallArchitectures=native",
                      "CapabilityBoundingSet=\n", "IPAddressDeny=any", "IPAddressAllow=localhost",
                      "ReadWritePaths=/var/lib/node_exporter/textfile\n"):
        assert directive in unit
    config = json.loads(_rendered("vpn-field-report.json.j2", server_refs=["p0-reality-upcloud-prod"]))
    assert config["listen"] == "127.0.0.1"
    assert config["server_refs"] == ["p0-reality-upcloud-prod"]


def _settings_assert_holds(**changes) -> bool:
    """Evaluate the role's real settings assert with the pinned ansible-core templar."""
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    tasks = yaml.safe_load((ROLE / "tasks/field-report.yml").read_text())
    task = next(task for task in tasks if task["name"] == "Require bounded field-report ingest settings and cohort tokens")
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["subscription_field_report"]
    field_report = {"cohort_token": TOKEN, "previous_cohort_token": PREVIOUS,
                    "previous_cohort_token_valid_until": "2999-01-01T00:00:00Z"}
    settings = {**defaults, "server_refs": ["p0-reality-upcloud-prod"]}
    for key, value in changes.items():
        (field_report if key in field_report else settings)[key] = value
    templar = Templar(loader=DataLoader(), variables={"subscription_field_report": settings, "field_report": field_report})
    return all(templar.template(trust_as_template("{{ " + condition + " }}")) for condition in task["ansible.builtin.assert"]["that"])


@pytest.mark.parametrize("key", ["path", "cohort_token", "previous_cohort_token", "previous_cohort_token_valid_until",
                                 "server_refs"])
def test_settings_assert_refuses_a_trailing_newline(key):
    assert _settings_assert_holds()
    value = {"path": FIELD_REPORT_PATH, "cohort_token": TOKEN, "previous_cohort_token": PREVIOUS,
             "previous_cohort_token_valid_until": "2999-01-01T00:00:00Z", "server_refs": "p0-reality-upcloud-prod"}[key]
    assert not _settings_assert_holds(**{key: [value + "\n"] if key == "server_refs" else value + "\n"})
