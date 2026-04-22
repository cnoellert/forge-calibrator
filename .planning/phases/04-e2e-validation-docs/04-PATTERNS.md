# Phase 4: E2E Validation + Docs — Pattern Map

**Mapped:** 2026-04-22
**Files to create:** 3 (1 shell script, 2 markdown docs)
**Analogs found:** 3 / 3
**Phase is docs + validation only — NO Python source changes, NO test patterns needed.**

---

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `tools/smoke-test/seamless-bridge-smoke.sh` (D-02 Claude's Discretion path) | validation-script | request-response (sequential [mech]/[human] steps) | `install.sh` | exact (shell, same visual rhythm, same preflight discipline) |
| `README.md` (repo root) | user-doc | document | `.planning/PROJECT.md` §What This Is + §Core Value (content source) + `PASSOFF.md` (tone reference) | partial (no existing README; borrow content from PROJECT.md, tone from PASSOFF.md) |
| `docs/seamless-bridge.md` | user-doc | document | `install.sh` (section-header rhythm, `> Section` shape), `tools/blender/forge_sender/__init__.py` + `preflight.py` + `transport.py` + `install.sh` (grep-anchor sources for verbatim troubleshooting copy) | partial (no existing user-doc analog; grep-anchoring is the dominant pattern) |

**Note on scope:** Phase 4 touches zero Python files. No pytest fixtures, no adapter patterns, no Flame API duck-typing — none of that applies. Patterns below are entirely shell + markdown + grep-anchored string literals.

---

## Pattern Assignments

### 1. `tools/smoke-test/seamless-bridge-smoke.sh` (validation-script, sequential prompts)

**Analog:** `install.sh` (both are top-level bash scripts; both bookend mechanized preflight with user-visible actions; both target Flame 2026.2.1 + the same forge env)

**Pattern to replicate (visual rhythm + printer helpers):**

- **Header docstring** (install.sh:1-28) — purpose, usage, env overrides, documented as comments before `set -euo pipefail`.
- **Colour helpers gated on TTY** (install.sh:76-84) — ANSI codes only when `-t 1`. CONTEXT D-Claude's-Discretion item 5 defaults this "yes" for `[human]` prompts.
- **Four printer functions** (install.sh:81-84):
  ```bash
  ok()   { printf "  %s✓%s %s\n" "$C_OK"   "$C_END" "$*"; }
  warn() { printf "  %s!%s %s\n" "$C_WARN" "$C_END" "$*"; }
  err()  { printf "  %s✗%s %s\n" "$C_ERR"  "$C_END" "$*" >&2; }
  step() { printf "\n%s>%s %s\n" "$C_DIM" "$C_END" "$*"; }
  ```
  Smoke test adds a fifth helper for the human prompt (per CONTEXT D-Claude's-Discretion item 5: "Default yes if it makes the prompts easier to spot"):
  ```bash
  human() { printf "\n  %s[HUMAN]%s %s\n" "$C_WARN" "$C_END" "$*"; }
  ```

- **Section-header idiom** (install.sh:239, 262, 283, 295, 309, 340, 430, 459, 484) — `step "Name"` prints `\n> Name\n` and sets visual rhythm between blocks. Every numbered step in CONTEXT D-03 maps to one `step` block:
  ```bash
  step "Working-tree clean"
  step "install.sh dry-run"
  step "install.sh live"
  step "forge_bridge.py sanity"
  step "Bridge reachable after Flame boot"   # [human] + [mech] curl
  step "Export Camera to Blender"             # [human]
  step "Send to Flame"                        # [human]
  step "Camera appears in target Action"      # [human]
  step "No orphan bridge after Flame quit"    # [human] + [mech] pgrep
  step "pytest"
  step "Done"
  ```

- **Exit-on-error discipline** (install.sh:30, 240-243, 322-326) — `set -euo pipefail` at top; explicit `err "..." ; exit 1` on preflight failure:
  ```bash
  if [[ ! -f "$SOURCE_HOOK" ]]; then
    err "missing source hook: $SOURCE_HOOK"
    exit 1
  fi
  ```
  Mirror this for every `[mech]` step per CONTEXT D-06 ("On any [mech] failure, the script exits non-zero with the failure line echoed").

- **Post-condition guard pattern** (install.sh:322-326):
  ```bash
  if (( PREFLIGHT_FAIL )); then
    err "preflight failed — fix the issues above and re-run"
    exit 1
  fi
  ```
  Smoke test's equivalent: each `[human]` `n` answer sets `HUMAN_FAIL=1` and adds the step description to a `FAILED_STEPS` array; at the end, print the array and exit 1 (per CONTEXT D-06: "the step description + 'report to the troubleshooting section of docs/seamless-bridge.md' message").

- **Transcript logging** (CONTEXT D-05: `/tmp/forge-smoke-YYYYMMDD-HHMMSS.log`) — install.sh has no direct analog, but the installer's `run()` / `eval` wrapper (install.sh:114-120) shows the printf-based teeing style. Smoke test should redirect all `ok`/`warn`/`err`/`step`/`human` output via `tee` to the timestamped log from first line; CONTEXT D-Claude's-Discretion item 6 adds `git describe --tags` / `git rev-parse HEAD` to the log header.

- **Dry-run sentinel** (install.sh:72, 114-120, 356) — install.sh has a `DRY_RUN` flag, but the smoke test runs real commands only (no dry-run mode). Skip this pattern.

- **y/n prompt idiom** (install.sh:441-442) — already lives in install.sh for overwrite confirmation:
  ```bash
  read -r -p "  overwrite? [y/N] " ans
  [[ "${ans:-N}" =~ ^[Yy]$ ]] || { err "aborted by user"; exit 1; }
  ```
  CONTEXT D-Claude's-Discretion item 4 leaves the exact form open. Shortest legible version per that steer:
  ```bash
  read -r -p "  pass? [y/n] " ans
  case "${ans,,}" in
    y|yes) ok "step passed" ;;
    *)     err "step failed — see docs/seamless-bridge.md#troubleshooting"
           FAILED_STEPS+=("<step description>")
           HUMAN_FAIL=1 ;;
  esac
  ```

- **Idempotence discipline** (CONTEXT D-04: "safe to invoke multiple times against an already-installed workstation"). install.sh itself is idempotent: `mkdir -p`, `rsync -a --delete`, `cp` overwrite, `rm -rf __pycache__`. The smoke test inherits this via its three subcall paths (`install.sh --dry-run`, `install.sh`, `pytest -q`) — all idempotent. The smoke test must NOT delete `~/forge-bakes/`, touch `/opt/Autodesk/`, or require `--force`.

- **Curl bridge-probe idiom** (install.sh:519-522 — documented in the Done-section `cat <<EOF`):
  ```
  curl -s http://localhost:9999/ -o /dev/null -w "%{http_code}\n"
  # expect: 200
  ```
  CONTEXT D-03 step 5 uses exactly this. Re-use verbatim so the smoke test output matches install.sh's `Next steps` section character-for-character.

**Pattern to avoid:**
- **Do NOT** import or source install.sh. CONTEXT D-01 scope says smoke test is a standalone artifact that bookends what install.sh already did; re-sourcing risks running the installer twice.
- **Do NOT** add Python test fixtures, pytest markers, or mock Flame objects — out of scope; step 10 just invokes `pytest -q` as a subprocess.
- **Do NOT** add a `--force` flag or any destructive option.
- **Do NOT** abbreviate the `[human]` prompt text. Artists alt-tabbing back to the terminal need the exact action described. (Same discipline as Phase 2 D-09 popup copy: direct, names the thing, offers the fix.)

---

### 2. `README.md` (user-doc, document)

**Analogs:**
- `.planning/PROJECT.md` §What This Is + §Core Value — source of the one-paragraph overview and the verbatim Core Value sentence (CONTEXT D-08 items 1-2).
- `PASSOFF.md` — tone reference (direct, names the thing, no jargon softening).

**Content excerpt to adapt (overview — CONTEXT D-08 item 1, adapt from PROJECT.md §What This Is, PROJECT.md:3-5):**
```
A vanishing-point camera calibration tool that lives inside Autodesk Flame.
A VFX artist draws 2-3 reference lines along orthogonal scene edges in a plate;
the tool solves a camera (position, rotation, FOV, focal length) and applies it
to a Flame Action node. Recent work (v6.x) extends this with a Flame↔Blender
camera round-trip so solved cameras — static or animated — can be refined in
Blender and returned to Flame.
```

**Content excerpt to use verbatim (Core Value — CONTEXT D-08 item 2, PROJECT.md:7-9):**
```
The solved camera must be geometrically faithful to the plate, and the
Flame↔Blender round-trip must preserve that fidelity end-to-end.
```
Bold the sentence in README.md to match PROJECT.md's treatment.

**Tone excerpt from PASSOFF.md (PASSOFF.md:18-23):**
```
The animated round-trip works but the UX still bounces off disk in three places
(`.fbx`, `.json`, `.blend`) and requires the user to alt-tab back to Flame to
trigger import. The cleaner shape: a Blender-side addon with a "Send to Flame"
button that reads stamped metadata off the camera's custom properties
(`forge_bake_action_name`, etc.) and `POST`s extract-and-import to forge-bridge's
`127.0.0.1:9999/exec` endpoint. No user round-trip to Flame's menu.
```
Pattern: names the problem in plain terms, names the solution by its user-facing capability, cites the mechanism (addon, metadata, POST) only as supporting detail. README.md's "What's new in v6.3" bullets follow the same shape.

**Pattern to replicate:**

- **H1 = project name** (PROJECT.md:1 — `# forge-calibrator`). README.md's H1 matches.
- **H2 sections in the CONTEXT D-08 order**: `## What this is` → `## Core value` → `## What's new in v6.3` → `## Install` → `## Validation` → `## History` → `## Troubleshooting`.
- **Relative markdown links only** (CONTEXT <specifics> "Link discipline"): `[install section](docs/seamless-bridge.md#install)`, never `https://github.com/...`. Docs render from the local checkout.
- **User-facing capability language for the v6.3 bullets** (CONTEXT D-Claude's-Discretion last item): "seamless round-trip", "forge-bridge autostart", "Blender Send-to-Flame addon". NOT "forge_sender", "camera_match_hook", "PyActionNode.import_fbx".
- **Install section stays a collapsed summary** (CONTEXT D-08 item 4) — one-liner `./install.sh` + one-liner addon install + link to the deep-dive. Detailed walkthrough lives in `docs/seamless-bridge.md`.

**Pattern to avoid:**
- **No internal jargon in user-facing text.** Phase 4 CONTEXT <specifics> is explicit: no `PyAttribute`, no `PyActionNode`, no `duck-typing`, no `namespace-package drift`. Use "Action", "camera", "Flame hook". The PASSOFF.md tone sample above does name `forge_bake_action_name` — that's acceptable in a troubleshooting recipe (users see the literal string in the error popup), but NOT in the README overview.
- **No screenshots, GIFs, video** (CONTEXT D-11). Text-only for v1.
- **No migration section** (CONTEXT D-17). The "What's new" bullet list is the release note; install.sh handles upgrade mechanics idempotently.
- **No github.com URLs** in cross-links (CONTEXT <specifics>).

---

### 3. `docs/seamless-bridge.md` (user-doc, document)

**Analogs:**
- `install.sh` — section-header shape (`> Section`) plus verbatim D-10 warning copy (install.sh:425-426) that's the grep-anchor for troubleshooting recipe 4.
- `tools/blender/forge_sender/transport.py` — Tier 3 envelope template string that's the grep-anchor for troubleshooting recipe 3 (transport.py:220).
- `tools/blender/forge_sender/__init__.py` — Tier 2 popup literal that's the grep-anchor for troubleshooting recipe 1 (__init__.py:240-242).
- `tools/blender/forge_sender/preflight.py` — Tier 1 popup literal that's the grep-anchor for troubleshooting recipe 2 (preflight.py:52-57).

**Pattern to replicate (structure per CONTEXT D-09):**

- **H1 = feature name** (e.g., `# Seamless Flame↔Blender bridge`).
- **Five top-level H2s in D-09 order**: `## Overview` → `## Install` (with `### For pipeline TDs` + `### For artists` subsections per D-10) → `## How forge-bridge autostart works` → `## Using Send to Flame` → `## Troubleshooting`.
- **Relative links to README** (e.g., `[back to README](../README.md)`). Artists open the file from the local checkout.

**Grep-anchored troubleshooting copy — recipe Symptom headings must be verbatim:**

Recipe 1 Symptom (CONTEXT D-12.1). Source: `tools/blender/forge_sender/__init__.py:240-242`:
```python
msg = (
    "Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999"
    " — is Flame running with the Camera Match hook loaded?"
)
```
Doc Symptom heading (single string, exactly as the artist sees it in the popup):
```
Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Match hook loaded?
```
Verification grep (per CONTEXT D-14): `grep -F "forge-bridge not reachable at http://127.0.0.1:9999" tools/blender/forge_sender/__init__.py` — must match.

Recipe 2 Symptom (CONTEXT D-12.2). Source: `tools/blender/forge_sender/preflight.py:52-57`:
```python
for key in _REQUIRED_STAMPED_KEYS:
    if key not in data:
        return (f"Send to Flame: active camera is missing '{key}' — "
                f"this camera was not baked by forge-calibrator. "
                f"Re-export from Flame via right-click → Camera Match → "
                f"Export Camera to Blender")
```
The keys: `_REQUIRED_STAMPED_KEYS = ("forge_bake_action_name", "forge_bake_camera_name")` (preflight.py:31). Doc Symptom heading covers both substitutions:
```
Send to Flame: active camera is missing 'forge_bake_action_name' — this camera was not baked by forge-calibrator. Re-export from Flame via right-click → Camera Match → Export Camera to Blender
```
(or `'forge_bake_camera_name'`; note both are part of the priority order — preflight check names only the first-missing key per preflight.py:27-31).
Verification grep: `grep -F "active camera is missing" tools/blender/forge_sender/preflight.py` — must match.

Recipe 3 Symptom (CONTEXT D-12.3). Source: `tools/blender/forge_sender/transport.py:215, 220`:
```python
# docstring:
``Send to Flame failed: {error}\\n\\n{traceback}``.
# implementation:
return (f"Send to Flame failed: {error}\n\n{traceback}", None)
```
Note: CONTEXT D-12.3 shows `"Send failed: {error}..."` but the actual source reads `"Send to Flame failed: {error}..."`. Use the **source** verbatim (grep-anchor discipline per D-14 overrides the CONTEXT prose paraphrase):
```
Send to Flame failed: {error}

{traceback}
```
Verification grep: `grep -F "Send to Flame failed:" tools/blender/forge_sender/transport.py` — must match.

Recipe 4 Symptom (CONTEXT D-12.4). Source: `install.sh:425-426`:
```bash
printf "  %s[WARN]%s forge-bridge install skipped (%s). VP-solve and v6.2 static round-trip still work. v6.3 Send-to-Flame will fail with \"forge-bridge not reachable at http://127.0.0.1:9999\" until the bridge is deployed. To retry: FORGE_BRIDGE_REPO=<path> ./install.sh   OR   curl -fsSL https://raw.githubusercontent.com/cnoellert/forge-bridge/%s/scripts/install-flame-hook.sh | bash\n" \
  "$C_WARN" "$C_END" "$BRIDGE_FAIL_REASON" "$FORGE_BRIDGE_VERSION" >&2
```
Doc Symptom heading (the `${reason}` slot is filled at runtime; the most common value is `sibling installer exited non-zero` per install.sh:382, 389):
```
[WARN] forge-bridge install skipped (sibling installer exited non-zero). VP-solve and v6.2 static round-trip still work.
```
Verification grep: `grep -F "forge-bridge install skipped" install.sh` — must match.

Recipe 5 Symptom (CONTEXT D-12.5). No source-code grep anchor — this recipe's trigger is a port conflict surfaced by whatever binds :9999 first (another service, stale forge-bridge, second Flame instance). Symptom heading comes from the Tier 2 popup (same as recipe 1 — the bridge still fails to start or respond) plus a user-visible diagnostic:
```
Send to Flame: forge-bridge not reachable at http://127.0.0.1:9999 — is Flame running with the Camera Match hook loaded?
(and/or `lsof -i :9999` shows a non-forge-bridge PID listening)
```
CONTEXT D-Claude's-Discretion item 7: pick the most portable form. Both `lsof -i :9999` and `lsof -iTCP:9999 -sTCP:LISTEN` work on macOS + Linux; the shorter form is more legible for the artist audience.

**Recipe format — CONTEXT D-13, three sections each:**
```markdown
### Symptom: {verbatim popup or install output text}

**Likely cause:** {plain-English explanation — one or two sentences}

**Fix:**
1. {copy-pasteable shell command}
2. {or exact UI step, e.g., "Flame: right-click Action → Camera Match → Export Camera to Blender"}
```
No extra headings, no "See also" appendix, no generic troubleshooting preamble. Keep the recipe tight.

**Install section structure (CONTEXT D-10, audience split via subsection headers inside one file):**

```markdown
## Install

### For pipeline TDs

[Walk through install.sh preflight (forge conda env, Wiretap CLI,
PyOpenColorIO, OCIO config), the `> forge-bridge` section flow,
and the /opt/Autodesk/shared/python/ layout.]

### For artists

1. Unzip `tools/blender/forge_sender/` to a temp location.
2. Blender → Preferences → Add-ons → Install from file → pick the zip.
3. Enable "Forge Sender".
4. In the 3D viewport, open the N-panel (N key) — you should see a
   "Forge" tab with a "Send to Flame" button.
```

**Section-name grep anchors (CONTEXT <Established Patterns>):** install.sh uses `> Install`, `> forge-bridge`, `> forge_core + forge_flame` as `step "..."` section headers (install.sh:340, 430, 459). The doc can reference these verbatim when explaining what TDs will see in the installer output ("When `install.sh` prints `> forge-bridge`, it's invoking..."). Don't invent new section names.

**Pattern to avoid:**
- **No internal jargon.** No `PyAttribute`, `PyActionNode`, `ast.parse`, `namespace-package`, `duck-typing`. The forge_sender custom-property names ARE user-visible (they appear in the Tier 1 popup), so they're quoted verbatim in recipe 2's Symptom — but that's the only place.
- **No screenshots, GIFs, video** (CONTEXT D-11).
- **No translated forward links** — if the exact string the artist copy-pastes into Ctrl-F differs from what's in the source, the grep anchor breaks. Keep the Symptom heading character-for-character matched to the source.
- **No HTTP URLs to github.com** in cross-doc links — only in the recipe 4 Fix block, which is the literal retry command the D-10 warning itself prints.
- **No Python code blocks in user-facing prose** (the `__init__.py:240` excerpt above is for this PATTERNS.md only; in the doc, quote the popup text as a markdown blockquote or heading, not as Python).

---

## Shared Patterns (cross-cutting)

### Grep-anchor discipline

**Sources:** All four production-code files that emit user-visible error text.
**Apply to:** Every Symptom heading in `docs/seamless-bridge.md` troubleshooting. Also to any Symptom text the smoke-test script echoes on `[human]` `n` answers.

**Verification pass (CONTEXT D-14, run during plan's verification step):**
```bash
grep -F "forge-bridge not reachable at http://127.0.0.1:9999" tools/blender/forge_sender/__init__.py
grep -F "active camera is missing" tools/blender/forge_sender/preflight.py
grep -F "Send to Flame failed:" tools/blender/forge_sender/transport.py
grep -F "forge-bridge install skipped" install.sh
```
All four must return at least one match. If any fails, the doc's Symptom heading has drifted from the source and the recipe is broken (Ctrl-F won't land the user where the popup sent them).

### Tone: direct, names the thing, offers the fix

**Sources:** Phase 2 D-09 popup copy (see preflight.py:52-57, __init__.py:240-245, transport.py:220), Phase 3 D-10 warning (install.sh:425-426).
**Apply to:** All prose in `README.md` + `docs/seamless-bridge.md` + the smoke-test script's `[human]` prompts.

**Excerpt illustrating the tone** (preflight.py:54-57):
```python
return (f"Send to Flame: active camera is missing '{key}' — "
        f"this camera was not baked by forge-calibrator. "
        f"Re-export from Flame via right-click → Camera Match → "
        f"Export Camera to Blender")
```
Three moves in 4 lines: (1) names the failure, (2) explains why in one sentence, (3) tells the user the single fix action. Every troubleshooting recipe's Likely cause + Fix should do the same.

### Simplicity preference

**Sources:** CONTEXT <Established Patterns> + repeated across Phase 1/2/3 decisions.
**Apply to:** Both docs + the smoke-test script.

- Fewest-lines-of-change favoured over abstraction.
- No heading levels beyond H3 without a compelling reason.
- 5 troubleshooting recipes — not 10, not 3. CONTEXT D-12 locks the count.
- No generic "Getting started" boilerplate; every section earns its place by covering one of the CONTEXT D-07/D-08/D-09 items.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | All three new files have clear analogs for their dominant patterns (install.sh for shell-script rhythm; PROJECT.md + PASSOFF.md for README content/tone; install.sh + forge_sender/* for grep-anchored doc copy). |

---

## Metadata

**Analog search scope:** `install.sh`, `tools/blender/forge_sender/*.py`, `.planning/PROJECT.md`, `PASSOFF.md`, `.planning/phases/02-blender-addon/02-CONTEXT.md`, `.planning/phases/03-forge-bridge-deploy/03-CONTEXT.md`.
**Files scanned:** ~15 (shell scripts + forge_sender addon sources + planning artefacts).
**Pattern extraction date:** 2026-04-22.

**Key correction from the mapping-context prompt:** The CONTEXT prompt described the Tier 3 envelope as `"Send failed: {error}\n\n{traceback}"`. The actual source (`transport.py:220`) reads `"Send to Flame failed: {error}\n\n{traceback}"`. The grep-anchor discipline in CONTEXT D-14 requires the doc to use the source string verbatim — use `"Send to Flame failed:"` as the recipe 3 Symptom heading, not `"Send failed:"`.

**Key correction on Tier 2/Tier 3 file locations:** The mapping-context prompt directed to `tools/blender/forge_sender/operator.py` for the Tier 3 envelope. That file does not exist — the addon is structured as a flat package with the Operator class living inside `__init__.py` (see `__init__.py:240-245` for Tier 2, `transport.py:215-220` for the Tier 3 envelope template consumed by `__init__.py`'s `parse_envelope` call at line 257). Recipe 1's grep target is `__init__.py`; recipe 3's grep target is `transport.py`.
