"""Generated task-tool dependencies are not repository-owned YAML."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_yamllint_excludes_generated_task_tool_dependencies():
    config = (ROOT / ".yamllint.yml").read_text()

    assert "  tools/tasking/node_modules/\n" in config
