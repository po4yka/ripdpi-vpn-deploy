"""Restore lists and pushes retained state versions through the locked backend.

Object storage (curl), OpenTofu decryption (tofu) and the backend wrapper
(terraform-env.sh) are stand-ins; the live restore drill covers the real ones.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PASSPHRASE = "synthetic-passphrase-0123456789"
SECRET_KEY = "synthetic-secret-key-value"
BUCKET = "fixture-bucket"
PROD_KEY = "state/upcloud/terraform.tfstate"
GREEN_KEY = "state/workspaces/prod-green/state/upcloud/terraform.tfstate"

# Serves the version listing and objects from STUB_STORE; logs argv and stdin.
CURL = """#!/usr/bin/env python3
import json, os, sys, urllib.parse
store = os.environ["STUB_STORE"]
next_page = os.path.join(store, "next-page")
if "key-marker=" in sys.argv[-1]:
    os.replace(open(next_page).read(), os.path.join(store, "listing.xml"))
with open(os.path.join(store, "curl.log"), "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read()}) + "\\n")
url = urllib.parse.urlsplit(sys.argv[-1])
query = urllib.parse.parse_qs(url.query, keep_blank_values=True)
if "versions" in query:
    sys.stdout.write(open(os.path.join(store, "listing.xml")).read())
    sys.exit(0)
path = os.path.join(store, "objects", query["versionId"][0])
if not os.path.exists(path):
    sys.stdout.write("<Error><Code>NoSuchVersion</Code></Error>")
    sys.exit(22)
sys.stdout.write(open(path).read())
"""

# "Encrypted" state is base64 plaintext under the passphrase recorded in meta.
TOFU = """#!/usr/bin/env python3
import base64, json, os, sys
with open(os.path.join(os.environ["STUB_STORE"], "tofu.log"), "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
work = sys.argv[1].removeprefix("-chdir=")
if sys.argv[2] == "init":
    sys.exit(0)
stored = json.load(open(os.path.join(work, "terraform.tfstate")))
if stored["meta"] != os.environ.get("TF_VAR_state_passphrase"):
    print("Error: decryption failed", file=sys.stderr)
    sys.exit(1)
sys.stdout.buffer.write(base64.b64decode(stored["encrypted_data"]))
"""

# The current remote state lives in STUB_STORE/current.json; pushes are logged.
WRAPPER = """#!/usr/bin/env python3
import json, os, sys
store = os.environ["STUB_STORE"]
current = os.path.join(store, "current.json")
with open(os.path.join(store, "wrapper.log"), "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1] == "init":
    sys.exit(0)
if sys.argv[1:3] == ["state", "pull"]:
    if os.path.exists(current):
        sys.stdout.write(open(current).read())
    sys.exit(0)
assert sys.argv[1:3] == ["state", "push"] and sys.argv[-1] == "-"
if os.environ.get("STUB_PUSH_FAIL"):
    print("Error: Error acquiring the state lock", file=sys.stderr)
    sys.exit(1)
pushed = sys.stdin.read()
with open(os.path.join(store, "push.log"), "a") as log:
    log.write(json.dumps({"args": sys.argv[3:], "env": os.environ["ENV"], "state": json.loads(pushed)}) + "\\n")
open(current, "w").write(pushed)
"""


def state(serial: int, lineage: str = "lineage-a", resources: int = 1) -> dict:
    return {"version": 4, "serial": serial, "lineage": lineage,
            "resources": [{"name": f"r{index}"} for index in range(resources)]}


def sealed(document: dict, passphrase: str = PASSPHRASE) -> str:
    return json.dumps({"serial": document["serial"], "lineage": document["lineage"], "meta": passphrase,
                       "encrypted_data": base64.b64encode(json.dumps(document).encode()).decode()})


def executable(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def restore(tmp_path):
    repo, store, binary, backend = (tmp_path / name for name in ("repo", "store", "bin", "backend"))
    for directory in (repo / "scripts", store / "objects", binary, backend):
        directory.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/restore-tf-state.py", repo / "scripts/restore-tf-state.py")
    executable(repo / "scripts/terraform-env.sh", WRAPPER)
    executable(binary / "curl", CURL)
    executable(binary / "tofu", TOFU)
    (backend / "upcloud.s3.tfbackend").write_text(
        f'bucket = "{BUCKET}"\nkey = "{PROD_KEY}"\nworkspace_key_prefix = "state/workspaces"\n'
        'region = "fr-par"\nendpoints = { s3 = "https://objects.invalid" }\nuse_lockfile = true\n')
    environment = {"PATH": f"{binary}:{os.environ['PATH']}", "HOME": str(tmp_path), "TMPDIR": str(tmp_path),
                   "PROVIDER": "upcloud", "ENV": "prod", "TF_BACKEND_ROOT": str(backend), "STUB_STORE": str(store),
                   "AWS_ACCESS_KEY_ID": "synthetic-access-key", "AWS_SECRET_ACCESS_KEY": SECRET_KEY,
                   "TF_VAR_state_passphrase": PASSPHRASE}

    def run(*arguments: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(repo / "scripts/restore-tf-state.py"), *arguments], env=environment | overrides,
                              text=True, capture_output=True, timeout=30, check=False)

    return store, run


def pushes(store: Path) -> list[dict]:
    log = store / "push.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_listing_shows_only_the_selected_workspace_object(restore):
    store, run = restore
    (store / "listing.xml").write_text(
        '<ListVersionsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Version><Key>{GREEN_KEY}</Key><VersionId>v-green-2</VersionId><IsLatest>true</IsLatest>"
        "<LastModified>2026-11-22T10:00:00Z</LastModified><Size>900</Size></Version>"
        f"<Version><Key>{GREEN_KEY}.tflock</Key><VersionId>v-lock</VersionId><IsLatest>true</IsLatest>"
        "<LastModified>2026-11-22T10:00:00Z</LastModified><Size>10</Size></Version>"
        f"<DeleteMarker><Key>{GREEN_KEY}</Key><VersionId>v-marker</VersionId><IsLatest>false</IsLatest>"
        "<LastModified>2026-11-21T10:00:00Z</LastModified></DeleteMarker>"
        "</ListVersionsResult>")
    result = run(ENV="prod-green")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "v-green-2  2026-11-22T10:00:00Z  size=900  latest=true  state",
        "v-marker  2026-11-21T10:00:00Z  size=-  latest=false  delete-marker",
    ]
    request = json.loads((store / "curl.log").read_text().splitlines()[0])
    assert request["argv"][-1].startswith(f"https://objects.invalid/{BUCKET}?versions=&prefix=state%2Fworkspaces%2Fprod-green%2F")
    assert SECRET_KEY not in json.dumps(request["argv"]) and SECRET_KEY in request["stdin"]


def test_listing_follows_truncated_pages_without_the_passphrase(restore):
    store, run = restore
    pages = store / "listing.xml"
    pages.write_text(
        f'<ListVersionsResult><IsTruncated>true</IsTruncated><NextKeyMarker>{PROD_KEY}</NextKeyMarker>'
        "<NextVersionIdMarker>v-1</NextVersionIdMarker>"
        f"<Version><Key>{PROD_KEY}</Key><VersionId>v-1</VersionId><IsLatest>true</IsLatest>"
        "<LastModified>2026-11-22T10:00:00Z</LastModified><Size>9</Size></Version></ListVersionsResult>")
    second = store / "listing-2.xml"
    second.write_text(
        f"<ListVersionsResult><IsTruncated>false</IsTruncated><Version><Key>{PROD_KEY}</Key><VersionId>v-0</VersionId>"
        "<IsLatest>false</IsLatest><LastModified>2026-11-21T10:00:00Z</LastModified><Size>8</Size></Version>"
        "</ListVersionsResult>")
    # The stand-in serves listing.xml; the marker request swaps in the second page.
    (store / "next-page").write_text(str(second))
    result = run(TF_VAR_state_passphrase="")
    assert result.returncode == 0, result.stderr
    assert [line.split()[0] for line in result.stdout.splitlines()] == ["v-1", "v-0"]
    requests = [json.loads(line)["argv"] for line in (store / "curl.log").read_text().splitlines()]
    assert requests[0][0] == "-q"
    assert "&key-marker=state%2Fupcloud%2Fterraform.tfstate&version-id-marker=v-1" in requests[1][-1]


def test_restore_pushes_the_version_as_the_next_serial(restore, tmp_path):
    store, run = restore
    (store / "objects/v-good").write_text(sealed(state(40, resources=3)))
    (store / "current.json").write_text(json.dumps(state(43, resources=0)))
    result = run(STATE_VERSION="v-good")
    assert result.returncode == 0, result.stderr
    [push] = pushes(store)
    assert push["args"] == ["-no-color", "-"] and push["env"] == "prod"
    assert push["state"] == state(44, resources=3)
    assert "serial 44" in result.stdout
    assert f"{BUCKET}/state/upcloud/terraform.tfstate?versionId=v-good" in (store / "curl.log").read_text()
    wrapper = [json.loads(line) for line in (store / "wrapper.log").read_text().splitlines()]
    assert wrapper[0] == ["init", "-input=false", "-no-color", "-reconfigure"]
    assert PASSPHRASE not in (store / "tofu.log").read_text() + json.dumps(wrapper)
    assert not list(tmp_path.glob("state-restore.*"))


def test_restore_into_empty_state_keeps_the_version_serial(restore):
    store, run = restore
    (store / "objects/v-good").write_text(sealed(state(40)))
    result = run("v-good")
    assert result.returncode == 0, result.stderr
    assert pushes(store)[0]["state"] == state(40)


def test_other_lineage_needs_the_explicit_override(restore):
    store, run = restore
    (store / "objects/v-other").write_text(sealed(state(5, lineage="lineage-b")))
    (store / "current.json").write_text(json.dumps(state(43)))
    refused = run("v-other")
    assert refused.returncode == 1 and "another lineage" in refused.stderr
    assert pushes(store) == []
    accepted = run("v-other", ALLOW_LINEAGE_CHANGE="1")
    assert accepted.returncode == 0, accepted.stderr
    [push] = pushes(store)
    assert push["args"] == ["-no-color", "-force", "-"]
    assert push["state"] == state(44, lineage="lineage-b")


@pytest.mark.parametrize("stored", [
    json.dumps(state(40)),                                  # plaintext object
    sealed(state(40), passphrase="another-passphrase-000"),  # wrong passphrase
    sealed({"version": 4, "serial": True, "lineage": "lineage-a", "resources": []}),
    "not-json",
], ids=["plaintext", "wrong-passphrase", "invalid-state", "not-json"])
def test_unusable_version_is_refused_before_any_push(restore, stored):
    store, run = restore
    (store / "objects/v-bad").write_text(stored)
    (store / "current.json").write_text(json.dumps(state(43)))
    result = run("v-bad")
    assert result.returncode == 1
    assert pushes(store) == []
    assert PASSPHRASE not in result.stdout + result.stderr


def test_missing_version_and_refused_push_report_failure(restore):
    store, run = restore
    missing = run("v-missing")
    assert missing.returncode == 1 and "NoSuchVersion" in missing.stderr
    (store / "objects/v-good").write_text(sealed(state(40)))
    locked = run("v-good", STUB_PUSH_FAIL="1")
    assert locked.returncode == 1 and "acquiring the state lock" in locked.stderr


@pytest.mark.parametrize(("arguments", "overrides", "message"), [
    (["../v"], {}, "usage"),
    ([], {"ENV": "default"}, "reserved"),
    ([], {"TF_BACKEND_ROOT": "relative"}, "absolute"),
    (["v-good"], {"TF_VAR_state_passphrase": ""}, "missing TF_VAR_state_passphrase"),
    ([], {"AWS_SECRET_ACCESS_KEY": ""}, "missing AWS_SECRET_ACCESS_KEY"),
    ([], {"AWS_SECRET_ACCESS_KEY": 'with"quote'}, "contains quotes"),
    ([], {"TF_BACKEND_ROOT": "/nonexistent-backend-root"}, "missing backend file"),
])
def test_bad_inputs_refuse_before_object_storage(restore, arguments, overrides, message):
    store, run = restore
    result = run(*arguments, **overrides)
    assert result.returncode == 2 and message in result.stderr
    assert not (store / "curl.log").exists()


ENCRYPTION_BLOCK = r'(key_provider "pbkdf2" "state"|method "aes_gcm" "state"|state)\s*\{[^{}]*\}'


def blocks(text: str) -> list[str]:
    import re

    return [" ".join(match.group(0).split()) for match in re.finditer(ENCRYPTION_BLOCK, text)]


@pytest.mark.parametrize("provider", ["hetzner", "scaleway", "upcloud", "vultr"])
def test_state_encryption_is_enforced_and_restore_decrypts_the_same_way(provider):
    """A fallback in state.tf would accept plaintext state; a drift would break restore decryption."""
    import importlib.util

    source = (ROOT / "terraform/providers" / provider / "state.tf").read_text()
    assert "unencrypted" not in source and "fallback" not in source
    assert source.count("enforced = true") == 2
    spec = importlib.util.spec_from_file_location("restore_tf_state", ROOT / "scripts/restore-tf-state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert blocks(module.ENCRYPTED_ROOT) == blocks(source)
