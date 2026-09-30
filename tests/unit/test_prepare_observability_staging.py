"""Private input preparation for disposable observability staging."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prepare-observability-staging.py"
ACCEPTANCE = ROOT / "scripts" / "observability-staging-acceptance.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _private_json(path: Path, value: object) -> Path:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, object]:
    tmp_path.chmod(0o700)
    config = _private_json(
        tmp_path / "config.json",
        {
            "schema_version": 1,
            "hosts": {
                "canary": "canary-a",
                "control-plane": "control-a",
                "deadman": "deadman-a",
            },
            "sender_ids": {
                "canary": "canary-a",
                "deadman-reverse": "deadman-reverse-a",
            },
            "pki": {
                "ingress_sni": "ingest.fixture.test",
                "control_plane_dns_san": "control.fixture.test",
                "deadman_pulse_sni": "pulse.fixture.test",
            },
            "silence_operator": "operator-a",
        },
    )
    telegram = _private_json(
        tmp_path / "telegram.json",
        {
            "schema_version": 1,
            "primary": {
                "bot_token": "123456789:primary-fixture-token",
                "chat_id": "-100000000001",
                "topic_id": 11,
            },
            "secondary": {
                "bot_token": "987654321:secondary-fixture-token",
                "chat_id": "-100000000002",
                "topic_id": 12,
            },
        },
    )
    return {
        "parent": tmp_path,
        "root": tmp_path / "prepared",
        "config": config,
        "telegram": telegram,
    }


def _fixture_pki() -> dict[str, dict[str, str]]:
    certificate = (
        "-----BEGIN CERTIFICATE-----\n" + "A" * 64 + "\n-----END CERTIFICATE-----\n"
    )
    private_key = (
        "-----BEGIN PRIVATE KEY-----\n" + "B" * 64 + "\n-----END PRIVATE KEY-----\n"
    )
    crl = "-----BEGIN X509 CRL-----\n" + "C" * 64 + "\n-----END X509 CRL-----\n"
    return {
        "receiver": {
            "certificate": certificate,
            "private_key": private_key,
            "crl": crl,
        },
        "pulse": {"certificate": certificate, "private_key": private_key, "crl": crl},
        "silence": {"certificate": certificate, "private_key": private_key, "crl": crl},
        "ingress": {"certificate": certificate, "private_key": private_key},
        "canary": {"certificate": certificate, "private_key": private_key},
        "reverse": {"certificate": certificate, "private_key": private_key},
        "pulse_server": {"certificate": certificate, "private_key": private_key},
        "silence_server": {"certificate": certificate, "private_key": private_key},
        "silence_client": {"certificate": certificate, "private_key": private_key},
    }


def _patch_generators(
    monkeypatch: pytest.MonkeyPatch, module, encrypted: list[dict]
) -> None:
    monkeypatch.setattr(module, "_source_identity", lambda: ("a" * 40, "b" * 64))

    def ssh(root: Path) -> None:
        module._write_private(root / "ssh" / "operator_ed25519", b"private-fixture\n")
        module._write_private(
            root / "ssh" / "operator_ed25519.pub", b"public-fixture\n"
        )

    def age(root: Path) -> str:
        module._write_private(
            root / "age" / "identity.txt", b"AGE-SECRET-KEY-fixture\n"
        )
        module._write_private(root / "age" / "recipient.txt", b"age1fixture\n")
        return "age1fixture"

    def pki(config, directory):
        material = _fixture_pki()
        return material, {
            "schema_version": 1,
            "task_id": module.TASK_ID,
            "change": module.CHANGE,
            "receiver": {"ca_private_key_pem": material["receiver"]["private_key"]},
        }

    def encrypt(value, recipient):
        encrypted.append(value)
        return b"sops-ciphertext-fixture\n"

    monkeypatch.setattr(module, "_generate_ssh", ssh)
    monkeypatch.setattr(module, "_generate_age", age)
    monkeypatch.setattr(module, "_generate_pki", pki)
    monkeypatch.setattr(module, "_encrypt_sops", encrypt)


def test_preparer_contract_matches_fixed_acceptance_controller() -> None:
    preparer = _load(SCRIPT, "observability_preparer_contract")
    acceptance = _load(ACCEPTANCE, "observability_acceptance_contract")

    assert preparer.STEPS == acceptance.STEPS
    assert preparer.STEP_TARGETS == acceptance.STEP_TARGETS
    assert preparer.STEP_RESTORES == acceptance.STEP_RESTORES
    assert preparer.OBSERVATION_STEPS == acceptance.OBSERVATION_STEPS
    assert preparer.STEP_DEADLINES == acceptance.STEP_MIN_DEADLINES


def test_makefile_exposes_literal_staging_preparation_surfaces() -> None:
    source = (ROOT / "Makefile").read_text(encoding="utf-8")
    prepare = source[source.index("observability-staging-prepare:\n") :]
    prepare = prepare[: prepare.index("\n\n")]
    materialize = source[source.index("observability-staging-materialize:\n") :]
    materialize = materialize[: materialize.index("\n\n")]

    assert "scripts/prepare-observability-staging.py prepare" in prepare
    assert '"$${OBSERVABILITY_STAGING_ROOT_LITERAL}"' in prepare
    assert '"$${OBSERVABILITY_STAGING_CONFIG_LITERAL}"' in prepare
    assert '"$${OBSERVABILITY_STAGING_TELEGRAM_INPUT_LITERAL}"' in prepare
    assert "scripts/prepare-observability-staging.py materialize" in materialize
    assert '"$${OBSERVABILITY_STAGING_ROOT_LITERAL}"' in materialize


def test_makefile_staging_preparation_rejects_extra_and_cross_verb_fields() -> None:
    prepare = [
        "make",
        "-n",
        "observability-staging-prepare",
        "OBSERVABILITY_STAGING_ROOT=/private/run",
        "OBSERVABILITY_STAGING_CONFIG=/private/config.json",
        "OBSERVABILITY_STAGING_TELEGRAM_INPUT=/private/telegram.json",
    ]
    materialize = [
        "make",
        "-n",
        "observability-staging-materialize",
        "OBSERVABILITY_STAGING_ROOT=/private/run",
    ]
    extra = subprocess.run(
        [*prepare, "ARBITRARY_COMMAND=id"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    cross_verb = subprocess.run(
        [*materialize, "OBSERVABILITY_STAGING_CONFIG=/private/config.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert extra.returncode != 0
    assert "accepts only the required private paths" in extra.stderr
    assert cross_verb.returncode != 0
    assert "accepts only the required private paths" in cross_verb.stderr


def test_source_identity_rejects_dirty_runtime_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(SCRIPT, "observability_preparer_dirty_schema")
    revision = "a" * 40
    digest = "b" * 64

    def run(command, **_kwargs):
        if command[0] == str(ROOT / "scripts" / "deploy-source-identity.sh"):
            return f"{revision} {digest}\n".encode()
        if command[:3] == ["git", "rev-parse", "--verify"]:
            return f"{revision}\n".encode()
        if command[:2] == ["git", "status"]:
            return (
                b" M secrets/schema.json\0" if "secrets/schema.json" in command else b""
            )
        raise AssertionError(f"unexpected command: {command!r}")

    monkeypatch.setattr(module, "_run", run)

    with pytest.raises(
        module.PreparationError, match="clean protected-main source required"
    ):
        module._source_identity()


def test_prepare_creates_private_fail_closed_scaffolding_without_secret_output(
    inputs, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load(SCRIPT, "observability_preparer_prepare")
    encrypted: list[dict] = []
    _patch_generators(monkeypatch, module, encrypted)

    module.prepare(inputs["root"], inputs["config"], inputs["telegram"])

    assert stat.S_IMODE(inputs["root"].stat().st_mode) == 0o700
    files = [path for path in inputs["root"].rglob("*") if path.is_file()]
    assert files
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)
    assert (
        inputs["root"] / "secrets" / "observability-secrets.sops.yaml"
    ).read_bytes() == b"sops-ciphertext-fixture\n"
    manifest_path = inputs["root"] / "acceptance" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_revision"] == "a" * 40
    assert manifest["hosts"] == {
        "canary": "canary-a",
        "control-plane": "control-a",
        "deadman": "deadman-a",
    }
    assert set(manifest["approvals"]) == set(module.STEPS)
    acceptance = _load(ACCEPTANCE, "observability_acceptance_manifest_inputs")
    assert set(manifest["inputs"]) == acceptance.INPUT_KEYS
    assert (
        manifest["inputs"]["candidate_control_plane_vars"]
        != manifest["inputs"]["control_plane_vars"]
    )
    assert (
        manifest["inputs"]["candidate_control_plane_secrets"]
        != manifest["inputs"]["control_plane_secrets"]
    )
    for path in manifest["approvals"].values():
        approval = json.loads(Path(path).read_text(encoding="utf-8"))
        assert approval["approved"] is False
        assert approval["approved_at"] is None
        assert approval["expires_at"] is None
    binding = json.loads(
        (inputs["root"] / "acceptance" / "hetzner-binding.json").read_text()
    )
    assert binding["account_id"] is None
    assert binding["state_sha256"] is None
    assert binding["server_id"] is None
    observations = json.loads(
        (inputs["root"] / "acceptance" / "observations.json").read_text()
    )
    assert set(observations["rows"]) == set(module.OBSERVATION_STEPS)
    assert all(row["observed"] is False for row in observations["rows"].values())
    assert len(encrypted) == 2
    module._validate_runtime(encrypted[0])
    assert (
        encrypted[0]["observability_secrets"]["senders"][1]["node_id"]
        == "deadman-reverse-a"
    )
    assert capsys.readouterr() == ("", "")
    serialized_root = b"".join(path.read_bytes() for path in files)
    assert b"primary-fixture-token" not in serialized_root
    assert b"secondary-fixture-token" not in serialized_root


def test_non_private_telegram_input_refuses_before_root_or_tool_execution(
    inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(SCRIPT, "observability_preparer_private_input")
    inputs["telegram"].chmod(0o644)
    monkeypatch.setattr(
        module, "_source_identity", lambda: pytest.fail("source identity called")
    )

    with pytest.raises(
        module.PreparationError, match="private Telegram input required"
    ):
        module.prepare(inputs["root"], inputs["config"], inputs["telegram"])

    assert not inputs["root"].exists()


def test_private_chat_topic_zero_is_schema_valid(inputs) -> None:
    module = _load(SCRIPT, "observability_preparer_private_chat")
    telegram = _private_json(
        inputs["parent"] / "telegram-private-chat.json",
        {
            "schema_version": 1,
            "primary": {
                "bot_token": "123456789:primary-fixture-token",
                "chat_id": "100000001",
                "topic_id": 0,
            },
            "secondary": {
                "bot_token": "987654321:secondary-fixture-token",
                "chat_id": "100000002",
                "topic_id": 0,
            },
        },
    )

    runtime = module._runtime_document(
        module._load_config(inputs["config"]),
        module._load_telegram(telegram),
        _fixture_pki(),
    )

    module._validate_runtime(runtime)
    assert runtime["observability_secrets"]["telegram"]["topic_id"] == 0
    assert runtime["observability_deadman_secrets"]["telegram"]["topic_id"] == 0


@pytest.mark.parametrize("topic_id", [-1, True, False])
def test_invalid_private_chat_topic_refuses(inputs, topic_id: object) -> None:
    module = _load(SCRIPT, f"observability_preparer_invalid_topic_{topic_id!s}")
    telegram = _private_json(
        inputs["parent"] / f"telegram-invalid-{topic_id!s}.json",
        {
            "schema_version": 1,
            "primary": {
                "bot_token": "123456789:primary-fixture-token",
                "chat_id": "100000001",
                "topic_id": topic_id,
            },
            "secondary": {
                "bot_token": "987654321:secondary-fixture-token",
                "chat_id": "100000002",
                "topic_id": 0,
            },
        },
    )

    with pytest.raises(module.PreparationError, match="Telegram input rejected"):
        module._load_telegram(telegram)


def test_symlinked_private_input_refuses_before_root_creation(
    inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(SCRIPT, "observability_preparer_symlink_input")
    link = inputs["parent"] / "telegram-link.json"
    link.symlink_to(inputs["telegram"])
    monkeypatch.setattr(
        module, "_source_identity", lambda: pytest.fail("source identity called")
    )

    with pytest.raises(
        module.PreparationError, match="private Telegram input required"
    ):
        module.prepare(inputs["root"], inputs["config"], link)

    assert not inputs["root"].exists()


def test_writable_non_sticky_root_ancestor_refuses_before_tool_execution(
    inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(SCRIPT, "observability_preparer_writable_ancestor")
    unsafe = inputs["parent"] / "unsafe-ancestor"
    unsafe.mkdir(mode=0o700)
    private_parent = unsafe / "private"
    private_parent.mkdir(mode=0o700)
    unsafe.chmod(0o777)
    monkeypatch.setattr(
        module, "_source_identity", lambda: pytest.fail("source identity called")
    )

    with pytest.raises(module.PreparationError, match="private parent rejected"):
        module.prepare(
            private_parent / "prepared", inputs["config"], inputs["telegram"]
        )

    assert not (private_parent / "prepared").exists()


def test_writable_sticky_ancestor_allows_private_input(inputs) -> None:
    module = _load(SCRIPT, "observability_preparer_sticky_ancestor")
    sticky = inputs["parent"] / "sticky-ancestor"
    sticky.mkdir(mode=0o700)
    private_parent = sticky / "private"
    private_parent.mkdir(mode=0o700)
    config = private_parent / "config.json"
    config.write_bytes(inputs["config"].read_bytes())
    config.chmod(0o600)
    sticky.chmod(0o1777)

    assert module._load_config(config)["schema_version"] == 1


def test_prepare_refuses_root_substitution_without_writing_into_replacement(
    inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(SCRIPT, "observability_preparer_root_substitution")
    encrypted: list[dict] = []
    _patch_generators(monkeypatch, module, encrypted)
    fixture_ssh = module._generate_ssh
    displaced = inputs["parent"] / "displaced"

    def substitute_root(workspace: Path) -> None:
        inputs["root"].rename(displaced)
        inputs["root"].mkdir(mode=0o700)
        (inputs["root"] / "sentinel").write_text("replacement\n", encoding="utf-8")
        fixture_ssh(workspace)

    monkeypatch.setattr(module, "_generate_ssh", substitute_root)

    with pytest.raises(module.PreparationError, match="private root binding changed"):
        module.prepare(inputs["root"], inputs["config"], inputs["telegram"])

    assert (inputs["root"] / "sentinel").read_text(encoding="utf-8") == "replacement\n"
    assert list(displaced.iterdir()) == []


def test_materialize_validates_decrypted_fragment_and_writes_atomically_private(
    inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(SCRIPT, "observability_preparer_materialize")
    root = inputs["root"]
    root.mkdir(mode=0o700)
    for name in ("age", "secrets", "materialized"):
        (root / name).mkdir(mode=0o700)
    module._write_private(root / "age" / "identity.txt", b"AGE-SECRET-KEY-fixture\n")
    module._write_private(
        root / "secrets" / "observability-secrets.sops.yaml", b"ciphertext\n"
    )
    config = module._load_config(inputs["config"])
    telegram = module._load_telegram(inputs["telegram"])
    runtime = module._runtime_document(config, telegram, _fixture_pki())
    plaintext = yaml.safe_dump(runtime, sort_keys=True).encode("utf-8")
    monkeypatch.setattr(module, "_run", lambda *args, **kwargs: plaintext)

    module.materialize(root)

    output = root / "materialized" / "observability-secrets.yml"
    assert output.read_bytes() == plaintext
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_materialize_refuses_root_substitution_before_plaintext_write(
    inputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(SCRIPT, "observability_preparer_materialize_substitution")
    root = inputs["root"]
    root.mkdir(mode=0o700)
    for name in ("age", "secrets", "materialized"):
        (root / name).mkdir(mode=0o700)
    module._write_private(root / "age" / "identity.txt", b"AGE-SECRET-KEY-fixture\n")
    module._write_private(
        root / "secrets" / "observability-secrets.sops.yaml", b"ciphertext\n"
    )
    config = module._load_config(inputs["config"])
    telegram = module._load_telegram(inputs["telegram"])
    plaintext = yaml.safe_dump(
        module._runtime_document(config, telegram, _fixture_pki()), sort_keys=True
    ).encode("utf-8")
    displaced = inputs["parent"] / "materialize-displaced"

    def substitute(*args, **kwargs) -> bytes:
        root.rename(displaced)
        root.mkdir(mode=0o700)
        (root / "sentinel").write_text("replacement\n", encoding="utf-8")
        return plaintext

    monkeypatch.setattr(module, "_run", substitute)

    with pytest.raises(module.PreparationError, match="private root binding changed"):
        module.materialize(root)

    assert (root / "sentinel").read_text(encoding="utf-8") == "replacement\n"
    assert not (displaced / "materialized" / "observability-secrets.yml").exists()


def test_materialize_closes_open_directory_when_later_directory_open_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(SCRIPT, "observability_preparer_materialize_directory_failure")
    closed: list[int] = []
    opened = iter((11,))

    monkeypatch.setattr(module, "_existing_private_root", lambda _path: Path("/root"))
    monkeypatch.setattr(module, "_open_secure_directory", lambda *_args, **_kwargs: 10)

    def open_relative(*_args, **_kwargs) -> int:
        try:
            return next(opened)
        except StopIteration:
            raise module.PreparationError("encrypted authority rejected") from None

    monkeypatch.setattr(module, "_open_relative_directory", open_relative)
    monkeypatch.setattr(module.os, "close", closed.append)

    with pytest.raises(module.PreparationError, match="encrypted authority rejected"):
        module.materialize(Path("/root"))

    assert closed == [11, 10]


def test_materialize_closes_identity_when_encrypted_input_open_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(SCRIPT, "observability_preparer_materialize_input_failure")
    closed: list[int] = []
    directories = iter((11, 12, 13))
    files = iter((14,))

    monkeypatch.setattr(module, "_existing_private_root", lambda _path: Path("/root"))
    monkeypatch.setattr(module, "_open_secure_directory", lambda *_args, **_kwargs: 10)
    monkeypatch.setattr(
        module, "_open_relative_directory", lambda *_args, **_kwargs: next(directories)
    )

    def open_private(*_args, **_kwargs) -> int:
        try:
            return next(files)
        except StopIteration:
            raise module.PreparationError("encrypted authority rejected") from None

    monkeypatch.setattr(module, "_open_private_at", open_private)
    monkeypatch.setattr(module.os, "close", closed.append)

    with pytest.raises(module.PreparationError, match="encrypted authority rejected"):
        module.materialize(Path("/root"))

    assert closed == [14, 13, 12, 11, 10]


def test_real_openssl_pki_has_expected_uses_and_empty_crl(tmp_path: Path) -> None:
    module = _load(SCRIPT, "observability_preparer_openssl")
    config = {
        "sender_ids": {"canary": "canary-a", "deadman-reverse": "deadman-reverse-a"},
        "pki": {
            "ingress_sni": "ingest.fixture.test",
            "control_plane_dns_san": "control.fixture.test",
            "deadman_pulse_sni": "pulse.fixture.test",
        },
    }
    tmp_path.chmod(0o700)

    pki, _ = module._generate_pki(config, tmp_path)

    assert pki["receiver"]["crl"].startswith("-----BEGIN X509 CRL-----")
    subprocess.run(
        [
            "openssl",
            "verify",
            "-x509_strict",
            "-purpose",
            "sslclient",
            "-crl_check_all",
            "-CAfile",
            str(tmp_path / "staging-observability-receiver-ca.crt"),
            "-CRLfile",
            str(tmp_path / "staging-observability-receiver-ca.crl"),
            str(tmp_path / "canary-sender.crt"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for hostname in ("ingest.fixture.test", "control.fixture.test"):
        subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(tmp_path / "ingress-server.crt"),
                "-noout",
                "-checkhost",
                hostname,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(
        [
            "openssl",
            "verify",
            "-x509_strict",
            "-purpose",
            "sslserver",
            "-CAfile",
            str(tmp_path / "staging-observability-pulse-ca.crt"),
            str(tmp_path / "pulse-server.crt"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
