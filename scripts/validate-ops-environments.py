#!/usr/bin/env python3
"""Check the ops repository's CI environments before any credential is used.

Usage:
  validate-ops-environments.py --root OPS [--public-repo PATH] [--public-ref REF]
  validate-ops-environments.py --root OPS --pr BASE HEAD [--public-repo PATH] [--public-ref REF]

Without --pr, every workflow under OPS/.github/workflows must keep each secret
in the environment that owns its class, run mutating environments only on a
push to the default branch, run no mutating command in a preview environment,
validate pull-request input before its first secret, and have a catalog entry
for every environment secret. Exit 0 when clean, 1 with findings.

With --pr, the diff BASE..HEAD of OPS is classified before credentials load.
Only boolean toggles on existing tfvars files may get an automatic credentialed
preview; any other change waits for the operator's merge. Prints a JSON verdict
and exits 0 for "preview", 1 for "defer".

With --public-repo, the upstream.lock revision (at HEAD in --pr mode) must be a
commit reachable from PUBLIC_REF (default origin/main) of the public checkout.
Exit 2 on usage or repository errors.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

STATE = {"STATE_PASSPHRASE", "STATE_ACCESS_KEY_ID", "STATE_SECRET_ACCESS_KEY"}
PROVIDERS = {"HCLOUD_TOKEN", "UPCLOUD_TOKEN", "VULTR_API_KEY", "SCW_ACCESS_KEY", "SCW_SECRET_KEY",
             "PORKBUN_API_KEY", "PORKBUN_SECRET_API_KEY"}
CI_AGE = {"SOPS_AGE_KEY"}
CI_SSH = {"CI_SSH_PRIVATE_KEY"}
TAILNET_TOFU = {"TS_CI_TOFU_OAUTH_CLIENT_ID", "TS_CI_TOFU_OAUTH_SECRET"}
TAILNET_DEPLOY = {"TS_CI_DEPLOY_OAUTH_CLIENT_ID", "TS_CI_DEPLOY_OAUTH_SECRET"}
TAILNET_POLICY = {"TS_POLICY_OAUTH_CLIENT_ID", "TS_POLICY_OAUTH_SECRET"}
MATRIX = {
    "tofu-plan": STATE | PROVIDERS | TAILNET_TOFU,
    "tofu-apply": STATE | PROVIDERS | TAILNET_TOFU,
    "deploy-check": CI_AGE | CI_SSH | TAILNET_DEPLOY,
    "deploy": CI_AGE | CI_SSH | TAILNET_DEPLOY,
    "ops-secrets": CI_AGE,
    "tailnet-policy": TAILNET_POLICY,
}
MUTATING = {"tofu-apply", "deploy", "ops-secrets", "tailnet-policy"}
EVENTS = {"preview": {"pull_request_target", "schedule", "push"}, "mutating": {"push"}}
MUTATING_COMMAND = re.compile(
    r"\bmake\b[^\n]*?\b(apply|destroy|staging-destroy|deploy[\w-]*|rotate-[\w-]+|issue-[\w-]+|promote-spare|"
    r"blue-green|rollback-[\w-]+|install-[\w-]+|fleet-[\w-]+|restore-state|bootstrap-secrets)\b"
    r"|\b(tofu|terraform|terraform-env\.sh)\b[^\n]*?\b(apply|destroy|import|force-unlock|state\s+(push|rm|mv))\b"
    r"|\bsops\b[^\n]*?(\s(-e|--encrypt|-i|--in-place|updatekeys|rotate|set)\b)")
SECRET_REFERENCE = re.compile(r"\bsecrets\s*(?:\.\s*([A-Za-z_][A-Za-z0-9_]*)|\[\s*['\"]([^'\"]+)['\"]\s*\])")
WHOLE_SECRETS = re.compile(r"\bsecrets\b(?!\s*[.\[])")
PR_HEAD = re.compile(r"github\.event\.pull_request\.head|github\.head_ref")
# Typed fields that an automatic preview may overlay on an existing target.
PREVIEW_TOGGLES = {"enable_hysteria", "enable_backups", "enable_provider_firewall", "additional_public_ip"}
TFVARS_PATH = re.compile(r"config/tfvars/[a-z0-9-]+/[A-Za-z0-9][A-Za-z0-9-]*\.tfvars")
ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
CATALOG_FIELDS = ("scope", "expires_at", "revoke_procedure")


def strings(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [text for key, value in node.items() for text in strings(key) + strings(value)]
    if isinstance(node, list):
        return [text for item in node for text in strings(item)]
    return []


def referenced(node: object) -> set[str]:
    return {one or two for text in strings(node) for one, two in SECRET_REFERENCE.findall(text)} - {"GITHUB_TOKEN"}


def triggers(workflow: dict) -> dict[str, object]:
    # PyYAML reads the bare key `on` as boolean true.
    raw = workflow.get("on", workflow.get(True))
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {event: None for event in raw}
    return dict(raw) if isinstance(raw, dict) else {}


def environment_name(job: dict) -> object:
    environment = job.get("environment")
    return environment.get("name") if isinstance(environment, dict) else environment


def check_job(where: str, job: dict, events: dict[str, object], shared: set[str], default_branch: str,
              used: set[tuple[str, str]]) -> list[str]:
    findings = []
    texts = strings(job)
    if job.get("secrets") == "inherit":
        findings.append(f"{where}: `secrets: inherit` hides which secrets the called workflow uses")
    if any(WHOLE_SECRETS.search(text) for text in texts if "${{" in text):
        findings.append(f"{where}: passes the whole secrets context")
    secrets = referenced(job) | shared
    environment = environment_name(job)
    if environment is None:
        findings += [f"{where}: uses secret {name} without an environment" for name in sorted(secrets)]
        return findings
    if not isinstance(environment, str) or environment not in MATRIX:
        return findings + [f"{where}: environment {environment!r} is not in the environment matrix"]
    findings += [f"{where}: secret {name} does not belong to environment {environment}"
                 for name in sorted(secrets - MATRIX[environment])]
    used.update((environment, name) for name in secrets & MATRIX[environment])
    kind = "mutating" if environment in MUTATING else "preview"
    for event in sorted(set(events) - EVENTS[kind]):
        findings.append(f"{where}: {kind} environment {environment} must not run on {event}")
    push = events.get("push")
    if "push" in events and (not isinstance(push, dict) or push.get("branches") != [default_branch]
                             or "tags" in push or "branches-ignore" in push):
        findings.append(f"{where}: push trigger must name only branch {default_branch}")
    steps = job.get("steps") or []
    if kind == "preview":
        for index, step in enumerate(steps):
            if isinstance(step, dict) and MUTATING_COMMAND.search(str(step.get("run", ""))):
                findings.append(f"{where}: step {index + 1} runs a mutating command in preview environment {environment}")
    if "pull_request_target" in events:
        validated = False
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses", ""))
            settings = step.get("with") or {}
            if (uses.startswith("actions/checkout") and PR_HEAD.search(" ".join(strings(settings)))
                    and str(settings.get("path", ".")).strip("./") == ""):
                findings.append(f"{where}: step {index + 1} checks out the pull request head over the trusted tree")
            if referenced(step) and not validated:
                findings.append(f"{where}: step {index + 1} uses a secret before validate-ops-environments.py --pr")
                break
            if re.search(r"validate-ops-environments\.py\b[^\n]*--pr\b", str(step.get("run", ""))):
                validated = True
    return findings


def check_workflows(root: Path, default_branch: str) -> tuple[list[str], set[tuple[str, str]]]:
    findings: list[str] = []
    used: set[tuple[str, str]] = set()
    directory = root / ".github/workflows"
    for path in sorted(directory.glob("*.y*ml")) if directory.is_dir() else []:
        name = path.relative_to(root).as_posix()
        try:
            workflow = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError) as error:
            findings.append(f"{name}: unreadable workflow ({type(error).__name__})")
            continue
        if not isinstance(workflow, dict):
            findings.append(f"{name}: not a workflow mapping")
            continue
        events = triggers(workflow)
        shared = referenced(workflow.get("env") or {})
        for job_id, job in (workflow.get("jobs") or {}).items():
            if isinstance(job, dict):
                findings += check_job(f"{name} job {job_id}", job, events, shared, default_branch, used)
    return findings, used


def check_catalog(root: Path, used: set[tuple[str, str]]) -> list[str]:
    try:
        entries = json.loads((root / "catalog.json").read_text()).get("credentials", [])
    except (OSError, ValueError, AttributeError):
        return ["catalog.json: unreadable"] if used else []
    held = {(entry.get("environment"), entry.get("secret")): entry for entry in entries
            if isinstance(entry, dict) and entry.get("authority") == "gh-environment"}
    findings = []
    for environment, secret in sorted(used):
        entry = held.get((environment, secret))
        if entry is None:
            findings.append(f"catalog.json: no gh-environment entry for {secret} in {environment}")
        else:
            findings += [f"catalog.json: {secret} in {environment} has no {field}"
                         for field in CATALOG_FIELDS if not entry.get(field)]
    return findings


def git(repository: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repository), *args], capture_output=True, text=True, check=False)


def check_pin(root: Path, revision_ref: str | None, public: Path, public_ref: str) -> list[str]:
    text = git(root, "show", f"{revision_ref}:upstream.lock").stdout if revision_ref else \
        (root / "upstream.lock").read_text() if (root / "upstream.lock").exists() else ""
    pin = dict(line.split("=", 1) for line in text.splitlines() if "=" in line).get("revision", "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", pin):
        return ["upstream.lock: revision must be a full commit id"]
    if git(public, "cat-file", "-e", f"{pin}^{{commit}}").returncode or \
            git(public, "merge-base", "--is-ancestor", pin, public_ref).returncode:
        return [f"upstream.lock: revision is not reachable from {public_ref} of the public repository"]
    return []


def tfvars_toggles(base_text: str, head_text: str, path: str) -> tuple[list[dict], list[str]]:
    base, head = base_text.splitlines(), head_text.splitlines()
    if len(base) != len(head):
        return [], [f"{path}: lines were added or removed"]
    toggles, reasons = [], []
    for number, (old, new) in enumerate(zip(base, head), start=1):
        if old == new:
            continue
        before, after = ASSIGNMENT.match(old), ASSIGNMENT.match(new)
        if not (before and after and before.group(1) == after.group(1)):
            reasons.append(f"{path}:{number}: change is not a value of an existing field")
        elif after.group(1) not in PREVIEW_TOGGLES:
            reasons.append(f"{path}:{number}: field {after.group(1)} needs the operator's merge")
        elif {before.group(2), after.group(2)} - {"true", "false"}:
            reasons.append(f"{path}:{number}: {after.group(1)} must stay a plain boolean")
        else:
            toggles.append({"path": path, "field": after.group(1), "from": before.group(2), "to": after.group(2)})
    return toggles, reasons


def classify(root: Path, base: str, head: str) -> dict:
    for revision in (base, head):
        if git(root, "cat-file", "-e", f"{revision}^{{commit}}").returncode:
            raise SystemExit(f"validate-ops-environments: unknown commit {revision}")
    reasons, toggles = [], []
    if git(root, "merge-base", "--is-ancestor", base, head).returncode:
        reasons.append("head does not descend from the trusted base")
    raw = git(root, "diff", "--raw", "-M", "-z", "--no-ext-diff", base, head)
    if raw.returncode:
        raise SystemExit("validate-ops-environments: git diff failed")
    fields = raw.stdout.split("\0")
    index = 0
    while index < len(fields) - 1:
        meta = fields[index].lstrip(":").split()
        status = meta[4] if len(meta) > 4 else "?"
        count = 2 if status[0] in "RC" else 1
        paths = fields[index + 1:index + 1 + count]
        index += 1 + count
        path = paths[-1]
        if status != "M":
            reasons.append(f"{' -> '.join(paths)}: {status} change needs the operator's merge")
        elif meta[0] != meta[1] or "120000" in meta[:2]:
            reasons.append(f"{path}: mode or symlink change needs the operator's merge")
        elif not TFVARS_PATH.fullmatch(path):
            reasons.append(f"{path}: changes to this path need the operator's merge")
        else:
            found, refused = tfvars_toggles(git(root, "show", f"{base}:{path}").stdout,
                                            git(root, "show", f"{head}:{path}").stdout, path)
            toggles += found
            reasons += refused
    if not toggles and not reasons:
        reasons.append("no previewable change")
    return {"verdict": "defer" if reasons else "preview", "reasons": reasons, "toggles": toggles}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the ops repository's CI environments.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--pr", nargs=2, metavar=("BASE", "HEAD"))
    parser.add_argument("--public-repo", type=Path)
    parser.add_argument("--public-ref", default="origin/main")
    parser.add_argument("--default-branch", default="main")
    args = parser.parse_args()
    if not args.root.is_dir():
        print(f"validate-ops-environments: {args.root} is not a directory", file=sys.stderr)
        return 2
    pin = check_pin(args.root, args.pr[1] if args.pr else None, args.public_repo, args.public_ref) \
        if args.public_repo else []
    if args.pr:
        result = classify(args.root, *args.pr)
        if pin:
            result = {**result, "verdict": "defer", "reasons": pin + result["reasons"]}
        print(json.dumps(result, indent=2))
        return 0 if result["verdict"] == "preview" else 1
    findings, used = check_workflows(args.root, args.default_branch)
    findings += check_catalog(args.root, used) + pin
    for finding in findings:
        print(finding, file=sys.stderr)
    if not findings:
        print(f"ops environments valid ({len(used)} environment secret references)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
