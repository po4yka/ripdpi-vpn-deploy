import tarfile
from artifact_helpers import scaffold, executable, cli
from vpnd.commands.doctor import STEPS


def setup(root):
    scaffold(root)
    executable(
        root,
        "make",
        """#!/bin/sh
target=$1
shift
echo "ran $target"
if [ "$target" = burn-check ] && [ "${FAIL_BURN_CHECK:-0}" = 1 ]; then
 echo 'burn-check: address is burned' >&2
 exit 3
fi
echo "$target: healthy"
""",
    )


def positions(report):
    return [report.index("make " + step) for step in STEPS]


# Rust test: vpnd/tests/doctor_resilience.rs::all_steps_run_and_report_after_a_mid_run_failure
def test_all_steps_run_and_report_after_a_mid_run_failure(tmp_path):
    setup(tmp_path)
    output = cli(tmp_path, "doctor", FAIL_BURN_CHECK="1")
    assert output.returncode != 0 and "1 of 6 doctor diagnostic steps failed" in output.stderr
    report = output.stdout
    assert positions(report) == sorted(positions(report))
    assert (
        "**Failed**" in report
        and "burn-check: address is burned" in report
        and "asn-drift: healthy" in report
    )


# Rust test: vpnd/tests/doctor_resilience.rs::healthy_run_exits_zero_without_failed_marks
def test_healthy_run_exits_zero_without_failed_marks(tmp_path):
    setup(tmp_path)
    output = cli(tmp_path, "doctor")
    assert output.returncode == 0, output.stderr
    assert "**Failed**" not in output.stdout and len(positions(output.stdout)) == 6


# Rust test: vpnd/tests/doctor_resilience.rs::bundle_preserves_the_failed_step_evidence
def test_bundle_preserves_the_failed_step_evidence(tmp_path):
    setup(tmp_path)
    path = tmp_path / "doctor-bundle.tar.gz"
    output = cli(tmp_path, "doctor", "--bundle", path, FAIL_BURN_CHECK="1")
    assert output.returncode != 0 and path.is_file()
    with tarfile.open(path) as archive:
        assert set(archive.getnames()) == {
            "vpnd-version.txt",
            "uname.txt",
            "terraform-version.txt",
            "ansible-version.txt",
            "audit-log.txt",
            "doctor-report.md",
        }
        report = archive.extractfile("doctor-report.md").read().decode()
    assert (
        "**Failed**" in report
        and "burn-check: address is burned" in report
        and len(positions(report)) == 6
    )


# Rust test: vpnd/tests/doctor_resilience.rs::explain_mode_lists_the_steps_without_running_them
def test_explain_mode_lists_the_steps_without_running_them(tmp_path):
    setup(tmp_path)
    output = cli(tmp_path, "--explain", "doctor")
    assert output.returncode == 0, output.stderr
    for step in STEPS:
        assert "make " + step in output.stderr
    assert "ran " not in output.stdout + output.stderr
