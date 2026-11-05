import re
import xml.etree.ElementTree as ET

import pytest
import qrcode

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


def _oracle(payload):
    # Library oracle with literal parameters: byte mode only (no mode optimisation), level M, 4-module quiet zone.
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    code.add_data(payload.encode("utf-8"), optimize=0)
    code.make(fit=True)
    return code.get_matrix()


# A numeric run inside letters changes the encoding when mode optimisation is on; the long payload forces a matrix above 32 modules.
@pytest.mark.parametrize(
    "payload",
    [PAYLOAD, "None", "ABC" + "1" * 40 + "xyz", "https://vpn.example.com/sub/" + "tok0123456789" * 8],
)
def test_write_svg_draws_the_expected_matrix_and_scales(tmp_path, payload):
    path = tmp_path / "qr.svg"
    write_svg(payload, path)
    root = ET.parse(path).getroot()
    d = root.find("{http://www.w3.org/2000/svg}path").attrib["d"]
    dark = {(int(x), int(y)) for x, y in re.findall(r"M(\d+),(\d+)H", d)}
    matrix = _oracle(payload)
    assert dark == {(x, y) for y, row in enumerate(matrix) for x, cell in enumerate(row) if cell}
    side = len(matrix)
    assert root.attrib["viewBox"] == f"0 0 {side} {side}"
    expected = str(max(256, side * 8))
    assert root.attrib["width"] == expected and root.attrib["height"] == expected
