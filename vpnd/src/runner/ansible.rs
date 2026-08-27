#![allow(dead_code)] // builders intentionally kept for future commands and tests

use crate::config::Context;
use crate::runner::Cmd;
use crate::state::{ipv4_limit, Host};
use anyhow::{anyhow, Context as _, Result};
use std::collections::BTreeSet;

#[cfg(test)]
fn fake_ctx() -> Context {
    use std::path::PathBuf;
    Context {
        root: PathBuf::from("/repo"),
        ansible_dir: PathBuf::from("/repo/ansible"),
        tf_root: PathBuf::from("/repo/terraform/providers/upcloud"),
        env: "prod".into(),
        provider: "upcloud".into(),
        sops_file: PathBuf::from("/config/prod.secrets.sops.yaml"),
        secrets_file: PathBuf::from("/tmp/vpn-prod.secrets.yaml"),
        config_dir: PathBuf::from("/config"),
        explain: false,
        yes: false,
        json: false,
    }
}

/// Builder for `ansible-playbook playbooks/<name>.yml` pinned to the repo's ansible config.
pub fn playbook(ctx: &Context, name: &str) -> Cmd {
    let path = ctx
        .ansible_dir
        .join("playbooks")
        .join(format!("{name}.yml"));
    Cmd::new("ansible-playbook")
        .arg(path.to_string_lossy().to_string())
        .arg("--inventory")
        .arg(ctx.ansible_dir.join("inventory/generated.ini"))
        .cwd(ctx.root.clone())
        .env(
            "ANSIBLE_CONFIG",
            ctx.ansible_cfg().to_string_lossy().to_string(),
        )
        .env(
            "VPN_SECRETS_FILE",
            ctx.secrets_file.to_string_lossy().to_string(),
        )
        .sensitive(ctx.secrets_file.to_string_lossy())
        .describe(format!("ansible-playbook playbooks/{name}.yml"))
}

/// Resolve exact inventory host keys, never IPs or unchecked Ansible patterns.
/// Registry addresses identify public endpoints; ansible_host may be a separate
/// management address, so prefer the rendered vpn_service_address contract.
pub async fn scoped_limit(ctx: &Context, host: Option<(&str, &Host)>) -> Result<String> {
    let expected_ip = host
        .map(|(name, record)| ipv4_limit(name, record))
        .transpose()?;
    let inventory = Cmd::new("ansible-inventory")
        .arg("--inventory")
        .arg(ctx.ansible_dir.join("inventory/generated.ini"))
        .arg("--list")
        .env("ANSIBLE_CONFIG", ctx.ansible_cfg().to_string_lossy())
        .cwd(ctx.root.clone())
        .describe("resolve exact inventory hosts for the selected environment and provider")
        .capture(ctx.explain)
        .await?;
    if ctx.explain {
        return Ok("<validated inventory host keys>".into());
    }
    inventory_limit(
        &inventory.stdout,
        &ctx.env,
        &ctx.provider,
        expected_ip.as_deref(),
    )
    .with_context(|| match host {
        Some((name, _)) => format!("resolve inventory target for host '{name}'"),
        None => "resolve inventory targets for the active environment/provider".into(),
    })
}

