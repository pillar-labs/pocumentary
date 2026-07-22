from pocumentary.gates import PaneStep, resolve_steps, signal_path, validate_gates
from pocumentary.spec import Layout, Pane, Recording, Spec


def _spec(*panes: Pane) -> Spec:
    return Spec(
        recording=Recording(),
        layout=Layout(mode="columns"),
        panes=panes,
    )


def test_resolves_one_step_per_pane_in_order():
    spec = _spec(
        Pane(title="a", cmd="x", signals=("ready",), delay=4.0),
        Pane(title="b", cmd="y", gate_on="ready"),
    )
    assert resolve_steps(spec) == [
        PaneStep(index=0, title="a", wait_for=None, delay=4.0),
        PaneStep(index=1, title="b", wait_for="ready", delay=0.0),
    ]


def test_signal_path_joins_the_runtime_dir():
    assert signal_path("/tmp/rt", "server_ready") == "/tmp/rt/server_ready"


def test_valid_gating_produces_no_errors():
    spec = _spec(
        Pane(title="a", cmd="x", signals=("ready",)),
        Pane(title="b", cmd="y", gate_on="ready", signals=("lure",)),
        Pane(title="c", cmd="z", gate_on="lure"),
    )
    assert validate_gates(spec) == []


def test_gating_on_an_undeclared_signal_is_an_error():
    spec = _spec(Pane(title="a", cmd="x"), Pane(title="b", cmd="y", gate_on="nope"))
    errors = validate_gates(spec)
    assert any("no pane emits" in e and "nope" in e for e in errors)


def test_gating_on_a_later_panes_signal_deadlocks():
    """Pane 1 would wait forever for a signal only pane 2 can emit — and pane 2
    is never launched, because launching is sequential."""
    spec = _spec(
        Pane(title="a", cmd="x", gate_on="ready"),
        Pane(title="b", cmd="y", signals=("ready",)),
    )
    errors = validate_gates(spec)
    assert any("deadlock" in e for e in errors)


def test_gating_on_your_own_signal_deadlocks():
    spec = _spec(Pane(title="a", cmd="x", gate_on="self", signals=("self",)))
    assert any("deadlock" in e for e in validate_gates(spec))


def test_two_panes_emitting_the_same_signal_is_an_error():
    spec = _spec(
        Pane(title="a", cmd="x", signals=("ready",)),
        Pane(title="b", cmd="y", signals=("ready",)),
    )
    errors = validate_gates(spec)
    assert any("emitted by more than one pane" in e and "ready" in e for e in errors)


def test_an_unconsumed_signal_is_not_an_error():
    """Declaring a signal nobody waits on is fine — it may be documentation, or
    a `[verify]` expectation."""
    assert validate_gates(_spec(Pane(title="a", cmd="x", signals=("done",)))) == []
