#!/usr/bin/env python3
"""Wait for reviewed public TLS addresses before an HTTP-01 CA request."""
import ipaddress
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RESOLVERS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)
TIMEOUT_SECONDS = 600
POLL_SECONDS = 5
STABLE_SAMPLES = 3


class Refusal(ValueError):
    pass


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        if response is not None:
            response.close()
        raise Refusal("DNS resolver redirects are refused")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal("duplicate DNS document field")
        result[key] = value
    return result


def domain(value):
    if not isinstance(value, str):
        raise Refusal("invalid public TLS domain")
    value = value.lower().removesuffix(".")
    if len(value) > 253 or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+", value
    ):
        raise Refusal("invalid public TLS domain")
    return value


def configuration(value):
    if not isinstance(value, dict) or set(value) != {"domains", "canonical_domain", "ipv4", "ipv6"}:
        raise Refusal("invalid public TLS DNS authority")
    names = value["domains"]
    if not isinstance(names, list) or not 1 <= len(names) <= 16:
        raise Refusal("invalid public TLS domains")
    names = [domain(name) for name in names]
    canonical = domain(value["canonical_domain"])
    if len(set(names)) != len(names) or canonical not in names:
        raise Refusal("ambiguous public TLS domains")
    expected = {}
    for family, key, version in ((1, "ipv4", 4), (28, "ipv6", 6)):
        text = value[key]
        if version == 6 and text is None:
            expected[family] = frozenset()
            continue
        if not isinstance(text, str):
            raise Refusal("missing Terraform-owned public address")
        address = ipaddress.ip_address(text)
        if (address.version != version or str(address) != text or not address.is_global
                or "%" in text or getattr(address, "is_site_local", False)
                or address.is_multicast or getattr(address, "ipv4_mapped", None) is not None):
            raise Refusal("invalid Terraform-owned public address")
        expected[family] = frozenset({str(address)})
    return names, canonical, expected


def addresses(document, name, family, canonical):
    if (not isinstance(document, dict) or type(document.get("Status")) is not int
            or document["Status"] != 0 or document.get("TC", False) is not False):
        raise Refusal("DNS response is not complete NOERROR")
    questions = document.get("Question")
    if (not isinstance(questions, list) or len(questions) != 1
            or not isinstance(questions[0], dict) or domain(questions[0].get("name")) != name
            or type(questions[0].get("type")) is not int or questions[0]["type"] != family):
        raise Refusal("DNS question differs from requested authority")
    answers = document.get("Answer", [])
    if not isinstance(answers, list) or len(answers) > 32:
        raise Refusal("invalid DNS answer set")
    records = []
    for row in answers:
        if (not isinstance(row, dict) or type(row.get("type")) is not int
                or not isinstance(row.get("data"), str)):
            raise Refusal("unsupported DNS answer")
        if row["type"] in {46, 47, 50}:  # DNSSEC metadata does not add address authority.
            continue
        if row["type"] not in {family, 5}:
            raise Refusal("unsupported DNS answer")
        records.append((domain(row.get("name")), row["type"], row["data"]))
    aliases = [row for row in records if row[1] == 5]
    terminal = name
    if aliases:
        if (len(aliases) != 1 or name == canonical or aliases[0][0] != name
                or domain(aliases[0][2]) != canonical):
            raise Refusal("unmanaged public TLS CNAME chain")
        terminal = canonical
    result = set()
    for owner, kind, text in records:
        if kind == 5:
            continue
        if owner != terminal:
            raise Refusal("DNS answer has an unrelated owner")
        address = ipaddress.ip_address(text)
        if address.version != (4 if family == 1 else 6):
            raise Refusal("DNS address family differs")
        result.add(str(address))
    return frozenset(result)


def query(resolver, name, family, timeout):
    parameters = {"name": name, "type": family, "do": "false", "cd": "false"}
    if resolver == "https://dns.google/resolve":
        parameters["edns_client_subnet"] = "0.0.0.0/0"
    url = resolver + "?" + urllib.parse.urlencode(parameters)
    request = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
    # These are public observations. Operator API proxies and credentials do not
    # take part in the resolver view used to admit a public CA request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirects())
    with opener.open(request, timeout=timeout) as response:
        if response.geturl() != url:
            raise Refusal("DNS resolver redirected the request")
        raw = response.read(65537)
    if len(raw) > 65536:
        raise Refusal("DNS response exceeds its bound")
    return json.loads(raw, object_pairs_hook=unique)


def wait(value):
    names, canonical, expected = configuration(value)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    stable = 0
    while time.monotonic() < deadline:
        matches = True
        try:
            for resolver in RESOLVERS:
                for name in names:
                    for family in (1, 28):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise Refusal("public TLS DNS deadline expired")
                        answer = query(resolver, name, family, min(5, remaining))
                        if addresses(answer, name, family, canonical) != expected[family]:
                            raise Refusal("public TLS DNS address set differs")
        except (ValueError, OSError, urllib.error.URLError):
            matches = False
        if time.monotonic() >= deadline:
            break
        stable = stable + 1 if matches else 0
        if stable == STABLE_SAMPLES:
            return {"dns_ready": True, "resolver_views": len(RESOLVERS), "stable_samples": stable}
        time.sleep(min(POLL_SECONDS, deadline - time.monotonic()))
    raise Refusal("public TLS DNS did not converge within 600 seconds")


def main():
    try:
        raw = sys.stdin.buffer.read(65537)
        if len(raw) > 65536:
            raise Refusal("public TLS DNS authority exceeds its bound")
        result = wait(json.loads(raw, object_pairs_hook=unique))
    except (ValueError, OSError) as exc:
        print(f"public-tls-dns: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
