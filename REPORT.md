# Design Report

## 1. Architecture

The system is a single Python process orchestrating a layered pipeline, not a
set of services — appropriate for this scope, where the brief explicitly
warns against building scaling infrastructure prematurely.

**The core seam is the `Surface` abstraction**: `observe()`, `act()`,
`element_visible()`, `current_url()`. Everything above it — the discovery
agent, the replay engine, the escalation layer — only ever talks to this
interface and never knows whether it's driving a browser, a legacy web app,
or (per the stub below) a desktop window. `WebSurface` implements it via
Playwright; `DesktopSurface` is a documented, unimplemented stub proving the
boundary holds (Section 4).

**Perception is accessibility-tree based**, not raw HTML and not
screenshot-only. Two reasons: it's dramatically more compact and meaningful
for legacy markup (a 50KB nested-table page becomes a few hundred characters
of roles and names), and accessibility roles/names exist on native desktop
apps too — a `RoleNameLocator("button", "Search")` means the same thing
whether resolved against a DOM or a Win32 window, which is the entire
argument for why the desktop extension story (Section 4) is credible rather
than aspirational.

**Discovery and replay are symmetric consumers of the same `Surface`**,
including the same safety and escalation wrapper (`EscalatingSurface`, a
decorator around any inner `Surface`). This was a deliberate refactor: an
earlier version embedded lease-checking directly in `WebSurface`; moving it
to a generic wrapper meant the identical mechanism gates both the LLM agent's
actions and the deterministic replay engine's actions, tested once against a
fake surface rather than duplicated and tested twice.

**Trade-off accepted**: there is no long-lived "platform" process managing
concurrent sessions or a credential vault — each demo script is a
self-contained run. A real deployment would need that; building it here
would be exactly the "scaling infrastructure" the brief says not to reward.

## 2. Artifact schema

`Capability` is the top-level artifact: `capability_id`, `version`,
`description`, `app_profile` (vendor/product/version — the multi-tenant
anchor, Section 4), `approval_state` (`draft`/`approved`, gating unattended
replay), typed `inputs`, typed `outputs`, ordered `steps`, declared
`outcomes`, `recoveries`, and a final `checkpoint`.

**One shared `Condition` vocabulary** (`text_present`, `element_visible`,
`url_matches`, `all_of`) is reused in four places: a step's postcondition, an
outcome's detector, a recovery's trigger, and the final checkpoint. This
avoided inventing four similar-but-different mini-languages for "check
something about the current state."

**`TargetDescriptor`** is a ranked list of locator strategies (role+name,
row-label, text-exact), tried in order. Which strategy actually resolved is
recorded at runtime (`resolved_via`) — this is the practical drift signal: if
strategy 1 stops working and strategy 3 starts being needed across many
invocations, that's observable without a human noticing by accident.

**`ValueSource`** (`literal` vs. `param`) is the actual parameterization
mechanism — it's what turns a recorded transcript into a callable capability
rather than a fixed macro.

**Pydantic, not dataclasses**: the same `TargetDescriptor`/`Step`/`Condition`
objects the live agent resolves against are what gets serialized into the
saved artifact — no separate storage representation to keep in sync.
Discriminated unions (a `kind` tag on each variant) make this round-trip
through JSON cleanly, tested explicitly.

**Deliberate restrictions, tested, not just stated**: artifacts store
relative paths only, never an absolute origin (the origin is tenant config
supplied at replay time — Section 4), and never credentials (a capability
assumes it starts on an already-authenticated session; login is handled
once, outside any artifact, by the calling harness). A unit test asserts
`"password" not in artifact_json` and `"http://" not in artifact_json`.

**Capability composition**: one capability's assumed starting point can be
another's natural ending point. The balance-lookup capability assumes an
authenticated session on `/search`; the sub-account-confirm capability
assumes it's already on a specific member's detail page. Neither ever needs
to know how to log in.

## 3. Determinism & error handling

Replay resolves targets through the identical ranked-strategy mechanism the
live agent uses — same code path, same `WebSurface._resolve()`.

**Three-way result contract**, tested for all three branches: `success`
(typed outputs), `business_outcome` (a declared code plus a success flag,
e.g. `MEMBER_NOT_FOUND`), `failed` (step id, expected, observed, an evidence
reference). Outcomes are checked **after every step**, not only on action
failure — a "member not found" result doesn't make the triggering click
itself fail (the page just renders different content), so checking only on
exception would miss it entirely. This is exactly the failure mode the brief
calls the most common design mistake here.

**Approval-state gating**: a `draft` capability refuses unattended replay
unless the caller explicitly passes `allow_draft=True` — a fail-safe default,
not an afterthought.

**Real bugs found and fixed while building this**, kept here as evidence the
system was actually exercised, not just designed:

