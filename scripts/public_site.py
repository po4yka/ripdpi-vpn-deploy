#!/usr/bin/env python3
"""Create, build, check and report an operator-owned public site bundle.

  public_site.py new    --dir DIR --url ORIGIN --name NAME --subject TEXT
  public_site.py build  --dir DIR --out BUNDLE
  public_site.py check  --bundle BUNDLE --url ORIGIN [--peer BUNDLE ...]
  public_site.py status --bundle BUNDLE

DIR holds identity.yml, theme/ and articles/. BUNDLE receives site/ (the
initial generation), backlog.tar (every generation as a delta) and
schedule.json. The repository supplies no prose, theme or asset: an operator
writes them, and `check` refuses content that another site also serves.
`check` protects an operator from an accidental copy; it is not a defence
against an operator who hides a copy on purpose. No subcommand uses the network.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import sys
import tarfile
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import jinja2
import yaml
from jinja2.sandbox import SandboxedEnvironment
from markdown_it import MarkdownIt
from markupsafe import Markup

REPO = Path(__file__).resolve().parent.parent
# The bundled site as rendered text (snapshot-check keeps the goldens current) and as served files.
BUNDLED_TREES = (
    REPO / "tests/snapshot/golden/nginx-xhttp/templates/public-site",
    REPO / "ansible/roles/nginx-xhttp/files/public-site",
    REPO / "ansible/roles/reality-self-steal/files/public-site",
)
REFRESHER = REPO / "ansible/roles/nginx-xhttp/files/model-news/refresh_model_news.py"
ORIGIN = re.compile(r"\Ahttps://[a-z0-9.-]+(:[0-9]+)?\Z")
ARTICLE_PATH = re.compile(r"\A(?:[a-z0-9-]+/)*[a-z0-9-]*\{slug\}[a-z0-9-]*(?:/index)?\.html\Z")
# A served file type that `check` cannot read is refused, so no page escapes the scan under another extension.
TEXT_TYPES = (".html", ".css", ".xml", ".txt", ".svg", ".js", ".json", ".webmanifest")
BINARY_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".ico", ".woff", ".woff2", ".pdf")
SHINGLE_WORDS = 8
# Part of a page's word sequences that another site may also contain. Measured values are in
# tests/unit/test_public_site_bundle.py: copies score above 0.7, independent text scores 0.0.
SIMILARITY_LIMIT = 0.10
# A shorter page (an error page, a list of links) has too few sequences for a ratio.
MIN_SHINGLES = 20
# Two unrelated sites can both hold a three-line robots.txt; a shared larger file is a copy.
MIN_IDENTICAL_BYTES = 200


class SiteError(Exception):
    pass


def forbidden_terms() -> tuple[str, ...]:
    """The public site vocabulary contract has one home: the news refresher that enforces it on a node."""
    spec = importlib.util.spec_from_file_location("refresh_model_news", REFRESHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FORBIDDEN


def regular_files(root: Path) -> dict[str, Path]:
    """Relative path of every file below root. A link or special file refuses the whole tree."""
    if root.is_symlink() or not root.is_dir():
        raise SiteError(f"{root}: a directory that is not a link is required")

    def refuse(error: OSError) -> None:
        raise error

    found: dict[str, Path] = {}
    for current, directories, names in os.walk(root, followlinks=False, onerror=refuse):
        for name in directories + names:
            path = Path(current, name)
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise SiteError(f"{path}: only regular files and directories are allowed")
        for name in names:
            found[Path(current, name).relative_to(root).as_posix()] = Path(current, name)
    return dict(sorted(found.items()))


def validate_identity(identity: object) -> dict:
    if not isinstance(identity, dict):
        raise SiteError("identity.yml must be a mapping")
    origin = identity.get("origin")
    if not isinstance(origin, str) or not ORIGIN.match(origin) or origin.endswith(":443"):
        raise SiteError("the origin must be a lowercase https origin without a path and without :443")
    for key in ("name", "subject", "seed"):
        if not isinstance(identity.get(key), str) or not identity[key].strip():
            raise SiteError(f"identity {key} must be a non-empty string")
    for key in ("cadence_days", "initial_articles"):
        if type(identity.get(key)) is not int or identity[key] < 1:
            raise SiteError(f"identity {key} must be an integer of at least 1")
    if not isinstance(identity.get("article_path"), str) or not ARTICLE_PATH.match(identity["article_path"]):
        raise SiteError("identity article_path must be a relative .html path with one {slug} and no '..'")
    try:
        date.fromisoformat(str(identity.get("start")))
    except ValueError as error:
        raise SiteError("identity start must be an ISO date") from error
    return identity


# --- new ---------------------------------------------------------------------

BRIEF = """# Site brief: {name}

