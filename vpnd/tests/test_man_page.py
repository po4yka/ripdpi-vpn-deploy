import argparse
from vpnd.commands.completions import command_tree, render_page_set, write_man_pages


def pages():
    return {name: page.replace(r"\-", "-") for name, page in render_page_set()}


# Rust test: vpnd/tests/man_page.rs::man_pages_cover_every_subcommand_and_visible_flag
def test_man_pages_cover_every_subcommand_and_visible_flag():
    result = pages()
    for name in [
        "vpnd",
        "vpnd-deploy",
        "vpnd-reconverge",
        "vpnd-share",
        "vpnd-doctor",
        "vpnd-probe",
        "vpnd-probe-matrix",
        "vpnd-preflight",
        "vpnd-fleet",
        "vpnd-fleet-status",
        "vpnd-fleet-rotate",
        "vpnd-fleet-drift",
        "vpnd-host",
        "vpnd-host-list",
        "vpnd-host-show",
        "vpnd-host-add",
        "vpnd-host-remove",
        "vpnd-ai-docs",
        "vpnd-update",
        "vpnd-completions",
    ]:
        assert name in result
    for command in ["deploy", "share", "doctor", "probe-matrix", "host", "update"]:
        assert command in result["vpnd"]
    for path, parser in command_tree():
        page = result["-".join(("vpnd",) + path)]
        for action in parser._actions:
            if action.help != argparse.SUPPRESS:
                for flag in action.option_strings:
                    if flag.startswith("--"):
                        assert flag in page


# Rust test: vpnd/tests/man_page.rs::man_pages_render_the_real_flag_values_the_replica_drifted_on
def test_man_pages_render_the_real_flag_values_the_replica_drifted_on():
    result = pages()
    assert "--duration" in result["vpnd-probe-matrix"] and "4h" in result["vpnd-probe-matrix"]
    assert "--token-stdin" in result["vpnd-share"] and "--token-file" in result["vpnd-share"]
    assert "--clip" in result["vpnd-doctor"] and "--ai" in result["vpnd-doctor"]


# Rust test: vpnd/tests/man_page.rs::man_pages_are_written_to_target_man_for_install
def test_man_pages_are_written_to_target_man_for_install(tmp_path):
    out = tmp_path / "target/man"
    write_man_pages(out)
    for name in ["vpnd.1", "vpnd-doctor.1", "vpnd-fleet-status.1"]:
        assert (out / name).is_file()
