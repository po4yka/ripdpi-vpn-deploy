"""Regression tests for the Jinja variable coverage checker."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check-secrets-coverage.py"

spec = importlib.util.spec_from_file_location("secrets_coverage", CHECKER)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def test_macro_arguments_and_set_values_are_local() -> None:
    template = """
    {% macro page(title, description, path, page_type='article') %}
      {% set canonical = public_site_canonical_url ~ path %}
      <title>{{ title | quote }}</title>
      <meta name="description" content="{{ description }}">
      <meta property="og:type" content="{{ page_type }}">
      <link rel="canonical" href="{{ public_site_canonical_url }}{{ path }}">
      <span data-canonical="{{ canonical }}"></span>
    {% endmacro %}
    """

    assert checker.extract_toplevel_vars(template) == {"public_site_canonical_url"}


def test_imported_namespace_is_local_but_context_values_are_not() -> None:
    template = """
    {% import "_site.html.j2" as site with context %}
    {{ site.page('Title', 'Description', '/notes/example.html') }}
    {{ global_content }}
    """

    assert checker.extract_toplevel_vars(template) == {"global_content"}


def test_macro_argument_does_not_hide_same_named_global_outside_macro() -> None:
    template = """
    {% macro card(title) %}<h2>{{ title }}</h2>{% endmacro %}
    <title>{{ title }}</title>
    """

    assert checker.extract_toplevel_vars(template) == {"title"}


def test_raw_blocks_do_not_contribute_literal_go_template_tokens() -> None:
    for raw_block in (
        '''{% raw %}
        {{ define "literal" }}{{ if .Values.enabled }}{{ range .Items }}
        {{ template "literal" . }}{{ else }}{{ end }}{{ end }}
        {{ hidden_inside_raw }}
        {% endraw %}''',
        '''{%- raw -%}
        {{ define "literal" }}{{ if .Values.enabled }}{{ range .Items }}
        {{ template "literal" . }}{{ else }}{{ end }}{{ end }}
        {{ hidden_inside_trimmed_raw }}
        {%- endraw -%}''',
    ):
        template = f"{raw_block}\n{{{{ unknown_outside_raw }}}}"

        assert checker.extract_toplevel_vars(template) == {"unknown_outside_raw"}
