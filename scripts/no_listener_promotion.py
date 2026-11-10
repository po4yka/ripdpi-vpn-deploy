"""SSH promotion for a node whose provider contract publishes no client listener.

A split-hop egress node has no data plane that an external sentinel can probe,
so its SSH baseline promotion relies on the fresh pinned SSH and SFTP checks
the transaction already runs. The deployment controller admits this kind only
for a host whose canonical provider listener contract is the empty list.
"""

from __future__ import annotations

import base64
import binascii
import json

KIND = "no-public-listener"
TARGET_FIELDS = {"inventory_alias", "public_service_address_sha256", "deployable_digest"}
# site.yml defaults Hysteria and AmneziaWG to on, so each transport must be explicitly off.
CLIENT_TRANSPORTS = ("enable_xray_reality", "enable_nginx_xhttp", "enable_hysteria", "enable_amneziawg")
CONTRACT = "terraform_public_listeners_b64"


class Refusal(Exception):
    """Categorical refusal that never includes private input."""


def is_kind(document: object) -> bool:
    return isinstance(document, dict) and document.get("kind") == KIND


def listener_free(host_variables: dict, effective_vpn: dict, shadowing: tuple[dict, ...]) -> bool:
    """True only for an explicit egress-only host whose own inventory row records no provider listener.

    `host_variables` is the host's inventory row; `shadowing` holds every other variable source
    (group-wide inventory vars, operator overrides, deployed secrets) that must not set the contract.
    """
    if (effective_vpn.get("enable_split_hop_egress") is not True
            or any(effective_vpn.get(name) is not False for name in CLIENT_TRANSPORTS)
            or any(CONTRACT in source for source in shadowing)):
        return False
    raw = host_variables.get(CONTRACT)
    if not isinstance(raw, str):
        return False
    try:
        return json.loads(base64.b64decode(raw, validate=True)) == []
    except (binascii.Error, ValueError, UnicodeError):
        return False


def validate(document: object, expected_target: dict) -> dict:
    """Return the document when it is exactly a schema-1 binding to the expected target."""
    if (
        not isinstance(document, dict)
        or document.get("kind") != KIND
        or set(document) != {"schema_version", "kind", "target_identity"}
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or not isinstance(document["target_identity"], dict)
        or set(document["target_identity"]) != TARGET_FIELDS
        or document["target_identity"] != expected_target
    ):
        raise Refusal("no-listener-promotion-refused")
    return document
