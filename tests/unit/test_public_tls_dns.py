"""Controller DNS admission, with only the public resolver boundary replaced."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("tls_dns", ROOT / "scripts/wait-public-tls-dns.py")
dns = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dns)
AUTHORITY = {"domains": ["site.example", "www.site.example"], "canonical_domain": "site.example",
             "ipv4": "8.8.8.8", "ipv6": "2606:4700:4700::1111"}


def answer(name="site.example", family=1, address="8.8.8.8", alias=False):
    rows = [{"name": name + ".", "type": 5, "data": "site.example."}] if alias else []
    if address:
        rows.append({"name": ("site.example" if alias else name) + ".", "type": family, "data": address})
    return {"Status": 0, "TC": False, "Question": [{"name": name + ".", "type": family}], "Answer": rows}


@pytest.fixture
def clock(monkeypatch):
    value = SimpleNamespace(now=0)
    monkeypatch.setattr(dns, "time", SimpleNamespace(
        monotonic=lambda: value.now,
        sleep=lambda seconds: setattr(value, "now", value.now + seconds),
    ))
    return value


@pytest.mark.parametrize("ipv6", [None, "2606:4700:4700::1111"])
def test_all_domains_and_resolver_views_must_match_three_times(monkeypatch, clock, ipv6):
    authority = {**AUTHORITY, "ipv6": ipv6}
    calls = []

    def query(resolver, name, family, timeout):
        calls.append((resolver, name, family, timeout))
        return answer(name, family, "8.8.8.8" if family == 1 else ipv6, name.startswith("www."))

    monkeypatch.setattr(dns, "query", query)
    result = dns.wait(authority)
    assert result == {"dns_ready": True, "resolver_views": 2, "stable_samples": 3}
    assert len(calls) == 24
    assert {row[:3] for row in calls} == {
        (resolver, name, family) for resolver in dns.RESOLVERS for name in AUTHORITY["domains"] for family in (1, 28)
    }
    assert all(0 < row[3] <= 5 for row in calls)
    assert clock.now == 10


def test_stale_ipv6_in_one_view_resets_the_stability_window(monkeypatch, clock):
    calls = []

    def query(resolver, name, family, timeout):
        calls.append((resolver, name, family))
        address = "8.8.8.8" if family == 1 else "2606:4700:4700::1111"
        if clock.now == 10 and resolver == dns.RESOLVERS[1] and name.startswith("www.") and family == 28:
            address = "2606:4700:4700::1001"
        return answer(name, family, address, name.startswith("www."))

    monkeypatch.setattr(dns, "query", query)
    assert dns.wait(AUTHORITY)["dns_ready"] is True
    assert len(calls) == 48
    assert clock.now == 25


@pytest.mark.parametrize("resolver,name,family", [
    (resolver, name, family) for resolver in range(2) for name in AUTHORITY["domains"] for family in (1, 28)
])
def test_a_single_failed_view_never_admits_issuance(monkeypatch, clock, resolver, name, family):
    def query(view, query_name, query_family, timeout):
        result = answer(query_name, query_family,
                        "8.8.8.8" if query_family == 1 else "2606:4700:4700::1111", query_name.startswith("www."))
        if (view, query_name, query_family) == (dns.RESOLVERS[resolver], name, family):
            result["Status"] = 3
        return result

    monkeypatch.setattr(dns, "query", query)
    with pytest.raises(dns.Refusal, match="did not converge"):
        dns.wait(AUTHORITY)
    assert clock.now == 600


@pytest.mark.parametrize("error", [TimeoutError, OSError, ValueError])
def test_resolver_errors_remain_bounded(monkeypatch, clock, error):
    def fail(*args):
        raise error("external resolver unavailable")
    monkeypatch.setattr(dns, "query", fail)
    with pytest.raises(dns.Refusal, match="did not converge"):
        dns.wait(AUTHORITY)
    assert clock.now == 600


def test_dns_child_interruption_is_not_converted_to_success(monkeypatch, clock):
    def cancel(*args):
        raise KeyboardInterrupt
    monkeypatch.setattr(dns, "query", cancel)
    with pytest.raises(KeyboardInterrupt):
        dns.wait(AUTHORITY)


@pytest.mark.parametrize("mutation", [
    {"Status": 3}, {"Status": 2}, {"Status": False}, {"TC": True}, {"TC": "false"},
    {"Question": []}, {"Question": [{"name": "other.example", "type": 1}]},
    {"Question": [{"name": "site.example", "type": 28}]}, {"Answer": None},
    {"Answer": [{"name": "other.example", "type": 1, "data": "8.8.8.8"}]},
    {"Answer": [{"name": "site.example", "type": 28, "data": "2606:4700:4700::1111"}]},
    {"Answer": [{"name": "site.example", "type": 1, "data": "not-an-address"}]},
    {"Answer": [{"name": "site.example", "type": True, "data": "8.8.8.8"}]},
])
def test_malformed_or_unrelated_answers_refuse(mutation):
    with pytest.raises(ValueError):
        dns.addresses({**answer(), **mutation}, "site.example", 1, "site.example")


@pytest.mark.parametrize("rows", [
    [{"name": "www.site.example", "type": 5, "data": "foreign.example"}],
    [{"name": "www.site.example", "type": 5, "data": "www.site.example"}],
    [{"name": "site.example", "type": 5, "data": "site.example"}],
    [{"name": "www.site.example", "type": 5, "data": "site.example"}] * 2,
    [{"name": "www.site.example", "type": 5, "data": "site.example"},
     {"name": "site.example", "type": 5, "data": "www.site.example"}],
])
def test_cname_authority_is_only_one_auxiliary_name_to_the_canonical_host(rows):
    result = answer("www.site.example", alias=True)
    result["Answer"] = rows + result["Answer"][1:]
    with pytest.raises(dns.Refusal):
        dns.addresses(result, "www.site.example", 1, "site.example")


def test_dnssec_metadata_does_not_add_address_authority():
    result = answer()
    result["Answer"].append({"name": "site.example", "type": 46, "data": "signed metadata"})
    assert dns.addresses(result, "site.example", 1, "site.example") == frozenset({"8.8.8.8"})


@pytest.mark.parametrize("key,value", [
    ("domains", []), ("domains", ["site.example"] * 2), ("domains", ["site.example", "SITE.EXAMPLE"]),
    ("domains", ["site.example"] * 17), ("domains", ["site.example", "bad..example"]),
    ("canonical_domain", "foreign.example"), ("ipv4", None), ("ipv4", "192.0.2.1"),
    ("ipv4", "100.64.0.1"), ("ipv4", "127.0.0.1"), ("ipv4", "224.0.0.1"),
    ("ipv4", "2606:4700:4700::1111"), ("ipv6", ""), ("ipv6", "fe80::1"),
    ("ipv6", "::ffff:808:808"), ("ipv6", "2606:4700:4700:0:0:0:0:1111"),
    ("ipv6", "2606:4700:4700::1111%eth0"), ("ipv6", "fec0::1"),
])
def test_invalid_authority_refuses_before_network(monkeypatch, key, value):
    def unexpected(*args):
        pytest.fail("invalid authority reached the network")
    monkeypatch.setattr(dns, "query", unexpected)
    with pytest.raises(ValueError):
        dns.wait({**AUTHORITY, key: value})


@pytest.mark.parametrize("addresses", [[], ["8.8.8.8", "8.8.4.4"]])
def test_missing_and_extra_addresses_do_not_match_the_expected_set(addresses):
    result = answer()
    result["Answer"] = [{"name": "site.example", "type": 1, "data": value} for value in addresses]
    assert dns.addresses(result, "site.example", 1, "site.example") != frozenset({"8.8.8.8"})


@pytest.mark.parametrize("kind", ["normal", "redirect", "oversized", "duplicate"])
def test_public_dns_transport_is_bounded_and_has_no_operator_proxy(monkeypatch, kind):
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def geturl(self):
            return "https://foreign.example/" if kind == "redirect" else observed["url"]

        def read(self, limit):
            assert limit == 65537
            if kind == "oversized":
                return b"x" * 65537
            if kind == "duplicate":
                return b'{"Status":3,"Status":0}'
            return json.dumps(answer()).encode()

    class Opener:
        def open(self, request, timeout):
            observed.update(url=request.full_url, timeout=timeout, accept=request.get_header("Accept"))
            if kind == "redirect":
                response = SimpleNamespace(close=lambda: observed.update(redirect_closed=True))
                observed["redirect_handler"].redirect_request(request, response, 302, "Found", {}, "https://foreign.example/")
            return Response()

    def build(proxy_handler, redirect_handler):
        observed["proxies"] = proxy_handler.proxies
        observed["redirect_handler"] = redirect_handler
        return Opener()

    monkeypatch.setattr(dns.urllib.request, "build_opener", build)
    if kind == "normal":
        assert dns.query("https://dns.google/resolve", "site.example", 1, 3) == answer()
        assert isinstance(observed.pop("redirect_handler"), dns.RefuseRedirects)
        assert observed == {"proxies": {}, "timeout": 3, "accept": "application/dns-json",
                            "url": "https://dns.google/resolve?name=site.example&type=1&do=false&cd=false&edns_client_subnet=0.0.0.0%2F0"}
    else:
        with pytest.raises(dns.Refusal):
            dns.query("https://dns.google/resolve", "site.example", 1, 3)
        if kind == "redirect":
            assert observed["redirect_closed"] is True


def test_cli_rejects_duplicate_authority_fields_without_network(monkeypatch, capsys):
    monkeypatch.setattr(dns.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b'{"domains":[],"domains":[]}')))
    assert dns.main() == 1
    assert "duplicate" in capsys.readouterr().err


def test_dns_admission_stays_between_http_publication_and_certificate_issuance():
    tasks = yaml.safe_load((ROOT / "ansible/roles/nginx-xhttp/tasks/tls-bootstrap.yml").read_text())
    prepare, gate, issue, prediction = tasks
    assert "--prepare" in prepare["ansible.builtin.command"]["argv"]
    assert "--issue" in issue["ansible.builtin.command"]["argv"]
    assert gate["delegate_to"] == "localhost" and gate["become"] is False
    assert gate["changed_when"] is False and gate["when"] == "not ansible_check_mode"
    command = gate["ansible.builtin.command"]
    assert command["argv"] == ["python3", "{{ role_path }}/../../../scripts/wait-public-tls-dns.py"]
    assert "vpn_service_address" in command["stdin"] and "server_ipv6" in command["stdin"]
    assert "ansible_host" not in command["stdin"]
    assert prediction["when"] == "ansible_check_mode"
