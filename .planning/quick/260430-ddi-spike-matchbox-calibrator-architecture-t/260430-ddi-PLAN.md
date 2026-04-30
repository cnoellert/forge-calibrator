---
quick_id: 260430-ddi
mode: quick
type: execute
wave: 1
depends_on: []
files_modified:
  - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md
  - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md
  - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-2.md
  - .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md
autonomous: false
requirements:
  - SPIKE-01-PathA-action-expression-pixel-sampling
  - SPIKE-02-PathB-matchbox-uniform-readback
  - SPIKE-03-snapshot-tool-from-python
must_haves:
  truths:
    - "PROBE.md states for each of the three probes: WORKED / DIDN'T-WORK / PARTIAL"
    - "Each probe finding is backed by a verbatim bridge transcript excerpt (request + response)"
    - "Bridge transcripts for each probe are saved under transcripts/ in this quick-task dir"
    - "PROBE.md contains a recommendation matrix tying findings to architectural paths (A / B / Snapshot)"
    - "PROBE.md ends with a 'Next planning step' callout naming the path(s) to plan next"
    - "If forge-bridge is dead or no Flame session exists, PROBE.md cleanly aborts with a 'human-in-the-loop required' note instead of fabricating findings"
    - "No production code outside .planning/quick/260430-ddi-... is modified"
  artifacts:
    - path: ".planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md"
      provides: "Findings document with three-probe results table, evidence excerpts, recommendation matrix, next-step callout"
      contains: "Probe 1, Probe 2a, Probe 2b, Probe 3, Recommendation Matrix, Next Planning Step"
    - path: ".planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md"
      provides: "Verbatim /exec request bodies + response JSON for Probe 1 (Action expression pixel sampling)"
    - path: ".planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-2.md"
      provides: "Verbatim /exec request bodies + response JSON for Probe 2a (live readback) and Probe 2b (save-required)"
    - path: ".planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md"
      provides: "Verbatim /exec request bodies + response JSON for Probe 3 (snapshot tool API search)"
  key_links:
    - from: "PROBE.md findings table"
      to: "transcripts/probe-{1,2,3}.md"
      via: "explicit citation/link per finding row"
      pattern: "transcripts/probe-"
    - from: "PROBE.md recommendation matrix"
      to: "Path A / Path B / Snapshot architectural options"
      via: "viable / blocked / partial verdict for each path"
      pattern: "Path [AB]|Snapshot"
---

<objective>
Run three independent feasibility probes against a live Flame 2026.2.1 session via forge-bridge, document the findings in PROBE.md with verbatim bridge transcripts as evidence, and produce a recommendation matrix that names which architectural path(s) for the matchbox calibrator are viable for follow-on planning.

Purpose: We are about to commit planning effort to one of three calibrator architectures (Action-expression pixel sampling, Python-driven matchbox uniform readback, or snapshot-tool-as-frame-source). Each rests on a Flame API assumption that has never been verified end-to-end. This spike answers those three questions with primary-source evidence so the next planner is not guessing.

Output:
- `260430-ddi-PROBE.md` — single findings document with results table, recommendation matrix, and next-step callout
- `transcripts/probe-{1,2,3}.md` — verbatim /exec call+response logs (the "show your work" trail)
- No source code changes outside `.planning/quick/260430-ddi-...`
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md

# Memory crumbs (REQUIRED reading — these encode hard rules that prevent crashes)
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/MEMORY.md
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_probing.md
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_repl_contract.md
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_qt_main_thread.md
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_capture_pattern.md
@/Users/cnoellert/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_export_iteration_crash.md

# The matchbox under probe
@matchbox/CameraMatch.xml
@matchbox/CameraMatch.1.glsl

