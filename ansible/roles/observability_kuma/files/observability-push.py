#!/usr/bin/env python3
"""Fail-closed, credential-isolated Kuma success signals; never log requests."""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib import parse, request

MAX_BODY = 262144
TIMEOUT = 4
ALIAS = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
TOKEN = re.compile(r"[A-Za-z0-9_-]{20,128}\Z")


class Refusal(ValueError):
    """Categorical exception without secrets or upstream response text."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def private_address(value):
    address = ipaddress.ip_address(value)
    if not (address.is_private or address in ipaddress.ip_network("100.64.0.0/10")):
        raise Refusal("destination")
    if address.is_loopback or address.is_unspecified or address.is_link_local or address.is_multicast:
        raise Refusal("destination")
    return address


def validate_config(config):
    if config["kind"] not in {"node", "pipeline", "delivery"} or not ALIAS.fullmatch(config["node_id"]):
        raise Refusal("config")
    origin = parse.urlsplit(config["origin"])
    if origin.scheme != "https" or origin.username or origin.password or origin.path or origin.query or origin.fragment:
        raise Refusal("destination")
    private_address(origin.hostname)
    if origin.port is not None and not 1 <= origin.port <= 65535:
        raise Refusal("destination")
    for name in ("prometheus_origin", "relay_origin"):
        local = parse.urlsplit(config[name])
        if local.scheme != "http" or local.hostname != "127.0.0.1" or local.path or local.query or local.fragment or local.username:
            raise Refusal("local-destination")
    if config["kind"] == "node":
        if not 1 <= len(config["services"]) <= 32 or any(not re.fullmatch(r"[A-Za-z0-9@_.-]+\.service", item) for item in config["services"]):
            raise Refusal("services")
    if config["kind"] == "pipeline":
        if not 1 <= len(config["expected_nodes"]) <= 10 or len(set(config["expected_nodes"])) != len(config["expected_nodes"]) or any(not ALIAS.fullmatch(item) for item in config["expected_nodes"]):
            raise Refusal("expected-nodes")
    return config


def credential(directory, name):
    path = directory / name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BODY:
            raise Refusal("credential")
        return stream.read()


def fetch(url, *, ca=None, bearer=None, method="GET", opener=None, timeout=TIMEOUT):
    headers = {"Accept": "application/json"}
    if method == 'POST':
        headers['Content-Type'] = 'application/json'
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    outbound = request.Request(url, headers=headers, method=method, data=b"{}" if method == "POST" else None)
    if opener is None:
        handlers = [request.ProxyHandler({}), NoRedirect()]
        if ca is not None:
            handlers.append(request.HTTPSHandler(context=ssl.create_default_context(cadata=ca)))
        opener = request.build_opener(*handlers).open
    with opener(outbound, timeout=timeout) as response:
        if response.status != 200 or response.headers.get_content_type() != "application/json":
            raise Refusal("acknowledgement")
        raw = response.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise Refusal("response-size")
    return json.loads(raw)


def fresh(value, now, max_age):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and -5 <= now - value <= max_age


def query(origin, expression, now, fetcher):
    result = fetcher(origin + "/api/v1/query?" + parse.urlencode({"query": expression}))
    if result.get("status") != "success" or result.get("data", {}).get("resultType") != "vector":
        raise Refusal("query")
    values = result["data"]["result"]
    if len(values) != 1 or not fresh(float(values[0]["value"][0]), now, 150) or float(values[0]["value"][1]) != 1:
        raise Refusal("condition")


def conditions(config, credentials, previous, now, fetcher=fetch, runner=subprocess.run):
    kind = config["kind"]
    if kind == "node":
        for unit in config["services"]:
            completed = runner(["/usr/bin/systemctl", "is-active", "--quiet", unit], capture_output=True, timeout=TIMEOUT, check=False)
            if completed.returncode:
                raise Refusal("local-service")
        return None
    relay_auth = credential(credentials, "relay-auth-token").strip()
    if not TOKEN.fullmatch(relay_auth):
        raise Refusal("relay-credential")
    if kind == "delivery":
        started = time.monotonic()
        answer = fetcher(config["relay_origin"] + "/v1/delivery-canary", bearer=relay_auth, method="POST", timeout=35)
        now += time.monotonic() - started
        if answer != {"status": "delivered"}:
            raise Refusal("delivery-canary")
    receipt = fetcher(config["relay_origin"] + "/v1/receipts", bearer=relay_auth)
    if kind == "delivery":
        sequence = receipt.get("edit_sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence <= previous.get("sequence", 0) or not fresh(receipt.get("edit_at"), now, 330) or not fresh(receipt.get("send_at"), now, 26 * 3600):
            raise Refusal("delivery-receipt")
        return sequence
    # The canary timestamp is consumed once: a cached acknowledgement cannot
    # repeatedly prove a functioning rule -> Alertmanager -> relay pipeline.
    stamp = receipt.get("rule_to_relay_at")
    if not fresh(stamp, now, 150) or stamp <= previous.get("sequence", 0):
        raise Refusal("pipeline-receipt")
    origin = config["prometheus_origin"]
    for node in config["expected_nodes"]:
        query(origin, 'min((up{job="node-exporter",node="' + node + '"} == bool 1) * (time() - timestamp(up{job="node-exporter",node="' + node + '"}) < bool 150))', now, fetcher)
    query(origin, 'min((up{job="observability-alertmanager"} == bool 1) * (time() - timestamp(up{job="observability-alertmanager"}) < bool 150))', now, fetcher)
    rules = fetcher(origin + "/api/v1/rules")
    groups = rules.get("data", {}).get("groups", [])
    if rules.get("status") != "success" or not groups:
        raise Refusal("rule-evaluation")
    for group in groups:
        evaluated = dt.datetime.fromisoformat(group["lastEvaluation"].replace("Z", "+00:00")).timestamp()
        if not fresh(evaluated, now, 150) or not group.get("rules") or any(rule.get("health") != "ok" or rule.get("lastError") for rule in group["rules"]):
            raise Refusal("rule-evaluation")
    return stamp


def atomic_write(path, content, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix=".push-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(config, credentials, state_path, now=None, fetcher=fetch, runner=subprocess.run):
    now = time.time() if now is None else now
    validate_config(config)
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    sequence = conditions(config, credentials, previous, now, fetcher, runner)
    token = credential(credentials, "push-token").strip()
    if not TOKEN.fullmatch(token):
        raise Refusal("push-credential")
    ca = credential(credentials, "observer-ca")
    answer = fetcher(config["origin"] + "/api/push/" + token, ca=ca)
    if not isinstance(answer, dict) or set(answer) != {"ok"} or answer['ok'] is not True:
        raise Refusal("acknowledgement")
    state = {"last_success": now, "sequence": sequence or 0}
    atomic_write(state_path, json.dumps(state) + "\n")
    return state


def main():
    # Only a non-secret kind appears on argv. systemd serializes each unit.
    kind = sys.argv[1] if len(sys.argv) == 2 else ""
    if kind not in {"node", "pipeline", "delivery"}:
        return 1
    state_path = Path("/var/lib/observability-push") / (kind + ".json")
    config = None
    success = False
    try:
        credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
        config = validate_config(json.loads(credential(credentials, "config")))
        if config["kind"] != kind:
            raise Refusal("kind")
        run(config, credentials, state_path)
        success = True
    except Exception:
        # urllib exceptions and parse errors can contain the entire bearer URL.
        print("observability-push: condition or transport failed", file=sys.stderr)
    try:
        if config is not None:
            previous = json.loads(state_path.read_text()) if state_path.exists() else {}
            output = Path(config["textfile_dir"]) / ("observability-push-" + kind + ".prom")
            atomic_write(output, 'observability_push_success{kind="' + kind + '"} ' + str(int(success)) + '\nobservability_push_last_success_timestamp_seconds{kind="' + kind + '"} ' + str(previous.get("last_success", 0)) + "\n", 0o644)
    except Exception:
        return 1
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
