from hypothesis import example, given, settings, strategies as st
from vpnd.commands.doctor import redact_secrets

ascii_text = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=40)
path = st.lists(
    st.sampled_from(["runtime", "space dir", "O'Brien", "данные", "line\nbreak", "tab\tpath"]),
    min_size=1,
    max_size=4,
).map(lambda parts: "/" + "/".join(parts) + "/vpn-test.secrets.yaml")


@example("prefix", "test", "\x0bsensitive suffix")
@example("prefix", "test", "\x0csensitive suffix")
@example("prefix", "test", "\x1csensitive suffix")
@example("prefix", "test", "\x1dsensitive suffix")
@example("prefix", "test", "\x1esensitive suffix")
@example("prefix", "test", "\x1fsensitive suffix")
@example("prefix", "test", "\rsensitive suffix")
@example("prefix", "test", "\x85sensitive suffix")
@example("prefix", "test", "\u2028sensitive suffix")
@example("prefix", "test", "\u2029sensitive suffix")
@settings(max_examples=256)
@given(ascii_text, st.from_regex(r"[a-z][a-z0-9-]{0,15}", fullmatch=True), ascii_text)
# Rust test: vpnd/tests/proptest_redact.rs::redact_masks_any_historical_default_path
def test_redact_masks_any_historical_default_path(prefix, env, suffix):
    assert (
        redact_secrets(prefix + "/tmp/vpn-" + env + ".secrets.yaml" + suffix, "")
        == "<redacted: secrets file path>"
    )


@settings(max_examples=256)
@given(ascii_text, path, ascii_text)
# Rust test: vpnd/tests/proptest_redact.rs::redact_masks_resolved_non_tmp_paths
def test_redact_masks_resolved_non_tmp_paths(prefix, resolved, suffix):
    assert redact_secrets(prefix + resolved + suffix, resolved) == "<redacted: secrets file path>"


# Original proptest seeds aed5d54c835bc73723993ccb8c74718eab32fde0570748a14a1f3501922a97f3
# and f64d329836cd234aaa193c97be4d731753d12941dbb15d811a15017f9d6a00f4 both shrink to ['', ''].
@example(["", ""], False)
@example(["", ""], True)
@settings(max_examples=256)
@given(
    st.lists(
        st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=80).filter(
            lambda line: not ("/tmp/vpn-" in line and ".secrets.yaml" in line)
        ),
        max_size=9,
    ),
    st.booleans(),
)
# Rust test: vpnd/tests/proptest_redact.rs::redact_preserves_non_secret_lines
def test_redact_preserves_non_secret_lines(lines, trailing_newline):
    value = "\n".join(lines) + ("\n" if trailing_newline else "")
    assert redact_secrets(value, "/nonexistent/resolved.secrets.yaml") == value


def test_redaction_uses_lf_boundaries_and_preserves_historical_crlf():
    marker = "<redacted: secrets file path>"
    path = "/tmp/vpn-old.secrets.yaml"
    for separator in [
        "\v",
        "\f",
        "\x1c",
        "\x1d",
        "\x1e",
        "\x1f",
        "\r",
        "\u0085",
        "\u2028",
        "\u2029",
    ]:
        line = "prefix" + separator + path + separator + "sensitive suffix"
        assert redact_secrets(line, "/different/current") == marker
        assert redact_secrets(line + "\n", "/different/current") == marker + "\n"
    assert (
        redact_secrets("before\n" + path + "\r\nafter\n", "/different/current")
        == "before\n" + marker + "\r\nafter\n"
    )
    # Resolved-path removal precedes fallback scanning and removes a CR that
    # belongs to the same LF-delimited line, matching the original algorithm.
    assert (
        redact_secrets("before\n" + path + "\r\nafter\n", path) == "before\n" + marker + "\nafter\n"
    )
    for value in [
        "",
        "\n",
        "\n\n",
        "plain",
        "plain\n",
        "plain\r",
        "plain\r\n",
        "plain\vtext",
        "plain\u2028text",
    ]:
        assert redact_secrets(value, "/different/current") == value
