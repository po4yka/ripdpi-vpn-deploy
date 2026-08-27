from pathlib import Path
import os
import shutil
import subprocess

import pytest


TEMPLATE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "cdn-front" / "templates" / "refresh-cf-prefixes.sh.j2"


def _script() -> str:
    return TEMPLATE.read_text()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o700)


def _run_refresh(tmp_path: Path, *, v4_mode: str = "valid", fail_lock: bool = False, fail_nginx_call: int = 0, fail_nft_check: bool = False, fail_nft_apply: bool = False, fail_reload: bool = False, fail_cache_restore: bool = False, origin_firewall: bool = True, seed_only: bool = False, nginx_active: bool = True) -> tuple[subprocess.CompletedProcess[str], Path, str]:
    prefix_dir = tmp_path / "prefixes"
    prefix_dir.mkdir()
    (prefix_dir / "cloudflare.v4").write_text("192.0.2.0/24\n")
    (prefix_dir / "cloudflare.v6").write_text("2001:db8:ffff::/48\n")
    (prefix_dir / "cloudflare.real_ip").write_text("old-real-ip\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    call_log = tmp_path / "calls.log"
    restore_fail_marker = tmp_path / "fail-cache-restore"
    _write_executable(fake_bin / "flock", """#!/usr/bin/env bash
exit "${FAIL_FLOCK:-0}"
""")
    _write_executable(fake_bin / "install", """#!/usr/bin/env bash
target="${!#}"
if [[ "$target" == *'.rollback.'* && "${FAIL_CACHE_RESTORE:-0}" == "1" && -e "$RESTORE_FAIL_MARKER" ]]; then
  exit 46
fi
exec "$REAL_INSTALL" "$@"
""")
    _write_executable(fake_bin / "curl", """#!/usr/bin/env bash
set -euo pipefail
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  */ips-v4)
    printf '%s\n' '198.51.100.0/25' '198.51.100.128/25' '203.0.113.0/25' '203.0.113.128/25' '192.0.2.0/24' > "$output"
    case "${V4_MODE:-valid}" in
      valid) ;;
      malformed) printf '%s\n' 'not-a-cidr' >> "$output" ;;
      singleton) printf '%s\n' '198.51.100.0/24' > "$output" ;;
      family) printf '%s\n' '2001:db8::/32' '198.51.100.0/25' '198.51.100.128/25' '203.0.113.0/25' '203.0.113.128/25' > "$output" ;;
      duplicate) printf '%s\n' '198.51.100.0/25' >> "$output" ;;
      *) exit 65 ;;
    esac
    ;;
  */ips-v6) printf '%s\n' '2001:db8:cf::/48' '2001:db8:100::/48' '2001:db8:200::/48' > "$output" ;;
  *) exit 64 ;;
esac
""")
    nginx_state = tmp_path / "nginx-state"
    nginx_state.write_text("0\n")
    _write_executable(fake_bin / "nginx", """#!/usr/bin/env bash
count="$(cat "$NGINX_STATE")"
count=$((count + 1))
printf '%s\n' "$count" > "$NGINX_STATE"
printf 'nginx %s\n' "$*" >> "$CALL_LOG"
if [[ "$count" == "${FAIL_NGINX_CALL:-0}" ]]; then
  exit 43
fi
exit 0
""")
    _write_executable(fake_bin / "nft", """#!/usr/bin/env bash
printf 'nft %s\n' "$*" >> "$CALL_LOG"
batch="${!#}"
cat "$batch" >> "$CALL_LOG"
if [[ "$*" == *'-c'* && "${FAIL_NFT_CHECK:-0}" == "1" ]]; then
  exit 44
fi
if [[ "$*" != *'-c'* && "${FAIL_NFT_APPLY:-0}" == "1" ]]; then
  exit 42
fi
""")
    _write_executable(fake_bin / "systemctl", """#!/usr/bin/env bash
printf 'systemctl %s\n' "$*" >> "$CALL_LOG"
if [[ "$1" == "is-active" ]]; then
  [[ "${NGINX_ACTIVE:-1}" == "1" ]] && exit 0
  exit 3
fi
if [[ "$1" == "reload" && "${NGINX_ACTIVE:-1}" != "1" ]]; then
  echo 'nginx.service is not active, cannot reload.' >&2
  exit 3
fi
if [[ "${FAIL_RELOAD:-0}" == "1" ]]; then
  touch "$RESTORE_FAIL_MARKER"
  exit 45
fi
exit 0
""")
    rendered = _script().replace("{{ cdn_front.cf_prefix_dir }}", str(prefix_dir)).replace("{{ cdn_front.origin_firewall | string | lower }}", "true" if origin_firewall else "false")
    script = tmp_path / "refresh.sh"
    _write_executable(script, rendered)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "CALL_LOG": str(call_log),
        "NGINX_STATE": str(nginx_state),
        "V4_MODE": v4_mode,
        "NGINX_ACTIVE": "1" if nginx_active else "0",
        "FAIL_FLOCK": "1" if fail_lock else "0",
        "FAIL_NGINX_CALL": str(fail_nginx_call),
        "FAIL_NFT_CHECK": "1" if fail_nft_check else "0",
        "FAIL_NFT_APPLY": "1" if fail_nft_apply else "0",
        "FAIL_RELOAD": "1" if fail_reload else "0",
        "FAIL_CACHE_RESTORE": "1" if fail_cache_restore else "0",
        "REAL_INSTALL": shutil.which("install", path=os.environ["PATH"]) or "/usr/bin/install",
        "RESTORE_FAIL_MARKER": str(restore_fail_marker),
    }
    result = subprocess.run([str(script), *(["--seed-only"] if seed_only else [])], capture_output=True, text=True, env=env)
    return result, prefix_dir, call_log.read_text() if call_log.exists() else ""


