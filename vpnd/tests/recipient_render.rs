//! Snapshot test for the recipient landing page render.
//!
//! Locked-in shape so a template tweak shows up as a clear PR diff,
//! mirroring `vpn-deploy/tests/snapshot/` discipline for Jinja templates.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use vpnd::pages::recipient::{render, AppCard, RecipientCtx};

#[test]
fn recipient_page_renders_with_expected_sections() {
    let ctx = RecipientCtx {
        client_name: "phone",
        host: "vpn.example.com",
        env: "prod",
        provider: "upcloud",
        subscription_url: "https://vpn.example.com/sub/recipient_token_123",
        singbox_deeplink:
            "sing-box://import-remote-profile?url=https%3A%2F%2Fvpn.example.com%2Fsub%2Frecipient_token_123",
        ripdpi_deeplink:
            "ripdpi://import?sub=https%3A%2F%2Fvpn.example.com%2Fsub%2Frecipient_token_123",
        apps: vec![
            AppCard {
                platform: "iOS".to_string(),
                primary: (
                    "Streisand",
                    "https://apps.apple.com/app/streisand/id6450534064",
                )
                    .into(),
                also: vec![],
            },
            AppCard {
                platform: "Android".to_string(),
                primary: (
                    "v2rayNG",
                    "https://github.com/2dust/v2rayNG/releases/latest",
                )
                    .into(),
                also: vec![(
                    "Hiddify",
                    "https://github.com/hiddify/hiddify-app/releases/latest",
                )
                    .into()],
            },
        ],
    };
    let out = render(&ctx).expect("render must succeed");

    assert!(out.contains("Connect to vpn.example.com"));
    assert!(out.contains("For <strong>phone</strong>"));
    assert!(out.contains("https://vpn.example.com/sub/recipient_token_123"));
    assert!(out.contains("sing-box://import-remote-profile"));
    assert!(out.contains("ripdpi://import?sub="));
    assert!(out.contains("Streisand"));
    assert!(out.contains("v2rayNG"));
    assert!(out.contains("Hiddify"));
    assert!(out.contains("Environment: <span class=\"mono\">prod</span>"));
    assert!(out.contains("noscript"));
    assert!(out.contains("Phone clock right?"));
}

#[test]
fn recipient_page_escapes_hostile_input() {
    let ctx = RecipientCtx {
        client_name: "<script>alert(1)</script>",
        host: "vpn.example.com",
        env: "prod",
        provider: "upcloud",
        subscription_url: "https://vpn.example.com/sub/x",
        singbox_deeplink: "sing-box://import-remote-profile?url=x",
        ripdpi_deeplink: "ripdpi://import?sub=https%3A%2F%2Fvpn.example.com%2Fsub%2Fx",
        apps: vec![],
    };
    let out = render(&ctx).expect("render must succeed");
    assert!(!out.contains("<script>alert(1)</script>"));
    assert!(out.contains("&#60;script&#62;") || out.contains("&lt;script&gt;"));
}
