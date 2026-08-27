//! Integration tests for pages::qr SVG and PNG (PPM-shaped) output.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use tempfile::TempDir;
use vpnd::pages::qr;

const PAYLOAD: &str = "https://vpn.example.com/sub/phone";

#[test]
fn write_svg_produces_file() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().join("qr.svg");
    qr::write_svg(PAYLOAD, &out).expect("write_svg must succeed");
    assert!(out.is_file(), "qr.svg must be created");
    assert!(
        out.metadata().unwrap().len() > 0,
        "qr.svg must be non-empty"
    );
}

#[test]
fn write_svg_output_is_valid_xml_with_svg_root() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().join("qr.svg");
    qr::write_svg(PAYLOAD, &out).unwrap();
    let contents = std::fs::read_to_string(&out).unwrap();
    assert!(
        contents.contains("<svg") && contents.contains("</svg>"),
        "SVG must contain <svg> root element, got {} bytes",
        contents.len()
    );
}

#[test]
fn write_svg_contains_rect_or_path_elements() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().join("qr.svg");
    qr::write_svg(PAYLOAD, &out).unwrap();
    let contents = std::fs::read_to_string(&out).unwrap();
    // QR SVG renderers emit either <rect> or <path> for the modules
    assert!(
        contents.contains("<rect") || contents.contains("<path"),
        "SVG must contain QR module elements (<rect> or <path>), snippet: {}",
        &contents[..contents.len().min(200)]
    );
}

#[test]
fn write_png_produces_file() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().join("qr.png");
    qr::write_png(PAYLOAD, &out).expect("write_png must succeed");
    assert!(out.is_file(), "qr.png must be created");
    assert!(
        out.metadata().unwrap().len() > 0,
        "qr.png must be non-empty"
    );
}

#[test]
fn write_png_is_ppm_format_with_correct_dimensions() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().join("qr.png");
    qr::write_png(PAYLOAD, &out).unwrap();
    let contents = std::fs::read_to_string(&out).unwrap();
    // The write_png implementation emits a P1 (bitmap PPM / PBM) file
    assert!(
        contents.starts_with("P1\n"),
        "output must be PBM P1 format, got: {:?}",
        &contents[..20.min(contents.len())]
    );

    // Parse dimensions from second line: "<width> <height>"
    let mut lines = contents.lines();
    let _magic = lines.next().unwrap(); // P1
    let dims = lines.next().expect("must have dimensions line");
    let mut parts = dims.split_whitespace();
    let width: usize = parts
        .next()
        .unwrap()
        .parse()
        .expect("width must be integer");
    let height: usize = parts
        .next()
        .unwrap()
        .parse()
        .expect("height must be integer");

    // A QR code with quiet zone must be at least 21x21 modules for version 1
    assert!(width >= 21, "QR width must be at least 21, got {width}");
    assert!(height >= 21, "QR height must be at least 21, got {height}");
    assert_eq!(
        width, height,
        "QR code must be square, got {width}x{height}"
    );
}

#[test]
fn write_svg_min_dimensions_at_least_256() {
    let dir = TempDir::new().unwrap();
    let out = dir.path().join("qr.svg");
    qr::write_svg(PAYLOAD, &out).unwrap();
    let contents = std::fs::read_to_string(&out).unwrap();
    let start = contents.find("<svg").expect("SVG root must exist");
    let tag_end = contents[start..].find('>').expect("SVG root must close");
    let tag = &contents[start..start + tag_end];
    for attribute in ["width", "height"] {
        let marker = format!("{attribute}=\"");
        let start = tag.find(&marker).expect("dimension attribute must exist") + marker.len();
        let value = &tag[start..];
        let end = value.find('"').expect("dimension value must close");
        let value: u32 = value[..end].parse().expect("dimension must be numeric");
        assert!(value >= 256, "SVG {attribute} must be >= 256, got {value}");
    }
}
