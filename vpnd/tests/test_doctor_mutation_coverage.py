"""Exercise doctor exports in-process with owned, synthetic subprocess tools."""

import asyncio
from argparse import Namespace
from pathlib import Path
import sys
import tarfile

import pytest

from vpnd import version
from vpnd.commands import doctor
from vpnd.config import Context


def executable(directory, name, body):
    path = directory / name
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def controlled(tmp_path, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    binary = tmp_path / "bin"
    binary.mkdir()
    events = tmp_path / "events"
    clipboard = tmp_path / "clipboard"
    ctx = Context(
        root=root,
        ansible_dir=root / "ansible",
        tf_root=root / "terraform/providers/upcloud",
        env="test",
        provider="upcloud",
        sops_file=root / "config/test.secrets.sops.yaml",
        secrets_file=root / "runtime/custom-private.secrets.yaml",
        config_dir=root / "config",
        explain=False,
        yes=False,
    )
    monkeypatch.setenv("PATH", str(binary))
    # A mutated host guard must still resolve registry paths inside the fixture.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("DOCTOR_EVENTS", str(events))
    monkeypatch.setenv("DOCTOR_CLIPBOARD", str(clipboard))
    monkeypatch.delenv("DOCTOR_FAIL_TARGET", raising=False)
    monkeypatch.delenv("DOCTOR_CLIP_FAIL", raising=False)
    executable(
        binary,
        "make",
        """import os
from pathlib import Path
import sys
target = sys.argv[1]
with Path(os.environ['DOCTOR_EVENTS']).open('a') as stream:
    stream.write(target + '\\n')
secret = next(arg.split('=', 1)[1] for arg in sys.argv[2:] if arg.startswith('SECRETS_FILE='))
print(target + ': healthy stdout')
print('loading ' + secret)
print('historical /tmp/vpn-test.secrets.yaml')
print(target + ': diagnostic stderr', file=sys.stderr)
sys.exit(7 if target == os.environ.get('DOCTOR_FAIL_TARGET') else 0)
""",
    )
    return ctx, binary, events, clipboard


def arguments():
    return Namespace(host=None, bundle=None, ai=False, clip=False)


def read_bundle(path):
    with tarfile.open(path, "r:gz") as archive:
        assert set(archive.getnames()) == {
            "vpnd-version.txt",
            "uname.txt",
            "terraform-version.txt",
            "ansible-version.txt",
            "audit-log.txt",
            "doctor-report.md",
        }
        assert all(member.mode == 0o644 for member in archive.getmembers())
        return {name: archive.extractfile(name).read().decode() for name in archive.getnames()}


@pytest.mark.parametrize("failed_target", [None, "burn-check"])
def test_doctor_runs_every_real_diagnostic_and_exports_partial_evidence(
    controlled, monkeypatch, capsys, failed_target
):
    ctx, _, events, _ = controlled
    if failed_target:
        monkeypatch.setenv("DOCTOR_FAIL_TARGET", failed_target)
        with pytest.raises(RuntimeError, match="1 of 6 doctor diagnostic steps failed"):
            asyncio.run(doctor.run(ctx, arguments()))
    else:
        result = asyncio.run(doctor.run(ctx, arguments()))
        assert result == 0
    output = capsys.readouterr()
    assert events.read_text().splitlines() == doctor.STEPS
    positions = [output.out.index(step + ": healthy stdout") for step in doctor.STEPS]
    assert positions == sorted(positions)
    assert all(step + ": diagnostic stderr" in output.out for step in doctor.STEPS)
    assert output.out.count("**Failed**") == int(failed_target is not None)
    assert output.out.count(doctor.MARKER) >= 12
    assert str(ctx.secrets_file) not in output.out + output.err
    assert "/tmp/vpn-test.secrets.yaml" not in output.out + output.err


def test_doctor_explain_has_all_steps_without_any_tool_or_export(controlled, capsys, tmp_path):
    ctx, _, events, clipboard = controlled
    ctx.explain = True
    bundle = tmp_path / "explain.tar.gz"
    args = arguments()
    args.bundle, args.ai, args.clip = bundle, True, True
    result = asyncio.run(doctor.run(ctx, args))
    assert result == 0
    output = capsys.readouterr()
    assert output.out == ""
    assert all("make " + step in output.err for step in doctor.STEPS)
    assert str(ctx.secrets_file) not in output.err
    assert not events.exists() and not clipboard.exists() and not bundle.exists()


def test_ai_prompt_redacts_report_and_excerpts_and_keeps_context(controlled):
    ctx, _, _, _ = controlled
    report = f"healthy report\nloading {ctx.secrets_file}\n"
    excerpts = "runbook evidence\nhistorical /tmp/vpn-test.secrets.yaml\n"
    prompt = doctor.ai_prompt(ctx, None, report, excerpts)
    assert "- env: test" in prompt and "- provider: upcloud" in prompt
    assert "- host: (active env)" in prompt
    assert "healthy report" in prompt and "runbook evidence" in prompt
    assert "docs/RUNBOOK-incident.md" in prompt and "CDN is NOT the baseline" in prompt
    assert prompt.count(doctor.MARKER) == 2
    assert str(ctx.secrets_file) not in prompt and "/tmp/vpn-test.secrets.yaml" not in prompt
    assert "- host: synthetic-host" in doctor.ai_prompt(ctx, "synthetic-host", "", "")


@pytest.mark.parametrize("exit_code", [0, 9])
def test_run_capture_keeps_real_stdout_for_success_and_failure(controlled, exit_code):
    _, binary, _, _ = controlled
    executable(
        binary,
        "synthetic-version",
        f"import sys\nassert sys.argv[1:] == ['--version']\nprint('version stdout')\nprint('version stderr', file=sys.stderr)\nsys.exit({exit_code})\n",
    )
    captured = asyncio.run(doctor.run_capture("synthetic-version", ["--version"]))
    assert captured == "version stdout\n" and "version stderr" not in captured


def test_run_capture_reports_a_missing_tool(controlled):
    captured = asyncio.run(doctor.run_capture("missing-version-tool", ["--version"]))
    assert captured.startswith("(missing-version-tool unavailable: ") and captured.endswith(")\n")


@pytest.mark.parametrize("audit_failure", [False, True])
def test_bundle_contains_real_tool_evidence_and_redacts_every_member(
    controlled, monkeypatch, tmp_path, audit_failure
):
    ctx, binary, events, _ = controlled
    for name, exit_code in [("uname", 0), ("ansible", 9)]:
        expected_args = ["-a"] if name == "uname" else ["--version"]
        executable(
            binary,
            name,
            f"import sys\nassert sys.argv[1:] == {expected_args!r}\nprint({(name + ' evidence')!r})\nprint({str(ctx.secrets_file)!r})\nprint('historical /tmp/vpn-test.secrets.yaml')\nsys.exit({exit_code})\n",
        )
    if audit_failure:
        monkeypatch.setenv("DOCTOR_FAIL_TARGET", "audit-log")
    path = tmp_path / "bundle.tar.gz"
    report = f"report evidence\nloading {ctx.secrets_file}\n/tmp/vpn-test.secrets.yaml\n"
    asyncio.run(doctor.write_bundle(ctx, report, path))
    entries = read_bundle(path)
    assert entries["vpnd-version.txt"] == "vpnd " + version() + "\n"
    assert entries["uname.txt"] == "uname evidence\n" + (doctor.MARKER + "\n") * 2
    assert entries["ansible-version.txt"] == "ansible evidence\n" + (doctor.MARKER + "\n") * 2
    assert entries["terraform-version.txt"].startswith("(terraform unavailable: ")
    assert entries["doctor-report.md"] == "report evidence\n" + (doctor.MARKER + "\n") * 2
    assert events.read_text().splitlines() == ["audit-log"]
    if audit_failure:
        assert entries["audit-log.txt"].startswith(
            "(audit-log unavailable: command failed (rc=7): "
        )
    else:
        assert (
            entries["audit-log.txt"] == "audit-log: healthy stdout\n" + (doctor.MARKER + "\n") * 2
        )
    assert all(str(ctx.secrets_file) not in text for text in entries.values())
    assert all("/tmp/vpn-test.secrets.yaml" not in text for text in entries.values())


def clipboard_tool(binary, name):
    executable(
        binary,
        name,
        """import os
from pathlib import Path
import sys
Path(os.environ['DOCTOR_CLIPBOARD']).write_bytes(sys.stdin.buffer.read())
Path(os.environ['DOCTOR_CLIPBOARD'] + '.argv').write_text(repr(sys.argv[1:]))
sys.exit(9 if os.environ.get('DOCTOR_CLIP_FAIL') == '1' else 0)
""",
    )


@pytest.mark.parametrize(
    "name, expected_args",
    [("pbcopy", []), ("wl-copy", []), ("xclip", ["-selection", "clipboard"]), ("xsel", ["-b"])],
)
def test_each_real_clipboard_backend_receives_exact_utf8(controlled, name, expected_args):
    _, binary, _, clipboard = controlled
    clipboard_tool(binary, name)
    text = "synthetic clipboard \N{SNOWMAN}\n"
    asyncio.run(doctor.try_copy_to_clipboard(text))
    assert clipboard.read_bytes() == text.encode()
    assert Path(str(clipboard) + ".argv").read_text() == repr(expected_args)


@pytest.mark.parametrize("backend", ["failed", "missing"])
def test_clipboard_failure_or_absence_is_reported(controlled, monkeypatch, backend):
    _, binary, _, clipboard = controlled
    if backend == "failed":
        clipboard_tool(binary, "pbcopy")
        monkeypatch.setenv("DOCTOR_CLIP_FAIL", "1")
        message = "pbcopy failed"
    else:
        message = "no clipboard binary found"
    with pytest.raises(RuntimeError, match=message):
        asyncio.run(doctor.try_copy_to_clipboard("synthetic request"))
    assert clipboard.exists() == (backend == "failed")


@pytest.mark.parametrize("backend", ["success", "failed", "missing"])
def test_full_ai_bundle_clipboard_exports_share_redaction_and_fallback(
    controlled, monkeypatch, tmp_path, capsys, backend
):
    ctx, binary, events, clipboard = controlled
    if backend != "missing":
        clipboard_tool(binary, "pbcopy")
    if backend == "failed":
        monkeypatch.setenv("DOCTOR_CLIP_FAIL", "1")
    path = tmp_path / "ai-bundle.tar.gz"
    args = arguments()
    args.bundle, args.ai, args.clip = path, True, True
    result = asyncio.run(doctor.run(ctx, args))
    assert result == 0
    output = capsys.readouterr()
    entries = read_bundle(path)
    assert events.read_text().splitlines() == doctor.STEPS + ["audit-log"]
    report = entries["doctor-report.md"]
    assert all(step + ": healthy stdout" in report for step in doctor.STEPS)
    assert "**Failed**" not in report
    if backend == "success":
        assert output.out == "" and "AI prompt copied to clipboard" in output.err
        prompt = clipboard.read_text()
    else:
        assert "printing to stdout" in output.err
        assert (
            "pbcopy failed" if backend == "failed" else "no clipboard binary found"
        ) in output.err
        prompt = output.out
        if backend == "failed":
            assert output.out == clipboard.read_text() + "\n"
    assert "You are debugging a vpn-deploy host" in prompt
    assert "Below is the output of `vpnd doctor`" in prompt
    assert all(step + ": diagnostic stderr" in prompt for step in doctor.STEPS)
    assert doctor.MARKER in prompt
    assert str(ctx.secrets_file) not in prompt + output.err
    assert "/tmp/vpn-test.secrets.yaml" not in prompt + output.err
    assert all(str(ctx.secrets_file) not in text for text in entries.values())
