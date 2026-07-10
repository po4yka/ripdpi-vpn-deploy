#![allow(dead_code)] // choose() and prompt() kept for Phase 1 wizard expansion

use anyhow::{anyhow, Result};
use dialoguer::theme::ColorfulTheme;
use std::fmt::Display;

/// Numbered-list choice with a default index. Mirrors Meridian's `choose()`.
pub fn choose<T: Display>(label: &str, options: &[T], default: usize) -> Result<usize> {
    if options.is_empty() {
        return Err(anyhow!("choose() called with no options"));
    }
    let theme = ColorfulTheme::default();
    let items: Vec<String> = options.iter().map(|o| o.to_string()).collect();
    let idx = dialoguer::Select::with_theme(&theme)
        .with_prompt(label)
        .items(&items)
        .default(default.min(items.len().saturating_sub(1)))
        .interact()?;
    Ok(idx)
}

/// Free-text input with an optional default shown in brackets. Empty input → default.
pub fn prompt(label: &str, default: Option<&str>) -> Result<String> {
    let theme = ColorfulTheme::default();
    let mut input = dialoguer::Input::<String>::with_theme(&theme)
        .with_prompt(label)
        .allow_empty(default.is_some());
    if let Some(d) = default {
        input = input.default(d.to_string());
    }
    Ok(input.interact_text()?)
}

/// Y/N confirmation. `default = true` shows `[Y/n]`. Mirrors Meridian's `confirm()`.
pub fn confirm(label: &str, default: bool) -> Result<bool> {
    let theme = ColorfulTheme::default();
    Ok(dialoguer::Confirm::with_theme(&theme)
        .with_prompt(label)
        .default(default)
        .interact()?)
}
