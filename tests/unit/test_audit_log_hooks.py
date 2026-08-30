import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "scripts" / "audit-log.sh"


def run_audit(tmp_path: Path, *args: str, extra_env: dict[str, str] | None = None):
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "AUDIT_LOG_FILE": str(tmp_path / "audit.log.age"),
            "AGE_KEY": str(tmp_path / "age.key"),
            "AUDIT_ACTOR": "tester@host",
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [str(AUDIT_LOG), *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_append_best_effort_skips_without_local_key(tmp_path: Path):
    result = run_audit(
        tmp_path,
        "append-best-effort",
        "--action",
        "new-client",
        "--client",
        "phone",
    )

    assert result.returncode == 0
    assert not (tmp_path / "audit.log.age").exists()


def test_append_best_effort_writes_json_record(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_age = fake_bin / "age"
    fake_age.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '-----BEGIN AGE ENCRYPTED FILE-----'\n"
        "cat\n"
        "printf '%s\\n' '-----END AGE ENCRYPTED FILE-----'\n"
    )
    fake_age.chmod(0o755)
    (tmp_path / "age.key").write_text("# public key: age1testrecipient\nAGE-SECRET-KEY-test\n")

    result = run_audit(
        tmp_path,
        "append-best-effort",
        "--action",
        "issue-sub-token",
        "--client",
        "phone",
        "--env",
        "staging",
        "--provider",
        "hetzner",
        "--note",
        'quote " survives',
        extra_env={"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    log_lines = (tmp_path / "audit.log.age").read_text().splitlines()
    records = [json.loads(line) for line in log_lines if line.startswith("{")]
    assert records == [
        {
            "action": "issue-sub-token",
            "actor": "tester@host",
            "client": "phone",
            "env": "staging",
            "iso": records[0]["iso"],
            "note": 'quote " survives',
            "provider": "hetzner",
            "ts": records[0]["ts"],
        }
    ]


def test_lifecycle_hooks_call_best_effort_append():
    expected = {
        "scripts/issue-bootstrap.sh": "--action issue-bootstrap",
        "scripts/issue-sub-token.sh": "--action issue-sub-token",
        "scripts/new-client.sh": "--action new-client",
        "scripts/rotate-secrets.sh": "--action rotate-secrets",
        "scripts/fleet-rotate.sh": "--action fleet-rotate-step",
        "scripts/destroy.sh": "--action staging-destroy",
        "Makefile": "--action rotate-credentials",
    }

    for relpath, action in expected.items():
        text = (REPO_ROOT / relpath).read_text()
        assert "append-best-effort" in text
        assert action in text

    controller = (REPO_ROOT / "scripts/deploy-controller.py").read_text()
    assert '"--action", "site-deploy"' in controller
    assert '"append-best-effort"' in controller
    assert "warp_outbound_role=conditional" in controller
