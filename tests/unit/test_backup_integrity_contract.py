"""Backup script must prove integrity and snapshot freshness."""

from pathlib import Path


def test_backup_checks_restic_and_remote_contents():
    script = (Path(__file__).resolve().parents[2] / "ansible/roles/backup/templates/vpn-backup.sh.j2").read_text()
    assert 'restic -r "$REPO" check' in script
    assert 'snapshots --tag vpn-stack --latest 1 --json' in script
    assert "rclone check" in script
    assert "rclone size" not in script
