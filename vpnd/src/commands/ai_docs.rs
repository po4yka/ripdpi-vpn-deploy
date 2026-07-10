use anyhow::{anyhow, Context as _, Result};
use owo_colors::OwoColorize;
use std::path::Path;

use crate::cli::AiDocsArgs;
use crate::config::Context;

/// Emit machine-readable endpoints for AI assistants (mirrors Meridian's website endpoints).
///
/// - `llms.txt`         — index of doc paths
/// - `llms-full.txt`    — every `docs/*.md` concatenated
/// - `md/<slug>.md`     — raw markdown per doc
pub async fn run(ctx: &Context, args: AiDocsArgs) -> Result<()> {
    let out = args.out.unwrap_or_else(|| ctx.root.join("ai-docs"));
    let md_dir = out.join("md");
    if !ctx.explain {
        std::fs::create_dir_all(&md_dir)?;
    }

    let docs = ctx.root.join("docs");
    let mut index = String::from("# vpn-deploy docs index\n\n");
    let mut full = String::new();

    let mut entries: Vec<_> = std::fs::read_dir(&docs)?
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().is_some_and(|x| x == "md"))
        .collect();
    entries.sort_by_key(|e| e.path());

    for e in entries {
        let path = e.path();
        let slug = path
            .file_stem()
            .ok_or_else(|| anyhow!("doc path has no file stem: {}", path.display()))?
            .to_string_lossy()
            .into_owned();
        let body =
            std::fs::read_to_string(&path).with_context(|| format!("read {}", path.display()))?;
        index.push_str(&format!("- [{}](/md/{}.md)\n", slug, slug));
        full.push_str(&format!("\n\n---\n\n## {}\n\n{}", slug, body));
        if !ctx.explain {
            std::fs::write(md_dir.join(format!("{slug}.md")), &body)?;
        }
    }

    if ctx.explain {
        eprintln!(
            "{} would emit llms.txt, llms-full.txt, and per-doc markdown to {}",
            "→".cyan(),
            out.display()
        );
        return Ok(());
    }

    std::fs::write(out.join("llms.txt"), &index)?;
    std::fs::write(out.join("llms-full.txt"), &full)?;

    println!("{} ai-docs emitted to {}", "✓".green(), out.display());
    print_endpoints(&out);
    Ok(())
}

fn print_endpoints(out: &Path) {
    println!();
    println!("  llms.txt:       {}", out.join("llms.txt").display());
    println!("  llms-full.txt:  {}", out.join("llms-full.txt").display());
    println!("  per-doc:        {}/", out.join("md").display());
}
