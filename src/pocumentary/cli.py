"""Thin CLI glue (U2/U4/U13). Effects live behind detect/driver; core stays pure."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from shutil import copyfileobj, rmtree, which
from urllib.request import Request, urlopen

from pocumentary.detect import detect_geometry, detect_scale, detect_screen_device_index
from pocumentary.driver import run_osascript
from pocumentary.dryrun import run_headless
from pocumentary.explain import explain
from pocumentary.gen import generate_layout_applescript
from pocumentary.layout import solve_layout
from pocumentary.naming import STAMP_FORMAT, expand_out
from pocumentary.narration import (
    NarrationError,
    build_sections,
    narrated_out_path,
    narration_warnings,
    overlap_errors,
)
from pocumentary.overlay import OverlayError, build_placements
from pocumentary.postprod import PostprodError, burn_overlays, burn_subtitles, mix_narration
from pocumentary.record import RecordError, prune_takes, run_take
from pocumentary.scaffold import scaffold_files
from pocumentary.spec import Spec, SpecError, Tts, parse, validate
from pocumentary.subtitles import SubtitleError, build_srt, captioned_out_path, load_timeline
from pocumentary.synth import SynthError, synthesize
from pocumentary.verify import check_expectations


def _load_valid_spec(path: str) -> Spec | None:
    """Read, parse and validate a spec. Print errors and return None on failure."""
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        print(f"error: spec file not found: {path}", file=sys.stderr)
        return None
    try:
        spec = parse(text)
    except SpecError as e:
        print(f"{path}: {e}")
        return None
    errors = validate(spec)
    if errors:
        for e in errors:
            print(f"{path}: {e}")
        return None
    return spec


def _anchor_cwds(spec: Spec, spec_path: str) -> Spec:
    """Resolve every pane's cwd against the spec file's directory.

    `record` opens a fresh Terminal (which starts in the user's home dir) while
    `dryrun` inherits the CLI's cwd, so a bare relative cwd resolves differently
    on the two paths. Anchoring to the spec's own directory makes both agree and
    makes a demo runnable from anywhere. A pane with no cwd defaults to the spec
    directory; an absolute cwd is left unchanged (pathlib drops the base when the
    right operand is absolute).
    """
    base = Path(spec_path).resolve().parent
    panes = tuple(
        replace(p, cwd=str(base / p.cwd) if p.cwd else str(base)) for p in spec.panes
    )
    return replace(spec, panes=panes)


def _cmd_validate(path: str) -> int:
    if not Path(path).exists():
        print(f"error: spec file not found: {path}", file=sys.stderr)
        return 2
    spec = _load_valid_spec(path)
    if spec is None:
        return 1
    for w in narration_warnings(spec):
        print(f"warning: {w}", file=sys.stderr)
    print(f"OK: {path} ({len(spec.panes)} panes, layout={spec.layout.mode})")
    return 0


def _cmd_explain() -> int:
    """Print the demo.toml schema reference. Pure output; always succeeds."""
    print(explain())
    return 0


def _cmd_scaffold(target: str) -> int:
    """Write a working starter demo into `target`. Create-only: never overwrite."""
    dest = Path(target)
    files = scaffold_files(dest.name or "demo")

    clashes = sorted(rel for rel in files if (dest / rel).exists())
    if clashes:
        print(
            f"error: refusing to overwrite existing files: {', '.join(clashes)}",
            file=sys.stderr,
        )
        return 2

    for rel, content in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    print(f"scaffolded {len(files)} files into {dest}/")
    print(f"next: uv run pocumentary dryrun {dest / 'demo.toml'}")
    return 0


def is_macos() -> bool:
    return sys.platform == "darwin"


def _cmd_layout(path: str) -> int:
    if not Path(path).exists():
        print(f"error: spec file not found: {path}", file=sys.stderr)
        return 2
    if not is_macos():
        print("error: layout preview requires macOS (Terminal.app)", file=sys.stderr)
        return 2
    spec = _load_valid_spec(path)
    if spec is None:
        return 1
    spec = _anchor_cwds(spec, path)
    try:
        geo = detect_geometry()
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    bounds = solve_layout(geo.width_pt, geo.height_pt, spec.layout.mode, len(spec.panes))
    script = generate_layout_applescript(spec, bounds)
    result = run_osascript(script)
    if result.returncode != 0:
        print(f"error: osascript failed: {result.stderr.strip()}", file=sys.stderr)
        return 2
    print(f"layout: opened {len(spec.panes)} windows ({spec.layout.mode})")
    return 0


def _cmd_record(path: str, runtime_dir: str | None) -> int:
    if not Path(path).exists():
        print(f"error: spec file not found: {path}", file=sys.stderr)
        return 2
    if not is_macos():
        print("error: record requires macOS (Terminal.app + avfoundation)", file=sys.stderr)
        return 2

    spec = _load_valid_spec(path)
    if spec is None:
        return 1
    spec = _anchor_cwds(spec, path)

    ffmpeg = which("ffmpeg")
    if ffmpeg is None:
        print(
            "error: ffmpeg not found on PATH. Install it with: brew install ffmpeg",
            file=sys.stderr,
        )
        return 2

    try:
        geometry = detect_geometry()
        scale = detect_scale()
        device_index = detect_screen_device_index(ffmpeg)
    except (RuntimeError, ValueError, LookupError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    stamp = time.strftime(STAMP_FORMAT)
    out_dir = str(Path(path).resolve().parent)
    out_path = str(Path(out_dir) / expand_out(spec.recording.out, stamp))
    log_path = f"{out_path}.ffmpeg.log"
    runtime = runtime_dir or tempfile.mkdtemp(prefix="pocumentary-")

    try:
        run_take(
            spec,
            geometry,
            scale=scale,
            device_index=device_index,
            out_path=out_path,
            log_path=log_path,
            runtime_dir=runtime,
            ffmpeg=ffmpeg,
        )
    except RecordError as e:
        print(f"error: {e}", file=sys.stderr)
        print(f"ffmpeg log: {log_path}", file=sys.stderr)
        return 2

    for pruned in prune_takes(out_dir, spec.recording.out, spec.recording.keep):
        print(f"pruned old take: {pruned}")

    print(f"recording: {out_path}")
    print(f"runtime dir: {runtime}")

    missing = check_expectations(runtime, spec.verify)
    if missing:
        # The .mov is still worth having — it shows exactly how the demo failed.
        print(f"FAIL: expectations not met: {', '.join(missing)}")
        return 1
    return 0


def _cmd_dryrun(path: str, runtime_dir: str | None) -> int:
    """Run the demo headlessly and return a verdict. Deliberately not macOS-gated."""
    if not Path(path).exists():
        print(f"error: spec file not found: {path}", file=sys.stderr)
        return 2

    spec = _load_valid_spec(path)
    if spec is None:
        return 1
    spec = _anchor_cwds(spec, path)

    runtime = runtime_dir or tempfile.mkdtemp(prefix="pocumentary-dryrun-")
    result = run_headless(spec, runtime)

    if not result.ok:
        for title, output in result.pane_output.items():
            if output.strip():
                print(f"--- {title} ---")
                print(output.rstrip())
        if result.gate_timeout:
            print(f"FAIL: timed out waiting for signal {result.gate_timeout!r}")
        if result.missing:
            print(f"FAIL: expectations not met: {', '.join(result.missing)}")
        print(f"runtime dir: {runtime}")
        return 1

    print(f"PASS: {path} ({len(spec.panes)} panes)")
    print(f"runtime dir: {runtime}")
    return 0


def _fetch_gif(url: str, dest: str) -> None:
    """Download an http(s) GIF to `dest`. Raises OSError (incl. URLError) on failure."""
    req = Request(url, headers={"User-Agent": "pocumentary"})
    with urlopen(req) as resp, open(dest, "wb") as f:  # noqa: S310 - http(s) only, checked by caller
        copyfileobj(resp, f)


def _resolve_gifs(placements: list, spec_path: str, tmp_dir: str) -> list[str]:
    """Map each placement's `gif` to a local file: download http(s) URLs into
    `tmp_dir`, resolve bare paths against the spec's directory. Raises OSError
    (missing file or download failure) naming the offender.
    """
    spec_dir = os.path.dirname(os.path.abspath(spec_path))
    paths: list[str] = []
    for i, p in enumerate(placements):
        if p.gif.startswith(("http://", "https://")):
            dest = os.path.join(tmp_dir, f"overlay-{i:03d}.gif")
            _fetch_gif(p.gif, dest)
            paths.append(dest)
        else:
            local = p.gif if os.path.isabs(p.gif) else os.path.join(spec_dir, p.gif)
            if not os.path.exists(local):
                raise FileNotFoundError(f"overlay gif not found: {local}")
            paths.append(local)
    return paths


def _cmd_annotate(spec_path: str, mov_path: str) -> int:
    """Burn the demo's [[annotation]] captions and [[overlay]] GIFs onto a take.

    Re-runnable: reads the timeline sidecar `record` wrote, so re-wording never
    needs another on-screen take (R3.3b). Captions and overlays are anchored to
    the same events; when both are present they burn in two passes (captions then
    overlays) into one file. Not macOS-gated — ffmpeg runs anywhere.
    """
    spec = _load_valid_spec(spec_path)
    if spec is None:
        return 1
    has_captions = bool(spec.annotations)
    has_overlays = bool(spec.overlays)
    if not (has_captions or has_overlays):
        print(
            f"error: {spec_path} has no [[annotation]] or [[overlay]] blocks to burn",
            file=sys.stderr,
        )
        return 2
    if not Path(mov_path).exists():
        print(f"error: recording not found: {mov_path}", file=sys.stderr)
        return 2
    timeline_path = f"{mov_path}.timeline.json"
    if not Path(timeline_path).exists():
        print(
            f"error: no timeline sidecar at {timeline_path}; "
            f"run `pocumentary record` to produce one",
            file=sys.stderr,
        )
        return 2

    ffmpeg = which("ffmpeg")
    if ffmpeg is None:
        print(
            "error: ffmpeg not found on PATH. Install it with: brew install ffmpeg",
            file=sys.stderr,
        )
        return 2

    try:
        timeline = load_timeline(Path(timeline_path).read_text())
        srt = build_srt(spec.annotations, timeline) if has_captions else ""
        placements = build_placements(spec.overlays, timeline) if has_overlays else []
    except (SubtitleError, OverlayError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    ffprobe = which("ffprobe") or "ffprobe"  # best-effort; used only for the output cap
    out_path = captioned_out_path(mov_path)
    tmp_dir = tempfile.mkdtemp(prefix="pocumentary-annotate-")
    tmp_mov: str | None = None
    try:
        gif_paths = _resolve_gifs(placements, spec_path, tmp_dir) if has_overlays else []
        if has_captions and has_overlays:
            fd, tmp_mov = tempfile.mkstemp(prefix="pocumentary-", suffix=".mov", dir=tmp_dir)
            os.close(fd)
            burn_subtitles(mov_path, srt, tmp_mov, ffmpeg)
            burn_overlays(tmp_mov, gif_paths, placements, out_path, ffmpeg, ffprobe)
        elif has_captions:
            burn_subtitles(mov_path, srt, out_path, ffmpeg)
        else:
            burn_overlays(mov_path, gif_paths, placements, out_path, ffmpeg, ffprobe)
    except OSError as e:
        print(f"error: could not resolve overlay gif: {e}", file=sys.stderr)
        return 2
    except PostprodError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        rmtree(tmp_dir, ignore_errors=True)

    print(f"captioned: {out_path}")
    return 0


_API_KEY_VAR = "ELEVENLABS_API_KEY"


def _parse_env_file(text: str) -> dict[str, str]:
    """Parse a minimal `.env` (KEY=VALUE lines) into a dict. Pure.

    Skips blank lines and `#` comments, tolerates an optional `export ` prefix,
    and strips surrounding single/double quotes from the value. Lines without an
    `=` are ignored.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _resolve_api_key(spec_path: str) -> str | None:
    """Find the ElevenLabs API key: env var first, then a `.env` beside the spec,
    then a `.env` in the current directory. Returns None if none of these has it.
    """
    key = os.environ.get(_API_KEY_VAR)
    if key:
        return key
    seen: set[str] = set()
    for d in (os.path.dirname(os.path.abspath(spec_path)), os.getcwd()):
        env_path = os.path.join(d, ".env")
        if env_path in seen or not os.path.exists(env_path):
            continue
        seen.add(env_path)
        value = _parse_env_file(Path(env_path).read_text()).get(_API_KEY_VAR)
        if value:
            return value
    return None


def _cmd_narrate(spec_path: str, mov_path: str) -> int:
    """Speak the demo's [[annotation]] lines and mix them onto an existing take.

    Re-runnable and re-wordable without another on-screen take (reads the timeline
    sidecar `record` wrote). Synth calls ElevenLabs behind the opt-in pocumentary[tts]
    extra; the API key comes from $ELEVENLABS_API_KEY or a `.env` beside the spec.
    Not macOS-gated — the SDK and ffmpeg run anywhere.
    """
    spec = _load_valid_spec(spec_path)
    if spec is None:
        return 1
    if not spec.annotations:
        print(f"error: {spec_path} has no [[annotation]] blocks to narrate", file=sys.stderr)
        return 2
    if not Path(mov_path).exists():
        print(f"error: recording not found: {mov_path}", file=sys.stderr)
        return 2
    timeline_path = f"{mov_path}.timeline.json"
    if not Path(timeline_path).exists():
        print(
            f"error: no timeline sidecar at {timeline_path}; "
            f"run `pocumentary record` to produce one",
            file=sys.stderr,
        )
        return 2

    ffmpeg = which("ffmpeg")
    if ffmpeg is None:
        print(
            "error: ffmpeg not found on PATH. Install it with: brew install ffmpeg",
            file=sys.stderr,
        )
        return 2
    ffprobe = which("ffprobe")
    if ffprobe is None:
        print(
            "error: ffprobe not found on PATH. Install it with: brew install ffmpeg",
            file=sys.stderr,
        )
        return 2

    api_key = _resolve_api_key(spec_path)
    if api_key:
        print("narrating with ElevenLabs", file=sys.stderr)
    else:
        print(
            f"note: no ${_API_KEY_VAR} (and no .env beside {spec_path}); "
            "falling back to on-device TTS (pip install 'pocumentary[tts-local]')",
            file=sys.stderr,
        )

    try:
        timeline = load_timeline(Path(timeline_path).read_text())
        sections = build_sections(spec.annotations, timeline)
    except (SubtitleError, NarrationError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    tts = spec.tts or Tts()
    out_dir = tempfile.mkdtemp(prefix="pocumentary-narrate-")
    try:
        try:
            clips = synthesize(sections, tts, out_dir, api_key, ffprobe)
        except SynthError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

        overlaps = overlap_errors(sections, [c.duration for c in clips])
        if overlaps:
            for o in overlaps:
                print(f"error: {o}", file=sys.stderr)
            return 2

        out_path = narrated_out_path(mov_path)
        try:
            mix_narration(
                mov_path, [c.path for c in clips], [s.offset for s in sections],
                out_path, ffmpeg,
            )
        except PostprodError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    finally:
        rmtree(out_dir, ignore_errors=True)

    print(f"narrated: {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pocumentary")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="check a demo.toml (pure, no screen)")
    p_validate.add_argument("spec", help="path to demo.toml")

    p_layout = sub.add_parser("layout", help="tile Terminal windows on screen, no capture")
    p_layout.add_argument("spec", help="path to demo.toml")

    p_record = sub.add_parser("record", help="run a full on-screen take and capture it")
    p_record.add_argument("spec", help="path to demo.toml")
    p_record.add_argument(
        "--runtime-dir", default=None, help="handshake directory (default: a fresh temp dir)"
    )

    p_dryrun = sub.add_parser(
        "dryrun", help="run the demo headlessly and assert its success (no screen)"
    )
    p_dryrun.add_argument("spec", help="path to demo.toml")
    p_dryrun.add_argument(
        "--runtime-dir", default=None, help="handshake directory (default: a fresh temp dir)"
    )

    p_annotate = sub.add_parser(
        "annotate", help="burn [[annotation]] captions onto a recorded take"
    )
    p_annotate.add_argument("spec", help="path to demo.toml")
    p_annotate.add_argument("mov", help="the recording (.mov) produced by `pocumentary record`")

    p_narrate = sub.add_parser(
        "narrate", help="speak [[annotation]] lines and mix them onto a recording"
    )
    p_narrate.add_argument("spec", help="path to demo.toml")
    p_narrate.add_argument("mov", help="the recording (.mov) produced by `pocumentary record`")

    p_scaffold = sub.add_parser(
        "scaffold", help="write a working starter demo.toml + role stubs"
    )
    p_scaffold.add_argument("dir", help="directory to create the starter demo in")

    sub.add_parser(
        "explain", help="print the demo.toml schema reference (agent-consumable)"
    )
    sub.add_parser("docs", help="alias for explain")

    args = parser.parse_args(argv)
    if args.cmd == "validate":
        return _cmd_validate(args.spec)
    if args.cmd == "layout":
        return _cmd_layout(args.spec)
    if args.cmd == "record":
        return _cmd_record(args.spec, args.runtime_dir)
    if args.cmd == "dryrun":
        return _cmd_dryrun(args.spec, args.runtime_dir)
    if args.cmd == "annotate":
        return _cmd_annotate(args.spec, args.mov)
    if args.cmd == "narrate":
        return _cmd_narrate(args.spec, args.mov)
    if args.cmd == "scaffold":
        return _cmd_scaffold(args.dir)
    if args.cmd in ("explain", "docs"):
        return _cmd_explain()
    parser.error(f"unknown command: {args.cmd}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
