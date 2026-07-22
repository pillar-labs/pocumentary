"""Pane 2 — a langroid `Neo4jChatAgent` stand-in (the vulnerable app).

Mirrors the vulnerable path in langroid <= 0.65.4 across two killchain steps:

  STEP 2  the agent's LLM turns the prompt into a Cypher tool call
          (`CypherRetrievalTool` / `CypherCreationTool`) — the injected command
          becomes the query.
  STEP 3  the handler hands that query straight to the Neo4j driver's
          `session.run()` with NO validation.

The bug (CVE-2026-55615, CWE-74): there is no `allow_dangerous_operations` gate
and no `_validate_query()`. The read path forwards raw query text; the write path
does only a no-op `.upper()` substring check that rejects nothing. The sibling
`SQLChatAgent` got exactly those guards in CVE-2026-25879; the Neo4j module was
left unprotected. So whoever controls the prompt controls the query.
"""
from __future__ import annotations

import socket
import sys

import demo_common as c

CYPHER_KEYWORDS = ("CALL", "MATCH", "CREATE", "MERGE", "LOAD", "UNWIND", "RETURN")


def llm_choose_cypher(prompt: str) -> str:
    """The LLM turns the prompt into a Cypher tool call.

    A poisoned prompt steers this choice — the query it emits is whichever
    Cypher the (possibly attacker-controlled) prompt instructs it to run.
    """
    for line in reversed(prompt.splitlines()):
        line = line.strip()
        if line.upper().startswith(CYPHER_KEYWORDS):
            return line
    return "MATCH (u:User)-[:HAS_ROLE]->(r:Role {name:'admin'}) RETURN count(u)"


def main() -> int:
    c.ensure_runtime()
    c.banner("langroid Neo4jChatAgent  (<= 0.65.4 — the vulnerable agent)")

    c.wait_for(c.NEO4J_PORT_FILE, "neo4j bolt port")
    port = int(c.NEO4J_PORT_FILE.read_text())
    c.step(f"opening a Neo4j driver session to 127.0.0.1:{port}")
    session = c.connect(port)
    c.ok("driver session established")
    c.signal("agent_ready")
    c.ok("signalled: agent_ready  (waiting for a user prompt)")

    c.wait_for(c.PROMPT_FILE, "an incoming chat prompt")
    prompt = c.PROMPT_FILE.read_text()
    c.step("received chat prompt:")
    for line in prompt.splitlines():
        print(f"       | {line}", flush=True)
    c.pace()

    # ---- STEP 2: the LLM writes the query -------------------------------------
    c.banner("STEP 2 of 4  ·  THE LLM WRITES THE QUERY", ch="-")
    cypher = llm_choose_cypher(prompt)
    c.step("the LLM answers with a CypherRetrievalTool call — the injected line becomes the query:")
    print(f"       {cypher}", flush=True)
    c.signal("cypher_emitted")
    c.ok("signalled: cypher_emitted")
    c.pace(4.0)

    # ---- STEP 3: no guardrail between the query and the driver ----------------
    c.banner("STEP 3 of 4  ·  NO GUARDRAIL", ch="-")
    c.step("SQLChatAgent here would call _validate_query() and check allow_dangerous_operations")
    c.ok("Neo4jChatAgent does neither — passing the query to session.run() verbatim")
    c.send_line(session, cypher)   # session.run(cypher)
    c.signal("forwarded")
    c.ok("signalled: forwarded  —  the raw query is on its way to the database")
    result = c.recv_line(session)
    c.ok(f"query returned: {result}")

    session.close()
    c.pace(3.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
