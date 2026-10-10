"""Atomic, private, local TOML host registry."""

from dataclasses import asdict, dataclass, field
import ipaddress
import tomllib
import tomli_w
from ..config import config_home
from ..protected_file import write_private


@dataclass
class Host:
    env: str
    provider: str
    ipv4: str | None = None
    ipv6: str | None = None
    deployed_with: str | None = None


@dataclass
class Registry:
    hosts: dict[str, Host] = field(default_factory=dict)

    @staticmethod
    def path():
        return config_home() / "vpn-provision/hosts.toml"

    @classmethod
    def load(cls):
        path = cls.path()
        try:
            raw = path.read_text()
        except FileNotFoundError:
            return cls()
        try:
            rows = tomllib.loads(raw).get("hosts", {})
            if not isinstance(rows, dict):
                raise ValueError("hosts must be a table")
            hosts = {}
            for name, row in sorted(rows.items()):
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("env"), str)
                    or not isinstance(row.get("provider"), str)
                ):
                    raise ValueError("host env/provider required")
                for key in ("ipv4", "ipv6", "deployed_with"):
                    if key in row and not isinstance(row[key], str):
                        raise ValueError("host field must be a string")
                hosts[name] = Host(
                    **{k: v for k, v in row.items() if k in Host.__dataclass_fields__}
                )
            return cls(hosts)
        except (ValueError, TypeError) as error:
            raise ValueError(f"parse {path}") from error

    def save(self):
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "hosts": {
                name: {k: v for k, v in asdict(host).items() if v is not None}
                for name, host in sorted(self.hosts.items())
            }
        }
        write_private(path, tomli_w.dumps(raw).encode())

    def upsert(self, name, host):
        self.hosts[name] = host
        self.hosts = dict(sorted(self.hosts.items()))

    def remove(self, name):
        return self.hosts.pop(name, None)

    def get(self, name):
        return self.hosts.get(name)

    def resolve_for(self, name, env, provider):
        host = self.get(name)
        if host is None:
            raise ValueError(f"host '{name}' not in registry")
        if host.env != env or host.provider != provider:
            raise ValueError(
                f"host '{name}' belongs to {host.env}/{host.provider} not {env}/{provider}"
            )
        return Host(**asdict(host))


def ipv4_limit(name, host):
    if host.ipv4 is None:
        raise ValueError(f"host '{name}' has no IPv4 limit address")
    try:
        return str(ipaddress.IPv4Address(host.ipv4))
    except ipaddress.AddressValueError:
        raise ValueError(
            f"host '{name}' ipv4 '{host.ipv4}' is not an IPv4 literal — refusing to build --limit"
        ) from None
