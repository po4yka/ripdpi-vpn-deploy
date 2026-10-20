"""Operator incident verbs act on exactly one named inventory alias."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
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


# Every guarded sequence the runbooks print: its runbook, the heading of its section and the step that faults it midway,
# the last `make` call before cleanup. The revocation sequences rotate and verify every node; the others deploy once.
GUARDED_SEQUENCES = {
    "rotate-revocation": ("RUNBOOK-rotate.md", "## 1. Single client leak", "rotate-credentials:node-a"),
    "deploy-add-client": ("RUNBOOK-deploy.md", "## Add a new client device", "rotate-credentials:node-a"),
    "reality-keypair": ("RUNBOOK-rotate.md", "## 2. Server-wide REALITY keypair", "deploy:"),
    "restic-password": ("RUNBOOK-rotate.md", "## 4. Restic password", "deploy:"),
}
REVOCATION_SEQUENCES = ("rotate-revocation", "deploy-add-client")
DEPLOY_SEQUENCES = ("reality-keypair", "restic-password")
# The exit statuses of the `make` stand-in at the step it is told to fail and when it runs `make clean`; the file it
# creates once `make clean` has completed.
STAND_IN_FAILURE = 7
CLEAN_FAILURE = 9
SHREDDED = "shredded"


def guarded_sequence(sequence: str) -> str:
    """The same subshell as the named runbook section prints it."""
    runbook, heading, _ = GUARDED_SEQUENCES[sequence]
    section = (ROOT / "docs" / runbook).read_text().split(heading, 1)[1].split("\n## ", 1)[0]
    block = re.search(r"^\(\n.*?^\)$", section, re.S | re.M)
    assert block, f"{runbook} no longer prints a guarded subshell under {heading!r}"
    return block.group(0)


# The signals an operator can send from the terminal or the system, with their numbers.
SIGNALS = (("INT", signal.SIGINT), ("QUIT", signal.SIGQUIT), ("TERM", signal.SIGTERM), ("HUP", signal.SIGHUP))


def reset_signal_dispositions() -> None:
    """Undo SIGINT/SIGQUIT/SIGHUP ignoring inherited from a background or `nohup` run, which a shell cannot trap."""
    for _, number in SIGNALS:
        signal.signal(number, signal.SIG_DFL)


def run_guarded_sequence(commands: str, tmp_path: Path, fault: str | None, signal_name: str | None = None,
                         whole_group: bool = False, *, clean_fails: bool = False, clean_signal: str | None = None,
                         environment: str = "prod") -> tuple[list[tuple[str, dict[str, str]]], str, int]:
    """Run printed commands against a recording `make` stand-in that faults the step named `target:node`.

    The stand-in exits with STAND_IN_FAILURE at that step or, when `signal_name` is given, delivers that signal to the
    shell running it and exits cleanly, as an operator interrupting a long rotation would. With `whole_group` the
    signal goes to the whole process group instead, as a terminal delivers it, so the stand-in `make` dies of it too.
    `make clean` creates SHREDDED when it completes, unless `clean_fails` makes it exit with CLEAN_FAILURE; with
    `clean_signal` it first delivers that signal to the whole process group, as a second Ctrl-C does.
    `environment` replaces the value the block assigns to its one `e` variable.
    """
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
if [ "$1" = clean ]; then
  [ -n "$CLEAN_SIGNAL" ] && kill -s "$CLEAN_SIGNAL" 0
  [ -n "$CLEAN_FAILS" ] && exit {CLEAN_FAILURE}
  : > "{tmp_path / SHREDDED}"
  exit 0
fi
if [ "$1:$node" = "$FAULT" ]; then
  [ -n "$SIGNAL" ] && {{ kill -s "$SIGNAL" "${{SIGNAL_TARGET:-$PPID}}"; exit 0; }}
  exit {STAND_IN_FAILURE}
fi
exit 0
""")
    (tools / "make").chmod(0o755)
    # The outer shell stands for the operator's interactive one, which survives the terminal's signal and reports the
    # status of the sequence; it needs its own session so that a group-wide signal reaches nothing else.
    commands = commands.replace("<alias-1> <alias-2>", "node-a node-b").replace("  e=prod\n", f"  e={environment}\n")
    result = subprocess.run(["bash", "-c", f"trap : INT QUIT TERM HUP\n{commands}\nexit $?"], capture_output=True,
                            text=True, timeout=10, preexec_fn=reset_signal_dispositions, start_new_session=True, cwd=tmp_path,
                            env={**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "FAULT": fault or "none",
                                 "SIGNAL": signal_name or "", "CLEAN_SIGNAL": clean_signal or "",
                                 "CLEAN_FAILS": "1" if clean_fails else "",
                                 **({"SIGNAL_TARGET": "0"} if whole_group else {})})
    steps = []
    for line in calls.read_text().splitlines():
        target, *assignments = line.rstrip("\x1f").split("\x1f")
        steps.append((target, dict(item.split("=", 1) for item in assignments)))
    return steps, result.stderr, result.returncode


