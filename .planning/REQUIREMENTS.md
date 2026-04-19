# Requirements: forge-calibrator — Seamless Blender↔Flame Bridge (v6.3)

**Defined:** 2026-04-19
**Core Value:** The solved camera must be geometrically faithful to the plate, and the Flame↔Blender round-trip must preserve that fidelity end-to-end.

## v1 Requirements

Scoped requirements for this milestone. Each maps to a roadmap phase via Traceability below.

### Export (EXP) — Zero-dialog Flame → Blender handoff

- [ ] **EXP-01**: Right-click Action → Blender launches on the target camera with zero dialogs (no WxH prompt, no save-path prompt)
- [ ] **EXP-02**: Plate resolution inferred automatically from the Action node's `resolution` PyAttribute (no user confirmation required)
- [ ] **EXP-03**: Intermediate files (`.fbx`, `.json`) written to a `tempfile.mkdtemp()` directory that's removed on successful export; only the `.blend` remains user-visible
- [ ] **EXP-04**: Camera custom properties stamped on export (`forge_bake_action_name`, `forge_bake_camera_name`, anything else the return-trip addon needs to identify the target Flame Action + camera)
- [ ] **EXP-05**: Blender launch behaviour configurable in `.planning/config.json` (`blender_launch_focus_steal: bool`); defaults to `false` (Blender launches in background, user alt-tabs when ready)

### Import (IMP) — "Send to Flame" trigger from Blender

- [ ] **IMP-01**: Blender addon with a "Send to Flame" button in the 3D viewport's N-panel sidebar; installable via standard Blender addon install flow
- [ ] **IMP-02**: Addon reads stamped metadata from the active camera's custom properties (`forge_bake_action_name`, `forge_bake_camera_name`) — surfaces an error if metadata absent
- [ ] **IMP-03**: Addon extracts the camera's per-frame T / R / focal / film-back to the v5 JSON contract (same shape `tools/blender/extract_camera.py` already produces)
- [ ] **IMP-04**: Addon POSTs to forge-bridge at `http://127.0.0.1:9999/exec` with code that runs `forge_flame.fbx_ascii.v5_json_to_fbx` + `forge_flame.fbx_io.import_fbx_to_action` inside Flame's Python, targeting the stamped Action name
- [ ] **IMP-05**: forge-bridge executes the payload inside Flame and returns a structured response (success + created camera name(s) OR error + traceback) that the addon surfaces in a Blender info popup
- [ ] **IMP-06**: User never has to alt-tab to Flame's menu to trigger the import — clicking "Send to Flame" in Blender is the complete trigger

### Bridge (BRG) — forge-bridge production lifecycle

- [ ] **BRG-01**: forge-bridge auto-starts as a Flame-spawned subprocess when the Camera Match hook initialises (Flame boot triggers it)
- [ ] **BRG-02**: Bridge process dies cleanly when Flame quits — no orphan processes, no port conflicts on the next Flame boot
- [ ] **BRG-03**: Bridge binds to `127.0.0.1` only (single-user, local workstation; never exposes Flame's Python surface to the network)
- [ ] **BRG-04**: `install.sh` deploys the forge-bridge launcher alongside the Camera Match hook so a fresh install wires the production bridge without extra user steps

### Docs (DOC) — End-to-end validation + user-facing docs

- [ ] **DOC-01**: E2E smoke test passes on Flame 2026.2.1 + Blender 4.5+: right-click Action → edit camera in Blender → click "Send to Flame" → new camera appears in the target Action, with keyframes preserved — entire loop without visiting Flame's batch menu for the return trip
- [ ] **DOC-02**: User-facing doc (README section or standalone `docs/seamless-bridge.md`) covering: what changed from v6.2, how to install the Blender addon, how the forge-bridge autostart works, troubleshooting recipes (bridge not running, addon not seeing camera metadata, etc.)

## v2 Requirements

Deferred beyond this milestone. Tracked here so they're not forgotten.

### Multi-cam / scene-wide round-trip

- **MULT-01**: Round-trip multiple cameras from an Action in one operation
- **MULT-02**: Round-trip lights / Axis nodes as an opt-in
- **MULT-03**: Round-trip animated null targets (e.g., Perspective.Target-style helpers)

### Workflow polish

- **POLISH-01**: "Last .blend per Action" memory so Import can default to the most recently exported file without a file dialog
- **POLISH-02**: Stamp bridge + hook versions into the FBX/.blend custom properties for forensic debugging of older round-trips
- **POLISH-03**: macOS Finder / Linux file-manager integration hints (e.g., open the .blend's containing folder on user request)

## Out of Scope

Explicit exclusions. Keeping them here prevents scope creep and invites explicit scope changes rather than silent expansion.

| Feature | Reason |
|---------|--------|
| Lights / meshes / materials in the FBX round-trip | Camera only. Other scene elements bloat the FBX parser and aren't the problem this tool solves. |
| Real-time bidirectional sync between Flame and Blender | Save-and-trigger is fine. Continuous sync adds websocket infra + failure modes without a clear user win. |
| Blender viewport colour matching to Flame's plate display | OCIO-across-hosts is a separate project; users can load reference plates manually in Blender. |
| Multi-user / shared-workstation auth on forge-bridge | Single-user local workstation is the target. Bridge binds `127.0.0.1` only; no auth needed. |
| Windows support | Flame doesn't run on Windows. Not a platform we target. |
| Replacing the single-frame JSON path entirely | v5 JSON contract stays for static exports. Animated goes FBX. Two paths is fine — JSON is simple + debuggable. |
| Public distribution as a general-purpose Flame-Blender plugin | This tool is internal to the forge ecosystem. If it spreads, the deploy story (install.sh) would need redesign. |

## Traceability

Empty at requirements-definition time. Populated during roadmap creation (Step 8).

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXP-01 | TBD | Pending |
| EXP-02 | TBD | Pending |
| EXP-03 | TBD | Pending |
| EXP-04 | TBD | Pending |
| EXP-05 | TBD | Pending |
| IMP-01 | TBD | Pending |
| IMP-02 | TBD | Pending |
| IMP-03 | TBD | Pending |
| IMP-04 | TBD | Pending |
| IMP-05 | TBD | Pending |
| IMP-06 | TBD | Pending |
| BRG-01 | TBD | Pending |
| BRG-02 | TBD | Pending |
| BRG-03 | TBD | Pending |
| BRG-04 | TBD | Pending |
| DOC-01 | TBD | Pending |
| DOC-02 | TBD | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 0 (roadmap pending)
- Unmapped: 17 ⚠️ (will resolve when roadmap lands)

---
*Requirements defined: 2026-04-19*
*Last updated: 2026-04-19 after initial definition*
