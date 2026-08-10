"""The CLAUDE.md coverage workflow must not parse a PR base ref as shell code."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/claude-md-touch.yml"


def test_base_ref_is_validated_and_used_only_as_data():
    source = WORKFLOW.read_text()

    assert "BASE_REF: ${{ github.base_ref }}" in source
    assert 'git check-ref-format --branch "$BASE_REF"' in source
    assert '"refs/heads/${BASE_REF}:refs/remotes/origin/${BASE_REF}"' in source
    assert 'git diff --name-only "origin/${BASE_REF}"...HEAD' in source
    assert 'git fetch origin "${{ github.base_ref }}"' not in source
    assert '"origin/${{ github.base_ref }}"...HEAD' not in source
