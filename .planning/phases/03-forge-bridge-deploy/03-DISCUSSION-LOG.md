# Phase 3: forge-bridge Deploy - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 03-forge-bridge-deploy
**Areas discussed:** Scope challenge (necessity of forge-bridge), Install source strategy, Version pinning, Install sequencing, Failure handling

---

## Scope challenge — Does Phase 3 require forge-bridge?

| Alternative | Description | Selected |
|-------------|-------------|----------|
| A. Keep forge-bridge external | install.sh invokes forge-bridge's own install-flame-hook.sh; runtime is the sibling repo's forge_bridge.py (the current plan). | ✓ |
| B. Inline minimal bridge into camera_match_hook | Add a ~200-300 LOC camera_match/bridge.py with a tiny http.server /exec endpoint. Hook starts/stops it. Single-repo. | |
| C. File-watcher / user-manual-import | Blender writes FBX to watched dir; Flame hook offers "Import new cameras" menu. Breaks IMP-06. | |
| D. Vendor forge-bridge into this repo | Copy flame_hooks/ into forge_flame/; no sibling coordination. Violates PROJECT.md separation stance. | |

**User's choice:** A — keep forge-bridge external.
**Notes:** User explicitly challenged premise: "Does this require forge-bridge honestly?" After reviewing the 4 alternatives and PROJECT.md §Context (§4) which says forge-bridge is "broken-out infrastructure... used beyond Camera Match", user confirmed: "I'm down to make forge_bridge a install requirement. I just wanted to ask the question." Rejection of Option B was deliberate — inlining was a real option but violates the broader forge-bridge vision.

---

## Install source strategy

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Curl from pinned GitHub tag | `curl -fsSL ... install-flame-hook.sh | bash` — always fresh, network-dependent. | |
| (b) Prefer local sibling clone, fall back to curl | Auto-detect `~/Documents/GitHub/forge-bridge/` etc.; curl as last resort. | ✓ |
| (c) Git submodule | Vendor a specific commit; submodule tax. | |
| (d) FORGE_BRIDGE_REPO env var (explicit path) | No guessing, no fallback. | (partial) |

**User's choice:** (b), with (d) folded in as an explicit override for predictability. The final D-01 in CONTEXT.md combines them: explicit env var first, sibling auto-detect second, curl fallback third.

---

## Version pinning

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Pinned tag constant in install.sh | `FORGE_BRIDGE_VERSION=v1.1.0` at top of file. | ✓ |
| (b) Track whatever's in sibling clone (no pin) | Always current; no pin to maintain. | |
| (c) Reference pin from config.json | User-overridable without editing install.sh. | |

**User's choice:** (a) — pinned tag constant.

---

## Install sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Before Camera Match hook install | Bridge deployed first; cleaner failure order. | ✓ |
| (b) After everything else | Bridge is polish / add-on. | |
| (c) Opt-in with `--with-bridge` flag | Default skip; explicit enable. | |

**User's choice:** (a) — before Camera Match.

---

## Failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| (a) Abort entire install run | Bridge required; halt everything. | |
| (b) Warn + continue | VP-solve + v6.2 features work without bridge; print explicit skip marker. | ✓ |
| (c) Prompt for retry | Interactive; ask user for path / sudo / retry. | |

**User's choice:** (b) — warn + continue.

## Claude's Discretion

- D-02: env var naming (`FORGE_BRIDGE_REPO` for path).
- D-03: verbose logging convention (which source path was used).
- D-06: local-clone-vs-pin drift surfaced as info, not error.
- D-08: install.sh output section header style.
- D-12: `--dry-run` mode prints rather than executes.
- D-13: `--force` mode pre-deletes the target file for clarity.

## Deferred Ideas

- BRG-02 live verification deferred to Phase 4 E2E smoke test.
- Bridge crash recovery UX handled by Phase 2's Transport Tier popup.
- Bridge logging destination owned by forge-bridge repo, not Phase 3.
- Inline bridge (Option B) explicitly rejected — revisit only if Camera Match remains the sole consumer.
- Version reconciliation / compatibility matrix — not needed with single-pin approach.
- Multi-version side-by-side install — not needed.
