//! Integration tests for pages::qr SVG output.
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