def test_every_downloaded_prefix_is_validated_with_ipaddress():
    script = _script()

    assert "ipaddress.ip_network" in script
    assert "network.version != expected_version" in script
    assert "minimum_count" in script
    assert "line != line.strip()" in script
    assert "grep -Eq" not in script


def test_nftables_sets_are_replaced_in_one_checked_transaction():
    script = _script()

    assert 'nft -c -f "$WORK/nft.batch"' in script
    assert 'nft -f "$WORK/nft.batch"' in script
    assert script.count("flush set inet filter cdn_front_origins") == 2
    assert "nft add element" not in script
    assert "2>/dev/null || true" not in script
    assert 'flock -n 9' in script
    assert script.index("NFT_APPLIED=1") < script.index('nft -f "$WORK/nft.batch"')


def test_candidates_are_validated_before_cache_publish_and_reload_is_strict():
    script = _script()

    candidate_check = script.index('nginx -t -q -c "$WORK/nginx-candidate.conf"')
    cache_stage = script.index('install -m 0644 "$WORK/v4"')
    nft_apply = script.index('nft -f "$WORK/nft.batch"')
    cache_publish = script.index('mv -f "$STAGED_V4"')
    reload_call = script.rindex("\nreload_nginx\n")
    assert candidate_check < cache_stage < nft_apply < cache_publish < reload_call
    assert script.index("INTEGRATED_PROBE=1") < script.index('mv -f "$STAGED_REAL_IP" "$PREFIX_DIR/cloudflare.real_ip"')
    assert "systemctl reload nginx 2>/dev/null || true" not in script


def test_malformed_line_keeps_previous_caches_and_skips_live_changes(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, v4_mode="malformed")

    assert result.returncode != 0
    assert (prefix_dir / "cloudflare.v4").read_text() == "192.0.2.0/24\n"
    assert (prefix_dir / "cloudflare.v6").read_text() == "2001:db8:ffff::/48\n"
    assert "nft " not in calls
    assert "systemctl " not in calls


@pytest.mark.parametrize("v4_mode", ["singleton", "family", "duplicate"])
def test_implausible_or_semantically_invalid_lists_are_rejected(tmp_path, v4_mode):
    result, prefix_dir, calls = _run_refresh(tmp_path, v4_mode=v4_mode)

    assert result.returncode != 0
    assert (prefix_dir / "cloudflare.v4").read_text() == "192.0.2.0/24\n"
    assert "nft " not in calls


def test_competing_refresh_is_rejected_before_download_or_mutation(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, fail_lock=True)

    assert result.returncode != 0
    assert (prefix_dir / "cloudflare.real_ip").read_text() == "old-real-ip\n"
    assert not calls


