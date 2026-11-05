"""Pure-Python QR SVGs, published through the private atomic writer."""

import xml.etree.ElementTree as ET
import qrcode
from qrcode.image.svg import SvgPathFillImage
from vpnd.protected_file import write_private


def write_svg(payload, out):
    # Library defaults: error correction M, 4-module quiet zone, smallest fitting version. Tests pin all three.
    code = qrcode.QRCode()
    code.add_data(payload.encode(), optimize=0)  # pragma: no mutate (qrcode tests optimize by truthiness, so None equals 0)
    code.make()
    image = code.make_image(image_factory=SvgPathFillImage)
    svg = ET.fromstring(image.to_string())
    size = len(code.get_matrix())
    dimension = max(256, size * 8)
    svg.set("shape-rendering", "crispEdges")
    svg.set("width", str(dimension))
    svg.set("height", str(dimension))
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    # The SVG is pure ASCII, so every ElementTree encoding spelling emits the same bytes.
    write_private(out, ET.tostring(svg, encoding="utf-8"))  # pragma: no mutate
