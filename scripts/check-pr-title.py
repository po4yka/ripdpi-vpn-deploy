#!/usr/bin/env python3
"""Require Conventional Commit subjects for the PR title and every commit in the PR.

main is rebase-merged only, so each commit of a pull request lands on main as
its own commit and becomes a release-please input.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

PATTERN = re.compile(r'(feat|fix|perf|test|docs|refactor|revert|chore|ci|build)(\([a-z0-9][a-z0-9-]*\))?!?: [^\r\n]+')
TRAILER = re.compile(r'(?im)^co-authored-by:')


def valid(title):
    return (isinstance(title, str) and PATTERN.fullmatch(title) is not None
            and title == title.strip() and not title.endswith('.')
            and 'codex' not in title.casefold())


def commit_messages(base, head):
    # A rebase merge replays only the non-merge commits of the pull request.
    log = subprocess.run(['git', 'log', '--no-merges', '--format=%H%x00%s%x00%b%x1e', f'{base}..{head}'],
                         capture_output=True, text=True, check=True)
    for record in log.stdout.split('\x1e'):
        record = record.lstrip('\n')
        if record:
            sha, subject, body = record.split('\x00', 2)
            yield sha, subject, body


def commit_problems(base, head):
    problems = []
    for sha, subject, body in commit_messages(base, head):
        if not valid(subject):
            problems.append(f'{sha[:12]}: commit subject is not a Conventional Commit: {subject}')
        if TRAILER.search(body):
            problems.append(f'{sha[:12]}: remove the Co-authored-by trailer')
    return problems


def main():
    if os.environ.get('GITHUB_EVENT_NAME') != 'pull_request':
        print('PR title check does not apply to this event')
        return 0
    pull_request = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['pull_request']
    if not valid(pull_request['title']):
        print('Use a Conventional Commit title, such as ci: improve repository policy', file=sys.stderr)
        return 1
    problems = commit_problems(pull_request['base']['sha'], pull_request['head']['sha'])
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print('Reword the commits above; every commit lands on main through a rebase merge', file=sys.stderr)
        return 1
    print('PR title and commit subjects are valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
