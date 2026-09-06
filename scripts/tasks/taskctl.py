#!/usr/bin/env python3
"""Fail-closed portfolio, mdtask, and OpenSpec workflow for RIPDPI."""

from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CONFIG_PATH = Path("tools/tasking/project.json")
PROJECT_CONFIG_SCHEMA = 1
FEDERATION_CONTRACT_VERSION = 1
FEDERATION_CONTRACT_PATH = Path("tools/tasking/federation-contract-v1.json")
GENERATED_SKILL_NAMES = (
    "mdtask",
    "mdtask-create",
    "mdtask-next",
    "openspec-apply-change",
    "openspec-archive-change",
    "openspec-explore",
    "openspec-propose",
    "openspec-sync-specs",
    "openspec-update-change",
    "sdd",
)
ALIAS_SKILL_NAMES = (*GENERATED_SKILL_NAMES, "repo-task-board")
GENERATED_ASSET_PATHS = frozenset(
    (
        ".agents/skills/.openspec-target",
        *(f".agents/skills/{name}/SKILL.md" for name in GENERATED_SKILL_NAMES),
    )
)
COMPATIBILITY_SKILL_ROOTS = {
    ".claude/skills": "../../.agents/skills",
    ".codex/skills": "../../.claude/skills",
    ".github/skills": "../../.agents/skills",
}
STATUS_ORDER = ("doing", "review", "blocked", "todo", "backlog")
STATUSES = frozenset((*STATUS_ORDER, "done", "dropped"))
KINDS = frozenset(("feature", "bug", "chore", "research", "epic"))
PRIORITIES = ("critical", "high", "medium", "low")
RISKS = frozenset(("standard", "high"))
PRIORITY_ORDER = {value: index for index, value in enumerate(PRIORITIES)}
MDTASK_PRIORITY_TOKENS = {
    "critical": " !crit",
    "high": " !high",
    "medium": "",
    "low": " !low",
}
AREA_PREFIXES = {
    "engine": "ENG",
    "rust-native": "RST",
    "diagnostics": "DGN",
    "transport": "TRN",
    "outbound": "OUT",
    "dns": "DNS",
    "routing": "RTE",
    "vpn": "VPN",
    "proxy": "PRX",
    "relay": "RLY",
    "android": "AND",
    "ui": "UIX",
    "data": "DAT",
    "service": "SVC",
    "testing": "TST",
    "ci": "CIC",
    "epic": "EPC",
}
PREFIX_AREAS = {prefix: area for area, prefix in AREA_PREFIXES.items()}
SPEC_REASONS = frozenset(
    (
        "regression-tested-single-module",
        "test-only",
        "docs-only",
        "dependency-only",
        "mechanical-refactor",
        "tooling-only",
        "research-only",
    )
)
EVIDENCE_CATEGORIES = ("local", "remote_ci", "device", "artifact", "deployment")
EVIDENCE_STATES = frozenset(("required", "passed", "not_applicable", "blocked"))
SAFE_OPENSPEC_COMMANDS = frozenset(
    ("list", "show", "status", "instructions", "templates", "schemas", "schema", "validate", "doctor", "context", "new", "change", "spec")
)
ID_RE = re.compile(r"^([A-Z][A-Z0-9]*)-(\d{16})$")
STEP_RE = re.compile(r"^- \[([ xX])\] ([A-Z][A-Z0-9]*-\d{16})\s+(.+)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHANGE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
QUALIFIED_REF_RE = re.compile(
    r"^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([A-Z][A-Z0-9]*-\d{16})$"
)

REQUIRED_FIELDS = (
    "id",
    "title",
    "kind",
    "status",
    "area",
    "priority",
    "risk",
    "owner",
    "parent",
    "blocked_by",
    "spec_mode",
    "openspec_change",
    "created",
    "updated",
)
OPTIONAL_FIELD_ORDER = (
    "spec_reason",
    "source_" "wiki_pages",
    "related_tasks",
    "status_detail",
    "status_note",
    "closed_at",
    "closed_reason",
    "evidence_summary",
)
OPTIONAL_FIELDS = frozenset(OPTIONAL_FIELD_ORDER)
ALLOWED_FIELDS = frozenset((*REQUIRED_FIELDS, *OPTIONAL_FIELDS))


class ContractError(RuntimeError):
    """Raised when repository task state violates the contract."""


@dataclass(frozen=True)
class ProjectConfig:
    schema: int
    federation_contract: int
    project: str
    areas: dict[str, str]
    evidence_categories: tuple[str, ...]
    openspec_schema: str
    allowed_peers: tuple[str, ...]

    @property
    def prefix_areas(self) -> dict[str, str]:
        return {prefix: area for area, prefix in self.areas.items()}


@dataclass(frozen=True)
class Document:
    path: Path
    values: dict[str, Any]
    body: str

    @property
    def task_id(self) -> str:
        return str(self.values["id"])


@dataclass(frozen=True)
class Step:
    path: Path
    line: int
    task_id: str
    done: bool
    text: str
    item_id: str | None
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalTaskSnapshot:
    relative: str
    document: Document
    text: str


@dataclass(frozen=True, order=True)
class SharedEvidenceMapping:
    source_task: str
    owner_task: str
    requirement: str
    command: str
    category: str
    source_revision: str

@dataclass(frozen=True)
class TerminalHistoryIndex:
    root: Path
    project: str
    federation_contract: int
    revisions: tuple[str, ...]
    by_revision: dict[str, dict[str, HistoricalTaskSnapshot]]

@dataclass
class TerminalHistoryResolver:
    root: Path
    config: ProjectConfig
    index: TerminalHistoryIndex | None = None

    def resolve(
        self,
        task_id: str,
        *,
        allow_uncommitted_purge: bool = False,
    ) -> dict[str, Any] | None:
        if self.index is None:
            self.index = build_terminal_history_index(self.root, self.config)
        return resolve_terminal_task(
            self.root,
            task_id,
            self.config,
            allow_uncommitted_purge=allow_uncommitted_purge,
            history_index=self.index,
        )


def fail(message: str) -> None:
    raise ContractError(message)


def load_project_config(root: Path) -> ProjectConfig:
    path = root / PROJECT_CONFIG_PATH
    if not path.is_file():
        fail(f"missing project task config {PROJECT_CONFIG_PATH}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return parse_project_config(raw, path)


def parse_project_config(raw: Any, path: Path) -> ProjectConfig:
    required = {
        "schema",
        "federation_contract",
        "project",
        "areas",
        "evidence_categories",
        "openspec_schema",
        "allowed_peers",
    }
    missing = sorted(required - raw.keys()) if isinstance(raw, dict) else sorted(required)
    unknown = sorted(raw.keys() - required) if isinstance(raw, dict) else []
    if not isinstance(raw, dict) or missing or unknown:
        fail(f"{path}: project config fields missing={missing}, unknown={unknown}")
    if raw["schema"] != PROJECT_CONFIG_SCHEMA:
        fail(f"{path}: unsupported project config schema {raw['schema']!r}")
    if raw["federation_contract"] != FEDERATION_CONTRACT_VERSION:
        fail(f"{path}: unsupported federation contract {raw['federation_contract']!r}")
    project = raw["project"]
    if not isinstance(project, str) or not PROJECT_RE.fullmatch(project):
        fail(f"{path}: project must use owner/repository syntax")
    areas = raw["areas"]
    if not isinstance(areas, dict) or not areas:
        fail(f"{path}: areas must be a non-empty object")
    if not all(
        isinstance(area, str)
        and re.fullmatch(r"[a-z][a-z0-9-]*", area)
        and isinstance(prefix, str)
        and re.fullmatch(r"[A-Z][A-Z0-9]*", prefix)
        for area, prefix in areas.items()
    ):
        fail(f"{path}: invalid area or prefix")
    if len(set(areas.values())) != len(areas):
        fail(f"{path}: area prefixes must be unique")
    if areas.get("epic") != "EPC":
        fail(f"{path}: epic area must use EPC prefix")
    evidence = raw["evidence_categories"]
    if (
        not isinstance(evidence, list)
        or not evidence
        or len(evidence) != len(set(evidence))
        or not all(isinstance(item, str) and re.fullmatch(r"[a-z][a-z0-9_]*", item) for item in evidence)
    ):
        fail(f"{path}: evidence_categories must be unique snake-case names")
    openspec_schema = raw["openspec_schema"]
    if not isinstance(openspec_schema, str) or not CHANGE_RE.fullmatch(openspec_schema):
        fail(f"{path}: openspec_schema must be lowercase kebab-case")
    peers = raw["allowed_peers"]
    if (
        not isinstance(peers, list)
        or len(peers) != len(set(peers))
        or not all(isinstance(peer, str) and PROJECT_RE.fullmatch(peer) for peer in peers)
        or project in peers
    ):
        fail(f"{path}: allowed_peers must contain unique external owner/repository names")
    return ProjectConfig(
        schema=raw["schema"],
        federation_contract=raw["federation_contract"],
        project=project,
        areas=dict(areas),
        evidence_categories=tuple(evidence),
        openspec_schema=openspec_schema,
        allowed_peers=tuple(peers),
    )


def config_for_path(path: Path) -> ProjectConfig:
    current = path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / PROJECT_CONFIG_PATH).is_file():
            return load_project_config(candidate)
    fail(f"cannot find {PROJECT_CONFIG_PATH} above {path}")


def reference_parts(value: str, config: ProjectConfig) -> tuple[str, str]:
    if ID_RE.fullmatch(value):
        return config.project, value
    match = QUALIFIED_REF_RE.fullmatch(value)
    if match is None:
        fail(f"invalid task reference {value!r}; expected TASK-ID or owner/repository#TASK-ID")
    project, task_id = match.groups()
    if project == config.project:
        fail(f"qualified local reference {value!r} must use {task_id}")
    if project not in config.allowed_peers:
        fail(f"task reference {value!r} targets an unapproved project")
    return project, task_id


def qualify_reference(value: str, config: ProjectConfig) -> str:
    project, task_id = reference_parts(value, config)
    return f"{project}#{task_id}"


def local_reference(value: str, config: ProjectConfig) -> str | None:
    project, task_id = reference_parts(value, config)
    return task_id if project == config.project else None


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value in {"null", "~"}:
        return None
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(item) for item in inner.split(",")]
    if value.startswith(("'", '"')):
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, str):
            fail(f"expected quoted string, got {type(parsed).__name__}")
        return parsed
    return value


