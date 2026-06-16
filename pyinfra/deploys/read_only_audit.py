"""Read-only pyinfra pilot for host audit checks.

Ansible remains the source of truth for configuration and remediation. Keep this deploy limited to observation commands; do not add package, file, service, or template mutations here.
"""

from __future__ import annotations

from pyinfra.operations import server


SSHD_SETTINGS = (
    "allowagentforwarding",
    "allowtcpforwarding",
    "kbdinteractiveauthentication",
    "maxsessions",
    "maxstartups",
    "passwordauthentication",
    "permitrootlogin",
    "permittunnel",
    "permituserenvironment",
    "pubkeyauthentication",
    "x11forwarding",
)

KNOWN_SERVICES = (
    "xray",
    "nginx",
    "hysteria-server",
    "awg-quick@awg0",
    "prometheus-node-exporter",
    "vpn-watchdog.timer",
    "vpn-backup.timer",
    "fail2ban",
    "unattended-upgrades",
)


server.shell(
    name="Read hostname",
    commands=["hostname"],
)

server.shell(
    name="Read OS release",
    commands=["uname -a; test ! -r /etc/os-release || cat /etc/os-release"],
)

server.shell(
    name="Report effective sshd hardening settings",
    commands=[
        "sshd -T | awk '/^("
        + "|".join(SSHD_SETTINGS)
        + ") / { print }'; rc=$?; echo sshd_effective_settings_rc=$rc; exit 0",
    ],
    _sudo=True,
)

server.shell(
    name="Check nftables configuration syntax",
    commands=["nft -c -f /etc/nftables.conf; rc=$?; echo nft_syntax_rc=$rc; exit 0"],
    _sudo=True,
)

server.shell(
    name="Check node capability manifest",
    commands=[
        "if test -r /var/lib/ripdpi-vpn-deploy/manifest.json; then "
        "python3 -m json.tool /var/lib/ripdpi-vpn-deploy/manifest.json >/dev/null "
        "&& echo manifest=valid_json || echo manifest=invalid_json; "
        "else echo manifest=missing; fi",
    ],
    _sudo=True,
)

for service in KNOWN_SERVICES:
    server.shell(
        name=f"Report service state: {service}",
        commands=[f"systemctl is-active {service}; rc=$?; echo {service}_active_rc=$rc; exit 0"],
        _sudo=True,
    )
