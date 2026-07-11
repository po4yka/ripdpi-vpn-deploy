"""Keep vpnd share URLs aligned with both subscription server boundaries."""

from pathlib import Path


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[body_start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def test_vpnd_share_matches_subscription_route_contract():
    root = Path(__file__).resolve().parents[2]
    share = (root / "vpnd/src/commands/share.rs").read_text()
    nginx = (
        root / "ansible/roles/subscription-host/templates/subscription.conf.j2"
    ).read_text()
    service = (
        root / "ansible/roles/subscription-host/templates/vpn-bootstrap.py.j2"
    ).read_text()

    token_pattern = "[A-Za-z0-9_-]{16,64}"
    assert token_pattern in nginx
    assert token_pattern in service
    assert "const MIN_TOKEN_LENGTH: usize = 16;" in share
    assert "const MAX_TOKEN_LENGTH: usize = 64;" in share
    assert '.json' not in _function_body(share, "pub fn build_sub_urls")
