"""Node-address lookups go to the encrypted resolver only and fail closed without it."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from doh_fixture import doh_server

ROOT = Path(__file__).resolve().parents[2]


def reversed_labels(address: str) -> str:
    """Reverse-DNS labels by string work, independent of the scripts under test."""
    if ":" not in address:
        return ".".join(reversed(address.split(".")))
    head, _, tail = address.partition("::")
    groups = head.split(":") + ["0"] * (8 - len(head.split(":")) - len(tail.split(":"))) + tail.split(":")
    return ".".join(reversed("".join(group.rjust(4, "0") for group in groups)))


ORIGIN = ("TXT", reversed_labels("192.0.2.7") + ".origin.asn.cymru.com")
ORIGIN6 = ("TXT", reversed_labels("2001:db8::7") + ".origin6.asn.cymru.com")
BLOCK_LIST = ("A", reversed_labels("192.0.2.9") + ".zen.spamhaus.org")
AS_RECORD = ("TXT", "AS64500.asn.cymru.com")
CYMRU = {
    ORIGIN: ['"64500 | 192.0.2.0/24 | XX | fixture | 2026-01-01"'],
    ORIGIN6: ['"64500 64501 | 2001:db8::/48 | XX | fixture | 2026-01-01"'],
    AS_RECORD: ['"64500 | XX | fixture | 2026-01-01 | FIXTURE-NET, XX"'],
}


def closed_resolver() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}/dns-query"


def cleartext_stubs(tmp_path: Path) -> tuple[Path, Path]:
    """`dig` and `whois` on PATH that record any call: a cleartext lookup is a failure."""
    calls = tmp_path / "cleartext-calls"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("dig", "whois"):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{calls}"\n')
        stub.chmod(0o755)
    return bin_dir, calls


def run(command: list[str], doh_url: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    bin_dir, _ = cleartext_stubs(tmp_path) if not (tmp_path / "bin").exists() else (tmp_path / "bin", None)
    return subprocess.run(
        command, capture_output=True, text=True, timeout=20,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "DOH_URL": doh_url, **env},
    )


def lookup(record_type: str, name: str, doh_url: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(ROOT / "scripts/doh-lookup.py"), record_type, name], doh_url, tmp_path)


def test_answers_are_printed_one_per_line_without_txt_quotes(tmp_path):
    records = {("A", "listed.example"): ["127.0.0.2", "127.0.0.4"], **CYMRU}
    with doh_server(records) as url:
        assert lookup("A", "listed.example", url, tmp_path).stdout == "127.0.0.2\n127.0.0.4\n"
        assert lookup("TXT", AS_RECORD[1], url, tmp_path).stdout == "64500 | XX | fixture | 2026-01-01 | FIXTURE-NET, XX\n"
        absent = lookup("A", "absent.example", url, tmp_path)
    assert absent.returncode == 0 and not absent.stdout


def test_txt_strings_are_joined_and_an_existing_query_is_kept(tmp_path):
    queries: list = []
    with doh_server({("TXT", "split.example"): ['"first " "second"'], ("TXT", "bare.example"): ["unquoted"]}, queries) as url:
        assert lookup("TXT", "split.example", url + "?ct=1", tmp_path).stdout == "first second\n"
        assert lookup("TXT", "bare.example", url, tmp_path).stdout == "unquoted\n"
    assert queries == [("TXT", "split.example"), ("TXT", "bare.example")]


def test_a_redirecting_resolver_is_not_followed(tmp_path):
    followed: list = []
    with doh_server({("A", "name.example"): ["192.0.2.1"]}, followed) as target:
        with doh_server({}, redirect_to=target + "?name=name.example&type=A") as url:
            result = lookup("A", "name.example", url, tmp_path)
    assert result.returncode == 1 and not result.stdout and not followed


@pytest.mark.parametrize("doh_url", ["closed", "http://resolver.example/dns-query", "ftp://127.0.0.1/dns-query"])
def test_a_lookup_that_cannot_be_encrypted_does_not_run(tmp_path, doh_url):
    result = lookup("A", "name.example", closed_resolver() if doh_url == "closed" else doh_url, tmp_path)
    assert result.returncode == 1 and not result.stdout
    assert "no cleartext query was sent" in result.stderr


@pytest.mark.parametrize(
    ("address", "expected"),
    [("192.0.2.7", ORIGIN), ("2001:db8::7", ORIGIN6)],
)
def test_asn_probe_queries_only_the_encrypted_resolver(tmp_path, address, expected):
    queries: list = []
    with doh_server(CYMRU, queries) as url:
        result = run(["bash", str(ROOT / "scripts/probe-asn.sh"), address], url, tmp_path)
    assert result.returncode == 0, result.stderr
    prefix = "192.0.2.0/24" if expected == ORIGIN else "2001:db8::/48"
    assert result.stdout == f"{address}\t64500\t{prefix}\tXX\tFIXTURE-NET, XX\n"
    # A numeric address is not resolved: only the origin and AS records are queried.
    assert queries == [expected, AS_RECORD]
    assert not (tmp_path / "cleartext-calls").exists()


@pytest.mark.parametrize("reverse", [False, True])
def test_asn_probe_selects_the_most_specific_prefix_whatever_the_answer_order(tmp_path, reverse):
    origins = ['"64501 | 192.0.0.0/22 | XX | fixture | 2026-01-01"', '"64502 64500 | 192.0.2.0/24 | XX | fixture | 2026-01-01"']
    records = {**CYMRU, ORIGIN: origins[::-1] if reverse else origins}
    with doh_server(records) as url:
        result = run(["bash", str(ROOT / "scripts/probe-asn.sh"), "192.0.2.7"], url, tmp_path)
    assert result.stdout == "192.0.2.7\t64500\t192.0.2.0/24\tXX\tFIXTURE-NET, XX\n", result.stderr


@pytest.mark.parametrize(
    "records",
    [{**CYMRU, ORIGIN: ['"NA | 192.0.2.0/24 | XX | fixture | 2026-01-01"']},
     {**CYMRU, AS_RECORD: ['"64999 | XX | fixture | 2026-01-01 | OTHER-NET, XX"']},
     {ORIGIN: CYMRU[ORIGIN]}],
    ids=["non-numeric-origin", "as-record-for-another-asn", "no-as-record"],
)
def test_asn_probe_refuses_an_unexpected_record(tmp_path, records):
    with doh_server(records) as url:
        result = run(["bash", str(ROOT / "scripts/probe-asn.sh"), "192.0.2.7"], url, tmp_path)
    assert result.returncode == 1 and not result.stdout


def test_asn_probe_fails_closed_without_the_encrypted_resolver(tmp_path):
    result = run(["bash", str(ROOT / "scripts/probe-asn.sh"), "192.0.2.7"], closed_resolver(), tmp_path)
    assert result.returncode == 1 and not result.stdout
    assert not (tmp_path / "cleartext-calls").exists()


@pytest.mark.parametrize(
    ("answer", "status", "text"),
    [(["127.0.0.2"], 1, "Spamhaus zen: listed"), ([], 0, "IP reputation clean")],
)
def test_reputation_check_reads_the_block_list_over_the_encrypted_resolver(tmp_path, answer, status, text):
    queries: list = []
    with doh_server({BLOCK_LIST: answer}, queries) as url:
        result = run(["bash", str(ROOT / "scripts/check-ip-reputation.sh")], url, tmp_path, IP="192.0.2.9", NTFY_TOPIC="")
    assert result.returncode == status, result.stderr
    assert text in result.stdout
    assert queries == [BLOCK_LIST]
    assert not (tmp_path / "cleartext-calls").exists()


@pytest.mark.parametrize("address", ["{payload}", "999.1.1.1"])
def test_reputation_check_refuses_an_address_that_is_not_dotted_ipv4(tmp_path, address):
    marker = tmp_path / "executed"
    payload = f"1.2.3.4');open({str(marker)!r},'w');('"
    netset = tmp_path / "firehol.netset"
    netset.write_text("198.51.100.0/24\n")
    result = run(["bash", str(ROOT / "scripts/check-ip-reputation.sh")], closed_resolver(), tmp_path,
                 IP=address.format(payload=payload), FIREHOL_NETSET_FILE=str(netset), NTFY_TOPIC="")
    assert result.returncode == 2
    assert "dotted IPv4" in result.stderr
    assert not marker.exists()


def test_reputation_check_reads_a_netset_path_as_data(tmp_path):
    # A quote in the operator-supplied path must not reach Python source.
    netset = tmp_path / "it's firehol.netset"
    netset.write_text("# fixture\n192.0.2.0/24\n")
    with doh_server({BLOCK_LIST: []}) as url:
        result = run(["bash", str(ROOT / "scripts/check-ip-reputation.sh")], url, tmp_path,
                     IP="192.0.2.9", FIREHOL_NETSET_FILE=str(netset), NTFY_TOPIC="")
    assert "FireHOL Level 1: listed" in result.stdout, result.stderr


def test_reputation_check_fails_closed_without_the_encrypted_resolver(tmp_path):
    result = run(["bash", str(ROOT / "scripts/check-ip-reputation.sh")], closed_resolver(), tmp_path, IP="192.0.2.9", NTFY_TOPIC="")
    assert result.returncode == 2
    assert "did not run" in result.stderr and "clean" not in result.stdout
    assert not (tmp_path / "cleartext-calls").exists()


def test_reputation_check_is_incomplete_when_the_block_list_refuses_the_resolver(tmp_path):
    with doh_server({BLOCK_LIST: ["127.255.255.254"]}) as url:
        result = run(["bash", str(ROOT / "scripts/check-ip-reputation.sh")], url, tmp_path, IP="192.0.2.9", NTFY_TOPIC="")
    assert result.returncode == 2
    assert "not measured" in result.stderr and "clean" not in result.stdout
