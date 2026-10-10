"""One argparse command tree for dispatch, help and generated documentation."""

import argparse
import os
from pathlib import Path
from . import version

COMMANDS = {
    "deploy": "Interactive deploy wizard.",
    "reconverge": "Idempotent re-deploy against existing hosts.",
    "share": "Bundled recipient handoff (URL, QR, sing-box and app cards).",
    "doctor": "Diagnostic bundle.",
    "probe": "Profile-aware probing.",
    "probe-matrix": "Multi-protocol simultaneity DPI probe across a configured matrix.",
    "preflight": "Pre-deploy guards.",
    "fleet": "Fleet-wide operations.",
    "host": "Local host registry.",
    "ai-docs": "Machine-readable docs endpoints.",
    "update": "Check for a newer vpnd release (cached 24 h).",
    "completions": "Emit shell completions to stdout.",
}


class UniqueStore(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        seen: set[tuple[int, str]] = getattr(namespace, "_seen", set())
        identity = (id(self), self.dest)
        if identity in seen:
            parser.error(f"the argument {option_string} cannot be used multiple times")
        seen.add(identity)
        setattr(namespace, "_seen", seen)
        setattr(namespace, self.dest, values)


class UniqueFlag(UniqueStore):
    def __init__(self, *args, **kwargs):
        kwargs["nargs"] = 0
        super().__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        return super().__call__(parser, namespace, True, option_string)


def flag(parser, name, **kwargs):
    parser.add_argument(name, action=UniqueFlag, default=False, **kwargs)


def globals_on(parser, root=False, host_add=False):
    default = {} if root else {"default": argparse.SUPPRESS}
    parser.add_argument(
        "--explain",
        action=UniqueFlag,
        **({"default": False} if root else default),
        help="Print underlying invocations without running them.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action=UniqueFlag,
        **({"default": False} if root else default),
        help="Skip interactive confirmation.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        action=UniqueStore,
        **({"default": os.environ.get("VPN_DEPLOY_ROOT")} if root else default),
        help="Override repository root (VPN_DEPLOY_ROOT; default: discover from cwd).",
    )
    if not host_add:
        parser.add_argument(
            "--env",
            "-e",
            action=UniqueStore,
            **({"default": os.environ.get("VPN_ENV", "prod")} if root else default),
            help="Target environment (VPN_ENV; default: prod).",
        )
        parser.add_argument(
            "--provider",
            "-p",
            action=UniqueStore,
            **({"default": os.environ.get("VPN_PROVIDER", "upcloud")} if root else default),
            help="Cloud provider Terraform root (VPN_PROVIDER; default: upcloud).",
        )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vpnd",
        description="Convenience CLI for vpn-deploy (wraps Make / Terraform / Ansible / SOPS)",
        allow_abbrev=False,
    )
    globals_on(parser, True)
    parser.add_argument("--version", "-V", action="version", version=f"vpnd {version()}")
    children = parser.add_subparsers(dest="command", required=True)
    nodes = {}
    for name, help_text in COMMANDS.items():
        node = children.add_parser(name, help=help_text, description=help_text, allow_abbrev=False)
        globals_on(node)
        nodes[name] = node
    for name in ("skip-precheck", "tag-on-success"):
        flag(nodes["deploy"], "--" + name)
    for command in ("doctor", "probe", "reconverge"):
        nodes[command].add_argument("--host", action=UniqueStore)
    flag(nodes["reconverge"], "--dry-run")
    share = nodes["share"]
    share.add_argument("client")
    flag(share, "--qr")
    share.add_argument("--type", choices=["singbox", "uri"], default="singbox", action=UniqueStore)
    share.add_argument("--out", type=Path, action=UniqueStore)
    tokens = share.add_mutually_exclusive_group(required=True)
    tokens.add_argument("--token-stdin", action=UniqueFlag, default=False)
    tokens.add_argument("--token-file", type=Path, action=UniqueStore)
    doctor = nodes["doctor"]
    flag(doctor, "--ai")
    flag(doctor, "--clip")
    doctor.add_argument("--bundle", type=Path, action=UniqueStore)
    nodes["probe"].add_argument(
        "--profile", choices=["p0", "p1", "p2", "all"], default="all", action=UniqueStore
    )
    matrix = nodes["probe-matrix"]
    matrix.add_argument("--duration", default="4h", action=UniqueStore)

    def u64(value):
        if not value.isascii() or not value.isdigit() or int(value) > 2**64 - 1:
            raise argparse.ArgumentTypeError("expected unsigned 64-bit integer")
        return int(value)

    matrix.add_argument("--poll-interval-seconds", type=u64, action=UniqueStore)
    for name in ("config", "output"):
        matrix.add_argument("--" + name, type=Path, action=UniqueStore)
    flag(matrix, "--json")
    flag(nodes["preflight"], "--skip-certs")
    fleet = nodes["fleet"].add_subparsers(dest="action", required=True)
    for name in ("status", "rotate", "drift"):
        node = fleet.add_parser(name, allow_abbrev=False)
        globals_on(node)
        if name == "rotate":
            node.add_argument("--plan", required=True, type=Path, action=UniqueStore)
            flag(node, "--resume")
            flag(node, "--dry-run")
    host = nodes["host"].add_subparsers(dest="action", required=True)
    for name in ("list", "show", "add", "remove"):
        node = host.add_parser(name, allow_abbrev=False)
        globals_on(node, host_add=name == "add")
        if name != "list":
            node.add_argument("name")
        if name in {"list", "show"}:
            flag(node, "--json")
        if name == "add":
            node.add_argument("--env", dest="host_env", required=True, action=UniqueStore)
            node.add_argument("--provider", dest="host_provider", required=True, action=UniqueStore)
            for key in ("ipv4", "ipv6"):
                node.add_argument("--" + key, action=UniqueStore)
    nodes["ai-docs"].add_argument("--out", type=Path, action=UniqueStore)
    nodes["completions"].add_argument("shell")
    descriptions = {
        "deploy": {
            "skip_precheck": "Skip running pre-deploy guards (mirrors SKIP_PRECHECK=1).",
            "tag_on_success": "Tag a known-good commit after a successful verify run.",
        },
        "reconverge": {
            "host": "Limit to a single host from the registry.",
            "dry_run": "Stop after dry-run; do not apply.",
        },
        "share": {
            "client": "Client name.",
            "qr": "Also emit a QR code image.",
            "type": "QR payload type (default: singbox).",
            "out": "Output directory (default: ./share/<client>/).",
            "token_stdin": "Read the opaque subscription token from stdin.",
            "token_file": "Read the opaque subscription token from a 0600 file.",
        },
        "doctor": {
            "host": "Host alias from the registry; omitted = active env's primary host.",
            "ai": "Format output as a clipboard-ready prompt for an AI assistant.",
            "clip": "Copy AI prompt to the system clipboard (requires --ai).",
            "bundle": "Pack a diagnostic gzip-tar bundle at this path (orthogonal to --ai).",
        },
        "probe": {
            "host": "Host alias from the registry; omitted = active env's primary host.",
            "profile": "Which profile to probe (default: all).",
        },
        "probe-matrix": {
            "duration": "Run duration; plain seconds or NN{s,m,h,d} (default: 4h).",
            "poll_interval_seconds": "Poll interval between matrix sweeps (seconds); overrides config.",
            "config": "Matrix config YAML (default: <root>/vpnd/config/probe-matrix.yaml).",
            "output": "Report JSON output (default: <root>/vpnd/state/probe-matrix-<unix-ms>.json).",
            "json": "Emit a machine-readable run summary instead of the human path line.",
        },
        "preflight": {"skip_certs": "Skip the certificate-validity check (faster smoke)."},
        "ai-docs": {"out": "Output directory (default: ./ai-docs/)."},
        "update": {
            "explain": "Print the GitHub API URL that would be queried and exit without fetching."
        },
        "completions": {
            "shell": "Shell to generate completions for: bash, zsh, fish, powershell (pwsh alias)."
        },
    }
    for name, messages in descriptions.items():
        for action in nodes[name]._actions:
            if action.dest in messages:
                action.help = messages[action.dest]
    nested = {
        "fleet": {
            "status": ("Summary table across every host:env pair.", {}),
            "rotate": (
                "Coordinated rotation across the fleet.",
                {
                    "plan": "Path to the fleet plan YAML.",
                    "resume": "Resume a partially-completed rotation.",
                    "dry_run": "Show what would happen without making changes.",
                },
            ),
            "drift": ("Diff fleet state against the last known-good tag.", {}),
        },
        "host": {
            "list": (
                "List registered hosts.",
                {"json": "Emit a machine-readable JSON array instead of the table."},
            ),
            "show": (
                "Show one host record.",
                {
                    "json": "Emit compact single-line JSON instead of the pretty form.",
                    "name": "Host name.",
                },
            ),
            "add": (
                "Add a host record.",
                {
                    "name": "Host name.",
                    "host_env": "Host environment.",
                    "host_provider": "Host cloud provider.",
                    "ipv4": "Host IPv4 address.",
                    "ipv6": "Host IPv6 address.",
                },
            ),
            "remove": ("Remove a host record.", {"name": "Host name."}),
        },
    }
    for command, entries in nested.items():
        subparsers = next(
            action
            for action in nodes[command]._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        for name, (description, messages) in entries.items():
            child = subparsers.choices[name]
            child.description = description
            for action in child._actions:
                if action.dest in messages:
                    action.help = messages[action.dest]
    return parser


def parse_args(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor" and args.clip and not args.ai:
        parser.error("--clip requires --ai")
    return args
