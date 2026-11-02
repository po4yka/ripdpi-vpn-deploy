"""A compiler rebuild must not accept unverified source or overwrite prior output."""

import importlib.util
import io
from pathlib import Path
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("security_runtime_build", ROOT / "scripts/build-security-runtimes.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.mark.parametrize("payload,accepted", [(b"abc", True), (b"abd", False)])
def test_source_checksum_before_publication(tmp_path, monkeypatch, payload, accepted):
    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(payload))
    component = dict(repository="rclone/rclone", commit="be8d6044eacb843b74d335db0c5fbe09222031fe",
                     sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    destination = tmp_path / "source.tar.gz"
    if accepted:
        builder.download_source(component, destination)
        assert destination.read_bytes() == b"abc"
    else:
        with pytest.raises(ValueError, match="checksum"):
            builder.download_source(component, destination)
        assert not destination.exists()


def test_old_compiler_refuses_before_output_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.platform, "system", lambda: "Linux")
    monkeypatch.setattr(builder.shutil, "which", lambda _: "/usr/bin/dpkg-deb")
    monkeypatch.setattr(builder.subprocess, "check_output", lambda *args, **kwargs: "go1.27.2\n")
    with pytest.raises(ValueError, match="exact pinned Go"):
        builder.build(tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_existing_output_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.platform, "system", lambda: "Linux")
    monkeypatch.setattr(builder.shutil, "which", lambda _: "/usr/bin/dpkg-deb")
    monkeypatch.setattr(builder.subprocess, "check_output", lambda *args, **kwargs: "go1.27.3\n")
    sentinel = tmp_path / "prior-artifact"
    sentinel.write_bytes(b"prior artifact")
    with pytest.raises(ValueError, match="new absolute directory"):
        builder.build(tmp_path)
    assert sentinel.read_bytes() == b"prior artifact"
    assert list(tmp_path.iterdir()) == [sentinel]


def test_compiler_process_ignores_ambient_workspace_and_go_environment(tmp_path, monkeypatch):
    output = tmp_path / 'absent-parent/output'
    monkeypatch.setattr(builder.platform, "system", lambda: "Linux")
    monkeypatch.setattr(builder.shutil, "which", lambda _: "/usr/bin/dpkg-deb")
    monkeypatch.setenv('GOENV', '/unselected/go-env')
    monkeypatch.setenv('GOWORK', '/unselected/go.work')
    monkeypatch.setenv('GOTOOLCHAIN', 'auto')
    monkeypatch.setenv('SYNTHETIC_API_TOKEN', 'synthetic')
    def compiler_version(*args, **kwargs):
        assert kwargs['env']['GOENV'] == 'off'
        assert kwargs['env']['GOWORK'] == 'off'
        assert kwargs['env']['GOTOOLCHAIN'] == 'local'
        return 'go1.27.3\n'
    monkeypatch.setattr(builder.subprocess, 'check_output', compiler_version)
    def source_boundary(component, destination):
        with tarfile.open(destination, 'w:gz') as tar:
            member = tarfile.TarInfo('owned-source/app/go.mod')
            member.size = 0
            tar.addfile(member, io.BytesIO())
    monkeypatch.setattr(builder, 'download_source', source_boundary)
    class BuildObserved(Exception):
        pass
    def compiler(argv, **kwargs):
        assert argv[:2] == ['go', 'build']
        env = kwargs['env']
        assert env['GOENV'] == 'off' and env['GOWORK'] == 'off'
        assert env['GOTOOLCHAIN'] == 'local' and env['GOFLAGS'] == '-mod=readonly -p=2'
        assert env['HOME'] == str(tmp_path / 'absent-parent/output/work/home')
        assert 'SYNTHETIC_API_TOKEN' not in env
        raise BuildObserved()
    monkeypatch.setattr(builder.subprocess, 'run', compiler)
    with pytest.raises(BuildObserved):
        builder.build(output)
    assert output.is_dir() and output.stat().st_mode & 0o777 == 0o700
    assert not (output / 'build.json').exists()