fn inventory_limit(
    raw: &str,
    env: &str,
    provider: &str,
    expected_ip: Option<&str>,
) -> Result<String> {
    let inventory: serde_json::Value =
        serde_json::from_str(raw).context("parse Ansible inventory")?;
    let hostvars = inventory["_meta"]["hostvars"]
        .as_object()
        .ok_or_else(|| anyhow!("inventory is missing hostvars"))?;
    let mut pending = vec!["vpn".to_string()];
    let mut visited = BTreeSet::new();
    let mut candidates = BTreeSet::new();
    while let Some(group) = pending.pop() {
        if !visited.insert(group.clone()) {
            continue;
        }
        let value = inventory
            .get(&group)
            .and_then(serde_json::Value::as_object)
            .ok_or_else(|| anyhow!("inventory is missing group '{group}'"))?;
        if let Some(values) = value.get("hosts") {
            for value in values
                .as_array()
                .ok_or_else(|| anyhow!("invalid inventory hosts"))?
            {
                candidates.insert(
                    value
                        .as_str()
                        .ok_or_else(|| anyhow!("invalid inventory hostname"))?
                        .to_owned(),
                );
            }
        }
        if let Some(children) = value.get("children") {
            for child in children
                .as_array()
                .ok_or_else(|| anyhow!("invalid inventory groups"))?
            {
                pending.push(
                    child
                        .as_str()
                        .ok_or_else(|| anyhow!("invalid inventory group name"))?
                        .to_owned(),
                );
            }
        }
    }
    let mut selected = Vec::new();
    for name in candidates {
        let vars = hostvars
            .get(&name)
            .ok_or_else(|| anyhow!("missing variables for inventory host '{name}'"))?;
        let host_env = vars["env"]
            .as_str()
            .ok_or_else(|| anyhow!("missing env for inventory host '{name}'"))?;
        let host_provider = vars["provider"]
            .as_str()
            .ok_or_else(|| anyhow!("missing provider for inventory host '{name}'"))?;
        if host_env != env || host_provider != provider {
            continue;
        }
        let address = vars
            .get("vpn_service_address")
            .or_else(|| vars.get("ansible_host"))
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| anyhow!("missing address for inventory host '{name}'"))?;
        let address: std::net::Ipv4Addr = address
            .parse()
            .with_context(|| format!("invalid IPv4 for inventory host '{name}'"))?;
        if expected_ip.is_some_and(|ip| ip != address.to_string()) {
            continue;
        }
        if name.is_empty()
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
            || inventory.get(&name).is_some()
            || matches!(name.as_str(), "all" | "ungrouped")
        {
            return Err(anyhow!("inventory host '{name}' is not a safe exact limit"));
        }
        selected.push(name);
    }
    if selected.is_empty() || (expected_ip.is_some() && selected.len() != 1) {
        return Err(anyhow!(
            "expected {} matching inventory hosts, found {}",
            if expected_ip.is_some() {
                "exactly one"
            } else {
                "at least one"
            },
            selected.len()
        ));
    }
    Ok(selected.join(","))
}

pub fn site(ctx: &Context) -> Cmd {
    playbook(ctx, "site")
}

pub fn verify(ctx: &Context) -> Cmd {
    playbook(ctx, "verify")
}

pub fn smoke(ctx: &Context) -> Cmd {
    playbook(ctx, "smoke-test")
}

pub fn rotate(ctx: &Context) -> Cmd {
    playbook(ctx, "rotate-credentials")
}

