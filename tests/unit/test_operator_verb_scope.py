"""Operator incident verbs act on exactly one named inventory alias."""
from __future__ import annotations

import json
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
# Spellings around the alias grammar, on both sides of each boundary.
ALIAS_SPELLINGS = ["node-a", "A", "9.x_y-z", "n" * 128, "n" * 129, "", "-node", ".node", "_node", "node a",
                   "node-a,node-b", "node:b", "node/b", "node*", "node-a\n", "n\u00e9ud"]
# Spellings that become shell or Make syntax when interpolated into a recipe.
HOSTILE_LIMITS = [
    "$(shell touch {marker})",
    "node-a$(shell touch {marker})",
    "$$(touch {marker})",
    'node-a"; touch {marker}; "',
    "node-a'; touch {marker}; '",
    "node-a`touch {marker}`",
    "node-a;touch {marker}",
]


def inventory(host_env: str | None = "prod") -> str:
    suffix = "" if host_env is None else f" env={host_env}"
    return (f"[vpn]\nnode-a ansible_connection=local{suffix}\nnode-b ansible_connection=local{suffix}\n"
            "[vpn-p1]\nnode-a\n")


def run_play(tmp_path: Path, verb: str, limit: str | None, *, hosts: str = "", environment: str | None = "prod",
             extra_env: dict[str, str] | None = None):
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
    env.update(extra_env or {})
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


def test_inherited_skip_tags_would_bypass_the_guard(tmp_path):
    """The guard is always-tagged; this is why the Make verbs drop inherited tag selection before ansible-playbook."""
    result, output, marker = run_play(tmp_path, "rollback-config", None, extra_env={"ANSIBLE_SKIP_TAGS": "always"})
    assert result.returncode == 0, output
    assert marker.exists()


