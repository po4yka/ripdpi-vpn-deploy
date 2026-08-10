from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "branch-protection.yml"


def test_solo_maintainer_merge_keeps_protection_without_required_review() -> None:
    source = WORKFLOW.read_text()

    assert "required_pull_request_reviews:" in source
    assert "required_approving_review_count: 0" in source
    assert "require_code_owner_reviews: false" in source
    assert "require_last_push_approval: false" in source

    assert "strict: true" in source
    assert "enforce_admins: true" in source
    assert "allow_force_pushes: false" in source
    assert "allow_deletions: false" in source
    assert "required_linear_history: true" in source
    assert "required_conversation_resolution: true" in source