Subject: {subject}
Origin: {origin}

Write this site for one operator. Do not copy text, markup, style sheets or images from another site
or from this repository's bundled site; `make public-site-check` refuses them.

## theme/

- `index.html.j2`, `article.html.j2` and `404.html.j2` are required.
- Every other `*.j2` file becomes a page at the same path without `.j2` (for example `feed.xml.j2`,
  `sitemap.xml.j2`, `robots.txt.j2`, `about.html.j2`). A file whose name starts with `_` is a partial.
- Every other file is copied unchanged (style sheets, images, fonts).
- Served file types: {types}.
- Template variables: `site.name`, `site.subject`, `site.origin`, `updated` (datetime of the newest
  article) and `articles` (published articles, newest first). `article.html.j2` also gets `article`.
  An article has `title`, `summary`, `topic`, `slug`, `path`, `url`, `date` (UTC datetime) and `html`.
- Load every resource from the site itself. Canonical, feed and sitemap URLs start with `site.origin`.
  Do not use `<base>` or a meta refresh.

## articles/

- One Markdown file for each article, published in file name order (`001-first-title.md`, ...).
- Front matter: `title` (required), `summary`, `topic`. Do not write a date: the schedule assigns it.
- {count} articles cover one year at this cadence.
- These terms must not appear anywhere: {forbidden}.

