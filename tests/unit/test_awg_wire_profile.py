"""Exercise canonical input boundaries and source capability admission."""
import pytest

from transport_semantics import (RANGE_SOURCE, RANGE_TOOLS, WIRE_PROFILE, header_range,
                              profile_errors, signature_size, source_errors)


def profile():
    return {"wire_profile": WIRE_PROFILE, "h1": "11-99", "h2": "100-199",
            "h3": "200", "h4": "4294967295", "i1": "<b 0xdeadbeef><r 12><rd 3><rc 4><t>"}


def test_real_profile_preserves_range_and_program():
    raw = profile()
    assert profile_errors(raw, "awg") == []
    assert header_range(raw["h1"]) == (11, 99)
    assert signature_size(raw["i1"]) == 27
    assert source_errors(raw, {"amneziawg_go_commit": RANGE_SOURCE,
                               "amneziawg_tools_commit": RANGE_TOOLS}, "awg") == []


@pytest.mark.parametrize("value", [1, True, None, "", "00", "01", "1-1", "2-1", "-1",
                                  " 1", "1 ", "1-02", "4294967296", "1-4294967296", "1" * 10000])
def test_bad_header_spelling_or_bounds_refuse(value):
    with pytest.raises(ValueError, match="invalid-awg-header-range"):
        header_range(value)


@pytest.mark.parametrize("value", ["deadbeef", "<b 0xAABB>", "<b 0x1>", "<b 0x>", "<r 0>",
                                  "<r 01>", "<r 1281>", "<r 1280><t>", "<t>" * 65,
                                  "<d>", "<ds>", "<dz 2>", "<r 2> ", "<t>\n", 1, ""])
def test_bad_or_excessive_signature_refuses(value):
    with pytest.raises(ValueError, match="invalid-awg-signature"):
        signature_size(value)


def test_overlap_at_closed_endpoint_refuses():
    raw = {**profile(), "h2": "99-199"}
    assert profile_errors(raw, "awg") == [("awg", "header ranges must be pairwise disjoint")]


def test_source_requires_both_exact_commits():
    raw = profile()
    for source in ({}, {"amneziawg_go_commit": RANGE_SOURCE},
                   {"amneziawg_go_commit": RANGE_SOURCE, "amneziawg_tools_commit": "0" * 40}):
        assert source_errors(raw, source, "awg")
    raw.pop("i1")
    assert source_errors(raw, {}, "awg")


def test_singleton_profile_retains_earlier_peer_wire_rules():
    raw = {"wire_profile": WIRE_PROFILE, **{f"h{i}": str(i) for i in range(1, 5)}}
    assert not profile_errors(raw, "awg")
    assert not source_errors(raw, {}, "awg")
    assert source_errors({**raw, "h1": "0"}, {}, "awg")


def test_reviewed_profile_survives_binding_export_and_bundle_validation(tmp_path):
    import json
    from pathlib import Path
    import subprocess
    import sys

    from awg_client import config, export
    from ripdpi_cohort_fingerprint import cohort_fingerprint
    from test_awg_device_binding import document

    source = document()
    source.update(amneziawg_go_commit=RANGE_SOURCE, amneziawg_tools_commit=RANGE_TOOLS)
    source["amneziawg_secrets"]["instances"][0].update(profile())
    block = export(source, {}, "device0", "upcloud:fixture", "awg0", "192.0.2.1")
    assert {name: block[name] for name in profile()} == profile()
    assert block["cohort_fingerprint"] == cohort_fingerprint(block)
    rendered = config(block)
    assert "H1 = 11-99\n" in rendered
    assert "I1 = <b 0xdeadbeef><r 12><rd 3><rc 4><t>\n" in rendered
    assert "wire_profile" not in rendered
    root = Path(__file__).resolve().parents[2]
    bundle = json.loads((root / "contract/ripdpi-bundle.example.json").read_text())
    bundle["amneziawg"] = [block]
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle))
    result = subprocess.run([sys.executable, str(root / "scripts/validate-bundle.py"), str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing", ["amneziawg_go_commit", "amneziawg_tools_commit"])
def test_export_refuses_range_profile_without_both_reviewed_sources(missing):
    from awg_client import export
    from awg_device_binding import BindingError
    from test_awg_device_binding import document

    source = document()
    source.update(amneziawg_go_commit=RANGE_SOURCE, amneziawg_tools_commit=RANGE_TOOLS)
    source.pop(missing)
    source["amneziawg_secrets"]["instances"][0].update(profile())
    with pytest.raises(BindingError, match="invalid-awg-contract"):
        export(source, {}, "device0", "upcloud:fixture", "awg0", "192.0.2.1")


@pytest.mark.parametrize("reviewed", [False, True])
def test_actual_role_admission_preserves_signature_render(tmp_path, reviewed):
    from pathlib import Path
    import subprocess
    import sys
    import yaml

    from test_awg_device_binding import document

    root = Path(__file__).resolve().parents[2]
    role = root / "ansible/roles/amneziawg"
    source = document()
    source["amneziawg_secrets"]["instances"][0].update(profile())
    rendered = tmp_path / "awg.conf"
    play = tmp_path / "admission.yml"
    variables = {
        "ansible_python_interpreter": sys.executable, "role_path": str(role), "vpn": {},
        "amneziawg": {}, "amneziawg_cohort": {},
        "amneziawg_secrets": source["amneziawg_secrets"],
        "amneziawg_go_commit": RANGE_SOURCE,
        "amneziawg_tools_commit": RANGE_TOOLS if reviewed else "0" * 40,
    }
    play.write_text(yaml.safe_dump([{
        "hosts": "localhost", "connection": "local", "gather_facts": False, "become": False,
        "vars": variables, "tasks": [
            {"ansible.builtin.import_tasks": str(role / "tasks/instances.yml")},
            {"name": "Render the admitted profile", "ansible.builtin.template": {
                "src": str(role / "templates/awg0.conf.j2"), "dest": str(rendered), "mode": "0600"},
             "vars": {"_inst": "{{ _awg_instances[0] }}"}},
        ],
    }]))
    result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(play)],
                            capture_output=True, text=True, timeout=30)
    assert (result.returncode == 0) is reviewed, result.stdout + result.stderr
    assert rendered.exists() is reviewed
    if reviewed:
        text = rendered.read_text()
        assert "H1 = 11-99\n" in text
        assert "I1 = <b 0xdeadbeef><r 12><rd 3><rc 4><t>\n" in text
        assert "wire_profile" not in text
