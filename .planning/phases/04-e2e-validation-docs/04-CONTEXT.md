# Phase 4: E2E Validation + Docs - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate the complete right-click → edit → Send-to-Flame loop on the production stack (Flame 2026.2.1 + Blender 4.5+) and ship user-facing docs covering install, forge-bridge autostart, and troubleshooting. Two requirements:

- **DOC-01:** E2E smoke test passes the full cycle without visiting Flame's batch menu for the return trip (captured as a hybrid shell-script + inline human checklist).
- **DOC-02:** User doc covers what changed from v6.2, how to install both install.sh and the Blender addon, how the autostart works, and at least 3 troubleshooting recipes.

**In scope:**
- New E2E smoke-test artifact (shell script + inline human checklist) that bookends the Phase 3 HUMAN-UAT Test 3 live checks (bridge reachable after Flame boot; no orphan after Flame quit).
- New `README.md` at repo root (thin overview + install summary + link to deep-dive doc).
- New `docs/seamless-bridge.md` (detailed user guide: install, autostart model, Send-to-Flame usage, 5 troubleshooting recipes).
- Grep-anchoring troubleshooting copy to the verbatim popup/warning strings Phase 2 D-09 and Phase 3 D-10 already emit.

**Out of scope** (belongs to later phases or v2):
- Any code changes in `forge_sender/`, `forge_flame/`, `camera_match_hook.py`, or `install.sh` — Phase 4 is validation + docs only. If the E2E smoke test surfaces a defect, gap-close via `/gsd-plan-phase {X} --gaps`, not Phase 4.
- Screenshots, GIFs, or video walkthroughs — text-only for v1; promote to v2 only if artist confusion warrants.
- Automated Flame-interactive tests (headless Flame / scripted dev instance is a separate, multi-month infra project).
- Multi-version docs or translation.
- A migration guide for v6.2 users beyond a "What's new" bullet list — `install.sh` handles upgrade mechanics.
- MULT-01 (multi-camera round-trip) validation — single-camera only per v1 scope.

</domain>

<decisions>
## Implementation Decisions

### E2E smoke-test format (DOC-01)

- **D-01:** The E2E smoke test is a **hybrid shell script + inline human checklist**. The script mechanizes what can be automated (install dry-run, install live, hook-file ast.parse, curl bridge, pytest) and prompts the user inline for the Flame/Blender interactive steps. On each human step, the script prints the exact action expected and waits for the user to type `y` (pass) or `n` (fail) before continuing. Rationale: full automation requires headless Flame (out of scope); pure checklist loses the pre-flight wins we already have from Phase 3 HUMAN-UAT.
- **D-02:** Script location is **Claude's Discretion** — likely `tools/smoke-test/seamless-bridge-smoke.sh` (new sibling to `tools/blender/`). Alternative acceptable location: `scripts/smoke-test.sh`. Planner picks whichever is more discoverable; either goes in `README.md` under "Validation".
- **D-03:** Mechanized + human steps, in order:
  1. **[mech]** Fresh working-tree check (`git status --porcelain` is empty or only `.claude/`).
  2. **[mech]** `./install.sh --dry-run` — exits 0, no side effects.
  3. **[mech]** `./install.sh` — exits 0; if bridge install is skipped, warning fires per Phase 3 D-10 (acceptable; smoke test records the skip and continues).
  4. **[mech]** Hook sanity: `test -f /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py && python3 -c 'import ast; ast.parse(open(...).read())'`.
  5. **[human]** Prompt: "Restart Flame now, then press Enter." → after Enter: **[mech]** `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` → expect `200`. ⬅ Folded from Phase 3 HUMAN-UAT Test 3, first half.
  6. **[human]** Prompt: "In Flame: right-click the Action → 'Export Camera to Blender'. Blender should open on the baked camera. Answer y/n."
  7. **[human]** Prompt: "In Blender: edit the camera (move it, rotate it, scrub a keyframe). Click N-panel → Forge → 'Send to Flame'. Expect the success popup 'Sent to Flame: camera X in Action Y'. Answer y/n."
  8. **[human]** Prompt: "In Flame: verify a new camera appears in the target Action with keyframes preserved (scrub the timeline). Answer y/n."
  9. **[human]** Prompt: "Quit Flame, then press Enter." → after Enter: **[mech]** `pgrep -f forge_bridge.py` returns nothing. ⬅ Folded from Phase 3 HUMAN-UAT Test 3, second half.
  10. **[mech]** Full pytest suite (`pytest -q`) — all pass.
