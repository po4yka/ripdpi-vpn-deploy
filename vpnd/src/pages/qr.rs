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

/// Renders a monochrome PPM and renames to .png for convenience.
///
/// We avoid the heavy `image` crate dependency by emitting a 1-bit
/// SVG-derived raster — operators using a polished PNG can run
/// `qrencode` (already in scripts/emit-qr.sh) for a fancier render.
pub fn write_png(payload: &str, out: &Path) -> Result<()> {
    let code = QrCode::new(payload.as_bytes())?;
    let pixels = code
        .render::<char>()
        .quiet_zone(true)
        .module_dimensions(1, 1)
        .dark_color('#')
        .light_color('.')
        .build();
    let dim = pixels.lines().count();
    let width = pixels
        .lines()
        .next()
        .map(|l| l.chars().count())
        .unwrap_or(dim);
    let mut ppm = format!("P1\n{width} {dim}\n");
    for line in pixels.lines() {
        for ch in line.chars() {
            ppm.push(if ch == '#' { '1' } else { '0' });
            ppm.push(' ');
        }
        ppm.push('\n');
    }
    // Write the .ppm payload but with the .png filename — operators can
    // post-process; emit-qr.sh remains the canonical PNG path.
    crate::protected_file::write_private(out, ppm.as_bytes())?;
    Ok(())
}