def read_document(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        fail(f"{path}: missing opening frontmatter delimiter")
    end = next(
        (index for index, line in enumerate(lines[1:], 1) if line.rstrip("\r\n") == "---"),
        None,
    )
    if end is None:
        fail(f"{path}: missing closing frontmatter delimiter")

    values: dict[str, Any] = {}
    index = 1
    while index < end:
        line = lines[index].rstrip("\r\n")
        if not line.strip():
            index += 1
            continue
        if line[0].isspace() or ":" not in line:
            fail(f"{path}:{index + 1}: unsupported frontmatter syntax")
        key, raw = line.split(":", 1)
        key = key.strip()
        if key in values:
            fail(f"{path}:{index + 1}: duplicate frontmatter key {key!r}")
        if raw.strip():
            values[key] = parse_scalar(raw)
            index += 1
            continue

        items: list[Any] = []
        index += 1
        while index < end:
            candidate = lines[index].rstrip("\r\n")
            match = re.match(r"^\s+-\s+(.+)$", candidate)
            if match is None:
                break
            items.append(parse_scalar(match.group(1)))
            index += 1
        values[key] = items

    return Document(path=path, values=values, body="".join(lines[end + 1 :]))


def quote_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(quote_scalar(item) for item in value) + "]"
    text = str(value)
    if not text or text != text.strip() or any(token in text for token in (":", "#", "[", "]", "{", "}")):
        return json.dumps(text, ensure_ascii=False)
    return text


def render_document(
    values: dict[str, Any],
    body: str,
    *,
    order: Sequence[str] | None = None,
    preserve_body: bool = False,
) -> str:
    ordered = list(order or REQUIRED_FIELDS)
    if order is None:
        ordered.extend(key for key in OPTIONAL_FIELD_ORDER if key in values)
    lines = ["---"]
    for key in ordered:
        value = values.get(key)
        if key == "source_" "wiki_pages" and isinstance(value, list) and value:
            lines.append(f"{key}:")
            lines.extend(f"  - {quote_scalar(item)}" for item in value)
        else:
            lines.append(f"{key}: {quote_scalar(value)}")
    lines.append("---")
    if preserve_body:
        return "\n".join(lines) + "\n" + body
    normalized_body = body.lstrip("\r\n").rstrip() + "\n"
    return "\n".join(lines) + "\n\n" + normalized_body


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "task"


def git_common_dir(root: Path) -> Path | None:
    result = subprocess.run(
        ("git", "rev-parse", "--git-common-dir"),
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else (root / path).resolve()


def allocate_id(root: Path, area: str, used_suffixes: set[str], config: ProjectConfig | None = None) -> str:
    config = config or load_project_config(root)
    if area not in config.areas:
        fail(f"unknown task area {area!r}")
    prefix = config.areas[area]
    common_dir = git_common_dir(root)
    reservation_path = common_dir / "taskctl-id-reservations" if common_dir else None

    def generate(reserved: set[str]) -> str:
        for _ in range(10_000):
            suffix = str(int(time.time() * 1000) * 1000 + random.SystemRandom().randrange(1000))
            if len(suffix) != 16:
                continue
            if suffix not in used_suffixes and suffix not in reserved:
                return suffix
        fail("unable to allocate a globally unique task ID")

    if reservation_path is None:
        return f"{prefix}-{generate(set())}"
    with reservation_path.open("a+", encoding="utf-8") as reservation:
        fcntl.flock(reservation.fileno(), fcntl.LOCK_EX)
        reservation.seek(0)
        reserved = {
            line.strip()
            for line in reservation
            if re.fullmatch(r"\d{16}", line.strip())
        }
        suffix = generate(reserved)
        reservation.write(suffix + "\n")
        reservation.flush()
        os.fsync(reservation.fileno())
        return f"{prefix}-{suffix}"


def issue_paths(root: Path) -> list[Path]:
    return sorted((root / "docs/tasks/issues").glob("*.md"))


def execution_paths(root: Path) -> list[Path]:
    return sorted((root / "docs/tasks/work").glob("*.md")) + sorted(
        path
        for path in (root / "openspec/changes").glob("*/tasks.md")
        if path.parent.name != "archive"
    )


def read_steps(path: Path) -> list[Step]:
    steps: list[Step] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = STEP_RE.match(line)
        if match is None:
            if re.match(r"^- \[[ xX]\]", line):
                fail(f"{path}:{number}: checkbox is not a valid mdtask record")
            continue
        text = match.group(3)
        item_match = re.search(r"(?:^|\s)@item:([^\s]+)", text)
        blockers = tuple(re.findall(r"(?:^|\s)@blocked_by:([^\s]+)", text))
        steps.append(
            Step(
                path=path,
                line=number,
                task_id=match.group(2),
                done=match.group(1).lower() == "x",
                text=text,
                item_id=item_match.group(1) if item_match else None,
                blockers=blockers,
            )
        )
    return steps


def lifecycle_receipt_path(root: Path, document: Document, execution: Path, kind: str) -> Path:
    if document.values["spec_mode"] == "required":
        return execution.parent / f".taskctl-{kind}.json"
    return execution.with_suffix(f".{kind}.json")


def read_lifecycle_receipt(
    root: Path,
    document: Document,
    execution: Path,
    kind: str,
) -> dict[str, Any]:
    path = lifecycle_receipt_path(root, document, execution, kind)
    if not path.is_file():
        fail(f"{document.path}: terminal {document.values['status']} state lacks taskctl {kind} receipt")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("task_id") != document.task_id:
        fail(f"{path}: receipt task backlink mismatch")
    if receipt.get("outcome") != document.values["status"]:
        fail(f"{path}: receipt outcome does not match terminal task")
    if document.values["spec_mode"] == "required" and receipt.get("change") != document.values["openspec_change"]:
        fail(f"{path}: receipt change backlink mismatch")
    if kind == "close":
        issue_hash = hashlib.sha256(document.path.read_bytes()).hexdigest()
        execution_hash = hashlib.sha256(execution.read_bytes()).hexdigest()
        if receipt.get("issue_sha256") != issue_hash or receipt.get("execution_sha256") != execution_hash:
            fail(f"{path}: close receipt content hashes do not match terminal state")
    return receipt


def validate_issue_shape(document: Document, config: ProjectConfig | None = None) -> None:
    config = config or config_for_path(document.path)
    values = document.values
    missing = [field for field in REQUIRED_FIELDS if field not in values]
    unknown = sorted(set(values) - ALLOWED_FIELDS)
    if missing:
        fail(f"{document.path}: missing fields: {', '.join(missing)}")
    if unknown:
        fail(f"{document.path}: unknown fields: {', '.join(unknown)}")
    for field in ("title", "owner", "created", "updated"):
        if not isinstance(values[field], str) or not values[field].strip():
            fail(f"{document.path}: {field} must be a non-empty string")
    if values["kind"] not in KINDS:
        fail(f"{document.path}: invalid kind {values['kind']!r}")
    if values["status"] not in STATUSES:
        fail(f"{document.path}: invalid status {values['status']!r}")
    if values["area"] not in config.areas:
        fail(f"{document.path}: invalid area {values['area']!r}")
    if values["priority"] not in PRIORITIES:
        fail(f"{document.path}: invalid priority {values['priority']!r}")
    if values["risk"] not in RISKS:
        fail(f"{document.path}: invalid risk {values['risk']!r}")
    if values["kind"] == "epic" and values["area"] != "epic":
        fail(f"{document.path}: epic kind requires epic area")
    if values["kind"] != "epic" and values["area"] == "epic":
        fail(f"{document.path}: epic area requires epic kind")
    match = ID_RE.fullmatch(str(values["id"]))
    if match is None:
        fail(f"{document.path}: invalid task ID {values['id']!r}")
    if config.prefix_areas.get(match.group(1)) != values["area"]:
        fail(f"{document.path}: ID prefix does not match area {values['area']!r}")
    for field in ("created", "updated"):
        raw_date = values[field]
        if not DATE_RE.fullmatch(raw_date):
            fail(f"{document.path}: {field} must use YYYY-MM-DD")
        try:
            date.fromisoformat(raw_date)
        except ValueError as error:
            fail(f"{document.path}: invalid {field}: {error}")
    if values["parent"] is not None:
        if not isinstance(values["parent"], str):
            fail(f"{document.path}: parent must be an ID or null")
        reference_parts(values["parent"], config)
    if not isinstance(values["blocked_by"], list) or not all(
        isinstance(value, str) for value in values["blocked_by"]
    ):
        fail(f"{document.path}: blocked_by must be a list of task references")
    for blocker in values["blocked_by"]:
        reference_parts(blocker, config)
    related = values.get("related_tasks", [])
    if not isinstance(related, list) or not all(isinstance(value, str) for value in related):
        fail(f"{document.path}: related_tasks must be a list of task references")
    for relation in related:
        reference_parts(relation, config)
    if values["status"] == "blocked" and not values["blocked_by"] and not values.get("status_detail"):
        fail(f"{document.path}: blocked task requires blocked_by or status_detail")
    if values["spec_mode"] not in {"required", "not-required"}:
        fail(f"{document.path}: spec_mode must be required or not-required")
    change = values["openspec_change"]
    if values["spec_mode"] == "required":
        if not isinstance(change, str) or not CHANGE_RE.fullmatch(change):
            fail(f"{document.path}: required OpenSpec change must be lowercase kebab-case")
        if values.get("spec_reason") is not None:
            fail(f"{document.path}: required OpenSpec task cannot have spec_reason")
    else:
        if change is not None:
            fail(f"{document.path}: spec-not-required task cannot link an OpenSpec change")
        if values.get("spec_reason") not in SPEC_REASONS:
            fail(f"{document.path}: invalid or missing spec_reason")
        if values["kind"] in {"feature", "epic"}:
            fail(f"{document.path}: {values['kind']} cannot waive OpenSpec")
        if values["risk"] == "high":
            fail(f"{document.path}: high-risk task cannot waive OpenSpec")
    for field in ("source_" "wiki_pages", "blocked_by", "related_tasks"):
        value = values.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            fail(f"{document.path}: {field} must be a string list")
    if values["status"] in {"done", "dropped"}:
        for field in ("closed_at", "closed_reason", "evidence_summary"):
            if not isinstance(values.get(field), str) or not values[field].strip():
                fail(f"{document.path}: terminal task requires {field}")
    elif any(field in values for field in ("closed_at", "closed_reason", "evidence_summary")):
        fail(f"{document.path}: non-terminal task cannot contain closure fields")


def assert_acyclic(edges: dict[str, list[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            fail(f"{label} cycle: {' -> '.join((*trail, node))}")
        if node in visited:
            return
        visiting.add(node)
        for target in edges.get(node, []):
            visit(target, [*trail, node])
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        visit(node, [])


def evidence_values(path: Path, config: ProjectConfig | None = None) -> dict[str, Any]:
    config = config or config_for_path(path)
    document = read_document(path)
    required = {"task_id", "change", "commit_sha"}
    for category in config.evidence_categories:
        required.update((category, f"{category}_evidence"))
    missing = sorted(required - document.values.keys())
    unknown = sorted(set(document.values) - required)
    if missing or unknown:
        fail(f"{path}: verification fields missing={missing}, unknown={unknown}")
    for category in config.evidence_categories:
        state = document.values[category]
        if state not in EVIDENCE_STATES:
            fail(f"{path}: invalid {category} evidence state {state!r}")
        evidence = document.values[f"{category}_evidence"]
        if state in {"passed", "not_applicable", "blocked"} and (
            not isinstance(evidence, str) or not evidence.strip()
        ):
            fail(f"{path}: {category}_evidence required for {state}")
    return document.values


def shared_evidence_mappings(
    verification: Document,
    config: ProjectConfig,
) -> tuple[SharedEvidenceMapping, ...]:
    heading = "## Shared operational evidence ownership"
    header = (
        "| Source task | Operational owner | Requirement | Acceptance command | "
        "Evidence category | Source revision |"
    )
    separator = "|---|---|---|---|---|---|"
    lines = verification.body.splitlines()
    indexes = [index for index, line in enumerate(lines) if line.strip() == heading]
    if not indexes:
        return ()
    if len(indexes) != 1:
        fail(f"{verification.path}: duplicate shared operational evidence section")
    index = indexes[0] + 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines) or lines[index].strip() != header:
        fail(f"{verification.path}: malformed shared operational evidence header")
    index += 1
    if index >= len(lines) or lines[index].strip() != separator:
        fail(f"{verification.path}: malformed shared operational evidence separator")
    index += 1
    mappings: list[SharedEvidenceMapping] = []
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        line = lines[index].strip()
        cells = (
            [cell.strip() for cell in line[1:-1].split("|")]
            if line.endswith("|")
            else []
        )
        if len(cells) != 6:
            fail(
                f"{verification.path}:{index + 1}: malformed shared operational evidence row"
            )
        (
            source_task,
            owner_task,
            requirement,
            command_cell,
            category,
            source_revision,
        ) = cells
        if ID_RE.fullmatch(source_task) is None or ID_RE.fullmatch(owner_task) is None:
            fail(
                f"{verification.path}:{index + 1}: shared evidence task IDs must be local stable IDs"
            )
        if source_task == owner_task:
            fail(
                f"{verification.path}:{index + 1}: shared evidence source and owner must differ"
            )
        if re.fullmatch(r"REQ-[A-Z0-9-]+", requirement) is None:
            fail(
                f"{verification.path}:{index + 1}: invalid shared evidence requirement"
            )
        if (
            len(command_cell) < 3
            or not command_cell.startswith("`")
            or not command_cell.endswith("`")
        ):
            fail(
                f"{verification.path}:{index + 1}: acceptance command must be one backtick-delimited command"
            )
        command = command_cell[1:-1].strip()
        if not command or "`" in command or "\n" in command:
            fail(f"{verification.path}:{index + 1}: invalid acceptance command")
        if category not in config.evidence_categories:
            fail(
                f"{verification.path}:{index + 1}: invalid shared evidence category {category!r}"
            )
        if SHA_RE.fullmatch(source_revision) is None:
            fail(
                f"{verification.path}:{index + 1}: source revision must be an exact 40-character SHA"
            )
        verification_task = verification.values.get("task_id")
        if verification_task not in {source_task, owner_task}:
            fail(
                f"{verification.path}:{index + 1}: shared evidence row does not include "
                f"verification task {verification_task}"
            )
        mappings.append(
            SharedEvidenceMapping(
                source_task=source_task,
                owner_task=owner_task,
                requirement=requirement,
                command=command,
                category=category,
                source_revision=source_revision,
            )
        )
        index += 1
    if not mappings:
        fail(
            f"{verification.path}: shared operational evidence section has no mappings"
        )
    if len(mappings) != len(set(mappings)):
        fail(f"{verification.path}: duplicate shared operational evidence mapping")
    return tuple(sorted(mappings))


def validate_source_revision(
    root: Path,
    source_revision: str,
    descendant_ref: str,
    *,
    context: str,
) -> None:
    commit = run_command(
        ("git", "cat-file", "-e", f"{source_revision}^{{commit}}"), root=root
    )
    if commit.returncode != 0:
        fail(f"{context}: source revision is not a commit")
    reachable = run_command(
        ("git", "merge-base", "--is-ancestor", source_revision, descendant_ref),
        root=root,
    )
    if reachable.returncode != 0:
        fail(f"{context}: source revision is not reachable from {descendant_ref}")


def validate_shared_requirement_coverage(
    context: str,
    category: str,
    source_requirements: set[str],
    mappings: Sequence[SharedEvidenceMapping],
) -> None:
    mapped_requirements = {mapping.requirement for mapping in mappings}
    if mapped_requirements != source_requirements:
        missing = sorted(source_requirements - mapped_requirements)
        extra = sorted(mapped_requirements - source_requirements)
        fail(
            f"{context}: shared {category} evidence does not map every source "
            f"requirement missing={missing}, extra={extra}"
        )


def archived_source_mappings(
    root: Path,
    config: ProjectConfig,
) -> dict[str, set[SharedEvidenceMapping]]:
    result: dict[str, set[SharedEvidenceMapping]] = {}
    for path in sorted(
        (root / "openspec/changes/archive").glob("*/verification.md")
    ):
        verification = read_document(path)
        task_id = verification.values.get("task_id")
        for mapping in shared_evidence_mappings(verification, config):
            if task_id == mapping.source_task:
                result.setdefault(mapping.source_task, set()).add(mapping)
    return result


def validate_requirement_evidence(
    change_dir: Path,
    steps: Sequence[Step],
    *,
    archived: bool,
    dropped_step_ids: set[str] | None = None,
    allow_incomplete: bool = False,
) -> None:
    requirement_ids: list[str] = []
    for spec in sorted((change_dir / "specs").glob("**/*.md")):
        requirement_ids.extend(
            re.findall(r"(?m)^### Requirement: (REQ-[A-Z0-9-]+)(?:\s|$)", spec.read_text(encoding="utf-8"))
        )
    if not requirement_ids:
        fail(f"{change_dir}: no stable REQ-* requirement IDs")
    if len(requirement_ids) != len(set(requirement_ids)):
        fail(f"{change_dir}: duplicate requirement IDs")
    verification = read_document(change_dir / "verification.md")
    rows: dict[str, tuple[str, str, str]] = {}
    for line in verification.body.splitlines():
        match = re.match(
            r"^\|\s*(REQ-[A-Z0-9-]+)\s*\|\s*([A-Z][A-Z0-9]*-\d{16})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$",
            line,
        )
        if allow_incomplete and re.match(r"^\s*\|\s*REQ-", line) and match is None:
            fail(f"{verification.path}: malformed requirement evidence row")
        if match:
            if allow_incomplete and match.group(1) in rows:
                fail(f"{verification.path}: duplicate requirement evidence row")
            rows[match.group(1)] = (match.group(2), match.group(3).strip(), match.group(4).strip())
    if set(rows) - set(requirement_ids) or (not allow_incomplete and set(rows) != set(requirement_ids)):
        missing = sorted(set(requirement_ids) - set(rows))
        extra = sorted(set(rows) - set(requirement_ids))
        fail(f"{verification.path}: requirement evidence mismatch missing={missing}, extra={extra}")
    step_ids = {step.task_id for step in steps} | (dropped_step_ids or set())
    for requirement_id, (step_id, evidence, result) in rows.items():
        if step_id not in step_ids:
            fail(f"{verification.path}: {requirement_id} maps to unknown step {step_id}")
        if archived and (
            evidence.casefold() in {"pending", "required", "blocked"}
            or result.casefold() not in {"passed", "not_applicable"}
        ):
            fail(f"{verification.path}: {requirement_id} lacks resolved archive evidence")


def requirement_ids(change_dir: Path) -> set[str]:
    found: list[str] = []
    for spec in sorted((change_dir / "specs").glob("**/*.md")):
        found.extend(
            re.findall(
                r"(?m)^### Requirement: (REQ-[A-Z0-9-]+)(?:\s|$)",
                spec.read_text(encoding="utf-8"),
            )
        )
    return set(found)


def validate_active_shared_evidence(
    root: Path,
    documents: Sequence[Document],
    config: ProjectConfig,
    historical: dict[str, dict[str, Any]] | None = None,
    *,
    authoring_task_id: str | None = None,
) -> None:
    historical = historical or {}
    by_id = {document.task_id: document for document in documents}
    verifications: dict[str, tuple[Document, dict[str, Any], Path]] = {}
    mappings_by_task: dict[str, set[SharedEvidenceMapping]] = {}
    for document in documents:
        if document.values["spec_mode"] != "required":
            continue
        change_dir = expected_execution_path(root, document).parent
        verification_path = change_dir / "verification.md"
        if document.task_id == authoring_task_id and not verification_path.is_file():
            continue
        verification = read_document(verification_path)
        values = evidence_values(verification.path, config)
        verifications[document.task_id] = (verification, values, change_dir)
        mappings_by_task[document.task_id] = set(
            shared_evidence_mappings(verification, config)
        )

    mappings = sorted(
        {
            mapping
            for task_mappings in mappings_by_task.values()
            for mapping in task_mappings
        }
    )

    # A purged source record is immutable, so every still-active owner that
    # retains its historical edge must also retain the matching mapping rows.
    # Otherwise an owner could silently erase the requirement-level contract
    # after the source disappeared from the working tree.
    for source_task, historical_source in historical.items():
        historical_mappings = {
            SharedEvidenceMapping(**raw)
            for raw in historical_source.get("_shared_evidence_mappings", [])
        }
        for mapping in historical_mappings:
            owner = by_id.get(mapping.owner_task)
            if owner is None:
                continue
            owner_related = {
                local
                for related in owner.values.get("related_tasks", [])
                if (local := local_reference(related, config)) is not None
            }
            if (
                source_task in owner_related
                and mapping not in mappings_by_task.get(mapping.owner_task, set())
            ):
                fail(
                    f"{mapping.owner_task}: shared {mapping.category} mapping "
                    "does not match historical source record"
                )

    for mapping in mappings:
        source = by_id.get(mapping.source_task)
        owner = by_id.get(mapping.owner_task)
        if owner is None:
            fail(
                f"{mapping.source_task}: shared {mapping.category} mapping owner "
                f"{mapping.owner_task} is not active"
            )
        source_record = verifications.get(mapping.source_task)
        owner_record = verifications.get(mapping.owner_task)
        historical_source = historical.get(mapping.source_task)
        if (
            source_record is None and historical_source is None
        ) or owner_record is None:
            fail("shared operational evidence requires OpenSpec source and owner tasks")
        source_mappings = (
            mappings_by_task[mapping.source_task]
            if source_record is not None
            else {
                SharedEvidenceMapping(**raw)
                for raw in historical_source.get("_shared_evidence_mappings", [])
            }
        )
        if mapping not in source_mappings:
            fail(
                f"{mapping.owner_task}: shared {mapping.category} mapping does not match source record"
            )
        if mapping not in mappings_by_task[mapping.owner_task]:
            fail(
                f"{mapping.source_task}: shared {mapping.category} mapping does not match owner record"
            )
        if mapping.source_task not in {
            local
            for related in owner.values.get("related_tasks", [])
            if (local := local_reference(related, config)) is not None
        }:
            fail(
                f"{owner.path}: shared evidence owner lacks related task {mapping.source_task}"
            )
        if source_record is not None:
            assert source is not None
            _, source_values, _ = source_record
            source_path = source.path
            source_document = source
        else:
            assert historical_source is not None
            source_values = historical_source.get("_verification", {})
            source_path = historical_source["path"]
            source_document = Document(
                path=Path(str(source_path)),
                values={
                    "id": mapping.source_task,
                    "spec_mode": "required",
                    "openspec_change": historical_source["openspec_change"],
                },
                body="",
            )
        if source_values["commit_sha"] != mapping.source_revision:
            fail(
                f"{source_path}: shared {mapping.category} mapping source revision "
                "does not match verification commit_sha"
            )
        descendant_ref = (
            "HEAD"
            if source_record is not None
            else str(historical_source["terminal_revision"])
        )
        validate_source_revision(
            root,
            mapping.source_revision,
            descendant_ref,
            context=str(source_path),
        )
        source_requirements = historical_requirement_ids(
            root,
            mapping.source_revision,
            source_document,
        )
        if mapping.requirement not in source_requirements:
            fail(
                f"{source_path}: shared {mapping.category} mapping names unknown "
                "requirement at source revision "
                f"{mapping.requirement}"
            )
        if source_values[mapping.category] == "not_applicable":
            validate_shared_requirement_coverage(
                str(source_path),
                mapping.category,
                source_requirements,
                [
                    candidate
                    for candidate in source_mappings
                    if candidate.source_task == mapping.source_task
                    and candidate.category == mapping.category
                ],
            )
        _, owner_values, _ = owner_record
        if owner_values[mapping.category] == "not_applicable":
            fail(
                f"{owner.path}: shared {mapping.category} evidence owner cannot be not_applicable"
            )


def expected_execution_path(root: Path, document: Document) -> Path:
    if document.values["spec_mode"] == "required":
        change = document.values["openspec_change"]
        active = root / "openspec/changes" / change / "tasks.md"
        if active.is_file():
            return active
        archives = sorted((root / "openspec/changes/archive").glob(f"*-{change}"))
        if len(archives) > 1:
            fail(f"{document.path}: multiple archives found for {change}")
        if archives:
            if document.values["status"] not in {"review", "done", "dropped"}:
                fail(f"{document.path}: archived change requires review or terminal status")
            return archives[0] / "tasks.md"
        return active
    return root / "docs/tasks/work" / f"{document.task_id}.md"


def load_state(root: Path, config: ProjectConfig | None = None) -> tuple[list[Document], list[Step]]:
    return _load_state(root, config)


def _load_state(
    root: Path,
    config: ProjectConfig | None = None,
    *,
    authoring_task_id: str | None = None,
    history_resolver: TerminalHistoryResolver | None = None,
) -> tuple[list[Document], list[Step]]:
    config = config or load_project_config(root)
    history_resolver = history_resolver or TerminalHistoryResolver(root, config)
    documents = [read_document(path) for path in issue_paths(root)]
    if not documents:
        fail("portfolio is empty")
    for document in documents:
        validate_issue_shape(document, config)

    ids: dict[str, Document] = {}
    suffixes: dict[str, str] = {}
    changes: dict[str, str] = {}
    for document in documents:
        if document.task_id in ids:
            fail(f"duplicate portfolio ID {document.task_id}")
        ids[document.task_id] = document
        suffix = ID_RE.fullmatch(document.task_id).group(2)  # type: ignore[union-attr]
        if suffix in suffixes:
            fail(
                f"numeric ID suffix {suffix} reused by {suffixes[suffix]} and {document.task_id}"
            )
        suffixes[suffix] = document.task_id
        change = document.values["openspec_change"]
        if change is not None:
            if change in changes:
                fail(
                    f"OpenSpec change {change!r} linked by {changes[change]} and {document.task_id}"
                )
            changes[change] = document.task_id

    parent_edges: dict[str, list[str]] = {}
    blocker_edges: dict[str, list[str]] = {}
    historical_related: dict[str, dict[str, Any]] = {}
    for source_task, mappings in archived_source_mappings(root, config).items():
        if source_task in ids:
            continue
        active_owners = {
            mapping.owner_task for mapping in mappings if mapping.owner_task in ids
        }
        if not active_owners:
            continue
        historical = history_resolver.resolve(
            source_task,
            allow_uncommitted_purge=True,
        )
        if historical is None or historical["status"] != "done":
            fail(f"{source_task}: archived shared mapping lacks valid terminal history")
        historical_related[source_task] = historical
        for owner_task in sorted(active_owners):
            owner_related = {
                local
                for related in ids[owner_task].values.get("related_tasks", [])
                if (local := local_reference(related, config)) is not None
            }
            if source_task not in owner_related:
                fail(
                    f"{owner_task}: historical source record requires retained related task "
                    f"{source_task}"
                )
    for document in documents:
        parent = document.values["parent"]
        if parent is not None:
            local_parent = local_reference(parent, config)
            if local_parent is None:
                if (
                    qualify_reference(parent, config)
                    == f"{config.project}#{document.task_id}"
                ):
                    fail(f"{document.path}: self parent {parent!r}")
            elif local_parent == document.task_id or local_parent not in ids:
                fail(f"{document.path}: missing or self parent {parent!r}")
            elif ids[local_parent].values["kind"] != "epic":
                fail(f"{document.path}: parent {parent} is not an epic")
            if local_parent is not None:
                parent_edges[document.task_id] = [local_parent]
        blockers = document.values["blocked_by"]
        for blocker in blockers:
            local_blocker = local_reference(blocker, config)
            if local_blocker is not None and (
                local_blocker == document.task_id or local_blocker not in ids
            ):
                fail(f"{document.path}: missing or self blocker {blocker!r}")
        blocker_edges[document.task_id] = [
            local
            for blocker in blockers
            if (local := local_reference(blocker, config)) is not None
        ]
        for related in document.values.get("related_tasks", []):
            local_related = local_reference(related, config)
            if local_related == document.task_id:
                fail(f"{document.path}: missing or self related task {related!r}")
            if local_related is not None and local_related not in ids:
                historical = historical_related.get(local_related)
                if historical is None:
                    historical = history_resolver.resolve(
                        local_related,
                        allow_uncommitted_purge=True,
                    )
                if historical is None or historical["status"] != "done":
                    fail(
                        f"{document.path}: missing or incomplete related task {related!r}"
                    )
                historical_related[local_related] = historical
    assert_acyclic(parent_edges, "parent")
    assert_acyclic(blocker_edges, "blocker")

    discovered_paths = set(execution_paths(root))
    expected_paths: set[Path] = set()
    all_steps: list[Step] = []
    all_dropped_step_ids: dict[str, str] = {}
    for document in documents:
        path = expected_execution_path(root, document)
        authoring = document.task_id == authoring_task_id
        expected_paths.add(path)
        if not path.is_file() and not authoring:
            fail(f"{document.path}: missing execution file {path.relative_to(root)}")
        steps = read_steps(path) if path.is_file() else []
        drop_receipt: dict[str, Any] | None = None
        dropped_step_ids: set[str] = set()
        if document.values["status"] in {"done", "dropped"}:
            read_lifecycle_receipt(root, document, path, "close")
        if document.values["status"] == "dropped":
            drop_receipt = read_lifecycle_receipt(root, document, path, "drop")
            raw_dropped_ids = drop_receipt.get("dropped_step_ids")
            if not isinstance(raw_dropped_ids, list) or not all(
                isinstance(item, str) and ID_RE.fullmatch(item)
                for item in raw_dropped_ids
            ):
                fail(
                    f"{lifecycle_receipt_path(root, document, path, 'drop')}: invalid dropped_step_ids"
                )
            dropped_step_ids = set(raw_dropped_ids)
            for dropped_step_id in dropped_step_ids:
                prefix = ID_RE.fullmatch(dropped_step_id).group(1)  # type: ignore[union-attr]
                if config.prefix_areas.get(prefix) != document.values["area"]:
                    fail(
                        f"{document.path}: dropped step prefix does not match task area"
                    )
                if dropped_step_id in all_dropped_step_ids:
                    fail(f"duplicate dropped execution step ID {dropped_step_id}")
                all_dropped_step_ids[dropped_step_id] = document.task_id
        if not steps and document.values["status"] != "dropped" and not authoring:
            fail(f"{path}: no mdtask execution steps")
        for step in steps:
            if step.item_id != document.task_id:
                fail(f"{path}:{step.line}: @item must be {document.task_id}")
        if document.values["status"] in {"done", "dropped"} and any(
            not step.done for step in steps
        ):
            fail(f"{document.path}: terminal task contains open execution steps")
        all_steps.extend(steps)
        if document.values["spec_mode"] == "required":
            change_dir = path.parent
            proposal = change_dir / "proposal.md"
            verification = change_dir / "verification.md"
            metadata = change_dir / ".openspec.yaml"
            for required_path in (proposal, verification, metadata):
                if (
                    authoring
                    and required_path == verification
                    and not verification.exists()
                ):
                    continue
                if not required_path.is_file():
                    fail(f"{document.path}: missing {required_path.relative_to(root)}")
            if f"Task ID: `{document.task_id}`" not in proposal.read_text(
                encoding="utf-8"
            ):
                fail(f"{proposal}: missing exact portfolio backlink")
            if authoring and not verification.exists():
                continue
            evidence = evidence_values(verification, config)
            if (
                evidence["task_id"] != document.task_id
                or evidence["change"] != document.values["openspec_change"]
            ):
                fail(f"{verification}: backlink does not match portfolio task")
            archived = change_dir.parent.name == "archive"
            validate_requirement_evidence(
                change_dir,
                steps,
                archived=archived,
                dropped_step_ids=dropped_step_ids,
                allow_incomplete=authoring,
            )
            if document.values["status"] == "done" and not archived:
                fail(f"{document.path}: done task requires an archived OpenSpec change")
            if archived:
                if any(not step.done for step in steps):
                    fail(f"{change_dir}: archived change contains open execution steps")
                if any(
                    evidence[category] in {"required", "blocked"}
                    for category in config.evidence_categories
                ):
                    fail(
                        f"{verification}: archived change contains incomplete evidence"
                    )
                if not isinstance(evidence["commit_sha"], str) or not SHA_RE.fullmatch(
                    evidence["commit_sha"]
                ):
                    fail(f"{verification}: archived change lacks an exact commit SHA")
                receipt_path = change_dir / ".taskctl-archive.json"
                if not receipt_path.is_file():
                    fail(f"{change_dir}: archive was not created by taskctl")
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if (
                    receipt.get("task_id") != document.task_id
                    or receipt.get("change") != document.values["openspec_change"]
                ):
                    fail(f"{receipt_path}: archive receipt backlink mismatch")
    validate_active_shared_evidence(
        root,
        documents,
        config,
        historical_related,
        authoring_task_id=authoring_task_id,
    )
    extras = discovered_paths - expected_paths
    if extras:
        fail(
            "orphan execution files: "
            + ", ".join(str(path.relative_to(root)) for path in sorted(extras))
        )

    step_ids: dict[str, Step] = {}
    for step in all_steps:
        match = ID_RE.fullmatch(step.task_id)
        if match is None:
            fail(f"{step.path}:{step.line}: invalid step ID {step.task_id}")
        suffix = match.group(2)
        if suffix in suffixes:
            fail(
                f"numeric ID suffix {suffix} reused by {suffixes[suffix]} and {step.task_id}"
            )
        suffixes[suffix] = step.task_id
        if step.task_id in step_ids:
            fail(f"duplicate execution step ID {step.task_id}")
        step_ids[step.task_id] = step
    for dropped_step_id, item_id in all_dropped_step_ids.items():
        suffix = ID_RE.fullmatch(dropped_step_id).group(2)  # type: ignore[union-attr]
        if suffix in suffixes:
            fail(
                f"numeric ID suffix {suffix} reused by {suffixes[suffix]} and {dropped_step_id}"
            )
        suffixes[suffix] = dropped_step_id
        if dropped_step_id in step_ids:
            fail(
                f"dropped execution step ID {dropped_step_id} is still active for {item_id}"
            )
    for step in all_steps:
        for blocker in step.blockers:
            if blocker not in step_ids:
                fail(f"{step.path}:{step.line}: missing step blocker {blocker}")
    assert_acyclic(
        {step.task_id: list(step.blockers) for step in all_steps},
        "execution blocker",
    )
    return documents, all_steps


def progress_by_item(steps: Iterable[Step]) -> dict[str, tuple[int, int]]:
    totals: dict[str, list[int]] = {}
    for step in steps:
        if step.item_id is None:
            continue
        progress = totals.setdefault(step.item_id, [0, 0])
        progress[1] += 1
        if step.done:
            progress[0] += 1
    return {task_id: (values[0], values[1]) for task_id, values in totals.items()}


def git_revision(root: Path) -> str:
    result = run_command(("git", "rev-parse", "HEAD"), root=root)
    revision = (result.stdout or "").strip()
    if result.returncode != 0 or not SHA_RE.fullmatch(revision):
        fail(f"cannot resolve Git revision for {root}")
    return revision


def federation_contract_hash(root: Path) -> str:
    path = root / FEDERATION_CONTRACT_PATH
    if not path.is_file():
        fail(f"missing federation contract {FEDERATION_CONTRACT_PATH}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("contract_version") != FEDERATION_CONTRACT_VERSION:
        fail(f"{path}: incompatible federation contract artifact")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_export_checkout(root: Path) -> None:
    result = run_command(
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "docs/tasks/issues",
            "docs/tasks/work",
            "openspec/changes",
            str(PROJECT_CONFIG_PATH),
            str(FEDERATION_CONTRACT_PATH),
        ),
        root=root,
    )
    if result.returncode != 0:
        fail(f"cannot inspect export checkout state in {root}")
    dirty = (result.stdout or "").strip()
    if dirty:
        fail("task export requires committed portfolio, OpenSpec, project config, and federation contract state")


def export_payload(
    root: Path,
    history_resolver: TerminalHistoryResolver | None = None,
) -> dict[str, Any]:
    validate_export_checkout(root)
    config = load_project_config(root)
    history_resolver = history_resolver or TerminalHistoryResolver(root, config)
    documents, steps = _load_state(
        root,
        config,
        history_resolver=history_resolver,
    )
    progress = progress_by_item(steps)
    tasks: list[dict[str, Any]] = []
    for document in sorted(documents, key=lambda item: item.task_id):
        done, total = progress.get(document.task_id, (0, 0))
        parent = document.values["parent"]
        tasks.append(
            {
                "id": f"{config.project}#{document.task_id}",
                "task_id": document.task_id,
                "path": document.path.relative_to(root).as_posix(),
                "kind": document.values["kind"],
                "risk": document.values["risk"],
                "status": document.values["status"],
                "progress": {"done": done, "total": total},
                "parent": (
                    qualify_reference(parent, config) if parent is not None else None
                ),
                "blocked_by": sorted(
                    qualify_reference(value, config)
                    for value in document.values["blocked_by"]
                ),
                "related_tasks": sorted(
                    qualify_reference(value, config)
                    for value in document.values.get("related_tasks", [])
                ),
                "openspec_change": document.values["openspec_change"],
                "historical": False,
            }
        )
    return {
        "contract_version": config.federation_contract,
        "contract_sha256": federation_contract_hash(root),
        "project": config.project,
        "revision": git_revision(root),
        "tasks": tasks,
    }


def git_show_text(root: Path, ref: str, path: str) -> str | None:
    result = run_command(("git", "show", f"{ref}:{path}"), root=root)
    return result.stdout if result.returncode == 0 else None


def git_tree_paths(root: Path, ref: str, prefix: str) -> list[str]:
    result = run_command(("git", "ls-tree", "-r", "--name-only", ref, "--", prefix), root=root)
    if result.returncode != 0:
        fail(f"cannot inspect Git tree {ref} in {root}")
    return sorted(filter(None, (result.stdout or "").splitlines()))


def historical_execution_path(root: Path, ref: str, document: Document) -> str:
    if document.values["spec_mode"] == "not-required":
        return f"docs/tasks/work/{document.task_id}.md"
    change = document.values["openspec_change"]
    active = f"openspec/changes/{change}/tasks.md"
    if git_show_text(root, ref, active) is not None:
        return active
    matches = [
        path
        for path in git_tree_paths(root, ref, "openspec/changes/archive")
        if path.endswith(f"-{change}/tasks.md")
    ]
    if len(matches) != 1:
        fail(f"{document.task_id}: terminal history has no unique OpenSpec execution file")
    return matches[0]


def historical_verification_document(
    root: Path,
    ref: str,
    document: Document,
    scratch: Path,
) -> Document:
    execution = historical_execution_path(root, ref, document)
    verification_text = git_show_text(
        root,
        ref,
        f"{execution.rsplit('/', 1)[0]}/verification.md",
    )
    if verification_text is None:
        fail(f"{document.task_id}: historical verification record is missing at {ref}")
    verification_path = scratch / "historical-verification.md"
    verification_path.write_text(verification_text, encoding="utf-8")
    return read_document(verification_path)

def historical_verification_values(
    root: Path,
    ref: str,
    document: Document,
    config: ProjectConfig,
    scratch: Path,
) -> dict[str, Any]:
    verification = historical_verification_document(root, ref, document, scratch)
    return evidence_values(verification.path, config)

def historical_requirement_ids(root: Path, ref: str, document: Document) -> set[str]:
    execution = historical_execution_path(root, ref, document)
    change_root = execution.rsplit("/", 1)[0]
    requirements: set[str] = set()
    for path in git_tree_paths(root, ref, f"{change_root}/specs"):
        if not path.endswith(".md"):
            continue
        text = git_show_text(root, ref, path)
        if text is not None:
            requirements.update(
                re.findall(r"(?m)^### Requirement: (REQ-[A-Z0-9-]+)(?:\s|$)", text)
            )
    return requirements

def validate_historical_shared_transfer(
    root: Path,
    *,
    task_id: str,
    category: str,
    previous_state: str,
    source_ref: str,
    source_snapshot: HistoricalTaskSnapshot,
    snapshots_at_source: dict[str, HistoricalTaskSnapshot],
    config: ProjectConfig,
    scratch: Path,
) -> None:
    source_verification = historical_verification_document(
        root,
        source_ref,
        source_snapshot.document,
        scratch,
    )
    source_values = evidence_values(source_verification.path, config)
    candidates = [
        mapping
        for mapping in shared_evidence_mappings(source_verification, config)
        if mapping.source_task == task_id and mapping.category == category
    ]
    if not candidates:
        fail(
            f"{source_snapshot.relative}: {category} evidence changed from {previous_state} "
            "to not_applicable without a shared mapping"
        )
    source_requirements = historical_requirement_ids(
        root,
        source_ref,
        source_snapshot.document,
    )
    validate_shared_requirement_coverage(
        source_snapshot.relative,
        category,
        source_requirements,
        candidates,
    )
    for mapping in candidates:
        if mapping.source_revision != source_values["commit_sha"]:
            fail(
                f"{source_snapshot.relative}: shared {category} mapping source revision "
                "does not match verification commit_sha"
            )
        validate_source_revision(
            root,
            mapping.source_revision,
            source_ref,
            context=source_snapshot.relative,
        )
        if mapping.requirement not in source_requirements:
            fail(
                f"{source_snapshot.relative}: shared {category} mapping names unknown requirement "
                f"{mapping.requirement}"
            )
        owner_snapshot = snapshots_at_source.get(mapping.owner_task)
        if owner_snapshot is None:
            fail(
                f"{source_snapshot.relative}: shared {category} mapping owner "
                f"{mapping.owner_task} is not active at transfer"
            )
        owner_document = owner_snapshot.document
        if task_id not in {
            local
            for related in owner_document.values.get("related_tasks", [])
            if (local := local_reference(related, config)) is not None
        }:
            fail(
                f"{owner_snapshot.relative}: shared evidence owner lacks related task {task_id}"
            )
        owner_verification = historical_verification_document(
            root,
            source_ref,
            owner_document,
            scratch,
        )
        owner_values = evidence_values(owner_verification.path, config)
        if mapping not in shared_evidence_mappings(owner_verification, config):
            fail(
                f"{owner_snapshot.relative}: shared {category} mapping does not match source record"
            )
        if owner_values[category] == "not_applicable":
            fail(
                f"{owner_snapshot.relative}: shared {category} evidence owner cannot be not_applicable"
            )


def validate_terminal_snapshot(
    root: Path,
    config: ProjectConfig,
    *,
    relative: str,
    terminal_ref: str,
    deletion_ref: str,
    document: Document,
    issue_text: str,
) -> tuple[str, list[Step]]:
    outcome = document.values["status"]
    execution_path = historical_execution_path(root, terminal_ref, document)
    execution_text = git_show_text(root, terminal_ref, execution_path)
    if execution_text is None:
        fail(f"{relative}: terminal execution snapshot is missing")
    with tempfile.TemporaryDirectory(prefix="taskctl-terminal-snapshot-") as directory:
        execution_file = Path(directory) / "execution.md"
        execution_file.write_text(execution_text, encoding="utf-8")
        terminal_steps = read_steps(execution_file)
    if outcome == "done" and not terminal_steps:
        fail(f"{relative}: completed task has no execution steps")
    if any(not step.done for step in terminal_steps):
        fail(f"{relative}: terminal commit contains open execution steps")

    if document.values["spec_mode"] == "required":
        receipt_root = execution_path.rsplit("/", 1)[0]
        close_path = f"{receipt_root}/.taskctl-close.json"
        drop_path = f"{receipt_root}/.taskctl-drop.json"
    else:
        receipt_root = f"docs/tasks/work/{document.task_id}"
        close_path = f"{receipt_root}.close.json"
        drop_path = f"{receipt_root}.drop.json"
    close_text = git_show_text(root, terminal_ref, close_path)
    close_receipt = json.loads(close_text) if close_text is not None else {}
    if (
        close_receipt.get("schema") != 1
        or close_receipt.get("task_id") != document.task_id
        or close_receipt.get("change") != document.values["openspec_change"]
        or close_receipt.get("outcome") != outcome
        or close_receipt.get("issue_sha256") != hashlib.sha256(issue_text.encode()).hexdigest()
        or close_receipt.get("execution_sha256") != hashlib.sha256(execution_text.encode()).hexdigest()
    ):
        fail(f"{relative}: close receipt does not match the terminal snapshot")
    drop_receipt: dict[str, Any] | None = None
    if outcome == "dropped":
        drop_text = git_show_text(root, terminal_ref, drop_path)
        drop_receipt = json.loads(drop_text) if drop_text is not None else {}
        dropped_ids = drop_receipt.get("dropped_step_ids")
        if (
            drop_receipt.get("schema") != 1
            or drop_receipt.get("task_id") != document.task_id
            or drop_receipt.get("change") != document.values["openspec_change"]
            or drop_receipt.get("outcome") != "dropped"
            or not isinstance(dropped_ids, list)
            or not all(isinstance(value, str) and ID_RE.fullmatch(value) for value in dropped_ids)
        ):
            fail(f"{relative}: invalid drop receipt in terminal commit")

    if document.values["spec_mode"] == "required":
        change = document.values["openspec_change"]
        archive_roots = {
            path.rsplit("/", 1)[0]
            for path in git_tree_paths(root, deletion_ref, "openspec/changes/archive")
            if path.endswith(f"-{change}/.taskctl-archive.json")
        }
        if len(archive_roots) != 1:
            fail(f"{relative}: terminal OpenSpec change was not archived before deletion")
        archive_root = next(iter(archive_roots))
        archived_close = git_show_text(root, deletion_ref, f"{archive_root}/.taskctl-close.json")
        if archived_close is None or json.loads(archived_close) != close_receipt:
            fail(f"{relative}: archived close receipt differs from terminal commit")
        archive_text = git_show_text(root, deletion_ref, f"{archive_root}/.taskctl-archive.json")
        archive_receipt = json.loads(archive_text) if archive_text is not None else {}
        expected_outcome = "dropped" if outcome == "dropped" else "review"
        if (
            archive_receipt.get("schema") != 1
            or archive_receipt.get("task_id") != document.task_id
            or archive_receipt.get("change") != change
            or archive_receipt.get("outcome") != expected_outcome
            or not SHA_RE.fullmatch(str(archive_receipt.get("commit_sha", "")))
        ):
            fail(f"{relative}: invalid OpenSpec archive receipt")
        verification_text = git_show_text(root, deletion_ref, f"{archive_root}/verification.md")
        if verification_text is None:
            fail(f"{relative}: archived verification record is missing")
        with tempfile.TemporaryDirectory(prefix="taskctl-terminal-verification-") as directory:
            verification_path = Path(directory) / "verification.md"
            verification_path.write_text(verification_text, encoding="utf-8")
            verification = evidence_values(verification_path, config)
        if (
            verification.get("task_id") != document.task_id
            or verification.get("change") != change
            or verification.get("commit_sha") != archive_receipt.get("commit_sha")
            or any(verification[category] in {"required", "blocked"} for category in config.evidence_categories)
        ):
            fail(f"{relative}: archive receipt does not match resolved verification evidence")
        if outcome == "dropped":
            archived_drop = git_show_text(root, deletion_ref, f"{archive_root}/.taskctl-drop.json")
            if archived_drop is None or json.loads(archived_drop) != drop_receipt:
                fail(f"{relative}: archived drop receipt differs from terminal commit")
    return execution_text, terminal_steps


def build_terminal_history_index(
    root: Path,
    config: ProjectConfig,
) -> TerminalHistoryIndex:
    resolved_root = root.resolve()
    shallow = run_command(("git", "rev-parse", "--is-shallow-repository"), root=root)
    if shallow.returncode != 0:
        fail(f"cannot inspect Git history for {root}")
    if (shallow.stdout or "").strip() == "true":
        fail(f"peer checkout {root} is shallow; full history is required")
    config_history = run_command(
        (
            "git",
            "log",
            "--first-parent",
            "--reverse",
            "--format=%H",
            "--",
            str(PROJECT_CONFIG_PATH),
        ),
        root=root,
    )
    config_revisions = list(filter(None, (config_history.stdout or "").splitlines()))
    if config_history.returncode != 0 or not config_revisions:
        fail(f"cannot locate strict task contract history in {root}")
    start = config_revisions[0]
    history = run_command(
        (
            "git",
            "rev-list",
            "--first-parent",
            "--reverse",
            "--ancestry-path",
            f"{start}..HEAD",
        ),
        root=root,
    )
    if history.returncode != 0:
        fail(f"cannot inspect task state transitions in {root}")
    revisions = (start, *filter(None, (history.stdout or "").splitlines()))
    with tempfile.TemporaryDirectory(prefix="taskctl-terminal-history-") as directory:
        scratch = Path(directory)
        by_revision = {
            revision: historical_task_snapshots(root, revision, scratch)
            for revision in revisions
        }
    return TerminalHistoryIndex(
        root=resolved_root,
        project=config.project,
        federation_contract=config.federation_contract,
        revisions=revisions,
        by_revision=by_revision,
    )


def resolve_terminal_task(
    root: Path,
    task_id: str,
    config: ProjectConfig,
    *,
    allow_uncommitted_purge: bool = False,
    history_index: TerminalHistoryIndex | None = None,
) -> dict[str, Any] | None:
    history_index = history_index or build_terminal_history_index(root, config)
    if (
        history_index.root != root.resolve()
        or history_index.project != config.project
        or history_index.federation_contract != config.federation_contract
    ):
        fail(f"terminal history index does not match {root}")
    revisions = history_index.revisions
    by_revision = history_index.by_revision

    with tempfile.TemporaryDirectory(prefix="taskctl-federation-history-") as directory:
        scratch = Path(directory)
        timeline = [
            (revision, by_revision[revision].get(task_id)) for revision in revisions
        ]
        synthetic_deletion = False
        if timeline[-1][1] is not None:
            if not allow_uncommitted_purge:
                return None
            final_snapshot = timeline[-1][1]
            assert final_snapshot is not None
            if (root / final_snapshot.relative).exists():
                return None
            document = final_snapshot.document
            if document.values.get("spec_mode") == "required":
                change = document.values.get("openspec_change")
                if (root / "openspec/changes" / str(change)).exists():
                    return None
                archives = list((root / "openspec/changes/archive").glob(f"*-{change}"))
                if len(archives) != 1:
                    return None
            else:
                work = root / f"docs/tasks/work/{task_id}.md"
                if (
                    work.exists()
                    or work.with_suffix(".close.json").exists()
                    or work.with_suffix(".drop.json").exists()
                ):
                    return None
            timeline.append((revisions[-1], None))
            synthetic_deletion = True
        deletion_indexes = [
            index
            for index in range(1, len(timeline))
            if timeline[index - 1][1] is not None and timeline[index][1] is None
        ]
        if not deletion_indexes:
            return None
        deletion_index = deletion_indexes[-1]
        deletion = timeline[deletion_index][0]
        final_ref, final_snapshot = timeline[deletion_index - 1]
        assert final_snapshot is not None
        historical_config = historical_project_config(root, final_ref, scratch)
        if (
            historical_config.project != config.project
            or historical_config.federation_contract != config.federation_contract
        ):
            fail(f"{config.project}#{task_id}: historical project contract mismatch")
        document = final_snapshot.document
        relative = final_snapshot.relative
        validate_issue_shape(document, historical_config)
        outcome = document.values["status"]
        if outcome not in {"done", "dropped"}:
            fail(f"{config.project}#{task_id}: deletion lacks a terminal state")

        last_absent = max(
            (
                index
                for index, (_, snapshot) in enumerate(timeline[:deletion_index])
                if snapshot is None
            ),
            default=-1,
        )
        incarnation = timeline[last_absent + 1 : deletion_index]
        previous_status: str | None = None
        terminal_transition: str | None = None
        terminal_index: int | None = None
        for index, (revision, snapshot) in enumerate(incarnation):
            assert snapshot is not None
            status = snapshot.document.values.get("status")
            if status in {"done", "dropped"}:
                terminal_transition = revision
                terminal_index = index
                break
            previous_status = status
        if terminal_transition is None or terminal_index is None:
            fail(f"{config.project}#{task_id}: terminal transition commit is missing")
        initial_strict_terminal = (
            terminal_index == 0 and incarnation[0][0] == revisions[0]
        )
        if not initial_strict_terminal and (
            previous_status is None or not transition_allowed(previous_status, outcome)
        ):
            fail(
                f"{config.project}#{task_id}: invalid terminal transition "
                f"{previous_status or 'missing'} -> {outcome}"
            )
        for _, snapshot in incarnation[terminal_index:]:
            assert snapshot is not None
            if snapshot.document.values.get("status") != outcome:
                fail(
                    f"{config.project}#{task_id}: task transitioned out of terminal state"
                )

        _, parsed_steps = validate_terminal_snapshot(
            root,
            historical_config,
            relative=relative,
            terminal_ref=final_ref,
            deletion_ref=deletion,
            document=document,
            issue_text=final_snapshot.text,
        )
        done = sum(1 for step in parsed_steps if step.done)
        terminal_sha_result = run_command(
            ("git", "rev-parse", terminal_transition), root=root
        )
        terminal_sha = (terminal_sha_result.stdout or "").strip()
        if terminal_sha_result.returncode != 0 or not SHA_RE.fullmatch(terminal_sha):
            fail(f"{config.project}#{task_id}: cannot resolve terminal revision")
        historical_evidence: dict[str, Any] = {}
        historical_mappings: list[dict[str, str]] = []
        historical_requirements: list[str] = []
        if document.values["spec_mode"] == "required":
            verification = historical_verification_document(
                root,
                final_ref,
                document,
                scratch,
            )
            historical_evidence = evidence_values(verification.path, historical_config)
            historical_mappings = [
                {
                    "source_task": mapping.source_task,
                    "owner_task": mapping.owner_task,
                    "requirement": mapping.requirement,
                    "command": mapping.command,
                    "category": mapping.category,
                    "source_revision": mapping.source_revision,
                }
                for mapping in shared_evidence_mappings(verification, historical_config)
            ]
            historical_requirements = sorted(
                historical_requirement_ids(root, final_ref, document)
            )
        return {
            "id": f"{config.project}#{task_id}",
            "task_id": task_id,
            "path": relative,
            "kind": document.values["kind"],
            "risk": document.values["risk"],
            "status": outcome,
            "progress": {"done": done, "total": len(parsed_steps)},
            "parent": (
                qualify_reference(document.values["parent"], historical_config)
                if document.values["parent"] is not None
                else None
            ),
            "blocked_by": sorted(
                qualify_reference(value, historical_config)
                for value in document.values["blocked_by"]
            ),
            "related_tasks": sorted(
                qualify_reference(value, historical_config)
                for value in document.values.get("related_tasks", [])
            ),
            "openspec_change": document.values["openspec_change"],
            "historical": True,
            "terminal_revision": terminal_sha,
            "deletion_revision": None if synthetic_deletion else deletion,
            "_verification": historical_evidence,
            "_shared_evidence_mappings": historical_mappings,
            "_requirements": historical_requirements,
        }


def federation_payload(root: Path, peer_root: Path) -> dict[str, Any]:
    roots = {root.resolve(), peer_root.resolve()}
    if len(roots) != 2:
        fail("federation requires a distinct peer checkout")
    configs_by_root = {candidate: load_project_config(candidate) for candidate in roots}
    configs = {config.project: config for config in configs_by_root.values()}
    roots_by_project = {
        config.project: candidate for candidate, config in configs_by_root.items()
    }
    if len(configs) != 2:
        fail("federation projects must have distinct identities")
    history_resolvers = {
        project: TerminalHistoryResolver(roots_by_project[project], config)
        for project, config in configs.items()
    }
    exports = [
        export_payload(candidate, history_resolvers[configs_by_root[candidate].project])
        for candidate in sorted(roots, key=str)
    ]
    for payload in exports:
        if payload["contract_version"] != FEDERATION_CONTRACT_VERSION:
            fail(f"{payload['project']}: incompatible federation contract")
        config = configs[payload["project"]]
        other_projects = set(configs) - {config.project}
        if not other_projects.issubset(set(config.allowed_peers)):
            fail(f"{config.project}: federation checkout contains an unapproved peer")
    contract_hashes = {payload["contract_sha256"] for payload in exports}
    if len(contract_hashes) != 1:
        fail("federation contract artifacts differ between repositories")
    nodes = {task["id"]: dict(task) for payload in exports for task in payload["tasks"]}
    pending = {
        reference
        for node in nodes.values()
        for reference in ([node["parent"]] if node["parent"] else [])
        + node["blocked_by"]
        + node["related_tasks"]
    }
    while True:
        missing = sorted(pending - nodes.keys())
        if not missing:
            break
        pending = set()
        for reference in missing:
            match = QUALIFIED_REF_RE.fullmatch(reference)
            if match is None or match.group(1) not in roots_by_project:
                fail(f"unknown federated task reference {reference!r}")
            project, task_id = match.groups()
            historical = history_resolvers[project].resolve(task_id)
            if historical is None:
                fail(f"missing federated task {reference}")
            nodes[reference] = {
                key: value
                for key, value in historical.items()
                if not key.startswith("_")
            }
            pending.update(
                ([historical["parent"]] if historical["parent"] else [])
                + historical["blocked_by"]
                + historical["related_tasks"]
            )
    parent_edges: dict[str, list[str]] = {}
    blocker_edges: dict[str, list[str]] = {}
    reverse_blocks: dict[str, list[str]] = {identity: [] for identity in nodes}
    children: dict[str, list[str]] = {identity: [] for identity in nodes}
    for identity, node in nodes.items():
        relations = (
            ([node["parent"]] if node["parent"] else [])
            + node["blocked_by"]
            + node["related_tasks"]
        )
        if identity in relations:
            fail(f"self federated reference {identity}")
        if node["parent"] is not None:
            if nodes[node["parent"]]["kind"] != "epic":
                fail(f"{identity}: parent {node['parent']} is not an epic")
            parent_edges[identity] = [node["parent"]]
            children[node["parent"]].append(identity)
        blocker_edges[identity] = list(node["blocked_by"])
        for blocker in node["blocked_by"]:
            if nodes[blocker]["status"] == "dropped":
                fail(f"{identity}: blocker {blocker} was dropped")
            reverse_blocks[blocker].append(identity)
    assert_acyclic(parent_edges, "federated parent")
    assert_acyclic(blocker_edges, "federated blocker")
    graph: list[dict[str, Any]] = []
    for identity in sorted(nodes):
        node = dict(nodes[identity])
        node["blocks"] = sorted(reverse_blocks[identity])
        node["children"] = sorted(children[identity])
        graph.append(node)
    ready = [
        node
        for node in graph
        if not node["historical"]
        and node["status"] in {"backlog", "todo"}
        and all(nodes[blocker]["status"] == "done" for blocker in node["blocked_by"])
    ]
    return {
        "contract_version": FEDERATION_CONTRACT_VERSION,
        "projects": sorted(configs),
        "revisions": {payload["project"]: payload["revision"] for payload in exports},
        "tasks": graph,
        "ready": ready,
        "valid": True,
    }


def escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def render_board(root: Path, documents: list[Document], steps: list[Step]) -> str:
    config = load_project_config(root)
    progress = progress_by_item(steps)
    reverse: dict[str, list[str]] = {document.task_id: [] for document in documents}
    for document in documents:
        for blocker in document.values["blocked_by"]:
            local_blocker = local_reference(blocker, config)
            if local_blocker is not None:
                reverse[local_blocker].append(document.task_id)
    lines = [
        "# Task Board",
        "",
        "_Generated by `taskctl`. Do not edit by hand._",
        "",
    ]
    for status in STATUS_ORDER:
        rows = [document for document in documents if document.values["status"] == status]
        rows.sort(
            key=lambda document: (
                PRIORITY_ORDER[document.values["priority"]],
                document.values["area"],
                document.values["title"].casefold(),
            )
        )
        lines.extend(
            (
                f"## {status.title()} ({len(rows)})",
                "",
                "| ID | Priority | Risk | Area | Kind | Issue | Owner | Progress | OpenSpec | Blocked by | Blocks | Updated |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|",
            )
        )
        for document in rows:
            values = document.values
            relative = document.path.relative_to(root / "docs/tasks").as_posix()
            done, total = progress.get(document.task_id, (0, 0))
            change = values["openspec_change"] or "—"
            blockers = ", ".join(values["blocked_by"]) or "—"
            blocks = ", ".join(sorted(reverse[document.task_id])) or "—"
            cells = (
                document.task_id,
                values["priority"],
                values["risk"],
                values["area"],
                values["kind"],
                f"[{values['title']}]({relative})",
                values["owner"],
                f"{done}/{total}",
                change,
                blockers,
                blocks,
                values["updated"],
            )
            lines.append("| " + " | ".join(escape_cell(cell) for cell in cells) + " |")
        lines.append("")
    return "\n".join(lines)


def run_command(command: Sequence[str], *, root: Path, capture: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["OPENSPEC_TELEMETRY"] = "0"
    return subprocess.run(
        command,
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )


def tool_binary(root: Path, name: str) -> Path:
    binary = root / "tools/tasking/node_modules/.bin" / name
    if not binary.exists():
        fail(f"missing pinned {name}; run npm ci --prefix tools/tasking --ignore-scripts")
    return binary


def validate_upstreams(root: Path, documents: list[Document]) -> None:
    config = load_project_config(root)
    mdtask = tool_binary(root, "mdtask")
    for args in (("validate",), ("list", "--all")):
        result = run_command((str(mdtask), *args), root=root)
        output = result.stdout or ""
        if result.returncode != 0 or "warning:" in output.casefold() or "without ids" in output.casefold():
            fail(f"mdtask {' '.join(args)} failed:\n{output.rstrip()}")
    if any(document.values["spec_mode"] == "required" for document in documents):
        openspec = tool_binary(root, "openspec")
        commands = (
            ("schema", "validate", config.openspec_schema, "--json"),
            ("validate", "--all", "--strict", "--no-interactive"),
        )
        for args in commands:
            result = run_command((str(openspec), *args), root=root)
            if result.returncode != 0:
                fail(f"openspec {' '.join(args)} failed:\n{(result.stdout or '').rstrip()}")


def validate_generated_assets(root: Path) -> None:
    lock_path = root / "tools/tasking/generated-assets.lock.json"
    if not lock_path.is_file():
        fail("missing tools/tasking/generated-assets.lock.json")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    if (
        payload.get("schema") != 1
        or payload.get("mdtask") != "0.1.17"
        or payload.get("openspec") != "1.8.0"
    ):
        fail("generated asset lock does not match pinned tool versions")
    files = payload.get("files")
    if not isinstance(files, dict) or set(files) != GENERATED_ASSET_PATHS:
        missing = (
            sorted(GENERATED_ASSET_PATHS - set(files or {}))
            if isinstance(files, dict)
            else sorted(GENERATED_ASSET_PATHS)
        )
        extra = (
            sorted(set(files or {}) - GENERATED_ASSET_PATHS)
            if isinstance(files, dict)
            else []
        )
        fail(f"generated asset lock has wrong canonical set: missing={missing}, extra={extra}")
    for relative, expected in files.items():
        path = root / relative
        if not path.is_file():
            fail(f"generated asset missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            fail(f"generated asset drift: {relative}")
    for alias_root, target_root in COMPATIBILITY_SKILL_ROOTS.items():
        for name in ALIAS_SKILL_NAMES:
            alias = root / alias_root / name
            expected = f"{target_root}/{name}"
            if not alias.is_symlink():
                fail(
                    "generated skill alias missing or not a symlink: "
                    f"{alias.relative_to(root)}"
                )
            actual = os.readlink(alias)
            if actual != expected:
                fail(
                    f"generated skill alias retargeted: {alias.relative_to(root)} "
                    f"expected {expected!r}, got {actual!r}"
                )
            if not alias.exists() or not (alias / "SKILL.md").is_file():
                fail(f"generated skill alias target missing: {alias.relative_to(root)}")


def historical_task_snapshots(
    root: Path,
    ref: str,
    scratch: Path,
) -> dict[str, HistoricalTaskSnapshot]:
    tree = run_command(
        ("git", "ls-tree", "-r", "--name-only", ref, "--", "docs/tasks/issues"),
        root=root,
    )
    if tree.returncode != 0:
        fail(f"cannot inspect task records at {ref}: {(tree.stdout or '').rstrip()}")
    snapshots: dict[str, HistoricalTaskSnapshot] = {}
    for index, relative in enumerate(
        item for item in (tree.stdout or "").splitlines() if item.endswith(".md")
    ):
        shown = run_command(("git", "show", f"{ref}:{relative}"), root=root)
        if shown.returncode != 0:
            fail(f"cannot read task record {relative} at {ref}")
        issue = scratch / f"issue-{hashlib.sha256(ref.encode()).hexdigest()[:12]}-{index}.md"
        issue.write_text(shown.stdout or "", encoding="utf-8")
        document = read_document(issue)
        task_id = document.values.get("id")
        if not isinstance(task_id, str) or ID_RE.fullmatch(task_id) is None:
            fail(f"{relative} at {ref}: missing or invalid task ID")
        if task_id in snapshots:
            fail(f"duplicate historical task ID {task_id} at {ref}")
        snapshots[task_id] = HistoricalTaskSnapshot(
            relative=relative,
            document=document,
            text=shown.stdout or "",
        )
    return snapshots


def historical_project_config(root: Path, ref: str, scratch: Path) -> ProjectConfig:
    shown = run_command(("git", "show", f"{ref}:{PROJECT_CONFIG_PATH}"), root=root)
    if shown.returncode != 0:
        fail(f"cannot read historical project config at {ref}")
    path = scratch / f"project-{hashlib.sha256(ref.encode()).hexdigest()[:12]}.json"
    path.write_text(shown.stdout or "", encoding="utf-8")
    try:
        raw = json.loads(shown.stdout or "")
    except json.JSONDecodeError as error:
        fail(f"{PROJECT_CONFIG_PATH} at {ref}: invalid JSON: {error}")
    return parse_project_config(raw, path)


def validate_deleted_history(root: Path, base: str) -> None:
    ancestry = run_command(
        ("git", "merge-base", "--is-ancestor", base, "HEAD"), root=root
    )
    if ancestry.returncode != 0:
        fail(f"cannot validate task history: {base} is not an ancestor of HEAD")
    history = run_command(
        (
            "git",
            "rev-list",
            "--first-parent",
            "--reverse",
            "--ancestry-path",
            f"{base}..HEAD",
        ),
        root=root,
    )
    if history.returncode != 0:
        fail(f"cannot inspect task history: {(history.stdout or '').rstrip()}")
    revisions = [base, *filter(None, (history.stdout or "").splitlines())]

    with tempfile.TemporaryDirectory(prefix="ripdpi-task-history-") as directory:
        scratch = Path(directory)
        by_revision = {
            revision: historical_task_snapshots(root, revision, scratch)
            for revision in revisions
        }
        head_ids = set(by_revision[revisions[-1]])
        candidate_ids: set[str] = set()
        for snapshots in by_revision.values():
            candidate_ids.update(snapshots)
        config_cache: dict[str, ProjectConfig] = {}

        def config_at(ref: str) -> ProjectConfig:
            if ref not in config_cache:
                config_cache[ref] = historical_project_config(root, ref, scratch)
            return config_cache[ref]

        for task_id in sorted(candidate_ids - head_ids):
            timeline = [
                (revision, by_revision[revision].get(task_id)) for revision in revisions
            ]
            deletion_indexes = [
                index
                for index in range(1, len(timeline))
                if timeline[index - 1][1] is not None and timeline[index][1] is None
            ]
            if not deletion_indexes:
                fail(f"{task_id}: cannot resolve disappearance commit")
            deletion_index = deletion_indexes[-1]
            deletion_sha = timeline[deletion_index][0]
            final_snapshot = timeline[deletion_index - 1][1]
            assert final_snapshot is not None
            relative = final_snapshot.relative
            final_document = final_snapshot.document
            final_ref = timeline[deletion_index - 1][0]
            validate_issue_shape(final_document, config_at(final_ref))
            outcome = final_document.values.get("status")
            if outcome not in {"done", "dropped"}:
                fail(
                    f"{relative}: deleted without a preceding committed terminal state"
                )
            for field in ("closed_at", "closed_reason", "evidence_summary"):
                if not final_document.values.get(field):
                    fail(f"{relative}: terminal state before deletion lacks {field}")

            terminal_transition_ref: str | None = None
            terminal_transition_snapshot: HistoricalTaskSnapshot | None = None
            prior_status: str | None = None
            last_absent = max(
                (
                    index
                    for index, (_, snapshot) in enumerate(timeline[:deletion_index])
                    if snapshot is None
                ),
                default=-1,
            )
            incarnation = timeline[last_absent + 1 : deletion_index]
            if (
                last_absent == -1
                and incarnation
                and incarnation[0][1] is not None
                and incarnation[0][1].document.values.get("status")
                in {"done", "dropped"}
            ):
                terminal_transition_ref, terminal_transition_snapshot = incarnation[0]
            else:
                for commit, snapshot in incarnation:
                    assert snapshot is not None
                    status = snapshot.document.values.get("status")
                    if status in {"done", "dropped"}:
                        terminal_transition_ref = commit
                        terminal_transition_snapshot = snapshot
                        break
                    prior_status = status
            if terminal_transition_ref is None or terminal_transition_snapshot is None:
                fail(f"{relative}: terminal transition commit is missing")
            validate_issue_shape(
                terminal_transition_snapshot.document,
                config_at(terminal_transition_ref),
            )
            terminal_index = next(
                index
                for index, (revision, _) in enumerate(incarnation)
                if revision == terminal_transition_ref
            )
            for _, snapshot in incarnation[terminal_index:]:
                assert snapshot is not None
                if snapshot.document.values.get("status") != outcome:
                    fail(f"{relative}: task transitioned out of terminal state")
            if (
                outcome == "done"
                and prior_status != "review"
                and terminal_transition_ref != base
            ):
                fail(
                    f"{relative}: invalid terminal transition {prior_status or 'missing'} -> done"
                )
            if (
                outcome == "dropped"
                and terminal_transition_ref != base
                and (
                    prior_status not in STATUSES
                    or not transition_allowed(prior_status, "dropped")
                )
            ):
                fail(
                    f"{relative}: invalid terminal transition {prior_status or 'missing'} -> dropped"
                )

            if (
                outcome == "done"
                and final_document.values.get("spec_mode") == "required"
            ):
                prior_evidence: dict[str, str] = {}
                for revision, snapshot in incarnation:
                    assert snapshot is not None
                    evidence = historical_verification_values(
                        root,
                        revision,
                        snapshot.document,
                        config_at(revision),
                        scratch,
                    )
                    for category in config_at(revision).evidence_categories:
                        previous = prior_evidence.get(category)
                        current = evidence[category]
                        if (
                            previous in {"required", "blocked"}
                            and current == "not_applicable"
                        ):
                            validate_historical_shared_transfer(
                                root,
                                task_id=task_id,
                                category=category,
                                previous_state=previous,
                                source_ref=revision,
                                source_snapshot=snapshot,
                                snapshots_at_source=by_revision[revision],
                                config=config_at(revision),
                                scratch=scratch,
                            )
                        prior_evidence[category] = current

            terminal_ref = final_ref
            terminal_document = final_document
            terminal_text = final_snapshot.text
            if terminal_document.values.get("status") != outcome:
                fail(f"{relative}: terminal transition does not match deleted outcome")
            validate_terminal_snapshot(
                root,
                config_at(final_ref),
                relative=relative,
                terminal_ref=terminal_ref,
                deletion_ref=deletion_sha,
                document=terminal_document,
                issue_text=terminal_text,
            )

            if terminal_document.values.get("spec_mode") == "required":
                change = terminal_document.values.get("openspec_change")
                tree = run_command(
                    (
                        "git",
                        "ls-tree",
                        "-r",
                        "--name-only",
                        terminal_ref,
                        "--",
                        "openspec/changes",
                    ),
                    root=root,
                )
                execution_candidates = [
                    item
                    for item in (tree.stdout or "").splitlines()
                    if item == f"openspec/changes/{change}/tasks.md"
                    or (item.endswith(f"-{change}/tasks.md") and "/archive/" in item)
                ]
                if len(execution_candidates) != 1:
                    fail(
                        f"{relative}: terminal commit has no unique OpenSpec execution snapshot"
                    )
                execution_path = execution_candidates[0]
                receipt_root = execution_path.rsplit("/", 1)[0]
                close_receipt_path = f"{receipt_root}/.taskctl-close.json"
            else:
                execution_path = f"docs/tasks/work/{terminal_document.task_id}.md"
                receipt_root = f"docs/tasks/work/{terminal_document.task_id}"
                close_receipt_path = f"{receipt_root}.close.json"

            execution_result = run_command(
                ("git", "show", f"{terminal_ref}:{execution_path}"), root=root
            )
            if execution_result.returncode != 0:
                fail(f"{relative}: terminal execution snapshot is missing")
            execution_file = scratch / "execution.md"
            execution_file.write_text(execution_result.stdout or "", encoding="utf-8")
            terminal_steps = read_steps(execution_file)
            if outcome == "done" and not terminal_steps:
                fail(f"{relative}: completed task has no execution steps")
            if any(not step.done for step in terminal_steps):
                fail(f"{relative}: terminal commit contains open execution steps")

            close_result = run_command(
                ("git", "show", f"{terminal_ref}:{close_receipt_path}"), root=root
            )
            if close_result.returncode != 0:
                fail(f"{relative}: close receipt is missing from terminal commit")
            close_receipt = json.loads(close_result.stdout or "{}")
            if (
                close_receipt.get("schema") != 1
                or close_receipt.get("task_id") != terminal_document.task_id
                or close_receipt.get("outcome") != outcome
                or close_receipt.get("issue_sha256")
                != hashlib.sha256(terminal_text.encode()).hexdigest()
                or close_receipt.get("execution_sha256")
                != hashlib.sha256((execution_result.stdout or "").encode()).hexdigest()
            ):
                fail(f"{relative}: close receipt does not match the terminal snapshot")
            if outcome == "dropped":
                drop_receipt_path = (
                    f"{receipt_root}/.taskctl-drop.json"
                    if terminal_document.values.get("spec_mode") == "required"
                    else f"{receipt_root}.drop.json"
                )
                drop_result = run_command(
                    ("git", "show", f"{terminal_ref}:{drop_receipt_path}"), root=root
                )
                if drop_result.returncode != 0:
                    fail(f"{relative}: drop receipt is missing from terminal commit")
                drop_receipt = json.loads(drop_result.stdout or "{}")
                if (
                    drop_receipt.get("task_id") != terminal_document.task_id
                    or drop_receipt.get("outcome") != "dropped"
                ):
                    fail(f"{relative}: invalid drop receipt in terminal commit")

            if terminal_document.values.get("spec_mode") == "required":
                change = terminal_document.values.get("openspec_change")
                tree = run_command(
                    (
                        "git",
                        "ls-tree",
                        "-r",
                        "--name-only",
                        deletion_sha,
                        "--",
                        "openspec/changes/archive",
                    ),
                    root=root,
                )
                archive_roots = {
                    item.rsplit("/", 1)[0]
                    for item in (tree.stdout or "").splitlines()
                    if item.endswith(f"-{change}/.taskctl-archive.json")
                }
                if len(archive_roots) != 1:
                    fail(
                        f"{relative}: terminal OpenSpec change was not archived before deletion"
                    )
                archive_root = next(iter(archive_roots))
                archived_close_result = run_command(
                    (
                        "git",
                        "show",
                        f"{deletion_sha}:{archive_root}/.taskctl-close.json",
                    ),
                    root=root,
                )
                if (
                    archived_close_result.returncode != 0
                    or json.loads(archived_close_result.stdout or "{}") != close_receipt
                ):
                    fail(
                        f"{relative}: archived close receipt differs from terminal commit"
                    )
                archive_result = run_command(
                    (
                        "git",
                        "show",
                        f"{deletion_sha}:{archive_root}/.taskctl-archive.json",
                    ),
                    root=root,
                )
                if archive_result.returncode != 0:
                    fail(
                        f"{relative}: archived lifecycle receipt missing: .taskctl-archive.json"
                    )
                archive_receipt = json.loads(archive_result.stdout or "{}")
                expected_archive_outcome = (
                    "dropped" if outcome == "dropped" else "review"
                )
                if (
                    archive_receipt.get("schema") != 1
                    or archive_receipt.get("task_id") != terminal_document.task_id
                    or archive_receipt.get("change") != change
                    or archive_receipt.get("outcome") != expected_archive_outcome
                    or not SHA_RE.fullmatch(str(archive_receipt.get("commit_sha", "")))
                ):
                    fail(f"{relative}: invalid OpenSpec archive receipt")
                verification_result = run_command(
                    ("git", "show", f"{deletion_sha}:{archive_root}/verification.md"),
                    root=root,
                )
                if verification_result.returncode != 0:
                    fail(f"{relative}: archived verification record is missing")
                verification_file = scratch / "archived-verification.md"
                verification_file.write_text(
                    verification_result.stdout or "", encoding="utf-8"
                )
                verification = read_document(verification_file)
                if (
                    verification.values.get("task_id") != terminal_document.task_id
                    or verification.values.get("change") != change
                    or verification.values.get("commit_sha")
                    != archive_receipt.get("commit_sha")
                ):
                    fail(
                        f"{relative}: archive receipt does not match verification record"
                    )
                if outcome == "dropped":
                    archived_drop_result = run_command(
                        (
                            "git",
                            "show",
                            f"{deletion_sha}:{archive_root}/.taskctl-drop.json",
                        ),
                        root=root,
                    )
                    if (
                        archived_drop_result.returncode != 0
                        or json.loads(archived_drop_result.stdout or "{}")
                        != drop_receipt
                    ):
                        fail(
                            f"{relative}: archived drop receipt differs from terminal commit"
                        )


def validate_repository(root: Path, *, base: str | None, upstreams: bool = True) -> tuple[list[Document], list[Step]]:
    documents, steps = load_state(root)
    expected = render_board(root, documents, steps)
    board = root / "docs/tasks/board.md"
    if not board.is_file() or board.read_text(encoding="utf-8") != expected:
        fail("docs/tasks/board.md is stale; run ./taskctl generate-board")
    validate_generated_assets(root)
    if upstreams:
        validate_upstreams(root, documents)
    if base:
        validate_deleted_history(root, base)
    return documents, steps


def find_document(documents: Sequence[Document], query: str) -> Document:
    exact = [document for document in documents if document.task_id == query]
    if exact:
        return exact[0]
    suffix = [document for document in documents if document.task_id.endswith(f"-{query}")]
    if len(suffix) == 1:
        return suffix[0]
    slug = [document for document in documents if document.path.stem == query]
    if len(slug) == 1:
        return slug[0]
    fail(f"task query {query!r} is missing or ambiguous")


def write_document(document: Document, values: dict[str, Any]) -> None:
    document.path.write_text(render_document(values, document.body), encoding="utf-8")


def transition_allowed(current: str, target: str) -> bool:
    return target in {
        "backlog": {"todo", "dropped"},
        "todo": {"backlog", "doing", "blocked", "dropped"},
        "doing": {"review", "blocked", "todo", "dropped"},
        "review": {"doing", "blocked", "done", "dropped"},
        "blocked": {"todo", "doing", "dropped"},
        "done": set(),
        "dropped": set(),
    }[current]


def command_generate_board(args: argparse.Namespace) -> int:
    documents, steps = load_state(args.root)
    board = args.root / "docs/tasks/board.md"
    board.write_text(render_board(args.root, documents, steps), encoding="utf-8")
    print(f"Generated {board.relative_to(args.root)} from {len(documents)} tasks")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    documents, steps = validate_repository(args.root, base=args.base, upstreams=not args.skip_upstreams)
    payload = {"schema": 1, "tasks": len(documents), "steps": len(steps), "valid": True}
    print(json.dumps(payload, sort_keys=True) if args.json else f"Task contracts valid ({len(documents)} tasks, {len(steps)} steps)")
    return 0


def command_list(args: argparse.Namespace) -> int:
    documents, steps = load_state(args.root)
    progress = progress_by_item(steps)
    selected = [
        document
        for document in documents
        if (not args.status or document.values["status"] in args.status)
        and (not args.area or document.values["area"] in args.area)
        and (not args.kind or document.values["kind"] in args.kind)
    ]
    rows = [
        {
            **document.values,
            "path": str(document.path.relative_to(args.root)),
            "progress": {
                "done": progress.get(document.task_id, (0, 0))[0],
                "total": progress.get(document.task_id, (0, 0))[1],
            },
        }
        for document in selected
    ]
    if args.json:
        print(json.dumps({"schema": 1, "tasks": rows}, ensure_ascii=False, sort_keys=True))
    else:
        for row in rows:
            print(f"{row['id']}\t{row['status']}\t{row['priority']}\t{row['title']}\t{row['progress']['done']}/{row['progress']['total']}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    documents, steps = load_state(args.root)
    document = find_document(documents, args.query)
    item_steps = [step for step in steps if step.item_id == document.task_id]
    if args.json:
        print(
            json.dumps(
                {
                    "schema": 1,
                    "task": document.values,
                    "path": str(document.path.relative_to(args.root)),
                    "execution": str(expected_execution_path(args.root, document).relative_to(args.root)),
                    "steps": [step.__dict__ | {"path": str(step.path.relative_to(args.root))} for step in item_steps],
                },
                ensure_ascii=False,
                default=str,
                sort_keys=True,
            )
        )
    else:
        print(document.path.read_text(encoding="utf-8"), end="")
        print(f"\nExecution: {expected_execution_path(args.root, document).relative_to(args.root)}")
    return 0


def command_ready(args: argparse.Namespace) -> int:
    config = load_project_config(args.root)
    documents, steps = load_state(args.root, config)
    by_id = {document.task_id: document for document in documents}
    unresolved: dict[str, list[str]] = {}
    ready = [
        document
        for document in documents
        if document.values["status"] in {"backlog", "todo"}
        and all(
            (local := local_reference(blocker, config)) is not None
            and by_id[local].values["status"] == "done"
            for blocker in document.values["blocked_by"]
        )
    ]
    for document in documents:
        external = [
            blocker for blocker in document.values["blocked_by"]
            if local_reference(blocker, config) is None
        ]
        if external:
            unresolved[document.task_id] = external
    if args.json:
        print(json.dumps({"schema": 1, "ready": [document.values for document in ready], "unresolved_external": unresolved}, ensure_ascii=False, sort_keys=True))
    else:
        for document in ready:
            print(f"{document.task_id}\t{document.values['priority']}\t{document.values['title']}")
        for task_id, blockers in sorted(unresolved.items()):
            print(f"UNRESOLVED_EXTERNAL\t{task_id}\t{','.join(blockers)}")
    return 0


def command_graph(args: argparse.Namespace) -> int:
    config = load_project_config(args.root)
    history_resolver = TerminalHistoryResolver(args.root, config)
    documents, _ = _load_state(
        args.root,
        config,
        history_resolver=history_resolver,
    )
    reverse: dict[str, list[str]] = {document.task_id: [] for document in documents}
    for document in documents:
        for blocker in document.values["blocked_by"]:
            local_blocker = local_reference(blocker, config)
            if local_blocker is not None:
                reverse[local_blocker].append(document.task_id)
    graph: list[dict[str, Any]] = [
        {
            "id": document.task_id,
            "status": document.values["status"],
            "historical": False,
            "parent": document.values["parent"],
            "blocked_by": document.values["blocked_by"],
            "related_tasks": document.values.get("related_tasks", []),
            "blocks": sorted(reverse[document.task_id]),
        }
        for document in documents
    ]
    active_ids = {document.task_id for document in documents}
    historical_ids = sorted(
        {
            local
            for document in documents
            for related in document.values.get("related_tasks", [])
            if (local := local_reference(related, config)) is not None
            and local not in active_ids
        }
    )

    def localize(reference: str) -> str:
        prefix = f"{config.project}#"
        return reference[len(prefix) :] if reference.startswith(prefix) else reference

    for task_id in historical_ids:
        historical = history_resolver.resolve(
            task_id,
            allow_uncommitted_purge=True,
        )
        if historical is None or historical["status"] != "done":
            fail(f"missing or incomplete historical related task {task_id}")
        graph.append(
            {
                "id": task_id,
                "status": historical["status"],
                "historical": True,
                "parent": (
                    localize(historical["parent"]) if historical["parent"] else None
                ),
                "blocked_by": [localize(value) for value in historical["blocked_by"]],
                "related_tasks": [
                    localize(value) for value in historical["related_tasks"]
                ],
                "blocks": [],
                "terminal_revision": historical["terminal_revision"],
                "deletion_revision": historical["deletion_revision"],
            }
        )
    graph.sort(key=lambda node: node["id"])
    if args.json:
        print(json.dumps({"schema": 1, "graph": graph}, sort_keys=True))
    else:
        for node in graph:
            print(
                f"{node['id']}: blocked_by={','.join(node['blocked_by']) or '-'} blocks={','.join(node['blocks']) or '-'}"
            )
    return 0


def command_export(args: argparse.Namespace) -> int:
    print(json.dumps(export_payload(args.root), ensure_ascii=False, sort_keys=True))
    return 0


def command_federation(args: argparse.Namespace) -> int:
    payload = federation_payload(args.root, args.peer_root.resolve())
    if args.federation_command == "validate":
        selected: Any = {
            "contract_version": payload["contract_version"],
            "projects": payload["projects"],
            "revisions": payload["revisions"],
            "tasks": len(payload["tasks"]),
            "valid": True,
        }
    elif args.federation_command == "ready":
        selected = {
            "contract_version": payload["contract_version"],
            "projects": payload["projects"],
            "ready": payload["ready"],
        }
    elif args.federation_command == "graph":
        selected = {
            "contract_version": payload["contract_version"],
            "projects": payload["projects"],
            "tasks": payload["tasks"],
        }
    else:
        selected = {
            "contract_version": payload["contract_version"],
            "projects": payload["projects"],
            "tasks": [
                {
                    key: node[key]
                    for key in ("id", "status", "kind", "path", "progress", "historical")
                }
                for node in payload["tasks"]
            ],
        }
    if args.json:
        print(json.dumps(selected, ensure_ascii=False, sort_keys=True))
    elif args.federation_command == "validate":
        print(f"Federation contracts valid ({selected['tasks']} tasks)")
    else:
        for node in selected["ready" if args.federation_command == "ready" else "tasks"]:
            print(f"{node['id']}\t{node['status']}\t{node['progress']['done']}/{node['progress']['total']}")
    return 0


def command_new(args: argparse.Namespace) -> int:
    config = load_project_config(args.root)
    documents, steps = load_state(args.root, config)
    used = {
        ID_RE.fullmatch(document.values["id"]).group(2)  # type: ignore[union-attr]
        for document in documents
        if ID_RE.fullmatch(str(document.values.get("id", "")))
    }
    used.update(
        ID_RE.fullmatch(step.task_id).group(2)  # type: ignore[union-attr]
        for step in steps
    )
    if args.spec_mode == "not-required" and not args.spec_reason:
        fail("spec-not-required task requires --spec-reason")
    if args.spec_mode == "not-required" and args.kind in {"feature", "epic"}:
        fail(f"{args.kind} cannot waive OpenSpec")
    if args.spec_mode == "not-required" and args.risk == "high":
        fail("high-risk task cannot waive OpenSpec")
    if args.area not in config.areas:
        fail(f"unknown task area {args.area!r}")
    if args.parent is not None:
        reference_parts(args.parent, config)
    task_id = allocate_id(args.root, args.area, used, config)
    slug = args.slug or slugify(args.title)
    path = args.root / "docs/tasks/issues" / f"{slug}.md"
    if path.exists():
        fail(f"task file already exists: {path.relative_to(args.root)}")
    if args.spec_mode == "required":
        change = args.openspec_change or f"{task_id.casefold()}-{slug}"
        spec_reason = None
    else:
        change = None
        spec_reason = args.spec_reason
    today = date.today().isoformat()
    values = {
        "id": task_id,
        "title": args.title,
        "kind": args.kind,
        "status": "backlog",
        "area": args.area,
        "priority": args.priority,
        "risk": args.risk,
        "owner": args.owner,
        "parent": args.parent,
        "blocked_by": [],
        "related_tasks": [],
        "spec_mode": args.spec_mode,
        "openspec_change": change,
        "created": today,
        "updated": today,
    }
    if spec_reason is not None:
        values["spec_reason"] = spec_reason
    document = Document(path=path, values=values, body="## Goal\n\nDescribe the observable outcome.\n\n## Acceptance criteria\n\nDefine verifiable completion criteria.\n")
    path.write_text(render_document(values, document.body), encoding="utf-8")
    if args.spec_mode == "not-required":
        work = args.root / "docs/tasks/work" / f"{task_id}.md"
        work.parent.mkdir(parents=True, exist_ok=True)
        step_id = allocate_id(
            args.root,
            args.area,
            used | {ID_RE.fullmatch(task_id).group(2)},  # type: ignore[union-attr]
            config,
        )
        work.write_text(
            f"# {task_id}: {args.title}\n\n## Objective\n\n{args.title}\n\n## Ownership\n\nDeclare owned paths before implementation.\n\n## Execution\n\n- [ ] {step_id} Define implementation and verification #{args.kind}{MDTASK_PRIORITY_TOKENS[args.priority]} @item:{task_id}\n",
            encoding="utf-8",
        )
    else:
        openspec = tool_binary(args.root, "openspec")
        result = run_command(
            (
                str(openspec),
                "new",
                "change",
                change,
                "--schema",
                config.openspec_schema,
                "--goal",
                f"{task_id} {args.title}",
                "--json",
            ),
            root=args.root,
        )
        if result.returncode != 0:
            path.unlink(missing_ok=True)
            fail(f"OpenSpec scaffold failed:\n{(result.stdout or '').rstrip()}")
    print(f"Created {task_id} at {path.relative_to(args.root)}")
    return 0


def command_start(args: argparse.Namespace) -> int:
    documents, _ = load_state(args.root)
    document = find_document(documents, args.query)
    current = document.values["status"]
    if current not in {"backlog", "todo", "blocked"}:
        fail(f"cannot start task from {current}")
    values = dict(document.values)
    values["status"] = "doing"
    values["owner"] = args.owner or values["owner"]
    values["updated"] = date.today().isoformat()
    write_document(document, values)
    print(f"Started {document.task_id}")
    return 0


def command_transition(args: argparse.Namespace) -> int:
    documents, _ = load_state(args.root)
    document = find_document(documents, args.query)
    current = document.values["status"]
    if args.status in {"done", "dropped"}:
        fail("use taskctl close prepare for terminal transitions")
    if not transition_allowed(current, args.status):
        fail(f"invalid transition {current} -> {args.status}")
    values = dict(document.values)
    values["status"] = args.status
    values["updated"] = date.today().isoformat()
    if args.detail is not None:
        values["status_detail"] = args.detail
    write_document(document, values)
    print(f"Transitioned {document.task_id}: {current} -> {args.status}")
    return 0


@contextmanager
def steps_write_lock(root: Path):
    # Shared by add/done/set, including callers in linked worktrees. Never unlink
    # a lock inode: another process may already be waiting on it.
    lock = (git_common_dir(root) or root) / "taskctl-steps.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def require_owned_execution_path(root: Path, path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            fail(f"execution authoring refuses symlink: {candidate}")
    if path.exists() and not path.is_file():
        fail(f"execution authoring requires a regular file: {path}")


def validate_step_planning(root: Path, document: Document, config: ProjectConfig) -> None:
    change = root / "openspec/changes" / document.values["openspec_change"]
    for path in (change / "proposal.md", change / "design.md", change / ".openspec.yaml"):
        require_owned_execution_path(root, path)
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            fail(f"step authoring requires nonempty {path.relative_to(root)}")
    require_owned_execution_path(root, change / "verification.md")
    if f"Task ID: `{document.task_id}`" not in (change / "proposal.md").read_text(encoding="utf-8"):
        fail("step authoring proposal lacks exact portfolio backlink")
    specs = sorted((change / "specs").glob("**/*.md"))
    if not specs:
        fail("step authoring requires delta specs")
    for path in specs:
        require_owned_execution_path(root, path)
    requirements = [requirement for path in specs for requirement in re.findall(
        r"(?m)^### Requirement: (REQ-[A-Z0-9-]+)(?:\s|$)", path.read_text(encoding="utf-8"),
    )]
    if not requirements or len(requirements) != len(set(requirements)):
        fail("step authoring requires unique stable REQ-* requirements")
    openspec = str(tool_binary(root, "openspec"))
    status = run_command((openspec, "status", "--change", change.name, "--json"), root=root)
    if status.returncode != 0:
        fail(f"OpenSpec planning status failed:\n{status.stdout}")
    planning = json.loads(status.stdout)
    if planning.get("schemaName") != config.openspec_schema:
        fail("step authoring requires the repository OpenSpec schema")
    completed = {item["id"] for item in planning["artifacts"] if item["status"] == "done"}
    if not {"proposal", "specs", "design"} <= completed:
        fail("step authoring requires complete proposal, specs and design")
    result = run_command((openspec, "validate", change.name, "--strict", "--json"), root=root)
    if result.returncode != 0:
        fail(f"OpenSpec planning validation failed:\n{result.stdout}")


def command_steps_add(args: argparse.Namespace) -> int:
    parser = argparse.ArgumentParser(prog="taskctl steps <TASK-ID> add")
    parser.add_argument("title")
    parser.add_argument("--kind", choices=sorted(KINDS))
    parser.add_argument("--priority", choices=PRIORITIES)
    addition = parser.parse_args(args.mdtask_args[1:])
    title = addition.title
    if (not title.strip() or title != title.strip() or len(title.splitlines()) != 1
            or any(ord(char) < 32 or char == "\x7f" for char in title)
            or re.search(r"(?:^|\s)[@#!]|\b[A-Z][A-Z0-9]*-\d{16}\b", title)):
        fail("step title must be plain single-line text without IDs or mdtask metadata")
    config = load_project_config(args.root)
    document = find_document([read_document(path) for path in issue_paths(args.root)], args.query)
    validate_issue_shape(document, config)
    path = expected_execution_path(args.root, document)
    require_owned_execution_path(args.root, path)
    if document.values["status"] in {"done", "dropped"} or path.parent.parent.name == "archive":
        fail("cannot add steps to terminal or archived work")
    authoring = document.values["spec_mode"] == "required"
    if authoring:
        validate_step_planning(args.root, document, config)
    documents, steps = _load_state(
        args.root, config, authoring_task_id=document.task_id if authoring else None,
    )
    used = {item.task_id.split("-", 1)[1] for item in (*documents, *steps)}
    # Dropped execution IDs remain reserved even when imported from another clone.
    for item in documents:
        if item.values["status"] == "dropped":
            receipt = read_lifecycle_receipt(args.root, item, expected_execution_path(args.root, item), "drop")
            used.update(step_id.split("-", 1)[1] for step_id in receipt["dropped_step_ids"])
    step_id = allocate_id(args.root, document.values["area"], used, config)
    kind = addition.kind or document.values["kind"]
    priority = addition.priority or document.values["priority"]
    record = f"- [ ] {step_id} {title} #{kind}{MDTASK_PRIORITY_TOKENS[priority]} @item:{document.task_id}\n"
    if path.exists():
        previous = path.read_bytes()
        content = ("" if not previous or previous.endswith(b"\n") else "\n") + record
        flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW
    else:
        content = f"# {document.task_id}\n\n## Execution\n\n{record}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags, 0o600), "a", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    print(f"Added {step_id} to {path.relative_to(args.root)}")
    if authoring:
        print("Planning validation remains pending: complete verification mappings.")
    print("Run taskctl generate-board, then taskctl validate.")
    return 0


def command_steps(args: argparse.Namespace) -> int:
    allowed = {"add", "list", "view", "done", "set", "validate"}
    if not args.mdtask_args or args.mdtask_args[0] not in allowed:
        fail(f"steps exposes only: {', '.join(sorted(allowed))}")
    action = args.mdtask_args[0]
    with steps_write_lock(args.root) if action in {"add", "done", "set"} else nullcontext():
        if action == "add":
            return command_steps_add(args)
        documents, _ = load_state(args.root)
        document = find_document(documents, args.query)
        path = expected_execution_path(args.root, document)
        mdtask = tool_binary(args.root, "mdtask")
        result = run_command((str(mdtask), *args.mdtask_args, "--path", str(path)), root=args.root, capture=False)
        return result.returncode


def verify_task(root: Path, document: Document, steps: list[Step], *, archive_ready: bool) -> None:
    config = load_project_config(root)
    item_steps = [step for step in steps if step.item_id == document.task_id]
    open_steps = [step.task_id for step in item_steps if not step.done]
    if open_steps:
        fail(f"{document.task_id}: open execution steps: {', '.join(open_steps)}")
    if document.values["spec_mode"] == "required":
        change = document.values["openspec_change"]
        execution = expected_execution_path(root, document)
        if execution.parent.parent.name != "archive":
            openspec = tool_binary(root, "openspec")
            result = run_command((str(openspec), "validate", change, "--strict", "--json"), root=root)
            if result.returncode != 0:
                fail(f"OpenSpec change {change} is invalid:\n{(result.stdout or '').rstrip()}")
        evidence = evidence_values(execution.parent / "verification.md", config)
        if archive_ready:
            if any(evidence[category] in {"required", "blocked"} for category in config.evidence_categories):
                fail(f"{change}: verification evidence is incomplete")
            if not isinstance(evidence["commit_sha"], str) or not SHA_RE.fullmatch(evidence["commit_sha"]):
                fail(f"{change}: verification commit_sha must be an exact 40-character SHA")


def command_verify(args: argparse.Namespace) -> int:
    documents, steps = load_state(args.root)
    document = find_document(documents, args.query)
    verify_task(args.root, document, steps, archive_ready=args.archive_ready)
    print(f"Verified {document.task_id}")
    return 0


def command_openspec_archive(args: argparse.Namespace) -> int:
    documents, steps = load_state(args.root)
    document = next(
        (item for item in documents if item.values["openspec_change"] == args.change),
        None,
    )
    if document is None:
        fail(f"OpenSpec change {args.change!r} has no portfolio task")
    if document.values["status"] not in {"review", "dropped"}:
        fail(f"{document.task_id}: archive requires review or a prepared dropped state")
    archive_args = ["archive", args.change, "--yes", "--json"]
    if document.values["status"] == "dropped":
        relative = document.path.relative_to(args.root).as_posix()
        committed = run_command(("git", "show", f"HEAD:{relative}"), root=args.root)
        if committed.returncode != 0:
            fail("dropped task record must be committed before archival")
        with tempfile.TemporaryDirectory(prefix="ripdpi-task-archive-") as directory:
            snapshot = Path(directory) / "issue.md"
            snapshot.write_text(committed.stdout or "", encoding="utf-8")
            if read_document(snapshot).values.get("status") != "dropped":
                fail("dropped terminal state must be committed before archival")
        execution = expected_execution_path(args.root, document)
        for kind in ("drop", "close"):
            receipt = lifecycle_receipt_path(args.root, document, execution, kind)
            receipt_relative = receipt.relative_to(args.root).as_posix()
            present = run_command(("git", "cat-file", "-e", f"HEAD:{receipt_relative}"), root=args.root)
            if present.returncode != 0:
                fail(f"commit the taskctl {kind} receipt before archival")
        verification_path = execution.parent / "verification.md"
        verification = read_document(verification_path)
        values = dict(verification.values)
        values["commit_sha"] = run_command(("git", "rev-parse", "HEAD"), root=args.root).stdout.strip()
        verification_path.write_text(
            render_document(values, verification.body, order=tuple(values)),
            encoding="utf-8",
        )
        archive_args.append("--skip-specs")
    verify_task(args.root, document, steps, archive_ready=True)
    openspec = tool_binary(args.root, "openspec")
    result = run_command((str(openspec), *archive_args), root=args.root, capture=False)
    if result.returncode != 0:
        return result.returncode
    archives = sorted((args.root / "openspec/changes/archive").glob(f"*-{args.change}"))
    if len(archives) != 1:
        fail(f"archive completed but exactly one archive for {args.change} was not found")
    evidence = evidence_values(archives[0] / "verification.md", load_project_config(args.root))
    receipt = {
        "schema": 1,
        "task_id": document.task_id,
        "change": args.change,
        "outcome": document.values["status"],
        "commit_sha": evidence["commit_sha"],
        "archived_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    (archives[0] / ".taskctl-archive.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


def command_openspec_cli(args: argparse.Namespace) -> int:
    if not args.openspec_args or args.openspec_args[0] not in SAFE_OPENSPEC_COMMANDS:
        fail(
            "OpenSpec passthrough exposes only project-scoped planning commands; "
            "use taskctl openspec archive for archival"
        )
    openspec = tool_binary(args.root, "openspec")
    result = run_command(
        (str(openspec), *args.openspec_args), root=args.root, capture=False
    )
    return result.returncode


def write_lifecycle_receipt(
    root: Path,
    document: Document,
    execution: Path,
    kind: str,
    payload: dict[str, Any],
) -> None:
    path = lifecycle_receipt_path(root, document, execution, kind)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_dropped_execution(
    root: Path,
    document: Document,
    steps: Sequence[Step],
    reason: str,
) -> Path:
    config = load_project_config(root)
    execution = expected_execution_path(root, document)
    dropped_step_ids = {step.task_id for step in steps if not step.done}
    rewritten: list[str] = []
    for line in execution.read_text(encoding="utf-8").splitlines():
        match = STEP_RE.match(line)
        if match and match.group(2) in dropped_step_ids:
            rewritten.append(f"- {match.group(2)} DROPPED: {match.group(3)}")
        else:
            rewritten.append(line)
    execution.write_text("\n".join(rewritten).rstrip() + "\n", encoding="utf-8")

    safe_reason = re.sub(r"\s+", " ", reason.replace("|", "/")).strip()
    if document.values["spec_mode"] == "required":
        verification_path = execution.parent / "verification.md"
        verification = read_document(verification_path)
        values = dict(verification.values)
        values["commit_sha"] = None
        for category in config.evidence_categories:
            values[category] = "not_applicable"
            values[f"{category}_evidence"] = f"Task dropped: {safe_reason}"
        body_lines: list[str] = []
        for line in verification.body.splitlines():
            match = re.match(
                r"^\|\s*(REQ-[A-Z0-9-]+)\s*\|\s*([A-Z][A-Z0-9]*-\d{16})\s*\|[^|]*\|[^|]*\|$",
                line,
            )
            if match:
                body_lines.append(
                    f"| {match.group(1)} | {match.group(2)} | Dropped: {safe_reason} | not_applicable |"
                )
            else:
                body_lines.append(line)
        verification_path.write_text(
            render_document(values, "\n".join(body_lines) + "\n", order=tuple(values)),
            encoding="utf-8",
        )

    write_lifecycle_receipt(
        root,
        document,
        execution,
        "drop",
        {
            "schema": 1,
            "task_id": document.task_id,
            "change": document.values["openspec_change"],
            "outcome": "dropped",
            "reason": safe_reason,
            "dropped_step_ids": sorted(dropped_step_ids),
            "prepared_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        },
    )
    return execution


def command_close_prepare(args: argparse.Namespace) -> int:
    documents, steps = load_state(args.root)
    document = find_document(documents, args.query)
    if args.outcome == "done":
        if document.values["status"] != "review":
            fail("done closure requires review status")
        verify_task(args.root, document, steps, archive_ready=document.values["spec_mode"] == "required")
        if document.values["spec_mode"] == "required":
            change = document.values["openspec_change"]
            active = args.root / "openspec/changes" / change
            if active.exists():
                fail(f"archive {change} with taskctl openspec archive before preparing done closure")
    else:
        if not args.reason:
            fail("dropped closure requires --reason")
        if not transition_allowed(document.values["status"], "dropped"):
            fail(f"cannot drop task from {document.values['status']}")
        task_steps = [step for step in steps if step.item_id == document.task_id]
        prepare_dropped_execution(args.root, document, task_steps, args.reason)
    values = dict(document.values)
    values["status"] = args.outcome
    values["updated"] = date.today().isoformat()
    values["closed_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    values["closed_reason"] = args.reason or "All acceptance criteria and required evidence passed."
    values["evidence_summary"] = args.evidence
    write_document(document, values)
    execution = expected_execution_path(args.root, Document(document.path, values, document.body))
    write_lifecycle_receipt(
        args.root,
        Document(document.path, values, document.body),
        execution,
        "close",
        {
            "schema": 1,
            "task_id": document.task_id,
            "change": document.values["openspec_change"],
            "outcome": args.outcome,
            "reason": values["closed_reason"],
            "evidence_summary": args.evidence,
            "prepared_at": values["closed_at"],
            "issue_sha256": hashlib.sha256(document.path.read_bytes()).hexdigest(),
            "execution_sha256": hashlib.sha256(execution.read_bytes()).hexdigest(),
        },
    )
    print(f"Prepared terminal state for {document.task_id}; commit it before purge")
    return 0


def command_close_purge(args: argparse.Namespace) -> int:
    documents, _ = load_state(args.root)
    document = find_document(documents, args.query)
    if document.values["status"] not in {"done", "dropped"}:
        fail("purge requires a prepared terminal state")
    relative = document.path.relative_to(args.root).as_posix()
    committed = run_command(("git", "show", f"HEAD:{relative}"), root=args.root)
    if committed.returncode != 0:
        fail("terminal task record must be committed before purge")
    with tempfile.TemporaryDirectory(prefix="ripdpi-task-purge-") as directory:
        snapshot = Path(directory) / "issue.md"
        snapshot.write_text(committed.stdout or "", encoding="utf-8")
        committed_document = read_document(snapshot)
        if committed_document.values.get("status") != document.values["status"]:
            fail("working terminal state differs from HEAD; commit it before purge")
    for candidate in documents:
        if candidate.task_id == document.task_id:
            continue
        if (
            candidate.values["parent"] == document.task_id
            or document.task_id in candidate.values["blocked_by"]
        ):
            fail(f"{document.task_id}: incoming reference from {candidate.task_id}")
        if (
            document.task_id in candidate.values.get("related_tasks", [])
            and document.values["status"] != "done"
        ):
            fail(f"{document.task_id}: incoming reference from {candidate.task_id}")
    execution = expected_execution_path(args.root, document)
    receipt_kinds = (
        ("close", "drop") if document.values["status"] == "dropped" else ("close",)
    )
    for kind in receipt_kinds:
        receipt = lifecycle_receipt_path(args.root, document, execution, kind)
        receipt_relative = receipt.relative_to(args.root).as_posix()
        committed_receipt = run_command(
            ("git", "cat-file", "-e", f"HEAD:{receipt_relative}"), root=args.root
        )
        if (
            committed_receipt.returncode != 0
            and document.values["spec_mode"] == "required"
        ):
            change = document.values["openspec_change"]
            committed_receipt = run_command(
                (
                    "git",
                    "cat-file",
                    "-e",
                    f"HEAD:openspec/changes/{change}/.taskctl-{kind}.json",
                ),
                root=args.root,
            )
        if committed_receipt.returncode != 0:
            fail(f"taskctl {kind} receipt must be committed before purge")
    if document.values["spec_mode"] == "required":
        change = document.values["openspec_change"]
        if (args.root / "openspec/changes" / change).exists():
            fail(f"OpenSpec change {change} is still active")
        archives = list((args.root / "openspec/changes/archive").glob(f"*-{change}"))
        if not archives:
            fail(f"OpenSpec change {change} has not been archived")
    else:
        if execution.exists():
            execution.unlink()
        for kind in receipt_kinds:
            lifecycle_receipt_path(args.root, document, execution, kind).unlink(
                missing_ok=True
            )
    document.path.unlink()
    print(f"Purged {document.task_id}; commit this deletion separately")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--base")
    validate.add_argument("--json", action="store_true")
    validate.add_argument("--skip-upstreams", action="store_true", help=argparse.SUPPRESS)
    validate.set_defaults(handler=command_validate)

    board = subparsers.add_parser("generate-board")
    board.set_defaults(handler=command_generate_board)

    listing = subparsers.add_parser("list")
    listing.add_argument("--status", action="append")
    listing.add_argument("--area", action="append")
    listing.add_argument("--kind", action="append")
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(handler=command_list)

    show = subparsers.add_parser("show")
    show.add_argument("query")
    show.add_argument("--json", action="store_true")
    show.set_defaults(handler=command_show)

    ready = subparsers.add_parser("ready")
    ready.add_argument("--json", action="store_true")
    ready.set_defaults(handler=command_ready)

    graph = subparsers.add_parser("graph")
    graph.add_argument("--json", action="store_true")
    graph.set_defaults(handler=command_graph)

    export = subparsers.add_parser("export")
    export.add_argument("--json", action="store_true")
    export.set_defaults(handler=command_export)

    federation = subparsers.add_parser("federation")
    federation_sub = federation.add_subparsers(dest="federation_command", required=True)
    for name in ("list", "ready", "graph", "validate"):
        federation_command = federation_sub.add_parser(name)
        federation_command.add_argument("--peer-root", type=Path, required=True)
        federation_command.add_argument("--json", action="store_true")
        federation_command.set_defaults(handler=command_federation)

    new = subparsers.add_parser("new")
    new.add_argument("--title", required=True)
    new.add_argument("--kind", required=True, choices=sorted(KINDS))
    new.add_argument("--area", required=True)
    new.add_argument("--priority", required=True, choices=PRIORITIES)
    new.add_argument("--risk", required=True, choices=sorted(RISKS))
    new.add_argument("--owner", default="unassigned")
    new.add_argument("--parent")
    new.add_argument("--slug")
    new.add_argument("--spec-mode", required=True, choices=("required", "not-required"))
    new.add_argument("--spec-reason", choices=sorted(SPEC_REASONS))
    new.add_argument("--openspec-change")
    new.set_defaults(handler=command_new)

    start = subparsers.add_parser("start")
    start.add_argument("query")
    start.add_argument("--owner")
    start.set_defaults(handler=command_start)

    transition = subparsers.add_parser("transition")
    transition.add_argument("query")
    transition.add_argument("status", choices=sorted(STATUSES - {"done", "dropped"}))
    transition.add_argument("--detail")
    transition.set_defaults(handler=command_transition)

    steps = subparsers.add_parser("steps")
    steps.add_argument("query")
    steps.add_argument("mdtask_args", nargs=argparse.REMAINDER)
    steps.set_defaults(handler=command_steps)

    verify = subparsers.add_parser("verify")
    verify.add_argument("query")
    verify.add_argument("--archive-ready", action="store_true")
    verify.set_defaults(handler=command_verify)

    openspec = subparsers.add_parser("openspec")
    openspec_sub = openspec.add_subparsers(dest="openspec_command", required=True)
    openspec_cli = openspec_sub.add_parser("cli")
    openspec_cli.add_argument("openspec_args", nargs=argparse.REMAINDER)
    openspec_cli.set_defaults(handler=command_openspec_cli)
    archive = openspec_sub.add_parser("archive")
    archive.add_argument("change")
    archive.set_defaults(handler=command_openspec_archive)

    close = subparsers.add_parser("close")
    close_sub = close.add_subparsers(dest="close_command", required=True)
    prepare = close_sub.add_parser("prepare")
    prepare.add_argument("query")
    prepare.add_argument("--outcome", required=True, choices=("done", "dropped"))
    prepare.add_argument("--reason")
    prepare.add_argument("--evidence", required=True)
    prepare.set_defaults(handler=command_close_prepare)
    purge = close_sub.add_parser("purge")
    purge.add_argument("query")
    purge.set_defaults(handler=command_close_purge)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.root = args.root.resolve()
    try:
        return int(args.handler(args))
    except (ContractError, OSError, ValueError, SyntaxError, json.JSONDecodeError) as error:
        print(f"taskctl: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
