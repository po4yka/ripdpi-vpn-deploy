#!/usr/bin/env python3
"""Render the public model news page from pinned upstream feeds.

Usage: refresh_model_news.py SOURCES_JSON SHELL_HTML OUTPUT_HTML

Each source is fetched over HTTPS with a size and time limit. Only titles,
dates, source names and links are kept; upstream text is never republished.
A failed source is skipped. When no source yields an entry, the previous page
stays in place and the exit status is non-zero so the unit shows the failure.
"""

from __future__ import annotations

import glob
import html
import http.client
import json
import os
import sys
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.parsers import expat

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 20
ITEMS_MARKER = "<!-- model-news:items -->"
UPDATED_MARKER = "<!-- model-news:updated -->"
ATOM = "{http://www.w3.org/2005/Atom}"
# An honest feed-reader identity without the site name, so third-party logs
# do not tie nodes to the site.
USER_AGENT = "model-news-refresh/1"
HUB_LISTING = "https://huggingface.co/api/models?author={org}&sort=createdAt&direction=-1&limit=10"
# The public site carries no transport vocabulary; drop any upstream entry that does.
FORBIDDEN = ("vpn", "proxy", "xray", "hysteria", "amnezia", "/admin", "/metrics", "/health")


class HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise ValueError("redirect leaves https")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


urllib.request.install_opener(urllib.request.build_opener(HttpsOnlyRedirects))


def fetch(url: str) -> bytes:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("source must use https")
    # The socket timeout bounds each read; the deadline bounds the whole body.
    deadline = time.monotonic() + TIMEOUT
    chunks, size = [], 0
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT) as response:
        while chunk := response.read(64 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("source response is too large")
            if time.monotonic() > deadline:
                raise TimeoutError("source response is too slow")
            chunks.append(chunk)
    return b"".join(chunks)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def feed_entries(body: bytes) -> list[dict]:
    # Feeds need no DTD. Expat reports one in any encoding before the tree parse.
    def refuse(*_args):
        raise ValueError("feed declares a DTD")

    probe = expat.ParserCreate()
    probe.StartDoctypeDeclHandler = refuse
    probe.EntityDeclHandler = refuse
    probe.Parse(body, True)
    root = ET.fromstring(body)
    entries = []
    for item in root.iter("item"):
        entries.append(
            {
                "title": item.findtext("title"),
                "link": (item.findtext("link") or "").strip(),
                "date": parse_date(item.findtext("pubDate")),
            }
        )
    for entry in root.iter(f"{ATOM}entry"):
        links = entry.findall(f"{ATOM}link")
        link = next((item for item in links if item.get("rel", "alternate") == "alternate"), None)
        entries.append(
            {
                "title": entry.findtext(f"{ATOM}title"),
                "link": None if link is None else (link.get("href") or "").strip(),
                "date": parse_date(
                    entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
                ),
            }
        )
    return entries


def hub_entries(body: bytes) -> list[dict]:
    entries = []
    for model in json.loads(body):
        model_id = model.get("id") or model.get("modelId")
        if not isinstance(model_id, str):
            continue
        entries.append(
            {
                "title": model_id,
                "link": "https://huggingface.co/" + urllib.parse.quote(model_id, safe="/"),
                "date": parse_date(model.get("createdAt")),
            }
        )
    return entries


def acceptable(entry: dict) -> bool:
    title, link = entry["title"], entry["link"]
    if not isinstance(title, str) or not isinstance(link, str) or entry["date"] is None:
        return False
    if urllib.parse.urlsplit(link).scheme != "https":
        return False
    text = unicodedata.normalize("NFKC", title + " " + link).casefold()
    return not any(term in text for term in FORBIDDEN)


def collect(sources: list[dict]) -> dict[str, list[dict]]:
    sections: dict[str, list[dict]] = {}
    for source in sources:
        try:
            if source["kind"] == "hub":
                url = HUB_LISTING.format(org=urllib.parse.quote(source["org"], safe=""))
            else:
                url = source["url"]
            body = fetch(url)
            parsed = hub_entries(body) if source["kind"] == "hub" else feed_entries(body)
        # One broken upstream must not hide the others.
        except (
            OSError,
            ValueError,
            SyntaxError,
            TypeError,
            AttributeError,
            KeyError,
            RecursionError,
            http.client.HTTPException,
            expat.ExpatError,
        ) as error:
            print(f"skip {source['name']}: {error}", file=sys.stderr)
            continue
        section = sections.setdefault(source["section"], [])
        for entry in parsed:
            if acceptable(entry):
                entry["title"] = " ".join(entry["title"].split())
                entry["source"] = source["name"]
                section.append(entry)
    for name, entries in sections.items():
        seen, unique = set(), []
        for entry in sorted(entries, key=lambda item: item["date"], reverse=True):
            if entry["link"] not in seen:
                seen.add(entry["link"])
                unique.append(entry)
        sections[name] = unique[:30]
    return {name: entries for name, entries in sections.items() if entries}


def render(shell: str, sections: dict[str, list[dict]], now: datetime) -> str:
    parts = []
    for name, entries in sections.items():
        parts.append(f'<section class="news-section">\n<h2>{html.escape(name)}</h2>\n<ol class="news-list">')
        for entry in entries:
            day = entry["date"]
            parts.append(
                f'<li><a href="{html.escape(entry["link"])}">{html.escape(entry["title"])}</a>'
                f'<span class="meta">{html.escape(entry["source"])} · '
                f'<time datetime="{day:%Y-%m-%d}">{day.day} {day:%B %Y}</time></span></li>'
            )
        parts.append("</ol>\n</section>")
    updated = f'Last refreshed <time datetime="{now:%Y-%m-%dT%H:%MZ}">{now.day} {now:%B %Y, %H:%M} UTC</time>.'
    return shell.replace(ITEMS_MARKER, "\n".join(parts)).replace(UPDATED_MARKER, updated)


def write_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(path) or "."
    for leftover in glob.glob(os.path.join(directory, ".news-*")):
        os.unlink(leftover)  # left by a killed run; only this unit writes here
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".news-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__.splitlines()[2], file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as handle:
        sources = json.load(handle)
    with open(argv[2], encoding="utf-8") as handle:
        shell = handle.read()
    if ITEMS_MARKER not in shell or UPDATED_MARKER not in shell:
        print("shell page lacks the news markers", file=sys.stderr)
        return 2
    sections = collect(sources)
    if not sections:
        print("no source returned an entry; keeping the previous page", file=sys.stderr)
        return 1
    write_atomic(argv[3], render(shell, sections, datetime.now(timezone.utc)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
