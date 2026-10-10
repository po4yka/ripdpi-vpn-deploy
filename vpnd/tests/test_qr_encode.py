import xml.etree.ElementTree as ET
from vpnd.pages.qr import write_svg

PAYLOAD = "https://vpn.example.com/sub/phone"


# Rust test: vpnd/tests/qr_encode.rs::write_svg_produces_file
def test_write_svg_produces_file(tmp_path):
    path = tmp_path / "qr.svg"
    write_svg(PAYLOAD, path)
    assert path.is_file() and path.stat().st_size > 0


# Rust test: vpnd/tests/qr_encode.rs::write_svg_output_is_valid_xml_with_svg_root
def test_write_svg_output_is_valid_xml_with_svg_root(tmp_path):
    path = tmp_path / "qr.svg"
    write_svg(PAYLOAD, path)
    assert "<svg" in path.read_text() and "</svg>" in path.read_text()
    assert ET.parse(path).getroot().tag.endswith("svg")


# Rust test: vpnd/tests/qr_encode.rs::write_svg_contains_rect_or_path_elements
def test_write_svg_contains_rect_or_path_elements(tmp_path):
    path = tmp_path / "qr.svg"
    write_svg(PAYLOAD, path)
    assert "<rect" in path.read_text() or "<path" in path.read_text()


# Rust test: vpnd/tests/qr_encode.rs::write_svg_min_dimensions_at_least_256
def test_write_svg_min_dimensions_at_least_256(tmp_path):
    path = tmp_path / "qr.svg"
    write_svg(PAYLOAD, path)
    root = ET.parse(path).getroot()
    assert int(root.attrib["width"]) >= 256 and int(root.attrib["height"]) >= 256


def test_qr_has_original_white_canvas_and_crisp_edges(tmp_path):
    path = tmp_path / "qr.svg"
    write_svg(PAYLOAD, path)
    root = ET.parse(path).getroot()
    canvas = root.find("{http://www.w3.org/2000/svg}rect")
    assert canvas is not None
    assert canvas.attrib["fill"].lower() in {"white", "#fff", "#ffffff"}
    assert canvas.attrib["width"] == "100%" and canvas.attrib["height"] == "100%"
    assert canvas.attrib.get("x", "0") == "0" and canvas.attrib.get("y", "0") == "0"
    assert root.attrib["shape-rendering"] == "crispEdges"
    assert root.find("{http://www.w3.org/2000/svg}path") is not None
