"""Kernel systemd isolation probe; it establishes no registered vendor behavior."""
import ctypes
import json
import os
from pathlib import Path
import socket
import sys

values = {"host_pid_namespace_hidden": os.stat("/proc/self/ns/pid").st_ino != int(sys.argv[1])}
status = dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
capabilities = int(status['CapEff'].strip(),16)
values['no_authority_escape_capabilities'] = all(not capabilities & (1<<bit) for bit in [1,6,7,19,21])
values['required_network_administration'] = bool(capabilities & (1<<12))
values['no_new_privileges'] = status['NoNewPrivs'].strip() == '1'
for key, address in [('host_systemd_bus_masked','/run/systemd/private'),('host_management_bus_masked','/run/dbus/system_bus_socket')]:
    with socket.socket(socket.AF_UNIX) as connection:
        try:
            connection.connect(address)
            values[key] = False
        except OSError:
            values[key] = True
try:
    Path('/etc/molecule-vendor-escape').write_text('forbidden')
    values['host_filesystem_readonly'] = False
except OSError:
    values['host_filesystem_readonly'] = True
values['unrelated_credentials_masked'] = not os.access('/etc/ripdpi/transport-egress',os.R_OK)
values['ssh_and_account_keys_masked'] = not os.access('/etc/shadow',os.R_OK) and not os.access('/etc/ssh',os.R_OK)
values['public_trust_inputs_present'] = Path('/etc/ssl/certs').is_dir() and Path('/etc/machine-id').is_file()
values['host_namespace_handles_masked'] = not os.access('/run/netns',os.R_OK)
libc = ctypes.CDLL(None, use_errno=True)
values['new_namespace_refused'] = libc.unshare(0x40000000) != 0
fd = os.open('/dev/net/tun',os.O_RDWR)
os.close(fd)
values['actual_tun_device_available'] = True
Path('/var/log/cloudflare-warp/probe.json').write_text(json.dumps(values))
if not all(values.values()):
    raise SystemExit(1)
