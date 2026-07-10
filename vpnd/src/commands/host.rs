use anyhow::{anyhow, Result};
use comfy_table::{presets::UTF8_FULL, ContentArrangement, Table};
use owo_colors::OwoColorize;

use crate::cli::{HostAction, HostArgs};
use crate::config::Context;
use crate::state::{Host, Registry};

pub async fn run(_ctx: &Context, args: HostArgs) -> Result<()> {
    let mut reg = Registry::load()?;
    match args.action {
        HostAction::List => list(&reg),
        HostAction::Show { name } => show(&reg, &name)?,
        HostAction::Add {
            name,
            env,
            provider,
            ipv4,
            ipv6,
        } => {
            reg.upsert(
                &name,
                Host {
                    env,
                    provider,
                    ipv4,
                    ipv6,
                    deployed_with: None,
                },
            );
            reg.save()?;
            eprintln!("{} added '{}'", "✓".green(), name);
        }
        HostAction::Remove { name } => {
            if reg.remove(&name).is_none() {
                return Err(anyhow!("no such host: {}", name));
            }
            reg.save()?;
            eprintln!("{} removed '{}'", "✓".green(), name);
        }
    }
    Ok(())
}

fn list(reg: &Registry) {
    if reg.hosts.is_empty() {
        eprintln!(
            "{}",
            "(no hosts registered — run `vpnd host add <name> --env … --provider …`)".dimmed()
        );
        return;
    }
    let mut t = Table::new();
    t.load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic);
    t.set_header(vec![
        "name",
        "env",
        "provider",
        "ipv4",
        "ipv6",
        "deployed_with",
    ]);
    for (name, h) in &reg.hosts {
        t.add_row(vec![
            name.clone(),
            h.env.clone(),
            h.provider.clone(),
            h.ipv4.clone().unwrap_or_default(),
            h.ipv6.clone().unwrap_or_default(),
            h.deployed_with.clone().unwrap_or_default(),
        ]);
    }
    println!("{t}");
}

fn show(reg: &Registry, name: &str) -> Result<()> {
    let h = reg
        .get(name)
        .ok_or_else(|| anyhow!("no such host: {}", name))?;
    println!("{}", serde_json::to_string_pretty(h)?);
    Ok(())
}
