"""The known-good tag is the conjunction of per-node verification receipts."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

FLEET = """[vpn-p0-web]
node-a
[vpn-p1-web]
node-b
[vpn:children]
vpn-p0-web
vpn-p1-web
[observability-kuma]
observer
"""
PAIR = """[vpn-split-hop-ingress-live]
pair-a
[vpn:children]
vpn-split-hop-ingress-live
"""


@pytest.fixture
def repo(tmp_path):
    """A throwaway checkout so `git tag` never touches this repository."""
    work = tmp_path / "repo"
    (work / "scripts").mkdir(parents=True)
    (work / "ansible").mkdir()
    for name in ("known-good.py", "deploy-source-identity.sh"):
        shutil.copy2(ROOT / "scripts" / name, work / "scripts" / name)
    (work / "ansible/site.yml").write_text("- hosts: vpn\n")
    (work / "fleet.ini").write_text(FLEET)
    (work / "pair.ini").write_text(PAIR)
    git = ["git", "-C", str(work)]
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    # The script's own `git tag -a` needs an identity; CI runners have no global one.
    subprocess.run(git + ["config", "user.name", "t"], check=True)
    subprocess.run(git + ["config", "user.email", "t@example.invalid"], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "init"], check=True)
    return work


def record(repo, receipts, inventory="fleet.ini", *limit):
    result = run(repo, "record", "--inventory", inventory, "--receipts", str(receipts), *limit)
    assert result.returncode == 0, result.stderr
    return result


def run(repo, *args):
    return subprocess.run([sys.executable, str(repo / "scripts/known-good.py"), *args],
                          cwd=repo, capture_output=True, text=True, check=False)


def tags(repo):
    return subprocess.run(["git", "-C", str(repo), "tag", "--points-at", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.split()


def head(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_tag_waits_for_every_vpn_host_then_tags_once(repo, tmp_path):
    receipts = str(tmp_path / "receipts")
    record(repo, receipts, "fleet.ini", "--limit", "node-a")
    refused = run(repo, "tag", "--inventory", "fleet.ini", "--receipts", receipts)

    assert refused.returncode == 1 and "node-b: no verification receipt" in refused.stderr
    assert "node-a" not in refused.stderr and "observer" not in refused.stderr
    assert tags(repo) == []

    record(repo, receipts, "fleet.ini", "--limit", "node-b")
    accepted = run(repo, "tag", "--inventory", "fleet.ini", "--receipts", receipts)
    again = run(repo, "tag", "--inventory", "fleet.ini", "--receipts", receipts)

    assert accepted.returncode == 0, accepted.stderr
    assert len(tags(repo)) == 1 and tags(repo)[0].startswith("vpn-deploy-known-good-")
    assert again.returncode == 0 and "already tagged" in again.stdout and len(tags(repo)) == 1


def test_an_added_inventory_makes_its_hosts_required(repo, tmp_path):
    receipts = str(tmp_path / "receipts")
    record(repo, receipts)

    refused = run(repo, "tag", "--inventory", "fleet.ini", "--inventory", "pair.ini", "--receipts", receipts)
    assert refused.returncode == 1 and "pair-a: no verification receipt" in refused.stderr

    record(repo, receipts, "pair.ini")
    accepted = run(repo, "tag", "--inventory", "fleet.ini", "--inventory", "pair.ini", "--receipts", receipts)
    assert accepted.returncode == 0, accepted.stderr
    assert "3 nodes" in accepted.stdout


@pytest.mark.parametrize(("field", "value", "message"), [
    ("verified_at", int(time.time()) - 25 * 3600, "receipt older than 24h"),
    ("verified_at", int(time.time()) + 3600, "receipt time is missing or in the future"),
    ("deployable_digest", "0" * 64, "receipt digest differs from the checkout"),
    ("alias", "node-a", "malformed receipt"),
], ids=["stale", "future", "foreign-digest", "other-alias"])
def test_stale_or_foreign_receipt_refuses(repo, tmp_path, field, value, message):
    receipts = tmp_path / "receipts"
    record(repo, receipts)
    path = receipts / head(repo) / "node-b.json"
    body = json.loads(path.read_text())
    body[field] = value
    path.write_text(json.dumps(body))

    refused = run(repo, "tag", "--inventory", "fleet.ini", "--receipts", str(receipts))
    assert refused.returncode == 1 and f"node-b: {message}" in refused.stderr
    assert tags(repo) == []


def test_receipts_from_an_older_revision_do_not_count(repo, tmp_path):
    receipts = str(tmp_path / "receipts")
    record(repo, receipts)
    old = head(repo)
    (repo / "ansible/site.yml").write_text("- hosts: vpn\n  gather_facts: false\n")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-am", "change"], check=True)

    refused = run(repo, "tag", "--inventory", "fleet.ini", "--receipts", receipts)
    assert refused.returncode == 1 and "node-a: no verification receipt" in refused.stderr
    assert (tmp_path / "receipts" / old / "node-a.json").is_file()


def test_record_refuses_a_selection_without_vpn_hosts(repo, tmp_path):
    result = run(repo, "record", "--inventory", "fleet.ini", "--limit", "observer",
                 "--receipts", str(tmp_path / "receipts"))
    assert result.returncode == 1 and "selected no vpn hosts" in result.stderr
    assert not (tmp_path / "receipts").exists()
