from vpnd.pages.recipient import AppCard, Link, RecipientCtx, render


def ctx(client="phone"):
    return RecipientCtx(
        client,
        "vpn.example.com",
        "prod",
        "upcloud",
        "https://vpn.example.com/sub/phone",
        "sing-box://import-remote-profile?url=x",
        "ripdpi://import?sub=x",
        [
            AppCard("iOS", Link("Streisand", "https://apps.apple.com/app/streisand/id6450534064")),
            AppCard(
                "Android",
                Link("v2rayNG", "https://github.com/2dust/v2rayNG/releases/latest"),
                [Link("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest")],
            ),
        ],
    )


# Rust test: vpnd/tests/recipient_render.rs::recipient_page_renders_with_expected_sections
def test_recipient_page_renders_with_expected_sections():
    out = render(ctx())
    for value in [
        "Connect to vpn.example.com",
        "For <strong>phone</strong>",
        "https://vpn.example.com/sub/phone",
        "sing-box://import-remote-profile",
        "ripdpi://import?sub=",
        "Streisand",
        "v2rayNG",
        "Hiddify",
        'Environment: <span class="mono">prod</span>',
        "noscript",
        "Phone clock right?",
    ]:
        assert value in out


# Rust test: vpnd/tests/recipient_render.rs::recipient_page_escapes_hostile_input
def test_recipient_page_escapes_hostile_input():
    out = render(ctx("<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
