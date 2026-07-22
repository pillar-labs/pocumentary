"""Pane 1 — the Neo4j + APOC backend (the sink).  KILLCHAIN STEP 4: EXECUTION.

Listens for a driver connection from the agent and runs whatever Cypher arrives,
exactly as a real Neo4j `session.run()` would. This instance has APOC / dbms
procedures enabled, so a `CALL apoc.os.exec([...])` reaches the operating system
— the precondition CVE-2026-55615 depends on. It performs NO judgement about
which queries are safe; that was supposed to be the agent's job.

When the injected Cypher arrives, the OS command runs for real (Calculator
launches) and the `rce` signal fires — the demo's success predicate.
"""
from __future__ import annotations

import ast
import socket
import subprocess
import sys

import demo_common as c


def parse_apoc_exec(cypher: str) -> list[str] | None:
    """If the query calls the OS-exec procedure, pull out its argv list."""
    marker = "apoc.os.exec("
    i = cypher.find(marker)
    if i < 0:
        return None
    start = cypher.find("[", i)
    end = cypher.find("]", start)
    if start < 0 or end < 0:
        return None
    argv = ast.literal_eval(cypher[start : end + 1])
    return [str(a) for a in argv]


def main() -> int:
    c.ensure_runtime()
    c.banner("NEO4J + APOC  (backend — runs whatever Cypher the agent sends)")

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    port = c.free_port()
    srv.bind(("127.0.0.1", port))
    srv.listen(1)
    c.NEO4J_PORT_FILE.write_text(str(port))
    c.step(f"bolt listener up on 127.0.0.1:{port}  (APOC + dbms.security enabled)")
    c.signal("db_ready")
    c.ok("signalled: db_ready")

    srv.settimeout(90.0)
    conn, _ = srv.accept()
    c.ok("agent connected a driver session — waiting for a query")

    conn.settimeout(90.0)
    cypher = c.recv_line(conn)          # blocks until the agent forwards (STEP 3)
    argv = parse_apoc_exec(cypher)

    if argv is None:
        # An ordinary read — answer as the graph would.
        c.step(f"session.run:  {cypher}")
        c.send_line(conn, "42")
    else:
        c.banner("STEP 4 of 4  ·  EXECUTION", ch="-")
        c.step("session.run() runs the query verbatim:")
        print(f"       {cypher}", flush=True)
        c.pace(3.0)
        c.ok(f"APOC procedures are enabled, so this reaches the OS: exec {argv}")
        c.pace(1.0)
        subprocess.Popen(argv)          # <-- attacker-controlled OS command. Pops calc.
        c.send_line(conn, "0")
        c.banner("!!  REMOTE CODE EXECUTION  —  Calculator launched  !!", ch="#")
        c.ok("CVE-2026-55615 · CVSS 9.2 · an attacker's chat prompt just ran code on this host")
        c.signal("rce")

    conn.close()
    srv.close()
    c.pace(4.0)  # hold on the RCE banner for the recording
    return 0


if __name__ == "__main__":
    sys.exit(main())
