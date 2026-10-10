from urllib.parse import unquote
from vpnd.commands.share import build_sub_urls, urlencode
from vpnd.pages.recipient import RecipientCtx, render
from vpnd.pages.qr import write_svg


def recipient():
    return RecipientCtx(
        "phone",
        "vpn.example.com",
        "prod",
        "upcloud",
        "https://vpn.example.com/sub/phone",
        "sing-box://import-remote-profile?url=x",
        "ripdpi://import?sub=x",
    )


# Rust test: vpnd/tests/share_bundle.rs::urlencode_encodes_colon_and_slashes
def test_urlencode_encodes_colon_and_slashes():
    encoded = urlencode("https://vpn.example.com/sub/phone.json")
    assert ":" not in encoded and "/" not in encoded and "%3A" in encoded


# Rust test: vpnd/tests/share_bundle.rs::urlencode_matches_subscription_host_route_expectation
def test_urlencode_matches_subscription_host_route_expectation():
    deep = "sing-box://import-remote-profile?url=" + urlencode(
        "https://vpn.example.com/sub/phone.json"
    )
    assert deep.startswith("sing-box://import-remote-profile?url=")
    assert "vpn%2Eexample%2Ecom" in deep
    assert "://" not in deep.split("?url=")[1]


# Rust test: vpnd/tests/share_bundle.rs::urlencode_is_reversible
def test_urlencode_is_reversible():
    original = "https://vpn.example.com/sub/my client.json"
    assert unquote(urlencode(original)) == original


# Rust test: vpnd/tests/share_bundle.rs::share_bundle_directory_structure_index_html
def test_share_bundle_directory_structure_index_html(tmp_path):
    path = tmp_path / "index.html"
    path.write_text(render(recipient()))
    assert path.is_file() and "phone" in path.read_text() and "vpn.example.com" in path.read_text()


# Rust test: vpnd/tests/share_bundle.rs::share_bundle_qr_svg_is_valid_xml
def test_share_bundle_qr_svg_is_valid_xml(tmp_path):
    path = tmp_path / "qr.svg"
    write_svg("https://vpn.example.com/sub/phone.json", path)
    assert path.is_file() and "<svg" in path.read_text() and "</svg>" in path.read_text()


# Rust test: vpnd/tests/share_bundle.rs::recipient_subscription_url_matches_host_and_client
def test_recipient_subscription_url_matches_host_and_client():
    ctx = recipient()
    ctx.client_name = "laptop"
    ctx.subscription_url = "https://vpn.example.com/sub/laptop"
    html = render(ctx)
    assert ctx.subscription_url in html and "laptop" in html


# Rust test: vpnd/tests/share_bundle.rs::build_sub_urls_token_path_with_host_and_port
def test_build_sub_urls_token_path_with_host_and_port():
    urls = build_sub_urls("https://sub.example.com:8444", "abc123_XYZ-token")
    assert urls.subscription_url == "https://sub.example.com:8444/sub/abc123_XYZ-token"
    assert urls.singbox_deeplink == "sing-box://import-remote-profile?url=" + urlencode(
        urls.subscription_url + ".json"
    )
    assert urls.qr_singbox == urls.subscription_url + ".json"
    assert urls.qr_uri == urls.subscription_url


# Rust test: vpnd/tests/share_bundle.rs::build_sub_urls_port_443_omitted
def test_build_sub_urls_port_443_omitted():
    urls = build_sub_urls("https://sub.example.com", "tok-ABCDEF")
    assert urls.subscription_url == "https://sub.example.com/sub/tok-ABCDEF"
    assert ":443" not in urls.subscription_url
