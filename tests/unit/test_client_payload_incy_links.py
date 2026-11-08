"""INCY share links come from the real materializer and refuse what they cannot carry."""
from copy import deepcopy
import json
import stat
import subprocess
from urllib.parse import unquote, urlsplit

import client_payload
import pytest

from test_client_payload_recipient_boundaries import materialization  # noqa: F401
from pathlib import Path

from test_emit_singbox_roundtrip import (
    REPO_ROOT, SCRIPT, _build_env, _make_fleet_pins, _plaintext_emitter, _secrets_as_json,
)

UUID = "abcdef12-3456-4789-8abc-def012345678"
FIXTURE_LINKS = [
    f"vless://{UUID}@198.51.100.10:443?encryption=none&security=reality&type=tcp&sni=cdn.example.com"
    f"&fp=chrome&pbk={'A' * 43}&sid=11223344&flow=xtls-rprx-vision#p0-reality-upcloud-prod",
    f"vless://{UUID}@198.51.100.10:8443?encryption=none&security=tls&type=xhttp&sni=vpn.example.com"
    "&fp=chrome&host=vpn.example.com&path=%2F5f3a9c0e1b7d4a26b8e9c3f1d0a47e62&mode=auto#p1-xhttp-upcloud-prod",
    "hysteria2://laptop:fixture-hysteria-password-laptop-001@198.51.100.10:443"
    "?sni=vpn.example.com&insecure=0&up=200&down=100#p2-hysteria2-upcloud-prod",
]


def _emit(tmp_path, *args):
    env = _build_env(tmp_path, _secrets_as_json(tmp_path))
    return subprocess.run(["bash", str(SCRIPT), "laptop", *args], capture_output=True, text=True,
                          env=env, cwd=str(REPO_ROOT))