Then run `make public-site-build` and `make public-site-check`.
"""


def new(directory: Path, origin: str, name: str, subject: str, start: date, cadence_days: int, initial: int) -> None:
    values = validate_identity({
        "origin": origin, "name": name, "subject": subject, "seed": secrets.token_hex(16),
        "start": start.isoformat(), "cadence_days": cadence_days, "initial_articles": initial,
        "article_path": "articles/{slug}.html",
    })
    if any((directory / item).exists() or (directory / item).is_symlink() for item in ("identity.yml", "brief.md")):
        raise SiteError(f"{directory} holds an identity; an identity is created once")
    for part in ("theme", "articles"):
        (directory / part).mkdir(parents=True, exist_ok=True)
    brief = BRIEF.format(name=name, subject=subject, origin=origin, count=initial + 365 // cadence_days,
                         forbidden=", ".join(forbidden_terms()), types=" ".join(TEXT_TYPES + BINARY_TYPES))
    for item, text in (("identity.yml", yaml.safe_dump(values, sort_keys=False, allow_unicode=True)), ("brief.md", brief)):
        with open(directory / item, "x", encoding="utf-8") as handle:
            handle.write(text)


# --- build -------------------------------------------------------------------


def schedule(seed: str, start: date, cadence_days: int, generations: int) -> list[datetime]:
    """Publication time of each generation: a function of the identity only, so a rebuilt bundle and a
    recreated node keep every earlier date. SHA-256 gives the same values on every interpreter."""
    def fraction(index: int) -> float:
        return int.from_bytes(hashlib.sha256(f"{seed}:{index}".encode()).digest()[:8], "big") / 2**64

    moment = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) + timedelta(seconds=int(fraction(0) * 86400))
    times = [moment]
    for index in range(1, generations):
        moment += timedelta(seconds=round(cadence_days * 86400 * (0.5 + fraction(index))))
        times.append(moment)
    return times


def load_articles(directory: Path, identity: dict) -> list[dict]:
    markdown = MarkdownIt("commonmark", {"html": False}).enable("table")
    articles = []
    for relative, path in regular_files(directory).items():
        if not relative.endswith(".md"):
            raise SiteError(f"{path}: articles are Markdown files")
        text = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
        meta = yaml.safe_load(match.group(1)) if match else None
        if not match or not isinstance(meta, dict) or not str(meta.get("title") or "").strip():
            raise SiteError(f"{path}: front matter with a title is required")
        slug = re.sub(r"\A\d+-", "", Path(relative).stem)
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
            raise SiteError(f"{path}: the file name must give a lowercase slug of letters, digits and dashes")
        location = identity["article_path"].format(slug=slug)
        articles.append({
            "title": str(meta["title"]).strip(), "summary": str(meta.get("summary") or ""),
            "topic": str(meta.get("topic") or ""), "slug": slug, "path": "/" + location,
            "url": identity["origin"] + "/" + location, "html": Markup(markdown.render(match.group(2))),
        })
    if len({article["slug"] for article in articles}) != len(articles):
        raise SiteError(f"{directory}: two articles have the same slug")
    return articles


def render_generations(directory: Path) -> tuple[list[dict[str, bytes]], list[datetime]]:
    identity_file = directory / "identity.yml"
    if identity_file.is_symlink() or not identity_file.is_file():
        raise SiteError(f"{identity_file}: a regular file is required")
    identity = validate_identity(yaml.safe_load(identity_file.read_text(encoding="utf-8")))
    theme = regular_files(directory / "theme")
    articles = load_articles(directory / "articles", identity)
    initial = identity["initial_articles"]
    if len(articles) < initial:
        raise SiteError(f"{directory}/articles: {initial} initial articles are required, {len(articles)} found")
    for required in ("index.html.j2", "article.html.j2", "404.html.j2"):
        if required not in theme:
            raise SiteError(f"{directory}/theme/{required} is required")
    times = schedule(identity["seed"], date.fromisoformat(str(identity["start"])), identity["cadence_days"],
                     len(articles) - initial + 1)
    for index, article in enumerate(articles):
        article["date"] = times[max(0, index - initial + 1)]
    environment = SandboxedEnvironment(loader=jinja2.FileSystemLoader(directory / "theme"), autoescape=True,
                                       undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    site = {"name": identity["name"], "subject": identity["subject"], "origin": identity["origin"]}
    generations = []
    for count in range(initial, len(articles) + 1):
        published = articles[:count][::-1]
        context = {"site": site, "articles": published, "updated": published[0]["date"]}
        tree: dict[str, bytes] = {}
        for relative, path in theme.items():
            if Path(relative).name.startswith("_"):
                continue
            if not relative.endswith(".j2"):
                tree[relative] = path.read_bytes()
            elif relative != "article.html.j2":
                tree[relative[:-3]] = environment.get_template(relative).render(context).encode()
        for article in published:
            target = article["path"].lstrip("/")
            if target in tree:
                raise SiteError(f"article {article['slug']} and a theme file both produce {target}")
            tree[target] = environment.get_template("article.html.j2").render(context, article=article).encode()
        generations.append(tree)
    findings = type_findings(generations[-1]) + resource_findings(sorted(generations[-1].items()), identity["origin"])
    if findings:
        raise SiteError("; ".join(findings))
    return generations, times


def build(directory: Path, out: Path) -> None:
    generations, times = render_generations(directory)
    if out.is_symlink() or (out.exists() and not (out / "schedule.json").is_file()):
        raise SiteError(f"{out} exists and is not a site bundle")
    staging = out.with_name(out.name + ".building")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        for relative, body in generations[0].items():
            target = staging / "site" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            os.utime(target, (times[0].timestamp(), times[0].timestamp()))
        # A member is stored in the first generation that changes it; generation n is members 0..n overlaid.
        with tarfile.open(staging / "backlog.tar", "w", format=tarfile.GNU_FORMAT) as archive:
            previous: dict[str, bytes] = {}
            for number, (tree, moment) in enumerate(zip(generations, times)):
                if previous.keys() - tree.keys():
                    raise SiteError(f"generation {number} removes {min(previous.keys() - tree.keys())}")
                for relative in sorted(tree):
                    if previous.get(relative) != tree[relative]:
                        member = tarfile.TarInfo(f"generations/{number}/{relative}")
                        member.size, member.mtime, member.mode = len(tree[relative]), int(moment.timestamp()), 0o644
                        archive.addfile(member, io.BytesIO(tree[relative]))
                previous = tree
        plan = {"version": 1, "generations": [{"n": n, "not_before": int(t.timestamp())} for n, t in enumerate(times)]}
        (staging / "schedule.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        if out.exists():
            shutil.rmtree(out)
        staging.rename(out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# --- check -------------------------------------------------------------------


CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")\s]+)|@import\s+['\"]([^'\"]+)")


class Page(HTMLParser):
    """Visible words, the URLs a browser loads without a click, and markup that redirects loads."""

    def __init__(self) -> None:
        super().__init__()
        self.words: list[str] = []
        self.resources: list[str] = []
        self.refused: list[str] = []
        self._hidden: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {name: value or "" for name, value in attrs}
        if tag in ("script", "style"):
            self._hidden.append(tag)
        if tag == "base" or (tag == "meta" and values.get("http-equiv", "").lower() == "refresh"):
            self.refused.append(f"<{tag}> changes where the page loads from")
        self.resources += [values[name] for name in ("src", "poster", "data", "background") if values.get(name)]
        self.resources += [part.split()[0] for part in values.get("srcset", "").split(",") if part.split()]
        if tag in ("link", "image", "use") and values.get("href"):
            self.resources.append(values["href"])
        self.resources += [a or b for a, b in CSS_URL.findall(values.get("style", ""))]

    def handle_endtag(self, tag):
        if self._hidden and self._hidden[-1] == tag:
            self._hidden.pop()

    def handle_data(self, data):
        if self._hidden and self._hidden[-1] == "style":
            self.resources += [a or b for a, b in CSS_URL.findall(data)]
        elif not self._hidden:
            self.words += re.findall(r"\w+", unicodedata.normalize("NFKC", data).casefold())


def page_of(body: bytes) -> Page:
    page = Page()
    page.feed(body.decode("utf-8", "replace"))
    return page


def shingles(words: list[str]) -> set[str]:
    return {" ".join(words[i:i + SHINGLE_WORDS]) for i in range(len(words) - SHINGLE_WORDS + 1)}


def containment(page: set[str], reference: set[str]) -> float:
    return len(page & reference) / len(page) if page else 0.0


def bundle_files(bundle: Path) -> list[tuple[str, bytes]]:
    """Every version of every file the bundle can serve: site/ and each archive member."""
    files = {(relative, path.read_bytes()) for relative, path in regular_files(bundle / "site").items()}
    archive_path = bundle / "backlog.tar"
    if archive_path.is_file():
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                parts = Path(member.name).parts
                if (not member.isreg() or len(parts) < 3 or parts[0] != "generations" or not parts[1].isdigit()
                        or ".." in parts):
                    raise SiteError(f"{archive_path}: unexpected member {member.name}")
                files.add(("/".join(parts[2:]), archive.extractfile(member).read()))
    return sorted(files)


def html_shingles(files: list[tuple[str, bytes]]) -> set[str]:
    found: set[str] = set()
    for relative, body in files:
        if relative.endswith((".html", ".j2")):
            found |= shingles(page_of(body).words)
    return found


def type_findings(names) -> list[str]:
    return [f"{relative}: file type is not served; use one of {' '.join(TEXT_TYPES + BINARY_TYPES)}"
            for relative in sorted(set(names)) if not relative.lower().endswith(TEXT_TYPES + BINARY_TYPES)]


def resource_findings(files: list[tuple[str, bytes]], origin: str) -> list[str]:
    """URLs that a browser or a crawler loads without a click must stay below the site origin."""
    findings = []
    for relative, body in files:
        text = body.decode("utf-8", "replace")
        resources: list[str] = []
        if relative.endswith((".html", ".svg")):
            page = page_of(body)
            resources = page.resources
            findings += [f"{relative}: {reason}" for reason in page.refused]
        elif relative.endswith(".css"):
            resources = [a or b for a, b in CSS_URL.findall(text)]
        elif relative.endswith(".xml"):
            declared = set(re.findall(r"""xmlns(?::\w+)?=["']([^"']+)""", text))
            resources = [url for url in re.findall(r"""https?://[^\s"'<>]+""", text) if url not in declared]
        elif relative.endswith(".txt"):
            resources = re.findall(r"(?im)^sitemap:\s*(\S+)", text)
        for raw in resources:
            url = re.sub(r"[\t\n\r]", "", raw).strip().replace("\\", "/")
            if re.match(r"(?:[A-Za-z][A-Za-z0-9+.-]*:)?//", url) and url != origin and not url.startswith(origin + "/"):
                findings.append(f"{relative}: references {url}, which is not below the site origin")
    return findings


def check(bundle: Path, origin: str, peers: list[Path]) -> list[str]:
    if not ORIGIN.match(origin):
        raise SiteError("the origin must be a lowercase https origin without a path")
    findings = [
        f"{required}: missing; a bundle holds its static tree in site/"
        for required in ("site/index.html", "site/404.html")
        if not (bundle / required).is_file()
    ]
    if findings:
        return findings
    files = bundle_files(bundle)
    references = {"the bundled site": [(f"{root}/{k}", p.read_bytes()) for root in BUNDLED_TREES
                                       for k, p in regular_files(root).items()]}
    if not html_shingles(references["the bundled site"]):
        raise SiteError("the bundled site reference is empty; the check cannot compare against it")
    references.update({str(peer): bundle_files(peer) for peer in peers})
    for label, reference in references.items():
        known = html_shingles(reference)
        digests = {hashlib.sha256(body).hexdigest() for _, body in reference if len(body) >= MIN_IDENTICAL_BYTES}
        for relative, body in files:
            if hashlib.sha256(body).hexdigest() in digests:
                findings.append(f"{relative}: byte-identical to a file of {label}")
            elif relative.endswith(".html"):
                own = shingles(page_of(body).words)
                share = containment(own, known)
                if len(own) >= MIN_SHINGLES and share > SIMILARITY_LIMIT:
                    findings.append(f"{relative}: {share:.0%} of its text is also in {label}")
    terms = forbidden_terms()
    for relative, body in files:
        text = "/" + relative
        if relative.lower().endswith(TEXT_TYPES):
            text += "\n" + body.decode("utf-8", "replace")
        text = unicodedata.normalize("NFKC", text).casefold()
        findings += [f"{relative}: contains the forbidden term {term!r}" for term in terms if term in text]
    findings += type_findings(relative for relative, _ in files) + resource_findings(files, origin)
    return list(dict.fromkeys(findings))


# --- status ------------------------------------------------------------------


def status(bundle: Path, now: float) -> tuple[int, int]:
    """Unpublished generations and whole days until the last one is published."""
    plan = bundle / "schedule.json"
    if not plan.is_file():
        if not (bundle / "site/index.html").is_file():
            raise SiteError(f"{bundle} is not a site bundle")
        return 0, 0
    times = [entry["not_before"] for entry in json.loads(plan.read_text(encoding="utf-8"))["generations"]]
    return sum(moment > now for moment in times), max(0, int((max(times) - now) // 86400))


def named_path(value: str) -> Path:
    # An unset Make variable arrives as an empty string, which Path turns into the current directory.
    if not value.strip():
        raise argparse.ArgumentTypeError("a directory is required")
    return Path(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("new")
    create.add_argument("--dir", type=named_path, required=True)
    create.add_argument("--url", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--subject", required=True)
    create.add_argument("--start", type=date.fromisoformat, default=None)
    create.add_argument("--cadence-days", type=int, default=9)
    create.add_argument("--initial-articles", type=int, default=3)
    make = commands.add_parser("build")
    make.add_argument("--dir", type=named_path, required=True)
    make.add_argument("--out", type=named_path, required=True)
    admit = commands.add_parser("check")
    admit.add_argument("--bundle", type=named_path, required=True)
    admit.add_argument("--url", required=True)
    admit.add_argument("--peer", type=named_path, action="append", default=[])
    report = commands.add_parser("status")
    report.add_argument("--bundle", type=named_path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            new(args.dir, args.url, args.name, args.subject, args.start or datetime.now(timezone.utc).date(),
                args.cadence_days, args.initial_articles)
        elif args.command == "build":
            build(args.dir, args.out)
        elif args.command == "check":
            findings = check(args.bundle, args.url, args.peer)
            for finding in findings:
                print(finding, file=sys.stderr)
            return 1 if findings else 0
        else:
            unpublished, days = status(args.bundle, time.time())
            print(f"unpublished generations: {unpublished}; days until the last publication: {days}")
    except (SiteError, OSError, yaml.YAMLError, jinja2.TemplateError, tarfile.TarError, KeyError, ValueError) as error:
        print(f"public-site: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
