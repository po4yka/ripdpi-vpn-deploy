"""Operator-owned public site bundles: identity, build, uniqueness admission and runway."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import date
from itertools import pairwise
from pathlib import Path

import public_site
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests/fixtures/public-site-identity"
ORIGIN = "https://platen.example.org"
GOLDEN = REPO_ROOT / "tests/snapshot/golden/nginx-xhttp/templates/public-site"
BUNDLED_FILES = REPO_ROOT / "ansible/roles/nginx-xhttp/files/public-site"


def digests(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    public_site.build(FIXTURE, tmp_path / "bundle")
    return tmp_path / "bundle"


def bundled_copy(tmp_path: Path, origin: str) -> Path:
    """The bundled site as an operator tree under another origin: what the removed render target produced."""
    site = tmp_path / "copy" / "site"
    shutil.copytree(BUNDLED_FILES, site)
    for golden in GOLDEN.rglob("*.j2"):
        if golden.name not in {"_site.html.j2", "news.html.j2"}:
            text = re.sub(r"https://[a-z0-9.-]+(:[0-9]+)?", origin, golden.read_text(encoding="utf-8"))
            (site / golden.name[:-3]).write_text(text, encoding="utf-8")
    return site.parent


def test_new_writes_one_identity_and_never_replaces_it(tmp_path: Path) -> None:
    public_site.new(tmp_path, ORIGIN, "Platen", "typewriter repair", date(2026, 3, 2), 9, 3)
    identity = (tmp_path / "identity.yml").read_text(encoding="utf-8")
    assert f"origin: {ORIGIN}" in identity
    assert re.search(r"^seed: [0-9a-f]{32}$", identity, re.MULTILINE)
    assert (tmp_path / "theme").is_dir() and (tmp_path / "articles").is_dir()
    assert "typewriter repair" in (tmp_path / "brief.md").read_text(encoding="utf-8")
    with pytest.raises(public_site.SiteError, match="created once"):
        public_site.new(tmp_path, "https://other.example.org", "Other", "other", date(2026, 3, 2), 9, 3)
    assert (tmp_path / "identity.yml").read_text(encoding="utf-8") == identity


@pytest.mark.parametrize("origin", ["http://platen.example.org", "https://platen.example.org:443",
                                    "https://Platen.example.org", "https://platen.example.org/notes"])
def test_new_refuses_an_unsafe_origin_without_writing(tmp_path: Path, origin: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/public_site.py"), "new", "--dir", str(tmp_path / "site"),
         "--url", origin, "--name", "Platen", "--subject", "typewriter repair"],
        capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 1
    assert "https origin" in result.stderr
    assert not (tmp_path / "site").exists()


def test_build_is_reproducible(tmp_path: Path, bundle: Path) -> None:
    public_site.build(FIXTURE, tmp_path / "again")
    assert digests(bundle) == digests(tmp_path / "again")
    assert {"site/index.html", "site/404.html", "backlog.tar", "schedule.json"} <= set(digests(bundle))


def test_build_refuses_a_link_in_its_inputs_and_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "identity"
    shutil.copytree(FIXTURE, source)
    (source / "theme" / "linked.css").symlink_to(source / "theme" / "assets" / "main.css")
    with pytest.raises(public_site.SiteError, match="only regular files"):
        public_site.build(source, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_build_refuses_a_canonical_url_on_another_host(tmp_path: Path) -> None:
    source = tmp_path / "identity"
    shutil.copytree(FIXTURE, source)
    base = source / "theme" / "_base.html.j2"
    base.write_text(base.read_text().replace('href="{{ site.origin }}{% block path', 'href="https://elsewhere.example.net{% block path'))
    with pytest.raises(public_site.SiteError, match="not below the site origin"):
        public_site.build(source, tmp_path / "bundle")


def test_schedule_starts_on_the_start_date_and_keeps_every_interval_near_the_cadence() -> None:
    times = public_site.schedule("5d0c1e9a7b3f42688c1d2e0f9a4b6c7d", date(2026, 3, 2), 9, 40)
    assert times[0].date() == date(2026, 3, 2)
    intervals = [(later - earlier).total_seconds() / 86400 for earlier, later in pairwise(times)]
    assert len(intervals) == 39
    assert 4.5 <= min(intervals) and max(intervals) <= 13.5
    assert times == public_site.schedule("5d0c1e9a7b3f42688c1d2e0f9a4b6c7d", date(2026, 3, 2), 9, 40)
    assert times != public_site.schedule("00000000000000000000000000000000", date(2026, 3, 2), 9, 40)
    # Pinned: a change of these values moves the dates of articles that a site already published.
    assert [int(moment.timestamp()) for moment in times[:4]] == [1772421049, 1773108017, 1774179362, 1774987726]


def test_each_generation_adds_one_article_with_a_later_date() -> None:
    generations, times = public_site.render_generations(FIXTURE)
    assert len(generations) == len(times) == 4
    for number, (earlier, later) in enumerate(pairwise(generations), start=1):
        added = later.keys() - earlier.keys()
        assert len(added) == 1 and next(iter(added)).startswith("bench/")
        assert later["feed.xml"].count(b"<entry>") == earlier["feed.xml"].count(b"<entry>") + 1
        newest = re.search(rb"<updated>([^<]+)</updated>", later["feed.xml"]).group(1).decode()
        assert newest == times[number].isoformat()
    assert generations[0]["feed.xml"].count(b"<entry>") == 2


def test_archive_holds_each_generation_as_a_delta_dated_by_the_schedule(bundle: Path) -> None:
    plan = {entry["n"]: entry["not_before"] for entry in json.loads((bundle / "schedule.json").read_text())["generations"]}
    with tarfile.open(bundle / "backlog.tar") as archive:
        members = archive.getmembers()
    assert all(member.isreg() and member.mtime == plan[int(member.name.split("/")[1])] for member in members)
    names = [member.name for member in members]
    assert "generations/1/assets/main.css" not in names
    expected, _ = public_site.render_generations(FIXTURE)
    overlay: dict[str, bytes] = {}
    with tarfile.open(bundle / "backlog.tar") as archive:
        for number, tree in enumerate(expected):
            for member in archive.getmembers():
                if member.name.startswith(f"generations/{number}/"):
                    overlay[member.name.split("/", 2)[2]] = archive.extractfile(member).read()
            assert overlay == tree
    assert os.stat(bundle / "site/index.html").st_mtime == plan[0]


def test_independent_content_is_admitted(bundle: Path) -> None:
    assert public_site.check(bundle, ORIGIN, []) == []
    # Calibration, measured 2026-11-20: the fixture shares no 8-word sequence with the bundled site.
    reference = public_site.html_shingles([(str(path), path.read_bytes()) for path in GOLDEN.rglob("*.j2")])
    shares = [public_site.containment(public_site.shingles(public_site.page_of(body).words), reference)
              for name, body in public_site.bundle_files(bundle) if name.endswith(".html")]
    assert max(shares) == 0.0


def test_bundled_pages_under_another_origin_are_refused(tmp_path: Path) -> None:
    copy = bundled_copy(tmp_path, "https://notes.example.org")
    findings = public_site.check(copy, "https://notes.example.org", [])
    similar = {line.split(":")[0] for line in findings if "of its text is also in the bundled site" in line}
    assert {"index.html", "about.html", "reading-benchmark-results.html", "models.html"} <= similar
    assert "assets/site.css: byte-identical to a file of the bundled site" in findings
    assert "404.html: byte-identical to a file of the bundled site" in findings


def test_bundled_pages_with_one_paragraph_replaced_are_still_refused(tmp_path: Path) -> None:
    copy = bundled_copy(tmp_path, "https://notes.example.org")
    reference = public_site.html_shingles([(str(path), path.read_bytes()) for path in GOLDEN.rglob("*.j2")])
    notes = sorted(path for path in (copy / "site").glob("*.html") if path.read_text().count("<p>") >= 5)
    assert len(notes) >= 6
    shares = []
    for page in notes:
        page.write_text(re.sub(r"<p>.*?</p>", "<p>" + "An unrelated sentence about ink and paper. " * 6 + "</p>",
                               page.read_text(), count=1, flags=re.DOTALL))
        shares.append(public_site.containment(public_site.shingles(public_site.page_of(page.read_bytes()).words), reference))
    # Calibration, measured 2026-11-20: a partial copy keeps more than 0.7; the limit is 0.10.
    assert min(shares) > 0.7
    findings = public_site.check(copy, "https://notes.example.org", [])
    assert all(any(line.startswith(f"{page.name}: ") and "also in the bundled site" in line for line in findings)
               for page in notes)


def mutate(bundle: Path, case: str) -> None:
    site = bundle / "site"
    index = site / "index.html"

    def insert(markup: str) -> None:
        index.write_text(index.read_text().replace("</main>", markup + "</main>"))

    if case == "bundled-asset":
        shutil.copy(BUNDLED_FILES / "assets/site.css", site / "assets/main.css")
    elif case == "external-script":
        insert('<script src="https://cdn.example.net/a.js"></script>')
    elif case == "external-font":
        (site / "assets/main.css").write_text("@font-face { src: url(//fonts.example.net/a.woff2); }\n")
    elif case == "inline-style":
        insert('<p style="background: url(https://cdn.example.net/b.png)">x</p>')
    elif case == "style-block":
        insert("<style>@import 'https://cdn.example.net/c.css';</style>")
    elif case == "base-tag":
        insert('<base href="/elsewhere/">')
    elif case == "rss-link":
        (site / "feed.xml").write_text("<rss><channel><link>https://elsewhere.example.net/</link></channel></rss>\n")
    elif case == "robots-sitemap":
        (site / "robots.txt").write_text("User-agent: *\nSitemap: https://elsewhere.example.net/sitemap.xml\n")
    elif case == "forbidden-term":
        index.write_text(index.read_text().replace("Bench log", "ＶＰＮ bench log"))
    elif case == "forbidden-path":
        (site / "admin").mkdir()
        shutil.copy(index, site / "admin/index.html")
    elif case == "unscanned-type":
        shutil.copy(index, site / "copy.htm")
    elif case == "no-error-page":
        (site / "404.html").unlink()


@pytest.mark.parametrize(("case", "expected"), [
    ("bundled-asset", "assets/main.css: byte-identical to a file of the bundled site"),
    ("external-script", "index.html: references https://cdn.example.net/a.js, which is not below the site origin"),
    ("external-font", "assets/main.css: references //fonts.example.net/a.woff2, which is not below the site origin"),
    ("inline-style", "index.html: references https://cdn.example.net/b.png, which is not below the site origin"),
    ("style-block", "index.html: references https://cdn.example.net/c.css, which is not below the site origin"),
    ("base-tag", "index.html: <base> changes where the page loads from"),
    ("rss-link", "feed.xml: references https://elsewhere.example.net/, which is not below the site origin"),
    ("robots-sitemap", "robots.txt: references https://elsewhere.example.net/sitemap.xml, which is not below the site origin"),
    ("forbidden-term", "index.html: contains the forbidden term 'vpn'"),
    ("forbidden-path", "admin/index.html: contains the forbidden term '/admin'"),
    ("unscanned-type", "copy.htm: file type is not served; use one of " + " ".join(public_site.TEXT_TYPES + public_site.BINARY_TYPES)),
    ("no-error-page", "site/404.html: missing; a bundle holds its static tree in site/"),
])
def test_check_names_each_refused_file(bundle: Path, case: str, expected: str) -> None:
    mutate(bundle, case)
    assert expected in public_site.check(bundle, ORIGIN, [])


def test_check_accepts_a_binary_asset_and_a_small_common_file(tmp_path: Path, bundle: Path) -> None:
    (bundle / "site/assets/mark.png").write_bytes(b"\x89PNG vpn xray " + bytes(range(256)))
    (bundle / "site/robots.txt").write_text("User-agent: *\nAllow: /\n")
    peer = tmp_path / "peer"
    (peer / "site").mkdir(parents=True)
    for name in ("index.html", "404.html"):
        (peer / "site" / name).write_text("<p>other</p>\n")
    shutil.copy(bundle / "site/robots.txt", peer / "site/robots.txt")
    assert public_site.check(bundle, ORIGIN, [peer]) == []


def test_check_refuses_to_run_without_its_reference_or_origin(bundle: Path, tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(public_site.SiteError, match="https origin"):
        public_site.check(bundle, "", [])
    (tmp_path / "empty").mkdir()
    monkeypatch.setattr(public_site, "BUNDLED_TREES", (tmp_path / "empty",))
    with pytest.raises(public_site.SiteError, match="reference is empty"):
        public_site.check(bundle, ORIGIN, [])
    monkeypatch.setattr(public_site, "BUNDLED_TREES", (tmp_path / "moved",))
    with pytest.raises(public_site.SiteError, match="directory that is not a link"):
        public_site.check(bundle, ORIGIN, [])


@pytest.mark.parametrize(("key", "value", "message"), [
    ("article_path", "../../{slug}.html", "article_path"),
    ("article_path", "/abs/{slug}.html", "article_path"),
    ("article_path", "{slug}.html", "both produce index.html"),
    ("initial_articles", 0, "initial_articles"),
    ("cadence_days", "9", "cadence_days"),
    ("origin", "https://platen.example.org:443", "https origin"),
])
def test_build_refuses_an_unsafe_identity_and_writes_nothing(tmp_path: Path, key: str, value: object, message: str) -> None:
    source = tmp_path / "identity"
    shutil.copytree(FIXTURE, source)
    identity = yaml.safe_load((source / "identity.yml").read_text())
    identity[key] = value
    (source / "identity.yml").write_text(yaml.safe_dump(identity))
    (source / "articles/006-index.md").write_text("---\ntitle: Index\n---\n\nBody.\n")
    with pytest.raises(public_site.SiteError, match=message):
        public_site.build(source, tmp_path / "bundle")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["identity"]


def test_an_unset_directory_is_refused_instead_of_the_working_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/public_site.py"), "new", "--dir", "", "--url", ORIGIN,
         "--name", "Platen", "--subject", "typewriter repair"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 2 and "a directory is required" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_a_peer_bundle_with_the_same_content_is_refused(tmp_path: Path, bundle: Path) -> None:
    peer = tmp_path / "peer"
    shutil.copytree(bundle, peer)
    findings = public_site.check(bundle, ORIGIN, [peer])
    assert f"bench/cleaning-type-slugs.html: byte-identical to a file of {peer}" in findings
    (peer / "backlog.tar").unlink()
    for page in (peer / "site/bench").glob("*.html"):
        page.write_text(page.read_text().replace("<h1>", "<h1>Again: "))
    assert any(line.startswith("bench/freeing-a-stuck-carriage.html: ") and f"also in {peer}" in line
               for line in public_site.check(bundle, ORIGIN, [peer]))


def test_status_counts_unpublished_generations_and_days_left(bundle: Path) -> None:
    last = json.loads((bundle / "schedule.json").read_text())["generations"][-1]["not_before"]
    assert public_site.status(bundle, last - 12 * 86400 - 60) == (2, 12)
    assert public_site.status(bundle, last + 1) == (0, 0)
    (bundle / "schedule.json").unlink()
    (bundle / "backlog.tar").unlink()
    assert public_site.status(bundle, 0) == (0, 0)
    assert public_site.check(bundle, ORIGIN, []) == []
    with pytest.raises(public_site.SiteError, match="not a site bundle"):
        public_site.status(bundle / "typo", 0)


def make(target: str, variables: dict[str, str], *, dry: bool = False) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "MFLAGS", "MAKELEVEL"}}
    environment.update(variables)
    return subprocess.run(["make", "--no-print-directory", *(["-n"] if dry else []), target], cwd=REPO_ROOT,
                          env=environment, capture_output=True, text=True, timeout=120, check=False)


def test_make_targets_build_and_admit_a_bundle_and_the_render_target_is_gone(tmp_path: Path) -> None:
    source = tmp_path / "identity"
    shutil.copytree(FIXTURE, source)
    variables = {"PUBLIC_SITE_DIR": str(source), "PUBLIC_SITE_URL": ORIGIN}
    built = make("public-site-build", variables)
    assert built.returncode == 0, built.stderr[-2000:]
    assert (source / "bundle/site/index.html").is_file()
    shutil.copytree(source / "bundle", tmp_path / "peer")
    assert make("public-site-check", variables).returncode == 0
    refused = make("public-site-check", {**variables, "PUBLIC_SITE_PEERS": str(tmp_path / "peer")})
    assert refused.returncode != 0 and "byte-identical" in refused.stderr
    assert "unpublished generations: 0" in make("public-site-status", variables).stdout
    assert make("public-site-render", {}, dry=True).returncode != 0
