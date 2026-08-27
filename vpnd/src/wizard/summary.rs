use comfy_table::{presets::UTF8_FULL, Cell, ContentArrangement, Table};
use owo_colors::OwoColorize;

/// Pre-commit summary panel: a labelled key-value table shown before the
/// final confirm() gate. Always print this before any state-changing op.
#[derive(Default)]
pub struct Summary {
    title: String,
    rows: Vec<(String, String)>,
}

impl Summary {
    pub fn new(title: impl Into<String>) -> Self {
        Self {
            title: title.into(),
            rows: Vec::new(),
        }
    }

    pub fn add(&mut self, key: impl Into<String>, value: impl Into<String>) -> &mut Self {
        self.rows.push((key.into(), value.into()));
        self
    }

    /// Read-only view of the collected rows, for contract tests.
    pub fn rows(&self) -> &[(String, String)] {
        &self.rows
    }

    pub fn render(&self) {
        println!();
        println!("{}", self.title.bold().underline());
        let mut t = Table::new();
        t.load_preset(UTF8_FULL)
            .set_content_arrangement(ContentArrangement::Dynamic);
        for (k, v) in &self.rows {
            t.add_row(vec![Cell::new(k), Cell::new(v)]);
        }
        println!("{t}");
    }
}