def _fixture_payload(tmp_path):
    result = _emit(tmp_path, "--profile-format", "ripdpi")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_cli_writes_exact_links_to_private_file_only(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    output = private / "links.txt"
    result = _emit(tmp_path, "--incy-links", str(output))
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines() == FIXTURE_LINKS
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert result.stdout == f"wrote 3 INCY links (2 vless, 1 hysteria2) to {output}\n"
    for secret in (UUID, "fixture-hysteria-password-laptop-001", "11223344"):
        assert secret not in result.stdout + result.stderr


def test_make_emit_incy_writes_links_from_explicit_plaintext(tmp_path):
    plaintext, env = _plaintext_emitter(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    output = private / "links.txt"
    result = subprocess.run(
        ["make", "--no-print-directory", "emit-incy", "CLIENT=laptop", f"OUTPUT={output}",
         f"SECRETS_FILE={plaintext}", *_make_fleet_pins(env["SOPS_FILE"])],
        env=env, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"wrote 3 INCY links (2 vless, 1 hysteria2) to {output}\n"
    assert output.read_text().splitlines()[2].startswith(
        "hysteria2://laptop:authoritative-plaintext-password@198.51.100.10:443?")
    assert "decrypt" not in Path(env["STUB_LOG"]).read_text()


@pytest.mark.parametrize("goal", [["emit-singbox"], ["emit-incy", "OUTPUT=/private/links.txt"]])
def test_make_emit_targets_keep_per_host_sops_files_free_of_plaintext_input(goal):
    def recipe(*extra):
        result = subprocess.run(["make", "-n", "--no-print-directory", *goal, "CLIENT=laptop", *extra],
                                cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        return result.stdout
    per_host = "SOPS_FILES=/private/a.sops.yaml,/private/b.sops.yaml"
    assert "VPN_SECRETS_FILE=" in recipe("SECRETS_FILE=/private/plain.yaml")
    assert "VPN_SECRETS_FILE=" not in recipe(per_host)
    assert "VPN_SECRETS_FILE=" in recipe(per_host, "SECRETS_FILE=/private/plain.yaml")


def test_make_emit_incy_requires_output():
    result = subprocess.run(["make", "--no-print-directory", "emit-incy", "CLIENT=laptop"],
                            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "usage: make emit-incy" in result.stdout


def test_cli_refuses_existing_output_without_change(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    output = private / "links.txt"
    output.write_text("previous\n")
    output.chmod(0o600)
    result = _emit(tmp_path, "--incy-links", str(output))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "client-payload: incy-output-exists\n"
    assert output.read_text() == "previous\n"


def test_cli_refuses_shared_output_directory(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    result = _emit(tmp_path, "--incy-links", str(shared / "links.txt"))
    assert result.returncode == 2
    assert result.stderr == "client-payload: unsafe-recipient-output\n"
    assert not (shared / "links.txt").exists()


@pytest.mark.parametrize("extra", [
    ["--incy-links", "", ],
    ["--incy-links", "links.txt", "--share-uri"],
    ["--incy-links", "links.txt", "--per-app-bypass", "com.example"],
], ids=["empty-output", "share-uri", "per-app"])
def test_cli_rejects_empty_or_combined_output_options(tmp_path, extra):
    result = _emit(tmp_path, *extra)
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "client-payload: INCY links take no other output option\n"


def test_cli_refuses_missing_output_directory(tmp_path):
    result = _emit(tmp_path, "--incy-links", str(tmp_path / "absent" / "links.txt"))
    assert result.returncode == 2
    assert result.stderr == "client-payload: unsafe-recipient-output\n"


@pytest.mark.parametrize(("mutate", "refusal"), [
    (lambda o: o[1]["transport"].update(mode="stream-up"), "unsupported-incy-xhttp-mode"),
    (lambda o: o[1]["transport"].update(xmux={"maxConcurrency": "1-4"}), "unsupported-incy-field"),
    (lambda o: o[2]["tls"].update(ech={"enabled": True}), "unsupported-incy-field"),
    (lambda o: o[2].update(bbr_profile="standard"), "unsupported-incy-field"),
    (lambda o: o[0].update(multiplex={"enabled": True}), "unsupported-incy-field"),
    (lambda o: o[2].update(obfs={"type": "other", "password": "x"}), "unsupported-incy-field"),
    (lambda o: o[1]["tls"].update(enabled=False), "unsupported-incy-field"),
    (lambda o: o.insert(0, {"type": "snell", "tag": "manual"}), "unsupported-incy-outbound"),
    (lambda o: o.insert(0, {"type": "wireguard", "tag": "awg"}), "unsupported-incy-outbound"),
])
def test_links_refuse_fields_they_cannot_carry(tmp_path, mutate, refusal):
    payload = _fixture_payload(tmp_path)
    mutate(payload["outbounds"])
    with pytest.raises(ValueError, match=f"^{refusal}$"):
        client_payload.incy_links(payload)


def test_links_encode_reserved_components_once(tmp_path):
    payload = _fixture_payload(tmp_path)
    secret, path = "p@ss/w:rd?#&", "/a b?c=d#e"
    payload["outbounds"][1]["transport"]["path"] = path
    payload["outbounds"][2]["password"] = "laptop:" + secret
    p1, hy2 = client_payload.incy_links(deepcopy(payload))[1:]
    assert "p%40ss%2Fw%3Ard%3F%23%26@" in hy2
    assert unquote(urlsplit(hy2).username + ":" + urlsplit(hy2).password) == "laptop:" + secret
    query = dict(part.split("=", 1) for part in urlsplit(p1).query.split("&"))
    assert query["path"] == "%2Fa%20b%3Fc%3Dd%23e"
    assert unquote(query["path"]) == path


def test_alternate_endpoint_keeps_its_own_port_name_and_tag(tmp_path):
    payload = _fixture_payload(tmp_path)
    alternate = deepcopy(payload["outbounds"][1])
    alternate.update(tag="p1-xhttp-upcloud-prod:alternate", server_port=2053)
    alternate["tls"]["server_name"] = alternate["transport"]["host"] = "alt.example.com"
    payload["outbounds"].insert(2, alternate)
    assert client_payload.incy_links(payload)[2] == (
        f"vless://{UUID}@198.51.100.10:2053?encryption=none&security=tls&type=xhttp&sni=alt.example.com"
        "&fp=chrome&host=alt.example.com&path=%2F5f3a9c0e1b7d4a26b8e9c3f1d0a47e62&mode=auto"
        "#p1-xhttp-upcloud-prod%3Aalternate")


def test_hopping_and_salamander_reach_the_link(materialization):  # noqa: F811
    context, _, render = materialization
    context.update(hysteria_port_range="20000-21000", hysteria_hop_interval="2m")
    assert client_payload.incy_links(render("ripdpi")) == [
        "hysteria2://fixture-device:synthetic-password@203.0.113.10:443?sni=owned.example.test&insecure=0"
        "&up=200&down=100&obfs=salamander&obfs-password=synthetic-obfs-first&mport=20000-21000"
        "&mportHopInt=120#p2-hysteria2-upcloud-fixture",
    ]
