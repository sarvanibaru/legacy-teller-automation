# Legacy Teller Automation

A computer-use automation system for legacy bank-style UIs: an LLM discovers how
to complete a goal against a target application, records the successful run as
a reusable, typed capability artifact, and replays that artifact
deterministically — with no model in the loop — including handling runtime
errors and escalating to a human when it can't safely proceed on its own.

See [`REPORT.md`](REPORT.md) for the full design write-up (architecture,
schema, determinism, heterogeneity/multi-tenant design, escalation, safety,
and cuts).

## 1. Setup

### Prerequisites

- Python 3.9+
- A terminal and `git`

### Install

```bash
git clone <this-repo-url>
cd legacy-teller-automation

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -e ".[dev]"
playwright install chromium
```

### Configure

Copy the example environment file and fill in your own Anthropic API key:

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=sk-ant-your-real-key-here
MOCK_APP_BASE_URL=http://localhost:5001
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

`ANTHROPIC_MODEL` can be swapped for any model your key has access to (e.g.
`claude-sonnet-4-6`) without touching any code. The discovery and demo scripts
below make real API calls and cost a small fraction of a cent each with
Haiku.

The mock app's login credentials (`user1` / `password123`, see
`mock_app/data.py`) are intentionally trivial — they protect nothing real, so
they're committed in plaintext on purpose rather than hidden behind
environment variables. The one credential that matters, the Anthropic API
key, is the only thing that ever goes in `.env` (gitignored, never committed).

### Start the target application

Most of what follows needs the mock bank app running. In its own terminal:

```bash
cd mock_app
python3 app.py
```

Leave this running. It serves at `http://localhost:5001`.

### Running without the live mock app

The full `pytest` suite does **not** require you to start the mock app
yourself — `tests/test_web_surface_live.py` and `tests/test_replay_live.py`
each spin up their own throwaway copy of it in a background thread for the
duration of the test, then tear it down. Every other test is pure logic
(policy, redaction, schema, replay engine, escalation mechanics) exercised
against fakes, with no live service and no network calls at all. Only the
scripts in `scripts/` (the actual demo path below) need the mock app running
separately, since they're meant to be watched running against a real,
visible browser.

### Run the test suite

```bash
pytest tests/ -v
```

All tests should pass (~72 at last count). This is the single best way to
confirm your setup is correct before running anything live.

## 2. Demo path

This is the exact sequence that exercises the full through-line the project
is built around: **a goal → a genuine LLM-driven discovery run → a saved
capability artifact → deterministic replay of that artifact, including an
error case.** The mock app must be running (see above) for all of these.

### Step 1 — A real, LLM-driven discovery run

```bash
python3 scripts/run_discovery.py
```

Opens a real (visible) Chromium window and drives it using live Anthropic API
calls to accomplish the goal "Look up member 12345 and read their current
savings balance." Saves the full trace and evidence (screenshots, a
structured JSONL log) to `evidence/discovery_balance_lookup/`.

### Step 2 — Emit an artifact from that run, then replay it deterministically

```bash
python3 scripts/emit_and_replay_from_discovery.py
```

Converts the trace from Step 1 into a real `Capability` artifact (no LLM
involved in this conversion), saves it to
`artifacts/member_read_savings_balance_agent_generated.json`, then replays it
**twice** with no model in the loop: once with a valid member ID (succeeds,
extracts the real balance) and once with an unknown one (fails — this
specific artifact never learned to recognize "member not found" as a
business outcome, since it only ever saw the happy path during discovery;
see `REPORT.md`, Cuts). Evidence for both replays is saved to
`evidence/replay_agent_generated_artifact/`.

### Step 3 — A hand-curated artifact that *does* handle the error cleanly

```bash
python3 scripts/build_balance_lookup_artifact.py
python3 scripts/run_replay_evidence.py
```

The first command builds and saves the hand-written version of the same
capability (`artifacts/member_read_savings_balance.json`), which **does**
declare a `MEMBER_NOT_FOUND` outcome. The second replays it twice the same
way — this time the "unknown member" case comes back as a clean business
outcome, not a failure, demonstrating the difference a properly curated
(vs. freshly auto-generated) artifact makes. Evidence saved to
`evidence/replay_success/` and `evidence/replay_business_outcome_not_found/`.

### Step 4 — Human escalation: an approval gate

```bash
python3 scripts/build_subaccount_artifact.py
python3 scripts/demo_approval_escalation.py
```

Replays a capability that reaches a genuinely irreversible step (opening a
sub-account). When it gets there, the run pauses and prints a URL
(`http://localhost:5050`) — open it in your browser to see the pending
action, the live screenshot, and Approve/Reject buttons. Approving lets the
same run continue and complete; rejecting stops it cleanly. Evidence
(including the persisted intervention request and its resolution) saved to
`evidence/demo_approval_escalation/`.

### Step 5 — Human escalation: a live takeover

```bash
python3 scripts/demo_takeover_escalation.py
```

Replays the agent-generated artifact from Step 2 with a deliberately unknown
member ID, which fails and pauses for a human takeover rather than just
erroring out. Follow the terminal instructions: operate the **visible browser
window** yourself to find a real member, then open the operator console and
click Resume. The same run then retries the failed step and completes
successfully — because you fixed it. (This demo's limitations are stated
explicitly in its own output and in `REPORT.md`, Escalation & Handoff.)

## 3. Project structure

```
mock_app/            the target application (deliberately legacy-styled, with error injection)
src/
  surfaces/           Surface abstraction: WebSurface (Playwright), DesktopSurface (design stub), targeting
  artifact/           the Capability schema (Pydantic), the emitter, hand-written examples
  agent/              the LLM discovery loop
  replay/             the deterministic replay engine
  safety/             policy engine and redaction
  evidence/           structured JSONL logging
  escalation/         session lease, intervention persistence, the operator console
scripts/              runnable demo/build scripts (see Demo path above)
artifacts/            saved capability JSON files
evidence/             logs, screenshots, and intervention records from real runs
tests/                the full test suite
policy.yaml           the safety policy (allowlist, blocklist, risk classification)
REPORT.md             the design write-up
```