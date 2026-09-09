use anyhow::Result;
use qrcode::render::svg;
use qrcode::QrCode;
use std::path::Path;

pub fn write_svg(payload: &str, out: &Path) -> Result<()> {
    let code = QrCode::new(payload.as_bytes())?;
    let s = code
        .render::<svg::Color<'_>>()
        .min_dimensions(256, 256)
        .build();
    crate::protected_file::write_private(out, s.as_bytes())?;
    Ok(())
}
