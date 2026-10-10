"""Read-only minimal typed view of descriptor-gated decrypted YAML."""

from dataclasses import dataclass, field
from .protected_file import open_private
from .yaml_loader import load_yaml


@dataclass(repr=False)
class Client:
    name: str
    uuid: str | None = None
    short_id: str | None = None
    _extra: dict = field(default_factory=dict)

    def __repr__(self):
        return f"Client(name={self.name!r}, ...)"


@dataclass(repr=False)
class XraySecrets:
    clients: list[Client] = field(default_factory=list)
    _extra: dict = field(default_factory=dict)


@dataclass(repr=False)
class NginxXhttpSecrets:
    server_name: str | None = None
    _extra: dict = field(default_factory=dict)


@dataclass(repr=False)
class SubscriptionSecrets:
    server_name: str | None = None
    port: int | None = None
    _extra: dict = field(default_factory=dict)


def mapping(value):
    if not isinstance(value, dict):
        raise ValueError("parse decrypted secrets YAML: expected mapping")
    return value


def optional_string(value):
    if value is not None and not isinstance(value, str):
        raise ValueError("parse decrypted secrets YAML: expected string")
    return value


@dataclass(repr=False)
class Secrets:
    xray: XraySecrets
    nginx_xhttp: NginxXhttpSecrets
    subscription: SubscriptionSecrets
    _extra: dict

    @classmethod
    def load(cls, path):
        with open_private(path) as handle:
            raw = load_yaml(handle)
        if not isinstance(raw, dict):
            raise ValueError("decrypted secrets YAML must contain a mapping")
        xray = mapping(raw.get("xray", {}))
        rows = xray.get("clients", [])
        if not isinstance(rows, list):
            raise ValueError("parse decrypted secrets YAML: clients must be a sequence")
        clients = []
        for row in rows:
            row = mapping(row)
            if not isinstance(row.get("name"), str):
                raise ValueError("parse decrypted secrets YAML: client name required")
            clients.append(
                Client(
                    row["name"],
                    optional_string(row.get("uuid")),
                    optional_string(row.get("short_id")),
                    {k: v for k, v in row.items() if k not in {"name", "uuid", "short_id"}},
                )
            )
        nginx = mapping(raw.get("nginx_xhttp", {}))
        subscription = mapping(raw.get("subscription", {}))
        port = subscription.get("port")
        if port is not None and (type(port) is not int or not 0 <= port <= 2**64 - 1):
            raise ValueError("parse decrypted secrets YAML: subscription port must be u64")
        return cls(
            XraySecrets(clients, {k: v for k, v in xray.items() if k != "clients"}),
            NginxXhttpSecrets(
                optional_string(nginx.get("server_name")),
                {k: v for k, v in nginx.items() if k != "server_name"},
            ),
            SubscriptionSecrets(
                optional_string(subscription.get("server_name")),
                port,
                {k: v for k, v in subscription.items() if k not in {"server_name", "port"}},
            ),
            {k: v for k, v in raw.items() if k not in {"xray", "nginx_xhttp", "subscription"}},
        )

    def __repr__(self):
        return f"Secrets(xray_clients={len(self.xray.clients)}, extra_keys={len(self._extra)})"

    def find_client(self, name):
        return next((client for client in self.xray.clients if client.name == name), None)

    def extra_key_count(self):
        return len(self._extra)

    def extra_key_names(self):
        return [key for key in self._extra if isinstance(key, str)]

    def subscription_host(self):
        return self.subscription.server_name

    def subscription_port(self):
        return self.subscription.port
