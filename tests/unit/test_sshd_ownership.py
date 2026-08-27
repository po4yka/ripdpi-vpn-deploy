"""Validate prospective managed SSH policy with the installed OpenSSH parser."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from template_render import merge_render_vars, render_template


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / 'ansible/roles/baseline/files/validate-sshd.py'


@pytest.fixture
def ssh_config(tmp_path):
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(tmp_path / 'key')], check=True)
    includes = tmp_path / 'sshd_config.d'
    includes.mkdir()
    main = tmp_path / 'sshd_config'
    main.write_text(f'HostKey {tmp_path}/key\nInclude {includes}/*.conf\n')
    boot = includes / '10-cloud-init-hardening.conf'
    boot.write_text('Port 2222\nPasswordAuthentication no\n')
    managed = includes / '20-ansible-hardening.conf'
    managed.write_text('X11Forwarding yes\nAllowTcpForwarding yes\n')
    candidate = tmp_path / 'candidate'
    candidate.write_text('X11Forwarding no\nAllowTcpForwarding no\n')
    return main, boot, managed, candidate


def validate(paths):
    main, boot, managed, candidate = paths
    return subprocess.run([
        sys.executable, str(VALIDATOR), '--main', str(main), '--boot', str(boot),
        '--managed', str(managed), '--sshd', '/usr/sbin/sshd', str(candidate),
    ], capture_output=True, text=True)


def test_candidate_is_validated_in_assembled_configuration_before_write(ssh_config):
    result = validate(ssh_config)
    assert result.returncode == 0, result.stderr
    assert 'X11Forwarding yes' in ssh_config[2].read_text()


def test_duplicate_boot_directive_fails_before_write(ssh_config):
    ssh_config[1].write_text('Port 2222\nX11Forwarding no\n')
    result = validate(ssh_config)
    assert result.returncode != 0
    assert 'duplicate' in result.stderr and 'x11forwarding' in result.stderr


def test_unmanaged_shadow_fails_effective_configuration_validation(ssh_config):
    (ssh_config[1].parent / '00-shadow.conf').write_text('AllowTcpForwarding yes\n')
    result = validate(ssh_config)
    assert result.returncode != 0
    assert 'allowtcpforwarding' in result.stderr and 'effective' in result.stderr


def test_first_managed_install_is_validated_at_its_include_position(ssh_config):
    ssh_config[2].unlink()
    assert validate(ssh_config).returncode == 0


def test_missing_include_does_not_claim_the_managed_policy_is_effective(ssh_config):
    main = ssh_config[0]
    main.write_text(main.read_text().split('Include')[0])
    result = validate(ssh_config)
    assert result.returncode != 0
    assert 'not included' in result.stderr


def test_real_managed_template_and_bootstrap_have_one_owner_and_valid_algorithms(ssh_config):
    cloud = yaml.safe_load((ROOT / 'terraform/shared/cloud-init.yaml.tftpl').read_text())
    bootstrap = next(item['content'] for item in cloud['write_files']
                     if item['path'].endswith('10-cloud-init-hardening.conf'))
    ssh_config[1].write_text(bootstrap.replace('${ssh_port}', '2222'))
    candidate = render_template(
        ROOT / 'ansible/roles/baseline/templates/sshd_config.d-hardening.conf.j2',
        merge_render_vars(),
    )
    ssh_config[3].write_text(candidate)
    result = validate(ssh_config)
    assert result.returncode == 0, result.stderr
    for key in ('Ciphers', 'MACs', 'KexAlgorithms'):
        assert f'\n{key} ' in candidate
