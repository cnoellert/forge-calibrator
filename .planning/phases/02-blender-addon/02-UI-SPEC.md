---
phase: 2
slug: blender-addon
status: approved
shadcn_initialized: false
preset: none
created: 2026-04-21
reviewed_at: 2026-04-21
surface: blender-addon
---

# Phase 2 — UI Design Contract (Blender Addon)

> Visual and interaction contract for the "Send to Flame" Blender addon. The UI surface is a **native Blender N-panel** rendered through `bl_ui` primitives — no HTML, no CSS, no design tokens. All widget colors, fonts, borders, and spacing come from the artist's active Blender theme and are **out of scope** for this spec.
>
> Web-oriented dimensions in the standard template (spacing scale, typography, color palette, responsive breakpoints, motion) are marked **N/A — native Blender widgets** with a one-line rationale. The dimensions that matter here are: **panel layout, icon choices, report-level mapping, exact popup copy, and enabled/disabled interaction rules**.
>
> Authority: scope and all "locked" entries are pre-populated from [`02-CONTEXT.md`](./02-CONTEXT.md) D-09, D-10, D-14, D-15 and the `<additional_context>` passed to gsd-ui-researcher. Items marked "researcher default" are committed choices within Claude's Discretion areas of CONTEXT — the planner and executor should treat them as locked unless explicitly revisited.

---

## Design System

| Property | Value | Source |
|----------|-------|--------|
| Tool | none (Blender-native) | CONTEXT D-11 (directory package, no custom Qt surface) |
| Preset | not applicable | Native Blender UI; `bl_info` is the only preset metadata |
| Component library | `bpy.types.Panel` + `bpy.types.Operator` via `bl_ui` layout API | CONTEXT D-11 |
| Icon library | Blender built-in icon set (`ERROR`, `EXPORT`, `CAMERA_DATA`, `OUTLINER_OB_CAMERA`) | researcher default |
| Font | inherited from active Blender theme (no override) | Blender convention |
| Styling surface | `layout.row()`, `layout.label()`, `layout.operator()`, `self.report()`, `wm.popup_menu` / `wm.info` operators | CONTEXT D-09, D-14 |

**Cross-surface note:** the separate `memory/forge_ui_style.md` palette (`#E87E24` FORGE orange, `#282c34` bg, etc.) governs the **Flame-side PySide2 dialogs** (e.g. the Camera Match window in `flame/camera_match_hook.py`). It does **not** apply to this phase — mixing a custom palette into a Blender N-panel would break the artist's theme and is explicitly out of scope.

---

## Spacing Scale

**N/A — native Blender widgets.** Row spacing is produced by `layout.row()` / `layout.separator()` primitives and respects the active Blender theme's padding. No pixel values are ours to set.

Exceptions: none. The only layout call that deviates from stock row stacking is a single `layout.separator()` between the two metadata label rows and the Send button (see "Panel Layout Contract" below) — this is Blender idiomatic, not a custom spacing token.

---

## Typography

**N/A — native Blender widgets.** All text renders through `layout.label()` / `layout.operator()` at the theme's default font size and weight. Bold / italic / color overrides are intentionally **not** used: they visually detach the panel from its sibling addons in the N-panel and confuse artists who expect standard Blender behavior.

Exceptions: none.

---

## Color

**N/A — native Blender widgets.** Widget colors (panel background, row highlight, button accent, disabled foreground) are derived from the user's active Blender theme. The addon makes exactly one color-adjacent call — `row.alert = True` on the disabled-state warning row (D-15) — which tells Blender to render the row in its theme-defined "warning red" color. This is a theme-respecting affordance, not a custom color.

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | Blender theme N-panel bg | inherited |
| Secondary (30%) | Blender theme row bg | inherited |
| Accent (10%) | Blender theme `row.alert` color | disabled-state warning row only (D-15) |
| Destructive | N/A — no destructive actions in this phase | Send is a one-way push that the bridge validates; nothing is deleted |

Accent reserved for: the single `row.alert = True` warning row shown when preflight Tier 1 fails (no active camera / missing metadata / wrong provenance). Never applied to the Send button or metadata rows.

---

## Panel Layout Contract

The N-panel lives in the 3D Viewport sidebar under the tab `Forge` (CONTEXT D-14). It contains exactly one `bpy.types.Panel` subclass — no sub-panels, no collapsible sections in v1.