- *Nested-table ambiguity.* `get_by_role("row", name="Savings Balance")`
  matched the intended row **and** several ancestor rows, because an
  accessible container's name absorbs its descendants' text in deeply nested
  legacy markup. Fixed by anchoring on the specific `rowheader` role and
  walking structurally to its sibling cell, rather than matching a row by an
  inherently ambiguous concatenated name.
- *A removed Playwright API.* `page.accessibility.snapshot()` no longer
  exists in current Playwright; migrated to `aria_snapshot()`, which turned
  out to be a strictly better fit (a readable string, no manual tree-walking
  needed).
- *A silently non-self-contained artifact.* An agent run that happened to
  already be on the right page never emitted a `navigate` step, so the
  resulting artifact implicitly assumed replay always starts from wherever
  that one recording began — false in general. Fixed by having the emitter
  always prepend a synthetic `navigate` to the run's recorded starting URL,
  unless the agent already included one itself.
- *Risk classified at the wrong moment.* Classifying a click's risk by the
  *current* page URL is wrong, because a click's current page is never its
  destination (the confirm button lives on `/confirm` and submits to
  `/submit` — you're never "on" `/submit` until after the click). Path-based
  `target_overrides` could therefore never fire for a real click. Fixed by
  also classifying by the target's accessible **name**, which is what's
  actually being interacted with regardless of page timing.

## 4. Heterogeneity & multi-tenant

**The `Surface` boundary is the whole story.** `WebSurface` and the
`DesktopSurface` stub implement an identical four-method contract. The stub's
docstring states precisely what would change (an observe/act implementation
backed by Windows UI Automation or macOS Accessibility, instead of
Playwright) and precisely what wouldn't (the agent loop, the replay engine,
the artifact schema, the policy engine — none of them know or care which
`Surface` they're holding).

**Legacy web is already handled**, not theoretical — the mock app's nested
tables and absent test IDs are the actual hostile case Section 1 describes.
A genuine frameset/iframe surface would need one more `Locator` variant (a
frame-path strategy); the targeting schema's discriminated-union shape means
adding that is additive, not a restructuring. Not built here — the mock app
expresses legacy hostility through table nesting rather than literal frames.

**Multi-tenant reuse** is anchored on `app_profile` (vendor/product/version).
Two tenants running the same underlying vendor product share an
`app_profile` and are candidates for reusing one capability rather than
re-recording per tenant. A per-tenant difference (a relabeled field, a moved
button) would be expressed as a small overlay — a patch referencing the base
`capability_id`/`version` plus a list of target or step overrides — never a
forked copy. This overlay type is designed (here) but not implemented, per
the brief's own scope note that multi-tenant support need not be built.

**What's actually built, not just designed, toward this**: artifacts store
relative paths exclusively, with the origin supplied by tenant configuration
at replay time — tested, not aspirational. And the recorded `resolved_via`
field is a real, already-working drift signal: a shift from strategy 1 to
strategy 3 across many replays of the same capability is exactly the kind of
per-tenant/version drift Section 3.7 asks how to detect.

## 5. Escalation & handoff

**Two kinds of intervention, because they need different things from a
human.** A "takeover" means the agent or replay is genuinely stuck and a
human must operate the live browser themselves. An "approval" means one
specific pending action is classified risky, and the human only needs to say
yes or no — the automation still performs the action itself, only after a
green light.

**The lease is a real `threading.Event`**, not a flag anyone could ignore:
`SessionController.assert_agent_turn()` is the chokepoint every action passes
through before acting, tested with genuine concurrent threads (one blocks, a
separate thread resolves it, the first thread wakes with the correct
payload) — not mocked.

**`EscalationManager`** persists the full context (capability, goal, step,
current screenshot and accessibility tree, reason, and — for an approval —
the exact proposed action) to `evidence/interventions/` *before* blocking,
and persists the resolution separately afterward. Both pass through the same
redaction pipeline used everywhere else in the system.

**`EscalatingSurface`** is a decorator wrapping any inner `Surface`. It is
what lets one mechanism gate both the discovery agent and the replay engine
without duplicating logic — and it's where the risk-by-name bug fix above
actually lives.

**Detection and resume, concretely:**
- *Discovery agent*: stuck is a repeated identical observation hash across
  several turns. On escalation, once a human resolves it, the agent
  re-observes and folds the fresh state into the existing tool-result
  message (appending a brand-new `user`-role message would violate the API's
  alternating-role requirement) and **continues the same run** — proven by a
  test where the run actually completes the goal after a simulated human fix.
- *Replay engine*: any hard step failure escalates, and after a human
  resolves it, the engine **retries the exact same failed action once**
  before accepting it as a genuine failure.

**Demonstrated live, twice**, with evidence in `evidence/`: an approval gate
on the sub-account's irreversible confirm step (a genuine business judgment
call), and a takeover triggered by a replay failure. The takeover demo is
deliberately caveated, in its own printed output and here: the specific
failure is engineered and reproducible on demand (an agent-generated
artifact that never learned a `MEMBER_NOT_FOUND` outcome, from Section 3,
because it only ever observed the happy path), chosen for reliability of
demonstration — **not** presented as a realistic reason a human would be
needed. A properly curated capability wouldn't need a human for that case at
all. Genuinely realistic takeover triggers (an unhandled native confirmation
dialog, an error state with no learned response) are supported by the same
mechanism but not exercised live, since the current retry-the-same-action
design doesn't cleanly express "the human did something different, now
continue" without a small extension (Section 7).

