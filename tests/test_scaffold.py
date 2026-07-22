from pocumentary.scaffold import scaffold_files
from pocumentary.spec import parse, validate


def test_scaffold_emits_exactly_the_expected_files():
    files = scaffold_files()
    assert set(files) == {"demo.toml", "roles/server.sh", "roles/client.sh"}


def test_scaffold_emits_a_valid_spec():
    files = scaffold_files("mydemo")
    assert validate(parse(files["demo.toml"])) == []


def test_scaffold_names_the_output_after_the_demo():
    assert 'out = "mydemo-{stamp}.mov"' in scaffold_files("mydemo")["demo.toml"]


def test_scaffold_is_deterministic():
    assert scaffold_files("x") == scaffold_files("x")


def test_scaffold_roles_carry_out_the_handshake_and_verify_predicate():
    """The server emits the signal the client gates on, and the client writes
    exactly the file [verify] asserts — so the starter passes dryrun, not just
    validate."""
    files = scaffold_files()
    spec = parse(files["demo.toml"])

    (server,) = [p for p in spec.panes if p.signals]
    signal = server.signals[0]
    (client,) = [p for p in spec.panes if p.gate_on == signal]
    assert f"$DEMO_RUNTIME_DIR/{signal}" in files["roles/server.sh"]

    assert spec.verify.expect  # a predicate exists
    for name in spec.verify.expect:
        assert f"$DEMO_RUNTIME_DIR/{name}" in files["roles/client.sh"]


def test_scaffold_roles_hold_the_final_frame():
    """Role scripts must not exit to an interactive prompt during `record` (zsh
    clobbers the window title); they hold with a trailing sleep."""
    files = scaffold_files()
    assert "sleep 30" in files["roles/server.sh"]
    assert "sleep 30" in files["roles/client.sh"]


def test_scaffold_demo_includes_valid_annotations():
    from pocumentary.spec import parse, validate

    files = scaffold_files()
    spec = parse(files["demo.toml"])
    assert len(spec.annotations) >= 1
    assert validate(spec) == []  # sample captions anchor to real events


def test_scaffolded_demo_has_tts_block_and_clean_narration():
    from pocumentary.scaffold import scaffold_files
    from pocumentary.spec import Tts, parse, validate
    from pocumentary.narration import narration_warnings

    toml = scaffold_files("demo")["demo.toml"]
    assert "[tts]" in toml
    spec = parse(toml)
    assert isinstance(spec.tts, Tts)
    assert validate(spec) == []                 # still valid
    assert narration_warnings(spec) == []       # every line fits its duration
    # annotations read as full sentences (end with a period)
    assert all(a.text.rstrip().endswith(".") for a in spec.annotations)
