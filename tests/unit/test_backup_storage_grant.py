"""Offsite backup credentials must be append-only and scoped to one node."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup-storage-grant.py"
spec = importlib.util.spec_from_file_location("backup_storage_grant", SCRIPT)
grant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grant)

CONFIG = "[offsite]\ntype = b2\naccount = id\nkey = secret\nhard_delete = false\n"
APPEND_ONLY = ["listBuckets", "listFiles", "readFiles", "writeFiles"]


class FakeB2:
    def __init__(self, capabilities, prefix="nodes/node-a/", bucket_type="allPrivate"):
        self.allowed = {
            "capabilities": capabilities,
            "buckets": [{"id": "b1", "name": "backups"}],
            "namePrefix": prefix,
        }
        self.bucket_type = bucket_type

    def open(self, outbound, timeout):
        if outbound.full_url.endswith("b2_authorize_account"):
            body = {
                "accountId": "acct",
                "authorizationToken": "token",
                "apiInfo": {"storageApi": {"apiUrl": "https://api.example.backblazeb2.com", "allowed": self.allowed}},
            }
        else:
            body = {"buckets": [{"bucketName": "backups", "bucketType": self.bucket_type}]}
        return io.BytesIO(json.dumps(body).encode())


def _check(fake, config=CONFIG):
    return grant.check(config, "offsite", "backups/nodes", "node-a", fake)


def test_append_only_node_grant_is_accepted() -> None:
    assert _check(FakeB2(APPEND_ONLY)) == "backup-storage-grant-accepted"


@pytest.mark.parametrize(
    "fake,category",
    [
        (FakeB2(APPEND_ONLY + ["deleteFiles"]), "append-only-grant-required"),
        (FakeB2(APPEND_ONLY, prefix="nodes/"), "node-prefix-grant-required"),
        (FakeB2(APPEND_ONLY, prefix="nodes/node-b/"), "node-prefix-grant-required"),
        (FakeB2(APPEND_ONLY, bucket_type="allPublic"), "private-bucket-required"),
    ],
)
def test_grant_that_can_delete_or_escape_the_node_is_refused(fake, category) -> None:
    with pytest.raises(ValueError, match=category):
        _check(fake)


def test_hard_delete_client_setting_is_refused() -> None:
    with pytest.raises(ValueError, match="hard-delete-configured"):
        _check(FakeB2(APPEND_ONLY), CONFIG.replace("hard_delete = false", "hard_delete = true"))


def test_same_host_local_remote_has_no_grant_to_check() -> None:
    assert _check(None, "[offsite]\ntype = local\n") == "backup-storage-grant-not-applicable"
