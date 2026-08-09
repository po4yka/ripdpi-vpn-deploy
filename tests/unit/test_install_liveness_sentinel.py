"""Security-facing tests for sentinel onboarding."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "install-liveness-sentinel.sh"


def _exe(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_installer_keeps_awg_private_key_off_argv_and_uses_strict_ssh(tmp_path: Path) -> None:
    config = tmp_path / "liveness.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "probe_timeout_seconds": 15,
                "degraded_after_ms": 3000,
                "stale_after_seconds": 120,
                "failure_threshold": 3,
                "otp_ttl_seconds": 3600,
                "expected_runtime": {"sing_box": "1.14.0", "awg": "1.0.0"},
                "policies": [
                    {
                        "id": "fullstack",
                        "required_profiles": ["p0-reality", "p2-amneziawg"],
                        "min_failed_vantages": 1,
                    }
                ],
                "sentinels": [
                    {
                        "id": "tls-freeze-a",
                        "ssh_target": "sentinel-a",
                        "ssh_transport_host": "sentinel-direct",
                        "ssh_host_key_alias": "sentinel-a",
                        "policy": "fullstack",
                    }
                ],
            }
        )
    )
    emitted = tmp_path / "emitted.json"
    emitted.write_text(
        json.dumps(
            {
                "outbounds": [
                    {"type": "vless", "tag": "p0-reality-upcloud-prod", "uuid": "secret-uuid"}
                ]
            }
        )
    )
    emit_singbox = tmp_path / "emit-singbox"
    _exe(emit_singbox, f"#!/usr/bin/env bash\ncat {emitted}\n")
    emit_awg = tmp_path / "emit-awg"
    _exe(
        emit_awg,
        "#!/usr/bin/env bash\nprintf '[Interface]\\nPrivateKey = PASTE_CLIENT_PRIVATE_KEY_HERE\\nAddress = 10.66.66.2/32\\nDNS = 1.1.1.1\\n[Peer]\\nPublicKey = server\\n'\n",
    )
    audit_log = tmp_path / "audit-log"
    _exe(audit_log, "#!/usr/bin/env bash\nprintf 'audit %s\\n' \"$*\" >> \"$CALL_LOG\"\n")
    call_log = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
printf 'ssh' >> "$CALL_LOG"; printf ' <%s>' "$@" >> "$CALL_LOG"; printf '\n' >> "$CALL_LOG"
if [[ "$*" == *' id -un' ]]; then echo probe; exit 0; fi
if [[ "$*" == *'/usr/local/sbin/vpn-protocol-liveness' ]]; then
  printf '{"schema_version":1,"sentinel":"tls-freeze-a","observed_at":9999999999,"control":{"verdict":"ok"},"profiles":[{"profile":"p0-reality","verdict":"ok"},{"profile":"p2-amneziawg","verdict":"ok"}],"runtime":{"sing_box":"1.14.0","awg":"1.0.0"}}\n'
fi
""",
    )
    _exe(
        bin_dir / "scp",
        """#!/usr/bin/env bash
printf 'scp' >> "$CALL_LOG"; printf ' <%s>' "$@" >> "$CALL_LOG"; printf '\n' >> "$CALL_LOG"
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "CALL_LOG": str(call_log),
            "EMIT_SINGBOX": str(emit_singbox),
            "EMIT_AWG": str(emit_awg),
            "LIVENESS_SENTINEL_REGISTRY": str(tmp_path / "registry.json"),
            "AUDIT_LOG": str(audit_log),
        }
    )
    private_key = "PRIVATE_KEY_MUST_NOT_APPEAR"

    result = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--config",
            str(config),
            "--sentinel",
            "tls-freeze-a",
            "--client",
            "liveness-a",
            "--awg-private-key-stdin",
        ],
        input=private_key + "\n",
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = call_log.read_text()
    assert private_key not in calls + result.stdout + result.stderr
    assert "<StrictHostKeyChecking=yes>" in calls
    assert "<BatchMode=yes>" in calls
    for option in (
        "<HostName=sentinel-direct>",
        "<HostKeyAlias=sentinel-a>",
        "<ProxyCommand=none>",
        "<ControlMaster=no>",
        "<ControlPath=none>",
        "<ControlPersist=no>",
    ):
        assert option in calls
    assert "audit append-best-effort --action install-liveness-sentinel" in calls
    registry = json.loads((tmp_path / "registry.json").read_text())
    assert registry["sentinels"]["tls-freeze-a"]["client"] == "liveness-a"
    assert registry["sentinels"]["tls-freeze-a"]["ssh_transport_host"] == "sentinel-direct"
    assert registry["sentinels"]["tls-freeze-a"]["ssh_host_key_alias"] == "sentinel-a"


def test_installer_requires_private_key_from_stdin(tmp_path: Path) -> None:
    config = tmp_path / "liveness.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "expected_runtime": {"sing_box": "1.14.0", "awg": "1.0.0"},
                "policies": [{"id": "fullstack", "required_profiles": ["p2-amneziawg"]}],
                "sentinels": [{"id": "x", "ssh_target": "sentinel-x", "policy": "fullstack"}],
            }
        )
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), "--config", str(config), "--sentinel", "x", "--client", "x"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--awg-private-key-stdin" in result.stderr


def test_installer_supports_policy_without_amneziawg_key(tmp_path: Path) -> None:
    config = tmp_path / "liveness.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "probe_url": "https://www.gstatic.com/generate_204",
                "expected_status": 204,
                "expected_runtime": {"sing_box": "1.14.0", "awg": "1.0.0"},
                "policies": [{"id": "stream", "required_profiles": ["p0-reality"]}],
                "sentinels": [{"id": "stream-a", "ssh_target": "sentinel-a", "policy": "stream"}],
            }
        )
    )
    emit_singbox = tmp_path / "emit-singbox"
    _exe(
        emit_singbox,
        "#!/usr/bin/env bash\nprintf '{\"outbounds\":[{\"type\":\"vless\",\"tag\":\"p0-reality-upcloud-primary\"},{\"type\":\"vless\",\"tag\":\"p0-reality-upcloud-fallback\"}]}\n'\n",
    )
    emit_awg = tmp_path / "emit-awg"
    _exe(emit_awg, "#!/usr/bin/env bash\nexit 99\n")
    audit_log = tmp_path / "audit-log"
    _exe(audit_log, "#!/usr/bin/env bash\nexit 0\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
if [[ "$*" == *' id -un' ]]; then echo probe; exit 0; fi
if [[ "$*" == *'/usr/local/sbin/vpn-protocol-liveness' ]]; then
  printf '{"schema_version":1,"sentinel":"stream-a","control":{"verdict":"ok"},"profiles":[{"profile":"p0-reality","verdict":"ok"}]}\n'
fi
""",
    )
    _exe(
        bin_dir / "scp",
        """#!/usr/bin/env bash
for arg in "$@"; do
  if [[ -f "$arg" ]]; then tar -xzf "$arg" -C "$SCP_CAPTURE"; fi
done
""",
    )
    scp_capture = tmp_path / "scp-capture"
    scp_capture.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "EMIT_SINGBOX": str(emit_singbox),
            "EMIT_AWG": str(emit_awg),
            "LIVENESS_SENTINEL_REGISTRY": str(tmp_path / "registry.json"),
            "AUDIT_LOG": str(audit_log),
            "SCP_CAPTURE": str(scp_capture),
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "--config", str(config), "--sentinel", "stream-a", "--client", "stream-a"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "registry.json").read_text())["sentinels"]["stream-a"]["client"] == "stream-a"
    installed = json.loads((scp_capture / "config.json").read_text())
    assert installed["sing_box"]["profiles"]["p0-reality"] == [18081, 18082]
    sing_box = json.loads((scp_capture / "sing-box.json").read_text())
    assert [item["type"] for item in sing_box["outbounds"]] == ["vless", "vless"]
    assert len(sing_box["inbounds"]) == 2
    assert "tar --no-xattrs" in SCRIPT.read_text()
