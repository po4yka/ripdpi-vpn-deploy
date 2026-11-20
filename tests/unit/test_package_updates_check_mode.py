"""Check-mode contract for the unattended security updates role."""

from pathlib import Path

import yaml

from template_render import render_template

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "ansible" / "roles" / "package_updates" / "tasks" / "main.yml"


def test_fresh_host_check_mode_defers_binary_validation_until_install() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    install = next(
        task for task in tasks if task["name"] == "Install unattended update packages"
    )
    validate = next(
        task
        for task in tasks
        if task["name"] == "Validate unattended-upgrades configuration"
    )

    assert install["register"] == "package_updates_packages"
    assert validate["when"] == [
        "_package_updates_effective_enabled",
        "not ansible_check_mode or not (package_updates_packages.changed | default(false))",
    ]


# Release-file fields of the Ubuntu pockets. Every pocket has the release
# codename; only the archive (suite) field names the pocket.
UBUNTU_POCKETS = {
    pocket: {
        "origin": "Ubuntu",
        "label": "Ubuntu",
        "codename": "noble",
        "archive": pocket,
    }
    for pocket in (
        "noble",
        "noble-updates",
        "noble-security",
        "noble-backports",
        "noble-proposed",
    )
}


def _selected_pockets(security_only: bool) -> set[str]:
    policy = render_template(
        ROOT
        / "ansible/roles/package_updates/templates/51ripdpi-unattended-upgrades.j2",
        dict(package_updates={"enabled": True, "security_only": security_only}),
    ).replace("${distro_codename}", "noble")
    patterns = [
        dict(field.split("=", 1) for field in line.strip(' ";').split(","))
        for line in policy.splitlines()
        if line.strip().startswith('"origin=')
    ]
    return {
        pocket
        for pocket, release in UBUNTU_POCKETS.items()
        if any(
            all(release[key] == value for key, value in pattern.items())
            for pattern in patterns
        )
    }


def test_origin_patterns_select_the_intended_ubuntu_pockets() -> None:
    assert _selected_pockets(security_only=True) == {"noble-security"}
    assert _selected_pockets(security_only=False) == {
        "noble",
        "noble-updates",
        "noble-security",
    }


def test_upgrade_timer_gets_a_fixed_per_host_delay_without_a_new_calendar_time() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    stagger = next(task for task in tasks if task.get("register") == "_package_updates_stagger")
    timer = stagger["ansible.builtin.copy"]["content"].splitlines()

    assert timer == ["[Timer]", "RandomizedDelaySec=12h", "FixedRandomDelay=true"]
    # Restarting the timer or moving OnCalendar can start an upgrade during the deploy.
    assert not any(task.get("ansible.builtin.systemd_service", {}).get("state") for task in tasks)
