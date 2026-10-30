"""Private, exact-device native probe profiles; never print the returned values."""
from __future__ import annotations

import copy
import ipaddress
import re

from awg_client import config as awg_config
from awg_client import export as awg_export
from awg_client import host_context
from awg_device_binding import public_key, resolve_binding
from client_payload import context
from transport_semantics import hysteria_client_bandwidth, xhttp_endpoints, xhttp_tuning


def _text(value):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError("invalid-probe-authority")
    return value


def _client(entries, client):
    selected = [entry for entry in entries if entry.get("name") == client]
    if len(selected) != 1:
        raise ValueError("missing-or-ambiguous-probe-client")
    return selected[0]


def render_profiles(document, cohort, client, host, endpoint, *, include_disabled=False):
    """Return private profiles, reading only public repository cohort defaults.

    ``document`` is the exact preimage for revoke and postimage for issue. The
    endpoint is the admitted node's numeric address, never an ambient lookup.
    Profile IDs are ordinal technical labels and contain no device identity.
    """
    if not isinstance(document, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client):
        raise ValueError("invalid-probe-input")
    endpoint = str(ipaddress.ip_address(endpoint))
    settings = context(cohort)
    toggles = dict(settings.get("vpn", {}))
    if include_disabled:
        xray_present = any(row.get("name") == client for row in document.get("xray", {}).get("clients", []))
        frontend = {**settings.get("nginx_xhttp", {}), **document.get("nginx_xhttp", {})}
        # A retained UUID does not invent an XHTTP endpoint on a P0-only node.
        retained_xhttp = toggles.get("enable_nginx_xhttp", False) or "server_name" in frontend
        toggles.update(enable_xray_reality=xray_present, enable_nginx_xhttp=xray_present and retained_xhttp,
                       enable_hysteria=any(row.get("name") == client for row in document.get("hysteria", {}).get("clients", [])),
                       enable_snell=any(row.get("name") == client for variant in document.get("snell_secrets", {}).get("variants", []) for row in variant.get("users", [])),
                       enable_naive=any(row.get("name") == client for row in document.get("naive_secrets", {}).get("clients", [])),
                       enable_amneziawg=any(row.get("name") == client for instance in document.get("amneziawg_secrets", {}).get("instances", []) for row in instance.get("peers", [])))
    result = []

    def append(engine, config, kind, credential, *, instance=None):
        if len(result) >= 64:
            raise ValueError("excessive-probe-profiles")
        locations = {"xray": (settings.get("xray_config_dir", "/etc/xray") + "/config.json", "xray.service"),
                     "hysteria": (settings.get("hysteria_config_dir", "/etc/hysteria") + "/config.yaml", "hysteria-server.service"),
                     "snell": (settings["snell"]["config_dir"] + "/config.json", "snell.service"),
                     "naive": (settings.get("naive", {}).get("config_dir", "/etc/naive") + "/caddy.json", "caddy-naive.service"),
                     "awg": (settings.get("amneziawg_config_dir", "/etc/amnezia/amneziawg") + "/" + (instance or "") + ".conf",
                             "awg-quick@" + (instance or "") + ".service")}
        filename, unit = locations[engine]
        result.append({"id": f"{engine}-{len(result) + 1}", "engine": engine,
                       "config": config, "witness": {"kind": kind, "credential": credential,
                                                       "instance": instance, "config_path": filename, "unit": unit}})

    xray = document.get("xray", {})
    if toggles.get("enable_xray_reality", True) or toggles.get("enable_nginx_xhttp", True):
        selected = _client(xray.get("clients", []), client)
        identity = _text(selected.get("uuid"))

        def native(stream, *, flow="", mux=False):
            user = {"id": identity, "encryption": "none"}
            if flow:
                user["flow"] = flow
            outbound = {"protocol": "vless", "settings": {"vnext": [
                {"address": endpoint, "port": stream.pop("port"), "users": [user]}]},
                "streamSettings": stream}
            if mux:
                outbound["mux"] = {"enabled": True, "concurrency": 8}
            append("xray", {"log": {"loglevel": "none"}, "outbounds": [outbound]}, "uuid", identity)

        if toggles.get("enable_xray_reality", True):
            flow = toggles.get("xray_flow_mode") or settings.get("p0_reality_flow_mode", "vision")
            shapes = settings["p0_reality_shapes"]
            mask = toggles.get("xray_finalmask", shapes[flow]["finalmask"])
            cohorts = xray.get("cohorts", [])
            members = [entry for entry in cohorts if client in entry["clients"]]
            if include_disabled and cohorts and not members:
                members = cohorts
            if cohorts and not members:
                raise ValueError("missing-probe-cohort-membership")
            if not cohorts:
                members = [{"port": settings.get("xray_port", 443)}]
                fallback = settings.get("xray_fallback_port", 0)
                if fallback and fallback != members[0]["port"]:
                    members.append({"port": fallback})
            for member in members:
                shape = shapes[member.get("flow_mode", flow)]
                stream = {"port": member["port"], "network": "raw", "security": "reality",
                          "realitySettings": {"fingerprint": settings.get("xray_utls_fingerprint", "chrome"),
                                              "serverName": _text(xray["server_names"][0]),
                                              "publicKey": _text(xray["reality_public_key"]),
                                              "shortId": _text(selected.get("short_id"))}}
                if member.get("finalmask", mask):
                    stream["finalmask"] = {"tcp": [{"type": "sudoku", "settings": {}}]}
                native(stream, flow=shape["client_flow"], mux=shape["client_mux"])
        if toggles.get("enable_nginx_xhttp", True):
            for target in xhttp_endpoints(document, settings):
                transport = {"host": target["host"], "path": xray["xhttp_path"],
                             "mode": xray.get("xhttp_mode", "auto")}
                tuning = xhttp_tuning(xray)
                if tuning:
                    transport["xmux"] = tuning
                native({"port": target["port"], "network": "xhttp", "security": "tls",
                        "tlsSettings": {"serverName": target["host"], "allowInsecure": False,
                                        "fingerprint": settings.get("xray_utls_fingerprint", "chrome")},
                        "xhttpSettings": transport})
    if toggles.get("enable_hysteria"):
        authority = document["hysteria"]
        selected = _client(authority.get("clients", []), client)
        ech = authority.get("ech")
        sni = authority.get("server_name") or (ech or {}).get("inner_name") or document.get("nginx_xhttp", {}).get("server_name")
        address = f"[{endpoint}]" if ":" in endpoint else endpoint
        port = settings.get("hysteria_port_range") or settings.get("hysteria_port", 443)
        config = {"server": f"{address}:{port}", "auth": client + ":" + _text(selected.get("password")),
                  "tls": {"sni": _text(sni), "insecure": False}}
        if ech:
            config["tls"]["ech"] = _text(ech["config_list"])
        bandwidth = hysteria_client_bandwidth(authority)
        if bandwidth:
            config["bandwidth"] = {"up": f"{bandwidth['up_mbps']} mbps", "down": f"{bandwidth['down_mbps']} mbps"}
        resource = authority.get("resource_profile", "bandwidth-capped")
        if resource != "bandwidth-capped":
            config["congestion"] = {"type": "bbr", "bbrProfile": resource.removeprefix("bbr-")}
        if authority.get("salamander_enabled"):
            config["obfs"] = {"type": "salamander", "salamander": {"password": _text(authority.get("salamander_password"))}}
        if settings.get("hysteria_port_range"):
            config["transport"] = {"type": "udp", "udp": {"hopInterval": settings.get("hysteria_hop_interval", "30s")}}
        append("hysteria", config, "username", client)
    if toggles.get("enable_snell"):
        retained_ids = {entry["id"] for entry in document["snell_secrets"]["variants"]
                        if any(row.get("name") == client for row in entry.get("users", []))}
        if include_disabled and not retained_ids <= {entry["id"] for entry in settings["snell"]["variants"]}:
            raise ValueError("unresolved-retained-snell-variant")
        for variant in settings["snell"]["variants"]:
            selected = [entry for entry in document["snell_secrets"]["variants"] if entry["id"] == variant["id"]]
            if len(selected) != 1:
                raise ValueError("missing-probe-snell-variant")
            authority = selected[0]
            if include_disabled and not any(row.get("name") == client for row in authority.get("users", [])):
                continue
            selected_user = _client(authority["users"], client)
            for reuse in (False, True):
                outbound = {"type": "snell", "tag": "probe", "server": endpoint, "server_port": variant["listen_port"],
                            "version": variant["client_version"], "psk": _text(authority["psk"]),
                            "userkey": _text(selected_user["userkey"]), "reuse": reuse, "network": "tcp"}
                outbound.update({"obfs_mode": "none"} if variant["client_version"] == 4 else {"mode": variant.get("mode", "default")})
                append("snell", {"log": {"disabled": True}, "outbounds": [outbound], "route": {"final": "probe"}},
                       "userkey", selected_user["userkey"])
    if toggles.get("enable_amneziawg"):
        defaults = host_context(cohort)
        private = _text(document["client_registry"][client]["awg_private_key"])
        retained = [(instance, peer) for instance in document.get("amneziawg_secrets", {}).get("instances", [])
                    for peer in instance.get("peers", []) if peer.get("name") == client]
        if len(retained) != 1 or retained[0][1].get("address_kind", "device") != "device":
            raise ValueError("ambiguous-probe-awg-peer")
        instance, peer = retained[0]
        if public_key(private) != peer["public_key"]:
            raise ValueError("probe-awg-key-mismatch")
        projected = copy.deepcopy(document)
        provider, environment = host.split(":")
        projected["client_registry"][client]["awg_binding"] = {"provider": provider, "environment": environment, "instance": instance["name"]}
        binding = resolve_binding(projected, defaults, client, host)
        block = awg_export(projected, defaults, client, host, binding.instance["name"], endpoint)
        if public_key(private) != binding.peer["public_key"]:
            raise ValueError("probe-awg-key-mismatch")
        append("awg", {"text": awg_config(block).replace("<CLIENT_PRIVATE_KEY>", private),
                       "addresses": block["address"], "dns": block["dns"], "mtu": block["mtu"]},
               "peer", binding.peer["public_key"], instance=binding.instance["name"])
    if toggles.get("enable_naive"):
        authority = document["naive_secrets"]
        selected = _client(authority.get("clients", []), client)
        append("naive", {"address": endpoint, "port": settings.get("naive_bind_port", 443),
                         "server_name": _text(authority.get("server_name")),
                         "username": _text(selected.get("username")), "password": _text(selected.get("password"))},
               "basic", selected["username"] + ":" + selected["password"])
    if not result:
        raise ValueError("no-device-probe-profiles")
    return copy.deepcopy(result)
