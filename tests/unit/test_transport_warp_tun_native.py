"""Actual TCP/UDP TUN frames and final underlay isolation, separate from vendor acceptance."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
pytestmark=pytest.mark.native_runtime


def test_two_native_tuns_authenticated_gateway_and_no_underlay_fallback():
    assert sys.platform=='linux' and os.geteuid()==0
    assert os.environ.get('TRANSPORT_NATIVE_ISOLATED')=='1', 'owned disconnected native runner required'
    source=ROOT/'tests/integration/transport_warp_tun/fixture.py'
    # Private mount namespace ensures the canonical adapter name cannot collide.
    runner='import os,subprocess,sys;subprocess.run(["mount","-t","tmpfs","tmpfs","/run/netns"],check=True);os.execv(sys.executable,[sys.executable,sys.argv[1],sys.argv[2]])'
    result=subprocess.run(['unshare','--net','--mount','--propagation','private',sys.executable,'-c',runner,str(source),str(ROOT)],text=True,capture_output=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    receipt=json.loads(result.stdout.splitlines()[-1])
    assert receipt['underlay_recipient_frames']==0
    assert receipt['registered_vendor_acceptance'] is False
    assert all(value is True for key,value in receipt.items() if key not in {'underlay_recipient_frames','registered_vendor_acceptance'})
