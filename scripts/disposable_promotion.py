"""Fixed first-onboarding adapter for one disposable staging deployment.

Invoked only through ``make deploy`` and its SSH baseline controller. The
private intent names explicit SOPS/age/AWG input files and persistent output
files; credentials never become command arguments or environment values.
It is not an operator command or an arbitrary deploy hook. A binding epoch is
published only during onboarding, never guessed during intent validation.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import re

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
KIND = "disposable-staging-intent"
PROFILES = {"p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"}
INPUTS = {
    "sops_file",
    "age_key_file",
    "awg_key_file",
    "executor_manifest",
    "cleanup_manifest",
}
PREPARED_INPUTS = INPUTS | {"sops_source_file"}
SOURCE_IDENTITY = {"path", "device", "inode", "sha256"}
OUTPUTS = {
    "liveness_config",
    "registry",
    "binding",
    "promotion_config",
    "authority",
    "executor_manifest",
}
TARGET = {"inventory_alias", "public_service_address_sha256", "deployable_digest"}


class OnboardingError(ValueError):
    """Categorical only: never echo configuration, credential or child output."""


def _module(name):
    spec = importlib.util.spec_from_file_location(
        "onboarding_" + name.replace("-", "_"), ROOT / "scripts" / (name + ".py")
    )
    if spec is None or spec.loader is None:
        raise OnboardingError("onboarding-component-unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _paths(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError
    for item in value.values():
        if (
            not isinstance(item, str)
            or not Path(item).is_absolute()
            or str(Path(item)) != item
            or ".." in Path(item).parts
            or any(ord(char) < 32 or ord(char) == 127 for char in item)
        ):
            raise ValueError


def _validate_intent(value, input_fields):
    fields = {
        "schema_version",
        "kind",
        "target_identity",
        "host",
        "cohort",
        "client",
        "liveness",
        "inputs",
        "outputs",
    }
    if input_fields == PREPARED_INPUTS:
        fields.add("sops_source_identity")
    try:
        if (
            not isinstance(value, dict)
            or set(value) != fields
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["kind"] != KIND
            or value["cohort"] != "device-full-staging"
            or not isinstance(value["host"], str)
            or re.fullmatch(
                r"upcloud:ci-staging-[a-z0-9][a-z0-9-]{0,51}", value["host"]
            )
            is None
            or not isinstance(value["client"], str)
            or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value["client"]) is None
        ):
            raise ValueError
        if len(json.dumps(value).encode()) > 32768:
            raise ValueError
        _paths(value["inputs"], input_fields)
        _paths(value["outputs"], OUTPUTS)
        sops_source = value["inputs"].get(
            "sops_source_file", value["inputs"]["sops_file"]
        )
        paths = [
            *value["inputs"].values(),
            *value["outputs"].values(),
            value["outputs"]["registry"] + ".pending.json",
            value["outputs"]["registry"] + ".lock",
            value["outputs"]["authority"] + ".lock",
            sops_source + ".new-client.lock",
        ]
        if len(paths) != len(set(paths)):
            raise ValueError
        config = value["liveness"]
        # This private intent deliberately lacks the not-yet-published epoch.
        # Reuse every other public schema rule, without inserting a fake epoch
        # or changing the public evaluator's accepted contract.
        schema = json.loads(
            (ROOT / "contract/protocol-liveness.schema.json").read_bytes()
        )
        target_schema = schema["$defs"]["target"]
        target_schema["required"].remove("applied_at")
        del target_schema["properties"]["applied_at"]
        jsonschema.Draft202012Validator(schema).validate(config)
        if (
            len(config["sentinels"]) != 1
            or len(config["policies"]) != 1
            or set(config["policies"][0]["required_profiles"]) != PROFILES
            or value["target_identity"] != config["sentinels"][0]["target"]
            or set(value["target_identity"]) != TARGET
        ):
            raise ValueError
        provider, environment = value["host"].split(":")
        awg = config["sentinels"][0].get("awg_target", {})
        if (
            awg.get("provider") != provider
            or awg.get("environment") != environment
            or _module("protocol-liveness").semantic_errors(config)
        ):
            raise ValueError
        return copy.deepcopy(value)
    except (ValueError, TypeError, KeyError, jsonschema.ValidationError):
        raise OnboardingError("onboarding-intent-refused") from None


def validate_intent(value):
    """Validate an operator or controller-prepared intent without file I/O."""
    if isinstance(value, dict) and isinstance(value.get("inputs"), dict):
        if set(value["inputs"]) == PREPARED_INPUTS:
            return _validate_prepared_intent(value)
    return _validate_intent(value, INPUTS)


def _validate_prepared_intent(value):
    """Validate the controller-only snapshot plus its canonical SOPS source."""
    prepared = _validate_intent(value, PREPARED_INPUTS)
    identity = prepared["sops_source_identity"]
    source = prepared["inputs"]["sops_source_file"]
    try:
        if (
            not isinstance(identity, dict)
            or set(identity) != SOURCE_IDENTITY
            or identity["path"] != source
            or not isinstance(identity["path"], str)
            or not Path(identity["path"]).is_absolute()
            or str(Path(identity["path"])) != identity["path"]
            or type(identity["device"]) is not int
            or not 0 <= identity["device"] <= 2**64 - 1
            or type(identity["inode"]) is not int
            or not 1 <= identity["inode"] <= 2**64 - 1
            or not isinstance(identity["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", identity["sha256"]) is None
            or source == prepared["inputs"]["sops_file"]
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise OnboardingError("onboarding-intent-refused")
    return prepared


def _decrypt(sops, age, output, environment):
    import install_liveness_sentinel as installer

    clean = {
        key: environment[key]
        for key in ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE")
        if key in environment
    }
    installer._run(
        [str(ROOT / "scripts/decrypt-secrets.sh")],
        environment={
            **clean,
            "SOPS_FILE": str(sops),
            "SOPS_AGE_KEY_FILE": str(age),
            "SECRETS_FILE": str(output),
        },
        timeout=60,
    )


def _cleanup_target(intent, host):
    import hashlib

    guard = _module("staging-cleanup-guard")
    manifest = guard.load_manifest(
        Path(intent["inputs"]["cleanup_manifest"]),
        expected_provider="upcloud",
        expected_environment=intent["host"].split(":")[1],
    )
    raw = guard._private_read(
        Path(manifest["state"]["path"]),
        "state",
        max_bytes=guard.MAX_STATE_BYTES,
        exact_parent_mode=False,
    )
    if hashlib.sha256(raw).hexdigest() != manifest["state"]["sha256"]:
        raise ValueError
    state = guard._json_object(raw, "state")
    if (
        guard._extract_state_identity(state, manifest["hostname"])
        != (manifest["server_uuid"], manifest["root_storage_uuid"])
        or state.get("outputs", {}).get("server_ipv4", {}).get("value")
        != host["address"]
        or manifest["hostname"] != host["name"]
    ):
        raise ValueError
    return manifest


def prepare_intent(intent, host, memberships, directory, deployed_secrets, environment):
    """Fence capabilities before site writes; only paths cross Ansible's stdin."""
    import hashlib
    import hmac
    import os
    import yaml

    # Only the controller may add the canonical source SOPS path after it has
    # snapshotted the original operator intent.
    value = _validate_intent(intent, INPUTS)
    guard = _module("staging-cleanup-guard")
    plaintext = directory / "onboarding-secrets.yaml"
    try:
        if (
            memberships != ["vpn-device-full-staging"]
            or host["name"] != value["target_identity"]["inventory_alias"]
            or hashlib.sha256(host["address"].encode()).hexdigest()
            != value["target_identity"]["public_service_address_sha256"]
        ):
            raise ValueError
        _cleanup_target(value, host)
        for path in value["outputs"].values():
            output = Path(path)
            if output.is_relative_to(directory):
                raise ValueError
            fd, _ = guard._open_private_parent(output, "onboarding output")
            os.close(fd)
            if os.path.lexists(output):
                guard._private_read(output, "onboarding output", max_bytes=262144)
        sops_source_file = value["inputs"]["sops_file"]
        source_raw, source_identity = guard._private_snapshot(
            Path(sops_source_file), "onboarding input", max_bytes=262144
        )
        for name, path in value["inputs"].items():
            raw = (
                source_raw
                if name == "sops_file"
                else guard._private_read(
                    Path(path), "onboarding input", max_bytes=262144
                )
            )
            # SOPS infers its store from the filename; this capability is YAML.
            suffix = ".yaml" if name == "sops_file" else ""
            snapshot = directory / ("onboarding-" + name + suffix)
            guard._private_write_new(snapshot, raw, "onboarding snapshot")
            value["inputs"][name] = str(snapshot)
        value["inputs"]["sops_source_file"] = sops_source_file
        value["sops_source_identity"] = {
            "path": sops_source_file,
            "device": source_identity[0],
            "inode": source_identity[1],
            "sha256": hashlib.sha256(source_raw).hexdigest(),
        }
        _cleanup_target(value, host)
        import disposable_liveness_executor as executor
        import time

        executor_manifest, _ = executor._read_private(
            Path(value["inputs"]["executor_manifest"])
        )
        executor._validate_manifest(executor_manifest, int(time.time()))
        _decrypt(
            Path(value["inputs"]["sops_file"]),
            Path(value["inputs"]["age_key_file"]),
            plaintext,
            environment,
        )
        secrets = yaml.safe_load(
            guard._private_read(plaintext, "onboarding secrets", max_bytes=262144)
        )
        if not isinstance(secrets, dict) or secrets != yaml.safe_load(deployed_secrets):
            raise ValueError
        enrollment = secrets.get("client_registry", {}).get(value["client"], {})
        private = guard._private_read(
            Path(value["inputs"]["awg_key_file"]), "onboarding input", max_bytes=128
        )
        if (
            enrollment.get("status") not in ("issued", "delivered", "active")
            or not isinstance(enrollment.get("awg_private_key"), str)
            or re.fullmatch(rb"[A-Za-z0-9+/]{43}=\n?", private) is None
            or not hmac.compare_digest(
                private.rstrip(b"\n"), enrollment["awg_private_key"].encode()
            )
        ):
            raise ValueError
        return value
    except (ValueError, TypeError, KeyError, OSError, yaml.YAMLError):
        raise OnboardingError("onboarding-capability-refused") from None
    finally:
        # This is a controller-created file in its private, disposable directory.
        # No operator-owned plaintext is removed or rewritten.
        try:
            plaintext.unlink(missing_ok=True)
        except OSError:
            # The private file may remain; never credit finalization or expose
            # the filesystem exception while the outer controller reclaims it.
            raise OnboardingError("onboarding-cleanup-incomplete") from None


