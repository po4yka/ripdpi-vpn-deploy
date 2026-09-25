"""A fresh nginx dry-run must plan installation without starting an absent unit."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_fresh_check_mode_requires_planned_nginx_package_before_activation() -> None:
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/nginx-xhttp/tasks/main.yml").read_text(encoding="utf-8")
    )
    by_name = {task["name"]: task for task in tasks}
    package = by_name["Install nginx"]
    stat = by_name["Inspect nginx unit before check-mode activation"]
    guard = by_name["Require planned nginx installation on a fresh check-mode host"]
    service = by_name["Ensure nginx is enabled and started"]
    assert package["register"] == "_nginx_xhttp_install_plan"
    assert stat["ansible.builtin.stat"]["path"] == "/lib/systemd/system/nginx.service"
    assert guard["ansible.builtin.assert"]["that"] == ["_nginx_xhttp_install_plan.changed"]
    assert tasks.index(package) < tasks.index(stat) < tasks.index(guard) < tasks.index(service)
    assert "_nginx_xhttp_unit_before.stat.exists" in service["when"]