def test_dropped_tag_selection_variables_are_the_ones_ansible_reads():
    result = subprocess.run(["ansible-config", "list", "--format", "json"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    options = json.loads(result.stdout)
    assert [entry["name"] for entry in options["TAGS_SKIP"]["env"]] == ["ANSIBLE_SKIP_TAGS"]
    assert [entry["name"] for entry in options["TAGS_RUN"]["env"]] == ["ANSIBLE_RUN_TAGS"]


def make(*arguments: str, env: dict[str, str] | None = None):
    base = {key: value for key, value in os.environ.items()
            if key not in {"ANSIBLE_LIMIT", "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES", "MAKELEVEL"}}
    return subprocess.run(["make", "--no-print-directory", *arguments], cwd=ROOT, env={**base, **(env or {})},
                          capture_output=True, text=True, timeout=30)


def play_alias_pattern() -> str:
    (task,) = yaml.safe_load((PLAYBOOKS / "tasks/exact-node.yml").read_text())
    (condition,) = [item for item in task["ansible.builtin.assert"]["that"] if "is match(" in item]
    return re.search(r"is match\('([^']+)'\)", condition).group(1)


@pytest.mark.parametrize("limit", [None, "", " ", "   "])
def test_make_refuses_an_absent_or_blank_limit(limit):
    result = make("require-exact-node", *([] if limit is None else [f"ANSIBLE_LIMIT={limit}"]))
    assert result.returncode != 0
    assert "requires ANSIBLE_LIMIT=<exact inventory alias>" in result.stdout + result.stderr


def test_make_accepts_a_named_limit():
    assert make("require-exact-node", "ANSIBLE_LIMIT=node-a").returncode == 0


@pytest.mark.parametrize("limit", [alias for alias in ALIAS_SPELLINGS if alias])
def test_make_alias_grammar_matches_the_play_guard(limit):
    """Make repeats the play's alias grammar; a drift would refuse a valid node or admit one the play then refuses."""
    # The play's `$` also matches before a trailing newline, which Make refuses.
    play_accepts = re.match(play_alias_pattern(), limit) is not None
    assert (make("require-exact-node", f"ANSIBLE_LIMIT={limit}").returncode == 0) == (play_accepts and not limit.endswith("\n"))


@pytest.mark.parametrize("alias", ALIAS_SPELLINGS)
def test_vpnd_rotation_builder_alias_grammar_matches_the_play_guard(alias):
    """vpnd repeats the guard's grammar too. It lives here, not in vpnd/tests, because mutation copies lack ansible/."""
    from vpnd.config import Context
    from vpnd.runner import ansible as vpnd_ansible

    context = Context(root=ROOT, ansible_dir=ROOT / "ansible", tf_root=ROOT / "terraform/providers/upcloud", env="prod",
                      provider="upcloud", sops_file=Path("/config/prod.secrets.sops.yaml"),
                      secrets_file=Path("/tmp/vpn-prod.secrets.yaml"), config_dir=Path("/config"), explain=True, yes=True)
    try:
        vpnd_ansible.rotate(context, alias)
        builder_accepts = True
    except ValueError:
        builder_accepts = False
    # The play's `$` also matches before a trailing newline, which the builder refuses.
    assert builder_accepts == (re.match(play_alias_pattern(), alias) is not None and not alias.endswith("\n"))


@pytest.mark.parametrize("template", HOSTILE_LIMITS)
def test_make_refuses_a_limit_that_is_not_an_alias_without_executing_it(tmp_path, template):
    marker = tmp_path / "executed"
    result = make("require-exact-node", f"ANSIBLE_LIMIT={template.format(marker=marker)}")
    assert result.returncode != 0
    assert "requires ANSIBLE_LIMIT=<exact inventory alias>" in result.stdout + result.stderr
    assert not marker.exists()


def printed_recipe(*goals: str, limit: str = "node-a") -> subprocess.CompletedProcess:
    return make("-n", *goals, f"ANSIBLE_LIMIT={limit}", "DEPLOY_SOURCE_REVISION=revision",
                "DEPLOYABLE_SOURCE_DIGEST=digest", "SECRETS_FILE=/nonexistent/runtime.yaml",
                "ROLLBACK_XRAY_VERSION=v26.3.27")


def recipe_text(*goals: str) -> str:
    result = printed_recipe(*goals)
    assert result.returncode == 0, result.stdout + result.stderr
    return re.sub(r"\\\n\s*", " ", result.stdout)


@pytest.mark.parametrize("template", HOSTILE_LIMITS)
@pytest.mark.parametrize("verb", VERBS)
def test_make_verbs_never_interpolate_the_limit_into_recipe_text(tmp_path, verb, template):
    marker = tmp_path / "executed"
    result = printed_recipe(verb, limit=template.format(marker=marker))
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert str(marker) not in result.stdout


@pytest.mark.parametrize("other", ["deploy", "verify", "clean"])
@pytest.mark.parametrize("verb", VERBS)
def test_make_refuses_the_verbs_beside_other_goals(verb, other):
    for goals in ((verb, other), (other, verb)):
        result = printed_recipe(*goals)
        assert result.returncode != 0, goals
        assert "cannot share an invocation with other Make goals" in result.stdout + result.stderr
        assert result.stdout == "", goals


def test_make_accepts_the_exact_node_verbs_in_one_invocation():
    text = recipe_text(*VERBS)
    for verb in VERBS:
        assert f'ansible/playbooks/{verb}.yml --limit "$EXACT_NODE_ALIAS"' in text


@pytest.mark.parametrize("verb", VERBS)
def test_make_verbs_require_the_alias_and_inventory_then_forward_the_limit(verb):
    text = recipe_text(verb)
    assert "requires ANSIBLE_LIMIT=<exact inventory alias>" in text
    assert 'ansible-inventory --list --limit "$EXACT_NODE_ALIAS"' in text
    assert f'ansible/playbooks/{verb}.yml --limit "$EXACT_NODE_ALIAS"' in text
    assert "node-a" not in text


@pytest.mark.parametrize("verb", VERBS)
def test_make_verbs_start_ansible_without_inherited_tag_selection(verb):
    assert re.search(rf"env -u ANSIBLE_SKIP_TAGS -u ANSIBLE_RUN_TAGS\s+VPN_SECRETS_FILE=\S+\s+"
                     rf"(ROLLBACK_XRAY_VERSION=\S+\s+)?ansible-playbook\s+\S*{verb}\.yml\s", recipe_text(verb))


def stand_in_ansible(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return the calls file, a PATH directory with a recording ansible-inventory, and a one-node generated inventory."""
    calls = tmp_path / "calls"
    tools = tmp_path / "bin"
    tools.mkdir()
    (tools / "ansible-inventory").write_text(f"#!/bin/sh\necho \"inventory $*\" >> {calls}\n"
                                            "echo '{\"vpn\": {\"hosts\": [\"node-a\"]}}'\n")
    (tools / "ansible-inventory").chmod(0o755)
    ansible_dir = tmp_path / "ansible"
    (ansible_dir / "inventory").mkdir(parents=True)
    (ansible_dir / "inventory/generated.ini").write_text("[vpn]\nnode-a\n")
    return calls, tools, ansible_dir


@pytest.mark.parametrize("source", ["argument", "environment"])
@pytest.mark.parametrize("verb", ["rollback-xray", "rollback-config"])
def test_make_runs_ansible_with_the_exact_alias_and_without_inherited_tag_selection(tmp_path, verb, source):
    """Run the real recipe against recording stand-ins for the two Ansible entry points."""
    calls, tools, ansible_dir = stand_in_ansible(tmp_path)
    (tools / "ansible-playbook").write_text(f"#!/bin/sh\necho \"playbook $* skip=${{ANSIBLE_SKIP_TAGS-unset}} "
                                           f"run=${{ANSIBLE_RUN_TAGS-unset}} limit=${{ANSIBLE_LIMIT-unset}}\" >> {calls}\n")
    (tools / "ansible-playbook").chmod(0o755)
    result = make(verb, *(["ANSIBLE_LIMIT=node-a"] if source == "argument" else []), f"ANSIBLE_DIR={ansible_dir}",
                  f"SECRETS_FILE={tmp_path}/runtime.yaml", "ROLLBACK_XRAY_VERSION=v26.3.27",
                  env={"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "ANSIBLE_SKIP_TAGS": "always",
                       "ANSIBLE_RUN_TAGS": "never", **({"ANSIBLE_LIMIT": "node-a"} if source == "environment" else {})})
    assert result.returncode == 0, result.stdout + result.stderr
    # The recipes bind the alias through EXACT_NODE_ALIAS; ANSIBLE_LIMIT, now an unexpanded reference, is not exported.
    assert calls.read_text().splitlines() == [
        "inventory --list --limit node-a",
        f"playbook {ansible_dir}/playbooks/{verb}.yml --limit node-a skip=unset run=unset limit=unset",
    ]


def test_make_runs_verbs_sharing_an_invocation_one_at_a_time_under_parallelism(tmp_path):
    """Two plays on the same node must never overlap, whatever -j the operator's environment carries."""
    calls, tools, ansible_dir = stand_in_ansible(tmp_path)
    (tools / "ansible-playbook").write_text(f"#!/bin/sh\nplay=$(basename \"$1\")\necho \"start $play\" >> {calls}\n"
                                           f"sleep 0.5\necho \"end $play\" >> {calls}\n")
    (tools / "ansible-playbook").chmod(0o755)
    result = make("-j4", "rollback-xray", "rollback-config", "ANSIBLE_LIMIT=node-a", f"ANSIBLE_DIR={ansible_dir}",
                  f"SECRETS_FILE={tmp_path}/runtime.yaml", "ROLLBACK_XRAY_VERSION=v26.3.27",
                  env={"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert [line for line in calls.read_text().splitlines() if not line.startswith("inventory")] == [
        "start rollback-xray.yml", "end rollback-xray.yml", "start rollback-config.yml", "end rollback-config.yml"]


def test_make_rotation_also_requires_clean_source_prechecks_and_names_the_node():
    text = recipe_text("rotate-credentials")
    assert "require a clean git checkout" in text
    assert "validate-secrets.py" in text
    assert 'node=$EXACT_NODE_ALIAS' in text


@pytest.mark.parametrize("verb", ["rollback-xray", "rollback-config"])
def test_make_rollbacks_stay_usable_without_clean_source_or_decrypted_secrets(verb):
    text = recipe_text(verb)
    assert "clean git checkout" not in text and "validate-secrets.py" not in text


def printed_revocation_commands(environment: str, provider: str, sops_file: str) -> str:
    """Render the revocation guidance exactly as new-client.sh prints it, without issuing a client."""
    script = (ROOT / "scripts/new-client.sh").read_text()
    guidance = re.search(r"^  if make decrypt.*?^(?=EOF$)", script, re.S | re.M).group(0)
    rendered = subprocess.run(["bash", "-c", f"cat <<EOF\n{guidance}EOF\n"], capture_output=True, text=True, timeout=10,
                              env={**os.environ, "ENV": environment, "PROVIDER": provider, "SOPS_FILE": sops_file})
    assert rendered.returncode == 0, rendered.stderr
    return rendered.stdout


# The runbooks that print the revocation sequence, with the heading of the section that holds it.
RUNBOOK_SECTIONS = {"RUNBOOK-rotate.md": "## 1. Single client leak", "RUNBOOK-deploy.md": "## Add a new client device"}


def runbook_revocation_commands(runbook: str) -> str:
    """The same sequence as the named runbook's section prints it."""
    section = (ROOT / "docs" / runbook).read_text().split(RUNBOOK_SECTIONS[runbook], 1)[1].split("\n## ", 1)[0]
    block = re.search(r"^(if make decrypt.*?)^```$", section, re.S | re.M)
    assert block, f"{runbook} no longer prints the guarded revocation loop under {RUNBOOK_SECTIONS[runbook]!r}"
    return block.group(1)


def run_revocation(commands: str, tmp_path: Path, failing: str | None) -> tuple[list[tuple[str, dict[str, str]]], str]:
    """Run printed commands against a recording `make` stand-in that fails the step named `target:node`."""
    tools = tmp_path / "bin"
    tools.mkdir()
    calls = tmp_path / "calls"
    (tools / "make").write_text(f"""#!/bin/sh
printf '%s\\037' "$@" >> "{calls}"
printf '\\n' >> "{calls}"
node=
for argument in "$@"; do
  case "$argument" in ANSIBLE_LIMIT=*) node=${{argument#ANSIBLE_LIMIT=}} ;; esac
done
[ "$1:$node" = "$FAILING" ] && exit 1
exit 0
""")
    (tools / "make").chmod(0o755)
    result = subprocess.run(["bash", "-c", commands.replace("<alias-1> <alias-2>", "node-a node-b")], capture_output=True,
                            text=True, timeout=10, env={**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
                                                        "FAILING": failing or "none"})
    assert result.returncode == 0, result.stderr
    steps = []
    for line in calls.read_text().splitlines():
        target, *assignments = line.rstrip("\x1f").split("\x1f")
        steps.append((target, dict(item.split("=", 1) for item in assignments)))
    return steps, result.stderr


def pair(node: str) -> list[tuple[str, str]]:
    return [("rotate-credentials", node), ("verify", node)]


# A failing step as `target:node`, the (target, node) steps that must run between decrypt and clean, and the stop message.
REVOCATION_CASES = [
    pytest.param(None, pair("node-a") + pair("node-b"), None, id="every-node-is-rotated-and-verified"),
    pytest.param("decrypt:", [], "decrypt failed; nothing rotated", id="a-failed-decrypt-never-reaches-the-loop"),
    pytest.param("rotate-credentials:node-a", pair("node-a")[:1], "stopped at node-a", id="rotate-fails-on-the-first-node"),
    pytest.param("rotate-credentials:node-b", pair("node-a") + pair("node-b")[:1], "stopped at node-b",
                 id="rotate-fails-on-the-second-node"),
    pytest.param("verify:node-a", pair("node-a"), "stopped at node-a", id="verify-fails-after-a-successful-rotate"),
]


def assert_revocation_sequence(steps, stderr, environment, rotated, message):
    # The decrypted file is created first and shredded last, even when decrypt or the loop fails.
    assert steps[0][0] == "decrypt" and steps[0][1]["ENV"] == environment
    assert steps[-1] == ("clean", {"ENV": environment})
    assert [(target, assignments["ANSIBLE_LIMIT"]) for target, assignments in steps[1:-1]] == rotated
    assert all(assignments["ENV"] == environment for _, assignments in steps[1:-1])
    for text in ("stopped at", "decrypt failed; nothing rotated"):
        assert (text in stderr) == (message is not None and message.startswith(text)), stderr
    if message is not None:
        assert message in stderr


@pytest.mark.parametrize("failing, rotated, message", REVOCATION_CASES)
def test_printed_revocation_loop_covers_every_node_cleans_up_and_stops_visibly(tmp_path, failing, rotated, message):
    sops_file = str(tmp_path / "sops dir" / "staging.secrets.sops.yaml")
    # Operator-supplied spellings with a space, a separator and a command substitution must reach Make as one argument each.
    environment, provider = "stag ing", f"het;zner $(touch {tmp_path}/executed)"
    steps, stderr = run_revocation(printed_revocation_commands(environment, provider, sops_file), tmp_path, failing)
    assert_revocation_sequence(steps, stderr, environment, rotated, message)
    # Decrypt reads the document the client was issued against, whatever its path.
    assert steps[0][1] == {"ENV": environment, "SOPS_FILE": sops_file}
    assert all(assignments["PROVIDER"] == provider for _, assignments in steps[1:-1])
    assert not (tmp_path / "executed").exists()


@pytest.mark.parametrize("failing, rotated, message", REVOCATION_CASES)
@pytest.mark.parametrize("runbook", RUNBOOK_SECTIONS)
def test_runbook_revocation_loop_stops_and_cleans_up_like_the_printed_one(tmp_path, runbook, failing, rotated, message):
    steps, stderr = run_revocation(runbook_revocation_commands(runbook), tmp_path, failing)
    assert_revocation_sequence(steps, stderr, "prod", rotated, message)
