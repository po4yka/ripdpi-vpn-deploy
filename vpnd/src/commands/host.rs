use anyhow::{anyhow, Result};
use comfy_table::{presets::UTF8_FULL, ContentArrangement, Table};
use owo_colors::OwoColorize;

use crate::cli::{HostAction, HostArgs};
use crate::config::Context;
use crate::state::{Host, Registry};

pub async fn run(_ctx: &Context, args: HostArgs) -> Result<()> {
    let mut reg = Registry::load()?;
    match args.action {
        HostAction::List { json } => {
            if json {
                println!("{}", list_json(&reg)?);
            } else {
                list(&reg);
            }
        }
        HostAction::Show { name, json } => {
            let host = reg
                .get(&name)
                .ok_or_else(|| anyhow!("no such host: {}", name))?;
            // The record is machine-readable in both modes; --json picks the
            // compact single-line form for pipelines.
            if json {
                println!("{}", serde_json::to_string(host)?);
            } else {
                println!("{}", serde_json::to_string_pretty(host)?);
            }
        }
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

/// Machine-readable host list: a JSON array in registry (name-sorted) order.
fn list_json(reg: &Registry) -> Result<String> {
    #[derive(serde::Serialize)]
    struct HostEntry<'a> {
        name: &'a str,
        env: &'a str,
        provider: &'a str,
        ipv4: Option<&'a str>,
        ipv6: Option<&'a str>,
        deployed_with: Option<&'a str>,
    }
    let entries: Vec<HostEntry> = reg
        .hosts
        .iter()
        .map(|(name, host)| HostEntry {
            name,
            env: &host.env,
            provider: &host.provider,
            ipv4: host.ipv4.as_deref(),
            ipv6: host.ipv6.as_deref(),
            deployed_with: host.deployed_with.as_deref(),
        })
        .collect();
    Ok(serde_json::to_string(&entries)?)
}
