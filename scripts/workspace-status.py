#!/usr/bin/env python3
"""Describe the caller's checkout using local Git metadata and taskctl."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def environment() -> dict[str, str]:
    # Inherited Git overrides can redirect -C to a different checkout or index.
    return {**{key: value for key, value in os.environ.items() if not key.startswith("GIT_")},
            "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1", "OPENSPEC_TELEMETRY": "0"}


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "status.renameLimit=0", "-C", str(cwd), *args],
        capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape",
        env=environment(), check=check, timeout=30,
    )


def summary(task_id: str | None) -> dict:
    cwd = Path.cwd()
    root = Path(git(cwd, "rev-parse", "--show-toplevel").stdout.removesuffix("\n"))
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    shallow = git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    base = {"ref": "origin/main", "revision": None, "ahead": None, "behind": None}
    known_main = git(root, "rev-parse", "--verify", "refs/remotes/origin/main^{commit}", check=False)
    if known_main.returncode == 0:
        base["revision"] = known_main.stdout.strip()
    if base["revision"] and not shallow:
        ahead, behind = git(root, "rev-list", "--left-right", "--count", f"{head}...{base['revision']}").stdout.split()
        base.update(ahead=int(ahead), behind=int(behind))
    changes = {"staged": 0, "unstaged": 0, "untracked": 0}
    entries = iter(git(root, "status", "--porcelain=v1", "-z", "--renames", "--untracked-files=all").stdout.split("\0"))
    for entry in entries:
        if not entry:
            continue
        status = entry[:2]
        if status == "??":
            changes["untracked"] += 1
        else:
            changes["staged"] += status[0] != " "
            changes["unstaged"] += status[1] != " "
            if "R" in status or "C" in status:
                next(entries)  # Porcelain -z adds the rename/copy source path.
    task = None
    if task_id:
        result = subprocess.run(
            [str(root / "taskctl"), "show", "--json", task_id], cwd=root,
            capture_output=True, text=True, check=True, timeout=30,
            env=environment(),
        )
        document = json.loads(result.stdout)
        task = {
            "id": document["task"]["id"], "status": document["task"]["status"],
            "portfolio": document["path"], "execution": document["execution"],
            "change": document["task"]["openspec_change"],
        }
    return {
        "schema": 1, "cwd": str(cwd), "worktree": str(root), "head": head,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "shallow": shallow, "known_main": base, "changes": changes, "task": task,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the same summary as JSON")
    parser.add_argument("--task", metavar="TASK-ID", help="resolve the selected task through taskctl")
    args = parser.parse_args()
    try:
        report = summary(args.task)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration):
        print("workspace-status: checkout or selected task metadata unavailable", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"cwd: {json.dumps(report['cwd'])}\nworktree: {json.dumps(report['worktree'])}")
        branch = json.dumps(report['branch']) if report['branch'] else '(detached HEAD)'
        print(f"branch: {branch}\nHEAD: {report['head']}")
        base = report["known_main"]
        print(f"known main: {base['ref']} {base['revision'] or '(unavailable)'} (local; no fetch)")
        if report["shallow"]:
            print("divergence: unavailable (shallow history)")
        elif base["revision"]:
            print(f"divergence: ahead={base['ahead']} behind={base['behind']}")
        print("changes: " + " ".join(f"{key}={value}" for key, value in report["changes"].items()))
        task = report["task"]
        if task:
            print(f"task: {task['id']} ({task['status']})\nportfolio: {task['portfolio']}\nexecution: {task['execution']}")
            print(f"change: {('openspec/changes/' + task['change']) if task['change'] else '(not required)'}")
        else:
            print("task: unspecified (use --task TASK-ID; discover with ./taskctl list)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
