#!/usr/bin/env bash
set -euo pipefail

tag="${1:-}"
expected_revision="${2:-}"

if [[ ! "$tag" =~ ^vpnd-v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "invalid vpnd release tag: $tag" >&2
  exit 1
fi

if [[ -z "$expected_revision" ]]; then
  echo "expected release revision is required" >&2
  exit 1
fi

if ! tag_revision="$(git rev-parse --verify "refs/tags/${tag}^{commit}")"; then
  echo "vpnd release tag does not resolve to a commit: $tag" >&2
  exit 1
fi

if ! expected_commit="$(git rev-parse --verify "${expected_revision}^{commit}")"; then
  echo "expected release revision does not resolve to a commit" >&2
  exit 1
fi

if [[ "$tag_revision" != "$expected_commit" ]]; then
  echo "vpnd release tag $tag does not match the workflow revision" >&2
  exit 1
fi

printf 'release-tag=%s\n' "$tag"
