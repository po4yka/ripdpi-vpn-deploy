"""Behavior of the node-local model news refresh."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT
    / "ansible"
    / "roles"
    / "nginx-xhttp"
    / "files"
    / "model-news"
    / "refresh_model_news.py"
)
spec = importlib.util.spec_from_file_location("refresh_model_news", SCRIPT)
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)

HUB_URL = "https://huggingface.co/api/models?author=lab&sort=createdAt&direction=-1&limit=10"
SHELL = "<main><p><!-- model-news:updated --></p>\n<!-- model-news:items -->\n</main>"

HUB = json.dumps(
    [
        {"id": "lab/Model-Old", "createdAt": "2026-09-01T00:00:00.000Z"},
        {"id": "lab/Model-New", "createdAt": "2026-10-20T08:00:00.000Z"},
        {"id": "lab/Model-New", "createdAt": "2026-10-20T08:00:00.000Z"},
        {"id": "lab/Fast-Proxy-Tool", "createdAt": "2026-10-21T00:00:00.000Z"},
    ]
).encode()

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Lab ships &lt;script&gt;alert(1)&lt;/script&gt; model</title>
<link>https://news.example/a</link><pubDate>Tue, 03 Nov 2026 13:41:00 GMT</pubDate></item>
<item><title>Ｎｅｗ ＶＰＮ rules announced</title>
<link>https://news.example/b</link><pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Plain link item</title>
<link>http://news.example/c</link><pubDate>Tue, 03 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>""".encode()

DTD = b"""<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY a "aaaaaaaa">]>
<rss><channel><item><title>&a;</title><link>https://news.example/d</link>
<pubDate>Tue, 03 Nov 2026 09:00:00 GMT</pubDate></item></channel></rss>"""

SOURCES = [
    {"name": "Lab", "kind": "hub", "section": "Repositories", "org": "lab"},
    {"name": "Wire", "kind": "feed", "section": "Headlines", "url": "https://news.example/feed"},
    {"name": "Broken", "kind": "feed", "section": "Headlines", "url": "https://bad.example/feed"},
]


def _serve(monkeypatch: pytest.MonkeyPatch, bodies: dict[str, bytes]) -> None:
    def urlopen(request, timeout):
        url = request.full_url
        if url not in bodies:
            raise OSError(f"unreachable {url}")
        return io.BytesIO(bodies[url])

    monkeypatch.setattr(news.urllib.request, "urlopen", urlopen)


def _run(tmp_path: Path, sources: list[dict]) -> tuple[int, Path]:
    sources_file = tmp_path / "sources.json"
    sources_file.write_text(json.dumps(sources))
    shell_file = tmp_path / "shell.html"
    shell_file.write_text(SHELL)
    output = tmp_path / "news.html"
    status = news.main(["refresh", str(sources_file), str(shell_file), str(output)])
    return status, output


def test_page_lists_escaped_deduplicated_newest_first_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(
        monkeypatch,
        {HUB_URL: HUB, "https://news.example/feed": RSS, "https://bad.example/feed": DTD},
    )
    previous_umask = news.os.umask(0o027)  # the unit's UMask
    try:
        status, output = _run(tmp_path, SOURCES)
    finally:
        news.os.umask(previous_umask)
    page = output.read_text()

    assert status == 0
    assert "<!-- model-news" not in page
    assert page.index("lab/Model-New") < page.index("lab/Model-Old")
    assert page.count('href="https://huggingface.co/lab/Model-New"') == 1
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>" not in page
    assert '<time datetime="2026-11-03">3 November 2026</time>' in page
    assert "Last refreshed <time datetime=" in page
    for dropped in ("Fast-Proxy-Tool", "ＶＰＮ", "Plain link item", "news.example/d"):
        assert dropped not in page
    assert oct(output.stat().st_mode & 0o777) == "0o640"
    assert output.stat().st_gid == tmp_path.stat().st_gid


def test_total_failure_keeps_the_previous_page_and_reports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, {"https://bad.example/feed": DTD})
    previous = tmp_path / "news.html"
    previous.write_text("previous page")

    status, output = _run(tmp_path, SOURCES)

    assert status == 1
    assert output.read_text() == "previous page"


def test_plain_http_source_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, {"http://news.example/feed": RSS})
    status, output = _run(
        tmp_path,
        [{"name": "Wire", "kind": "feed", "section": "Headlines", "url": "http://news.example/feed"}],
    )

    assert status == 1
    assert not output.exists()


def test_oversized_response_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        {"https://news.example/feed": b" " * (2 * 1024 * 1024 + 1), HUB_URL: HUB},
    )
    status, output = _run(tmp_path, SOURCES[:2])

    assert status == 0
    assert "Headlines" not in output.read_text()


def test_dtd_in_another_encoding_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, {"https://news.example/feed": DTD.decode().replace('version="1.0"?>', 'version="1.0" encoding="UTF-16"?>').encode("utf-16")})
    status, output = _run(tmp_path, [SOURCES[1]])

    assert status == 1
    assert not output.exists()


def test_redirect_away_from_https_is_refused() -> None:
    handler = news.HttpsOnlyRedirects()
    request = news.urllib.request.Request("https://news.example/feed")
    with pytest.raises(ValueError, match="leaves https"):
        handler.redirect_request(request, None, 302, "Found", {}, "http://news.example/feed")
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://mirror.example/feed")


def test_malformed_entry_link_drops_only_that_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = RSS.replace(b"https://news.example/a", b"https://[")
    _serve(monkeypatch, {HUB_URL: HUB, "https://news.example/feed": feed})
    status, output = _run(tmp_path, SOURCES[:2])
    page = output.read_text()

    assert status == 0
    assert "lab/Model-New" in page
    assert "alert(1)" not in page


def test_slow_source_is_cut_off_by_the_wall_clock_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Trickle(io.BytesIO):
        def read(self, size=-1):
            while True:  # never finishes; only the wall-clock alarm stops it
                news.signal.pause()

    def urlopen(request, timeout):
        return Trickle() if request.full_url == "https://news.example/feed" else io.BytesIO(HUB)

    monkeypatch.setattr(news.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(news, "TIMEOUT", 0.2)
    status, output = _run(tmp_path, SOURCES[:2])

    assert status == 0
    assert "lab/Model-New" in output.read_text()


def test_retirement_inside_a_protected_ingress_waits_for_the_commit(tmp_path: Path) -> None:
    tasks = SCRIPT.parents[2] / "tasks"
    play = tmp_path / "play.yml"
    play.write_text(
        json.dumps(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {"_transport_ingress_request": {"owners": []}},
                    "tasks": [
                        {"ansible.builtin.include_tasks": str(tasks / "model-news-retire.yml")},
                        {"ansible.builtin.assert": {"that": ["_nginx_model_news_retire_after_commit"]}},
                    ],
                }
            ]
        )
    )
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(play)],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env={**os.environ, "ANSIBLE_NOCOLOR": "1"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Stop and disable the model news timer" not in result.stdout

    site = yaml.safe_load((REPO_ROOT / "ansible" / "playbooks" / "site.yml").read_text())
    names = [
        task.get("name")
        for play_ in site
        for block in play_.get("tasks", []) + play_.get("post_tasks", [])
        for task in block.get("block", [block])
    ]
    commit = names.index("Commit the ready protected ingress and egress composition")
    assert names.index("Retire the model news page after the protected commit") == commit + 1
