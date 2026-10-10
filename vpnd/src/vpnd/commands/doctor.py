"""Resilient local diagnostics with redaction at every export boundary."""

import asyncio
import io
from pathlib import Path
import shutil
import sys
import tarfile
from vpnd import docs_bundle
from vpnd.runner import make, Cmd
from vpnd.runner.process import CapturePolicy

STEPS = [
    "fleet-status",
    "burn-check",
    "asn-drift",
    "check-ip-reputation",
    "probing-summary",
    "audit-permissions",
]
MARKER = "<redacted: secrets file path>"


def redact_secrets(text, resolved_secrets_path):
    if resolved_secrets_path:
        offset = 0
        while (start := text.find(resolved_secrets_path, offset)) >= 0:
            end = start + len(resolved_secrets_path)
            line_start = text.rfind("\n", 0, start) + 1
            line_end = text.find("\n", end)
            if line_end < 0:
                line_end = len(text)
            text = text[:line_start] + MARKER + text[line_end:]
            offset = line_start + len(MARKER)
    result = []
    chunks = text.split("\n")
    for index, chunk in enumerate(chunks):
        line = chunk + ("\n" if index < len(chunks) - 1 else "")
        if "/tmp/vpn-" in line and ".secrets.yaml" in line:
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            result.append(MARKER + ending)
        else:
            result.append(line)
    return "".join(result)


def render_step_section(explain, stdout, stderr, failed):
    section = f"### {explain}\n\n"
    if failed:
        section += "**Failed**\n\n"
    if stdout:
        section += f"```\n{stdout}```\n\n"
    if stderr:
        section += f"stderr:\n\n```\n{stderr}```\n\n"
    if not stdout and not stderr and not failed:
        section += "```\n(no output)\n```\n\n"
    return section


def ai_prompt(ctx, host, report, excerpts):
    prompt = f"""You are debugging a vpn-deploy host running a four-tier multi-profile VPN
stack (P0 VLESS+REALITY+Vision, P1 nginx+XHTTP direct, P2 Hysteria2 + AmneziaWG).

Context:
- env: {ctx.env}
- provider: {ctx.provider}
- host: {host or "(active env)"}
- threat model: active L7 fingerprinting and aggressive QoS. CDN is NOT the baseline; see docs/CDN-DECISION.md.
- relevant runbooks: docs/RUNBOOK-incident.md, docs/RUNBOOK-rollback.md.

Below is the output of `vpnd doctor`. Please identify the most likely root cause,
propose the smallest safe remediation, and cite which runbook or script applies.

{report}{excerpts}
"""
    return redact_secrets(prompt, str(ctx.secrets_file))


async def run_capture(program, args):
    try:
        return (
            await Cmd.new(program)
            .args(args)
            .capture_policy(CapturePolicy.OWNED_PROCESS_GROUP)
            .capture_detailed(False)
        ).stdout
    except OSError as error:
        return f"({program} unavailable: {error})\n"


async def write_bundle(ctx, report, out_path):
    from vpnd import version

    __version__ = version()
    entries = [("vpnd-version.txt", f"vpnd {__version__}\n")]
    for name, program, args in [
        ("uname.txt", "uname", ["-a"]),
        ("terraform-version.txt", "terraform", ["--version"]),
        ("ansible-version.txt", "ansible", ["--version"]),
    ]:
        entries.append((name, await run_capture(program, args)))
    try:
        audit = (
            await make.target(ctx, "audit-log")
            .capture_policy(CapturePolicy.OWNED_PROCESS_GROUP)
            .capture(False)
        ).stdout
    except Exception as error:
        audit = f"(audit-log unavailable: {error})\n"
    entries += [("audit-log.txt", audit), ("doctor-report.md", report)]

    def encode():
        with tarfile.open(out_path, mode="w:gz") as archive:
            for name, value in entries:
                data = redact_secrets(value, str(ctx.secrets_file)).encode()
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o644
                archive.addfile(info, io.BytesIO(data))

    await asyncio.to_thread(encode)


async def try_copy_to_clipboard(text):
    for argv in [("pbcopy",), ("wl-copy",), ("xclip", "-selection", "clipboard"), ("xsel", "-b")]:
        if shutil.which(argv[0]):
            child = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE)
            try:
                await child.communicate(text.encode())
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
            if child.returncode:
                raise RuntimeError(f"{argv[0]} failed")
            return
    raise RuntimeError("no clipboard binary found (tried pbcopy, wl-copy, xclip, xsel)")


async def run(ctx, args):
    if args.host:
        from vpnd.commands import ensure_host_in_registry
        from vpnd.state.registry import Registry

        ensure_host_in_registry(ctx, Registry.load(), args.host)
    report, failed = "", 0
    for step in STEPS:
        command = make.target(ctx, step).capture_policy(CapturePolicy.OWNED_PROCESS_GROUP)
        try:
            result = await command.capture_detailed(ctx.explain)
            failed += result.rc != 0
            report += render_step_section(
                command.redacted_explain(), result.stdout, result.stderr, result.rc != 0
            )
        except Exception as error:
            failed += 1
            report += render_step_section(
                command.redacted_explain(), "", f"(capture failed: {error})", True
            )
    if ctx.explain:
        return 0
    if args.bundle:
        await write_bundle(ctx, report, Path(args.bundle))
        print(f"ok: bundle written to {args.bundle}", file=sys.stderr)
    if args.ai:
        prompt = ai_prompt(ctx, args.host, report, docs_bundle.relevant_runbook_excerpts(report))
        if args.clip:
            try:
                await try_copy_to_clipboard(prompt)
                print("AI prompt copied to clipboard", file=sys.stderr)
            except Exception as error:
                print(f"note: {error}; printing to stdout", file=sys.stderr)
                print(prompt)
        else:
            print(prompt)
    elif not args.bundle:
        print("Doctor report\n\n" + redact_secrets(report, str(ctx.secrets_file)))
    if failed:
        raise RuntimeError(f"{failed} of {len(STEPS)} doctor diagnostic steps failed")
    return 0
