# Phase 4: E2E Validation + Docs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 04-e2e-validation-docs
**Areas discussed:** E2E test format, Doc structure, Troubleshooting scope, Media, Phase 3 Test 3 placement, Upgrade story
**Flow:** user requested recommendations after gray-area presentation; accepted all recos with "lock all" — equivalent to "Other (Claude's recommended defaults)" across all six areas.

---

## 1. E2E test format (DOC-01)

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Markdown checklist | Human-run, in-tree, cheapest | |
| (b) Hybrid: shell script + inline human checklist | Script mechanizes automatable steps; prompts inline for Flame/Blender interactions | ✓ (recommended) |
| (c) Pytest/automation | Drives forge-bridge over HTTP | |

**User's choice:** (b) Hybrid
**Rationale (captured):** Full automation requires headless Flame (out of scope). Pure checklist loses the pre-flight wins from Phase 3 HUMAN-UAT. Hybrid automates `install.sh --dry-run`, live install, `ast.parse`, `curl :9999`, `pgrep -f forge_bridge`, and pytest — while delegating `right-click Action` / `Blender edit` / `click Send` / `verify camera in Action` to inline y/n prompts.

---

## 2. User doc structure (DOC-02)

| Option | Description | Selected |
|--------|-------------|----------|
| (a) README.md only | Everything at root | |
| (b) docs/seamless-bridge.md only | Standalone doc | |
| (c) Both — thin README + deep-dive in docs/ | README as discovery/onboarding; docs/ as canonical user guide | ✓ (recommended) |

**User's choice:** (c) Both
**Rationale (captured):** No `README.md` exists today; shipping v6.3 without one is a gap. Thin README serves TDs (install pointer) and artists (at-a-glance "what's this?"); `docs/seamless-bridge.md` gives the detailed user guide room to grow. Marginal cost: both files land this phase.

---

## 3. Troubleshooting scope

| Option | Description | Selected |
|--------|-------------|----------|
| (a) 3 recipes (minimum required) | bridge not running, addon missing metadata, import failure | |
| (b) 5 recipes | 3 required + "install said skipped" (Phase 3 D-10) + "port 9999 in use" | ✓ (recommended) |
| (c) 10+ recipes | Exhaustive | |

**User's choice:** (b) 5 recipes
**Rationale (captured):** Recipe 4 ("install said skipped") is near-free — Phase 3 D-10's warning copy already tells users the fix; docs just anchor it. Recipe 5 ("port 9999 in use") is the one realistic install-time surprise on macOS/Linux workstations. Past 5 hits diminishing returns and reads as fear-doc.

---

## 4. Media in docs

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Text-only | Fastest, lowest rot, honors user's consistent simplicity preference | ✓ (recommended) |
| (b) Text + screenshots for Blender install flow | Highest-value addition; stable UI | |
| (c) Text + GIF of full Send loop | Highest artist value, highest maintenance cost | |

**User's choice:** (a) Text-only
**Rationale (captured):** User's preference across Phase 1 and Phase 2 was consistently simplicity over flexibility, minimal maintenance. Text-only honors that. Deferred: revisit (b) in v2 if first-cycle artist feedback specifically flags Blender addon-install confusion.

---

## 5. Phase 3 HUMAN-UAT Test 3 placement

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Fold into E2E smoke test | Bookend the Send loop: bridge reachable as step 5, no orphan as step 9 | ✓ (recommended) |
| (b) Standalone "first-install sanity check" section | Dedicated docs section | |
| (c) Part of "bridge not running" recipe | Troubleshooting-only | |

**User's choice:** (a) Fold into E2E smoke test
**Rationale (captured):** BRG-01 + BRG-02 live verification is the happy-path validation by definition — putting it in troubleshooting treats the happy path as an exception. One source of truth (the smoke-test script). Matches the bracket structure: Flame boot (verify bridge up) → the round-trip → Flame quit (verify no orphan).

---

## 6. v6.2 → v6.3 upgrade story

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Full migration section | Separate doc walking through upgrade steps | |
| (b) "What's new" bullet list + link to install | Short list in README; link to install section for the one new user action (addon install) | ✓ (recommended) |
| (c) Nothing | Users just re-run install.sh | |

**User's choice:** (b) "What's new" + link
**Rationale (captured):** `install.sh` handles the upgrade mechanics idempotently (Phase 3 verified). The only new user action is installing the Blender addon, which is already covered in the Install section (Phase 2 D-12). A separate migration section would duplicate install content.

---

## Claude's Discretion

Items the user deferred to Claude entirely (captured as D-* items in CONTEXT.md):

- Exact file path for the smoke-test script (D-02: likely `tools/smoke-test/seamless-bridge-smoke.sh`; alternatives acceptable).
- Exact wording of README one-paragraph overview (adapt from PROJECT.md §What This Is).
- Section ordering within `docs/seamless-bridge.md` Troubleshooting (D-12 order is recommended but planner may reorder).
- Implementation style of y/n prompts in the smoke-test script (`read -rp`, `case`, helper function).
- ANSI color codes for `[human]` prompt labels.
- `git describe` / `git rev-parse HEAD` provenance in smoke-test log header.
- `lsof` invocation variant in recipe 5.
- Cross-linking density between README and docs/seamless-bridge.md.
- Exact "what's new in v6.3" bullet copy (≤3 items, user-facing capability names only).

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section:

- Screenshots / GIFs / video (v2 candidate).
- Automated Flame-interactive tests (separate multi-month infra project).
- Multi-version docs (v6.3 only).
- Internationalization / translation (English only).
- Full migration guide (bullet list + install section suffices).
- Dedicated CHANGELOG.md (v2+).
- MULT-01 validation in E2E smoke test (v2).
- Uninstall script / docs.
- Offline/air-gapped install narrative (recipe 4 covers it).
