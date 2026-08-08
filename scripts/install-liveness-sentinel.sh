#!/usr/bin/env bash
# Provision one managed client-path sentinel without transferring SOPS material.
#
# Usage:
#   scripts/install-liveness-sentinel.sh --config FILE --sentinel ID --client NAME --awg-private-key-stdin
#
# When the selected policy includes AmneziaWG, its private key is read as one line from stdin. The command validates the sentinel policy, emits only the named client's required profiles, installs a fixed root-owned remote command through strict SSH, runs one authenticated probe, and records the client assignment locally.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EMIT_SINGBOX="${EMIT_SINGBOX:-${REPO_ROOT}/scripts/emit-singbox.sh}"
EMIT_AWG="${EMIT_AWG:-${REPO_ROOT}/scripts/emit-awg.sh}"
RUNNER="${LIVENESS_SENTINEL_RUNNER:-${REPO_ROOT}/scripts/vpn-protocol-liveness.py}"
REGISTRY="${LIVENESS_SENTINEL_REGISTRY:-${HOME}/.config/vpn-provision/liveness-sentinels.json}"
AUDIT_LOG="${AUDIT_LOG:-${REPO_ROOT}/scripts/audit-log.sh}"

CONFIG=""
SENTINEL=""
CLIENT=""
READ_AWG_STDIN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --sentinel) SENTINEL="$2"; shift 2 ;;
    --client) CLIENT="$2"; shift 2 ;;
    --awg-private-key-stdin) READ_AWG_STDIN=1; shift ;;
    -h|--help)
      echo "usage: $0 --config FILE --sentinel ID --client NAME --awg-private-key-stdin" >&2
      exit 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -f "$CONFIG" ]] || { echo "configuration not found: $CONFIG" >&2; exit 1; }
