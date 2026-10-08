"""Real local publication and Make boundaries; synthetic inputs are not live proof."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from test_disposable_promotion import intent

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/prepare-disposable-promotion-intent.py"


def module():
    spec = importlib.util.spec_from_file_location("prepare_intent", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def setup(tmp_path, intent):
    private = tmp_path.resolve()
    private.chmod(0o700)
    config = private / "predeployment.json"
    config.write_text(json.dumps(intent["liveness"]))
    config.chmod(0o600)
    (private / "prepared").mkdir(mode=0o700)
    helper = module()
    values = {name + "_LITERAL": intent["inputs"][key]
              for key, name in helper.INPUT_ENV.items()}
    values.update({
        "PROMOTION_LIVENESS_CONFIG_LITERAL": str(config),
        "PROMOTION_CLIENT_LITERAL": intent["client"],
        "PROMOTION_OUTPUT_DIR_LITERAL": str(private / "prepared"),
    })
    return helper, values, config


def test_publishes_valid_private_intent_and_exact_alias_mapping_without_key_reads(setup):
    helper, values, config = setup
    # Referenced credentials deliberately do not exist; preparation must not open them.
    for name in helper.INPUT_ENV.values():
        assert not Path(values[name + "_LITERAL"]).exists()
    original = config.read_bytes()
    outcome = helper.prepare(values)
    output = Path(values["PROMOTION_OUTPUT_DIR_LITERAL"])
    data = json.loads((output / "intent.json").read_bytes())
    assert helper.validate_intent(data) == data
    assert json.loads((output / "deployment-inputs.json").read_bytes()) == {
        data["target_identity"]["inventory_alias"]: str(output / "intent.json")
    }
    assert "applied_at" not in data["target_identity"]
    assert outcome == {"status": "promotion-intent-prepared"}
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in output.iterdir())
    assert set(p.name for p in output.iterdir()) == {"intent.json", "deployment-inputs.json"}
    assert config.read_bytes() == original
    assert all(not Path(p).exists() for p in data["outputs"].values())


@pytest.mark.parametrize("case", ["prod", "epoch", "profile", "config-mode", "parent-mode",
                                  "symlink-config", "symlink-parent", "output-exists",
                                  "input-alias", "missing", "duplicate", "oversized", "nan", "deep",
                                  "output-missing", "output-mode"])
def test_refusal_preserves_inputs_and_existing_destination(setup, case):
    helper, values, config = setup
    output = Path(values["PROMOTION_OUTPUT_DIR_LITERAL"])
    if case in {"prod", "epoch", "profile"}:
        data = json.loads(config.read_bytes())
        if case == "prod":
            data["sentinels"][0]["awg_target"]["environment"] = "prod"
        elif case == "epoch":
            data["sentinels"][0]["target"]["applied_at"] = 1
        else:
            data["policies"][0]["required_profiles"].pop()
        config.write_text(json.dumps(data))
    elif case == "config-mode":
        config.chmod(0o644)
    elif case == "parent-mode":
        config.parent.chmod(0o755)
    elif case == "symlink-config":
        link = config.with_name("link.json")
        link.symlink_to(config)
        values["PROMOTION_LIVENESS_CONFIG_LITERAL"] = str(link)
    elif case == "symlink-parent":
        link = config.with_name("link")
        link.symlink_to(config.parent, target_is_directory=True)
        values["PROMOTION_OUTPUT_DIR_LITERAL"] = str(link / "prepared")
    elif case == "output-exists":
        (output / "retained").write_text("existing")
    elif case == "output-missing":
        output.rmdir()
    elif case == "output-mode":
        output.chmod(0o755)
    elif case == "input-alias":
        values["PROMOTION_SOPS_FILE_LITERAL"] = str(output / "intent.json")
    elif case == "missing":
        del values["PROMOTION_CLIENT_LITERAL"]
    elif case == "duplicate":
        config.write_text('{"sentinels":[],"sentinels":[]}')
    elif case == "nan":
        config.write_text('{"invalid":NaN}')
    elif case == "deep":
        config.write_text("[" * 1500 + "0" + "]" * 1500)
    elif case == "oversized":
        config.write_text(" " * (helper.LIMIT + 1))
    original = config.read_bytes()
    with pytest.raises(helper.PreparationError):
        helper.prepare(values)
    assert config.read_bytes() == original
    if case == "output-exists":
        assert (output / "retained").read_text() == "existing"
    elif case == "output-missing":
        assert not output.exists()
    else:
        assert list(output.iterdir()) == []
    if case == "output-mode":
        assert stat.S_IMODE(output.stat().st_mode) == 0o755


def test_interrupted_publication_retains_private_partial_without_success(setup, monkeypatch):
    helper, values, _ = setup
    publish = helper._publish
    def fail_mapping(fd, name, value):
        if name == "deployment-inputs.json":
            raise OSError("private diagnostic must not be exposed")
        publish(fd, name, value)
    monkeypatch.setattr(helper, "_publish", fail_mapping)
    with pytest.raises(helper.PreparationError, match="^intent-preparation-incomplete$"):
        helper.prepare(values)
    output = Path(values["PROMOTION_OUTPUT_DIR_LITERAL"])
    assert set(p.name for p in output.iterdir()) == {"intent.json"}
    original = (output / "intent.json").read_bytes()
    with pytest.raises(helper.PreparationError, match="^intent-output-not-empty$"):
        helper.prepare(values)
    assert (output / "intent.json").read_bytes() == original


def test_replaced_destination_refuses_success_without_touching_replacement(setup, monkeypatch):
    helper, values, _ = setup
    output = Path(values["PROMOTION_OUTPUT_DIR_LITERAL"])
    moved = output.with_name("retained-partial")
    publish = helper._publish
    def replace_after_intent(fd, name, value):
        publish(fd, name, value)
        if name == "intent.json":
            output.rename(moved)
            output.mkdir(mode=0o700)
            (output / "foreign").write_text("retained")
    monkeypatch.setattr(helper, "_publish", replace_after_intent)
    with pytest.raises(helper.PreparationError, match="^intent-directory-changed$"):
        helper.prepare(values)
    assert set(p.name for p in output.iterdir()) == {"foreign"}
    assert (output / "foreign").read_text() == "retained"
    assert set(p.name for p in moved.iterdir()) == {"intent.json"}


def test_replacement_before_first_write_keeps_foreign_mode_and_contents(setup, monkeypatch):
    helper, values, _ = setup
    output = Path(values["PROMOTION_OUTPUT_DIR_LITERAL"])
    moved = output.with_name("retained-empty")
    open_directory = helper._directory
    replaced = False
    def replace_after_open(path):
        nonlocal replaced
        fd = open_directory(path)
        if path == output and not replaced:
            replaced = True
            output.rename(moved)
            output.mkdir(mode=0o755)
            output.chmod(0o755)
            (output / "foreign").write_text("retained")
        return fd
    monkeypatch.setattr(helper, "_directory", replace_after_open)
    with pytest.raises(helper.PreparationError):
        helper.prepare(values)
    assert stat.S_IMODE(output.stat().st_mode) == 0o755
    assert (output / "foreign").read_text() == "retained"
    assert set(p.name for p in output.iterdir()) == {"foreign"}
    assert list(moved.iterdir()) == []


def run_make(setup, *arguments, extra=None):
    _, values, _ = setup
    env = {k: v for k, v in os.environ.items()
           if k not in {"MAKEFILES", "MAKEFLAGS", "GNUMAKEFLAGS", "MFLAGS"}}
    env.update({key.removesuffix("_LITERAL"): value for key, value in values.items()})
    env.update(extra or {})
    return subprocess.run(["make", "--no-print-directory", *arguments], cwd=ROOT,
                          env=env, text=True, capture_output=True, timeout=30)


def test_real_make_publishes_the_same_contract_without_operator_configuration(setup, tmp_path):
    # MAKE variable expansion would execute this poison value if configuration were parsed.
    poison = tmp_path / "operator-config-read"
    result = run_make(setup, "prepare-disposable-promotion-intent",
                      extra={"PROVIDER": "$(shell touch " + str(poison) + ")"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "promotion-intent-prepared"}
    assert not poison.exists()


@pytest.mark.parametrize("source", ["environment", "command", "mixed-goal"])
def test_make_refuses_or_keeps_expressions_literal_before_effects(setup, tmp_path, source):
    marker = tmp_path / "expression-executed"
    expression = "$(shell touch " + str(marker) + ")"
    arguments = ["prepare-disposable-promotion-intent"]
    extra = {}
    if source == "environment":
        extra["PROMOTION_CLIENT"] = expression
    elif source == "command":
        arguments.append("PROMOTION_CLIENT=" + expression)
    else:
        arguments.append("deploy")
    result = run_make(setup, *arguments, extra=extra)
    assert result.returncode != 0
    assert not marker.exists()
    assert list(Path(setup[1]["PROMOTION_OUTPUT_DIR_LITERAL"]).iterdir()) == []
    assert expression not in result.stdout + result.stderr


def test_command_argument_refusal_does_not_echo_input():
    value = "private-value-must-not-be-echoed"
    result = subprocess.run([sys.executable, str(SCRIPT), "--unexpected", value],
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "intent-arguments-refused"
    assert value not in result.stderr
