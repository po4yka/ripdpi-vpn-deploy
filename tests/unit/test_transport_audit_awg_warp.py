"""Pinned AWG admission and armored WARP repository-key boundaries."""
from pathlib import Path
import re

import pytest
import yaml

from awg_client import export
from awg_device_binding import BindingError
from test_awg_device_binding import document
from transport_semantics import awg_errors


ROOT = Path(__file__).resolve().parents[2]


def instance(source):
    return source["amneziawg_secrets"]["instances"][0]


@pytest.mark.parametrize("s1,s2", [(0, 56), (50, 106), (1224, 1280)])
def test_equal_awg_handshake_sizes_refuse_before_recipient_export(s1, s2):
    source = document()
    instance(source).update(s1=s1, s2=s2)
    errors = awg_errors(source["amneziawg_secrets"])
    assert any("initiation and response sizes must differ" in reason for _, reason in errors)
    with pytest.raises(BindingError, match="invalid-awg-contract"):
        export(source, {}, "device0", "upcloud:fixture", "awg0", "192.0.2.1")


@pytest.mark.parametrize("index,value", [
    (index, value) for index in range(1, 5) for value in range(5) if value != index
])
def test_awg_headers_that_the_pinned_engine_rewrites_refuse(index, value):
    source = document()
    instance(source).update({f"h{i}": 10 + i for i in range(1, 5)})
    instance(source)[f"h{index}"] = value
    assert any(path.endswith(f".h{index}") for path, _ in awg_errors(source["amneziawg_secrets"]))
    with pytest.raises(BindingError, match="invalid-awg-contract"):
        export(source, {}, "device0", "upcloud:fixture", "awg0", "192.0.2.1")


@pytest.mark.parametrize("headers", [
    [1, 2, 3, 4], [5, 6, 7, 8], [1, 12, 3, 14],
    [2**32 - 4, 2**32 - 3, 2**32 - 2, 2**32 - 1],
])
def test_supported_awg_headers_and_distinct_sizes_keep_exact_export_values(headers):
    source = document()
    instance(source).update(s1=0, s2=55, **{f"h{i}": value for i, value in enumerate(headers, 1)})
    assert awg_errors(source["amneziawg_secrets"]) == []
    block = export(source, {}, "device0", "upcloud:fixture", "awg0", "192.0.2.1")
    assert [block[f"h{i}"] for i in range(1, 5)] == headers


def test_effective_awg_headers_still_must_be_distinct():
    source = document()
    instance(source).update(h1=11, h2=11, h3=13, h4=14)
    assert any("headers must be pairwise distinct" in reason
               for _, reason in awg_errors(source["amneziawg_secrets"]))


def test_warp_repository_uses_the_same_pinned_armored_key_for_admission_and_apt():
    tasks = yaml.safe_load((ROOT / "ansible/roles/warp-outbound/tasks/prepare.yml").read_text())
    by_name = {task["name"]: task for task in tasks}
    download = by_name["Install Cloudflare WARP GPG key"]
    verify = by_name["Verify Cloudflare WARP GPG key checksum against the pin"]
    enforce = by_name["Assert GPG key matches pinned sha256"]
    source = by_name["Add Cloudflare WARP apt source"]
    key_path = download["ansible.builtin.get_url"]["dest"]
    assert key_path.endswith(".asc"), "upstream ASCII armor must not be labeled a binary keyring"
    assert verify["ansible.builtin.stat"] == {"path": key_path, "checksum_algorithm": "sha256"}
    signed_by = re.search(r"\[signed-by=([^\]]+)\]", source["ansible.builtin.copy"]["content"])
    assert signed_by and signed_by.group(1) == key_path
    assert "_warp_gpg_stat.stat.checksum == warp_outbound.pubkey_sha256" in enforce["ansible.builtin.assert"]["that"]
    assert tasks.index(download) < tasks.index(verify) < tasks.index(enforce) < tasks.index(source)
    assert all(task["when"] == "warp_outbound.install_warp_cli | default(true)"
               for task in (download, verify, enforce, source))
