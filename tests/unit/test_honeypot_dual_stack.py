"""Honeypot listener and verification must honor both public IP families."""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "scripts" / "check-templates-render.py"
TEMPLATE = REPO_ROOT / "ansible" / "roles" / "honeypot" / "templates" / "honeypot.py.j2"
SECURITY_VERIFY = REPO_ROOT / "ansible" / "playbooks" / "security-verify.yml"
MOLECULE_VERIFY = REPO_ROOT / "ansible" / "roles" / "honeypot" / "molecule" / "default" / "verify.yml"

renderer_spec = importlib.util.spec_from_file_location("honeypot_dual_stack_renderer", RENDERER)
renderer = importlib.util.module_from_spec(renderer_spec)
sys.modules[renderer_spec.name] = renderer
renderer_spec.loader.exec_module(renderer)


def test_honeypot_binds_and_verifies_ipv4_and_ipv6(tmp_path: Path, monkeypatch) -> None:
    variables = renderer.merge_render_vars()
    variables["server_ipv6"] = "2001:db8::10"
    variables["honeypot"] = {
        **variables["honeypot"],
        "log_dir": str(tmp_path / "log"),
        "textfile_dir": str(tmp_path / "textfile"),
    }
    source = renderer.render_template(TEMPLATE, variables)
    module_path = tmp_path / "rendered_honeypot.py"
    module_path.write_text(source, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("rendered_dual_stack_honeypot", module_path)
    honeypot = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = honeypot
    spec.loader.exec_module(honeypot)

    class FakeSocket:
        def __init__(self, family: int) -> None:
            self.family = family
            self.options: list[tuple[int, int, int]] = []
            self.address = None
            self.backlog = None

        def setsockopt(self, level: int, option: int, value: int) -> None:
            self.options.append((level, option, value))

        def bind(self, address) -> None:
            self.address = address

        def listen(self, backlog: int) -> None:
            self.backlog = backlog

        def close(self) -> None:
            pass

    sockets: list[FakeSocket] = []

    def socket_factory(family: int, _kind: int) -> FakeSocket:
        created = FakeSocket(family)
        sockets.append(created)
        return created

    monkeypatch.setattr(honeypot.socket, "socket", socket_factory)

    listeners = honeypot._create_listener_sockets()

    assert listeners == sockets
    assert [listener.family for listener in listeners] == [socket.AF_INET, socket.AF_INET6]
    assert sockets[0].address == (honeypot.LISTEN_ADDR, honeypot.LISTEN_PORT)
    assert sockets[1].address == ("::", honeypot.LISTEN_PORT)
    assert (socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1) in sockets[1].options
    assert all(listener.backlog == 128 for listener in listeners)

    security_verify = SECURITY_VERIFY.read_text(encoding="utf-8")
    molecule_verify = MOLECULE_VERIFY.read_text(encoding="utf-8")
    for verification in (security_verify, molecule_verify):
        assert "ss -H -lnt4" in verification
        assert "ss -H -lnt6" in verification
