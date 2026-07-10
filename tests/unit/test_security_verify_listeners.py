"""Ensure listener verification fails for missing contract listeners."""

from pathlib import Path


def test_security_verify_checks_expected_listeners_are_present():
    playbook = Path(__file__).resolve().parents[2] / "ansible/playbooks/security-verify.yml"
    content = playbook.read_text()
    assert 'echo "missing tcp ${port}"' in content
    assert 'echo "missing udp ${port}"' in content
