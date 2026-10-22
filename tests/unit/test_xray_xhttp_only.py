"""XHTTP-only profile must still run a valid localhost Xray backend."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import copy
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from tests.site_role_graph import site_roles
from transport_fixtures import guarded_xray_bytes

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "xray" / "templates" / "config.json.j2"
SITE_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "site.yml"
ROTATION_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rotate-credentials.yml"
VERIFY_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "verify.yml"
NGINX_XHTTP_TASKS = (
    REPO_ROOT / "ansible" / "roles" / "nginx-xhttp" / "tasks" / "enable.yml"
)
ROLLBACK_PLAYBOOK = REPO_ROOT / "ansible" / "playbooks" / "rollback-xray.yml"

spec = importlib.util.spec_from_file_location("xhttp_only_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def test_p1_web_renders_only_the_local_xhttp_inbound() -> None:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load(
        (REPO_ROOT / "ansible" / "group_vars" / "vpn-p1-web.yml").read_text()
    )
    variables.update(profile)
    config = json.loads(renderer.render_template(TEMPLATE, variables))

    assert [inbound["tag"] for inbound in config["inbounds"]] == [
        "vless-xhttp-localhost"
    ]
    assert config["inbounds"][0]["listen"] == "127.0.0.1"
    assert config["inbounds"][0]["streamSettings"]["network"] == "xhttp"


@pytest.mark.parametrize("alternate_port", [0, 2053])
def test_p0_profile_inherits_the_shared_reality_shape_model(alternate_port: int) -> None:
    variables = renderer.merge_render_vars()
    profile = yaml.safe_load(
        (REPO_ROOT / "ansible" / "group_vars" / "vpn-p0-minimal.yml").read_text()
    )
    variables.update(profile)
    variables["xray_fallback_port"] = alternate_port

    config = json.loads(renderer.render_template(TEMPLATE, variables))
    expected_tags = ["vless-reality-primary", "vless-reality-fallback"] if alternate_port else ["vless-reality"]
    assert [inbound["tag"] for inbound in config["inbounds"]] == expected_tags
    assert [inbound["port"] for inbound in config["inbounds"]] == ([443, alternate_port] if alternate_port else [443])
    assert all(inbound["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"
               for inbound in config["inbounds"])


@pytest.mark.parametrize(
    ("scenario", "expected_port"), [("cohort", 2443), ("default", 2444)]
)
def test_installed_ansible_smoke_client_uses_the_shared_mux_and_finalmask_shape(
    tmp_path: Path, scenario: str, expected_port: int
) -> None:
    """The live smoke client must not retain a separate Vision-only shape."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for smoke shape parity"
    source = yaml.safe_load(
        (REPO_ROOT / "ansible/playbooks/smoke-test.yml").read_text()
    )[0]

    def find_task(tasks: list[dict], name: str) -> dict:
        for task in tasks:
            if task.get("name") == name:
                return task
            for nested in (
                task.get("block", []),
                task.get("rescue", []),
                task.get("always", []),
            ):
                found = find_task(nested, name)
                if found:
                    return found
        return {}

    included = yaml.safe_load(
        (REPO_ROOT / 'ansible/playbooks/tasks/smoke-reality.yml').read_text()
    )
    names = (
        "Require valid REALITY smoke cohort",
        "Select REALITY smoke client from cohort",
        "Require REALITY smoke client belongs to selected cohort",
        "Render Xray client config (REALITY)",
    )
    tasks = [copy.deepcopy(find_task(source['tasks'], 'Select every effective REALITY smoke listener')),
             {'name': 'Select first listener for shape assertion', 'ansible.builtin.set_fact':
              {'smoketest_reality_cohort': '{{ smoketest_reality_cohorts[0] }}'}}]
    tasks.extend(copy.deepcopy(find_task(included, name)) for name in names)
    assert all(tasks), "smoke playbook must retain cohort selection and render tasks"
    task = tasks[-1]
    destination = tmp_path / "xray-client.json"
    copy_args = task["ansible.builtin.copy"]
    copy_args.update(dest=str(destination))
    copy_args.pop("owner", None)
    copy_args.pop("group", None)
    copy_args.pop("mode", None)
    clients = [{"name": "chosen", "uuid": "fixture-uuid", "short_id": "abcd"}]
    cohorts: list[dict] = []
    vpn = {"xray_flow_mode": "mux-masked"}
    if scenario == "cohort":
        clients.insert(0, {"name": "other", "uuid": "other-uuid", "short_id": "dead"})
        cohorts = [
            {
                "name": "mux-shaped",
                "port": 2443,
                "flow_mode": "mux",
                "finalmask": True,
                "clients": ["chosen"],
            },
        ]
        vpn = {"xray_flow_mode": "vision", "xray_finalmask": False}

    play = [
        {
            "hosts": "localhost",
            "gather_facts": False,
            "become": False,
            "vars": {
                "ansible_python_interpreter": sys.executable,
                "p0_reality_shape_template": str(
                    REPO_ROOT / "ansible/templates/p0-reality-shape.json.j2"
                ),
                "smoketest_dir": str(tmp_path),
                "xray": {
                    "server_names": ["fixture.example"],
                    "reality_public_key": "fixture-public",
                    "clients": clients,
                    "cohorts": cohorts,
                },
                "xray_port": 2444,
                "vpn": vpn,
                "p0_reality_flow_mode": "vision",
                "p0_reality_shapes": {
                    "vision": {
                        "client_flow": "xtls-rprx-vision",
                        "client_mux": False,
                        "finalmask": False,
                    },
                    "mux": {"client_flow": "", "client_mux": True, "finalmask": False},
                    "mux-masked": {
                        "client_flow": "",
                        "client_mux": True,
                        "finalmask": True,
                    },
                },
            },
            "tasks": tasks,
        }
    ]
    playbook = tmp_path / "smoke-shape.yml"
    playbook.write_text(yaml.safe_dump(play, sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    env.update(
        ANSIBLE_CONFIG=str(config), ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local")
    )
    result = subprocess.run(
        [executable, "-i", "localhost,", "-c", "local", str(playbook)],
        capture_output=True,
        text=True,
        env=env,
        timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    config_json = json.loads(destination.read_text())
    outbound = config_json["outbounds"][0]
    assert outbound["settings"]["vnext"][0]["port"] == expected_port
    assert outbound["settings"]["vnext"][0]["users"][0]["id"] == "fixture-uuid"
    assert "flow" not in outbound["settings"]["vnext"][0]["users"][0]
    assert outbound["mux"] == {"enabled": True, "concurrency": 8}
    assert outbound["streamSettings"]["finalmask"] == {"tcp": [{"type": "sudoku", "settings": {}}]}


def _run_live_p0_shape_preflight(
    tmp_path: Path,
    profile: str,
    *,
    cohorts: list[dict] | None = None,
    vpn_override: dict | None = None,
) -> subprocess.CompletedProcess:
    """Execute the live role preflight with real profile replacement semantics."""
    executable = shutil.which("ansible-playbook")
    assert executable, "ansible-playbook is required for the P0 shape contract"
    root = tmp_path / "ansible"
    group_vars = root / "group_vars"
    group_vars.mkdir(parents=True)
    shutil.copyfile(
        REPO_ROOT / "ansible" / "group_vars" / "all.yml", group_vars / "all.yml"
    )
    shutil.copyfile(
        REPO_ROOT / "ansible" / "group_vars" / f"{profile}.yml",
        group_vars / f"{profile}.yml",
    )
    source = yaml.safe_load(
        (REPO_ROOT / "ansible" / "roles" / "xray" / "tasks" / "enable.yml").read_text()
    )
    names = {
        "Resolve the effective P0 REALITY shape",
        "Pre-flight — default P0 REALITY shape must be declared",
        "Pre-flight — cohort P0 REALITY shapes must be declared",
    }
    tasks = [task for task in source if task["name"] in names]
    assert {task["name"] for task in tasks} == names
    play = {
        "hosts": profile,
        "gather_facts": False,
        "become": False,
        "vars": {
            "ansible_python_interpreter": sys.executable,
            "xray": {"version": "fixture", "cohorts": cohorts or []},
        },
        "tasks": [
            *tasks,
            {
                "name": "Report effective P0 shape",
                "ansible.builtin.debug": {
                    "msg": "P0_SHAPE={{ p0_reality_effective_flow_mode }}"
                },
            },
        ],
    }
    playbook = root / "shape.yml"
    playbook.write_text(yaml.safe_dump([play], sort_keys=False))
    inventory = root / "inventory"
    inventory.write_text(f"[{profile}]\nlocalhost ansible_connection=local\n")
    config = root / "ansible.cfg"
    config.write_text("[defaults]\nretry_files_enabled = False\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    env.update(ANSIBLE_CONFIG=str(config), ANSIBLE_NOCOLOR="1", ANSIBLE_FORCE_COLOR="0")
    command = [executable, "-i", str(inventory), str(playbook)]
    if vpn_override:
        command.extend(["--extra-vars", json.dumps({"vpn": vpn_override})])
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=40)


@pytest.mark.parametrize("profile", ["vpn-p0-minimal", "vpn-family-standard"])
def test_installed_ansible_profiles_inherit_nonreplaceable_p0_flow_default(
    tmp_path: Path, profile: str
) -> None:
    result = _run_live_p0_shape_preflight(tmp_path, profile)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "P0_SHAPE=vision" in result.stdout


def test_installed_ansible_cohort_without_flow_inherits_profile_shape(
    tmp_path: Path,
) -> None:
    result = _run_live_p0_shape_preflight(
        tmp_path,
        "vpn-p0-minimal",
        cohorts=[{"name": "implicit", "port": 443, "clients": []}],
        vpn_override={"xray_flow_mode": "mux"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "P0_SHAPE=mux" in result.stdout


def test_site_playbook_runs_xray_for_reality_or_xhttp() -> None:
    playbook = yaml.safe_load(SITE_PLAYBOOK.read_text())[0]
    xray_role = next(role for role in site_roles(playbook) if role["role"] == "xray")
    enabled = xray_role["vars"]["xray_role_enabled"]
    assert "enable_xray_reality" in enabled
    assert "enable_nginx_xhttp" in enabled
    from scripts.template_render import render_fragment
    for reality, xhttp, subscription in [(False, False, False), (True, False, False),
                                         (False, True, False), (True, True, False), (True, True, True)]:
        selected = render_fragment('selected.txt', enabled, {
            'vpn': {'enable_xray_reality': reality, 'enable_nginx_xhttp': xhttp},
            'vpn_subscription_only': subscription,
        })
        assert selected == str((reality or xhttp) and not subscription)


def test_rotation_playbook_updates_xhttp_only_xray() -> None:
    playbook = ROTATION_PLAYBOOK.read_text()
    xray_task = playbook.split("- name: Stage rotated Xray credentials through the authoritative role", 1)[1].split(
        "- name: Stage rotated Hysteria credentials through the authoritative role",
        1,
    )[0]

    assert "enable_xray_reality" in xray_task
    assert "enable_nginx_xhttp" in xray_task
    assert "xray_log_path: /var/log/xray" in playbook


def test_xray_activation_has_one_guarded_owner_and_is_inert_in_check_mode() -> None:
    handlers = yaml.safe_load(
        (REPO_ROOT / "ansible" / "roles" / "xray" / "handlers" / "main.yml").read_text()
    )
    assert handlers == []
    activation = next(task for task in yaml.safe_load((REPO_ROOT / "ansible/roles/transport-egress/tasks/activate.yml").read_text()) if task["name"] == "Activate only a ready guarded generation after frontend staging")
    assert activation["when"] == "not ansible_check_mode"
    assert activation["block"][0]["ansible.builtin.systemd_service"]["name"] == "ripdpi-transport-generation.service"
    assert "status" in activation["block"][1]["ansible.builtin.command"]["argv"]


def test_private_masquerade_resolution_preserves_global_nss_authority() -> None:
    role_tasks = yaml.safe_load(NGINX_XHTTP_TASKS.read_text())
    assert all('ansible.builtin.blockinfile' not in task for task in role_tasks)
    assert '/etc/hosts' not in NGINX_XHTTP_TASKS.read_text()
    hysteria = REPO_ROOT / 'ansible/roles/hysteria'
    unit = (hysteria / 'templates/hysteria-server.service.j2').read_text()
    assert 'masquerade-hosts:/etc/hosts' in unit
    tasks = yaml.safe_load((hysteria / 'tasks/enable.yml').read_text())
    staged = next(task for task in tasks if task['name'] == 'Stage complete Hysteria authority for guarded consumer acceptance')
    expression = staged['ansible.builtin.set_fact']['transport_runtime_candidates']
    assert "hysteria_masquerade_hosts.content | b64encode" in expression
    assert staged['no_log'] and staged['diff'] is False
    assert not any(task.get('ansible.builtin.copy', {}).get('dest') == '{{ hysteria_config_dir }}/masquerade-hosts' and task.get('check_mode') is not True for task in tasks)


def _validation_binary(path: Path, trace: Path) -> None:
    """A local config parser exercises helper arguments/assets, not Xray semantics."""
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "assert sys.argv[1:4] == ['run', '-test', '-config']\n"
        "assert len(sys.argv) == 5\n"
        "assets = Path(os.environ['XRAY_LOCATION_ASSET'])\n"
        "assert (assets / 'fixture.dat').read_text() == 'validation asset'\n"
        f"Path({str(trace)!r}).write_text(json.dumps({{'argv': sys.argv[1:], 'assets': str(assets)}}))\n"
        "config = json.loads(Path(sys.argv[4]).read_text())\n"
        "assert config['outbounds'][0]['settings']['servers'][0]['users'][0]['pass'] in {'synthetic-outgoing-authority-00000000000000000000', 'synthetic-incoming-authority-00000000000000000000'}\n"
    )
    path.chmod(0o755)


def _run_xray_tasks(
    tmp_path: Path,
    play: dict,
    *,
    check: bool = False,
    validation_binary: Path | None = None,
) -> subprocess.CompletedProcess:
    """Execute source tasks locally; only paths and service effects are sandboxed."""
    executable = shutil.which("ansible-playbook")
    assert executable, "real Ansible is required for restore-point regressions"
    # Retain the production include_role and helper installation tasks, but give
    # the isolated role only temporary destinations and the real helper source.
    role = tmp_path / "roles/xray"
    (role / "tasks").mkdir(parents=True)
    (role / "files").mkdir()
    helper_source = REPO_ROOT / "ansible/roles/xray/files/xray_validate.py"
    shutil.copyfile(helper_source, role / "files/xray_validate.py")
    libexec = tmp_path / "libexec"
    libexec.mkdir()
    helper = libexec / "vpn-xray-validate"
    # Check-mode rollback runs on an already-deployed host: provision its
    # existing helper before the play, then let the real role reconcile it.
    shutil.copyfile(helper_source, helper)
    helper.chmod(0o755)
    helper_tasks = yaml.safe_load(
        (REPO_ROOT / "ansible/roles/xray/tasks/validation-helper.yml").read_text()
    )
    for task in helper_tasks:
        module = task.get("ansible.builtin.file", task.get("ansible.builtin.copy"))
        module.update(owner=str(os.getuid()), group=str(os.getgid()))
        for key in ("path", "dest"):
            if key in module:
                module[key] = module[key].replace("/usr/local/libexec", str(libexec))
    (role / "tasks/validation-helper.yml").write_text(yaml.safe_dump(helper_tasks))
    helper_command = str(helper)
    if validation_binary is not None:
        helper_command += " --binary " + shlex.quote(str(validation_binary))
    play = yaml.safe_load(
        yaml.safe_dump(play).replace(
            "/usr/local/libexec/vpn-xray-validate", helper_command
        )
    )
    assets = tmp_path / "runtime assets"
    assets.mkdir()
    (assets / "fixture.dat").write_text("validation asset")
    commands = tmp_path / "commands"
    commands.mkdir()
    systemctl = commands / "systemctl"
    systemctl.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "assert sys.argv[1:] == ['show', 'xray.service', '--property=Environment', '--value']\n"
        f"print({('XRAY_LOCATION_ASSET=' + shlex.quote(str(assets)))!r})\n"
    )
    systemctl.chmod(0o755)
    play.update(hosts="localhost", become=False, gather_facts=False)
    play.setdefault("vars", {})["ansible_python_interpreter"] = sys.executable
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump([play], sort_keys=False))
    config = tmp_path / "ansible.cfg"
    config.write_text(
        f"[defaults]\nretry_files_enabled = False\nroles_path = {tmp_path / 'roles'}\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ANSIBLE_")
    }
    env.update(
        ANSIBLE_CONFIG=str(config),
        ANSIBLE_LOCAL_TEMP=str(tmp_path / "ansible-local"),
        PATH=str(commands) + os.pathsep + os.environ["PATH"],
    )
    return subprocess.run(
        [
            executable,
            "-i",
            "localhost,",
            "-c",
            "local",
            str(path),
            *(["--check"] if check else []),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )


@pytest.mark.parametrize("filename, action", [("rollback-config.yml", "config"), ("rollback-xray.yml", "runtime")])
def test_operator_rollback_uses_the_same_native_acceptance_owner(filename, action):
    play = yaml.safe_load((REPO_ROOT / "ansible/playbooks" / filename).read_text())[0]
    command = play["tasks"][0]
    assert len(play["tasks"]) == 1
    assert "transport_runtime_rollback.py" in command["ansible.builtin.command"]["argv"]
    assert repr(action) in command["ansible.builtin.command"]["argv"]
    assert command["no_log"] is True and command["diff"] is False
    assert command["check_mode"] is False
    # Complete pinned native publication and recovery are exercised by the
    # isolated transport acceptance suite, including these operator entry points.


@pytest.mark.parametrize(
    "scenario",
    [
        "changed",
        "unchanged",
        "first-config",
        "check",
        "disabled",
        "xhttp-only",
        "reject-config",
    ],
)
def test_rotation_preserves_immediate_restore_point(
    tmp_path: Path, scenario: str
) -> None:
    rotation = yaml.safe_load(ROTATION_PLAYBOOK.read_text())[0]
    stages = next(task["block"] for task in rotation["tasks"] if task["name"] ==
                  "Reconcile protected credential rotation through authoritative roles")
    selected = next(task for task in stages if task.get("ansible.builtin.include_role") == {"name": "xray"})
    role = yaml.safe_load((REPO_ROOT / "ansible/roles/xray/tasks/enable.yml").read_text())
    names = {"Select staged Xray validation asset authority", "Check if previous Xray config exists",
             "Detect Xray config change before preserving rollback state",
             "Validate Xray candidate before quiescing the accepted route",
             "Stage complete Xray authority for guarded consumer acceptance"}
    tasks = [copy.deepcopy(task) for task in role if task["name"] in names]
    assert len(tasks) == len(names)
    current = tmp_path / "config.json"
    previous = tmp_path / "config.json.prev"
    old_bytes = guarded_xray_bytes('outgoing')
    if scenario != "first-config":
        current.write_text(old_bytes)
        os.chown(current, -1, os.getgid())
        current.chmod(0o640)
    previous.write_text("older restore point\n")
    os.chown(previous, -1, os.getgid())
    previous.chmod(0o640)
    desired = old_bytes if scenario == "unchanged" else guarded_xray_bytes('incoming')
    if scenario == "reject-config":
        desired = "{invalid candidate"
    template = tmp_path / "candidate.j2"
    template.write_text(desired)
    trace = tmp_path / "validated"
    binary = tmp_path / "xray"
    _validation_binary(binary, trace)
    def adapt(items):
        for task in items:
            for section in ("block", "always"):
                if section in task:
                    adapt(task[section])
            module = task.get("ansible.builtin.template", task.get("ansible.builtin.copy"))
            if module is not None:
                module.update(owner=str(os.getuid()), group=str(os.getgid()))
            if "ansible.builtin.template" in task:
                module["src"] = str(template)
    adapt(tasks)
    staged = next(task for task in tasks if task['name'].startswith('Stage complete Xray authority'))
    expression = staged['ansible.builtin.set_fact']['transport_runtime_candidates']
    expression = expression.replace("'config.json.j2'", repr(str(template)))
    unit_template = tmp_path / 'unit.j2'
    unit_template.write_text('ExecStart={{ xray_runtime_binary }} run -config {{ xray_etc_dir }}/config.json\n')
    expression = expression.replace("'xray.service.j2'", repr(str(unit_template)))
    staged['ansible.builtin.set_fact']['transport_runtime_candidates'] = expression
    staged_result = tmp_path / 'staged-result.json'
    tasks.append({'name': 'Retain private source-only staged candidate', 'ansible.builtin.copy': {
        'content': '{{ transport_runtime_candidates | to_json }}', 'dest': str(staged_result), 'mode': '0600'},
        'when': 'transport_runtime_candidates is defined', 'no_log': True, 'diff': False})
    play = {
        "tasks": [{"name": "Exercise canonical role restore point selected by rotation",
                   "when": "xray_role_enabled | bool", "block": tasks}],
        "vars": {
            **selected["vars"],
            "role_path": str(tmp_path / "roles/xray"),
            "xray_etc_dir": str(tmp_path), "xray_runtime_group": str(os.getgid()),
            "transport_egress_frontend_gids": {"xray": os.getgid()},
            "xray_runtime_binary": str(binary), "xray_asset_dir": str(tmp_path / "runtime assets"),
            "xray_runtime_bundled_asset_dir": str(tmp_path / "runtime assets"),
            "vpn": {
                "enable_xray_reality": scenario not in {"disabled", "xhttp-only"},
                "enable_nginx_xhttp": scenario == "xhttp-only",
            }
        },
    }
    result = _run_xray_tasks(
        tmp_path, play, check=scenario == "check", validation_binary=binary
    )
    assert (result.returncode != 0) == (scenario == "reject-config"), (
        result.stdout + result.stderr
    )
    assert trace.exists() == (
        scenario in {"changed", "unchanged", "first-config", "xhttp-only"}
    )
    if trace.exists():
        assert json.loads(trace.read_text())["assets"] == str(
            tmp_path / "runtime assets"
        )
    # Rendering and native admission stage authority without publishing it.
    # Real service/protocol adoption is exercised in the separate native lane.
    if scenario == 'first-config':
        assert not current.exists()
    else:
        assert current.read_text() == old_bytes
    assert previous.read_text() == 'older restore point\n'
    if scenario in {'changed', 'unchanged', 'first-config', 'xhttp-only'}:
        staged_candidates = json.loads(staged_result.read_text())
        config = next(item for item in staged_candidates if item['path'] == str(current))
        assert __import__('base64').b64decode(config['data']).decode() == desired
        assert config['mode'] == 0o640 and config['gid'] == os.getgid()
    assert previous.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize('existing', [False, True])
def test_geodata_check_mode_reports_unverified_future_assets_without_publication(tmp_path, existing):
    role = yaml.safe_load((REPO_ROOT / 'ansible/roles/xray/tasks/enable.yml').read_text())
    names = {'Require staged geodata authority before ordinary Xray admission',
             'Report unverified future geodata bytes during predictive Xray convergence',
             'Select staged Xray validation asset authority',
             'Check if previous Xray config exists',
             'Detect Xray config change before preserving rollback state',
             'Validate Xray candidate before quiescing the accepted route'}
    tasks = [copy.deepcopy(task) for task in role if task['name'] in names]
    assert len(tasks) == len(names)
    current, previous = tmp_path/'config.json', tmp_path/'config.json.prev'
    if existing:
        current.write_text(guarded_xray_bytes('outgoing')); current.chmod(0o640)
        previous.write_text('preceding-private-authority'); previous.chmod(0o640)
    before = {path: (path.read_bytes(), path.stat().st_ino) for path in (current,previous) if path.exists()}
    template = tmp_path/'candidate.j2'
    template.write_text(guarded_xray_bytes('incoming'))
    def adapt(items):
        for task in items:
            for key in ('block','always'):
                if key in task:
                    adapt(task[key])
            if 'ansible.builtin.template' in task:
                module = task['ansible.builtin.template']
                module.update(src=str(template), owner=str(os.getuid()), group=str(os.getgid()))
    adapt(tasks)
    assets = tmp_path/'selected-assets'
    if existing:
        assets.mkdir(); (assets/'geoip.dat').write_bytes(b'preceding-asset')
    asset_before = (assets/'geoip.dat').read_bytes() if existing else None
    tasks.append({'name':'Observe source-owned predictive asset selection', 'ansible.builtin.debug':{
        'msg':'selected-authority={{ _xray_candidate_asset_dir }}'}})
    play = {'tasks':tasks, 'vars':{'role_path':str(tmp_path/'roles/xray'),
        'xray_etc_dir':str(tmp_path), 'xray_runtime_group':str(os.getgid()),
        'xray_runtime_binary':str(tmp_path/'missing-future-runtime'), 'xray_asset_dir':str(assets),
        'vpn':{'enable_geodata':True}}}
    result = _run_xray_tasks(tmp_path, play, check=True)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'remain unverified until ordinary convergence' in result.stdout
    assert 'selected-authority='+str(assets) in result.stdout
    assert {path: (path.read_bytes(), path.stat().st_ino) for path in (current,previous) if path.exists()} == before
    assert ((assets/'geoip.dat').read_bytes() if existing else None) == asset_before
    assert not (tmp_path/'missing-future-runtime').exists()
    assert not any(tmp_path.glob('*.xray.json'))
