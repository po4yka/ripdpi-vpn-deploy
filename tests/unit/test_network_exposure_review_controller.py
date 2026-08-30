"""Controller boundary tests for the local-only exposure review command."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/network-exposure-review-controller.py"


def load_controller():
    spec = importlib.util.spec_from_file_location("network_exposure_review_controller", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config(path, **changes):
    value = {"mode": "log_only", "artifact": "/private/artifact.json", "trusted_key": "/private/key.pem",
             "trusted_key_sha256": "a" * 64, "source_id": "reviewed-source",
             "promotion": {"approved": False, "digest": "", "authorized_hosts": []}}
    value.update(changes)
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return value


def environment(path, **changes):
    value = {"NETWORK_EXPOSURE_CONFIG": str(path), "ANSIBLE_LIMIT": "vpn-p0", "PATH": os.environ["PATH"]}
    value.update(changes)
    return value


def valid_runner(*args, **kwargs):
    return subprocess.CompletedProcess(args[0], 0, json.dumps({"validation": "valid", "source_id": "reviewed-source",
        "counts": {"ingress": 1, "host_egress": 2, "forwarded": 3}, "content_sha256": "b" * 64,
        "artifact_sha256": "c" * 64}), "")


def _make_fixture(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "network-exposure-review-controller.py").write_bytes(SCRIPT.read_bytes())
    (scripts / "fleet_inspection.py").write_text(textwrap.dedent("""\
        class InspectionError(Exception):
            pass

        def select_hosts(_path, aliases):
            if aliases != ["vpn-p0"]:
                raise InspectionError("unexpected-alias")
            return [{"name": "vpn-p0"}]
        """))
    (scripts / "network-exposure-gate.py").write_text(textwrap.dedent("""\
        import json
        print(json.dumps({
            "validation": "valid",
            "source_id": "reviewed-source",
            "counts": {"ingress": 1, "host_egress": 2, "forwarded": 3},
            "content_sha256": "b" * 64,
            "artifact_sha256": "c" * 64,
        }))
        """))
    path = tmp_path / "review.json"
    config(path)
    return path


def test_invalid_inputs_never_resolve_inventory_or_start_validator(tmp_path, monkeypatch):
    controller = load_controller()
    path = tmp_path / "config.json"
    config(path, mode="canary")
    called = []
    monkeypatch.setattr(controller.inspection, "select_hosts", lambda *_: called.append("inventory"))
    with pytest.raises(controller.ReviewError, match="invalid-config"):
        controller.review(environment(path), runner=lambda *_args, **_kwargs: called.append("validator"))
    assert called == []


@pytest.mark.parametrize("mutation", ["symlink", "writable"])
def test_unsafe_config_refuses_before_local_or_child_work(tmp_path, monkeypatch, mutation):
    controller = load_controller()
    path = tmp_path / "config.json"
    config(path)
    if mutation == "symlink":
        target = tmp_path / "target.json"
        config(target)
        path.unlink()
        path.symlink_to(target)
    else:
        path.chmod(0o640)
    monkeypatch.setattr(controller.inspection, "select_hosts", lambda *_: pytest.fail("inventory called"))
    with pytest.raises(controller.ReviewError, match="unsafe-config"):
        controller.review(environment(path), runner=lambda *_args, **_kwargs: pytest.fail("validator called"))


def test_replaced_config_refuses_after_selection_before_validator(tmp_path, monkeypatch):
    controller = load_controller()
    path = tmp_path / "config.json"
    config(path)
    def replace(*_):
        replacement = tmp_path / "replacement.json"
        config(replacement, source_id="other-source")
        os.replace(replacement, path)
        return [{"name": "vpn-p0"}]
    monkeypatch.setattr(controller.inspection, "select_hosts", replace)
    with pytest.raises(controller.ReviewError, match="config-replaced"):
        controller.review(environment(path), runner=lambda *_args, **_kwargs: pytest.fail("validator called"))


def test_controller_emits_only_redacted_aggregate_and_resolves_once(tmp_path, monkeypatch):
    controller = load_controller()
    path = tmp_path / "config.json"
    config(path)
    selected = []
    monkeypatch.setattr(controller.inspection, "select_hosts", lambda _path, aliases: selected.append(aliases) or [{"name": "vpn-p0", "address": "198.51.100.8"}])
    result = controller.review(environment(path), runner=valid_runner)
    assert selected == [["vpn-p0"]]
    assert result == {"source_id": "reviewed-source", "content_sha256": "b" * 64,
                      "artifact_sha256": "c" * 64, "counts": {"ingress": 1, "host_egress": 2, "forwarded": 3}}
    encoded = json.dumps(result)
    assert "vpn-p0" not in encoded and "198.51.100.8" not in encoded and str(path) not in encoded


@pytest.mark.parametrize("key,value", [("ANSIBLE_DEBUG", "true"), ("ANSIBLE_PLUGIN_PATH", "/tmp/plugin"), ("GIT_DIR", "/tmp/git")])
def test_ambient_execution_controls_refuse_before_validator(tmp_path, monkeypatch, key, value):
    controller = load_controller()
    path = tmp_path / "config.json"
    config(path)
    monkeypatch.setattr(controller.inspection, "select_hosts", lambda *_: pytest.fail("inventory called"))
    with pytest.raises(controller.ReviewError):
        controller.review(environment(path, **{key: value}), runner=lambda *_args, **_kwargs: pytest.fail("validator called"))


def test_make_valid_review_removes_its_exported_ansible_config(tmp_path):
    path = _make_fixture(tmp_path)
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "network-exposure-review",
         "NETWORK_EXPOSURE_CONFIG=" + str(path), "ANSIBLE_LIMIT=vpn-p0"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"],
             "ANSIBLE_CONFIG": "/operator/ambient-ansible.cfg"},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "artifact_sha256": "c" * 64,
        "content_sha256": "b" * 64,
        "counts": {"forwarded": 3, "host_egress": 2, "ingress": 1},
        "source_id": "reviewed-source",
    }


def test_make_valid_review_does_not_import_hostile_pythonpath_sitecustomize(tmp_path):
    path = _make_fixture(tmp_path)
    hostile = tmp_path / "hostile-python"
    hostile.mkdir()
    marker = tmp_path / "sitecustomize-executed"
    (hostile / "sitecustomize.py").write_text(
        "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
    )
    result = subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "network-exposure-review",
         "NETWORK_EXPOSURE_CONFIG=" + str(path), "ANSIBLE_LIMIT=vpn-p0"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"],
             "PYTHONPATH": str(hostile)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("failure", ["chmod", "open", "write", "fsync"])
def test_snapshot_setup_failure_removes_owned_directory(tmp_path, monkeypatch, failure):
    controller = load_controller()
    path = tmp_path / "config.json"
    config(path)
    monkeypatch.setattr(controller.inspection, "select_hosts", lambda *_: [{"name": "vpn-p0"}])

    original_temporary_directory = controller.tempfile.TemporaryDirectory
    directories = []

    def tracked_temporary_directory(*args, **kwargs):
        kwargs["dir"] = tmp_path
        directory = original_temporary_directory(*args, **kwargs)
        directories.append(directory)
        return directory

    monkeypatch.setattr(controller.tempfile, "TemporaryDirectory", tracked_temporary_directory)
    if failure == "chmod":
        original_chmod = controller.os.chmod
        monkeypatch.setattr(
            controller.os,
            "chmod",
            lambda target, mode: (_ for _ in ()).throw(OSError("chmod failed"))
            if Path(target).name.startswith("network-exposure-review-")
            else original_chmod(target, mode),
        )
    elif failure == "open":
        original_open = controller.os.open
        monkeypatch.setattr(
            controller.os,
            "open",
            lambda target, *args, **kwargs: (_ for _ in ()).throw(OSError("open failed"))
            if Path(target).name == "review.json"
            else original_open(target, *args, **kwargs),
        )
    elif failure == "write":
        monkeypatch.setattr(controller.os, "write", lambda *_: (_ for _ in ()).throw(OSError("write failed")))
    else:
        monkeypatch.setattr(controller.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("fsync failed")))

    with pytest.raises(OSError, match=f"{failure} failed"):
        controller.review(environment(path), runner=lambda *_args, **_kwargs: pytest.fail("validator called"))
    assert directories
    assert all(not Path(directory.name).exists() for directory in directories)


@pytest.mark.parametrize("assignment", ["NETWORK_EXPOSURE_CONFIG", "ANSIBLE_LIMIT"])
def test_make_rejects_literal_make_shell_before_recipe_side_effect(tmp_path, assignment):
    marker = tmp_path / "marker"
    hostile = "$(shell touch " + str(marker) + ")"
    values = {"NETWORK_EXPOSURE_CONFIG": str(tmp_path / "config.json"), "ANSIBLE_LIMIT": "vpn-p0"}
    values[assignment] = hostile
    result = subprocess.run(["make", "-f", str(ROOT / "Makefile"), "network-exposure-review",
                             *(key + "=" + value for key, value in values.items())],
                            cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert not marker.exists()
    assert "literal values" in result.stderr


@pytest.mark.parametrize("assignment,value", [("NETWORK_EXPOSURE_CONFIG", "'quoted'"), ("ANSIBLE_LIMIT", "$(touch nope)")])
def test_make_rejects_quotes_and_shell_substitution_literals(tmp_path, assignment, value):
    values = {"NETWORK_EXPOSURE_CONFIG": str(tmp_path / "config.json"), "ANSIBLE_LIMIT": "vpn-p0"}
    values[assignment] = value
    result = subprocess.run(["make", "-f", str(ROOT / "Makefile"), "network-exposure-review",
                             *(key + "=" + item for key, item in values.items())],
                            cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "literal values" in result.stderr
