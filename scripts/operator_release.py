"""Check reviewed release archives and actual local APT policy without mutation."""
import io
import gzip
import re
import tarfile
from urllib.parse import unquote, urlsplit
import zipfile

import yaml

from operator_private import MAX_BYTES, checked, fields, read_owned, require, resolve_pointer, sha256, unique


def member_name(name):
    require(isinstance(name, str) and len(name) <= 512 and
            re.fullmatch(r"[A-Za-z0-9_.+/-]+", name) and
            not name.startswith("/") and not {"", ".", ".."} & set(name.split("/")), "unsafe-member")
    return name


def check_apt(policy):
    fields(policy, ("package", "version", "preference"))
    package, version = policy["package"], policy["version"]
    require(isinstance(package, str) and re.fullmatch(r"[a-z0-9][a-z0-9+.-]{0,99}", package)
            and isinstance(version, str) and re.fullmatch(r"[A-Za-z0-9.+:~_-]{1,100}", version), "invalid-package")
    preference = read_owned(policy["preference"], private=False, limit=65536).decode()
    expected = {"Package": package, "Pin": "version " + version, "Pin-Priority": "1001"}
    rows = [line.split(":", 1) for line in preference.splitlines() if line.strip() and not line.startswith("#")]
    require(len(rows) == 3 and all(len(row) == 2 for row in rows)
            and {key.strip(): value.strip() for key, value in rows} == expected, "package-preference-mismatch")
    installed = checked(["dpkg-query", "-W", "-f=${Version}", package], limit=65536).decode().strip()
    candidate = checked(["apt-cache", "policy", package], limit=65536).decode()
    selected = re.findall(r"(?m)^\s*(?:Installed|Candidate):\s*(\S+)\s*$", candidate)
    require(installed == version and selected == [version, version], "package-version-mismatch")


def check(plan):
    fields(plan, ("schema_version",), ("releases", "apt"))
    require("releases" in plan or "apt" in plan, "release-or-package-required")
    releases = plan.get("releases", [])
    require(isinstance(releases, list) and len(releases) <= 32 and
            (bool(releases) or "releases" not in plan), "release-count")
    total = 0
    for release in releases:
        fields(release, ("source", "source_sha256", "pointer", "archives"))
        raw, authority = read_owned(release["source"], limit=4 * 1024 * 1024, with_identity=True)
        require(sha256(raw) == release["source_sha256"], "release-source-mismatch")
        class UniqueYaml(yaml.SafeLoader):
            pass
        UniqueYaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                   lambda loader, node: unique(loader.construct_pairs(node)))
        source = yaml.load(raw, Loader=UniqueYaml)
        descriptor = resolve_pointer(source, release["pointer"])
        require(isinstance(descriptor, dict) and
                {"version", "urls", "sha256", "archive_members"} <= descriptor.keys(), "invalid-release-source")
        version = descriptor["version"]
        require(isinstance(version, str) and re.fullmatch(r"[A-Za-z0-9.+_-]{1,100}", version), "invalid-version")
        archives = release["archives"]
        require(isinstance(archives, dict) and bool(archives) and
                archives.keys() <= {"amd64", "arm64"}, "invalid-architecture")
        member_maps = [value for key, value in descriptor.items() if key == "archive_members" or key.endswith("_archive_members")]
        require(all(isinstance(value, dict) and archives.keys() <= value.keys()
                    for value in [descriptor["urls"], descriptor["sha256"], *member_maps]), "incomplete-architecture")
        architectures = {arch: {"url": descriptor["urls"][arch], "sha256": descriptor["sha256"][arch],
                               "archive": archive, "members": [value[arch] for value in member_maps]}
                         for arch, archive in archives.items()}
        for architecture, item in architectures.items():
            fields(item, ("url", "sha256", "archive", "members"))
            url = urlsplit(item["url"])
            require(url.scheme == "https" and url.hostname and not url.username and not url.password
                    and not url.query and not url.fragment and
                    version.removeprefix("v") in
                    [unquote(part).removeprefix("v") for part in url.path.split("/")],
                    "invalid-release-url")
            data = read_owned(item["archive"], private=False)
            total += len(data)
            require(total <= MAX_BYTES, "release-size-limit")
            require(sha256(data) == item["sha256"], "archive-checksum-mismatch")
            members = item["members"]
            require(isinstance(members, list) and 1 <= len(members) <= 16
                    and len(set(members)) == len(members), "invalid-selected-members")
            for name in members:
                member_name(name)
            found = set()
            if zipfile.is_zipfile(io.BytesIO(data)):
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    rows = archive.infolist()
                    require(len(rows) <= 10000, "archive-member-limit")
                    expanded = 0
                    seen = set()
                    for row in rows:
                        name = row.filename.rstrip("/")
                        member_name(name)
                        require(name not in seen, "duplicate-member")
                        seen.add(name)
                        mode = row.external_attr >> 16
                        require(not (mode & 0o170000) or (mode & 0o170000) in (0o100000, 0o040000), "unsafe-member")
                        expanded += row.file_size
                        require(expanded <= MAX_BYTES, "archive-expanded-limit")
                        if row.filename in members:
                            require(not row.is_dir() and len(archive.read(row)) == row.file_size, "invalid-selected-member")
                            found.add(row.filename)
            else:
                with gzip.GzipFile(fileobj=io.BytesIO(data)) if data.startswith(b"\x1f\x8b") else io.BytesIO(data) as stream:
                    expanded_data = stream.read(MAX_BYTES + 1)
                require(len(expanded_data) <= MAX_BYTES, "archive-expanded-limit")
                with tarfile.open(fileobj=io.BytesIO(expanded_data), mode="r:") as archive:
                    expanded = 0
                    seen = set()
                    for count, row in enumerate(archive, 1):
                        require(count <= 10000, "archive-member-limit")
                        member_name(row.name.rstrip("/"))
                        require(row.name not in seen and (row.isdir() or row.isfile()), "unsafe-or-duplicate-member")
                        seen.add(row.name)
                        expanded += row.size
                        require(0 <= row.size <= MAX_BYTES and expanded <= MAX_BYTES, "archive-expanded-limit")
                        if row.name in members:
                            require(row.isfile(), "invalid-selected-member")
                            found.add(row.name)
            require(found == set(members), "archive-member-mismatch")
        require(read_owned(release["source"], limit=4 * 1024 * 1024, with_identity=True) == (raw, authority),
                "release-source-changed")
    if "apt" in plan:
        check_apt(plan["apt"])
    return {"result": "release-inputs-verified", "architectures": sum(len(r["archives"]) for r in releases),
            "package_policy_checked": "apt" in plan, "runtime_version_qualified": False}
