import time

from pocumentary.dryrun import HeadlessResult, launch_pane, run_headless, terminate_all, wait_for_signal
from pocumentary.spec import Layout, Pane, Recording, Spec, Verify


def test_launches_a_pane_and_collects_its_exit_code(tmp_path):
    lp = launch_pane(Pane(title="a", cmd="exit 0"), str(tmp_path))
    assert lp.proc.wait(timeout=10) == 0


def test_a_failing_pane_reports_its_status(tmp_path):
    lp = launch_pane(Pane(title="a", cmd="exit 7"), str(tmp_path))
    assert lp.proc.wait(timeout=10) == 7


def test_the_runtime_dir_is_visible_to_the_pane(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    pane = Pane(title="a", cmd='printf "%s" "$DEMO_RUNTIME_DIR" > out.txt', cwd=str(work))
    launch_pane(pane, str(tmp_path)).proc.wait(timeout=10)
    assert (work / "out.txt").read_text() == str(tmp_path)


def test_pane_cwd_is_honoured(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    pane = Pane(title="a", cmd='printf "%s" "$DEMO_RUNTIME_DIR" > seen.txt', cwd=str(work))
    launch_pane(pane, str(tmp_path)).proc.wait(timeout=10)
    assert (work / "seen.txt").read_text() == str(tmp_path)


def test_headless_pacing_is_off_by_default(tmp_path):
    """R2: pacing is for humans watching a recording; headless runs flat out."""
    work = tmp_path / "w"
    work.mkdir()
    pane = Pane(title="a", cmd='printf "%s" "$DEMO_STEP_DELAY" > d.txt', cwd=str(work))
    launch_pane(pane, str(tmp_path)).proc.wait(timeout=10)
    assert (work / "d.txt").read_text() == "0"


def test_pane_env_reaches_the_process(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    pane = Pane(title="a", cmd='printf "%s" "$MY_VAR" > v.txt', cwd=str(work), env={"MY_VAR": "hi"})
    launch_pane(pane, str(tmp_path)).proc.wait(timeout=10)
    assert (work / "v.txt").read_text() == "hi"


def test_the_ambient_environment_is_inherited(tmp_path, monkeypatch):
    """Role scripts need PATH and friends; we add to the environment, not replace it."""
    monkeypatch.setenv("AMBIENT_MARKER", "present")
    work = tmp_path / "w"
    work.mkdir()
    pane = Pane(title="a", cmd='printf "%s" "$AMBIENT_MARKER" > a.txt', cwd=str(work))
    launch_pane(pane, str(tmp_path)).proc.wait(timeout=10)
    assert (work / "a.txt").read_text() == "present"


def test_pane_env_overrides_the_ambient_value(tmp_path, monkeypatch):
    """The pane's own env wins over the inherited ambient value: launch_pane
    layers pane_env on top of os.environ, so a colliding key resolves to the
    pane's value, not the ambient one."""
    monkeypatch.setenv("COLLIDE", "ambient")
    work = tmp_path / "w"
    work.mkdir()
    pane = Pane(
        title="a",
        cmd='printf "%s" "$COLLIDE" > c.txt',
        cwd=str(work),
        env={"COLLIDE": "pane"},
    )
    launch_pane(pane, str(tmp_path)).proc.wait(timeout=10)
    assert (work / "c.txt").read_text() == "pane"


def test_a_chatty_pane_does_not_deadlock_and_output_is_captured(tmp_path):
    """A pane that writes far more than a pipe buffer (~64KB) before exiting
    would hang a PIPE-based launcher waiting on an undrained pipe; a
    file-backed launcher must let it finish and still capture every byte."""
    lp = launch_pane(Pane(title="a", cmd="yes X | head -c 100000"), str(tmp_path))
    assert lp.proc.wait(timeout=10) == 0
    assert len(lp.read_output()) == 100000


def test_read_output_captures_what_a_pane_prints(tmp_path):
    lp = launch_pane(Pane(title="a", cmd='printf "hello world"'), str(tmp_path))
    lp.proc.wait(timeout=10)
    assert lp.read_output() == "hello world"


def test_terminate_all_stops_long_running_panes(tmp_path):
    panes = [launch_pane(Pane(title=f"p{i}", cmd="sleep 60"), str(tmp_path)) for i in range(2)]
    terminate_all(panes, grace=2.0)
    assert all(p.proc.poll() is not None for p in panes)


def test_terminate_all_tolerates_already_finished_panes(tmp_path):
    lp = launch_pane(Pane(title="a", cmd="exit 0"), str(tmp_path))
    lp.proc.wait(timeout=10)
    terminate_all([lp], grace=2.0)  # must not raise
    assert lp.proc.poll() == 0


def _spec(*panes, **kw):
    return Spec(
        recording=Recording(gate_timeout=kw.pop("gate_timeout", 10.0)),
        layout=Layout(mode="columns"),
        panes=panes,
        verify=kw.pop("verify", Verify()),
    )


def test_wait_for_signal_sees_a_file_that_appears(tmp_path):
    (tmp_path / "ready").write_text("")
    assert wait_for_signal(str(tmp_path), "ready", timeout=1.0) is True


def test_wait_for_signal_gives_up(tmp_path):
    started = time.monotonic()
    assert wait_for_signal(str(tmp_path), "never", timeout=0.3) is False
    assert time.monotonic() - started < 3


def test_gated_panes_run_in_order(tmp_path):
    """Pane B may only start after pane A's handshake file exists. B records the
    order by appending to a shared log, so a wrong order is visible, not inferred."""
    spec = _spec(
        Pane(
            title="A",
            cmd='sleep 0.4; echo A >> "$DEMO_RUNTIME_DIR/order"; : > "$DEMO_RUNTIME_DIR/ready"',
            signals=("ready",),
        ),
        Pane(
            title="B",
            cmd='echo B >> "$DEMO_RUNTIME_DIR/order"; : > "$DEMO_RUNTIME_DIR/b_done"',
            gate_on="ready",
        ),
        # Wait on B's OWN completion signal, not on `order`. `order` already
        # exists the moment the gate opens, so expecting it would let the run
        # finish — and terminate B — before B had written its line.
        verify=Verify(expect=("b_done",), timeout=10.0),
    )
    result = run_headless(spec, str(tmp_path))
    assert result.ok
    assert (tmp_path / "order").read_text().split() == ["A", "B"]


def test_a_gate_that_never_fires_is_reported(tmp_path):
    spec = _spec(
        Pane(title="A", cmd="true", signals=("ready",)),  # declared but never written
        Pane(title="B", cmd="true", gate_on="ready"),
        gate_timeout=0.3,
    )
    result = run_headless(spec, str(tmp_path))
    assert result.gate_timeout == "ready"
    assert not result.ok


def test_unmet_expectations_fail_the_run(tmp_path):
    spec = _spec(
        Pane(title="A", cmd="true"),
        verify=Verify(expect=("takeover.json",), timeout=0.3),
    )
    result = run_headless(spec, str(tmp_path))
    assert result.missing == ["takeover.json"]
    assert not result.ok


def test_met_expectations_pass_the_run(tmp_path):
    spec = _spec(
        Pane(title="A", cmd='echo done > "$DEMO_RUNTIME_DIR/takeover.json"'),
        verify=Verify(expect=("takeover.json",), timeout=10.0),
    )
    assert run_headless(spec, str(tmp_path)).ok


def test_pane_output_is_captured_for_diagnosis(tmp_path):
    spec = _spec(Pane(title="A", cmd="echo hello-from-pane"))
    result = run_headless(spec, str(tmp_path))
    assert "hello-from-pane" in result.pane_output["A"]


def test_long_running_panes_are_cleaned_up(tmp_path):
    """A demo whose server never exits must not leave a process behind."""
    spec = _spec(
        Pane(title="server", cmd=': > "$DEMO_RUNTIME_DIR/up"; sleep 60', signals=("up",)),
        Pane(title="client", cmd="true", gate_on="up"),
        verify=Verify(expect=("up",), timeout=10.0),
    )
    started = time.monotonic()
    result = run_headless(spec, str(tmp_path))
    assert result.ok
    assert time.monotonic() - started < 30  # did not wait out the 60s sleep


def test_the_runtime_dir_is_created_if_absent(tmp_path):
    target = tmp_path / "fresh"
    run_headless(_spec(Pane(title="A", cmd="true")), str(target))
    assert target.is_dir()


def test_no_expectations_still_bounds_a_runaway_pane(tmp_path):
    """With no verify expectations, a pane that never exits must not hang the
    run: the wait for natural completion is bounded, then cleanup fires."""
    spec = _spec(Pane(title="A", cmd="sleep 60"), verify=Verify(timeout=0.5))
    started = time.monotonic()
    result = run_headless(spec, str(tmp_path))
    assert result.ok  # no expectations => nothing missing
    assert time.monotonic() - started < 10  # bounded, did not wait out the sleep


def test_a_chatty_gating_pane_still_opens_the_gate(tmp_path):
    """Regression: a pane writing far more than a pipe buffer (~64KB) before
    creating its signal file must still open the gate. File-backed capture
    lets it keep writing; a pipe would block it before it could signal, so the
    gate would falsely time out."""
    spec = _spec(
        Pane(
            title="A",
            cmd='yes X | head -c 200000; : > "$DEMO_RUNTIME_DIR/ready"',
            signals=("ready",),
        ),
        Pane(title="B", cmd=': > "$DEMO_RUNTIME_DIR/b_done"', gate_on="ready"),
        verify=Verify(expect=("b_done",), timeout=10.0),
        gate_timeout=10.0,
    )
    result = run_headless(spec, str(tmp_path))
    assert result.gate_timeout is None
    assert result.ok
    assert len(result.pane_output["A"]) >= 200000
