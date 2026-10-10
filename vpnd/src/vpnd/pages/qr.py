"""Pure-Python QR SVGs, published through the private atomic writer."""

import xml.etree.ElementTree as ET
import qrcode
from qrcode.image.svg import SvgPathFillImage
from vpnd.protected_file import write_private


def write_svg(payload, out):
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
    code.add_data(payload.encode("utf-8"), optimize=0)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathFillImage)
    svg = ET.fromstring(image.to_string())
    size = len(code.get_matrix())
    dimension = max(256, size * 8)
    svg.set("shape-rendering", "crispEdges")
    svg.set("width", str(dimension))
    svg.set("height", str(dimension))
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    write_private(out, ET.tostring(svg, encoding="utf-8"))
