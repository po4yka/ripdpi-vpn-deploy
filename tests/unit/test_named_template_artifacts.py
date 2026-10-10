"""Named rendering prevents markup injection without changing config credentials."""

from html.parser import HTMLParser
import json
import subprocess
import xml.etree.ElementTree as ET

import pytest

from template_render import render_fragment, render_template


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize("name", ["page.html", "page.html.j2", "page.HTML.J2"])
def test_html_value_is_text_instead_of_an_executable_element(tmp_path, name):
    value = '"><img src=x onerror="alert(1)">&\''
    path = tmp_path / name
    path.write_text("<p>{{ value }}</p>")
    page = Page()
    page.feed(render_template(path, {"value": value}))
    assert page.tags == ["p"]
    assert "".join(page.text) == value


@pytest.mark.parametrize("name", ["document.xml", "document.xml.j2"])
def test_xml_value_cannot_add_an_element(tmp_path, name):
    value = '</value><injected attribute="x"/>&'
    path = tmp_path / name
    path.write_text("<value>{{ value }}</value>")
    root = ET.fromstring(render_template(path, {"value": value}))
    assert root.text == value and list(root) == []


def test_html_json_remains_parseable_without_script_breakout(tmp_path):
    value = '</script><img src=x onerror="alert(1)">&\''
    path = tmp_path / "data.html.j2"
    path.write_text('<script type="application/ld+json">{{ value | to_json }}</script>')
    rendered = render_template(path, {"value": {"name": value}})
    page = Page()
    page.feed(rendered)
    assert page.tags == ["script"]
    assert json.loads("".join(page.text)) == {"name": value}


def test_json_and_shell_keep_exact_special_credential_characters(tmp_path):
    value = "a'\"<&>$`\\ credential"
    config = tmp_path / "config.json.j2"
    config.write_text('{"credential": {{ value | to_json }}}')
    rendered = render_template(config, {"value": value})
    assert rendered == json.dumps({"credential": value})
    script = tmp_path / "credential.sh.j2"
    script.write_text("printf '%s' {{ value | quote }}\n")
    result = subprocess.run(
        ["/bin/sh", "-c", render_template(script, {"value": value})],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == value


@pytest.mark.parametrize("name", ["nginx.conf.j2", "worker.service.j2", "cursor.txt"])
def test_nonmarkup_artifacts_preserve_their_own_syntax(name):
    value = "literal<&>\"' characters"
    assert render_fragment(name, "{{ value }}", {"value": value}) == value