def pair(node: str) -> list[tuple[str, str]]:
    return [("rotate-credentials", node), ("verify", node)]


# A faulted step as `target:node`, the signal delivered there (None: the step fails), the (target, node) steps that must
# run between decrypt and clean, the stop message, and the exit status of the whole sequence.
REVOCATION_CASES = [
    pytest.param(None, None, pair("node-a") + pair("node-b"), None, 0, id="every-node-is-rotated-and-verified"),
    pytest.param("decrypt:", None, [], "decrypt failed; nothing rotated", STAND_IN_FAILURE,
                 id="a-failed-decrypt-never-reaches-the-loop"),
    pytest.param("rotate-credentials:node-a", None, pair("node-a")[:1], "stopped at node-a", STAND_IN_FAILURE,
                 id="rotate-fails-on-the-first-node"),
    pytest.param("rotate-credentials:node-b", None, pair("node-a") + pair("node-b")[:1], "stopped at node-b",
                 STAND_IN_FAILURE, id="rotate-fails-on-the-second-node"),
    pytest.param("verify:node-a", None, pair("node-a"), "stopped at node-a", STAND_IN_FAILURE,
                 id="verify-fails-after-a-successful-rotate"),
    *(pytest.param("rotate-credentials:node-a", name, pair("node-a")[:1], None, 128 + number,
                   id=f"sig{name.lower()}-during-a-rotation-stops-the-loop-and-cleans-up")
      for name, number in SIGNALS),
    pytest.param("decrypt:", "INT", [], None, 128 + signal.SIGINT, id="sigint-during-decrypt-still-cleans-up"),
]


def assert_revocation_sequence(steps, stderr, environment, rotated, message):
    # The decrypted file is created first and shredded last, even when decrypt, the loop or the operator interrupts it.
    assert steps[0][0] == "decrypt" and steps[0][1]["ENV"] == environment
    assert steps[-1] == ("clean", {"ENV": environment})
    assert [(target, assignments["ANSIBLE_LIMIT"]) for target, assignments in steps[1:-1]] == rotated
    assert all(assignments["ENV"] == environment for _, assignments in steps[1:-1])
    for text in ("stopped at", "decrypt failed; nothing rotated"):
        assert (text in stderr) == (message is not None and message.startswith(text)), stderr
    if message is not None:
        assert message in stderr


@pytest.mark.parametrize("fault, signal_name, rotated, message, status", REVOCATION_CASES)
@pytest.mark.parametrize("sequence", REVOCATION_SEQUENCES)
def test_runbook_revocation_sequence_cleans_up_on_every_exit_and_keeps_the_failing_status(
        tmp_path, sequence, fault, signal_name, rotated, message, status):
    steps, stderr, returncode = run_guarded_sequence(guarded_sequence(sequence), tmp_path, fault, signal_name)
    assert_revocation_sequence(steps, stderr, "prod", rotated, message)
    # Cleanup succeeds in every case, so a failed or interrupted sequence keeps its own status instead of clean's zero.
    assert returncode == status, stderr


