"""Bind rotation survivors to current authenticated canonical liveness reports."""
from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import os
import stat
import time
from pathlib import Path

import fleet_inspection
import yaml

LIMIT = 65536


class RotationError(Exception):
    """Categorical errors only; never print private file contents."""


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise RotationError("duplicate-or-invalid-mapping")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_regular(path, *, private=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT
                or (private and (info.st_uid != os.geteuid() or info.st_nlink != 1
                                 or stat.S_IMODE(info.st_mode) != 0o600))):
            raise RotationError("unsafe-file")
        data = bytearray()
        while len(data) <= LIMIT:
            chunk = os.read(descriptor, min(8192, LIMIT + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
        raise RotationError("input-limit")
    finally:
        os.close(descriptor)


def liveness_module():
    spec = importlib.util.spec_from_file_location("fleet_protocol_liveness", Path(__file__).with_name("protocol-liveness.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def healthy_survivors(config_path, nodes, *, excluded=()):
    """Count only complete fresh positive witnesses, never persisted decisions."""
    if not nodes:
        return set()
    live = liveness_module()
    try:
        config = live.validate_config(yaml.load(read_regular(config_path), Loader=UniqueLoader))
        if len(config["sentinels"]) > 100 or config.get("stale_after_seconds", 120) > 300:
            raise RotationError("liveness-scope-or-freshness-refused")
        default_inventory = Path(__file__).resolve().parent.parent / "ansible/inventory/generated.ini"
        inventory = Path(os.environ.get("FLEET_INVENTORY", str(default_inventory)))
        hosts = fleet_inspection.select_hosts(inventory, [node["current"] for node in nodes],
                                             selection_kind="provider-env")
        aliases = {node["inventory_alias"] for node in nodes}
        if [host["name"] for host in hosts] != [node["inventory_alias"] for node in nodes]:
            raise RotationError("liveness-inventory-binding-mismatch")
        if len({host["address"] for host in hosts}) != len(hosts):
            raise RotationError("liveness-distinct-targets-required")
        aliases -= set(excluded)
        witnesses = {alias: [] for alias in aliases}
        addresses = {host["name"]: hashlib.sha256(host["address"].encode()).hexdigest() for host in hosts}
        targets = {}
        for sentinel in config["sentinels"]:
            target = sentinel["target"]
            alias = target["inventory_alias"]
            if alias not in aliases:
                continue
            if target["public_service_address_sha256"] != addresses[alias]:
                raise RotationError("liveness-public-target-mismatch")
            if alias in targets and targets[alias] != target:
                raise RotationError("liveness-generation-mismatch")
            targets[alias] = target
            witnesses[alias].append(sentinel)
    except (fleet_inspection.InspectionError, live.ConfigError, OSError, ValueError, TypeError,
            KeyError, RecursionError, yaml.YAMLError):
        raise RotationError("liveness-configuration-refused") from None
    selected = [sentinel for values in witnesses.values() for sentinel in values]
    if not selected:
        return set()
    raw_reports = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(selected))) as pool:
        futures = [pool.submit(live.pull_report, sentinel, config.get("probe_timeout_seconds", 15),
                               live.remote_probe_deadline(config, sentinel)) for sentinel in selected]
        for future in concurrent.futures.as_completed(futures):
            sentinel_id, raw, error = future.result()
            if not error:
                raw_reports[sentinel_id] = raw
    now = int(time.time())
    positive = set()
    for sentinel in selected:
        raw = raw_reports.get(sentinel["id"])
        if raw is None:
            continue
        report, error = live.validate_report(raw, sentinel, config, now)
        if error or report is None or report["control"]["verdict"] != "ok":
            continue
        if all(profile["verdict"] == "ok" and all(variant["verdict"] == "ok"
               for variant in profile.get("variants") or []) and
               (profile["profile"] != "p2-amneziawg" or all(family["verdict"] == "ok"
               for family in profile["family_results"].values())) for profile in report["profiles"]):
            positive.add(sentinel["id"])
    return {alias for alias, values in witnesses.items()
            if values and all(sentinel["id"] in positive for sentinel in values)}
