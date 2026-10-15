"""Operator incident verbs act on exactly one named inventory alias."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS = ROOT / "ansible/playbooks"
VERBS = ("rotate-credentials", "rollback-xray", "rollback-config")
GUARD_MESSAGE = "One exact inventory alias required"
ENVIRONMENT_MESSAGE = "inventory environment must equal ENV"


def inventory(host_env: str | None = "prod") -> str:
    suffix = "" if host_env is None else f" env={host_env}"
    return (f"[vpn]\nnode-a ansible_connection=local{suffix}\nnode-b ansible_connection=local{suffix}\n"
            "[vpn-p1]\nnode-a\n")


def run_play(tmp_path: Path, verb: str, limit: str | None, *, hosts: str = "", environment: str | None = "prod"):
    """Run the real play heads against a local inventory and report whether the marker task ran.

    Host selection, batching and pre_tasks come from the shipped playbook; only the
    privileged, remote and secret-consuming parts are replaced by one marker task.
    """
    real = yaml.safe_load((PLAYBOOKS / f"{verb}.yml").read_text())[0]
    marker = tmp_path / "mutation"
    play = {key: real[key] for key in ("hosts", "serial", "any_errors_fatal", "pre_tasks") if key in real}
    play.update(name=real["name"], become=False, gather_facts=False,
                vars={"ansible_python_interpreter": sys.executable},
                tasks=[{"name": "Publish mutation marker",
                        "ansible.builtin.copy": {"dest": str(marker), "content": "mutated"}}])
    (tmp_path / "tasks").mkdir()
    shutil.copy(PLAYBOOKS / "tasks/exact-node.yml", tmp_path / "tasks/exact-node.yml")
    (tmp_path / "play.yml").write_text(yaml.safe_dump([play]))
    (tmp_path / "hosts.ini").write_text(hosts or inventory())
    (tmp_path / "ansible.cfg").write_text("[defaults]\nhost_key_checking = False\nretry_files_enabled = False\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ANSIBLE_") and key != "ENV"}
    env.update(ANSIBLE_CONFIG=str(tmp_path / "ansible.cfg"), ANSIBLE_HOME=str(tmp_path / "home"))
    if environment is not None:
        env["ENV"] = environment
    argv = ["ansible-playbook", "-i", "hosts.ini", "play.yml"] + ([] if limit is None else ["--limit", limit])
    result = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90)
    return result, result.stdout + result.stderr, marker


@pytest.mark.parametrize("verb", VERBS)
def test_each_play_binds_one_host_before_any_other_task(verb):
    play = yaml.safe_load((PLAYBOOKS / f"{verb}.yml").read_text())[0]
    assert play["hosts"] == "vpn" and play["serial"] == 1 and play["any_errors_fatal"] is True
    assert play["pre_tasks"][0]["ansible.builtin.import_tasks"] == "tasks/exact-node.yml"
    assert all("always" in task["tags"] for task in play["pre_tasks"])


def test_rotation_guard_ordering_matches_the_runbook():
    """RUNBOOK-rotate.md says the refusal follows fact gathering and the controller-side secrets load; change both together."""
    play = yaml.safe_load((PLAYBOOKS / "rotate-credentials.yml").read_text())[0]
    assert play.get("gather_facts", True) is not False
    assert play.get("vars_files")


def test_shared_guard_cannot_be_skipped_by_tag_selection():
    (task,) = yaml.safe_load((PLAYBOOKS / "tasks/exact-node.yml").read_text())
    assert "always" in task["tags"]


@pytest.mark.parametrize("limit", [None, "node-a,node-b", "vpn-p1", "node-a:&vpn"])
@pytest.mark.parametrize("verb", VERBS)
def test_play_refuses_every_selection_except_one_exact_alias(tmp_path, verb, limit):
    result, output, marker = run_play(tmp_path, verb, limit)
    assert result.returncode != 0, output
    assert GUARD_MESSAGE in output
    assert not marker.exists()


@pytest.mark.parametrize("verb", VERBS)
def test_one_host_inventory_still_requires_the_limit(tmp_path, verb):
    result, output, marker = run_play(tmp_path, verb, None, hosts="[vpn]\nnode-a ansible_connection=local env=prod\n")
    assert result.returncode != 0, output
    assert GUARD_MESSAGE in output
    assert not marker.exists()


@pytest.mark.parametrize("verb", VERBS)
def test_exact_alias_targets_only_that_host(tmp_path, verb):
    result, output, marker = run_play(tmp_path, verb, "node-a")
    assert result.returncode == 0, output
    assert marker.exists()
    assert "node-a" in output and "node-b" not in output


@pytest.mark.parametrize("host_env,selected", [("staging", "prod"), ("prod", "staging"), ("prod", None), (None, None)])
def test_rotation_refuses_a_host_outside_the_selected_environment(tmp_path, host_env, selected):
    result, output, marker = run_play(tmp_path, "rotate-credentials", "node-a", hosts=inventory(host_env), environment=selected)
    assert result.returncode != 0, output
    assert ENVIRONMENT_MESSAGE in output
    assert not marker.exists()


def make(*arguments: str):
    env = {key: value for key, value in os.environ.items()
           if key not in {"ANSIBLE_LIMIT", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES", "MAKELEVEL"}}
    return subprocess.run(["make", "--no-print-directory", *arguments], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("limit", [None, "", " ", "   "])
def test_make_refuses_an_absent_or_blank_limit(limit):
    result = make("require-exact-node", *([] if limit is None else [f"ANSIBLE_LIMIT={limit}"]))
    assert result.returncode != 0
    assert "requires ANSIBLE_LIMIT=<exact inventory alias>" in result.stdout + result.stderr


def test_make_accepts_a_named_limit():
    assert make("require-exact-node", "ANSIBLE_LIMIT=node-a").returncode == 0


def printed_recipe(verb: str) -> str:
    result = make("-n", verb, "ANSIBLE_LIMIT=node-a", "DEPLOY_SOURCE_REVISION=revision",
                  "DEPLOYABLE_SOURCE_DIGEST=digest", "SECRETS_FILE=/nonexistent/runtime.yaml",
                  "ROLLBACK_XRAY_VERSION=v26.3.27")
    assert result.returncode == 0, result.stdout + result.stderr
    return re.sub(r"\\\n\s*", " ", result.stdout)


@pytest.mark.parametrize("verb", VERBS)
def test_make_verbs_require_the_alias_and_inventory_then_forward_the_limit(verb):
    text = printed_recipe(verb)
    assert "requires ANSIBLE_LIMIT=<exact inventory alias>" in text
    assert 'ansible-inventory --list --limit "node-a"' in text
    assert f'ansible/playbooks/{verb}.yml --limit "node-a"' in text


def test_make_rotation_also_requires_clean_source_prechecks_and_names_the_node():
    text = printed_recipe("rotate-credentials")
    assert "require a clean git checkout" in text
    assert "validate-secrets.py" in text
    assert "node=node-a" in text


@pytest.mark.parametrize("verb", ["rollback-xray", "rollback-config"])
def test_make_rollbacks_stay_usable_without_clean_source_or_decrypted_secrets(verb):
    text = printed_recipe(verb)
    assert "clean git checkout" not in text and "validate-secrets.py" not in text
