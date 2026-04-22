# forge-calibrator

## What This Is

A vanishing-point camera calibration tool that lives inside Autodesk Flame. A VFX artist draws 2-3 reference lines along orthogonal scene edges in a plate; the tool solves a camera (position, rotation, FOV, focal length) and applies it to a Flame Action node. Recent work (v6.x) extends this with a Flame↔Blender camera round-trip so solved cameras — static or animated — can be refined in Blender and returned to Flame.

## Core Value

**The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.** Everything else — UX polish, seamless workflows, automation — is secondary. If the numbers are wrong, the compositing CG won't glue to the plate and the tool fails its purpose.

## Requirements

### Validated

<!-- Shipped and confirmed valuable across v1.0 → v6.2. -->

- ✓ User can draw 2 or 3 vanishing-point lines on a plate and produce a Flame camera solve — shipped v1-v4
- ✓ Per-line residual labels (`Δ<N>px`) shown in 3-line mode to surface which lines disagree with the fit — v4
- ✓ Apply solved camera to a user-picked Action camera, with optional axis drops at VP line endpoints — v4
- ✓ Wiretap-based single-frame media reader handling Sony / ARRI MXF plus auto-detected source colour space — v4 (replaces broken PyExporter path)
- ✓ ACES 2.0 OCIO `DisplayViewTransform` preview with soft highlight rolloff — v4
- ✓ `install.sh` with preflight checks for forge conda env, Wiretap CLI, Flame-bundled PyOpenColorIO, and a resolvable OCIO config — v5
- ✓ `forge_core` / `forge_flame` package split — host-agnostic math (numpy-only) importable from any host, Flame-specific adapters isolated — v5
- ✓ Flame ↔ Blender static camera round-trip via v5 JSON contract, validated to float32 precision — v6.0
- ✓ Batch UI menu wired: "Open Camera Match" (clip scope), "Export / Import Camera to/from Blender" (Action scope) — v6.1
- ✓ Animated camera round-trip via custom ASCII FBX parser + writer (`forge_flame/fbx_ascii.py`), Flame export via `action.export_fbx(bake_animation=True)` with Perspective camera excluded, import via `action.import_fbx` — v6.2
- ✓ 264-test pytest suite covering solver math, FBX parser/writer, hook parity, Blender bridge CLI composition, image buffer decoding, OCIO pipeline — ongoing

### Active

<!-- This milestone: seamless Blender↔Flame bridge. -->

- [ ] Right-click Action → Blender opens on target camera, zero-dialog export (plate resolution inferred from the Action node itself)
- [ ] Intermediate files (`.fbx`, `.json`) written to a temp directory and cleaned on success; only the `.blend` remains visible to the user
- [ ] Camera custom-properties stamped on export (`forge_bake_action_name`, `forge_bake_camera_name`, etc.) so the return trip knows which Flame Action to target
- [ ] Blender addon with a "Send to Flame" sidebar panel button; reads stamped metadata, extracts the camera, POSTs the import to forge-bridge
- [ ] forge-bridge ingests the POSTed JSON, runs the FBX conversion + `import_fbx` inside Flame, user sees the new camera in the target Action
- [ ] forge-bridge auto-starts as a Flame-spawned subprocess — Flame's init hook launches it on boot, it dies when Flame quits
- [ ] `install.sh` extended to deploy the forge-bridge launcher alongside the hook
- [ ] Blender launch behaviour configurable in `.planning/config.json` (focus-steal on/off); default off

### Out of Scope

<!-- Explicit boundaries — things a reasonable observer might propose but we're deliberately not building. -->

- **Lights / meshes / materials in the FBX round-trip** — camera only. Other scene elements bloat the FBX, complicate the parser, and aren't the problem this tool exists to solve.
- **Real-time bidirectional sync between Flame and Blender** — save-and-trigger is fine. Continuous sync would need websockets and invite more failure modes than it solves.
- **Blender viewport colour matching to Flame's plate display** — users can load a reference plate manually if needed. OCIO config matching across hosts is its own large project.
- **Multi-user / shared-workstation auth on forge-bridge** — single-user local workstation is the target. Bridge listens only on `127.0.0.1`.
- **Windows support** — Flame doesn't run on Windows; macOS + Linux only.
- **Replacing the single-frame JSON path** for the static export — v5 JSON contract stays. Animated path uses FBX; static can continue via JSON for back-compat and debugging.

## Context

