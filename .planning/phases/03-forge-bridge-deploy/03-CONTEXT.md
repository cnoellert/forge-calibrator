# Phase 3: forge-bridge Deploy - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire `install.sh` to deploy the forge-bridge Flame hook alongside the Camera Match hook, so a fresh install gives the user a working `127.0.0.1:9999` bridge on Flame boot without any separate setup step. BRG-01/02/03 are already satisfied by the forge-bridge sibling repo's own design (`flame_hooks/forge_bridge/scripts/forge_bridge.py` launches as a Flame-spawned subprocess on hook load, dies when Flame quits, binds 127.0.0.1 only — all of this already works in this session). **BRG-04 is the new work:** our `install.sh` must invoke forge-bridge's own `install-flame-hook.sh` so downstream machines don't have to do a separate install step.

**Scope boundaries (locked):**
- No new process-management code. forge-bridge owns its own lifecycle (Flame's hook registers the subprocess; the bridge handles its own shutdown path). We do NOT reimplement any of that.
- No changes to `flame/camera_match_hook.py`. The hook already hits `http://127.0.0.1:9999/exec` in Phase 2's transport layer — that contract stays.
- No changes to `forge_sender/` addon or `forge_flame/` code — Phase 3 is pure install wiring.
- No vendoring or git-submodule of forge-bridge. We integrate as a production dependency per PROJECT.md Context §4 ("this milestone integrates it as a production dependency but doesn't own its internals").
- Smoke-testing BRG-01/BRG-02 live (Flame boots → bridge listens; Flame quits → no orphan) is part of **Phase 4's E2E smoke test**, not Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Install source strategy

- **D-01:** `install.sh` resolves forge-bridge's installer in this priority:
  1. **Explicit override:** `FORGE_BRIDGE_REPO` env var (absolute path to a local clone) — use that clone's `scripts/install-flame-hook.sh`.
  2. **Sibling clone auto-detect:** look for `../forge-bridge/`, then `$HOME/Documents/GitHub/forge-bridge/`, then `$HOME/code/forge-bridge/`. First one found wins.
  3. **Curl fallback:** `curl -fsSL https://raw.githubusercontent.com/cnoellert/forge-bridge/${FORGE_BRIDGE_VERSION}/scripts/install-flame-hook.sh | bash` using the pinned version from D-02.
- **D-02 (Claude's Discretion):** env var name is `FORGE_BRIDGE_REPO` (path) — NOT `FORGE_BRIDGE_LOCAL`. Keeps symmetry with `FORGE_BRIDGE_VERSION` and is unambiguous about what it points at.
- **D-03:** When the local clone path is used, print `[forge-bridge] using local clone at {path}` so the user knows which copy got deployed. When curl is used, print `[forge-bridge] fetching {VERSION} from GitHub`. No silent magic.

### Version pinning

- **D-04:** `install.sh` defines a top-of-file constant `FORGE_BRIDGE_VERSION="v1.1.0"` (or whatever tag is current at Phase 3 execution time — confirm with the sibling repo before writing). Upgrading requires a code change + review.
- **D-05:** The pinned version is passed to the bridge's installer via the `FORGE_BRIDGE_VERSION` env var when invoking its script (the bridge's installer already reads this var per `install-flame-hook.sh` header).
- **D-06 (Claude's Discretion):** Local-clone path does NOT override the version pin — when using a local clone, the clone's current HEAD is what gets deployed, and a `[forge-bridge] local clone version: {tag or HEAD SHA}` info line is printed. Pin-vs-clone drift is a known trade-off of dev-friendly install; we surface it rather than enforce.

### Install sequencing inside install.sh

- **D-07:** Bridge install runs **BEFORE** the Camera Match hook + `forge_core` / `forge_flame` / `tools/blender/` sync steps. Rationale: if the bridge fails to install, the user sees "forge-bridge install failed" before "hook installed but bridge unreachable" — clearer failure semantics. Order is: `preflight → forge-bridge install → camera_match + forge_core + forge_flame + tools/blender sync → stub __init__.py → purge __pycache__`.
- **D-08 (Claude's Discretion):** Add a new `> forge-bridge` section header to install.sh's output alongside the existing `> Install` and `> forge_core + forge_flame` sections, so the output flow is readable.

### Failure handling

- **D-09:** If the bridge install fails for any reason (local clone missing AND curl fails, permission denied, sanity check fails), **install.sh warns + continues** rather than aborting. The rest of the install (Camera Match hook + `forge_core` / `forge_flame` / Blender tools) still deploys because VP-solve + static JSON round-trip (v6.2 features) still work without the bridge.
- **D-10:** The warning output is explicit and actionable: `[WARN] forge-bridge install skipped (${reason}). VP-solve and v6.2 static round-trip still work. v6.3 Send-to-Flame will fail with "forge-bridge not reachable at http://127.0.0.1:9999" until the bridge is deployed. To retry: FORGE_BRIDGE_REPO=<path> ./install.sh   OR   curl -fsSL https://raw.githubusercontent.com/cnoellert/forge-bridge/v1.1.0/scripts/install-flame-hook.sh | bash`.
- **D-11:** The install.sh exit code reflects the OVERALL install state — if Camera Match itself installs fine and only bridge fails, exit 0 with the warning. If Camera Match fails too, exit non-zero. The bridge is NOT a hard prerequisite for the legacy features.

### Scope boundary enforcement

- **D-12:** install.sh's `--dry-run` mode must show the bridge install step without executing it. The bridge's own installer has no `--dry-run`, so dry-run mode prints `[dry-run] would execute: {resolved installer path or curl command}` and skips.
- **D-13:** install.sh's `--force` mode must propagate to the bridge install — when `--force` is set, delete any existing `/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` before invoking the bridge installer so it overwrites cleanly. (The bridge's installer uses plain `cp` which will overwrite anyway, but the explicit `rm -f` makes intent unambiguous for anyone reading install.sh.)

### Verification

- **D-14:** install.sh does NOT attempt a live bridge smoke test (i.e., it does NOT start Flame and curl 127.0.0.1:9999). Verification-that-it-actually-runs is deferred to Phase 4's E2E smoke test. Phase 3's verification is strictly "the hook file exists at the expected path after install and is parseable as Python."
- **D-15:** Bridge install success is confirmed via a post-install ls check: `test -f /opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py && python3 -c "ast.parse(open(\"${path}\").read())"`. Matches the sanity check the bridge's installer already does. If either fails, classify as bridge-install-failed per D-09.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Authority docs
- `.planning/PROJECT.md` §Key Decisions ("forge-bridge as Flame-spawned subprocess (Option B)"; "forge-bridge is being broken out... this milestone integrates it as a production dependency but doesn't own its internals") — defines the Phase 3 integration stance.
- `.planning/REQUIREMENTS.md` §Bridge (BRG-01..BRG-04) — the four requirements this phase closes.
- `.planning/ROADMAP.md` §Phase 3 — phase goal + success criteria.

### forge-bridge sibling repo (authoritative — read at plan time to confirm paths and behaviors)
- `~/Documents/GitHub/forge-bridge/scripts/install-flame-hook.sh` — the installer we invoke. Honors `FORGE_BRIDGE_VERSION` + `FORGE_BRIDGE_HOOK_DIR` env vars.
- `~/Documents/GitHub/forge-bridge/flame_hooks/forge_bridge/scripts/forge_bridge.py` — the hook that gets deployed. Already handles subprocess spawn, 127.0.0.1 binding, clean shutdown — BRG-01/02/03 are satisfied by this file's existing design.
- `~/Documents/GitHub/forge-bridge/README.md` — broader forge-bridge vision (vocabulary, dep graph, channel manager). Informative context; not directly referenced by Phase 3's scope.

### Existing install.sh patterns (preserve, don't disturb)
- `install.sh` (this repo) — specifically the preflight section (lines 1-40), the `> Install` / `> forge_core + forge_flame` section headers, and the `--dry-run` / `--force` / `--install-dir` flag handling. Phase 3 adds a new section; it does not rewrite the existing flow.
- `.planning/codebase/STRUCTURE.md` §Install topology — documents `/opt/Autodesk/shared/python/` layout that bridge install must coexist with.

### Prior phase context (carries forward)
- `.planning/phases/02-blender-addon/02-CONTEXT.md` §Transport tier + D-12 — the existing "bridge unreachable" popup is the runtime fallback if Phase 3's install fails. Phase 3 doesn't need to build any runtime recovery.
- `.planning/phases/02-blender-addon/02-04-SUMMARY.md` §D-17 vs D-19 trail — the bridge is used for payload exec only; no Flame-side frame-rate probing anywhere in the live stack.

### Memory docs
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge.md` — earlier bridge payload contract (superseded by `flame_bridge_probing.md`'s 2026-04-19 update).
- `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/flame_bridge_probing.md` — current payload contract and probing discipline.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `install.sh` — the only file being modified in this phase. Has existing `--dry-run` / `--force` / `--install-dir` flag handling, preflight checks (conda env, Wiretap CLI, OCIO config), and a section-header pattern (`> Install`, `> forge_core + forge_flame`, `> Done`) that Phase 3 follows for consistency.
- Environment override pattern established in install.sh: variables read from env first, defaults second (see existing `FORGE_ENV`, `INSTALL_DIR` handling). Phase 3 adds `FORGE_BRIDGE_REPO` and `FORGE_BRIDGE_VERSION` following the same convention.

### Established Patterns
- **Sibling-dir package layout:** `camera_match/`, `forge_core/`, `forge_flame/`, `tools/blender/` all ship as siblings under `/opt/Autodesk/shared/python/`. The forge-bridge hook at `/opt/Autodesk/shared/python/forge_bridge/scripts/forge_bridge.py` is consistent with this layout — no new topology.
- **Sanity-check-after-copy:** existing install.sh runs a `python3 -c "import ast; ast.parse(...)"` check on copied files. The bridge's installer does the same for forge_bridge.py — no new pattern needed, just propagate the result.
- **Print-not-exec in dry-run:** existing install.sh's `--dry-run` prints actions without executing. Phase 3's bridge-install step follows the same convention (D-12).

### Integration Points
- **Install.sh invocation of external script:** the bridge's `install-flame-hook.sh` becomes the first external script our install.sh calls out to. No other part of install.sh shells out to external installers today — this is a new category, but it's narrow (one installer, one known contract).
- **Network dependency:** curl fallback introduces a net-required install path. Existing install.sh has no network dependencies (all sources are local files). Phase 3 documents this in D-10's warning copy so users on air-gapped machines understand the failure mode.

</code_context>

<specifics>
## Specific Ideas

- User explicitly challenged whether forge-bridge is necessary at all before locking this direction (see session transcript 2026-04-21). Confirmed: forge-bridge stays external per PROJECT.md's stance that it's "broken-out infrastructure" used beyond Camera Match. Inlining (~200-300 LOC bridge module into camera_match_hook) was considered and explicitly rejected for this milestone. This decision is logged here so future phases don't re-litigate it.
- The recommended "preferred local clone" path (D-01) was motivated by observed workflow: during Wave 2-4 execution, the user iterated on forge-bridge code in the sibling repo. A curl-only install.sh would have pulled stale tagged versions during dev. Local-clone-first preserves the fast feedback loop.
- Version pin default `v1.1.0` is the tag observed in the sibling repo's install-flame-hook.sh header at the time this CONTEXT.md was written. The planner should re-check the sibling repo's current latest tag before writing install.sh — if it's advanced, use the newer pin.

</specifics>

<deferred>
## Deferred Ideas

- **BRG-02 live verification (start Flame → curl 127.0.0.1:9999 → kill Flame → verify no orphan)** — deferred to Phase 4's E2E smoke test. Phase 3 trusts forge-bridge's own shutdown design.
- **Bridge crash recovery UX** (restart bridge when it dies mid-session) — Phase 2's Transport Tier popup already handles this at the client layer. Any additional recovery (e.g., a "Retry bridge" button in the Forge panel) is v2 scope.
- **Bridge logging destination** (stdout/stderr landing location, rotation, etc.) — not in Phase 3 scope. forge-bridge's internal design owns this. If debugging requires better logs, that's a forge-bridge repo change, not a Camera Match change.
- **Inline bridge (Alternative B from discussion)** — keep forge-bridge external per this phase's decision. If Camera Match remains the only production consumer 6-12 months from now, revisit as a separate initiative.
- **Version reconciliation / compatibility matrix** between Camera Match hook and forge-bridge hook versions — out of scope for this milestone. The pinned version in install.sh is the only coupling, and upgrading is a manual code-review step.
- **Multi-version install (keep v1.0 + v1.1 bridges side-by-side)** — not needed. Single pinned version.

</deferred>

---

*Phase: 03-forge-bridge-deploy*
*Context gathered: 2026-04-22*