**Panel identity:**

| Attribute | Value | Source |
|-----------|-------|--------|
| `bl_label` | `"Send to Flame"` | researcher default — matches the primary CTA verb |
| `bl_idname` | `"VIEW3D_PT_forge_sender"` | Blender naming convention: `{SPACE}_PT_{unique}` |
| `bl_space_type` | `'VIEW_3D'` | IMP-01 (3D viewport sidebar) |
| `bl_region_type` | `'UI'` | N-panel region |
| `bl_category` | `"Forge"` | CONTEXT D-14 |
| `bl_order` | `0` (explicit) | researcher default — future Forge tools may add panels in the same tab; `bl_order` reserves slot 0 for the Send panel so it stays top-most on install |

**Row order (top-to-bottom) — valid camera (happy path):**

| # | Element | Blender call | Icon | Enabled |
|---|---------|--------------|------|---------|
| 1 | Action label row | `layout.label(text=f"Target Action: {action_name}", icon='OUTLINER_OB_CAMERA')` | `OUTLINER_OB_CAMERA` | n/a (label) |
| 2 | Camera label row | `layout.label(text=f"Target Camera: {camera_name}", icon='CAMERA_DATA')` | `CAMERA_DATA` | n/a (label) |
| 3 | Separator | `layout.separator()` | — | n/a |
| 4 | Send button | `layout.operator("forge.send_to_flame", icon='EXPORT')` | `EXPORT` | see `poll()` rules below |

**Row order — preflight Tier 1 failure (disabled state, per D-15):**

| # | Element | Blender call | Icon | Enabled |
|---|---------|--------------|------|---------|
| 1 | Warning row | `row = layout.row(); row.alert = True; row.label(text="Not a Flame-baked camera", icon='ERROR')` | `ERROR` | n/a (label) |
| 2 | Separator | `layout.separator()` | — | n/a |
| 3 | Send button (disabled) | `layout.operator("forge.send_to_flame", icon='EXPORT')` | `EXPORT` | **disabled** — operator `poll()` returns `False` |

**Icon choices — committed defaults** (Claude's Discretion per CONTEXT §Claude's Discretion):

| Icon name | Where | Rationale |
|-----------|-------|-----------|
| `EXPORT` | Send button | Matches the "pushing data out of Blender to Flame" semantic; the alternative `PLAY` implies a render/playback action, and `TRIA_RIGHT` is used for expanders. `EXPORT` is Blender's canonical "write out / send" glyph and reads correctly at N-panel width. |
| `ERROR` | Disabled warning row | Standard Blender red-triangle glyph; reinforces the `row.alert = True` color semantic. |
| `OUTLINER_OB_CAMERA` | Target Action label | Visually distinguishes the Action row from the Camera row without hijacking the camera-data glyph. Pairs the label with a "node / scene object" metaphor. |
| `CAMERA_DATA` | Target Camera label | Blender's standard camera-data-block glyph; signals "this is the data-block that will be walked for keyframes". |

**Disabled-state styling (D-15):** use `row.alert = True` on the warning label row. The Send button's disabled appearance comes automatically from the operator `poll()` returning `False` — do **not** additionally set `button.enabled = False` on the layout (the poll path is canonical and handles keyboard / API access paths the layout flag misses).

**Operator `poll()` rules** — the Send button is enabled iff **all** of:

1. `context.active_object is not None`
2. `context.active_object.type == 'CAMERA'`
3. `"forge_bake_action_name" in context.active_object.data`
4. `"forge_bake_camera_name" in context.active_object.data`
5. `context.active_object.data.get("forge_bake_source") == "flame"`

These are the five conditions behind D-09 Tier 1 (a)–(d). Any failure disables the button and swaps the panel into the disabled-state row order above. Preflight runs the same checks again inside `execute()` so a keyboard-invoked operator (F3 search, custom keymap) can't bypass the panel gate — belt-and-braces, matching the two-layer pattern in `bake_camera._stamp_metadata` (reserved-key reject + write-last belt-and-braces per CLAUDE.md).

**Out of scope for v1 panel** (deferred per CONTEXT §Deferred):
- Target-Action override input field
- Frame-range display
- Bridge-status indicator
- Version badges
- Any sub-panels or collapsible sections
- Multi-camera send UI