- **D-04:** Script is **idempotent** and **non-destructive** on re-run — safe to invoke multiple times against an already-installed workstation. It does NOT clobber `~/forge-bakes/`, does NOT require `--force`, and does NOT assume a clean `/opt/Autodesk/` state.
- **D-05:** **Success criterion for DOC-01:** smoke-test script exits 0 AND every `[human]` step's y/n prompt was answered `y`. The script records the full run transcript to `/tmp/forge-smoke-YYYYMMDD-HHMMSS.log` for audit.
- **D-06:** On any `[mech]` failure, the script exits non-zero with the failure line echoed. On any `[human]` step answered `n`, the script exits non-zero with the step description + "report to the troubleshooting section of docs/seamless-bridge.md" message. The test fails loud — no silent skips.

### User doc structure (DOC-02)

- **D-07:** Two files are created:
  - `README.md` (new, repo root) — thin overview, install summary, "what's new in v6.3" bullet list, link to the deep-dive doc, link to `PASSOFF.md` for v4→v6.2 history.
  - `docs/seamless-bridge.md` (new) — canonical user guide for the seamless round-trip capability.
- **D-08:** **README.md structure:**
  1. What this is (≤3 sentences, adapted from `.planning/PROJECT.md` §What This Is).
  2. Core value statement (1 sentence, verbatim from PROJECT.md).
  3. **What's new in v6.3** (bullet list): seamless round-trip, forge-bridge autostart, Blender "Send to Flame" addon. Link to `docs/seamless-bridge.md` for details.
  4. **Install** (collapsed summary):
     - Run `./install.sh` (macOS/Linux; requires forge conda env).
     - Install the Blender addon: unzip `tools/blender/forge_sender/` → Blender Preferences → Add-ons → Install from file → enable.
     - Link to `docs/seamless-bridge.md#install` for the detailed walkthrough.
  5. **Validation** (1 paragraph): Pointer to the E2E smoke-test script (D-02 path) + one-line command to run it.
  6. **History**: Pointer to `PASSOFF.md` for the v4→v6.2 backstory.
  7. **Troubleshooting**: Link to `docs/seamless-bridge.md#troubleshooting`.
- **D-09:** **`docs/seamless-bridge.md` structure:**
  1. **Overview** — what the seamless round-trip does (1 paragraph); the three moving parts (Flame hook / forge-bridge / Blender addon).
  2. **Install** — subsection per audience:
     - *For pipeline TDs*: install.sh flow (preflight, what deploys where, `/opt/Autodesk/` layout).
     - *For artists*: Blender addon install (unzip → Preferences → Add-ons → Install from file → enable → N-panel Forge tab appears).
  3. **How forge-bridge autostart works** — plain-language description: Flame boots → Camera Match hook registers → forge-bridge.py subprocess spawns → binds `127.0.0.1:9999` → dies when Flame quits. Note that no user action is needed.
  4. **Using Send to Flame** — the happy-path walkthrough: bake camera from Flame → edit in Blender → click Send to Flame → see camera appear in target Action with keyframes preserved. Name the N-panel "Forge" tab explicitly.
  5. **Troubleshooting** — 5 recipes per D-12/D-13.
- **D-10:** **Audience split** is handled via subsection headers inside the Install section (pipeline-TD subsection + artist subsection) — NOT via separate files. Keeps everything findable; artists can skip the TD section.
- **D-11:** **Text-only — no screenshots, GIFs, or video** for v1. Carries forward Phase 1/2 "simplicity over flexibility" preference. Revisit in v2 only if first-cycle artist feedback flags addon-install confusion specifically.

### Troubleshooting recipes (5)

