"""Day-1 bootstrap must not generate unrecoverable AWG client keys."""

from pathlib import Path


def _bootstrap_awg_instance(tmp_path, name):
    """Run the real bootstrap; only key tools and encryption are stubbed."""
    import os
    import subprocess
    import sys

    import yaml

    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    for tool, body in {
        "age": "exit 0",
        "age-keygen": 'printf "# public key: age1stub\\nAGE-SECRET-KEY-STUB\\n" > "$2"',
        "xray": 'printf "Private key: stub-private\\nPublic key: stub-public\\n"',
        "wg": "printf 'AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=\\n'",
        "sops": 'for last in "$@"; do :; done; cat "$last"',
    }.items():
        path = stubs / tool
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)
    config = tmp_path / name
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PATH": f"{stubs}:{Path(sys.executable).parent}:{os.environ['PATH']}",
           "HOME": str(tmp_path), "VPN_PROVISION_CONFIG_DIR": str(config)}
    result = subprocess.run([str(root / "scripts/bootstrap-secrets.sh"), "--target", "mirror.example.test:443",
                             "--server-name", "node.example.test"], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    document = yaml.safe_load((config / "prod.secrets.sops.yaml").read_text())
    (instance,) = document["amneziawg_secrets"]["instances"]
    return instance


def test_bootstrap_writes_a_generated_wire_shape_and_port_per_instance(tmp_path):
    first = _bootstrap_awg_instance(tmp_path, "first")
    second = _bootstrap_awg_instance(tmp_path, "second")
    names = ("listen_port", "jc", "jmin", "jmax", "s1", "s2")
    for instance in (first, second):
        assert instance["peers"] == []
        assert all(type(instance[name]) is int for name in names)
        assert 20000 <= instance["listen_port"] <= 32767
        assert 3 <= instance["jc"] <= 8 and 20 <= instance["jmin"] <= 80
        assert instance["jmin"] + 20 <= instance["jmax"] <= instance["jmin"] + 200
        assert 15 <= instance["s1"] <= 150 and 15 <= instance["s2"] <= 150
        assert 148 + instance["s1"] != 92 + instance["s2"]
        assert [instance[name] for name in names[1:]] != [4, 40, 70, 50, 100]
    assert [first[name] for name in names] != [second[name] for name in names]