def test_full_nginx_candidate_failure_restores_old_include_before_nft(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, fail_nginx_call=2)

    assert result.returncode == 43
    assert (prefix_dir / "cloudflare.real_ip").read_text() == "old-real-ip\n"
    assert "nft " not in calls
    assert "systemctl " not in calls


def test_nft_preflight_failure_keeps_previous_caches_and_skips_reload(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, fail_nft_check=True)

    assert result.returncode == 44
    assert (prefix_dir / "cloudflare.v4").read_text() == "192.0.2.0/24\n"
    assert "nft -c -f" in calls
    assert "systemctl " not in calls


def test_nft_apply_failure_keeps_previous_caches_and_skips_reload(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, fail_nft_apply=True)

    assert result.returncode == 42
    assert (prefix_dir / "cloudflare.v4").read_text() == "192.0.2.0/24\n"
    assert (prefix_dir / "cloudflare.real_ip").read_text() == "old-real-ip\n"
    assert "nft -c -f" in calls
    assert "flush set inet filter cdn_front_origins\n" in calls
    assert "systemctl " not in calls


def test_success_replaces_caches_applies_batch_and_reloads(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (prefix_dir / "cloudflare.v4").read_text().splitlines()[0] == "198.51.100.0/25"
    assert (prefix_dir / "cloudflare.v6").read_text().splitlines()[0] == "2001:db8:cf::/48"
    assert "add element inet filter cdn_front_origins { 198.51.100.0/25" in calls
    assert "add element inet filter cdn_front_origins_v6 { 2001:db8:cf::/48" in calls
    assert calls.count("nft -f") == 1
    assert "systemctl reload nginx" in calls


def test_reload_failure_restores_previous_caches_and_nftables(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, fail_reload=True)

    assert result.returncode == 45
    assert (prefix_dir / "cloudflare.v4").read_text() == "192.0.2.0/24\n"
    assert (prefix_dir / "cloudflare.real_ip").read_text() == "old-real-ip\n"
    assert calls.count("nft -f") == 2


def test_cache_rollback_failure_is_reported_and_skips_rollback_reload(tmp_path):
    result, _, calls = _run_refresh(tmp_path, fail_reload=True, fail_cache_restore=True)

    assert result.returncode == 45
    assert "cache rollback failed" in result.stderr
    assert calls.count("systemctl reload nginx") == 1


def test_origin_firewall_disabled_does_not_require_nft(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, origin_firewall=False)

    assert result.returncode == 0, result.stderr
    assert (prefix_dir / "cloudflare.v4").read_text().splitlines()[0] == "198.51.100.0/25"
    assert "nft " not in calls
    assert "systemctl reload nginx" in calls


def test_cold_seed_publishes_validated_prefixes_without_starting_nginx(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, seed_only=True, nginx_active=False)

    assert result.returncode == 0, result.stderr
    assert (prefix_dir / "cloudflare.v4").read_text().startswith("198.51.100.0/25")
    assert "nginx -t" in calls
    assert "systemctl reload" not in calls
    assert "systemctl start" not in calls


def test_seed_only_rejects_an_active_nginx_before_mutation(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, seed_only=True)

    assert result.returncode != 0
    assert (prefix_dir / "cloudflare.real_ip").read_text() == "old-real-ip\n"
    assert "nft " not in calls
    assert "nginx -t" not in calls


def test_regular_refresh_does_not_pass_when_nginx_is_stopped(tmp_path):
    result, prefix_dir, calls = _run_refresh(tmp_path, nginx_active=False)

    assert result.returncode != 0
    assert (prefix_dir / "cloudflare.real_ip").read_text() == "old-real-ip\n"
    assert "systemctl reload nginx" in calls


def test_role_starts_nginx_only_after_the_desired_site_is_validated():
    tasks = (TEMPLATE.parents[1] / "tasks/main.yml").read_text()
    assert "--seed-only" in tasks
    assert "policy_rc_d: 101" in tasks, "package install must not start the default listener"
    assert tasks.index("Disable default nginx site") < tasks.index("Seed CF prefix list")
    validate = tasks.index("name: Validate the full nginx config")
    start = tasks.index("name: Ensure nginx is enabled and started after validation")
    timer = tasks.index("name: Enable prefix-refresh timer")
    assert tasks.index("name: Drop nginx CDN-front site") < validate < start < timer