def _ensure_document(path, document):
    import disposable_liveness_executor as executor
    import os

    if os.path.lexists(path):
        if executor._read_private(path)[0] != document:
            raise ValueError
    else:
        executor._write_new(path, document)


def finalize(intent, environment, *, clock=None):
    """Install before SSH prepare, or reconcile the exact existing assignment.

    Persistent private authority/config files preserve the binding epoch across
    controller restarts. They are not a success receipt: only the canonical
    installer and an exact executor receipt establish installation. A separate
    fresh evaluator must still pass before SSH prepare and after SSH apply.
    """
    import hashlib
    import hmac
    import io
    import os
    import time
    from contextlib import ExitStack
    import install_liveness_sentinel as installer
    import disposable_liveness_executor as executor

    guard = _module("staging-cleanup-guard")
    project_locks = ExitStack()
    try:
        value = _validate_prepared_intent(intent)
        outputs = {name: Path(path) for name, path in value["outputs"].items()}
        inputs = {name: Path(path) for name, path in value["inputs"].items()}
        sentinel = value["liveness"]["sentinels"][0]
        state_manifest = guard.load_manifest(
            inputs["cleanup_manifest"],
            expected_provider="upcloud",
            expected_environment=value["host"].split(":")[1],
        )
        state = guard._json_object(
            guard._private_read(
                Path(state_manifest["state"]["path"]),
                "state",
                max_bytes=guard.MAX_STATE_BYTES,
                exact_parent_mode=False,
            ),
            "state",
        )
        _cleanup_target(
            value,
            {
                "address": state["outputs"]["server_ipv4"]["value"],
                "name": value["target_identity"]["inventory_alias"],
            },
        )
        if (
            hashlib.sha256(
                state["outputs"]["server_ipv4"]["value"].encode()
            ).hexdigest()
            != value["target_identity"]["public_service_address_sha256"]
        ):
            raise ValueError
        # The ciphertext binds the enrolled private key; decryption capability
        # and its key were compared with deployment plaintext by preflight.
        # Completed reuse therefore never reopens the AWG private key.
        source_identity = value["sops_source_identity"]
        source_path = Path(source_identity["path"])
        project_lock = source_path.with_name(source_path.name + ".new-client.lock")
        # Retirement and every supported SOPS writer use this lock. Acquire it
        # before the first ciphertext read and retain it through publication.
        project_locks.enter_context(executor._exclusive_locks((project_lock,)))
        scope = {key: value[key] for key in value if key != "inputs"}
        raw_inputs = {
            key: guard._private_read(inputs[key], "onboarding input", max_bytes=262144)
            for key in ("sops_file", "executor_manifest", "cleanup_manifest")
        }
        source_sops, observed_source_identity = guard._private_snapshot(
            source_path, "onboarding input", max_bytes=262144
        )
        if (
            observed_source_identity
            != (source_identity["device"], source_identity["inode"])
            or not hmac.compare_digest(
                hashlib.sha256(source_sops).hexdigest(), source_identity["sha256"]
            )
            or not hmac.compare_digest(source_sops, raw_inputs["sops_file"])
        ):
            raise ValueError
        scope["sops_project_lock_sha256"] = hashlib.sha256(
            str(project_lock).encode("utf-8")
        ).hexdigest()
        scope["input_sha256"] = {
            key: hashlib.sha256(raw).hexdigest() for key, raw in raw_inputs.items()
        }
        scope_digest = hashlib.sha256(
            json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        clean = {
            key: environment[key]
            for key in ("HOME", "PATH", "LANG", "LC_ALL", "LC_CTYPE")
            if key in environment
        }
        env = {
            **clean,
            "HOSTS": value["host"],
            "COHORTS": value["cohort"],
            "SOPS_FILE": str(inputs["sops_file"]),
            "SOPS_AGE_KEY_FILE": str(inputs["age_key_file"]),
        }
        home = Path(clean.get("HOME", str(Path.home())))
        runner = lambda command, **kwargs: installer._run(
            list(command), environment=clean, **kwargs
        )
        authority_lock = outputs["authority"].with_name(
            outputs["authority"].name + ".lock"
        )
        with executor._exclusive_locks((authority_lock,)):
            if os.path.lexists(outputs["authority"]):
                authority, _ = executor._read_private(outputs["authority"])
                if (
                    set(authority) != {"schema_version", "scope_sha256", "applied_at"}
                    or type(authority["schema_version"]) is not int
                    or authority["schema_version"] != 1
                    or authority["scope_sha256"] != scope_digest
                    or type(authority["applied_at"]) is not int
                    or authority["applied_at"] < 1
                ):
                    raise ValueError
            else:
                pending = outputs["registry"].with_name(
                    outputs["registry"].name + ".pending.json"
                )
                if any(os.path.lexists(path) for path in (*outputs.values(), pending)):
                    raise ValueError
                epoch = int((clock or time.time)())
                if epoch < 1:
                    raise ValueError
                authority = {
                    "schema_version": 1,
                    "scope_sha256": scope_digest,
                    "applied_at": epoch,
                }
                executor._write_new(outputs["authority"], authority)
            config = copy.deepcopy(value["liveness"])
            config["sentinels"][0]["target"]["applied_at"] = authority["applied_at"]
            _module("protocol-liveness").validate_config(config)
            _ensure_document(outputs["liveness_config"], config)
            manifest = guard._json_object(raw_inputs["executor_manifest"], "executor")
            if guard.canonical_json(manifest) != raw_inputs["executor_manifest"]:
                raise ValueError
            _ensure_document(outputs["executor_manifest"], manifest)
            sid = sentinel["id"]
            with installer.registry_lock(outputs["registry"]):
                registry = installer._state(outputs["registry"], "sentinels")
                pending = installer._state(
                    outputs["registry"].with_name(
                        outputs["registry"].name + ".pending.json"
                    ),
                    "pending",
                )
                if set(registry["sentinels"]) - {sid} or set(pending["pending"]) - {
                    sid
                }:
                    raise ValueError
                entry = registry["sentinels"].get(sid)
                if entry is not None and pending["pending"]:
                    raise ValueError
                if entry is not None:
                    binding = executor.load_bound_executor(
                        outputs["binding"],
                        outputs["executor_manifest"],
                        outputs["liveness_config"],
                        home=home,
                        now=int(time.time()),
                        runner=runner,
                    )
                    revision, source, _engine = installer._source_identity(ROOT)
                    expected = {
                        **config["sentinels"][0]["target"],
                        "required_profiles": sorted(PROFILES),
                        "source_revision": revision,
                        "runner_sha256": hashlib.sha256(source).hexdigest(),
                        "public_profile_digest": binding["target_identity"][
                            "public_profile_digest"
                        ],
                    }
                    if (
                        any(
                            entry.get(key) != sentinel.get(key)
                            for key in (
                                "ssh_target",
                                "ssh_transport_host",
                                "ssh_host_key_alias",
                                "policy",
                                "vantage",
                            )
                        )
                        or entry.get("client") != value["client"]
                        or entry["target_identity"] != expected
                        or entry.get("executor_binding_sha256")
                        != executor.binding_digest(outputs["binding"])
                        or binding["target_identity"] != expected
                        or binding["provenance"] != entry["provenance"]
                        or binding["generation_id"] != entry["generation_id"]
                        or binding["client"] != value["client"]
                        or binding["sentinel"] != sid
                        or binding["cleanup_manifest_sha256"]
                        != scope["input_sha256"]["cleanup_manifest"]
                    ):
                        raise ValueError
                    receipt = installer._receipt(
                        sentinel, entry, env, executor={"profile": binding["profile"]}
                    )
                    expected_receipt = {
                        "generation_id": entry["generation_id"],
                        "status": "committed",
                        "runner_sha256": expected["runner_sha256"],
                        "provenance": entry["provenance"],
                        "target_identity": expected,
                    }
                    if receipt != expected_receipt:
                        raise ValueError
            if entry is None:
                # A single fenced private read supplies only the installer's
                # stdin; no key appears in JSON, argv or environment values.
                key = guard._private_read(
                    inputs["awg_key_file"], "onboarding input", max_bytes=128
                )
                with io.StringIO(key.decode("ascii")) as stream:
                    receipt = installer.install(
                        outputs["liveness_config"],
                        sid,
                        value["client"],
                        outputs["registry"],
                        read_awg_stdin=True,
                        stdin=stream,
                        environment=env,
                        executor_manifest=outputs["executor_manifest"],
                        executor_binding=outputs["binding"],
                        cleanup_manifest=inputs["cleanup_manifest"],
                    )
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("status") != "committed"
                ):
                    raise ValueError
            proof = {
                "schema_version": 1,
                "liveness_config": str(outputs["liveness_config"]),
                "expected_sentinels": [sid],
                "target_identity": receipt["target_identity"],
                "executor": {
                    "manifest": str(outputs["executor_manifest"]),
                    "binding": str(outputs["binding"]),
                },
            }
            _ensure_document(outputs["promotion_config"], proof)
            return outputs["promotion_config"]
    except (ValueError, KeyError, TypeError, OSError):
        raise OnboardingError("onboarding-finalization-refused") from None
    finally:
        project_locks.close()