## 6. Safety

**Three independent layers, one chokepoint.** Every surface implementation
calls through a single `PolicyEngine`: (1) an origin + path allowlist
checked at navigate time; (2) an explicit path blocklist checked *before*
the allowlist, so a block can never be silently overridden by a loose allow
pattern; (3) risk classification (`safe` / `requires_approval` / `blocked`)
by generic action type, overridable by target — by path for navigation, by
accessible name for clicks (Section 5's fix).

**Fail-safe default**: an action type or target nobody classified defaults
to `requires_approval`, not `safe`. Adding a new action and forgetting to
classify it stops for human review rather than silently proceeding.

**Redaction, two independent mechanisms, one call site.** Sensitive field
*names* (password, ssn, token, …) are redacted regardless of value; sensitive
*shapes* (an SSN pattern, a credit-card-length digit run, an API key prefix,
a bearer token) are redacted regardless of field name, catching a value that
ends up somewhere with an innocent-looking key. Deliberately biased toward
over-redaction — the credit-card-shaped pattern is loose enough to
occasionally mask a harmless long number, which for regulated financial data
is a far smaller cost than a false negative. All of it runs through one
function, called once, inside `EvidenceLogger.log()` — no caller needs to
remember to redact.

**Credentials never reach three places**: the LLM (the harness authenticates
before the agent loop starts — the model never sees a password), any log (the
`EvidenceLogger` isn't even constructed until after login completes in the
demo scripts), or any saved artifact (tested explicitly, Section 2).

**Limits, stated plainly rather than glossed over:**
- Policy is a static YAML file. Classifying a newly-discovered risky action
  requires a human to edit it and redeploy — reasonable at this scope, not a
  story that scales unmodified to hundreds of tenants.
- The name-based target override is an **exact** match. A tenant that
  cosmetically relabels "Confirm and Open Account" to "Confirm" would
  silently stop matching the override and fall back to the generic
  action-type risk (`safe`, for a click) — a real blind spot, not merely a
  theoretical one, since it's a *silent* match failure rather than an
  unclassified action correctly defaulting to caution.
- Redaction is pattern/name based, not semantic. Sensitive free text with
  neither a recognizable field name nor a recognizable shape could slip
  through.

## 7. Cuts

**Outcomes and recoveries are never auto-populated by discovery.** A single
successful run only ever observes the happy path; an emitted artifact starts
with both empty, requiring a human reviewer — or a second, deliberately
adversarial discovery run — before promotion to `approved`. Demonstrated
honestly rather than hidden: the live replay of the agent-generated artifact
genuinely fails on an unknown member, for exactly this reason.

**Not implemented, explicitly out of scope per the brief**: `DesktopSurface`
(a documented stub only) and `CapabilityOverlay` (designed in Section 4, no
second tenant variant exists to replay against).

**Smaller, real gaps:**
- `TextExactLocator` exists in the targeting vocabulary for completeness;
  nothing currently drives the agent or emitter to choose it.
- No frame-path locator strategy for a literal frameset/iframe surface — the
  mock app's hostility is nested tables, not frames.
- The escalation retry model re-attempts the *same* failed action once; it
  doesn't yet support a human's *different* corrective action (dismissing a
  dialog, say) being incorporated before the engine continues with the next
  step. The schema's `Recovery.action` field anticipates this; it isn't
  wired into the live escalation path.
- Evidence screenshots are taken liberally — on every `observe()` call,
  specifically so outcomes are caught as early as possible — which
  occasionally produces near-duplicate frames when nothing visibly changes
  between two checks in a row. Cosmetic, not a correctness issue.
- No multi-run stability scoring, and no agent-facing capability catalog
  (though the schema's typed inputs/outputs are already shaped like a
  function signature, so this would be a thin wrapper, not a redesign).

**What I'd build next, in priority order**: (1) a second, deliberately
adversarial discovery run per capability, specifically targeting known error
states, to auto-populate outcomes rather than relying solely on manual
curation; (2) wire `Recovery.action` into the live escalation path so a
human's corrective action — not just a bare retry — can be incorporated;
(3) a `CapabilityOverlay` resolver plus a second, re-skinned tenant-variant
mock app, to prove cross-tenant reuse for real rather than only in design;
(4) a frame-path locator strategy against a genuine frameset page.