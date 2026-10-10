from pathlib import Path
import pytest
from vpnd.config import Context
from vpnd.state import Registry, Host, ipv4_limit
from vpnd.state.version import warn_on_skew
from vpnd import version
from concurrent.futures import ThreadPoolExecutor
import threading


def fake_ctx(root=Path("/repo"), explain=False):
    return Context(
        root,
        root / "ansible",
        root / "terraform/providers/upcloud",
        "prod",
        "upcloud",
        Path("/config/prod.secrets.sops.yaml"),
        Path("/tmp/vpn-prod.secrets.yaml"),
        Path("/config"),
        explain,
        True,
    )


# Rust test: vpnd/src/state/registry.rs::resolve_for_rejects_unknown_alias
def test_resolve_for_rejects_unknown_alias():
    reg = Registry()
    reg.upsert("prod1", Host("prod", "upcloud", "203.0.113.5"))
    with pytest.raises(ValueError, match="not in registry"):
        reg.resolve_for("ghost", "prod", "upcloud")


# Rust test: vpnd/src/state/registry.rs::resolve_for_rejects_env_or_provider_mismatch
def test_resolve_for_rejects_env_or_provider_mismatch():
    reg = Registry()
    reg.upsert("box", Host("staging", "hetzner"))
    for env, provider in (("prod", "hetzner"), ("staging", "vultr")):
        with pytest.raises(ValueError):
            reg.resolve_for("box", env, provider)
    assert reg.resolve_for("box", "staging", "hetzner")


# Rust test: vpnd/src/state/registry.rs::ipv4_limit_rejection_table
def test_ipv4_limit_rejection_table():
    for bad in ("all", "prod:*", "999.1.1.1", "", "203.0.113.5x", "prod:!tag"):
        with pytest.raises(ValueError):
            ipv4_limit("bad-host", Host("prod", "upcloud", bad))


# Rust test: vpnd/src/state/registry.rs::ipv4_limit_rejects_zero_padded_octets
def test_ipv4_limit_rejects_zero_padded_octets():
    with pytest.raises(ValueError):
        ipv4_limit("padded", Host("prod", "upcloud", "203.000.113.005"))


# Rust test: vpnd/src/state/registry.rs::ipv4_limit_accepts_literal
def test_ipv4_limit_accepts_literal():
    assert ipv4_limit("ok", Host("prod", "upcloud", "203.0.113.5")) == "203.0.113.5"


# Rust test: vpnd/src/state/registry.rs::ipv4_limit_requires_an_address
def test_ipv4_limit_requires_an_address():
    with pytest.raises(ValueError, match="no IPv4 limit address"):
        ipv4_limit("noip", Host("prod", "upcloud"))


# Rust test: vpnd/src/state/version.rs::warn_on_skew_is_silent_when_versions_match
def test_warn_on_skew_is_silent_when_versions_match(capsys):
    warn_on_skew("myhost", Host("prod", "upcloud", deployed_with=version()))
    assert not capsys.readouterr().err


# Rust test: vpnd/src/state/version.rs::warn_on_skew_does_not_panic_on_mismatch
def test_warn_on_skew_does_not_panic_on_mismatch(capsys):
    warn_on_skew("myhost", Host("prod", "upcloud", deployed_with="0.0.0-old"))
    assert "0.0.0-old" in capsys.readouterr().err


# Rust test: vpnd/src/state/version.rs::warn_on_skew_is_silent_when_deployed_with_absent
def test_warn_on_skew_is_silent_when_deployed_with_absent(capsys):
    warn_on_skew("myhost", Host("prod", "upcloud"))
    assert not capsys.readouterr().err


# Rust test: vpnd/tests/registry_roundtrip.rs::production_registry_io_roundtrip_and_fail_closed_errors
def test_production_registry_io_roundtrip_and_fail_closed_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(Registry, "path", staticmethod(lambda: tmp_path / "config/hosts.toml"))
    path = Registry.path()
    assert path.is_relative_to(tmp_path)
    assert not Registry.load().hosts
    host = Host("staging", "upcloud", "192.0.2.1", "2001:db8::1", "1.3.0")
    registry = Registry()
    for name in ("zeta", "alpha", "middle"):
        registry.upsert(name, host)
    registry.save()
    assert path.is_file()
    loaded = Registry.load()
    assert list(loaded.hosts) == ["alpha", "middle", "zeta"]
    assert loaded.get("alpha") == host
    loaded.upsert("alpha", Host("prod", "vultr"))
    removed = loaded.remove("middle")
    missing = loaded.remove("missing")
    assert removed is not None and missing is None
    loaded.save()
    loaded = Registry.load()
    assert (
        len(loaded.hosts) == 2
        and loaded.get("alpha").env == "prod"
        and loaded.get("alpha").ipv4 is None
    )
    Registry().save()
    assert not Registry.load().hosts
    path.write_text("invalid toml")
    with pytest.raises(ValueError):
        Registry.load()
    path.unlink()
    path.mkdir()
    with pytest.raises(OSError):
        Registry.load()
    with pytest.raises(OSError):
        registry.save()
    path.rmdir()
    running = threading.Event()
    running.set()

    def reader():
        count = 0
        while running.is_set():
            Registry.load()
            count += 1
        return count

    def writer(worker):
        for round in range(25):
            Registry({"worker": Host(f"env-{worker}-{round}", "upcloud")}).save()

    with ThreadPoolExecutor(max_workers=5) as pool:
        reading = pool.submit(reader)
        try:
            list(pool.map(writer, range(4)))
        finally:
            running.clear()
        assert reading.result() > 0
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(Registry.load().hosts) == 1
    assert not [p for p in path.parent.iterdir() if ".tmp." in p.name or p.name.endswith(".tmp")]
