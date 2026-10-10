from hypothesis import given, settings, strategies as st
from urllib.parse import unquote
from vpnd.commands.share import urlencode


@settings(max_examples=256)
@given(st.text())
# Rust test: vpnd/tests/proptest_urlencode.rs::urlencode_no_whitespace_survives
def test_urlencode_no_whitespace_survives(s):
    encoded = urlencode(s)
    assert " " not in encoded and "\t" not in encoded and "\n" not in encoded


@settings(max_examples=256)
@given(st.text())
# Rust test: vpnd/tests/proptest_urlencode.rs::urlencode_roundtrip_via_url_decode
def test_urlencode_roundtrip_via_url_decode(s):
    assert unquote(urlencode(s)) == s
