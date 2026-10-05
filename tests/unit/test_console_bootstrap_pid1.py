"""Real kernel/PID1 expiry in private namespaces, not VPS identity proof."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.native_runtime
def test_console_lease_real_pid1_expiry_and_private_runtime_paths():
    assert sys.platform == 'linux' and os.geteuid() == 0
    assert Path('/proc/1/comm').read_text().strip() == 'systemd'
    nonce = uuid.uuid4().hex
    anchor = 'vpn-console-test-'+nonce
    root = Path(tempfile.mkdtemp(prefix='vpn-console-test-', dir='/run'))
    shadow = root/'shadow-run'
    shadow.mkdir(mode=0o755)
    main = root/'main.nft'
    main.write_bytes(b'#!/usr/sbin/nft -f\n# Managed by Ansible role `firewall`. Hand edits will be overwritten.\ndestroy table inet filter\ntable inet filter {\n  chain input {\n    type filter hook input priority 0; policy drop;\n    tcp dport 443 accept\n    counter drop\n  }\n}\n')
    source = (ROOT/'scripts/console_bootstrap_guest.py').read_text()
    try:
        subprocess.run(['systemd-run','--quiet','--unit='+anchor,'--property=PrivateNetwork=yes',
                        '/usr/bin/sleep','infinity'], capture_output=True, timeout=15, check=True)
        pid = int(subprocess.run(['systemctl','show',anchor,'--property=MainPID','--value'],
                                 capture_output=True, timeout=15, check=True).stdout.strip())
        assert pid > 1
        program = textwrap.dedent('''
            import os,json,time,stat,subprocess
            from pathlib import Path
            subprocess.run(['mount','--bind',MAIN,'/etc/nftables.conf'],check=True)
            subprocess.run(['mount','--bind',SHADOW,'/run'],check=True)
            request={'schema_version':1,'nonce':NONCE,'hostname':'node-one','root_filesystem_uuid':'00000000-0000-0000-0000-000000000001','host_key_sha256':'a'*64,'inventory_alias':'node-one','public_address':'192.0.2.10','ssh_port':22,'public_sources':['198.51.100.20'],'source_revision':'b'*40,'deployable_digest':'c'*64,'expires_at':int(time.time())+90}
            real=scope['command']
            def command(argv,**kwargs):
                if argv[0]=='systemd-run':
                    # Only test isolation changes: the real production timer
                    # sources and revoker run under the actual host PID1.
                    argv=['nsenter','--mount=/proc/1/ns/mnt',*argv[:1],
                          '--property=NetworkNamespacePath=/proc/'+str(PID)+'/ns/net',
                          '--property=BindPaths='+STATE+':/run/vpn-console-bootstrap',*argv[1:]]
                return real(argv,**kwargs)
            scope['command']=command
            original_statvfs=scope['os'].statvfs
            scope['os'].statvfs=lambda path: __import__('types').SimpleNamespace(f_flag=os.ST_RDONLY) if path=='/' else original_statvfs(path)
            old=os.umask(0o077)
            try: scope['boot'](request,SOURCE)
            finally: os.umask(old)
            # Exact VPS identity/read-only-root remain explicit fixtures.
            scope['identity']=lambda value: None
            loaded=subprocess.run(['nft','-f','/etc/nftables.conf'],capture_output=True)
            assert loaded.returncode==0,loaded.stderr.decode()
            for path in ['/run/systemd','/run/systemd/system','/run/systemd/system/multi-user.target.wants']:
                assert stat.S_IMODE(Path(path).stat().st_mode)==0o755
            assert stat.S_IMODE(Path('/run/vpn-console-bootstrap').stat().st_mode)==0o700
            scope['apply']()
            owned=lambda: [row for row in json.loads(real(['nft','-j','list','ruleset']))['nftables'] if row.get('rule',{}).get('comment')=='vpn-console-lease:'+request['nonce']]
            assert len(owned())==1
            end=time.monotonic()+100
            while owned() and time.monotonic()<end: time.sleep(.25)
            assert not owned()
            scope['revoke']()
            print(json.dumps({'kernel_expiry':'passed','pid1_timer':'passed','runtime_modes':'passed','idempotent_revoke':'passed','vps_identity':'fixture-only','readonly_root':'fixture-only'}))
        ''')
        for key, value in {'SHADOW':str(shadow),'MAIN':str(main),'NONCE':nonce,'PID':pid,
                           'STATE':str(shadow/'vpn-console-bootstrap'),'SOURCE':source}.items():
            program = program.replace(key, repr(value))
        program = 'scope={"__name__":"console_native_test"};exec('+repr(source)+',scope)\n'+program
        result = subprocess.run(['nsenter','--net=/proc/'+str(pid)+'/ns/net','unshare','--mount',
                                 '--propagation','private',sys.executable,'-I','-B','-'],
                                input=program.encode(), capture_output=True, timeout=120, check=False)
        assert result.returncode == 0, result.stderr.decode()[-2500:]
        value = json.loads(result.stdout.decode().splitlines()[-1])
        assert value == {'kernel_expiry':'passed','pid1_timer':'passed','runtime_modes':'passed',
                         'idempotent_revoke':'passed','vps_identity':'fixture-only','readonly_root':'fixture-only'}
    finally:
        # Only invocation-owned units and its private scratch directory.
        subprocess.run(['systemctl','stop','vpn-console-expiry-'+nonce+'.timer',
                        'vpn-console-expiry-'+nonce+'.service'], capture_output=True, timeout=15)
        subprocess.run(['systemctl','stop',anchor], capture_output=True, timeout=15, check=True)
        shutil.rmtree(root)