- **Brownfield at v6.2.** PASSOFF.md at repo root has a detailed v4 → v6.2 history with session recaps. Codebase map in `.planning/codebase/` (STACK, ARCHITECTURE, STRUCTURE, CONVENTIONS, TESTING, INTEGRATIONS, CONCERNS).
- **Rich gotcha memory** at `~/.claude/projects/-Users-cnoellert-Documents-GitHub-forge-calibrator/memory/`: Flame rotation convention (verified via FBX export), module reload pitfalls (menu cache caveat), Wiretap single-frame-read recipe (GBR byte order), Perspective camera exclusion rule, PyAttribute-has-no-keyframe-API finding, forge-bridge probing discipline.
- **Known fragility:** `flame/camera_match_hook.py` is a 2100-line monolith; Flame's batch-menu dict is captured at hook-registration time and requires a full Flame restart to refresh (not a programmatic reload).
- **forge-bridge is being broken out** into its own standalone repo (multipurpose HTTP endpoint into Flame's Python, used beyond Camera Match). This milestone integrates it as a production dependency but doesn't own its internals.
- **Live-validated** on Flame 2026.2.1 during the v6.2 session: synthetic v5 JSON → FBX writer → `action.import_fbx` produced a camera matching input position / rotation / focal within float32 precision.

## Constraints

- **Tech stack**: Python 3.11 (Flame-bundled) for production code. FBX Python SDK wheel ships cp310-only — not usable in-process. Blender 4.5's FBX importer rejects ASCII FBX — motivates the custom parser in `forge_flame/fbx_ascii.py`.
- **Runtime dependencies**: numpy + opencv-python in a conda `forge` env (dev-side); PyOpenColorIO from Flame's bundled Python (NOT installed in forge — version-conflict risk); Wiretap SDK from Flame; Blender 4.5+ as a subprocess; forge-bridge as the HTTP RPC endpoint into Flame's Python.
- **Platform**: macOS + Linux. Windows unsupported (Flame doesn't run there).
- **Compatibility**: Flame 2026.2.1 is the primary target. Older Flame versions untested; newer versions may need API re-verification.
- **Performance (non-goal this milestone)**: Wiretap single-frame reads run ~1.5s for a 4K 32-bit float MXF. Not on the hot path for this milestone's scope.
- **Security posture**: Internal VFX post-production tool. No user-facing auth surface; artifacts live on trusted storage. forge-bridge binds to `127.0.0.1` only.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Animated camera I/O routes through ASCII FBX, not PyAttribute keyframing | PyAttribute has no keyframe API (confirmed live; only `get_value` / `set_value` / `values`-as-bounds). `PyActionNode.export_fbx(bake_animation=True)` is the only programmatic route to animated camera data. | ✓ Good — shipped v6.2 |
| Ship a custom ASCII FBX parser + writer (`forge_flame/fbx_ascii.py`) instead of adopting the FBX SDK | Blender rejects ASCII FBX; Autodesk FBX Python SDK wheel is cp310-only and Flame is 3.11; assimp isn't installed. | ✓ Good — shipped v6.2, ~900 LOC, 51 tests |
| Template-driven FBX writer using a live Flame export as structural template (`forge_flame/templates/camera_baked.fbx`) | Mutating a known-accepted file is lower-risk than authoring FBX structure from first principles; inherits Flame's exact Definitions / Connections shape so `import_fbx` accepts our output without fuss. | ✓ Good — round-trip validated live |
| Keep v5 JSON contract as the bridge between FBX converters and Blender's existing `bake_camera.py` / `extract_camera.py` | Blender side is already multi-frame-capable on JSON; swapping to direct FBX in Blender would rewrite more than it saves, and Blender can't read ASCII FBX anyway. | ✓ Good — Blender scripts unchanged in v6.2 |
| Menu handler changes require a full Flame restart to take effect | Flame caches the `get_batch_custom_ui_actions()` return at hook-registration time; no programmatic reload API exists. The `gc` / `exec` reload pattern refreshes module globals but NOT Flame's cached dispatch table. | ⚠️ Revisit — only matters for dev iteration speed; shipped behaviour is fine |
| forge-bridge as Flame-spawned subprocess (Option B from the milestone design) rather than login daemon | Lifecycle aligned with Flame's session; no orphan bridge processes; no launchd / systemd install complexity; simpler `install.sh`. | — Pending (this milestone) |
| Blender auto-launch will default to no-focus-steal, configurable in `.planning/config.json` | User's stated preference; respects macOS focus etiquette; configurable escape hatch for users who'd rather see Blender immediately. | — Pending (this milestone) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-22 after Phase 4 (E2E Validation + Docs) — README.md + docs/seamless-bridge.md + tools/smoke-test/seamless-bridge-smoke.sh delivered; DOC-02 closed. DOC-01 runtime closure deferred to after Phase 4.1 empty-camera-bake UX fix (pre-existing Phase 1/2 bug surfaced by smoke test Test 1 on fresh Camera Match solve).*
