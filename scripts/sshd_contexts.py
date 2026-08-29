"""Strict connection contexts shared by local SSH transaction controllers."""

import ipaddress
import json
import re


NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class ContextError(ValueError):
    """A connection context is ambiguous or outside the bounded contract."""


def validate_contexts(value):
    if not isinstance(value, list) or not 2 <= len(value) <= 8:
        raise ContextError("invalid-contexts")
    seen = set()
    for context in value:
        if not isinstance(context, dict) or set(context) != {"user", "host", "addr", "laddr", "lport"}:
            raise ContextError("invalid-contexts")
        if any(not isinstance(context[key], str) or NAME.fullmatch(context[key]) is None
               for key in ("user", "host")):
            raise ContextError("invalid-contexts")
        try:
            for key in ("addr", "laddr"):
                if not isinstance(context[key], str) or "%" in context[key]:
                    raise ValueError
                ipaddress.ip_address(context[key])
        except ValueError:
            raise ContextError("invalid-contexts") from None
        if type(context["lport"]) is not int or not 1 <= context["lport"] <= 65535:
            raise ContextError("invalid-contexts")
        canonical = json.dumps(context, sort_keys=True, separators=(",", ":"))
        if canonical in seen:
            raise ContextError("invalid-contexts")
        seen.add(canonical)
    return value


def bind_contexts(value, public_address, management_address, port):
    """Bind sshd -C contexts to both exact transports used for confirmation."""
    validate_contexts(value)
    try:
        public = str(ipaddress.ip_address(public_address))
        management = str(ipaddress.ip_address(management_address))
    except ValueError:
        raise ContextError("invalid-context-binding") from None
    if public == management or type(port) is not int or not 1 <= port <= 65535:
        raise ContextError("invalid-context-binding")
    if any(context["lport"] != port for context in value):
        raise ContextError("invalid-context-binding")
    try:
        local_addresses = {str(ipaddress.ip_address(context["laddr"])) for context in value}
    except ValueError:
        raise ContextError("invalid-context-binding") from None
    if local_addresses != {public, management}:
        raise ContextError("invalid-context-binding")
    return value
