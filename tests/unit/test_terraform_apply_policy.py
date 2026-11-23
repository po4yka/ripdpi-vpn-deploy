"""Exercise the operator saved-plan gate without provider access."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


pytestmark = pytest.mark.usefixtures("stub_tofu_backend")

ROOT = Path(__file__).resolve().parents[2]


def _setup(tmp_path: Path, provider_name: str = "upcloud") -> tuple[Path, dict[str, str]]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    for name in ("policy-plan.sh", "check-tf-plan.sh", "terraform-env.sh", "tofu_backend.py", "terraform-plan-policy.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    shutil.copytree(ROOT / "terraform/policy", repo / "terraform/policy")
    provider = repo / "terraform/providers" / provider_name
    provider.mkdir(parents=True)
    (provider / "prod.tfplan").write_text("original saved plan")
    private = tmp_path / "private"
    private.mkdir()
    bins = tmp_path / "bin"
    bins.mkdir()
    terraform = bins / "tofu"
    terraform.write_text('''#!/usr/bin/env python3
import json, os, pathlib, stat, sys
args=sys.argv[1:]
args=[arg for arg in args if not arg.startswith('-chdir=')]
if args[0]=='workspace': sys.exit(0)
plan=pathlib.Path(args[-1])
entry={'command':args[0], 'path':str(plan), 'content':plan.read_text(),
       'mode':stat.S_IMODE(plan.stat().st_mode),
       'parent_mode':stat.S_IMODE(plan.parent.stat().st_mode)}
with open(os.environ['CALL_LOG'],'a') as handle: handle.write(json.dumps(entry)+'\\n')
if args[0]=='show':
    if os.environ.get('SHOW_FAIL'): sys.exit(3)
    print(os.environ['STUB_PLAN_JSON'])
    if os.environ.get('CHANGE_SOURCE'):
        pathlib.Path(os.environ['SOURCE_PLAN']).write_text('changed after policy snapshot')
if args[0]=='apply': sys.exit(int(os.environ.get('APPLY_EXIT','0')))
''')
    terraform.chmod(0o755)
    doc = {
        "variables": {"ssh_port": {"value": 22}, "allowed_ssh_cidrs": {"value": ["192.0.2.42/32"]}},
        "resource_changes": [],
    }
    env = os.environ | {
        "PATH": f"{bins}:{os.environ['PATH']}", "CALL_LOG": str(tmp_path / "calls.jsonl"),
        "STUB_PLAN_JSON": json.dumps(doc), "PROVIDER": provider_name, "ENV": "prod",
        "TMPDIR": str(private), "SOURCE_PLAN": str(provider / "prod.tfplan"),
    }
    return repo, env


def _run(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(repo / "scripts/policy-plan.sh"), "apply"],
                          env=env, cwd=repo, text=True, capture_output=True)


def _calls(env: dict[str, str]) -> list[dict]:
    path = Path(env["CALL_LOG"])
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_safe_plan_applies_same_private_snapshot_and_cleans_up(tmp_path: Path) -> None:
    repo, env = _setup(tmp_path)
    private_plan = tmp_path / "private/green.tfplan"
    original = Path(env["SOURCE_PLAN"])
    original.rename(private_plan)
    original.write_text("competing shared plan")
    env.update(TF_PLAN_FILE=str(private_plan), SOURCE_PLAN=str(private_plan), CHANGE_SOURCE="1")
    result = _run(repo, env)
    assert result.returncode == 0, result.stderr
    calls = _calls(env)
    assert [call["command"] for call in calls] == ["show", "apply"]
    assert calls[0]["path"] == calls[1]["path"]
    assert calls[1]["content"] == "original saved plan"
    assert all(call["mode"] == 0o400 and call["parent_mode"] == 0o700 for call in calls)
    assert list(Path(env["TMPDIR"]).iterdir()) == [private_plan]
    assert private_plan.read_text() == "changed after policy snapshot"
    assert original.read_text() == "competing shared plan"


@pytest.mark.parametrize("case", ["selected-second", "unrelated", "missing-file", "existing", "missing-server", "registered-blue", "configured-blue"])
def test_green_apply_requires_selected_management_identity(tmp_path, case):
    repo, env = _setup(tmp_path, "hetzner")
    private = tmp_path / "management key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "fixture",
                    "-f", str(private)], check=True)
    public = private.with_suffix(".pub").read_text().strip()
    # The generated public sidecar does not authorize access by itself.
    keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIACuqbmHay9Ja1UTyK6Xs0ld57/VDX6uINKx2394i/LI bootstrap"]
    if case != "unrelated":
        keys.append(public.replace("fixture", "inventory"))
    if case == "missing-file":
        private.unlink()
    plan = json.loads(env["STUB_PLAN_JSON"])
    plan["variables"]["admin_ssh_public_keys"] = {"value": keys}
    plan["resource_changes"] = [{"address": "hcloud_server.vpn", "type": "hcloud_server",
                                 "change": {"actions": ["no-op" if case == "existing" else "create"],
                                            "after": {"firewall_ids": [1001]}}}]
    if case == "missing-server":
        plan["resource_changes"].clear()
    blue_key = keys[0] if case == "registered-blue" else public
    blue_digest = hashlib.sha256(" ".join(blue_key.split()[:2]).encode()).hexdigest()
    configured_key = keys[0] if case == "configured-blue" else public
    configured_digest = hashlib.sha256(" ".join(configured_key.split()[:2]).encode()).hexdigest()
    env.update(BLUE_GREEN_MANAGEMENT_KEY_FILE=str(private),
               BLUE_GREEN_RESERVED_KEY_DIGESTS=f"{configured_digest}:{blue_digest}",
               STUB_PLAN_JSON=json.dumps(plan))
    result = _run(repo, env)
    accepted = case in ("selected-second", "existing")
    assert (result.returncode == 0) == accepted, result.stderr
    assert [row["command"] for row in _calls(env)] == (["show", "apply"] if accepted else ["show"])
    assert public.split()[1] not in result.stdout + result.stderr
    if case == "missing-file":
        assert "Cannot verify the Green plan or read the selected SSH identity" in result.stderr
        assert str(private) not in result.stderr


def test_denied_policy_never_invokes_apply(tmp_path: Path) -> None:
    repo, env = _setup(tmp_path)
    doc = json.loads(env["STUB_PLAN_JSON"])
    doc["resource_changes"] = [{"address": "hcloud_firewall.test", "type": "hcloud_firewall",
                                "change": {"after": {"rule": [{"direction": "in", "protocol": "tcp",
                                  "port": "20-30", "source_ips": ["0.0.0.0/0"]}]}}}]
    env["STUB_PLAN_JSON"] = json.dumps(doc)
    result = _run(repo, env)
    assert result.returncode != 0
    assert [call["command"] for call in _calls(env)] == ["show"]
    assert list(Path(env["TMPDIR"]).iterdir()) == []


@pytest.mark.parametrize("failure", ["show", "empty-policy", "malformed-plan", "apply"])
def test_failure_paths_clean_up_and_preserve_apply_status(tmp_path: Path, failure: str) -> None:
    repo, env = _setup(tmp_path)
    if failure == "show":
        env["SHOW_FAIL"] = "1"
    elif failure == "empty-policy":
        shutil.rmtree(repo / "terraform/policy")
        (repo / "terraform/policy").mkdir()
        (repo / "terraform/policy/empty.rego").write_text("package main\n")
    elif failure == "malformed-plan":
        env["STUB_PLAN_JSON"] = "synthetic-private-value"
    else:
        env["APPLY_EXIT"] = "17"
    result = _run(repo, env)
    if failure == "apply":
        assert result.returncode == 17
    assert result.returncode != 0
    assert [call["command"] for call in _calls(env)] == (["show", "apply"] if failure == "apply" else ["show"])
    assert list(Path(env["TMPDIR"]).iterdir()) == []
    assert "synthetic-private-value" not in result.stdout + result.stderr


def test_missing_or_symlink_plan_is_refused_before_terraform(tmp_path: Path) -> None:
    repo, env = _setup(tmp_path)
    source = Path(env["SOURCE_PLAN"])
    source.unlink()
    assert _run(repo, env).returncode != 0
    source.symlink_to(tmp_path / "foreign.tfplan")
    assert _run(repo, env).returncode != 0
    assert _calls(env) == []


def test_make_apply_uses_the_policy_gate() -> None:
    source = (ROOT / "Makefile").read_text()
    target = source.split("\napply:\n", 1)[1].split("\n\n", 1)[0]
    assert './scripts/policy-plan.sh apply' in target


def test_standalone_and_ci_policy_paths_share_evaluator() -> None:
    standalone = (ROOT / "scripts/tf-policy-test.sh").read_text()
    workflow = (ROOT / ".github/workflows/tf-policy.yml").read_text()
    assert '"${REPO_ROOT}/scripts/check-tf-plan.sh" "$PLAN_JSON"' in standalone
    assert "../../../scripts/check-tf-plan.sh ci-policy.json" in workflow