[[ "$SENTINEL" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]] || { echo "invalid sentinel id" >&2; exit 1; }
[[ "$CLIENT" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || { echo "invalid client name" >&2; exit 1; }

for tool in python3 ssh scp tar; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing: $tool" >&2; exit 1; }
done

IFS=$'\t' read -r SSH_TARGET REQUIRED_PROFILES PROBE_URL EXPECTED_STATUS TIMEOUT_SECONDS DEGRADED_AFTER_MS SING_BOX_VERSION AWG_VERSION < <(python3 - "$CONFIG" "$SENTINEL" <<'PY'
import sys, yaml
config = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
sentinel = next((s for s in config.get("sentinels", []) if s.get("id") == sys.argv[2]), None)
if not sentinel:
    raise SystemExit("sentinel is not declared in configuration")
policy = next((p for p in config.get("policies", []) if p.get("id") == sentinel.get("policy")), None)
if not policy:
    raise SystemExit("sentinel policy is not declared")
runtime = config.get("expected_runtime") or {}
print("\t".join(map(str, [sentinel["ssh_target"], ",".join(policy["required_profiles"]), config["probe_url"], config["expected_status"], config.get("probe_timeout_seconds", 15), config.get("degraded_after_ms", 3000), runtime["sing_box"], runtime["awg"]])))
PY
)

AWG_PRIVATE_KEY=""
if [[ ",${REQUIRED_PROFILES}," == *",p2-amneziawg,"* ]]; then
  if (( ! READ_AWG_STDIN )); then
    echo "--awg-private-key-stdin is required when policy requires p2-amneziawg; private keys are never accepted in argv" >&2
    exit 1
  fi
  IFS= read -r AWG_PRIVATE_KEY
  [[ -n "$AWG_PRIVATE_KEY" ]] || { echo "empty AWG private key on stdin" >&2; exit 1; }
fi

python3 - "$REGISTRY" "$SENTINEL" "$CLIENT" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
try:
    registry = json.loads(path.read_text())
except (OSError, json.JSONDecodeError):
    registry = {"schema_version": 1, "sentinels": {}}
for sentinel_id, entry in registry.get("sentinels", {}).items():
    if entry.get("client") == sys.argv[3] and sentinel_id != sys.argv[2]:
        raise SystemExit(f"client {sys.argv[3]} is already assigned to sentinel {sentinel_id}")
PY

umask 077
WORK="$(mktemp -d -t vpn-liveness-install.XXXXXX)"
cleanup() {
  unset AWG_PRIVATE_KEY
  if command -v shred >/dev/null 2>&1; then
    find "$WORK" -type f -exec shred -u {} + 2>/dev/null || true
  else
    find "$WORK" -type f -exec rm -f {} + 2>/dev/null || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

"$EMIT_SINGBOX" "$CLIENT" > "$WORK/emitted-singbox.json"
if [[ -n "$AWG_PRIVATE_KEY" ]]; then
  "$EMIT_AWG" "$CLIENT" > "$WORK/awg.conf"
  AWG_PRIVATE_KEY="$AWG_PRIVATE_KEY" python3 - "$WORK/awg.conf" <<'PY'
import os, pathlib, sys
path = pathlib.Path(sys.argv[1])
lines = []
for line in path.read_text().splitlines():
    if line.strip().startswith("DNS"):
        continue
    if line.strip().startswith("PrivateKey"):
        line = f"PrivateKey = {os.environ['AWG_PRIVATE_KEY']}"
    lines.append(line)
path.write_text("\n".join(lines) + "\n")
PY
else
  : > "$WORK/awg.conf"
fi
unset AWG_PRIVATE_KEY

mkdir "$WORK/install"
install -m 0755 "$RUNNER" "$WORK/install/vpn-protocol-liveness"
if [[ -s "$WORK/awg.conf" ]]; then
  install -m 0600 "$WORK/awg.conf" "$WORK/install/awg.conf"
fi
python3 - "$WORK/emitted-singbox.json" "$WORK/awg.conf" "$WORK/install" "$SENTINEL" "$REQUIRED_PROFILES" "$PROBE_URL" "$EXPECTED_STATUS" "$TIMEOUT_SECONDS" "$DEGRADED_AFTER_MS" "$SING_BOX_VERSION" "$AWG_VERSION" <<'PY'
import json, pathlib, sys
source, awg_source, out_dir, sentinel, required_csv, url, status, timeout, degraded, sing_version, awg_version = sys.argv[1:]
doc = json.loads(pathlib.Path(source).read_text())
outbounds = doc.get("outbounds") or []
prefixes = {
    "p0-reality": "p0-reality-",
    "p1-xhttp": "p1-xhttp-",
    "p2-hysteria2": "p2-hysteria2-",
}
port_bases = {"p0-reality": 18080, "p1-xhttp": 18180, "p2-hysteria2": 18280}
required = required_csv.split(",")
profiles = {}
rendered_outbounds = []
rendered_inbounds = []
rendered_rules = []
for profile in required:
    if profile == "p2-amneziawg":
        continue
    selected = [item for item in outbounds if str(item.get("tag", "")).startswith(prefixes[profile])]
    if not selected:
        raise SystemExit(f"required profile {profile} is not present in emitted sing-box config")
    profile_ports = []
    rendered_outbounds.extend(selected)
    for index, outbound in enumerate(selected, start=1):
        port = port_bases[profile] + index
        inbound_tag = f"probe-{profile}-{index}"
        rendered_inbounds.append({"type": "mixed", "tag": inbound_tag, "listen": "127.0.0.1", "listen_port": port})
        rendered_rules.append({"inbound": [inbound_tag], "outbound": outbound["tag"]})
        profile_ports.append(port)
    profiles[profile] = profile_ports
if profiles:
    rendered = {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": rendered_inbounds,
        "outbounds": rendered_outbounds,
        "route": {"rules": rendered_rules, "auto_detect_interface": True},
    }
    (pathlib.Path(out_dir) / "sing-box.json").write_text(json.dumps(rendered, separators=(",", ":")) + "\n")
sentinel_config = {
    "schema_version": 1,
    "sentinel": sentinel,
    "probe_url": url,
    "expected_status": int(status),
    "timeout_seconds": int(timeout),
    "degraded_after_ms": int(degraded),
    "expected_runtime": {"sing_box": sing_version, "awg": awg_version},
    "sing_box": {"config": "/etc/vpn-liveness/sing-box.json", "profiles": profiles},
}
if "p2-amneziawg" in required:
    awg_address = next((line.split("=", 1)[1].strip() for line in pathlib.Path(awg_source).read_text().splitlines() if line.strip().startswith("Address")), "")
    if not awg_address:
        raise SystemExit("emitted AWG config has no client address")
    sentinel_config["amneziawg"] = {"config": "/etc/vpn-liveness/awg.conf", "address": awg_address.split(",", 1)[0].strip()}
(pathlib.Path(out_dir) / "config.json").write_text(json.dumps(sentinel_config, separators=(",", ":")) + "\n")
PY
chmod 0600 "$WORK/install"/*
chmod 0755 "$WORK/install/vpn-protocol-liveness"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10)
REMOTE_USER="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" id -un)"
[[ "$REMOTE_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]] || { echo "unsafe remote username" >&2; exit 1; }
REMOTE_DIR="/tmp/vpn-liveness-${SENTINEL}"
COPYFILE_DISABLE=1 tar --no-xattrs -C "$WORK/install" -czf "$WORK/install.tar.gz" .
scp "${SSH_OPTS[@]}" "$WORK/install.tar.gz" "${SSH_TARGET}:${REMOTE_DIR}.tar.gz"
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "set -eu; rm -rf '${REMOTE_DIR}'; mkdir -m 0700 '${REMOTE_DIR}'; tar -xzf '${REMOTE_DIR}.tar.gz' -C '${REMOTE_DIR}'; sudo install -d -m 0700 /etc/vpn-liveness; sudo install -m 0755 '${REMOTE_DIR}/vpn-protocol-liveness' /usr/local/sbin/vpn-protocol-liveness; sudo find '${REMOTE_DIR}' -maxdepth 1 -type f ! -name vpn-protocol-liveness -exec install -m 0600 {} /etc/vpn-liveness/ \;; printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/vpn-protocol-liveness\n' '${REMOTE_USER}' | sudo tee /etc/sudoers.d/vpn-protocol-liveness >/dev/null; sudo chmod 0440 /etc/sudoers.d/vpn-protocol-liveness; sudo visudo -cf /etc/sudoers.d/vpn-protocol-liveness >/dev/null; rm -rf '${REMOTE_DIR}' '${REMOTE_DIR}.tar.gz'"

VERIFY="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" sudo -n /usr/local/sbin/vpn-protocol-liveness)"
VERIFY_JSON="$VERIFY" python3 - "$SENTINEL" "$REQUIRED_PROFILES" <<'PY'
import json, os, sys
report = json.loads(os.environ["VERIFY_JSON"])
if report.get("sentinel") != sys.argv[1]:
    raise SystemExit("installed sentinel returned the wrong identity")
verdicts = {item.get("profile"): item.get("verdict") for item in report.get("profiles", [])}
bad = [profile for profile in sys.argv[2].split(",") if verdicts.get(profile) not in {"ok", "throttled"}]
if report.get("control", {}).get("verdict") not in {"ok", "throttled"} or bad:
    raise SystemExit("installed sentinel did not pass its initial authenticated probe")
PY

python3 - "$REGISTRY" "$SENTINEL" "$CLIENT" "$SSH_TARGET" <<'PY'
import json, os, pathlib, tempfile, sys
path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
try:
    registry = json.loads(path.read_text())
except (OSError, json.JSONDecodeError):
    registry = {"schema_version": 1, "sentinels": {}}
registry.setdefault("sentinels", {})[sys.argv[2]] = {"client": sys.argv[3], "ssh_target": sys.argv[4]}
fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
with os.fdopen(fd, "w") as handle:
    json.dump(registry, handle, sort_keys=True)
    handle.write("\n")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
PY

ENV="${ENV:-prod}" PROVIDER="${PROVIDER:-upcloud}" "$AUDIT_LOG" append-best-effort --action install-liveness-sentinel --client "$CLIENT" --note "sentinel=${SENTINEL}"

echo "sentinel ${SENTINEL} installed and healthy"