@pytest.mark.parametrize("name, number", SIGNALS)
@pytest.mark.parametrize("sequence", REVOCATION_SEQUENCES)
def test_runbook_revocation_sequence_cleans_up_when_a_terminal_signals_the_whole_process_group(
        tmp_path, sequence, name, number):
    """Ctrl-C, Ctrl-\\ and a hangup reach `make` and the subshell together, so `make` dies of the signal as well."""
    steps, stderr, returncode = run_guarded_sequence(guarded_sequence(sequence), tmp_path, "rotate-credentials:node-a",
                                                     name, whole_group=True)
    assert_revocation_sequence(steps, stderr, "prod", pair("node-a")[:1], None)
    assert returncode == 128 + number, stderr


@pytest.mark.parametrize("sequence", REVOCATION_SEQUENCES)
def test_runbook_revocation_sequence_takes_its_environment_from_one_variable(tmp_path, sequence):
    """Adapting the block for another environment changes one line; a missed literal would shred the wrong file."""
    steps, stderr, returncode = run_guarded_sequence(guarded_sequence(sequence), tmp_path, None, environment="staging")
    assert_revocation_sequence(steps, stderr, "staging", pair("node-a") + pair("node-b"), None)
    assert returncode == 0, stderr


# A faulted step as `target:`, the signal delivered there (None: the step fails), the make targets that must run before
# clean, and the exit status of the whole sequence.
DEPLOY_CASES = [
    pytest.param(None, None, ["decrypt", "deploy", "verify"], 0, id="every-step-runs-in-order"),
    pytest.param("decrypt:", None, ["decrypt"], STAND_IN_FAILURE, id="a-failed-decrypt-never-reaches-deploy"),
    pytest.param("deploy:", None, ["decrypt", "deploy"], STAND_IN_FAILURE, id="a-failed-deploy-skips-verify"),
    pytest.param("verify:", None, ["decrypt", "deploy", "verify"], STAND_IN_FAILURE, id="a-failed-verify-still-cleans-up"),
    *(pytest.param("deploy:", name, ["decrypt", "deploy"], 128 + number,
                   id=f"sig{name.lower()}-during-deploy-stops-the-sequence-and-cleans-up")
      for name, number in SIGNALS),
]


@pytest.mark.parametrize("fault, signal_name, ran, status", DEPLOY_CASES)
@pytest.mark.parametrize("sequence", DEPLOY_SEQUENCES)
def test_runbook_deploy_sequences_clean_up_last_and_keep_the_failing_status(tmp_path, sequence, fault, signal_name, ran,
                                                                          status):
    steps, stderr, returncode = run_guarded_sequence(guarded_sequence(sequence), tmp_path, fault, signal_name)
    # Nothing selects an environment here, so every call runs with the Makefile's own default.
    assert steps == [(target, {}) for target in [*ran, "clean"]], stderr
    assert returncode == status, stderr


@pytest.mark.parametrize("fails_midway, status", [(False, 1), (True, STAND_IN_FAILURE)],
                         ids=["after-success-exits-nonzero", "after-a-failed-step-keeps-its-status"])
@pytest.mark.parametrize("sequence", GUARDED_SEQUENCES)
def test_runbook_failed_cleanup_makes_a_successful_sequence_fail_and_keeps_a_failing_status(
        tmp_path, sequence, fails_midway, status):
    fault = GUARDED_SEQUENCES[sequence][2] if fails_midway else None
    steps, stderr, returncode = run_guarded_sequence(guarded_sequence(sequence), tmp_path, fault, clean_fails=True)
    assert steps[-1][0] == "clean" and not (tmp_path / SHREDDED).exists(), stderr
    assert returncode == status, stderr


