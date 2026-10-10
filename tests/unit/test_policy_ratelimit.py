"""Regression guard for the policy-ratelimit daemon.

The daemon ships as a Jinja2 template; this test renders it against the role
defaults, execs the rendered module, and exercises the pure `RateLimiter`
decision core against golden Xray-core v26.3.27 log fixtures.

It pins the finding from docs/AUDIT-SILENT-FAILURE.md: the daemon bans
authenticated clients whose traffic is routed to the `block` outbound (or
rejected at the VLESS layer), and it can NOT see external REALITY probes —
those land in error.log, not the access.log it tails. The fixtures encode
both: blackholed/rejected offenders must be banned; benign clients, RFC1918
sources, and the REALITY error-log probe line must never be.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = REPO_ROOT / "ansible" / "roles" / "policy-ratelimit"
TEMPLATE = ROLE / "templates" / "policy-ratelimit.py.j2"
DEFAULTS = ROLE / "defaults" / "main.yml"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
ACCESS_LOG = FIXTURES / "xray-access-sample.log"
ERROR_LOG = FIXTURES / "xray-error-sample.log"

NOW = 1000.0  # constant logical clock — all events land inside one window


def _render_daemon() -> dict:
    """Render the .j2 against role defaults and exec it into a namespace.

    Rendering here also asserts the template has no Jinja syntax break and
    produces importable Python.
    """
    jinja2 = pytest.importorskip("jinja2")
    defaults = yaml.safe_load(DEFAULTS.read_text())
    env = jinja2.Environment(keep_trailing_newline=True)
    src = env.from_string(TEMPLATE.read_text()).render(**defaults)
    ns: dict = {"__name__": "policy_ratelimit_rendered"}
    exec(compile(src, str(TEMPLATE), "exec"), ns)  # noqa: S102 — trusted template
    return ns


@pytest.fixture(scope="module")
def daemon() -> dict:
    return _render_daemon()


def _access_lines() -> list[str]:
    return [ln for ln in ACCESS_LOG.read_text().splitlines() if ln.strip()]


def _error_lines() -> list[str]:
    return [ln for ln in ERROR_LOG.read_text().splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# Defaults sanity — thresholds the fixtures were authored against
# ---------------------------------------------------------------------------


def test_defaults_match_fixture_assumptions():
    cfg = yaml.safe_load(DEFAULTS.read_text())["policy_ratelimit"]
    assert cfg["rejects_per_window"] == 5
    assert cfg["window_seconds"] == 60
    assert "dead_contract_min_lines" in cfg


# ---------------------------------------------------------------------------
# classify_line — token coupling to the real Xray access-log shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sep", ["->", ">>", "==>"])
def test_block_tag_matches_every_detour_separator(daemon, sep):
    line = f"... accepted udp:1.2.3.4:443 [vless-reality {sep} block] email: x"
    assert daemon["classify_line"](line) == "block"


def test_benign_direct_is_not_an_event(daemon):
    line = "... accepted tcp:1.2.3.4:443 [vless-reality -> direct] email: x"
    assert daemon["classify_line"](line) is None


def test_dns_out_detour_is_not_an_event(daemon):
    line = "... accepted udp:1.2.3.4:53 [vless-reality -> dns-out] email: x"
    assert daemon["classify_line"](line) is None


def test_rejected_status_is_an_event(daemon):
    line = "from tcp:203.0.113.99:53000 rejected tcp:1.2.3.4:443"
    assert daemon["classify_line"](line) == "rejected"


def test_word_block_inside_a_hostname_is_not_matched(daemon):
    # "block" appearing outside the detour bracket must not trip BLOCK_RE.
    line = (
        "... accepted tcp:1.2.3.4:443 [vless-reality -> direct] email: blockchain-user"
    )
    assert daemon["classify_line"](line) is None


# ---------------------------------------------------------------------------
# REALITY probe lines (error.log) — the design limitation, encoded as a test
# ---------------------------------------------------------------------------


def test_reality_probe_lines_are_never_actionable(daemon):
    """External probes hit error.log with no block/rejected token — the
    daemon must classify every one as None, proving it cannot ban probers."""
    for line in _error_lines():
        assert daemon["classify_line"](line) is None, line


def test_error_fixture_actually_contains_probe_lines():
    lines = _error_lines()
    assert lines, "error fixture is empty"
    assert all("processed invalid connection" in ln for ln in lines)


# ---------------------------------------------------------------------------
# is_exempt_ip — RFC1918 / loopback guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    ["10.0.0.5", "127.0.0.1", "192.168.1.1", "172.16.0.1", "172.31.255.254", "0.0.0.0"],
)
def test_private_ips_are_exempt(daemon, ip):
    assert daemon["is_exempt_ip"](ip) is True


@pytest.mark.parametrize(
    "ip", ["203.0.113.55", "198.51.100.10", "172.15.0.1", "172.32.0.1", "8.8.8.8"]
)
def test_public_ips_are_not_exempt(daemon, ip):
    assert daemon["is_exempt_ip"](ip) is False


# ---------------------------------------------------------------------------
# Source-IP extraction — ban the client, not a private destination
# ---------------------------------------------------------------------------


def test_source_ip_is_extracted_not_private_destination(daemon):
    # block-by-private-destination rule: source is public, dest is RFC1918.
    line = (
        "from tcp:203.0.113.55:52050 accepted tcp:192.168.1.1:80 "
        "[vless-reality -> block] email: bob"
    )
    assert daemon["IP_RE"].search(line).group(1) == "203.0.113.55"


# ---------------------------------------------------------------------------
# End-to-end: feed the golden access log, assert the exact ban set
# ---------------------------------------------------------------------------


def test_bans_exactly_the_offenders_from_golden_log(daemon):
    limiter = daemon["RateLimiter"](5, 60, 300)
    banned: list[str] = []
    for line in _access_lines():
        ip = limiter.observe(line, NOW)
        if ip is not None:
            banned.append(ip)

    # 203.0.113.55 (6 block events) and 203.0.113.99 (5 rejected) cross the
    # threshold; nothing else does.
    assert set(banned) == {"203.0.113.55", "203.0.113.99"}
    # No benign client, below-threshold client, or RFC1918 source is banned.
    assert "198.51.100.10" not in banned  # benign direct x8
    assert "198.51.100.20" not in banned  # only 2 block events (< 5)
    assert "10.0.0.5" not in banned  # RFC1918 source, exempt
    assert limiter.bans == 2


def test_counters_reflect_only_non_exempt_events(daemon):
    limiter = daemon["RateLimiter"](5, 60, 300)
    for line in _access_lines():
        limiter.observe(line, NOW)
    assert limiter.lines == 27  # every line tailed
    # 6 (.55) + 5 (.99) + 2 (.20) = 13; the 6 RFC1918 lines are not events.
    assert limiter.events == 13


def test_below_threshold_does_not_ban(daemon):
    limiter = daemon["RateLimiter"](5, 60, 300)
    line = (
        "from tcp:198.51.100.20:40001 accepted udp:1.2.3.4:443 "
        "[vless-reality -> block] email: carol"
    )
    bans = [limiter.observe(line, NOW) for _ in range(4)]
    assert all(b is None for b in bans)
    assert limiter.bans == 0


def test_window_expiry_prevents_ban(daemon):
    """Events spread beyond window_seconds must not accumulate to a ban."""
    limiter = daemon["RateLimiter"](5, 60, 300)
    line = (
        "from tcp:203.0.113.77:50000 accepted udp:1.2.3.4:443 "
        "[vless-reality -> block] email: x"
    )
    banned = [limiter.observe(line, float(t)) for t in range(0, 5 * 100, 100)]
    assert all(b is None for b in banned)  # 100s apart > 60s window


# ---------------------------------------------------------------------------
# Dead-contract gauge — a broken sink/token is observable, not silent
# ---------------------------------------------------------------------------


def test_dead_contract_flips_when_lines_but_no_events(daemon):
    limiter = daemon["RateLimiter"](5, 60, 300)
    benign = "... accepted tcp:1.2.3.4:443 [vless-reality -> direct] email: x"
    for _ in range(10):
        limiter.observe(benign, NOW)
    assert limiter.events == 0
    assert limiter.dead_contract(10) is True  # enough volume, zero events
    assert limiter.dead_contract(100) is False  # not enough volume yet


def test_dead_contract_clears_once_an_event_is_seen(daemon):
    limiter = daemon["RateLimiter"](5, 60, 300)
    benign = "... accepted tcp:1.2.3.4:443 [vless-reality -> direct] email: x"
    block = "... accepted udp:1.2.3.4:443 [vless-reality -> block] email: x"
    for _ in range(10):
        limiter.observe(benign, NOW)
    limiter.observe(block, NOW)
    assert limiter.events == 1
    assert limiter.dead_contract(5) is False  # an event was matched


def test_detector_health_metrics_report_success_input_progress_and_error_state(
    daemon, tmp_path, monkeypatch
):
    limiter = daemon["RateLimiter"](5, 60, 300)
    limiter.observe("benign input", NOW)
    limiter.errors = 1
    monkeypatch.setitem(daemon, "TEXTFILE_DIR", tmp_path)
    monkeypatch.setattr(daemon["time"], "time", lambda: NOW)

    daemon["flush_textfile"](limiter)
    metrics = (tmp_path / "vpn_policy_ratelimit.prom").read_text()

    for name, value in {
        "vpn_policy_ratelimit_collection_success": 1,
        "vpn_policy_ratelimit_last_success_timestamp_seconds": int(NOW),
        "vpn_policy_ratelimit_input_progress_total": 1,
        "vpn_policy_ratelimit_input_errors_total": 1,
    }.items():
        assert re.search(rf"^{name} {value}$", metrics, re.MULTILINE)
    assert 'vpn_policy_ratelimit_error_state{state="error"} 1' in metrics

    daemon["flush_textfile"](limiter)
    metrics = (tmp_path / "vpn_policy_ratelimit.prom").read_text()
    assert 'vpn_policy_ratelimit_error_state{state="ok"} 1' in metrics


def _event(ip):
    return f"from tcp:{ip}:40001 rejected tcp:1.2.3.4:443"


def test_idle_expiry_and_capacity_preserve_active_windows(daemon):
    limiter = daemon["RateLimiter"](3, 60, 300, max_sources=2)
    limiter.observe(_event("203.0.113.1"), 0)
    limiter.observe(_event("203.0.113.2"), 0)
    assert limiter.observe(_event("203.0.113.3"), 1) is None
    assert len(limiter.history) == 2
    assert limiter.capacity_drops == 1
    assert limiter.errors == 1
    assert limiter.observe(_event("203.0.113.1"), 2) is None
    assert limiter.observe(_event("203.0.113.1"), 3) == "203.0.113.1"
    limiter.expire(61)
    assert not limiter.history
    limiter.observe(_event("203.0.113.3"), 62)
    assert len(limiter.history) == 1


def test_metric_publication_ignores_legacy_temporary_symlink(
    daemon, tmp_path, monkeypatch
):
    victim = tmp_path / "victim"
    victim.write_text("must survive")
    (tmp_path / "vpn_policy_ratelimit.prom.tmp").symlink_to(victim)
    monkeypatch.setitem(daemon, "TEXTFILE_DIR", tmp_path)
    daemon["flush_textfile"](daemon["RateLimiter"](5, 60, 300))
    assert victim.read_text() == "must survive"
    output = tmp_path / "vpn_policy_ratelimit.prom"
    assert output.is_file() and output.stat().st_mode & 0o777 == 0o640


def test_metric_output_symlink_is_rejected(daemon, tmp_path, monkeypatch):
    victim = tmp_path / "victim"
    victim.write_text("must survive")
    output = tmp_path / "vpn_policy_ratelimit.prom"
    output.symlink_to(victim)
    limiter = daemon["RateLimiter"](5, 60, 300)
    monkeypatch.setitem(daemon, "TEXTFILE_DIR", tmp_path)
    daemon["flush_textfile"](limiter)
    assert victim.read_text() == "must survive"
    assert output.is_symlink()
    assert limiter.errors == 1


def test_idle_and_missing_input_ticks_are_distinct(daemon, tmp_path, monkeypatch):
    monkeypatch.setattr(daemon["time"], "sleep", lambda _: None)
    path = tmp_path / "access.log"
    follower = daemon["tail"](path)
    assert next(follower) == (None, False)
    path.write_text("")
    assert next(follower) == (None, True)
    with path.open("a") as stream:
        stream.write("new input\n")
    assert next(follower) == ("new input\n", True)
    follower.close()


def test_main_publishes_startup_and_idle_health(daemon, tmp_path, monkeypatch):
    times = iter([1000, 1000, 1016, 1016, 1032, 1032])
    monkeypatch.setattr(daemon["time"], "time", lambda: next(times, 1032))
    monkeypatch.setitem(daemon, "TEXTFILE_DIR", tmp_path)
    monkeypatch.setitem(
        daemon, "tail", lambda _: iter([(None, True), (None, True), (None, False)])
    )
    publications = []
    real_publish = daemon["publish_metrics"]
    monkeypatch.setitem(
        daemon,
        "publish_metrics",
        lambda value: (publications.append(value), real_publish(value)),
    )
    daemon["main"]()
    assert len(publications) == 3
    assert all(
        "vpn_policy_ratelimit_input_progress_total 0" in value for value in publications
    )
    assert "vpn_policy_ratelimit_input_available 0" in publications[-1]
    assert 'vpn_policy_ratelimit_error_state{state="error"} 1' in publications[-1]


def test_failed_atomic_publication_preserves_previous_complete_metrics(
    daemon, tmp_path, monkeypatch
):
    limiter = daemon["RateLimiter"](5, 60, 300)
    monkeypatch.setitem(daemon, "TEXTFILE_DIR", tmp_path)
    daemon["flush_textfile"](limiter)
    before = (tmp_path / "vpn_policy_ratelimit.prom").read_bytes()

    def reject_replace(*args, **kwargs):
        raise PermissionError("injected publication failure")

    monkeypatch.setattr(daemon["os"], "replace", reject_replace)
    limiter.observe("new line", NOW)
    daemon["flush_textfile"](limiter)
    assert (tmp_path / "vpn_policy_ratelimit.prom").read_bytes() == before
    assert limiter.errors == 1
    assert not list(tmp_path.glob(".policy-ratelimit-*"))


@pytest.mark.parametrize("rotation", ["truncate", "replace"])
def test_actual_tail_recovers_rotation_without_recounting_retained_input(
    daemon, tmp_path, monkeypatch, rotation
):
    monkeypatch.setattr(daemon["time"], "sleep", lambda _seconds: None)
    path = tmp_path / "access.log"
    path.write_text("retained history\n" * 20)
    follower = daemon["tail"](path)
    assert next(follower) == (None, True), "startup must not recount retained history"
    with path.open("a") as stream:
        stream.write("observed before rotation\n")
    assert next(follower) == ("observed before rotation\n", True)
    previous_inode = path.stat().st_ino
    if rotation == "truncate":
        path.write_text("observed after rotation\n")
        assert path.stat().st_ino == previous_inode
    else:
        replacement = tmp_path / "replacement.log"
        replacement.write_text("observed after rotation\n")
        replacement.replace(path)
        assert path.stat().st_ino != previous_inode
    assert next(follower) == ("observed after rotation\n", True)
    assert next(follower) == (
        None,
        True,
    ), "rotation must not count the new record twice"
    with path.open("a") as stream:
        stream.write("subsequent input\n")
    assert next(follower) == ("subsequent input\n", True)
    follower.close()
