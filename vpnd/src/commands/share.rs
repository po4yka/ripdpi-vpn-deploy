use anyhow::{anyhow, Result};
use owo_colors::OwoColorize;

use crate::cli::{ShareArgs, ShareType};
use crate::config::Context;
use crate::pages::{qr, recipient};
use crate::runner::make;
use crate::secrets::Secrets;
use crate::wizard::section;

pub async fn run(ctx: &Context, args: ShareArgs) -> Result<()> {
    section(
        "Share",
        "Bundled recipient handoff — landing page + QR + sing-box payload + per-platform app cards.",
    );

    // Decrypt happens via the Makefile, so SOPS gating and audit-log behavior match operator habit.
    if !ctx.secrets_file.is_file() {
        make::target(ctx, "decrypt").run(ctx.explain).await?;
    }

    if ctx.explain {
        eprintln!("{} would emit: sing-box bundle, recipient page, QR (if --qr)", "→".cyan());
        return Ok(());
    }

    let secrets = Secrets::load(&ctx.secrets_file)?;
    let client = secrets
        .find_client(&args.client)
        .ok_or_else(|| anyhow!("client '{}' not found in {}", args.client, ctx.secrets_file.display()))?;

    // sing-box bundle from existing script — preserves multi-host + cohort awareness.
    let singbox = make::target_with(ctx, "emit-singbox", &[("CLIENT", &args.client)]).capture(false).await?;

    let out = args.out.unwrap_or_else(|| ctx.root.join("share").join(&args.client));
    std::fs::create_dir_all(&out)?;

    // sing-box JSON (always emitted)
    std::fs::write(out.join("config.singbox.json"), &singbox.stdout)?;

    // Recipient landing page
    let host = secrets.xhttp_host.as_deref().or(secrets.server_name.as_deref()).unwrap_or("(unset)");
    let subscription_url = format!("https://{host}/sub/{}", &client.name);
    let singbox_deeplink = format!(
        "sing-box://import-remote-profile?url={}",
        urlencode(&format!("https://{host}/sub/{}.json", &client.name)),
    );
    let ripdpi_deeplink = format!("ripdpi://import?sub={}", urlencode(&subscription_url));
    let page = recipient::render(&recipient::RecipientCtx {
        client_name: &client.name,
        host,
        env: &ctx.env,
        provider: &ctx.provider,
        subscription_url: &subscription_url,
        singbox_deeplink: &singbox_deeplink,
        ripdpi_deeplink: &ripdpi_deeplink,
        apps: per_platform_apps(),
    })?;
    std::fs::write(out.join("index.html"), &page)?;

    // QR
    if args.qr {
        let payload = match args.r#type {
            ShareType::Singbox => format!("https://{host}/sub/{}.json", &client.name),
            ShareType::Uri => format!("https://{host}/sub/{}", &client.name),
        };
        qr::write_png(&payload, &out.join("qr.png"))?;
        qr::write_svg(&payload, &out.join("qr.svg"))?;
        qr::write_png(&ripdpi_deeplink, &out.join("qr-ripdpi.png"))?;
        qr::write_svg(&ripdpi_deeplink, &out.join("qr-ripdpi.svg"))?;
    }

    println!();
    println!("{} {}", "share bundle:".green().bold(), out.display());
    println!("  recipient URL:  https://{host}/sub/{}", &client.name);
    println!("  landing page:   {}", out.join("index.html").display());
    if args.qr {
        println!("  QR (png/svg):   {}", out.join("qr.png").display());
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
