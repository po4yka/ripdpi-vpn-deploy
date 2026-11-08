#!/usr/bin/env python3
"""Write one owner-only INCY config from an issued device artifact, ready for Home -> Paste."""
import base64
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from client_payload import incy_links, write_incy_links


def _rank(link):
    if urlsplit(link).scheme == 'hysteria2':
        return 2
    return 1 if parse_qs(urlsplit(link).query).get('type') == ['xhttp'] else 0


def config_lines(artifact):
    """Return one line per server: REALITY first, then XHTTP, Hysteria2 and AmneziaWG."""
    links = sorted(incy_links(artifact['profile']), key=_rank)
    awg = ['amneziawg://' + base64.urlsafe_b64encode(conf.encode()).decode().rstrip('=')
           for _, conf in sorted(artifact.get('amneziawg_configs', {}).items())]
    lines = []
    for index, link in enumerate([*links, *awg]):
        # Recipients see these names; outbound tags name the infrastructure.
        name = f'Запасной {index}' if index else 'Основной'
        name += {'hysteria2': ' (UDP)', 'amneziawg': ' (AWG)'}.get(urlsplit(link).scheme, '')
        lines.append(link.partition('#')[0] + '#' + quote(name))
    return lines


def main(argv):
    if len(argv) != 3:
        print('usage: incy_config.py <recipient.json> <new output file>', file=sys.stderr)
        return 2
    source, output = argv[1:]
    try:
        if os.stat(source).st_mode & 0o077:
            raise ValueError('unsafe-recipient-input')
        lines = config_lines(json.loads(Path(source).read_text(encoding='utf-8')))
        write_incy_links(output, lines)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        detail = str(error) if isinstance(error, ValueError) and re.fullmatch('[a-z0-9-]+', str(error)) else 'refused'
        print('incy-config: ' + detail, file=sys.stderr)
        return 2
    print(f'wrote {len(lines)} INCY servers to {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
