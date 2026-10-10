from pathlib import Path
import pytest
from vpnd.config import Context
from vpnd.protected_file import write_private, require_owner
from concurrent.futures import ThreadPoolExecutor


def fake_ctx(root=Path("/repo"), explain=False):
    return Context(
        root,
        root / "ansible",
        root / "terraform/providers/upcloud",
        "prod",
        "upcloud",
        Path("/config/prod.secrets.sops.yaml"),
        Path("/tmp/vpn-prod.secrets.yaml"),
        Path("/config"),
        explain,
        True,
    )


# Rust test: vpnd/src/protected_file.rs::private_write_preserves_an_unrelated_temp_file
def test_private_write_preserves_an_unrelated_temp_file(tmp_path):
    output = tmp_path / "report.json"
    unrelated = tmp_path / "report.tmp"
    unrelated.write_bytes(b"another writer's bytes")
    write_private(output, b"new report")
    assert unrelated.read_bytes() == b"another writer's bytes"
    assert output.read_bytes() == b"new report"
    assert output.stat().st_mode & 0o777 == 0o600


# Rust test: vpnd/src/protected_file.rs::parallel_private_writes_with_shared_stems_do_not_collide
def test_parallel_private_writes_with_shared_stems_do_not_collide(tmp_path):
    def worker(extension):
        path = tmp_path / f"report.{extension}"
        for _ in range(20):
            write_private(path, extension.encode())
        assert path.read_bytes() == extension.encode()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, ["json", "jsonl", "html", "svg"]))
    assert len(list(tmp_path.iterdir())) == 4


# Rust test: vpnd/src/protected_file.rs::metadata_gate_rejects_a_foreign_uid_even_for_a_private_regular_file
def test_metadata_gate_rejects_a_foreign_uid_even_for_a_private_regular_file(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"")
    path.chmod(0o600)
    metadata = path.stat()
    require_owner(metadata, metadata.st_uid)
    with pytest.raises(ValueError):
        require_owner(metadata, metadata.st_uid + 1)
