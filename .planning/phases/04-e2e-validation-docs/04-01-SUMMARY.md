---
phase: 04-e2e-validation-docs
plan: "01"
subsystem: docs
tags: [docs, user-facing, grep-anchor, v6.3, DOC-02]
dependency_graph:
  requires: []
  provides: [README.md, docs/seamless-bridge.md]
  affects: [DOC-02]
tech_stack:
  added: []
  patterns: [grep-anchor, relative-markdown-links, audience-split-subsections]
key_files:
  created:
    - README.md
    - docs/seamless-bridge.md
  modified: []
decisions:
  - "smoke-test script path agreed as tools/smoke-test/seamless-bridge-smoke.sh (D-02 Claude's Discretion)"
  - "lsof -i :9999 used for recipe 5 (shorter, most portable on macOS + Linux per D-Claude's-Discretion item 7)"
  - "Recipe 3 Symptom uses verbatim source 'Send to Flame failed:' not CONTEXT D-12.3 paraphrase 'Send failed:' (D-14 grep-anchor discipline)"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-22"
  tasks_completed: 3
  files_changed: 2
---

# Phase 04 Plan 01: Write README.md and docs/seamless-bridge.md Summary

**One-liner:** Two user-facing docs closing DOC-02 — thin README overview + deep-dive
seamless-bridge guide with 5 grep-anchored troubleshooting recipes covering all D-09/D-12
scenarios.

## Artifacts Created

| File | Lines | Purpose |
|------|-------|---------|
| `README.md` | 59 | Repo-root overview: What this is, Core value, What's new in v6.3, Install summary, Validation pointer, History pointer, Troubleshooting pointer |
| `docs/seamless-bridge.md` | 170 | Canonical user guide: Overview, Install (TD + artist subsections), Autostart explanation, Send-to-Flame walkthrough, 5 troubleshooting recipes |

## Grep-Anchor Sweep Output (Task 3)

All 12 grep assertions passed. Evidence:

**Recipe 1 — both directions:**
```
tools/blender/forge_sender/__init__.py:240:   "Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999"
docs/seamless-bridge.md: ### Symptom: Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Match hook loaded?
docs/seamless-bridge.md: ### Symptom: Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Match hook loaded? (and `lsof -i :9999` shows a non-forge-bridge process listening)
```

**Recipe 2 — both directions:**
```
tools/blender/forge_sender/preflight.py:54:   return (f"Send to Flame: active camera is missing '{key}' — "
docs/seamless-bridge.md: ### Symptom: Send to Flame: active camera is missing 'forge_bake_action_name' — this camera was not baked by forge-calibrator...
```

**Recipe 3 — both directions:**
```
tools/blender/forge_sender/transport.py:215: ``Send to Flame failed: {error}\\n\\n{traceback}``.
tools/blender/forge_sender/transport.py:220:         return (f"Send to Flame failed: {error}\n\n{traceback}", None)
docs/seamless-bridge.md: ### Symptom: Send to Flame failed: {error}
```

**Recipe 4 — both directions:**
```
install.sh:425:   printf "  %s[WARN]%s forge-bridge install skipped (%s). VP-solve and v6.2 static round-trip still work...
docs/seamless-bridge.md: ### Symptom: [WARN] forge-bridge install skipped (sibling installer exited non-zero). VP-solve and v6.2 static round-trip still work.
```

**Cross-link checks (all PASS):**
- `README.md` → `docs/seamless-bridge.md`: PASS
- `docs/seamless-bridge.md` → `../README.md`: PASS
- `README.md` → `PASSOFF.md`: PASS
- `README.md` → `tools/smoke-test/seamless-bridge-smoke.sh`: PASS

## DOC-02 Closure Evidence

| CONTEXT item | Satisfied by | Location |
|---|---|---|
| D-07: Two files (README.md + docs/seamless-bridge.md) | Both files created | repo root + docs/ |
| D-08: README.md 7-section structure | All 7 H2s in correct order | README.md |
| D-08 item 1: What this is | Adapted from PROJECT.md §What This Is | README.md §What this is |
| D-08 item 2: Core value verbatim | Bold sentence from PROJECT.md | README.md §Core value |
| D-08 item 3: What's new in v6.3 (3 bullets) | 3 bullets linking to docs/ | README.md §What's new in v6.3 |
| D-08 item 4: Install collapsed summary | 3 bullets + see-also | README.md §Install |
| D-08 item 5: Validation pointer | smoke-test script path + command | README.md §Validation |
| D-08 item 6: History pointer | Links to PASSOFF.md | README.md §History |
| D-08 item 7: Troubleshooting pointer | One-line link to doc | README.md §Troubleshooting |
| D-09: 5 H2 sections in order | All 5 present | docs/seamless-bridge.md |
| D-10: Audience split inside Install | ### For pipeline TDs + ### For artists | docs/seamless-bridge.md §Install |
| D-11: No screenshots/GIFs/video | Text-only throughout | Both files |
| D-12: 5 recipes in order | All 5 recipes present | docs/seamless-bridge.md §Troubleshooting |
| D-13: Three-section recipe format | Symptom/Likely cause/Fix | All 5 recipes |
| D-14: Grep-anchor discipline | All 4 source anchors verified | Task 3 sweep above |
| D-16: What's new v6.3 bullets | 3 bullets in README.md | README.md §What's new in v6.3 |
| D-17: No migration section | Absent from README.md | Verified |

## Discretion Items Exercised

1. **Smoke-test script path:** `tools/smoke-test/seamless-bridge-smoke.sh` — matches
   Plan 02 convention per D-02 Claude's Discretion.
2. **`lsof -i :9999`** chosen for recipe 5 over `-iTCP:9999 -sTCP:LISTEN` — shorter,
   equally portable on macOS + Linux per D-Claude's-Discretion item 7.
3. **Recipe 3 Symptom uses `"Send to Flame failed:"`** — source `transport.py:220` is
   authoritative; CONTEXT D-12.3 paraphrase (`"Send failed:"`) was overridden per D-14
   grep-anchor discipline. PATTERNS.md §Key correction confirms this.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `README.md` exists: FOUND
- `docs/seamless-bridge.md` exists: FOUND
- Task 1 commit `63542a5` exists: FOUND
- Task 2 commit `289dbde` exists: FOUND
- All 12 grep assertions: PASS
- No source code changes: CONFIRMED (only README.md and docs/seamless-bridge.md in diff)