---

## Copywriting Contract

All strings below are **exact**. Placeholder substitutions use Python f-string syntax (`{action_name}`, `{camera_name}`, `{missing_key}`, `{created_name}`, `{error}`, `{traceback}`). No ellipses, no sentence-ending period on popup bodies (matches Blender's built-in report/info style), em-dash separator between cause and action hint.

**Convention notes:**
- No jargon: "Action" and "camera", never "PyActionNode" or "PyAttribute" (CONTEXT §Specifics).
- Missing-metadata tier names the missing key **verbatim** (IMP-02 literal requirement; D-09 Tier 1c).
- Transport tier includes the bridge URL verbatim (CONTEXT §Claude's Discretion).
- Remote tier includes Flame's traceback verbatim (CONTEXT §Claude's Discretion, D-09 Tier 3).
- Line-break convention in multi-line popups: single `\n` for soft wrap inside a paragraph; double `\n\n` to separate the one-line summary from a multi-line traceback.

### Panel labels

| Element | Copy |
|---------|------|
| Panel title (`bl_label`) | `Send to Flame` |
| Target Action row | `Target Action: {action_name}` |
| Target Camera row | `Target Camera: {camera_name}` |
| Disabled warning row (D-15) | `Not a Flame-baked camera` |
| Send button label | `Send to Flame` |

### Success popup (D-10)

| Field | Value |
|-------|-------|
| Surface | `self.report({'INFO'}, ...)` **plus** `bpy.ops.wm.info` popup with the same body |
| Report level | `'INFO'` — success is not an error or warning |
| Copy | `Sent to Flame: camera '{created_name}' in Action '{action_name}'` |

If the bridge returns more than one created camera name (edge case — `import_fbx_to_action` returns a list), join with `, ` and pluralize: `Sent to Flame: cameras '{name_a}', '{name_b}' in Action '{action_name}'`.

### Preflight Tier 1 — addon-side, before POST (D-09.1)

All preflight failures use `self.report({'ERROR'}, ...)` **plus** a blocking popup via `bpy.ops.wm.popup_menu` with a single-line title. Report level is `'ERROR'` across all four sub-tiers — each is a hard stop, not a warning.

| Sub-tier | Trigger | Copy |
|----------|---------|------|
| (a) | `context.active_object is None` | `Send to Flame: no active object — select a forge-baked camera in the 3D viewport and try again` |
| (b) | `context.active_object.type != 'CAMERA'` | `Send to Flame: active object is not a camera — select a forge-baked camera in the 3D viewport and try again` |
| (c) | `"forge_bake_action_name" not in cam.data` or `"forge_bake_camera_name" not in cam.data` | `Send to Flame: active camera is missing '{missing_key}' — this camera was not baked by forge-calibrator. Re-export from Flame via right-click → Camera Match → Export Camera to Blender` |
| (d) | `cam.data.get("forge_bake_source") != "flame"` | `Send to Flame: active camera was not baked by forge-calibrator (forge_bake_source != 'flame') — re-export from Flame via right-click → Camera Match → Export Camera to Blender` |

**`{missing_key}` substitution rule:** report the first missing key in the order `forge_bake_action_name`, `forge_bake_camera_name`. If both are missing, name only the first — the fix is the same either way (re-export) and listing both adds noise.

### Transport Tier — addon-side, POST failed (D-09.2)

| Field | Value |
|-------|-------|
| Surface | `self.report({'ERROR'}, ...)` **plus** `bpy.ops.wm.popup_menu` blocking popup |
| Report level | `'ERROR'` |
| Trigger | `requests.exceptions.ConnectionError` or `requests.exceptions.Timeout` (or `urllib.error.URLError` / `socket.timeout` on the urllib fallback path per CONTEXT D-13) |
| Copy | `Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Match hook loaded?` |

### Remote Tier — bridge returned `error` / `traceback` (D-09.3)

| Field | Value |
|-------|-------|
| Surface | `self.report({'ERROR'}, ...)` **plus** `bpy.ops.wm.popup_menu` blocking popup with a copy-paste-friendly monospace body (use `draw` callback that emits `layout.label(text=line)` per line so pipeline-TDs can screenshot or copy the traceback) |
| Report level | `'ERROR'` |
| Trigger | Bridge response contains a non-empty `error` field per `memory/flame_bridge.md` response envelope (`result`, `stdout`, `stderr`, `error`, `traceback`) |
| Copy | `Send to Flame failed: {error}\n\n{traceback}` |

**Traceback formatting:** preserve the traceback verbatim — do not strip leading/trailing whitespace, do not re-flow lines, do not translate Flame-side class names. The pipeline-TD audience relies on line-for-line fidelity for diagnosis (CONTEXT §Specifics: "artist / pipeline-TD audience"). If the traceback exceeds ~20 lines, still render it in full — Blender's popup scrolls.

**No per-exception-class parsing** on the addon side (D-09 Tier 3 explicit note). The addon surfaces whatever the bridge returns; the Flame Python stack is the source of truth.

### Bridge-returned error variants (covered by Remote Tier copy template)

These are the specific Flame-side errors the bridge will return for D-06 / D-07 (Target Action resolution) and D-17 / D-18 (frame-rate):

| Trigger (Flame side) | `error` field value |
|----------------------|---------------------|
| 0 Actions match stamped name (D-07) | `No Action named '{action_name}' in current batch — was it renamed or deleted?` |
| 2+ Actions match stamped name (D-07) | `Ambiguous: {N} Actions named '{action_name}' — rename to disambiguate and resend` |
| `flame.batch.frame_rate.get_value()` returns a string not in `_FPS_FROM_FRAME_RATE` (D-18) | `Unknown Flame batch frame rate: '{fps_string}' — expected one of {supported_list}` |
| `import_fbx_to_action` raises | Propagate Flame's native exception message as `error`; put the full stack in `traceback` |

These strings live on the **Flame side** of the bridge payload, not in the addon. The addon's contract is only: render whatever comes back via the Remote Tier template above. Listed here so the planner can encode them into the bridge-side Python and the tester can assert against them.

### Report-level matrix (consolidated)

| Surface | Report level | Popup op | Body copy source |
|---------|-------------|----------|------------------|
| Success (D-10) | `'INFO'` | `bpy.ops.wm.info` or equivalent | template above |
| Preflight Tier 1 (a, b, c, d) | `'ERROR'` | `bpy.ops.wm.popup_menu` | template above |
| Transport Tier | `'ERROR'` | `bpy.ops.wm.popup_menu` | template above |
| Remote Tier | `'ERROR'` | `bpy.ops.wm.popup_menu` with multi-line `draw` | template above |

**No `'WARNING'` level is used anywhere in this phase.** Every failure path is a hard stop that requires user action (re-select the camera, re-export from Flame, relaunch Flame, rename an Action, fix a frame rate). Softening any of these to `'WARNING'` would invite artists to ignore them — which violates the Core Value ("geometric fidelity trumps UX smoothness", CONTEXT §Specifics).

---

## Interaction Contract

| Stage | Trigger | Addon behavior |
|-------|---------|----------------|
| Idle | Panel drawn | Read `context.active_object.data` custom props; render happy-path or disabled-state rows per `poll()` result |
| Click Send | User clicks button (or F3 search → "Send to Flame") | Operator `execute()` runs preflight re-check → extract keyframes → POST to bridge → render success or failure popup |
| During POST | `requests.post(url, json=payload, timeout=5)` | Blender UI freezes for up to 5 s (D-16 sync operator). No progress indicator, no cancel button — sub-second typical round-trip makes async overhead not worth the bpy thread-safety cost |
| Success | Bridge returns envelope with no `error` field, non-empty result | Success popup (INFO) per D-10 |
| Failure | Any of Tier 1/2/3 triggers | Error popup (ERROR) per taxonomy above; operator returns `{'CANCELLED'}` |
| After failure | Next click | Fresh attempt — no rate-limiting, no "last error" banner in the panel. The panel returns to idle state immediately |

**Timeout UX (D-16):** 5 s is the initial default; if live validation shows the p99 round-trip exceeds 3 s, the planner may bump to 10 s (CONTEXT §Claude's Discretion). Do not adjust pre-emptively.

**Keyboard / API access:** the operator is registered with a stable `bl_idname` (`forge.send_to_flame`) so artists can bind it to a custom keymap or invoke it from F3 search without the N-panel visible. The same `poll()` gate blocks invocation in all access paths.

---

## Accessibility / Ergonomics

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Audience | VFX artists (primary) + pipeline TDs (error path) | CONTEXT §Specifics |
| Color-only signaling | Not used. `row.alert = True` always co-occurs with the `ERROR` icon | Accessible to artists on custom themes where "alert red" may be muted |
| Copy tone | Direct, imperative fix-hint after em-dash | Matches Phase 1 popup convention (`01-CONTEXT.md` D-15) |
| Copy-paste-able errors | Remote Tier renders traceback line-per-line via `layout.label()` in the popup `draw` callback | Pipeline TDs need verbatim line references for Flame-side debugging |
| Named missing keys | Tier 1(c) names `forge_bake_action_name` / `forge_bake_camera_name` verbatim | IMP-02 literal requirement |
| Named bridge URL | Tier 2 names `http://127.0.0.1:9999` verbatim | Pipeline TD can curl the URL to verify bridge liveness |
| Keyboard access | `bl_idname` stable; operator works from F3 search | Power users / keymap-heavy artists |
| Theme respect | No custom colors, no font overrides | Artists run light and dark Blender themes; hardcoding colors would break one or the other |

Dimensions intentionally not specified: responsive breakpoints (N/A — panel is fixed-width by Blender), motion / animation (N/A — no transitions), typography scale (N/A — theme-inherited), WCAG color contrast (N/A — theme-inherited), touch targets (N/A — desktop-only Blender).

---

## Component Inventory

Downstream (`gsd-planner`, `gsd-executor`) builds these components:

| Component | File | Class | Responsibility |
|-----------|------|-------|----------------|
| Panel | `tools/blender/forge_sender/__init__.py` or `panel.py` (Claude's Discretion per D-11) | `VIEW3D_PT_forge_sender(bpy.types.Panel)` | Draw N-panel rows per the Panel Layout Contract above |
| Operator | `tools/blender/forge_sender/__init__.py` or `operator.py` | `FORGE_OT_send_to_flame(bpy.types.Operator)` with `bl_idname="forge.send_to_flame"` | `poll()` + `execute()`; wires preflight → extract → transport → popup |
| Preflight helper | `tools/blender/forge_sender/preflight.py` | `def check(context) -> Optional[str]` | Returns `None` on pass, or one of the four Tier 1 copy strings on fail |
| Transport helper | `tools/blender/forge_sender/transport.py` | `def send(payload: dict) -> dict` | Wraps `requests.post`; raises on transport error; returns bridge response dict |
| Math helper | `tools/blender/forge_sender/flame_math.py` | reuses existing names from `extract_camera.py` | Shared Euler / axis-swap / keyframe-walk (D-04/D-05) |

**Naming pattern** (matches CLAUDE.md conventions):
- Panel class: `{SPACE}_PT_{unique}` → `VIEW3D_PT_forge_sender`
- Operator class: `{CATEGORY}_OT_{unique}` → `FORGE_OT_send_to_flame`
- `bl_idname` for operator: `forge.send_to_flame` (lowercase dot-notation; Blender operator ID convention)

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable — no shadcn on this phase |
| third-party | none | not applicable |

shadcn initialization gate: **skipped.** Tech stack for this phase is Blender's `bpy` Python API, not React/Next.js/Vite. Registry vetting is not applicable.

**Dependency safety note** (adjacent but not registry-gated): the addon depends on `requests` from Blender 4.5's bundled Python (D-13). If a future Blender bundle drops `requests`, the fallback is `urllib.request` (Python stdlib, no third-party risk). Never introduce a `pip install` step inside Blender — artists install the addon via Preferences → Add-ons → Install from file and must not be asked to touch Blender's site-packages.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS — exact strings declared for every popup and label; missing-key verbatim naming honored; no jargon
- [ ] Dimension 2 Visuals: PASS — panel layout contract frozen; icon names committed; disabled state explicit
- [ ] Dimension 3 Color: N/A — native Blender theme; `row.alert` is the only color-adjacent call
- [ ] Dimension 4 Typography: N/A — native Blender theme; no font overrides
- [ ] Dimension 5 Spacing: N/A — native Blender layout primitives only
- [ ] Dimension 6 Registry Safety: N/A — no shadcn / third-party UI registries in this phase

**Approval:** pending