pub fn dry_run(ctx: &Context) -> Cmd {
    site(ctx)
        .arg("--check")
        .arg("--diff")
        .describe("ansible-playbook site.yml --check --diff")
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]
    use super::*;

    fn scoped_inventory() -> serde_json::Value {
        serde_json::json!({
            "vpn": {"children": ["cohort"]},
            "cohort": {"hosts": ["fixture-node", "staging-node", "other-provider"]},
            "_meta": {"hostvars": {
                "fixture-node": {"env": "prod", "provider": "upcloud", "ansible_host": "100.64.0.5", "vpn_service_address": "203.0.113.5"},
                "staging-node": {"env": "staging", "provider": "upcloud", "ansible_host": "203.0.113.6"},
                "other-provider": {"env": "prod", "provider": "vultr", "ansible_host": "203.0.113.7"}
            }}
        })
    }

    #[test]
    fn inventory_scope_uses_public_address_and_exact_host_key() {
        let raw = scoped_inventory().to_string();
        assert_eq!(
            inventory_limit(&raw, "prod", "upcloud", Some("203.0.113.5")).unwrap(),
            "fixture-node"
        );
        assert_eq!(
            inventory_limit(&raw, "prod", "upcloud", None).unwrap(),
            "fixture-node"
        );
        assert!(inventory_limit(&raw, "prod", "upcloud", Some("100.64.0.5")).is_err());
        assert!(inventory_limit(&raw, "prod", "upcloud", Some("203.0.113.6")).is_err());
        assert!(inventory_limit(&raw, "prod", "hetzner", None).is_err());
    }

    #[test]
    fn inventory_scope_rejects_ambiguous_addresses_and_group_collisions() {
        let mut inventory = scoped_inventory();
        inventory["_meta"]["hostvars"]["staging-node"]["env"] = "prod".into();
        inventory["_meta"]["hostvars"]["staging-node"]["ansible_host"] = "203.0.113.5".into();
        assert!(inventory_limit(
            &inventory.to_string(),
            "prod",
            "upcloud",
            Some("203.0.113.5")
        )
        .is_err());
        let mut inventory = scoped_inventory();
        inventory["fixture-node"] = serde_json::json!({"hosts": ["staging-node"]});
        assert!(inventory_limit(
            &inventory.to_string(),
            "prod",
            "upcloud",
            Some("203.0.113.5")
        )
        .is_err());
    }

    #[test]
    fn inventory_scope_rejects_pattern_names_and_missing_scope_metadata() {
        for name in [
            "all",
            "vpn:*",
            "host,other",
            "@targets",
            "[nodes]",
            "!other",
        ] {
            let mut inventory = scoped_inventory();
            let vars = inventory["_meta"]["hostvars"]["fixture-node"].take();
            inventory["_meta"]["hostvars"][name] = vars;
            inventory["cohort"]["hosts"][0] = name.into();
            assert!(
                inventory_limit(&inventory.to_string(), "prod", "upcloud", None).is_err(),
                "{name}"
            );
        }
        let mut inventory = scoped_inventory();
        inventory["_meta"]["hostvars"]["fixture-node"]["env"] = serde_json::Value::Null;
        assert!(inventory_limit(&inventory.to_string(), "prod", "upcloud", None).is_err());
    }

    #[test]
    fn playbook_program_is_ansible_playbook() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "site").explain();
        assert!(
            s.contains("ansible-playbook"),
            "program must be ansible-playbook, got: {s}"
        );
    }

    #[test]
    fn playbook_path_contains_playbook_name() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "rotate-credentials").explain();
        assert!(
            s.contains("rotate-credentials.yml"),
            "playbook path must include name.yml, got: {s}"
        );
    }

    #[test]
    fn playbook_sets_ansible_config_env() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "site").explain();
        assert!(
            s.contains("ANSIBLE_CONFIG="),
            "must set ANSIBLE_CONFIG, got: {s}"
        );
        assert!(
            s.contains("ansible.cfg"),
            "ANSIBLE_CONFIG must point to ansible.cfg, got: {s}"
        );
    }

    #[test]
    fn playbook_sets_vpn_secrets_file_env() {
        let ctx = fake_ctx();
        let s = playbook(&ctx, "site").explain();
        assert!(
            s.contains("VPN_SECRETS_FILE="),
            "must set VPN_SECRETS_FILE, got: {s}"
        );
        assert!(
            s.contains("/tmp/vpn-prod.secrets.yaml"),
            "VPN_SECRETS_FILE must be secrets_file, got: {s}"
        );
    }

    #[test]
    fn dry_run_appends_check_and_diff() {
        let ctx = fake_ctx();
        let s = dry_run(&ctx).explain();
        assert!(
            s.contains("--check"),
            "dry_run must include --check, got: {s}"
        );
        assert!(
            s.contains("--diff"),
            "dry_run must include --diff, got: {s}"
        );
    }

    #[test]
    fn site_uses_site_playbook() {
        let ctx = fake_ctx();
        let s = site(&ctx).explain();
        assert!(s.contains("site.yml"), "site() must use site.yml, got: {s}");
    }

    #[test]
    fn rotate_uses_rotate_credentials_playbook() {
        let ctx = fake_ctx();
        let s = rotate(&ctx).explain();
        assert!(
            s.contains("rotate-credentials.yml"),
            "rotate() must use rotate-credentials.yml, got: {s}"
        );
    }
}