@pytest.mark.parametrize("name", [name for name, _ in SIGNALS])
@pytest.mark.parametrize("sequence", GUARDED_SEQUENCES)
def test_runbook_second_signal_during_cleanup_does_not_cut_the_shred_short(tmp_path, sequence, name):
    """The interrupt that ends the sequence is followed by a second signal that reaches `make clean` with the group."""
    steps, stderr, returncode = run_guarded_sequence(guarded_sequence(sequence), tmp_path, GUARDED_SEQUENCES[sequence][2],
                                                     "INT", clean_signal=name)
    assert steps[-1][0] == "clean" and (tmp_path / SHREDDED).exists(), stderr
    assert returncode == 128 + signal.SIGINT, stderr


def redeploy_blocks() -> list[str]:
    """The preflight, deploy and journal-recovery subshells of the ordinary re-deploy recipe, in order."""
    section = (ROOT / "docs/RUNBOOK-deploy.md").read_text().split("### Ordinary re-deploy recipe", 1)[1]
    section = section.split("\n## ", 1)[0]
    blocks = re.findall(r"^\(\n.*?^\)$", section, re.S | re.M)
    assert len(blocks) == 3, "the re-deploy recipe no longer prints its three guarded subshells"
    return blocks


# A block index, a faulted step as `target:node`, the signal delivered there (None: the step fails), the make targets
# that must run, and the exit status of the block.
REDEPLOY_CASES = [
    pytest.param(0, None, None, ["decrypt", "validate", "dry-run"], 0, id="preflight-success-keeps-plaintext-for-review"),
    pytest.param(0, "decrypt:", None, ["decrypt", "clean"], STAND_IN_FAILURE, id="preflight-decrypt-fails"),
    pytest.param(0, "dry-run:", None, ["decrypt", "validate", "dry-run", "clean"], STAND_IN_FAILURE,
                 id="preflight-dry-run-fails"),
    *(pytest.param(0, "dry-run:", name, ["decrypt", "validate", "dry-run", "clean"], 128 + number,
                   id=f"preflight-sig{name.lower()}-cleans-up") for name, number in SIGNALS),
    pytest.param(1, None, None, ["deploy", "verify", "source-drift", "clean"], 0, id="deploy-success-cleans-up"),
    pytest.param(1, "deploy:", None, ["deploy", "clean"], STAND_IN_FAILURE, id="deploy-fails"),
    pytest.param(1, "verify:", None, ["deploy", "verify", "clean"], STAND_IN_FAILURE, id="verify-fails"),
    *(pytest.param(1, "deploy:", name, ["deploy", "clean"], 128 + number,
                   id=f"deploy-sig{name.lower()}-cleans-up") for name, number in SIGNALS),
    pytest.param(2, None, None, ["decrypt", "deploy", "clean"], 0, id="recovery-success-cleans-up"),
    pytest.param(2, "deploy:<exact-alias>", None, ["decrypt", "deploy", "clean"], STAND_IN_FAILURE,
                 id="recovery-deploy-fails"),
]


@pytest.mark.parametrize("block, fault, signal_name, ran, status", REDEPLOY_CASES)
def test_redeploy_recipe_cleans_plaintext_unless_a_successful_preflight_awaits_review(
        tmp_path, block, fault, signal_name, ran, status):
    steps, stderr, returncode = run_guarded_sequence(redeploy_blocks()[block], tmp_path, fault, signal_name)
    assert [target for target, _ in steps] == ran, stderr
    assert returncode == status, stderr


@pytest.mark.parametrize("block, fault, status", [(0, "dry-run:", STAND_IN_FAILURE), (1, None, 1),
                                                   (1, "deploy:", STAND_IN_FAILURE)])
def test_redeploy_recipe_failed_cleanup_never_hides_a_failure(tmp_path, block, fault, status):
    steps, stderr, returncode = run_guarded_sequence(redeploy_blocks()[block], tmp_path, fault, clean_fails=True)
    assert steps[-1][0] == "clean", stderr
    assert returncode == status, stderr
