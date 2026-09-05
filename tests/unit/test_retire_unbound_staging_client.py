"""Recovery retirement for an issued staging client; fixture data is synthetic."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/retire-unbound-staging-client.py"


_MODULE = None


def _load():
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    spec = importlib.util.spec_from_file_location("retire_unbound", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULE = module
    return _MODULE


def _private(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class SopsRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, *, timeout=30, input_bytes=b"", environment=None):
        command = tuple(argv)
        self.calls.append(command)
        assert timeout <= 30
        if command[:4] == ("sops", "--decrypt", "--output-type", "yaml"):
            return Path(command[4]).read_bytes()
        if command[:3] == ("sops", "unset", "--idempotent"):
            target = Path(command[3])
            document = yaml.safe_load(target.read_bytes())
            tokens = []
            for name, index in re.findall(r'\["([^"\\]+)"\]|\[(\d+)\]', command[4]):
                tokens.append(name if name else int(index))
            parent = document
            for token in tokens[:-1]:
                parent = parent[token]
            token = tokens[-1]
            if isinstance(parent, list):
                parent.pop(token)
            else:
                parent.pop(token, None)
            target.write_bytes(yaml.safe_dump(document, sort_keys=True).encode())
            target.chmod(0o600)
            return b""
        raise AssertionError(command)


@pytest.fixture
def setup(tmp_path: Path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    server_uuid = "00112233-4455-4677-8899-aabbccddeeff"
    storage_uuid = "ffeeddcc-bbaa-4988-8766-554433221100"
    hostname = "vpn-ci-staging-fixture"
    environment = "ci-staging-fixture"
    state = _private(
        root / "terraform.tfstate",
        _canonical(
            {
                "version": 4,
                "terraform_version": "1.14.5",
                "serial": 4,
                "lineage": "12345678-1234-4234-8234-123456789abc",
                "outputs": {},
                "resources": [],
            }
        ),
    )
    manifest = {
        "schema_version": 2,
        "provider": "upcloud",
        "environment": environment,
        "workspace": environment,
        "state": {
            "path": str(state),
            "sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        },
        "hostname": hostname,
        "provider_account_username": "staging-owner",
        "server_uuid": server_uuid,
        "root_storage_uuid": storage_uuid,
        "created_at": "2026-09-04T07:58:43Z",
        "target_at": "2026-09-05T19:58:43Z",
        "escalation_at": "2026-09-06T03:58:43Z",
        "expiry_at": "2026-09-06T06:58:43Z",
    }
    manifest_path = _private(root / "cleanup.json", _canonical(manifest))
    absence = {
        "schema_version": 2,
        "status": "verified",
        "deadline_status": "within_deadline",
        "provider": "upcloud",
        "environment": environment,
        "provider_account_username": "staging-owner",
        "manifest_sha256": hashlib.sha256(_canonical(manifest)).hexdigest(),
        "apply_started_at": "2026-09-05T20:04:00Z",
        "expiry_at": manifest["expiry_at"],
        "observed_at": "2026-09-05T20:12:00Z",
        "server_uuid": server_uuid,
        "root_storage_uuid": storage_uuid,
        "server_status": "absent",
        "root_storage_status": "absent",
        "billing_status": "no-active-owned-resources",
    }
    absence_path = _private(root / "post-destroy.json", _canonical(absence))

    # Reuse the canonical schema-shaped liveness fixture and strip its epoch.
    fixture_spec = importlib.util.spec_from_file_location(
        "promotion_fixture", ROOT / "tests/unit/test_sshd_promotion_proof.py"
    )
    assert fixture_spec and fixture_spec.loader
    fixture = importlib.util.module_from_spec(fixture_spec)
    fixture_spec.loader.exec_module(fixture)
    promotion = json.loads(fixture._config(root).read_text())
    liveness = yaml.safe_load(Path(promotion["liveness_config"]).read_bytes())
    target = {
        "inventory_alias": hostname,
        "public_service_address_sha256": "b" * 64,
        "deployable_digest": "c" * 64,
    }
    liveness["sentinels"][0]["target"] = dict(target)
    liveness["sentinels"][0]["awg_target"] = {
        "provider": "upcloud",
        "environment": environment,
        "instance": "vpn_awg",
    }
    outputs = {
        key: str(root / f"output-{key}.json")
        for key in (
            "liveness_config",
            "registry",
            "binding",
            "promotion_config",
            "authority",
            "executor_manifest",
        )
    }
    client = "staging-client"
    sops_file = root / "staging.secrets.sops.yaml"
    intent = {
        "schema_version": 1,
        "kind": "disposable-staging-intent",
        "target_identity": target,
        "host": f"upcloud:{environment}",
        "cohort": "device-full-staging",
        "client": client,
        "liveness": liveness,
        "inputs": {
            "sops_file": str(sops_file),
            "age_key_file": str(root / "age-key"),
            "awg_key_file": str(root / "awg-key"),
            "executor_manifest": str(root / "executor-input.json"),
            "cleanup_manifest": str(manifest_path),
        },
        "outputs": outputs,
    }
    intent_path = _private(root / "intent.json", _canonical(intent))
    secrets = {
        "xray": {
            "clients": [{"name": client, "uuid": "private-xray"}],
            "cohorts": [
                {
                    "name": "staging-vision",
                    "port": 443,
                    "flow_mode": "vision",
                    "clients": [client],
                },
                {
                    "name": "staging-mux",
                    "port": 8443,
                    "flow_mode": "mux",
                    "clients": [client],
                },
            ],
        },
        "hysteria": {"clients": [{"name": client, "password": "private-hy"}]},
        "amneziawg_secrets": {
            "peers": [{"name": client, "preshared_key": "private-awg"}]
        },
        "snell_secrets": {
            "variants": [
                {"id": "one", "users": [{"name": client, "userkey": "private-1"}]},
                {"id": "two", "users": [{"name": client, "userkey": "private-2"}]},
            ]
        },
        "client_registry": {
            client: {
                "status": "issued",
                "issued_at": "2026-09-04T08:00:00Z",
                "formats": [],
                "hosts": [f"upcloud:{environment}"],
                "cohorts": [],
                "token_hash_prefix": "",
                "token_expires": "",
                "awg_public_key_fingerprint": "sha256:0123456789abcdef",
                "awg_private_key": "private-client-key",
                "last_payload_identity": {"source": "", "outputs": ""},
            }
        },
        "unrelated": {"value": "preserve"},
    }
    _private(sops_file, yaml.safe_dump(secrets, sort_keys=True).encode())
    paths = {
        "intent_path": intent_path,
        "cleanup_manifest_path": manifest_path,
        "absence_evidence_path": absence_path,
        "state_path": state,
        "sops_file": sops_file,
        "journal_path": root / "retirement.journal.json",
        "receipt_path": root / "retirement.receipt.json",
    }
    return {
        "root": root,
        "paths": paths,
        "intent": intent,
        "manifest": manifest,
        "absence": absence,
        "secrets": secrets,
        "runner": SopsRunner(),
        "client": client,
    }


def _run(setup, **kwargs):
    values = dict(setup["paths"])
    values.update(runner=setup["runner"])
    values.update(kwargs)
    return _load().retire(**values)


def test_retirement_removes_exact_issued_client_and_is_idempotent(setup):
    before = setup["paths"]["sops_file"].read_bytes()
    result = _run(setup)
    assert result["status"] == "retired"
    assert result["changed"] is True
    assert result["ciphertext_before_sha256"] == hashlib.sha256(before).hexdigest()
    final = yaml.safe_load(setup["paths"]["sops_file"].read_bytes())
    assert final["unrelated"] == {"value": "preserve"}
    assert final["xray"]["clients"] == []
    assert all(cohort["clients"] == [] for cohort in final["xray"]["cohorts"])
    assert final["hysteria"]["clients"] == []
    assert final["amneziawg_secrets"]["peers"] == []
    assert all(variant["users"] == [] for variant in final["snell_secrets"]["variants"])
    assert final["client_registry"] == {}
    assert stat.S_IMODE(setup["paths"]["journal_path"].stat().st_mode) == 0o600
    assert stat.S_IMODE(setup["paths"]["receipt_path"].stat().st_mode) == 0o600
    calls = len(setup["runner"].calls)
    second = _run(setup)
    assert second == {**result, "changed": False}
    assert len(setup["runner"].calls) == calls + 1  # semantic final reread only


def test_retirement_round_trips_real_sops_ciphertext(setup, monkeypatch):
    roundtrip_spec = importlib.util.spec_from_file_location(
        "retirement_sops_roundtrip", ROOT / "tests/unit/test_sops_roundtrip.py"
    )
    assert roundtrip_spec and roundtrip_spec.loader
    roundtrip = importlib.util.module_from_spec(roundtrip_spec)
    roundtrip_spec.loader.exec_module(roundtrip)
    roundtrip._require_binaries()

    plain = _private(
        setup["root"] / "synthetic-plaintext.yaml",
        yaml.safe_dump(setup["secrets"], sort_keys=True).encode(),
    )
    encrypted = setup["root"] / "synthetic.sops.yaml"
    roundtrip._sops_encrypt(
        plain,
        encrypted,
        roundtrip.AGE_KEY,
        roundtrip._age_recipient(roundtrip.AGE_KEY),
    )
    setup["paths"]["sops_file"].write_bytes(encrypted.read_bytes())
    setup["paths"]["sops_file"].chmod(0o600)
    monkeypatch.setenv("SOPS_AGE_KEY_FILE", str(roundtrip.AGE_KEY))

    values = dict(setup["paths"])
    values["runner"] = _load()._run_command
    assert _load().retire(**values)["changed"] is True
    final = roundtrip._sops_decrypt(setup["paths"]["sops_file"], roundtrip.AGE_KEY)
    assert final["xray"]["clients"] == []
    assert final["hysteria"]["clients"] == []
    assert final["amneziawg_secrets"]["peers"] == []
    assert all(variant["users"] == [] for variant in final["snell_secrets"]["variants"])
    assert final["client_registry"] == {}
    assert b"private-" not in setup["paths"]["sops_file"].read_bytes()


@pytest.mark.parametrize(
    "case",
    [
        "duplicate-root-xray",
        "duplicate-xray-clients",
        "duplicate-client",
        "duplicate-snell-users",
    ],
)
def test_retirement_refuses_duplicate_yaml_keys_without_rewrite(setup, case):
    payload = yaml.safe_dump(setup["secrets"], sort_keys=True)
    if case == "duplicate-root-xray":
        payload = "xray: {}\n" + payload
    elif case == "duplicate-xray-clients":
        payload = payload.replace(
            "xray:\n  clients:", "xray:\n  clients: []\n  clients:", 1
        )
    elif case == "duplicate-client":
        payload = payload.replace(
            "client_registry:\n  staging-client:",
            "client_registry:\n  staging-client: {}\n  staging-client:",
            1,
        )
    else:
        payload = payload.replace("    users:\n", "    users: []\n    users:\n", 1)
    setup["paths"]["sops_file"].write_text(payload)
    setup["paths"]["sops_file"].chmod(0o600)
    before = setup["paths"]["sops_file"].read_bytes()

    with pytest.raises(_load().RetirementError, match="retirement-secrets"):
        _run(setup)

    assert setup["paths"]["sops_file"].read_bytes() == before
    assert not setup["paths"]["journal_path"].exists()
    assert not setup["paths"]["receipt_path"].exists()
    assert not list(setup["paths"]["sops_file"].parent.glob("*.retire-*.sops.yaml"))


@pytest.mark.parametrize(
    "status", ["delivered", "active", "stale", "revoked", "burned"]
)
def test_retirement_refuses_nonissued_registry_without_mutation(setup, status):
    document = copy.deepcopy(setup["secrets"])
    document["client_registry"][setup["client"]]["status"] = status
    setup["paths"]["sops_file"].write_text(yaml.safe_dump(document))
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(_load().RetirementError, match="retirement-secrets"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before
    assert not setup["paths"]["journal_path"].exists()


@pytest.mark.parametrize(
    "case",
    [
        "xray-missing",
        "hysteria-duplicate",
        "awg-missing",
        "snell-missing",
        "snell-duplicate",
        "registry-host",
    ],
)
def test_retirement_refuses_partial_duplicate_or_foreign_client_state(setup, case):
    document = copy.deepcopy(setup["secrets"])
    client = setup["client"]
    if case == "xray-missing":
        document["xray"]["clients"] = []
    elif case == "hysteria-duplicate":
        document["hysteria"]["clients"].append({"name": client})
    elif case == "awg-missing":
        document["amneziawg_secrets"]["peers"] = []
    elif case == "snell-missing":
        document["snell_secrets"]["variants"][0]["users"] = []
    elif case == "snell-duplicate":
        document["snell_secrets"]["variants"][0]["users"].append({"name": client})
    else:
        document["client_registry"][client]["hosts"] = ["upcloud:prod"]
    setup["paths"]["sops_file"].write_text(yaml.safe_dump(document))
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(_load().RetirementError, match="retirement-secrets"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


@pytest.mark.parametrize("case", ["duplicate-reference", "unknown-reference"])
def test_retirement_refuses_invalid_xray_cohort_references_without_mutation(
    setup, case
):
    document = copy.deepcopy(setup["secrets"])
    references = document["xray"]["cohorts"][0]["clients"]
    if case == "duplicate-reference":
        references.append(setup["client"])
    else:
        references.append("unknown-client")
    setup["paths"]["sops_file"].write_text(yaml.safe_dump(document))
    before = setup["paths"]["sops_file"].read_bytes()

    with pytest.raises(_load().RetirementError, match="retirement-secrets"):
        _run(setup)

    assert setup["paths"]["sops_file"].read_bytes() == before
    assert not setup["paths"]["journal_path"].exists()


@pytest.mark.parametrize(
    "artifact",
    [
        "binding",
        "promotion_config",
        "registry",
        "liveness_config",
        "authority",
        "executor_manifest",
        "pending",
    ],
)
def test_retirement_refuses_any_onboarding_output(setup, artifact):
    if artifact == "pending":
        path = Path(setup["intent"]["outputs"]["registry"] + ".pending.json")
    else:
        path = Path(setup["intent"]["outputs"][artifact])
    _private(path, b"foreign\n")
    with pytest.raises(_load().RetirementError, match="retirement-bound"):
        _run(setup)


@pytest.mark.parametrize(
    "case",
    [
        "manifest-digest",
        "provider",
        "environment",
        "hostname",
        "server",
        "storage",
        "state-path",
        "state-digest",
        "state-version",
        "state-nonempty",
    ],
)
def test_retirement_refuses_target_or_state_mismatch(setup, case):
    if case == "manifest-digest":
        setup["absence"]["manifest_sha256"] = "d" * 64
        setup["paths"]["absence_evidence_path"].write_bytes(
            _canonical(setup["absence"])
        )
    elif case in {"provider", "environment", "server", "storage"}:
        key = {
            "provider": "provider",
            "environment": "environment",
            "server": "server_uuid",
            "storage": "root_storage_uuid",
        }[case]
        setup["absence"][key] = (
            "vultr"
            if case == "provider"
            else (
                "ci-staging-other"
                if case == "environment"
                else "11112233-4455-4677-8899-aabbccddeeff"
            )
        )
        setup["paths"]["absence_evidence_path"].write_bytes(
            _canonical(setup["absence"])
        )
    elif case == "hostname":
        setup["intent"]["target_identity"]["inventory_alias"] = "other-host"
        setup["intent"]["liveness"]["sentinels"][0]["target"][
            "inventory_alias"
        ] = "other-host"
        setup["paths"]["intent_path"].write_bytes(_canonical(setup["intent"]))
    elif case == "state-path":
        other = _private(
            setup["root"] / "other.tfstate", setup["paths"]["state_path"].read_bytes()
        )
        setup["paths"]["state_path"] = other
    elif case == "state-digest":
        setup["manifest"]["state"]["sha256"] = "d" * 64
        setup["paths"]["cleanup_manifest_path"].write_bytes(
            _canonical(setup["manifest"])
        )
        setup["absence"]["manifest_sha256"] = hashlib.sha256(
            _canonical(setup["manifest"])
        ).hexdigest()
        setup["paths"]["absence_evidence_path"].write_bytes(
            _canonical(setup["absence"])
        )
    elif case == "state-version":
        setup["paths"]["state_path"].write_bytes(
            _canonical({"version": 3, "outputs": {}, "resources": []})
        )
    else:
        setup["paths"]["state_path"].write_bytes(
            _canonical({"version": 4, "resources": [{"mode": "managed"}]})
        )
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(
        _load().RetirementError, match="retirement-(target|state|intent|absence)"
    ):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


@pytest.mark.parametrize(
    ("status", "deadline", "applied", "observed"),
    [
        (
            "verified_after_expiry",
            "expired_after_apply",
            "2026-09-06T07:00:00Z",
            "2026-09-06T07:01:00Z",
        ),
        ("verified", "within_deadline", "2026-09-05T20:04:00Z", "2026-09-06T07:01:00Z"),
        (
            "verified_after_expiry",
            "within_deadline",
            "2026-09-05T20:04:00Z",
            "2026-09-06T07:01:00Z",
        ),
        ("verified", "within_deadline", "2026-09-05T20:04:00Z", "2026-09-05T19:00:00Z"),
    ],
)
def test_retirement_refuses_noncanonical_absence_timeline(
    setup, status, deadline, applied, observed
):
    setup["absence"].update(
        status=status,
        deadline_status=deadline,
        apply_started_at=applied,
        observed_at=observed,
    )
    setup["paths"]["absence_evidence_path"].write_bytes(_canonical(setup["absence"]))
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(_load().RetirementError, match="retirement-absence"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


@pytest.mark.parametrize(
    "name",
    [
        "intent_path",
        "cleanup_manifest_path",
        "absence_evidence_path",
        "state_path",
        "sops_file",
    ],
)
def test_retirement_refuses_unsafe_private_inputs(setup, name):
    path = setup["paths"][name]
    if name == "intent_path":
        path.chmod(0o644)
    else:
        payload = path.read_bytes()
        path.unlink()
        path.symlink_to(_private(setup["root"] / f"foreign-{name}", payload))
    with pytest.raises(_load().RetirementError, match="retirement-input"):
        _run(setup)


def test_retirement_refuses_oversize_input_without_decrypt(setup):
    setup["paths"]["intent_path"].write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(_load().RetirementError, match="retirement-input"):
        _run(setup)
    assert setup["runner"].calls == []


def test_retirement_categorizes_short_journal_write_and_removes_owned_partial(
    setup, monkeypatch
):
    module = _load()
    original = module.os.write
    failed = False

    def fail_first_write(fd, payload):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError("fixture write failure")
        return original(fd, payload)

    monkeypatch.setattr(module.os, "write", fail_first_write)
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(module.RetirementError, match="retirement-journal"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before
    assert not setup["paths"]["journal_path"].exists()


@pytest.mark.parametrize("lock_index", [0, 1])
def test_retirement_lock_is_project_and_client_exclusive(setup, lock_index):
    module = _load()
    lock = module.lock_paths(setup["paths"]["sops_file"], setup["client"])[lock_index]
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    os.fchmod(fd, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(module.RetirementError, match="retirement-busy"):
            _run(setup)
    finally:
        os.close(fd)


def test_retirement_refuses_a_concurrent_process_holding_project_lock(setup):
    module = _load()
    project, _client = module.lock_paths(setup["paths"]["sops_file"], setup["client"])
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, os, sys; "
                "fd=os.open(sys.argv[1], os.O_CREAT|os.O_RDWR, 0o600); "
                "os.fchmod(fd, 0o600); fcntl.flock(fd, fcntl.LOCK_EX); "
                "print('ready', flush=True); sys.stdin.buffer.read(1)"
            ),
            str(project),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline() == "ready\n"
        with pytest.raises(module.RetirementError, match="retirement-busy"):
            _run(setup)
    finally:
        assert holder.stdin is not None
        holder.stdin.close()
        assert holder.wait(timeout=5) == 0


def test_retirement_interlocks_the_canonical_sops_writer_lock(setup):
    module = _load()
    canonical = Path(str(setup["paths"]["sops_file"]) + ".new-client.lock")
    project, _client = module.lock_paths(setup["paths"]["sops_file"], setup["client"])
    assert project == canonical
    assert (
        'SOPS_LOCK="${SOPS_FILE}.new-client.lock"'
        in (ROOT / "scripts/new-client.sh").read_text()
    )
    assert (
        'REGISTRY_LOCK="${sops_file}.new-client.lock"'
        in (ROOT / "scripts/issue-sub-token.sh").read_text()
    )
    assert (
        'sops_file.with_name(sops_file.name + ".new-client.lock")'
        in (ROOT / "scripts/disposable_liveness_executor.py").read_text()
    )

    before = setup["paths"]["sops_file"].read_bytes()
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, os, sys; "
                "fd=os.open(sys.argv[1], os.O_CREAT|os.O_RDWR, 0o600); "
                "os.fchmod(fd, 0o600); fcntl.flock(fd, fcntl.LOCK_EX); "
                "print('ready', flush=True); sys.stdin.buffer.read(1)"
            ),
            str(canonical),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline() == "ready\n"
        with pytest.raises(module.RetirementError, match="retirement-busy"):
            _run(setup)
    finally:
        assert holder.stdin is not None
        holder.stdin.close()
        assert holder.wait(timeout=5) == 0
    assert setup["paths"]["sops_file"].read_bytes() == before
    assert setup["runner"].calls == []


def test_new_client_controller_cannot_cross_an_active_retirement(setup):
    module = _load()
    before = setup["paths"]["sops_file"].read_bytes()
    environment = {
        "HOME": str(setup["root"]),
        "PATH": os.environ["PATH"],
        "SOPS_FILE": str(setup["paths"]["sops_file"]),
    }

    with module._locks(module.lock_paths(setup["paths"]["sops_file"], setup["client"])):
        result = subprocess.run(
            [str(ROOT / "scripts/new-client.sh"), "concurrent-client"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    assert result.returncode != 0
    assert "another new-client transaction is active" in result.stderr
    assert setup["paths"]["sops_file"].read_bytes() == before
    assert setup["runner"].calls == []


def test_retirement_detects_ciphertext_replacement_before_publish(setup):
    replacement = b"foreign encrypted bytes\n"

    def replace():
        setup["paths"]["sops_file"].write_bytes(replacement)
        setup["paths"]["sops_file"].chmod(0o600)

    with pytest.raises(_load().RetirementError, match="retirement-ciphertext"):
        _run(
            setup,
            failpoint=lambda phase: replace() if phase == "before-publish" else None,
        )
    assert setup["paths"]["sops_file"].read_bytes() == replacement


def test_retirement_detects_candidate_replacement_before_publish(setup):
    before = setup["paths"]["sops_file"].read_bytes()

    def replace_candidate(phase):
        if phase != "after-candidate":
            return
        candidates = list(setup["root"].glob(".staging.secrets.sops.yaml.retire-*"))
        assert len(candidates) == 1
        candidates[0].write_bytes(b"foreign candidate\n")
        candidates[0].chmod(0o600)

    class Crash(BaseException):
        pass

    with pytest.raises(Crash):
        _run(
            setup,
            failpoint=lambda phase: (
                (
                    replace_candidate(phase),
                    (_ for _ in ()).throw(Crash()),
                )
                if phase == "after-candidate"
                else None
            ),
        )
    with pytest.raises(_load().RetirementError, match="retirement-candidate"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


def test_retirement_refuses_unbound_candidate_namespace(setup):
    candidate = setup["paths"]["sops_file"].with_name(
        f".{setup['paths']['sops_file'].name}.retire-{'a' * 32}.yaml"
    )
    _private(candidate, b"partial candidate\n")
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(_load().RetirementError, match="retirement-candidate"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


def test_retirement_refuses_candidate_left_before_journal_transition(
    setup, monkeypatch
):
    module = _load()
    original = module._replace_document

    class Crash(BaseException):
        pass

    def interrupt(path, expected, value, category):
        if (
            path == setup["paths"]["journal_path"]
            and expected["state"] == "prepared"
            and value["state"] == "candidate"
        ):
            raise Crash
        return original(path, expected, value, category)

    monkeypatch.setattr(module, "_replace_document", interrupt)
    with pytest.raises(Crash):
        _run(setup)
    monkeypatch.setattr(module, "_replace_document", original)
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(module.RetirementError, match="retirement-candidate"):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


def test_retirement_refuses_orphan_journal_replace_file(setup):
    partial = setup["paths"]["journal_path"].with_name(
        f".{setup['paths']['journal_path'].name}.replace-{'a' * 32}"
    )
    _private(partial, b"partial journal replacement\n")
    before = setup["paths"]["sops_file"].read_bytes()

    with pytest.raises(_load().RetirementError, match="retirement-journal"):
        _run(setup)

    assert setup["paths"]["sops_file"].read_bytes() == before
    assert partial.read_bytes() == b"partial journal replacement\n"


@pytest.mark.parametrize(
    "phase", ["after-prepared", "after-candidate", "after-publish", "after-receipt"]
)
def test_retirement_recovers_every_durable_boundary(setup, phase):
    class Crash(BaseException):
        pass

    with pytest.raises(Crash):
        _run(
            setup,
            failpoint=lambda observed: (
                (_ for _ in ()).throw(Crash()) if observed == phase else None
            ),
        )
    result = _run(setup)
    assert result["status"] == "retired"
    assert result["changed"] is True
    assert _run(setup)["changed"] is False


def test_retirement_journal_advances_monotonically(setup, monkeypatch):
    module = _load()
    transitions = []
    original = module._replace_document

    def observe(path, expected, value, category):
        if path == setup["paths"]["journal_path"]:
            transitions.append((expected["state"], value["state"]))
        return original(path, expected, value, category)

    monkeypatch.setattr(module, "_replace_document", observe)
    assert _run(setup)["changed"] is True
    assert transitions == [
        ("prepared", "candidate"),
        ("candidate", "published"),
        ("published", "verified"),
    ]


@pytest.mark.parametrize(
    "kind", ["partial", "foreign-request", "foreign-ciphertext", "foreign-receipt"]
)
def test_retirement_recovery_refuses_partial_or_foreign_state(setup, kind):
    module = _load()
    if kind == "partial":
        _private(setup["paths"]["journal_path"], b'{"schema_version":1')
    else:
        request = module._request(setup["paths"])
        if kind == "foreign-request":
            request["intent_sha256"] = "f" * 64
        journal = module._journal("prepared", request)
        _private(setup["paths"]["journal_path"], _canonical(journal))
        if kind == "foreign-ciphertext":
            setup["paths"]["sops_file"].write_text("foreign\n")
        elif kind == "foreign-receipt":
            _private(
                setup["paths"]["receipt_path"],
                _canonical(
                    {
                        "schema_version": 1,
                        "status": "retired",
                        "request_sha256": "f" * 64,
                    }
                ),
            )
    before = setup["paths"]["sops_file"].read_bytes()
    with pytest.raises(
        module.RetirementError, match="retirement-(journal|ciphertext|receipt)"
    ):
        _run(setup)
    assert setup["paths"]["sops_file"].read_bytes() == before


@pytest.mark.parametrize("artifact", ["journal_path", "receipt_path"])
def test_retirement_refuses_unsafe_recovery_artifact(setup, artifact):
    if artifact == "journal_path":

        class Crash(BaseException):
            pass

        with pytest.raises(Crash):
            _run(
                setup,
                failpoint=lambda phase: (
                    (_ for _ in ()).throw(Crash())
                    if phase == "after-prepared"
                    else None
                ),
            )
    else:
        _run(setup)
    path = setup["paths"][artifact]
    payload = path.read_bytes()
    path.unlink()
    path.symlink_to(_private(setup["root"] / f"foreign-{artifact}", payload))
    with pytest.raises(_load().RetirementError, match="retirement-(journal|receipt)"):
        _run(setup)


def test_retirement_propagates_canonical_owner_refusal(setup, monkeypatch):
    module = _load()
    guard = module._guard()

    class RejectForeignOwner:
        def __getattr__(self, name):
            return getattr(guard, name)

        def _private_snapshot(self, *args, **kwargs):
            raise guard.GuardError("foreign owner")

    monkeypatch.setattr(module, "_guard", lambda: RejectForeignOwner())
    with pytest.raises(module.RetirementError, match="retirement-input"):
        _run(setup)
    assert setup["runner"].calls == []


def test_cli_and_make_never_emit_secret_values(setup, monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(module, "_run_command", setup["runner"])
    argv = [
        "retire-unbound-staging-client.py",
        "--intent",
        str(setup["paths"]["intent_path"]),
        "--cleanup-manifest",
        str(setup["paths"]["cleanup_manifest_path"]),
        "--absence-evidence",
        str(setup["paths"]["absence_evidence_path"]),
        "--state",
        str(setup["paths"]["state_path"]),
        "--sops-file",
        str(setup["paths"]["sops_file"]),
        "--journal",
        str(setup["paths"]["journal_path"]),
        "--receipt",
        str(setup["paths"]["receipt_path"]),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0
    output = capsys.readouterr()
    assert "private-" not in output.out + output.err
    assert json.loads(output.out) == {
        "changed": True,
        "schema_version": 1,
        "status": "retired",
    }


def test_cli_redacts_unexpected_dependency_failure(setup, monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(
        module,
        "retire",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("private-secret")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "retire-unbound-staging-client.py",
            "--intent",
            str(setup["paths"]["intent_path"]),
            "--cleanup-manifest",
            str(setup["paths"]["cleanup_manifest_path"]),
            "--absence-evidence",
            str(setup["paths"]["absence_evidence_path"]),
            "--state",
            str(setup["paths"]["state_path"]),
            "--sops-file",
            str(setup["paths"]["sops_file"]),
            "--journal",
            str(setup["paths"]["journal_path"]),
            "--receipt",
            str(setup["paths"]["receipt_path"]),
        ],
    )
    assert module.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "retire-unbound-staging-client: retirement-internal\n"


def _make_args(intent: str = "/private/i") -> list[str]:
    return [
        "make",
        "-n",
        "retire-unbound-staging-client",
        f"UNBOUND_STAGING_INTENT={intent}",
        "STAGING_CLEANUP_MANIFEST=/private/a",
        "STAGING_POST_DESTROY_EVIDENCE=/private/b",
        "STAGING_CLEANUP_STATE=/private/c",
        "SOPS_FILE=/private/d",
        "UNBOUND_CLIENT_JOURNAL=/private/e",
        "UNBOUND_CLIENT_RECEIPT=/private/f",
    ]


@pytest.mark.parametrize(
    "field",
    [
        "UNBOUND_STAGING_INTENT",
        "STAGING_CLEANUP_MANIFEST",
        "STAGING_POST_DESTROY_EVIDENCE",
        "STAGING_CLEANUP_STATE",
        "SOPS_FILE",
        "UNBOUND_CLIENT_JOURNAL",
        "UNBOUND_CLIENT_RECEIPT",
    ],
)
def test_make_boundary_keeps_every_operator_path_literal(tmp_path: Path, field: str):
    marker = tmp_path / "expanded"
    args = _make_args()
    args = [
        f"{field}=$(shell touch {marker})" if item.startswith(f"{field}=") else item
        for item in args
    ]
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "literal values" in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize(
    "credential",
    [
        "SOPS_AGE_KEY_FILE",
        "SOPS_AGE_KEY_CMD",
        "UPCLOUD_USERNAME",
        "UPCLOUD_PASSWORD",
        "UPCLOUD_API_USERNAME",
        "UPCLOUD_API_PASSWORD",
        "UPCLOUD_TOKEN",
        "TAILSCALE_AUTH_KEY",
    ],
)
def test_make_boundary_rejects_command_line_credentials(
    tmp_path: Path, credential: str
):
    marker = tmp_path / "expanded"
    result = subprocess.run(
        [*_make_args(), f"{credential}=$(shell touch {marker})"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "credentials must come from the environment" in result.stderr
    assert not marker.exists()


def test_make_boundary_rejects_multiple_goals():
    result = subprocess.run(
        [*_make_args(), "help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "requires exactly one Make goal" in result.stderr


def test_make_target_forwards_only_documented_literal_paths(tmp_path: Path):
    binary = tmp_path / "bin"
    binary.mkdir()
    build_gate = binary / "build-gate"
    build_gate.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    build_gate.chmod(0o700)
    argv = _make_args()
    argv.remove("-n")
    result = subprocess.run(
        argv,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PATH": f"{binary}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "--",
        "python3",
        "./scripts/retire-unbound-staging-client.py",
        "--intent",
        "/private/i",
        "--cleanup-manifest",
        "/private/a",
        "--absence-evidence",
        "/private/b",
        "--state",
        "/private/c",
        "--sops-file",
        "/private/d",
        "--journal",
        "/private/e",
        "--receipt",
        "/private/f",
    ]


def test_make_target_rejects_unknown_command_variable_before_recipe():
    result = subprocess.run(
        [*_make_args(), "CLIENT=foreign"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "only its documented command-line fields" in result.stderr
