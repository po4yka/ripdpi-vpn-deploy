#!/usr/bin/env python3
"""Plan repository policy changes; apply only with explicit operator authority."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / '.github/repository-policy.json'


def api(endpoint, method='GET', payload=None, allow_missing=False):
    args = ['gh', 'api', '--hostname', 'github.com', '--method', method, endpoint,
            '-H', 'Accept: application/vnd.github+json',
            '-H', 'X-GitHub-Api-Version: 2022-11-28']
    if payload is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        if allow_missing and '(HTTP 404)' in result.stderr:
            return None
        raise RuntimeError(f'GitHub API failed: {method} {endpoint}')
    return json.loads(result.stdout) if result.stdout.strip() else None


def matches(actual, expected):
    """Ignore server-added defaults, but compare every managed rule and actor."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and matches(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            any(matches(item, value) for item in actual) for value in expected)
    return type(actual) is type(expected) and actual == expected


def plan(policy):
    repo = policy['repository']
    if repo != 'po4yka/ripdpi-vpn-deploy':
        raise ValueError('Foreign repository is outside this policy')
    base = f'repos/{repo}'
    metadata = api(base)
    owner_bypass = policy['rulesets'][1]['bypass_actors']
    if (metadata['full_name'] != repo or not metadata['permissions']['admin']
            or metadata['owner']['type'] != 'User'
            or owner_bypass != [{'actor_id': metadata['owner']['id'],
                                 'actor_type': 'User', 'bypass_mode': 'pull_request'}]):
        raise ValueError('Repository, administration access, or owner bypass identity differs')
    if api(f'{base}/branches/main/protection', allow_missing=True) is not None:
        raise ValueError('Classic main protection remains; reconcile it before applying rulesets')
    existing = api(f'{base}/rulesets?per_page=100')
    changes = []
    for desired in policy['rulesets']:
        candidates = [item for item in existing if item['name'] == desired['name']
                      or (desired['name'] == 'main-ci' and item['name'] == 'main')]
        if len(candidates) > 1:
            raise ValueError(f'Ambiguous ruleset: {desired["name"]}')
        if candidates:
            current = candidates[0]
            if current.get('source_type') != 'Repository':
                raise ValueError('Inherited ruleset cannot be changed here')
            endpoint = f'{base}/rulesets/{current["id"]}'
            if not matches(api(endpoint), desired):
                changes.append(('PUT', endpoint, desired))
        else:
            changes.append(('POST', f'{base}/rulesets', desired))
    if not matches(metadata, policy['settings']):
        changes.append(('PATCH', base, policy['settings']))
    immutable = api(f'{base}/immutable-releases')
    if immutable['enabled'] != policy['immutable_releases']:
        if not policy['immutable_releases']:
            raise ValueError('Refusing to disable release immutability')
        changes.append(('PUT', f'{base}/immutable-releases', None))
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply the reviewed repository policy')
    args = parser.parse_args()
    try:
        policy = json.loads(POLICY.read_text())
        changes = plan(policy)
        print(json.dumps([{'method': m, 'endpoint': e, 'payload': p}
                          for m, e, p in changes], indent=2))
        if args.apply:
            for method, endpoint, payload in changes:
                api(endpoint, method, payload)
            if plan(policy):
                raise RuntimeError('Repository readback differs from the reviewed policy')
            print('Repository policy verified; no remaining changes')
    except (ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
