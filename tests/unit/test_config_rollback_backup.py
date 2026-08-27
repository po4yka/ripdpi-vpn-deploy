"""Ensure idempotent convergence does not overwrite rollback configs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_xray_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/xray/tasks/main.yml").read_text()
    assert "register: _xray_config_change" in content
    assert "- _xray_config_change.changed" in content


def test_hysteria_backup_requires_a_predicted_config_change():
    content = (ROOT / "ansible/roles/hysteria/tasks/main.yml").read_text()
    assert "register: _hysteria_config_change" in content
    assert "- _hysteria_config_change.changed" in content


def test_rotation_preserves_config_only_before_a_real_change():
    import yaml
    tasks = yaml.safe_load((ROOT / 'ansible/playbooks/rotate-credentials.yml').read_text())[0]['tasks']
    backup = next(task for task in tasks if task.get('ansible.builtin.copy', {}).get('dest') == '/etc/xray/config.json.prev')
    assert '_rotation_xray_change.changed' in backup['when']
    assert '_rotation_xray_stat.stat.exists' in backup['when']
    render_index = next(i for i, task in enumerate(tasks) if task['name'] == 'Re-render Xray config')
    assert tasks.index(backup) < render_index
    preview = next(task for task in tasks if task.get('register') == '_rotation_xray_change')
    assert preview['check_mode'] is True
    assert preview['ansible.builtin.template'] == tasks[render_index]['ansible.builtin.template']


def test_rollback_checks_exact_target_before_mutating_current_link():
    import yaml
    tasks = yaml.safe_load((ROOT / 'ansible/playbooks/rollback-xray.yml').read_text())[0]['tasks']
    switch = next(i for i, task in enumerate(tasks) if 'ansible.builtin.file' in task)
    validate = next(i for i, task in enumerate(tasks) if task['name'] == 'Validate current config with rollback binary')
    assert validate < switch
    assert tasks[validate]['ansible.builtin.command']['argv'][0] == '/opt/xray/releases/{{ rollback_xray_version }}/xray'
    assert any('rb_current.stat.lnk_source' in str(task) for task in tasks[:switch])


def test_rejected_rollback_binary_keeps_current_symlink(tmp_path):
    """Run the real Ansible tasks on local files; no service or fleet is touched."""
    import os
    import subprocess
    import yaml

    root = tmp_path / 'opt/xray'
    release = root / 'releases/v1.0.0'
    release.mkdir(parents=True)
    old = root / 'releases/v2.0.0'
    old.mkdir()
    current = root / 'current'
    current.symlink_to(old)
    binary = release / 'xray'
    binary.write_text('#!/bin/sh\nexit 42\n')
    binary.chmod(0o755)
    play = yaml.safe_load((ROOT / 'ansible/playbooks/rollback-xray.yml').read_text())[0]
    switch = next(i for i, task in enumerate(play['tasks']) if 'ansible.builtin.file' in task)
    play.update(hosts='localhost', become=False, vars={'rollback_xray_version': 'v1.0.0'})
    play['tasks'] = play['tasks'][:switch + 1]
    rendered = yaml.safe_dump([play], sort_keys=False).replace('/opt/xray', str(root))
    path = tmp_path / 'rollback.yml'
    path.write_text(rendered)
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
                            cwd=tmp_path, env={**os.environ, 'ANSIBLE_CONFIG': str(ROOT / 'ansible/ansible.cfg'),
                                             'ANSIBLE_NOCOLOR': '1'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'Validate current config with rollback binary' in result.stdout
    assert '42' in result.stdout
    assert current.resolve() == old