- **D-12:** Recipes in this order and with these exact triggers (grep-anchored to the real popup/warning text):
  1. **"forge-bridge not reachable at 127.0.0.1:9999 — is Flame running?"** (Phase 2 D-09 Tier 2 popup verbatim)
     - Likely cause: Flame not running, or bridge didn't start on boot.
     - Fix: ensure Flame is running; test bridge with `curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"` (expect 200); if 200 but still failing, restart Flame.
  2. **"Active camera missing `forge_bake_action_name` / `forge_bake_camera_name`"** (Phase 2 D-09 Tier 1(c) popup verbatim)
     - Likely cause: camera wasn't baked from Flame, or it was baked by an older tool that doesn't stamp metadata.
     - Fix: in Flame, right-click the target Action → "Export Camera to Blender" to get a freshly baked camera with correct metadata.
  3. **"Send failed: {error}\n\n{traceback}"** (Phase 2 D-09 Tier 3 envelope)
     - Likely cause: Flame-side import crash, FBX parse failure, or Action renamed/deleted after bake.
     - Fix: check the traceback's top line; most common: Action was renamed (re-bake from the current name) or Action has two cameras with the same name (rename to disambiguate).
  4. **"forge-bridge install skipped (sibling installer exited non-zero)"** (Phase 3 D-10 warning verbatim)
     - Likely cause: no local forge-bridge clone found AND curl-fallback failed (usually offline or firewalled).
     - Fix: either `FORGE_BRIDGE_REPO=<path> ./install.sh` with a local clone, or ensure network access to `raw.githubusercontent.com` and re-run `./install.sh`. VP-solve and v6.2 static round-trip still work without the bridge.
  5. **"Port 9999 already in use" / bridge won't start**
     - Likely cause: another service (or a leftover forge-bridge from a previous Flame session that didn't shut down cleanly) holds port 9999.
     - Fix: `lsof -i :9999` to find the PID → `kill <pid>` → restart Flame. If this recurs, check for a second Flame instance.
- **D-13:** **Recipe format**: each recipe has exactly three sections: **Symptom** (verbatim error text user sees), **Likely cause** (plain-English explanation), **Fix** (copy-pasteable commands or exact UI steps).
- **D-14:** **Grep-anchoring** — every recipe's Symptom line MUST be a string the user can Ctrl-F from the exact error popup or install output. The planner/executor verifies this by grepping `forge_sender/` and `install.sh` for the anchor strings.

### Phase 3 HUMAN-UAT Test 3 placement

- **D-15:** Phase 3's deferred Test 3 (bridge reachable after Flame boot; no orphan after Flame quit) is folded into the E2E smoke test at step 5 (reachable) and step 9 (no orphan) per D-03. It is NOT a troubleshooting recipe — it is the happy-path validation that brackets the Send loop.

### v6.2 → v6.3 upgrade story

- **D-16:** A "**What's new in v6.3**" bullet list lives in `README.md` (D-08 item 3), linking to `docs/seamless-bridge.md`. Three bullets: seamless round-trip, forge-bridge autostart, Blender Send-to-Flame addon.
- **D-17:** **No separate migration section.** `install.sh` handles the upgrade mechanics idempotently; the single new user action is installing the Blender addon, which is already covered in the Install section (D-09 item 2). Do not duplicate install content under a "Migration" heading.

### Claude's Discretion

Items the planner/executor can decide without re-consulting the user:

- Exact path for the smoke-test script (`tools/smoke-test/` vs `scripts/` vs `tests/e2e/`) per D-02.
- Exact wording of the `README.md` one-paragraph overview (adapted from PROJECT.md §What This Is).
- Exact section ordering within the Troubleshooting section of `docs/seamless-bridge.md` if a different order reads better than D-12's order.
- Whether the smoke-test script uses `read -rp` for y/n prompts, a case statement, or a tiny helper function — pick whichever is shortest and most legible.
- Whether the `[human]` step messaging uses ANSI color codes for the prompt label (e.g., bold yellow "HUMAN:"). Default yes if it makes the prompts easier to spot in the transcript.
- Whether to snapshot `git describe --tags` or `git rev-parse HEAD` into the smoke-test log header for provenance. Default yes if trivial.
- Whether the "Port 9999 already in use" recipe's `lsof` example uses `-i :9999` or `-iTCP:9999 -sTCP:LISTEN`. Pick whichever is most portable across macOS + Linux.
- Cross-linking density between `README.md` and `docs/seamless-bridge.md` — use markdown relative links liberally.
- Exact copy of the "what's new in v6.3" bullets (keep ≤3 items, names user-facing capabilities, does NOT name internal components like `forge_sender` or `camera_match_hook`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Authority docs
- `.planning/REQUIREMENTS.md` §Docs (DOC-01, DOC-02) — the two requirements Phase 4 closes.
- `.planning/PROJECT.md` §What This Is, §Core Value, §Context, §Out of Scope — source of `README.md` overview copy.
- `.planning/ROADMAP.md` §Phase 4 Success Criteria — the two conditions the phase must satisfy.
- `PASSOFF.md` (repo root) — v4→v6.2 backstory; `README.md` links to it.

### Prior phase context (locked decisions carried forward)
- `.planning/phases/01-export-polish/01-CONTEXT.md` — Blender launch behavior (D-01/D-02), default `.blend` path `~/forge-bakes/{action}_{cam}.blend` (D-04), metadata stamping keys (D-11), zero-dialog semantics (error dialogs still allowed).
- `.planning/phases/02-blender-addon/02-CONTEXT.md` — **Three-tier error popup taxonomy (D-09) is the source of truth for troubleshooting recipe 1/2/3 symptom copy**; manual zip install decision (D-12) shapes the Install section; N-panel tab name `Forge` (D-14).
- `.planning/phases/03-forge-bridge-deploy/03-CONTEXT.md` — install.sh wiring; **D-10 warning copy is the source of truth for troubleshooting recipe 4**; D-14 confirms E2E live checks belong here.
- `.planning/phases/03-forge-bridge-deploy/03-HUMAN-UAT.md` — Phase 3 Test 3 (bridge reachable + no orphan) — the deferred live check that folds into Phase 4's smoke test per D-15.

### Code referenced in troubleshooting recipes (must be grep-anchored)
- `tools/blender/forge_sender/preflight.py` — Tier 1 popup text (recipe 2).
- `tools/blender/forge_sender/transport.py` — Tier 2 popup text (recipe 1).
- `tools/blender/forge_sender/operator.py` (or wherever the Tier 3 popup lives per Phase 2 executor's choice) — Tier 3 envelope (recipe 3).
- `install.sh:425-426` — Phase 3 D-10 warning `printf` (recipe 4).

### External dependencies named in docs
- `~/Documents/GitHub/forge-bridge/` — sibling repo; docs mention it by name but do NOT require users to clone.
- `/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` — where the bridge hook lands after install; named in the autostart explanation.

### Memory docs (gotchas the planner must know)
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md` — `/exec` endpoint contract (informs recipe 3 traceback explanation).
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_probing.md` — probing discipline (not strictly needed for docs but good context).
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_module_reload.md` — why Flame restart is required for hook changes (informs autostart explanation).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `PASSOFF.md` — existing v4→v6.2 history; `README.md` links to it rather than duplicating.
- `install.sh` — deployment mechanics; docs describe WHAT it does, not HOW it does it (grep-anchor the section names: `> forge-bridge`, `> Install`, `> forge_core + forge_flame`).
- `tools/blender/forge_sender/` (Phase 2 output) — addon source; install doc points here as the zip source.
- 311-test pytest suite — smoke-test step 10 invokes it.
- `.planning/PROJECT.md` §What This Is + §Core Value — source copy for `README.md` overview.

### Established Patterns
- **Shell script style from install.sh:** section headers via `step "Name"` printer, preflight sanity checks at top, `ok "..."` / `warn "..."` / `step "..."` helpers. Smoke-test script should mirror this visual rhythm even if it doesn't import from install.sh.
- **Doc tone from Phase 1/2 specifics:** direct, names the thing, offers the fix, no internal jargon in user-facing surface. No "PyActionNode" / "PyAttribute" / "duck-typing" in user docs.
- **Grep-anchor discipline:** user docs that quote error text must match the source verbatim so Ctrl-F works. Executor verifies via grep.
- **Simplicity preference:** across Phase 1, 2, and 3, user consistently chose fewest-lines-of-change, minimal maintenance burden, no premature abstraction. Extend that preference into docs — no over-structured headings, no exhaustive recipe coverage beyond the 5 in D-12.

### Integration Points
- **New files (all three land in Phase 4):**
  - `README.md` (repo root)
  - `docs/seamless-bridge.md` (new `docs/` directory)
  - Smoke-test script at a Claude's Discretion path (D-02) — `tools/smoke-test/seamless-bridge-smoke.sh` is the likely pick.
- **No changes to any existing code or config.** Phase 4 is validation + docs only. If the smoke test reveals a defect, gap-close via `/gsd-plan-phase 4 --gaps`, not Phase 4.

</code_context>

<specifics>
## Specific Ideas

- **User runs macOS/Linux VFX post-production environments** — docs assume Unix-ish shell (`./install.sh`, `curl`, `pgrep`). No Windows examples (Flame doesn't run on Windows anyway; Out of Scope).
- **Primary audience: artist reads docs when something breaks.** Troubleshooting section is the most-read section. Put verbatim error text at the top of each recipe so Ctrl-F lands the user exactly where they need to be.
- **Secondary audience: pipeline TD reads docs during install.** TD subsection lives inside the Install section, not as a separate file.
- **Tone mirrors Phase 2 D-09 popup copy** — direct, names the thing, offers the fix. No "PyAttribute" in user-facing text; use "Action" and "camera".
- **Smoke test is the authoritative gate for cutting v6.3.** Once the script exits 0 AND all y/n prompts were `y`, the milestone ships. The script's exit code is the source of truth.
- **Grep-anchor everything.** Troubleshooting recipe symptoms must match the source verbatim. Executor verifies this by running `grep -F "{symptom}" <source-file>` during the verification pass.
- **The "forge" branding lives in two places:** Blender N-panel tab name (`Forge`, per Phase 2 D-14) and the smoke-test/install section headers. Keep these consistent in docs so artists can Ctrl-F "Forge" and find what they need.
- **Link discipline:** use relative markdown links between `README.md` and `docs/seamless-bridge.md` (`[install section](docs/seamless-bridge.md#install)`). Do not link to github.com URLs — docs are read from the local checkout.

</specifics>

<deferred>
## Deferred Ideas

- **Screenshots / GIFs / video walkthroughs** — text-only for v1; revisit in v2 only if first-cycle artist feedback flags specific confusion points (most likely candidate: Blender addon install UI flow).
- **Automated Flame-interactive tests** — would require headless Flame or a scripted Flame dev instance. Separate multi-month infra project; out of scope for v6.3.
- **Multi-version docs** — v6.3 is the only documented version; PASSOFF.md covers historical context for older versions. Don't attempt to document v4/v5/v6.0/v6.1/v6.2 in the new doc.
- **Internationalization / translation of docs** — English only. If this tool ever ships beyond the current team, revisit.
- **Full migration guide** for v6.2 → v6.3 — covered by "What's new" bullet list + install section. Separate migration doc would duplicate content and rot faster than a bullet list.
- **"Changelog" / release-notes feed** — the v6.3 "What's new" bullets in `README.md` are the release notes. Maintaining a separate CHANGELOG.md is v2+ scope if the project ever takes outside contributions.
- **MULT-01 (multi-camera round-trip) in the E2E smoke test** — single-camera only per v1 scope. MULT-01 validation belongs with MULT-01's implementation phase in v2.
- **Uninstall script / uninstall docs** — not needed; artists re-run `install.sh` for upgrades and rarely uninstall. If anyone asks, add a recipe.
- **Offline / air-gapped install recipe** — Phase 3 D-10 already mentions the offline failure mode in its warning copy; troubleshooting recipe 4 covers the fix (use `FORGE_BRIDGE_REPO=<path>`). A full offline-install narrative is overkill.

### Reviewed Todos (not folded)

None — `todo match-phase 4` returned zero matches.

</deferred>

---

*Phase: 04-e2e-validation-docs*
*Context gathered: 2026-04-22*
