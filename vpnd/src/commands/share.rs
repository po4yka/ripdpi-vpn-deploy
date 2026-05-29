use anyhow::{anyhow, Result};
use owo_colors::OwoColorize;

use crate::cli::{ShareArgs, ShareType};
use crate::config::Context;
use crate::pages::{qr, recipient};
use crate::runner::make;
use crate::secrets::Secrets;
use crate::wizard::section;

/// Computed subscription URLs for a share bundle.
pub struct SubUrls {
    pub subscription_url: String,
    pub singbox_deeplink: String,
    pub qr_singbox: String,
    pub qr_uri: String,
}

/// Build subscription URLs from a base URL and a path segment.
///
/// `base` — e.g. `https://sub.example.com` or `https://sub.example.com:8444`
/// `segment` — opaque token or percent-encoded client name; must already be safe to embed in a path
pub fn build_sub_urls(base: &str, segment: &str) -> SubUrls {
    let subscription_url = format!("{base}/sub/{segment}");
    let singbox_deeplink = format!(
        "sing-box://import-remote-profile?url={}",
        urlencode(&format!("{base}/sub/{segment}.json"))
    );
    let qr_singbox = format!("{base}/sub/{segment}.json");
    let qr_uri = format!("{base}/sub/{segment}");
    SubUrls { subscription_url, singbox_deeplink, qr_singbox, qr_uri }
}

/// Validate that a token contains only base64url alphabet characters.
fn validate_token(token: &str) -> Result<()> {
    let valid = token.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-');
    if !valid {
        return Err(anyhow!(
            "token contains invalid characters — only base64url alphabet [A-Za-z0-9_-] is allowed"
        ));
    }
    Ok(())
}

pub async fn run(ctx: &Context, args: ShareArgs) -> Result<()> {
    section(
        "Share",
        "Bundled recipient handoff — landing page + QR + sing-box payload + per-platform app cards.",
    );

    // Decrypt happens via the Makefile, so SOPS gating and audit-log behavior match operator habit.
    if !ctx.secrets_file.is_file() {
        make::target(ctx, "decrypt").run(ctx.explain).await?;
        ctx.secure_secrets_file();
    }

    if ctx.explain {
        eprintln!("{} would emit: sing-box bundle, recipient page, QR (if --qr)", "→".cyan());
        return Ok(());
    }

    let secrets = Secrets::load(&ctx.secrets_file)?;
    let client = secrets
        .find_client(&args.client)
        .ok_or_else(|| anyhow!("client '{}' not found in the decrypted secrets file", args.client))?;

    // Transport host — used when no subscription host is configured.
    let host = secrets.xhttp_host.as_deref().or(secrets.server_name.as_deref()).unwrap_or("(unset)");

    // Build the base URL and path segment according to whether a token was supplied.
    let (base, segment) = if let Some(ref tok) = args.token {
        validate_token(tok)?;
        let sub_host = secrets.subscription_host().unwrap_or(host);
        let base = match secrets.subscription_port() {
            Some(443) | None => format!("https://{sub_host}"),
            Some(port) => format!("https://{sub_host}:{port}"),
        };
        (base, tok.clone())
    } else {
        eprintln!(
            "{} no --token supplied — subscription URL uses the enumerable client name.\n  \
             Run `make issue-sub-token CLIENT={} --print-token-only` and pass `--token <TOKEN>` \
             to use an opaque subscription token.",
            "WARNING:".yellow().bold(),
            &args.client,
        );
        (format!("https://{host}"), urlencode(&client.name))
    };

    let urls = build_sub_urls(&base, &segment);

    // sing-box bundle from existing script — preserves multi-host + cohort awareness.
    let singbox = make::target_with(ctx, "emit-singbox", &[("CLIENT", &args.client)]).capture(false).await?;

    let out = args.out.unwrap_or_else(|| ctx.root.join("share").join(&args.client));
    std::fs::create_dir_all(&out)?;

    // sing-box JSON (always emitted)
    std::fs::write(out.join("config.singbox.json"), &singbox.stdout)?;

    // Recipient landing page. ripdpi:// one-tap import derives from the
    // (token-aware) subscription URL computed above.
    let ripdpi_deeplink = format!("ripdpi://import?sub={}", urlencode(&urls.subscription_url));
    let page = recipient::render(&recipient::RecipientCtx {
        client_name: &client.name,
        host,
        env: &ctx.env,
        provider: &ctx.provider,
        subscription_url: &urls.subscription_url,
        singbox_deeplink: &urls.singbox_deeplink,
        ripdpi_deeplink: &ripdpi_deeplink,
        apps: per_platform_apps(),
    })?;
    std::fs::write(out.join("index.html"), &page)?;

    // QR
    if args.qr {
        let payload = match args.r#type {
            ShareType::Singbox => &urls.qr_singbox,
            ShareType::Uri => &urls.qr_uri,
        };
        // Emit SVG QR codes only. write_png produces a PBM file renamed to
        // .png (no real PNG encoder — no-new-deps constraint), which browsers
        // refuse to render; the recipient page references qr.svg / qr-ripdpi.svg.
        qr::write_svg(payload, &out.join("qr.svg"))?;
        qr::write_svg(&ripdpi_deeplink, &out.join("qr-ripdpi.svg"))?;
    }

    println!();
    println!("{} {}", "share bundle:".green().bold(), out.display());
    println!("  recipient URL:  {}", urls.subscription_url);
    println!("  landing page:   {}", out.join("index.html").display());
    if args.qr {
        println!("  QR (svg):       {}", out.join("qr.svg").display());
    }
    println!();
    println!(
        "  Hand the recipient {} — it has the QR, deep link, and per-platform app cards.",
        "the URL".bold()
    );
    Ok(())
}

fn per_platform_apps() -> Vec<recipient::AppCard> {
    vec![
        recipient::AppCard {
            platform: "iOS".to_string(),
            primary: ("Streisand", "https://apps.apple.com/app/streisand/id6450534064").into(),
            also: vec![("v2RayTun", "https://apps.apple.com/app/v2raytun/id6476628951").into()],
        },
        recipient::AppCard {
            platform: "Android".to_string(),
            primary: ("v2rayNG", "https://github.com/2dust/v2rayNG/releases/latest").into(),
            also: vec![("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest").into()],
        },
        recipient::AppCard {
            platform: "macOS / Windows / Linux".to_string(),
            primary: ("sing-box", "https://sing-box.sagernet.org/installation/package-manager/").into(),
            also: vec![("Hiddify", "https://github.com/hiddify/hiddify-app/releases/latest").into()],
        },
    ]
}

pub fn urlencode(s: &str) -> String {
    use percent_encoding::{utf8_percent_encode, NON_ALPHANUMERIC};
    utf8_percent_encode(s, NON_ALPHANUMERIC).to_string()
}
