"""The probing summary counts nginx 403/444 responses from the decoy vhost logs."""

import datetime as dt
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "probing_summary_remote", ROOT / "scripts" / "probing-summary-remote.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _line(when: dt.datetime, status: int) -> str:
    stamp = when.strftime("%d/%b/%Y:%H:%M:%S %z")
    return f'- - - [{stamp}] "GET /wp-login.php HTTP/1.1" {status} 153 "-" "-"\n'


def test_nginx_events_come_from_every_vhost_log_and_skip_absent_files(tmp_path, monkeypatch):
    module = _load()
    now = module.NOW
    primary = tmp_path / "vpn-xhttp.access.log"
    primary.write_text(
        _line(now - dt.timedelta(hours=1), 403)
        + _line(now - dt.timedelta(hours=2), 200)
        + _line(now - dt.timedelta(hours=3), 403)
        + _line(now - dt.timedelta(days=8), 403)
    )
    self_steal = tmp_path / "reality-self-steal.access.log"
    self_steal.write_text(_line(now - dt.timedelta(hours=26), 444))
    (tmp_path / "access.log").write_text(_line(now - dt.timedelta(hours=1), 403) * 5)
    monkeypatch.setattr(module, "NGINX_ACCESS_LOGS", (
        primary, tmp_path / "vpn-xhttp-fallback.access.log", self_steal))

    events = module._read_nginx_403()

    assert len(events) == 3
    assert sorted(module._bucket_hour(ts) for ts, _ in events) == sorted(
        module._bucket_hour(now - dt.timedelta(hours=h)) for h in (1, 3, 26))
    assert {ip for _, ip in events} == {"-"}
