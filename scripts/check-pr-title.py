#!/usr/bin/env python3
"""Require a Conventional Commit title for the squash commit."""

import json
import os
from pathlib import Path
import re
import sys

PATTERN = re.compile(r'(feat|fix|perf|test|docs|refactor|revert|chore|ci|build)(\([a-z0-9][a-z0-9-]*\))?!?: [^\r\n]+')


def valid(title):
    return (isinstance(title, str) and PATTERN.fullmatch(title) is not None
            and title == title.strip() and not title.endswith('.')
            and 'codex' not in title.casefold())


def main():
    if os.environ.get('GITHUB_EVENT_NAME') != 'pull_request':
        print('PR title check does not apply to this event')
        return 0
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if not valid(event['pull_request']['title']):
        print('Use a Conventional Commit title, such as ci: improve repository policy', file=sys.stderr)
        return 1
    print('PR title is valid')
    return 0


if __name__ == '__main__':
    sys.exit(main())