<bridge_contract>
forge-bridge `/exec` (POST http://127.0.0.1:9999/exec) — current contract:

  Payload:   {"code": "<python source>"}
  Headers:   Content-Type: application/json
  Response:  {"result": "<repr of last expression>", "stdout": "...", "stderr": "...", "error": null|str, "traceback": null|str}

Hard rules (violating any of these crashes Flame and ends the spike):
  R1. REPL semantics — last bare expression's repr() becomes `result`. Setting `_result = ...` does NOT propagate. End every code body with a bare expression that names what you want returned.
  R2. One probe per /exec call — never bundle three introspections in one request; if it crashes you can't tell which call did it.
  R3. NO QDialog / QWidget / QApplication.exec() calls reachable from any /exec invocation. The bridge runs off-main-thread and any modal Qt UI from a worker thread is a hard SIGSEGV on macOS. This rules out anything that opens the calibrator UI, an error dialog box, etc.
  R4. NO iteration over many (Action, Camera) FBX export pairs in one /exec — bridge SIGSEGVs on selection thrashing. (Not relevant to this spike, but stay alert if introspection accidentally triggers it.)
  R5. If a probe SIGSEGVs (no envelope returned, curl times out), STOP, save what you learned to PROBE.md immediately, ask the user to restart Flame, and document the crash itself as the finding for that probe. Do not retry the same call without changing strategy. After two consecutive crashes, abort the spike with the partial findings written down.
  R6. For Probe 2 specifically — if any save call is required, scope the work to a throwaway batch group (`flame.batch.create_batch_group(...)`) so the user's open work is never touched. NEVER call `flame.batch.save()` (or whatever the save API turns out to be) on the user's primary batch.
</bridge_contract>

<probe_specs>
**Probe 1 — Path A: Action expression pixel sampling**
  Question:  Can a Flame Action camera attribute (e.g., `pos_x`) be expression-linked to read a known pixel value from an upstream node's output?
  Setup:     Have the user wire `Clip → Matchbox(CameraMatch) → Action` in a throwaway batch group. The matchbox already pixel-encodes `cam_pos` at output (0,0) (see `matchbox/CameraMatch.1.glsl` lines 244-252). User then opens the Action camera's expression editor on `pos_x`.
  Investigation steps (in priority order):
    1.1  Search Flame's bundled docs/help paths for an expression reference. Try (read-only, via Bash, NOT bridge):
           ls /opt/Autodesk/flame_*/doc 2>/dev/null
           ls /opt/Autodesk/flame_*/help 2>/dev/null
           find /opt/Autodesk -maxdepth 4 -iname "*expression*" 2>/dev/null
           find /opt/Autodesk -maxdepth 4 -iname "*scripting*manual*" 2>/dev/null
         Document what you find. If a manual lists pixel-sampling syntax, copy the relevant excerpt.
    1.2  Via bridge, introspect attribute expression API (one probe per call):
           import flame; type(flame.batch).__mro__   # PyBatch class info
           [m for m in dir(<a PyAttribute>) if 'expr' in m.lower() or 'link' in m.lower()]
         Look for: set_expression / setExpression / get_expression / link methods.
    1.3  HUMAN-IN-THE-LOOP step: ask the user (via the checkpoint at the end of this task) to attempt entering candidate expression syntaxes into Flame's animation/expression editor on the Action camera's pos_x attribute. Candidates to try (record each verbatim with the resulting error or success):
           pixel(<upstream_node>, 0, 0).r
           sample(<upstream>, 0, 0).x
           <upstream>.pixel(0,0).r
           <upstream>[0,0].r
         Plus any syntax surfaced by step 1.1. The user reports back what worked / what error message they got.
  Possible outcomes:
    WORKED       — record the exact expression syntax + a screenshot path or transcribed value showing the Action camera's pos_x updates when the matchbox solve changes
    DIDN'T-WORK  — record the candidate syntaxes tried + the error messages Flame produced
    PARTIAL      — works only with caveats (e.g., requires manual refresh, only on render not interactive, crashes on Action recompute)

**Probe 2 — Path B: Matchbox uniform readback**
  Question:  Can matchbox `out_*` uniform values set from Python be read back via Python? Live (no save) or save-required?
  Setup:     Same throwaway batch group as Probe 1, with the CameraMatch matchbox already inserted.
  Investigation steps:
    2.1  Discover the matchbox node's wrapper class. Via bridge (one call each):
           import flame; mb = next(n for n in flame.batch.nodes if 'CameraMatch' in (n.name.get_value() if hasattr(n.name,'get_value') else str(n.name)) or 'Matchbox' in type(n).__name__)
           type(mb).__name__
           [a for a in dir(mb) if not a.startswith('_')]
         Note: the actual matchbox node type may be PyMatchboxNode, PyShader, PyMatchbox, or something else. Discover empirically.
    2.2  Find the uniform accessor:
           hasattr(mb, 'parameters'), hasattr(mb, 'attributes'), hasattr(mb, 'uniforms')
           [a for a in dir(mb) if 'param' in a.lower() or 'unif' in a.lower()]
         Look for a dict-like or attribute-list interface keyed by uniform name (e.g., `out_pos_x`).
    2.3  PROBE 2a — LIVE READBACK (optimistic path):
           Set a known sentinel value via the discovered API (e.g., `mb.parameters['out_pos_x'].set_value(42.0)` — adapt to actual API).
           In a SEPARATE /exec call (per R2), read it back: `mb.parameters['out_pos_x'].get_value()`.
           If equal to 42.0 → LIVE-READABLE. Done. Skip 2b.
           If readback is None / 0.0 / unchanged → save is suspected required, fall through to 2b.
    2.4  PROBE 2b — SAVE-REQUIRED (only if 2a fails):
           Discover the save API: [a for a in dir(flame.batch) if 'save' in a.lower()]
           Confirm we are inside a throwaway `create_batch_group(...)` (R6) — abort and ask the user to switch if not.
           Set sentinel → call save → read back. Time the round-trip with `time.perf_counter()`.
           If it now reads 42.0 → SAVE-REQUIRED + record latency.
           If still doesn't read → NOT-READABLE.
    2.5  CAPTURE-ON-CALL (defensive — apply ONLY for the actual set_value/save/read sequence in 2a/2b):
         If the Probe 2 exploratory introspection feels stable, you can skip the capture-on-call wrappers. If anything in 2a/2b feels risky (unfamiliar API surface, ambiguous wrapper type), monkey-patch the discovered set/get methods in the bridge namespace to log inputs to `~/forge_diag/probe2_capture/` BEFORE running the risky call. Pattern reference: `memory/flame_bridge_capture_pattern.md`.
  Possible outcomes:
    LIVE-READABLE   — Path B has no save constraint; record the exact API surface (class + method names)
    SAVE-REQUIRED   — Path B works but with friction; record save API + round-trip latency
    NOT-READABLE    — Path B is dead; record what was tried and how it failed
    DISCOVERY-BLOCKED — couldn't even find the wrapper class or uniform accessor; record the dir() output verbatim

**Probe 3 — Snapshot tool from Python**
  Question:  Is there a Python entry point to invoke Flame's player snapshot button, and if so, what does it produce?
  Investigation steps (all read-only via bridge — one probe per call):
    3.1  Search Flame's Python module surface:
           import flame; [a for a in dir(flame) if 'snap' in a.lower() or 'capture' in a.lower() or 'still' in a.lower()]
           [a for a in dir(flame.batch) if 'snap' in a.lower() or 'capture' in a.lower() or 'still' in a.lower()]
           import flame; hasattr(flame, 'execute_shortcut')
    3.2  If 3.1 surfaces a candidate, read its docstring:
           repr(flame.<thing>.__doc__)         # NEVER call help() — bridge has crashed on it before
    3.3  Search Flame's installed help/scripts for "snapshot":
           grep -rli 'snapshot' /opt/Autodesk/flame_*/python 2>/dev/null | head -20
           grep -rli 'snapshot' /opt/Autodesk/flame_*/lib/python* 2>/dev/null | head -20
         (Bash, NOT bridge — these are filesystem reads.)
    3.4  If a callable is found, attempt invocation in the throwaway batch group with the player parked on a known frame. Record:
           - return value (path? bool? None?)
           - filesystem side-effects (where did the snapshot land — search recently-modified DPX/EXR/JPG under common Flame export roots like `/var/tmp/Autodesk`, `~/Movies/Autodesk`, project's DEFAULT_EXPORT path)
           - file format + bit depth + color space (use `file <path>` and `oiiotool --info <path>` if available, else `dpxinfo` or just byte-header inspection)
           - relationship to player position (does it match the currently parked frame?)
  Possible outcomes:
    FOUND          — record API surface, output path pattern, format, color space, timing semantics
    NOT-FOUND      — record everything that was searched (API surface dump + grep results) so the next planner can verify the search was thorough
    PARTIAL        — found something close (e.g., shortcut-only, or only via a deprecated module), record limitations

**Optional Probe 4 — Cross-probe state**
  Goal: Establish whether running probes 1/2/3 in the same Flame session corrupts state. The required ordering already does this implicitly — note in PROBE.md whether any probe required a Flame restart to keep going. If yes, that itself is a finding.
</probe_specs>

<probe_md_skeleton>
The final PROBE.md MUST follow this skeleton (exact section headings — downstream tools may grep for them):

```
# 260430-ddi-PROBE — Matchbox Calibrator Architecture Spike

## Pre-flight
- forge-bridge alive: YES / NO  (curl 1+1 result: ...)
- Flame session running: YES / NO
- Throwaway batch group used: <name>
- Started: <ISO timestamp>
- Aborted (if applicable): <reason>

## Findings Table

| Probe | Path     | Verdict        | Evidence | Notes |
|-------|----------|----------------|----------|-------|
| 1     | A (expr) | WORKED / DIDN'T-WORK / PARTIAL | [transcripts/probe-1.md](transcripts/probe-1.md) | <one-line> |
| 2a    | B (live) | LIVE-READABLE / FAILED         | [transcripts/probe-2.md](transcripts/probe-2.md) | <one-line> |
| 2b    | B (save) | SAVE-REQUIRED / NOT-READABLE / N/A | [transcripts/probe-2.md](transcripts/probe-2.md) | <one-line> |
| 3     | Snapshot | FOUND / NOT-FOUND / PARTIAL    | [transcripts/probe-3.md](transcripts/probe-3.md) | <one-line> |
| 4     | Session  | CLEAN / DEGRADED               | (inline)                                       | <one-line> |

## Probe 1 — Path A: Action Expression Pixel Sampling
### Setup
### Steps Run (with verbatim bridge excerpts)
### Result
### Verdict: <WORKED | DIDN'T-WORK | PARTIAL>

## Probe 2 — Path B: Matchbox Uniform Readback
### 2a — Live readback
### 2b — Save-required (if applicable)
### Verdict: <LIVE-READABLE | SAVE-REQUIRED | NOT-READABLE | DISCOVERY-BLOCKED>

## Probe 3 — Snapshot Tool
### Search Surface Covered
### Candidate(s) Found
### Invocation Result
### Verdict: <FOUND | NOT-FOUND | PARTIAL>

## Recommendation Matrix

| Architectural Path                        | Status from this spike | Recommended? | Rationale |
|-------------------------------------------|------------------------|--------------|-----------|
| Path A — Action expression on matchbox px |                        |              |           |
| Path B — Python-driven uniform readback   |                        |              |           |
| Snapshot — replace Wiretap as frame src   |                        |              |           |

## Next Planning Step
<one paragraph: which path(s) the next planner should pursue, and which to drop. If all three are blocked, name what would unblock them.>

## Memory Crumb Candidates
<list any findings durable enough to warrant a new memory crumb. If none, say "None — all findings are situational and live in this PROBE.md only.">
```
</probe_md_skeleton>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Pre-flight + Probe 1 (Action expression pixel sampling)</name>
  <files>
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md,
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md
  </files>
  <action>
**Pre-flight (mandatory; abort cleanly on failure):**
1. Create `transcripts/` subdir if it doesn't exist:
     mkdir -p .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts
2. Initialize PROBE.md with the skeleton from `<probe_md_skeleton>` above (Pre-flight section + empty Findings Table rows + empty per-probe sections). Stamp the start ISO timestamp.
3. Bridge ping (Bash):
     curl -sS -m 5 -X POST http://127.0.0.1:9999/exec -H "Content-Type: application/json" -d '{"code": "1+1"}'
   Append the verbatim request + response to transcripts/probe-1.md under a "## Pre-flight" section.
   - If curl fails (exit 7 / timeout / connection refused) OR response `result` is not `"2"`: write "ABORTED — forge-bridge not reachable" to PROBE.md Pre-flight section, list the exact recovery steps the user needs (start Flame, confirm forge-bridge subprocess is running, retry `/gsd-quick`), and STOP this task. Do not proceed to Probe 1.
4. Confirm Flame session has a batch open:
     curl -sS -X POST http://127.0.0.1:9999/exec -H "Content-Type: application/json" -d '{"code": "import flame; bool(flame.batch)"}'
   If `result` is not `"True"` or returns an error, write "ABORTED — no batch open" to PROBE.md and STOP.
5. Confirm a clip + a CameraMatch matchbox + an Action exist in the user's batch (this is the prerequisite for Probe 1's pixel-sampling test). If not, surface a checkpoint to the user asking them to wire the chain, then resume.

**Probe 1 execution (only if pre-flight passed):**
6. Filesystem search for Flame expression docs (Bash; record output verbatim in transcripts/probe-1.md under "## Step 1.1 — Doc search"):
     ls -la /opt/Autodesk/flame_*/doc 2>&1 | head -50
     ls -la /opt/Autodesk/flame_*/help 2>&1 | head -50
     find /opt/Autodesk -maxdepth 4 -iname "*expression*" 2>/dev/null | head -30
     find /opt/Autodesk -maxdepth 4 -iname "*scripting*manual*" 2>/dev/null | head -30
   If any doc references pixel/sampler expression syntax, transcribe the relevant excerpt into transcripts/probe-1.md.
7. Bridge introspection — one /exec per call, full request+response logged to transcripts/probe-1.md (R1, R2):
   - 7a. List PyAttribute methods on a real Action camera attribute, looking for expression hooks:
          import flame
          act = next((n for n in flame.batch.nodes if type(n).__name__.startswith('PyAction')), None)
          cam = act.nodes[0] if act else None
          attr = cam.position[0] if cam else None
          [m for m in dir(attr) if 'expr' in m.lower() or 'link' in m.lower() or 'connect' in m.lower()]
   - 7b. If 7a surfaces a candidate (e.g., set_expression / setExpression), read its docstring:
          repr(type(attr).set_expression.__doc__)   # adapt to actual method name; NEVER use help()
   - 7c. List flame module-level expression utilities:
          import flame; [a for a in dir(flame) if 'expr' in a.lower()]
8. Surface a HUMAN-IN-THE-LOOP checkpoint (see Task 4) so the user can attempt the candidate expression syntaxes in Flame's animation/expression editor on the Action camera's `pos_x`. The user reports back which syntax (if any) accepted and whether `pos_x` updates when the matchbox solve changes. Record verbatim in transcripts/probe-1.md.
9. Write the Probe 1 section of PROBE.md with verdict (WORKED / DIDN'T-WORK / PARTIAL), evidence summary, and link to transcripts/probe-1.md. Update the Findings Table row.

**Crash-handling (R5):** If any /exec call returns no envelope (curl timeout / connection drop), immediately:
  - Write "Probe 1 SIGSEGV — see transcripts/probe-1.md" to PROBE.md verdict row
  - Record everything captured so far into transcripts/probe-1.md
  - Mark Probe 1 verdict as DIDN'T-WORK with rationale "bridge SIGSEGV during introspection"
  - Ask the user to restart Flame and confirm before continuing to Task 2 (this is itself a Probe 4 finding — record it in the cross-probe-state section of PROBE.md)
  </action>
  <verify>
    <automated>test -f .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && test -f .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md && grep -q "## Probe 1" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && grep -qE "Verdict: (WORKED|DIDN'T-WORK|PARTIAL|ABORTED)" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md</automated>
  </verify>
  <done>
    PROBE.md exists with skeleton populated through Probe 1. transcripts/probe-1.md contains verbatim request/response for every /exec call made. PROBE.md Findings Table row 1 has a verdict. If pre-flight failed, PROBE.md cleanly states "ABORTED" with recovery steps and the task stops there (still a successful task — clean abort > fabricated finding).
  </done>
</task>

<task type="auto">
  <name>Task 2: Probe 2 (Matchbox uniform readback) + Probe 3 (Snapshot API)</name>
  <files>
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-2.md,
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md,
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md
  </files>
  <action>
**Precondition:** Task 1 completed without ABORTED status. If Task 1 ABORTED on pre-flight, skip this task and go straight to Task 4 to finalize PROBE.md with the abort summary.

**R6 GUARDRAIL — required first move for Probe 2:**
Before any uniform-set call, confirm the work is happening inside a throwaway batch group, not the user's primary batch. One /exec call:
  import flame
  bg_name = flame.batch.name.get_value() if hasattr(flame.batch.name, 'get_value') else str(flame.batch.name)
  bg_name
Log to transcripts/probe-2.md. If the batch group looks like the user's real work (not obviously a "forge_probe_*" or similar throwaway), surface a checkpoint asking the user to either (a) create a throwaway batch group via `flame.batch.create_batch_group("forge_probe_2")` and switch to it, or (b) confirm explicitly that they accept the risk of save calls touching this batch. Do NOT proceed without one of those.

**Probe 2 execution:**
1. Step 2.1 — discover the matchbox wrapper class. Three /exec calls (R2):
   - 2.1a: list batch nodes and identify the CameraMatch matchbox:
        import flame
        nodes = list(flame.batch.nodes)
        [(n.name.get_value() if hasattr(n.name,'get_value') else str(n.name), type(n).__name__) for n in nodes]
   - 2.1b: pick the matchbox node (adapt the predicate to whatever 2.1a shows):
        mb = next(n for n in flame.batch.nodes if type(n).__name__ in ('PyMatchboxNode','PyMatchbox','PyShader') or 'CameraMatch' in str(getattr(n,'name','')))
        type(mb).__name__
   - 2.1c: list attribute surface:
        [a for a in dir(mb) if not a.startswith('_')]
2. Step 2.2 — find the uniform accessor. One /exec each:
   - 2.2a: hasattr probes:
        (hasattr(mb,'parameters'), hasattr(mb,'attributes'), hasattr(mb,'uniforms'), hasattr(mb,'parameter'))
   - 2.2b: filter for likely names:
        [a for a in dir(mb) if 'param' in a.lower() or 'unif' in a.lower()]
   - 2.2c: once an accessor is identified (call it ACC), enumerate keys:
        list(mb.ACC.keys()) if hasattr(mb.ACC,'keys') else [a for a in dir(mb.ACC) if not a.startswith('_')]
   Look for an entry like `out_pos_x` (or whatever shape Flame exposes the matchbox uniform under).
3. Step 2.3 — Probe 2a (LIVE READBACK). Three SEPARATE /exec calls (R2):
   - 2.3a: write sentinel:
        mb.ACC['out_pos_x'].set_value(42.0); 'set'   # adapt to actual API; trailing 'set' so result is non-None
   - 2.3b (separate request): readback:
        mb.ACC['out_pos_x'].get_value()
   - 2.3c: compare. If result == 42.0 → LIVE-READABLE. Stop, skip 2b. If not (None / 0.0 / 42.0 → 0.0) → fall through to 2b.
4. Step 2.4 — Probe 2b (SAVE-REQUIRED), only if 2a failed AND R6 guardrail is in place:
   - 2.4a: discover save API:
        [a for a in dir(flame.batch) if 'save' in a.lower()]
   - 2.4b (separate): set sentinel value (different from 42.0 to disambiguate from 2a's residue, e.g., 137.0).
   - 2.4c (separate): call save with timing:
        import time; t0=time.perf_counter(); flame.batch.<save_method>(); time.perf_counter() - t0
   - 2.4d (separate): readback. If 137.0 → SAVE-REQUIRED, record the save method name and round-trip latency. If still wrong → NOT-READABLE.
5. Write Probe 2 section of PROBE.md (2a + 2b + verdict) and update Findings Table rows 2a/2b. Link to transcripts/probe-2.md.

**Probe 3 execution (independent of Probe 2's outcome):**
6. Step 3.1 — module surface search. Three /exec calls (R2):
   - 3.1a: import flame; [a for a in dir(flame) if 'snap' in a.lower() or 'capture' in a.lower() or 'still' in a.lower()]
   - 3.1b: [a for a in dir(flame.batch) if 'snap' in a.lower() or 'capture' in a.lower() or 'still' in a.lower()]
   - 3.1c: hasattr(flame, 'execute_shortcut')
7. Step 3.2 — for each candidate found in 3.1, read its docstring (NEVER help()):
        repr(flame.<candidate>.__doc__)
8. Step 3.3 — filesystem search (Bash, not bridge):
        grep -rli 'snapshot' /opt/Autodesk/flame_*/python 2>/dev/null | head -20
        grep -rli 'snapshot' /opt/Autodesk/flame_*/lib/python* 2>/dev/null | head -20
        find /opt/Autodesk -maxdepth 5 -iname "*snapshot*" 2>/dev/null | head -30
   Record verbatim in transcripts/probe-3.md.
9. Step 3.4 — IF a callable is found AND it's not obviously destructive: park the player on a known frame (ask user via brief checkpoint if needed), then invoke it in the throwaway batch group:
   - record return value
   - find the produced file: `find /var/tmp/Autodesk ~/Movies ~/Pictures /tmp -newer /tmp/probe3_marker -type f 2>/dev/null | head -20` (touch /tmp/probe3_marker just before the call to scope the search)
   - probe format/colorspace: `file <path>`; if oiiotool is available `oiiotool --info <path>`; else read first 32 bytes with `xxd <path> | head -2`
   IF no callable found: skip 3.4. Verdict is NOT-FOUND with the search trail as evidence.
10. Write Probe 3 section of PROBE.md and update Findings Table row 3.

**Crash-handling (R5):** Same pattern as Task 1. If a /exec returns no envelope, save what's captured to the appropriate transcript, record the crash itself as the finding for that sub-probe, mark verdict as "BLOCKED — bridge SIGSEGV", note in Probe 4 (cross-probe state) section, and surface a checkpoint asking the user to restart Flame before deciding whether to retry. Two consecutive crashes → STOP and proceed to Task 4 to finalize with partial findings.

**R3 reminder:** Nothing in either probe should call QDialog.exec / QWidget.show / open the calibrator UI / open an error message box. If a candidate API has a side-effect of opening UI (e.g., `flame.execute_shortcut("Snapshot")` might trigger a save dialog), check the docstring first; if unsure, do NOT invoke from bridge — record as "unsafe to invoke from bridge per R3" in transcripts/probe-3.md and ask the user to test it via the menu/shortcut directly, reporting back what happened.
  </action>
  <verify>
    <automated>test -f .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-2.md && test -f .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md && grep -q "## Probe 2" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && grep -q "## Probe 3" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && grep -qE "Verdict: (LIVE-READABLE|SAVE-REQUIRED|NOT-READABLE|DISCOVERY-BLOCKED|BLOCKED)" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && grep -qE "Verdict: (FOUND|NOT-FOUND|PARTIAL|BLOCKED)" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md</automated>
  </verify>
  <done>
    transcripts/probe-2.md and transcripts/probe-3.md exist with verbatim request/response for every /exec call made. PROBE.md has fully-written Probe 2 and Probe 3 sections with verdicts. Findings Table rows 2a, 2b, 3 are populated. R6 was honored throughout (no save against user's primary batch). No production code modified. If any sub-probe crashed, the crash is documented as the verdict for that sub-probe with the transcript trail showing the last successful state.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Human-in-the-loop verification — Probe 1 expression entry, optional Probe 3 invocation</name>
  <what-built>
    Tasks 1 and 2 have run all the bridge-safe introspection and produced candidate expression syntaxes (Probe 1) and possibly candidate snapshot API calls (Probe 3) that need to be tried in Flame's UI directly — not via the bridge — because:
      - R3 forbids UI dialogs from /exec
      - Expression entry happens in Flame's animation editor, not via Python
      - Some snapshot APIs may trigger save dialogs that would crash if invoked from the bridge
  </what-built>
  <how-to-verify>
    The executor will surface this checkpoint with the candidate list inline. Steps for the user:

    1. **Probe 1 — expression entry test**
       - Open the throwaway batch group used for the spike
       - Right-click the Action camera's `Position X` field → Animation → Edit Expression (or equivalent — depends on Flame version)
       - For each candidate syntax the executor lists (e.g., `pixel(<matchbox_node>, 0, 0).r`), paste it in and try to apply
       - Note for each candidate: ACCEPTED (with no error), REJECTED (with the exact error message Flame shows), or UNCERTAIN
       - If any candidate ACCEPTED: change one of the matchbox VP line endpoints (so `cam_pos` recomputes) and observe whether `pos_x` updates. YES = WORKED. NO = PARTIAL.
       - Report results back to the executor for transcription into transcripts/probe-1.md.

    2. **Probe 3 — manual snapshot invocation (only if Task 2 surfaced a candidate that was unsafe to invoke from bridge)**
       - Park player on a known frame
       - Invoke the snapshot via the menu / shortcut the executor names
       - Note: where did the file land? what format? was a dialog shown? did Flame stay alive?
       - Report findings back for transcription into transcripts/probe-3.md.

    3. **Cross-probe state check (Probe 4)**
       - During the spike, did Flame need to be restarted at any point? If yes, between which probes?
       - Report yes/no.

    Reply format examples:
      "P1 candidate 1 (pixel(...)) → REJECTED, error 'Unknown function pixel'. Candidate 2 (sample(...)) → ACCEPTED, pos_x DID update on VP change."
      "P3 — invoked Snapshot via player; file landed at <path>, .dpx, no dialog, Flame fine."
      "P4 — no restart needed."
  </how-to-verify>
  <resume-signal>
    Reply with the results above OR type "skip" if you want the executor to proceed with current findings only (Probe 1 will be marked DIDN'T-WORK / Probe 3 candidate left as PARTIAL).
  </resume-signal>
</task>

<task type="auto">
  <name>Task 4: Transcribe human findings, write Recommendation Matrix + Next Planning Step</name>
  <files>
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md,
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-1.md,
    .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/transcripts/probe-3.md
  </files>
  <action>
1. Transcribe the user's checkpoint reply verbatim into the relevant transcripts (probe-1.md for P1, probe-3.md for P3) under a "## Human-in-the-loop verification" section. Update the Probe 1 verdict (and Probe 3 verdict if applicable) in PROBE.md based on what the user reported.
2. Fill in the Probe 4 (cross-probe state) row of the Findings Table:
   - CLEAN if no Flame restart was needed mid-spike
   - DEGRADED if a restart was required (note between which probes, and reference the relevant memory crumbs about session decay if applicable)
3. Write the **Recommendation Matrix** section of PROBE.md. For each of the three architectural paths, fill in:
   - **Status from this spike** — verbatim from the corresponding probe verdict
   - **Recommended?** — one of: YES (pursue first), MAYBE (pursue if first choice blocks), NO (drop)
   - **Rationale** — one or two sentences citing the probe evidence

   Decision rules for the matrix:
   - Path A recommended YES iff Probe 1 verdict is WORKED. MAYBE if PARTIAL. NO if DIDN'T-WORK.
   - Path B recommended YES iff Probe 2a is LIVE-READABLE. MAYBE if Probe 2b is SAVE-REQUIRED with sub-second latency (note the threshold in the rationale). NO if NOT-READABLE or save round-trip > 2 seconds (would make the calibrator UX unworkable).
   - Snapshot recommended YES iff Probe 3 verdict is FOUND with raw/uncolored output. MAYBE if FOUND but graded/lossy. NO if NOT-FOUND.
   - If multiple paths are YES, the recommendation order in the "Next Planning Step" section is: B (simplest if live readback works) → A (no Python companion needed) → Snapshot (orthogonal, can be planned in parallel as Wiretap replacement regardless of A/B outcome).

4. Write the **Next Planning Step** section. One paragraph that:
   - Names which path(s) the next planner should pursue
   - Names which to drop
   - If all three are blocked: names what would unblock the most viable one (e.g., "Path A is currently blocked because Flame's expression syntax doesn't expose pixel sampling; an unblocking spike would be to test whether the Action camera supports custom Python callbacks via PyAttribute.set_callback if such an API exists")

5. Write the **Memory Crumb Candidates** section. Most spike findings live only in PROBE.md, NOT in the memory index. Only add a crumb candidate if a finding meets the bar: "would I want this if I forgot it" — i.e., a durable Flame API behavior that would save a future session from re-running the same probe. If nothing meets that bar, write "None — all findings are situational and live in this PROBE.md only." (per CLAUDE.md memory-crumb discipline).

6. Stamp the PROBE.md "Started" timestamp's matching "Completed" timestamp at the end of the Pre-flight section.

7. Final self-check (echo to PROBE.md as a "## Self-check" section that verifies):
   - All three primary probes have a verdict (no blank rows in Findings Table)
   - Each verdict row links to its transcript
   - Recommendation Matrix fully populated
   - Next Planning Step paragraph names at least one concrete path (or names what would unblock)
   - No production code outside .planning/quick/260430-ddi-... was modified (run `git status` and confirm only files under that dir + this PROBE.md changed)
  </action>
  <verify>
    <automated>cd /Users/cnoellert/Documents/GitHub/forge-calibrator && grep -q "## Recommendation Matrix" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && grep -q "## Next Planning Step" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && grep -q "## Memory Crumb Candidates" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && ! grep -qE "^\| (1|2a|2b|3) \|.*\|\s*\|\s*\|\s*\|" .planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/260430-ddi-PROBE.md && (cd /Users/cnoellert/Documents/GitHub/forge-calibrator && test -z "$(git status --porcelain | grep -v '^.. .planning/quick/260430-ddi-')")</automated>
  </verify>
  <done>
    PROBE.md is complete: Pre-flight stamped, all three primary probes have verdicts with transcript links, Recommendation Matrix populated for all three architectural paths, Next Planning Step paragraph names at least one concrete recommendation (or unblocking action if all blocked), Memory Crumb Candidates section present (even if "None"), Self-check section confirms no production code touched. The next planner can read PROBE.md alone and know which path to plan.
  </done>
</task>

</tasks>

<threat_model>
This spike is research-only against a local-only forge-bridge (`127.0.0.1:9999`) inside an internal VFX pipeline. No new attack surface is introduced. Per CLAUDE.md "Security posture: Internal VFX post-production tool. No user-facing auth surface; artifacts live on trusted storage. forge-bridge binds to `127.0.0.1` only." — this spike does not change any of that.

The relevant *operational* threats (Flame stability, not security) are already mitigated in `<bridge_contract>` rules R1-R6 above. No STRIDE register applies — no new authentication, persistence, or network-exposed surface is created. Security enforcement section retained for schema-completeness.

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-260430-ddi-01 | Tampering (operational, not security) | forge-bridge /exec session state | mitigate | One probe per /exec (R2); throwaway batch group for any state-mutating call (R6); capture-on-call wrappers if save/set is risky (R5) |
| T-260430-ddi-02 | Denial-of-Service (Flame crash) | Flame Qt main thread | mitigate | No QDialog/QWidget/exec from /exec (R3); checkpoint-route human-only verification through actual menu flow |
| T-260430-ddi-03 | Information Disclosure | n/a | accept | Bridge is 127.0.0.1-only, internal post-production environment |
</threat_model>

<verification>
After all four tasks complete, verify:
- `260430-ddi-PROBE.md` exists with all required sections (Pre-flight, Findings Table, Probe 1/2/3 detail sections, Recommendation Matrix, Next Planning Step, Memory Crumb Candidates, Self-check)
- `transcripts/probe-1.md`, `transcripts/probe-2.md`, `transcripts/probe-3.md` all exist and contain verbatim /exec request bodies + responses (curl output blocks)
- Each Findings Table row links to its transcript
- Recommendation Matrix has Status + Recommended + Rationale filled for Path A, Path B, Snapshot
- Next Planning Step names at least one concrete path or unblocking action
- `git status` shows ONLY files under `.planning/quick/260430-ddi-...` modified — no production code touched
</verification>

<success_criteria>
The next planner can:
1. Open PROBE.md and within 60 seconds know which architectural path to plan first (or that all are blocked)
2. Audit any finding by following the transcript link and reading the verbatim bridge call
3. Trust the result is primary-source evidence, not assumption — every "WORKED" or "DIDN'T-WORK" is backed by a /exec response
4. Skip ever re-running these probes against this Flame version (2026.2.1) unless a Flame upgrade invalidates the assumption
</success_criteria>

<output>
After all four tasks complete, the artifacts in `.planning/quick/260430-ddi-spike-matchbox-calibrator-architecture-t/` constitute the deliverable. No SUMMARY.md is required for quick tasks — PROBE.md IS the deliverable.
</output>
