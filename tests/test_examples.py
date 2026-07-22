from pathlib import Path

from pocumentary.cli import main
from pocumentary.spec import parse, validate

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_every_example_validates():
    for path in sorted(EXAMPLES.glob("*.toml")):
        assert validate(parse(path.read_text())) == [], path.name


def test_gated_example_passes_dryrun(tmp_path):
    """The full V4 loop against a real spec: gates fire, roles hand off, the
    verify predicate is met, exit code is 0."""
    assert (
        main(["dryrun", str(EXAMPLES / "gated-demo.toml"), "--runtime-dir", str(tmp_path)]) == 0
    )
    assert (tmp_path / "server_ready").exists()
    assert (tmp_path / "handoff.json").exists()


def test_gated_example_fails_loudly_when_a_role_is_broken(tmp_path):
    """Sabotage the handshake and confirm dryrun returns non-zero — R6.

    Both `signals` and `gate_on` are renamed together, so the spec stays
    internally consistent and `validate` still passes: the failure has to be
    caught at RUN time by the gate. The role scripts are symlinked in so the
    server genuinely runs and writes its real `server_ready`, which no longer
    matches the renamed signal the client now waits on. The gate timeout is
    shrunk to 1s so the test does not sit for the example's 30.
    """
    (tmp_path / "roles").symlink_to(EXAMPLES / "roles", target_is_directory=True)
    spec_text = (
        (EXAMPLES / "gated-demo.toml")
        .read_text()
        .replace("server_ready", "never_written")
        .replace("gate_timeout = 30.0", "gate_timeout = 1.0")
    )
    broken = tmp_path / "broken.toml"
    broken.write_text(spec_text)
    assert main(["dryrun", str(broken), "--runtime-dir", str(tmp_path / "rt")]) == 1
