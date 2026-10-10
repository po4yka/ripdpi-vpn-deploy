"""Real sshd effective denial, group, factor and forced-command admission gates."""

from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ansible/roles/real-vps-awg-nat/files/verify_ssh_admission.py"


@pytest.mark.parametrize(
    "extra,accepted",
    [
        ("", True),
        ("AuthenticationMethods publickey\n", True),
        ("DenyUsers evidence\n", False),
        ("DenyUsers unrelated\n", False),
        ("AllowGroups evidence-group\n", False),
        ("DenyGroups unrelated-group\n", False),
        ("AuthenticationMethods publickey,publickey\n", False),
        ("ForceCommand internal-sftp\n", False),
    ],
)
def test_effective_native_ssh_admission_does_not_confuse_allowusers_with_access(
    monkeypatch, extra, accepted
):
    spec = importlib.util.spec_from_file_location("verify_ssh_admission", SOURCE)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(
        prefix=".evidence-ssh-admission-", dir=Path.home()
    ) as directory:
        root = Path(directory)
        key = root / "host_key"
        config = root / "sshd_config"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
        )
        config.write_text(
            f"HostKey {key}\nPort 2222\nAllowUsers evidence\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\nAllowTcpForwarding no\nAllowAgentForwarding no\nX11Forwarding no\nPermitTunnel no\nPermitTTY no\nPermitUserRC no\n"
            + extra
        )
        invoke = subprocess.run

        def scoped(argv, **kwargs):
            assert argv[:2] == ["/usr/sbin/sshd", "-T"]
            return invoke(
                [*argv, "-f", str(config)], stdin=subprocess.DEVNULL, **kwargs
            )

        monkeypatch.setattr(helper.subprocess, "run", scoped)
        actual = helper.policy(
            "user=evidence,host=sentinel.example.test,addr=198.51.100.2,laddr=192.0.2.10,lport=2222"
        )
        assert (
            actual["allowusers"] == "evidence"
        ), "every negative fixture retains the apparent AllowUsers admission"
        request = {
            "user": "evidence",
            "local": "192.0.2.10",
            "sources": ["198.51.100.2"],
        }
        if accepted:
            helper.verify(request)
        else:
            with pytest.raises(ValueError):
                helper.verify(request)


def test_admission_gate_is_read_only_and_precedes_server_mutation():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/real-vps-awg-nat/tasks/server.yml").read_text()
    )
    gate = next(
        row
        for row in tasks
        if row["name"]
        == "Prove the reviewed restricted SSH admission before provisioning server state"
    )
    assert gate["check_mode"] is False and gate["changed_when"] is False
    assert gate["no_log"] is True and gate["diff"] is False
    assert tasks.index(gate) == 1 and "ansible.builtin.assert" in tasks[0]
