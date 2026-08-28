"""Pure, named-client sentinel profiles. No filesystem, decryption, or transport IO.

The caller owns canonical emitter inputs, resolved host variables and endpoint,
private-file publication, runtime parser gates, and the stdin-only key callback.
Only ``files`` contains private runtime material; public evidence is constructed
from an allowlist before hashing and never includes key-derived fingerprints.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import ipaddress
import json
from pathlib import PurePosixPath
import re
import uuid

PROFILES = {"p0-reality", "p1-xhttp", "p2-hysteria2", "p2-amneziawg"}
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
PARAM_DEFAULTS = {"jc": 4, "jmin": 40, "jmax": 70, "s1": 50, "s2": 100}


class ProfileError(ValueError):
    """Categorical error only: never include input values or key callback errors."""


def _text(value):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ProfileError("invalid-string")
    return value


def _host(value):
    value = _text(value)
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value):
            raise ProfileError("invalid-endpoint") from None
        return value


def _port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ProfileError("invalid-port")
    return value


def _key(value):
    try:
        decoded = base64.b64decode(value, validate=True) if isinstance(value, str) else b""
        if len(decoded) != 32 or base64.b64encode(decoded).decode() != value:
            raise ValueError
    except (ValueError, TypeError):
        raise ProfileError("invalid-awg-key") from None
    return value


def _derive(callback, private):
    try:
        return _key(callback(_key(private)))
    except Exception:
        raise ProfileError("awg-key-derivation") from None


def _client(entries, name, unique_fields):
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
        raise ProfileError("invalid-clients")
    for field in ("name", *unique_fields):
        values = [_text(entry.get(field)) for entry in entries]
        try:
            if field == "allowed_ips":
                values = [str(ipaddress.ip_network(value, strict=False)) for value in values]
            elif field == "uuid":
                values = [str(uuid.UUID(value)) for value in values]
            elif field == "short_id":
                if any(not re.fullmatch(r"(?:[0-9a-fA-F]{2}){1,8}", value) for value in values):
                    raise ValueError
                values = [value.lower() for value in values]
        except ValueError:
            raise ProfileError("invalid-client-identity") from None
        if len(values) != len(set(values)):
            raise ProfileError("duplicate-client-identity")
    matches = [entry for entry in entries if entry["name"] == name]
    if len(matches) != 1:
        raise ProfileError("client-missing")
    return matches[0]


def _outbounds(document, profile):
    entries = document.get("outbounds") if isinstance(document, dict) else None
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
        raise ProfileError("invalid-emitter-output")
    tags = [_text(e.get("tag")) for e in entries]
    if len(tags) != len(set(tags)):
        raise ProfileError("duplicate-outbound-tag")
    selected = [e for e in entries if e["tag"].startswith(profile + "-")]
    if not 1 <= len(selected) <= 16:
        raise ProfileError("missing-or-excessive-profile-variants")
    return selected


def _tls(outbound, reality=False):
    tls = outbound.get("tls")
    if (not isinstance(tls, dict) or tls.get("enabled") is not True or tls.get("insecure", False) is not False
            or set(tls) - {"enabled", "server_name", "insecure", "utls", "reality"}):
        raise ProfileError("invalid-profile-tls")
    result = {"server_name": _host(tls.get("server_name")), "enabled": True}
    if "utls" in tls:
        utls = tls["utls"]
        if (not isinstance(utls, dict) or utls.get("enabled") is not True
                or set(utls) != {"enabled", "fingerprint"} or not NAME.fullmatch(_text(utls.get("fingerprint")))):
            raise ProfileError("invalid-profile-tls")
        result["fingerprint"] = utls["fingerprint"]
    if not reality and "reality" in tls:
        raise ProfileError("invalid-profile-tls")
    return result


def _hysteria_options(outbound, secrets):
    public = {}
    if secrets.get("salamander_enabled", False):
        expected = {"type": "salamander", "password": _text(secrets.get("salamander_password"))}
        if outbound.get("obfs") != expected:
            raise ProfileError("wrong-hysteria-obfs")
        public["obfs"] = "salamander"
    elif "obfs" in outbound:
        raise ProfileError("unexpected-hysteria-obfs")
    if "server_ports" in outbound or "hop_interval" in outbound:
        ranges, interval = outbound.get("server_ports"), outbound.get("hop_interval")
        if (not isinstance(ranges, list) or not 1 <= len(ranges) <= 16
                or not isinstance(interval, str) or not re.fullmatch(r"[1-9][0-9]*(?:ms|s|m|h)", interval)):
            raise ProfileError("invalid-hysteria-hopping")
        for port_range in ranges:
            if not isinstance(port_range, str) or not re.fullmatch(r"[0-9]+:[0-9]+", port_range):
                raise ProfileError("invalid-hysteria-hopping")
            low, high = map(int, port_range.split(":"))
            if not 1 <= low <= high <= 65535:
                raise ProfileError("invalid-hysteria-hopping")
        public.update(server_ports=list(ranges), hop_interval=interval)
    return public


def _selected_awg(secrets, binding, defaults, cohort):
    if (not isinstance(binding, dict) or set(binding) != {"provider", "environment", "instance"}
            or any(not isinstance(v, str) or not NAME.fullmatch(v) for v in binding.values())
            or binding["provider"] not in {"upcloud", "vultr", "scaleway", "hetzner"}):
        raise ProfileError("awg-binding")
    raw = secrets.get("amneziawg_secrets")
    if not isinstance(raw, dict) or not isinstance(defaults, dict) or not isinstance(cohort, dict):
        raise ProfileError("invalid-awg-config")
    instances = raw.get("instances", [])
    if not isinstance(instances, list) or any(not isinstance(i, dict) for i in instances):
        raise ProfileError("invalid-awg-instances")
    names = [i.get("name") for i in instances]
    if any(not isinstance(n, str) or not NAME.fullmatch(n) for n in names) or len(names) != len(set(names)):
        raise ProfileError("duplicate-or-invalid-awg-instance")
    # Match the server's guard across all sources, not merely the selected one.
    for source in (raw, cohort, *instances):
        if (any(type(source.get(p, 0)) is not int or source.get(p, 0) != 0 for p in ("s3", "s4"))
                or any(p in source for p in ("i1", "i2", "i3", "i4", "i5"))):
            raise ProfileError("awg-parameters-unsupported")
    if instances:
        matches = [i for i in instances if i["name"] == binding["instance"]]
        if len(matches) != 1:
            raise ProfileError("awg-binding")
        chosen = matches[0]
        effective = {**PARAM_DEFAULTS, **chosen}
    else:
        if binding["instance"] != defaults.get("interface", "awg0"):
            raise ProfileError("awg-binding")
        chosen = raw
        effective = {**PARAM_DEFAULTS, **cohort, **raw}
    # Single-instance network fields come from role variables, unlike the old
    # emit-awg helper's top-level secret listen_port fallback.
    network = chosen if instances else defaults
    return effective, network.get("listen_port", defaults.get("listen_port", 51820)), network.get(
        "address_v4", defaults.get("address_v4", "10.66.66.1/24"))


def _awg(secrets, client, binding, endpoint, private_key, derive, defaults, cohort):
    chosen, port, address = _selected_awg(secrets, binding, defaults, cohort)
    peer = _client(chosen.get("peers"), client, ("public_key", "preshared_key", "allowed_ips"))
    try:
        server = ipaddress.IPv4Interface(address)
        assigned = ipaddress.IPv4Interface(peer["allowed_ips"])
        if (assigned.network.prefixlen != 32 or assigned.ip not in server.network
                or assigned.ip in (server.ip, server.network.network_address, server.network.broadcast_address)):
            raise ValueError
    except (ValueError, TypeError):
        raise ProfileError("awg-address") from None
    parameters = {}
    for name in (*PARAM_DEFAULTS, "h1", "h2", "h3", "h4"):
        value = chosen.get(name)
        maximum = 128 if name == "jc" else (2**32 - 1 if name.startswith("h") else 1280)
        if type(value) is not int or not 0 <= value <= maximum:
            raise ProfileError("awg-parameters-invalid")
        parameters[name] = value
    if parameters["jmin"] > parameters["jmax"] or len({parameters[f"h{i}"] for i in range(1, 5)}) != 4:
        raise ProfileError("awg-parameters-invalid")
    if _derive(derive, private_key) != _key(peer.get("public_key")):
        raise ProfileError("awg-key-mismatch")
    server_public = _derive(derive, chosen.get("server_private_key"))
    endpoint = _host(endpoint)
    port = _port(port)
    endpoint_text = f"[{endpoint}]" if ":" in endpoint else endpoint
    fields = ["[Interface]", f"PrivateKey = {_key(private_key)}", f"Address = {assigned}", "MTU = 1420"]
    fields += [f"{name.capitalize()} = {value}" for name, value in parameters.items()]
    fields += ["", "[Peer]", f"PublicKey = {server_public}", f"PresharedKey = {_key(peer.get('preshared_key'))}",
               f"Endpoint = {endpoint_text}:{port}", "AllowedIPs = 0.0.0.0/0", "PersistentKeepalive = 25", ""]
    public = {"profile": "p2-amneziawg", "server": endpoint, "port": port, **binding}
    return "\n".join(fields), str(assigned), public


def build_profiles(standard_doc, ripdpi_doc, secrets_doc, client, required_profiles, awg_binding,
                   endpoint, private_key, derive_public_key, generation_root, *, awg_defaults, awg_cohort):
    """Return private ``files``, runner ``runtime`` settings, and public evidence.

    JSON files are returned as dicts; ``awg.conf`` is an INI string. The caller
    must serialize only into its private generation after real parser checks.
    """
    if not isinstance(client, str) or not NAME.fullmatch(client):
        raise ProfileError("invalid-client-name")
    registry = secrets_doc.get("client_registry", {}) if isinstance(secrets_doc, dict) else {}
    enrollment = registry.get(client) if isinstance(registry, dict) else None
    if not isinstance(enrollment, dict) or enrollment.get("status") not in ("issued", "delivered", "active"):
        raise ProfileError("client-not-active")
    if (not isinstance(required_profiles, (list, tuple)) or not required_profiles
            or any(not isinstance(p, str) or p not in PROFILES for p in required_profiles)
            or len(required_profiles) != len(set(required_profiles))):
        raise ProfileError("invalid-required-profiles")
    root = PurePosixPath(_text(generation_root))
    if not root.is_absolute() or ".." in root.parts:
        raise ProfileError("invalid-generation-root")
    needed = set(required_profiles)
    for section, enabled in (("xray", bool(needed & {"p0-reality", "p1-xhttp"})), ("hysteria", "p2-hysteria2" in needed)):
        if enabled and not isinstance(secrets_doc.get(section), dict):
            raise ProfileError("invalid-clients")
    xray_client = _client(secrets_doc.get("xray", {}).get("clients"), client, ("uuid", "short_id")) if needed & {"p0-reality", "p1-xhttp"} else None
    hysteria_client = _client(secrets_doc.get("hysteria", {}).get("clients"), client, ("password",)) if "p2-hysteria2" in needed else None
    if xray_client:
        try:
            uuid.UUID(xray_client["uuid"])
        except ValueError:
            raise ProfileError("invalid-xray-identity") from None
    files, runtime, public = {}, {}, []
    standard = {"log": {"level": "warn"}, "inbounds": [], "outbounds": [], "route": {"rules": []}}
    xray = {"log": {"loglevel": "warning"}, "inbounds": [], "outbounds": [], "routing": {"rules": []}}
    maps = {"sing_box": {}, "xray": {}}
    for profile in ("p0-reality", "p2-hysteria2", "p1-xhttp"):
        if profile not in needed:
            continue
        selected = _outbounds(ripdpi_doc if profile == "p1-xhttp" else standard_doc, profile)
        engine = "xray" if profile == "p1-xhttp" else "sing_box"
        maps[engine][profile] = []
        for index, original in enumerate(selected, 1):
            outbound = copy.deepcopy(original)
            allowed = {"type", "tag", "server", "server_port", "tls"}
            allowed |= {"password", "obfs", "server_ports", "hop_interval"} if profile == "p2-hysteria2" else {"uuid", "flow", "multiplex", "transport"}
            if set(outbound) - allowed:
                raise ProfileError("unsupported-outbound-field")
            server, port = _host(outbound.get("server")), _port(outbound.get("server_port"))
            tls = _tls(outbound, reality=profile == "p0-reality")
            if profile == "p0-reality":
                server_names = secrets_doc["xray"].get("server_names")
                if not isinstance(server_names, list) or not server_names:
                    raise ProfileError("missing-reality-sni")
                expected_sni = server_names[0]
            else:
                frontend = secrets_doc.get("nginx_xhttp")
                if not isinstance(frontend, dict):
                    raise ProfileError("missing-frontend-sni")
                expected_sni = frontend.get("server_name")
                if profile == "p2-hysteria2" and secrets_doc["hysteria"].get("server_name") is not None:
                    expected_sni = secrets_doc["hysteria"]["server_name"]
            if tls["server_name"] != _host(expected_sni):
                raise ProfileError("wrong-server-sni")
            metadata = {"profile": profile, "variant": index, "server": server, "port": port, "tls": tls}
            if profile == "p2-hysteria2":
                if outbound.get("type") != "hysteria2" or outbound.get("password") != client + ":" + hysteria_client["password"]:
                    raise ProfileError("wrong-client-material")
                metadata.update(_hysteria_options(outbound, secrets_doc["hysteria"]))
            else:
                if outbound.get("type") != "vless" or outbound.get("uuid") != xray_client["uuid"]:
                    raise ProfileError("wrong-client-material")
                if profile == "p0-reality":
                    reality = outbound["tls"].get("reality", {})
                    if (reality != {"enabled": True, "public_key": secrets_doc["xray"].get("reality_public_key"),
                                   "short_id": xray_client["short_id"]} or "transport" in outbound):
                        raise ProfileError("wrong-reality-material")
                    if "multiplex" in outbound:
                        if outbound["multiplex"] != {"enabled": True, "protocol": "smux", "max_streams": 8} or "flow" in outbound:
                            raise ProfileError("unsupported-reality-flow")
                        metadata["flow"] = "mux"
                    elif outbound.get("flow") != "xtls-rprx-vision":
                        raise ProfileError("unsupported-reality-flow")
                    else:
                        metadata["flow"] = "vision"
            if engine == "sing_box":
                proxy_port = 18081 + len(standard["inbounds"])
                inbound_tag = f"probe-{profile}-{index}"
                standard["inbounds"].append({"type": "socks", "tag": inbound_tag, "listen": "127.0.0.1", "listen_port": proxy_port})
                standard["outbounds"].append(outbound)
                standard["route"]["rules"].append({"inbound": [inbound_tag], "action": "route", "outbound": outbound["tag"]})
            else:
                transport = outbound.get("transport")
                if (not isinstance(transport, dict) or set(transport) != {"type", "host", "path"}
                        or transport["type"] != "xhttp" or _host(transport["host"]) != tls["server_name"]
                        or not re.fullmatch(r"/[A-Za-z0-9/_~.%+-]*", _text(transport["path"]))
                        or "flow" in outbound or "multiplex" in outbound):
                    raise ProfileError("invalid-xhttp-transport")
                expected_path = secrets_doc["xray"].get("xhttp_path")
                if transport["path"] != (expected_path if expected_path is not None else "/app-sync"):
                    raise ProfileError("wrong-xhttp-path")
                proxy_port = 18181 + len(xray["inbounds"])
                inbound_tag = f"probe-xhttp-{index}"
                xray["inbounds"].append({"listen": "127.0.0.1", "port": proxy_port, "protocol": "socks",
                                         "tag": inbound_tag, "settings": {"udp": False}})
                native = {"protocol": "vless", "tag": outbound["tag"], "settings": {"vnext": [{"address": server, "port": port,
                          "users": [{"id": xray_client["uuid"], "encryption": "none"}]}]},
                          "streamSettings": {"network": "xhttp", "security": "tls", "tlsSettings": {"serverName": tls["server_name"], "allowInsecure": False},
                                             "xhttpSettings": {"host": transport["host"], "path": transport["path"]}}}
                if "fingerprint" in tls:
                    native["streamSettings"]["tlsSettings"]["fingerprint"] = tls["fingerprint"]
                xray["outbounds"].append(native)
                xray["routing"]["rules"].append({"type": "field", "inboundTag": [inbound_tag], "outboundTag": outbound["tag"]})
                metadata["path"] = transport["path"]
            maps[engine][profile].append(proxy_port)
            public.append(metadata)
    for engine, filename, document in (("sing_box", "sing-box.json", standard), ("xray", "xray.json", xray)):
        if maps[engine]:
            files[filename] = document
            runtime[engine] = {"config": str(root / filename), "profiles": maps[engine]}
    if "p2-amneziawg" in needed:
        awg, address, metadata = _awg(secrets_doc, client, awg_binding, endpoint, private_key,
                                     derive_public_key, awg_defaults, awg_cohort)
        files["awg.conf"] = awg
        runtime["amneziawg"] = {"config": str(root / "awg.conf"), "address": address}
        public.append(metadata)
    digest = hashlib.sha256(json.dumps(public, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"files": files, "runtime": runtime, "public_profiles": public, "public_profile_digest": digest}
