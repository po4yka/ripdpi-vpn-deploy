"""Off-node self-steal renewal: act only when due, once, never change the source, refuse a wrong pair."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "renew-self-steal-cert.py"
INSTALLER = SCRIPT.parent / "install-operator-crons.sh"
NAME = "edge.example.test"

FAKE_SOPS = r'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args[:2] == ["--decrypt", "--extract"]:
    path, doc = args[2], json.load(open(args[3]))
    try:
        for key in path.strip("[]").split("]["):
            doc = doc[json.loads(key)]
    except KeyError:
        sys.exit(1)
    sys.stdout.write(doc)
elif args[:2] == ["set", "--value-stdin"]:
    target, path = args[2], args[3]
    doc = json.load(open(target)); node = doc
    keys = [json.loads(k) for k in path.strip("[]").split("][")]
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = json.load(sys.stdin)
    json.dump(doc, open(target, "w"))
else:
    sys.exit(2)
'''

FAKE_LEGO = r'''#!/usr/bin/env python3
import os, pathlib, shutil, sys
if sys.argv[1:] == ["--version"]:
    print("lego version " + os.environ["FAKE_LEGO_VERSION"] + " darwin/arm64"); sys.exit(0)
pathlib.Path(os.environ["FAKE_LEGO_CALLED"]).write_text("called")
assert os.environ.get("VULTR_API_KEY") == "dns-token"
args = sys.argv[1:]
out = pathlib.Path(args[args.index("--path") + 1]) / "certificates"
out.mkdir(parents=True, exist_ok=True)
domain = args[args.index("--domains") + 1]
src = pathlib.Path(os.environ["FAKE_ISSUED"])
shutil.copy(src / "cert.pem", out / (domain + ".crt"))
shutil.copy(src / "key.pem", out / (domain + ".key"))
'''


def _pair(directory: Path, name: str, days: int) -> tuple[str, str]:
    directory.mkdir(parents=True)
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
                    "-keyout", str(directory / "key.pem"), "-out", str(directory / "cert.pem"), "-days", str(days),
                    "-subj", "/CN=" + name, "-addext", "subjectAltName=DNS:" + name],
                   check=True, capture_output=True)
    return (directory / "cert.pem").read_text(), (directory / "key.pem").read_text()


@pytest.fixture()
def kit(tmp_path: Path):
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    for name, body in (("sops", FAKE_SOPS), ("lego", FAKE_LEGO)):
        (bin_dir / name).write_text(body.replace("/usr/bin/env python3", sys.executable)); (bin_dir / name).chmod(0o755)
    dns = tmp_path / "vultr.json"; dns.write_text(json.dumps({"api_key": "dns-token"}))
    kit_dir = tmp_path / "kit"; kit_dir.mkdir()
    source = kit_dir / "p0-runtime.sops.json"

    def setup(current_days: int, issued_name: str = NAME, lego_version: str = "5.6.0", nginx_name: str | None = None):
        if not (tmp_path / "current").exists():
            cert, key = _pair(tmp_path / "current", NAME, current_days)
            doc = {"reality_self_steal": {"server_name": NAME, "cert_pem": cert, "key_pem": key}}
            if nginx_name:
                doc["nginx_xhttp"] = {"server_name": nginx_name}
            source.write_text(json.dumps(doc))
            _pair(tmp_path / "issued", issued_name, 90)
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], FAKE_LEGO_VERSION=lego_version,
                   FAKE_ISSUED=str(tmp_path / "issued"), FAKE_LEGO_CALLED=str(tmp_path / "lego-called"))
        result = subprocess.run([sys.executable, str(SCRIPT), "--sops-file", str(source), "--dns-sops-file", str(dns),
                                 "--lego-path", str(tmp_path / "lego")], env=env, capture_output=True, text=True)
        renewed = sorted(kit_dir.glob("p0-runtime-self-steal-renewed-*.sops.json"))
        return result, source, renewed
    return setup, tmp_path


def test_certificate_with_time_left_is_not_reissued(kit) -> None:
    setup, tmp = kit
    result, _, renewed = setup(current_days=90)
    assert result.returncode == 0
    assert json.loads(result.stdout)["state"] == "not-due"
    assert renewed == [] and not (tmp / "lego-called").exists()


def test_due_certificate_is_reissued_once_into_a_new_document(kit) -> None:
    setup, tmp = kit
    result, source, renewed = setup(current_days=10)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["state"] == "renewed"
    [output] = renewed
    pair = json.loads(output.read_text())["reality_self_steal"]
    assert pair["cert_pem"] == (tmp / "issued" / "cert.pem").read_text()
    assert pair["key_pem"] == (tmp / "issued" / "key.pem").read_text()
    assert json.loads(source.read_text())["reality_self_steal"]["cert_pem"] == (tmp / "current" / "cert.pem").read_text()
    assert not list((tmp / "lego").rglob("*.key")), "issued key must not stay on disk"
    assert "dns-token" not in result.stdout + result.stderr

    (tmp / "lego-called").unlink()
    again, _, still = setup(current_days=10)
    assert json.loads(again.stdout)["state"] == "awaiting-deploy"
    assert still == renewed and not (tmp / "lego-called").exists()


@pytest.mark.parametrize("issued_name,lego_version,nginx_name,category", [
    ("other.example.test", "5.6.0", None, "issued-name-mismatch"),
    (NAME, "5.7.0", None, "lego-version-mismatch"),
    (NAME, "5.6.0", NAME, "shared-hostname-needs-both-certificates"),
])
def test_wrong_pair_unpinned_client_or_shared_name_is_refused(kit, issued_name, lego_version, nginx_name, category) -> None:
    setup, tmp = kit
    result, _, renewed = setup(current_days=10, issued_name=issued_name, lego_version=lego_version, nginx_name=nginx_name)
    assert result.returncode == 1
    assert result.stderr.strip() == "self-steal-renewal-refused: " + category
    assert renewed == [] and not list((tmp / "lego").rglob("*.key"))


def _cron(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(tmp_path), PROVIDER="upcloud", ENV="prod", **extra)
    return subprocess.run(["bash", str(INSTALLER), "--dry-run"], cwd=SCRIPT.parents[1], env=env,
                          capture_output=True, text=True)


def test_cron_runs_renewal_daily_only_with_both_documents(tmp_path: Path) -> None:
    skipped = _cron(tmp_path)
    assert skipped.returncode == 0 and "renew-self-steal-cert" not in skipped.stdout
    assert "self-steal renewal skipped" in skipped.stderr

    p0, dns = tmp_path / "p0 runtime.sops.yaml", tmp_path / "vultr.sops.json"
    p0.write_text("{}"); dns.write_text("{}")
    enabled = _cron(tmp_path, SELF_STEAL_SOPS_FILE=str(p0), SELF_STEAL_DNS_SOPS_FILE=str(dns))
    assert enabled.returncode == 0, enabled.stderr
    [line] = [l for l in enabled.stdout.splitlines() if "renew-self-steal-cert" in l]
    assert line.startswith("27 4 * * *")
    assert "SELF_STEAL_SOPS_FILE=" + str(p0).replace(" ", "\\ ") in line

    missing = _cron(tmp_path, SELF_STEAL_SOPS_FILE=str(p0), SELF_STEAL_DNS_SOPS_FILE=str(tmp_path / "missing.json"))
    assert missing.returncode != 0 and "must both name existing files" in missing.stderr
    relative = _cron(tmp_path, SELF_STEAL_SOPS_FILE=os.path.relpath(p0, SCRIPT.parents[1]), SELF_STEAL_DNS_SOPS_FILE=str(dns))
    assert relative.returncode != 0
