from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_task_contract_validates_the_local_portfolio_only() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "./taskctl validate \"${args[@]}\"" in workflow
    assert "federation validate" not in workflow
    assert "Check out federated RIPDPI portfolio" not in workflow
