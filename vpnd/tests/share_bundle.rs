//! Integration tests for commands::share bundle structure and urlencode.
//!
//! The share command requires a decrypted secrets file and a make emit-singbox stub.
//! We test the structural invariants via the recipient page and qr modules directly,
//! and test the production URL encoder. Full bundle/token validation is in share_command.rs.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use tempfile::TempDir;
use vpnd::commands::share::{build_sub_urls, urlencode as share_urlencode};
use vpnd::pages::{qr, recipient};

// --- urlencode tests ---

#[test]
fn urlencode_encodes_colon_and_slashes() {
    let url = "https://vpn.example.com/sub/phone.json";
    let encoded = share_urlencode(url);
    assert!(
        !encoded.contains(':'),
        "colon must be encoded, got: {encoded}"
    );
    assert!(
        !encoded.contains('/'),
        "slashes must be encoded, got: {encoded}"
    );
    assert!(
        encoded.contains("%3A") || encoded.contains("%3a"),
        "colon must be percent-encoded, got: {encoded}"
    );
}

#[test]
fn urlencode_matches_subscription_host_route_expectation() {
    // The subscription-host nginx route uses the encoded URL as a query param.
    // Verify the deep link is constructed correctly.
    let host = "vpn.example.com";
    let client = "phone";
    let sub_url = format!("https://{host}/sub/{client}.json");
    let deeplink = format!(
        "sing-box://import-remote-profile?url={}",
        share_urlencode(&sub_url)
    );

    assert!(
        deeplink.starts_with("sing-box://import-remote-profile?url="),
        "deeplink must start with sing-box scheme, got: {deeplink}"
    );
    assert!(
        deeplink.contains("vpn%2Eexample%2Ecom") || deeplink.contains("vpn.example.com"),
        "host must appear in deeplink, got: {deeplink}"
    );
    // The raw url must NOT appear unencoded after ?url=
    let after_url = deeplink.split("?url=").nth(1).unwrap();
    assert!(
        !after_url.contains("://"),
        "raw :// must not appear in encoded portion, got: {after_url}"
    );
}

#[test]
fn urlencode_is_reversible() {
    let original = "https://vpn.example.com/sub/my client.json";
    let encoded = share_urlencode(original);
    // percent_encoding::percent_decode can reverse it
    let decoded = percent_encoding::percent_decode_str(&encoded)
        .decode_utf8()
        .unwrap();
    assert_eq!(decoded, original, "urlencode must be reversible");
}

// --- Bundle structure tests via qr + recipient modules ---

#[test]
fn share_bundle_directory_structure_index_html() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().to_path_buf();

    // Render recipient page (index.html)
    let ctx = recipient::RecipientCtx {
        client_name: "phone",
        host: "vpn.example.com",
        env: "prod",
        provider: "upcloud",
        subscription_url: "https://vpn.example.com/sub/phone",
        singbox_deeplink:
            "sing-box://import-remote-profile?url=https%3A%2F%2Fvpn.example.com%2Fsub%2Fphone.json",
        ripdpi_deeplink: "ripdpi://import?sub=https%3A%2F%2Fvpn.example.com%2Fsub%2Fphone",
        apps: vec![],
    };
    let html = recipient::render(&ctx).unwrap();
    std::fs::write(out.join("index.html"), &html).unwrap();

    assert!(out.join("index.html").is_file(), "index.html must exist");
    let content = std::fs::read_to_string(out.join("index.html")).unwrap();
    assert!(
        content.contains("phone"),
        "index.html must mention client name"
    );
    assert!(
        content.contains("vpn.example.com"),
        "index.html must mention host"
    );
}

#[test]
fn share_bundle_qr_png_has_valid_ppm_format() {
    let dir = TempDir::new().unwrap();
    let payload = "https://vpn.example.com/sub/phone.json";
    let png_path = dir.path().join("qr.png");

    qr::write_png(payload, &png_path).unwrap();
    assert!(png_path.is_file(), "qr.png must exist");

    let content = std::fs::read_to_string(&png_path).unwrap();
    assert!(
        content.starts_with("P1\n"),
        "qr.png (PPM) must start with P1"
    );
}

#[test]
fn share_bundle_qr_svg_is_valid_xml() {
    let dir = TempDir::new().unwrap();
    let payload = "https://vpn.example.com/sub/phone.json";
    let svg_path = dir.path().join("qr.svg");

    qr::write_svg(payload, &svg_path).unwrap();
    assert!(svg_path.is_file(), "qr.svg must exist");

    let content = std::fs::read_to_string(&svg_path).unwrap();
    assert!(content.contains("<svg"), "qr.svg must be valid SVG");
    assert!(
        content.contains("</svg>"),
        "qr.svg must have closing SVG tag"
    );
}

#[test]
fn recipient_subscription_url_matches_host_and_client() {
    let host = "vpn.example.com";
    let client = "laptop";
    let sub_url = format!("https://{host}/sub/{client}");

    let ctx = recipient::RecipientCtx {
        client_name: client,
        host,
        env: "prod",
        provider: "upcloud",
        subscription_url: &sub_url,
        singbox_deeplink: "sing-box://import-remote-profile?url=x",
        ripdpi_deeplink: "ripdpi://import?sub=x",
        apps: vec![],
    };
    let html = recipient::render(&ctx).unwrap();
    assert!(
        html.contains(&sub_url),
        "subscription URL must appear in rendered page"
    );
    assert!(
        html.contains(client),
        "client name must appear in rendered page"
    );
}

// --- build_sub_urls / token-path tests ---

#[test]
fn build_sub_urls_token_path_with_host_and_port() {
    // (a) token path with a subscription host + non-443 port
    let base = "https://sub.example.com:8444";
    let token = "abc123_XYZ-token";
    let urls = build_sub_urls(base, token);

    assert_eq!(
        urls.subscription_url,
        "https://sub.example.com:8444/sub/abc123_XYZ-token"
    );
    assert_eq!(
        urls.singbox_deeplink,
        format!(
            "sing-box://import-remote-profile?url={}",
            share_urlencode("https://sub.example.com:8444/sub/abc123_XYZ-token.json")
        )
    );
    assert_eq!(
        urls.qr_singbox,
        "https://sub.example.com:8444/sub/abc123_XYZ-token.json"
    );
    assert_eq!(
        urls.qr_uri,
        "https://sub.example.com:8444/sub/abc123_XYZ-token"
    );
}

#[test]
fn build_sub_urls_port_443_omitted() {
    // (b) base without explicit port (443 is implied by https) — caller must not append :443
    // The caller in share.rs skips appending :443 before calling build_sub_urls;
    // confirm the helper doesn't double-encode anything.
    let base = "https://sub.example.com"; // no port — 443 was filtered by caller
    let token = "tok-ABCDEF";
    let urls = build_sub_urls(base, token);

    assert_eq!(
        urls.subscription_url,
        "https://sub.example.com/sub/tok-ABCDEF"
    );
    assert!(
        !urls.subscription_url.contains(":443"),
        "port 443 must not appear"
    );
}
