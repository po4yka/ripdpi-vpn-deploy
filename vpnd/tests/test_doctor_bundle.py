from vpnd.commands.doctor import redact_secrets, render_step_section


# Rust test: vpnd/tests/doctor_bundle.rs::redact_masks_historical_default_tmp_path
def test_redact_masks_historical_default_tmp_path():
    text = "a\nSECRETS_FILE=/tmp/vpn-prod.secrets.yaml\nz\n"
    assert redact_secrets(text, "") == "a\n<redacted: secrets file path>\nz\n"
    value = redact_secrets(
        "loading /tmp/vpn-prod.secrets.yaml for client phone",
        "/cache/vpn-provision/vpn-prod.secrets.yaml",
    )
    assert value == "<redacted: secrets file path>" and "/tmp/vpn-" not in value


# Rust test: vpnd/tests/doctor_bundle.rs::redact_masks_resolved_path_outside_tmp
def test_redact_masks_resolved_path_outside_tmp():
    path = "/Users/op/Library/Caches/vpn-provision/vpn-prod.secrets.yaml"
    assert (
        redact_secrets("safe\nuse " + path + " now\nnext\n", path)
        == "safe\n<redacted: secrets file path>\nnext\n"
    )
    value = redact_secrets("reading secrets from " + path + " (env=prod)", path)
    assert value == "<redacted: secrets file path>" and "Library/Caches" not in value


# Rust test: vpnd/tests/doctor_bundle.rs::redact_leaves_innocent_lines_unchanged
def test_redact_leaves_innocent_lines_unchanged():
    text = "healthy\n/tmp/innocent.yaml\n\n"
    assert redact_secrets(text, "/nonexistent") == text


# Rust test: vpnd/src/commands/doctor.rs::healthy_section_renders_invocation_and_stdout
def test_healthy_section_renders_invocation_and_stdout():
    value = render_step_section("make fleet-status", "all green\n", "", False)
    assert value.startswith("### make fleet-status\n\n") and "Failed" not in value
    assert "```\nall green\n```" in value and "stderr:" not in value


# Rust test: vpnd/src/commands/doctor.rs::failed_section_marks_failure_and_keeps_both_streams
def test_failed_section_marks_failure_and_keeps_both_streams():
    value = render_step_section("make burn-check", "partial stdout\n", "IP is burned\n", True)
    assert (
        "**Failed**" in value
        and "```\npartial stdout\n```" in value
        and "stderr:\n\n```\nIP is burned\n```" in value
    )
    assert value.index("partial stdout") < value.index("IP is burned")


# Rust test: vpnd/src/commands/doctor.rs::capture_failure_section_records_the_error_without_streams
def test_capture_failure_section_records_the_error_without_streams():
    value = render_step_section("make fleet-status", "", "(capture failed: boom)", True)
    assert "**Failed**" in value and "(capture failed: boom)" in value
