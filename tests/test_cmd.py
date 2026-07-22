from pocumentary.cmd import build_command, pane_env
from pocumentary.spec import Pane


def test_build_command_bare():
    assert build_command("python role.py") == "clear; python role.py"


def test_build_command_with_cwd_and_env():
    got = build_command("python role.py", {"DEMO_STEP_DELAY": "2.2"}, "/tmp/demo")
    assert got == "clear; cd /tmp/demo; DEMO_STEP_DELAY=2.2 python role.py"


def test_build_command_quotes_spaces_in_env_and_cwd():
    got = build_command("run", {"MSG": "hello world"}, "/tmp/my demos")
    assert got == "clear; cd '/tmp/my demos'; MSG='hello world' run"


def test_build_command_quotes_single_quote_in_env():
    got = build_command("run", {"MSG": "it's fine"})
    assert got == """clear; MSG='it'"'"'s fine' run"""


def test_build_command_env_order_preserved():
    got = build_command("run", {"A": "1", "B": "2"})
    assert got == "clear; A=1 B=2 run"


def test_pane_env_injects_the_runtime_dir_and_pace():
    env = pane_env(Pane(title="a", cmd="x"), "/tmp/rt", 2.2)
    assert env["DEMO_RUNTIME_DIR"] == "/tmp/rt"
    assert env["DEMO_STEP_DELAY"] == "2.2"


def test_pane_env_formats_a_whole_number_without_a_trailing_zero():
    """`DEMO_STEP_DELAY=0` reads better in a recorded terminal than `0.0`."""
    assert pane_env(Pane(title="a", cmd="x"), "/tmp/rt", 0.0)["DEMO_STEP_DELAY"] == "0"


def test_pane_env_lets_the_pane_override_injected_values():
    pane = Pane(title="a", cmd="x", env={"DEMO_STEP_DELAY": "9", "OWN": "1"})
    env = pane_env(pane, "/tmp/rt", 2.2)
    assert env["DEMO_STEP_DELAY"] == "9"
    assert env["OWN"] == "1"
    assert env["DEMO_RUNTIME_DIR"] == "/tmp/rt"


def test_pane_env_result_feeds_build_command():
    pane = Pane(title="a", cmd="run.py", cwd="/w")
    built = build_command(pane.cmd, pane_env(pane, "/tmp/rt", 0.0), pane.cwd)
    assert built.startswith("clear; cd /w;")
    assert "DEMO_RUNTIME_DIR=/tmp/rt" in built
    assert built.endswith("run.py")
