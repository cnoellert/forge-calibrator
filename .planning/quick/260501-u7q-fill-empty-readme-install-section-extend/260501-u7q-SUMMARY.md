---
quick_id: 260501-u7q
mode: quick
type: execute
wave: 1
verdict: SHIPPED
files_modified:
  - README.md
  - install.sh
commits:
  - 1dc666c
  - 549f33e
requirements: [TESTER-ROLLOUT-POLISH]
date: 2026-05-01
---

# Quick 260501-u7q — Fill empty README ## Install + extend install.sh conda preflight

## Verdict

**SHIPPED** — both atomic commits landed clean; pytest 542/0/2; bash -n install.sh clean; all four conda-preflight branches verified live in dry-run.

## Commits

| Hash | Type | Subject |
|------|------|---------|
| `1dc666c` | docs | rewrite README ## Install as crisp gateway (prereqs + one-line + verify + pointer) |
| `549f33e` | feat | extend install.sh conda preflight (no-conda detect + auto-create prompt + --yes flag) |

## Files Modified

| File | Lines (+/-) | Change |
|------|-------------|--------|
| README.md | +32 / -19 | `## Install` section replaced with three-subsection gateway (Prereqs / One-line install / Verify) |
| install.sh | +52 / -6 | `--yes` flag added; conda preflight distinguishes (no conda) vs (no env); auto-create branch with default-N prompt |

Combined diff: 2 files changed, 84 insertions(+), 25 deletions(-).

## Key Behavior Verification

### README.md rendered shape

- **Section length:** 38 lines (≤40 target).
- **Three subsections:** `### Prereqs`, `### One-line install`, `### Verify`.
- **One-line install:** `git clone https://github.com/cnoellert/forge-calibrator.git && cd forge-calibrator && ./install.sh` (single shell line, fenced as bash).
- **Verify steps:** 3 numbered (restart Flame + 15-30s wait, curl probe expects 200, FORGE → Camera right-click check).
- **Pointers to docs/seamless-bridge.md:** 8 across the file (was 6 — net +2 in the new ## Install section: one for `#for-artists`, one for `#troubleshooting`, plus the trailing `[full walkthrough]`). Min ≥3 satisfied.
- **Diff scope:** single hunk from `## Install` → `## Validation` line; everything else byte-identical.
- **Total file:** 98 lines (was 86; +12 net within the 80-95 target band).

### install.sh dry-run transcripts (4 branches)

**Branch 1 — no conda (synthetic PATH=/usr/bin:/bin):**

```
> Forge conda env
  ✗ conda not found on PATH
  ! install miniconda from https://docs.conda.io/projects/miniconda/
  ! then create the forge env: conda env create -f forge-env.yml
```

Sets `PREFLIGHT_FAIL=1`; exits 1 at the existing `preflight failed — fix the issues above and re-run` line.

**Branch 2 — no env, interactive default-N (empty stdin):**

```
> Forge conda env
  ! forge env not found at /tmp/__nonexistent_forge_env_path__
  ! create it manually: conda env create -f forge-env.yml
```

Prompt `auto-create forge env now? [y/N]` shown but skipped here by piped empty stdin (default N on bare Enter); on 'n' branch prints copy-pasteable one-liner and sets `PREFLIGHT_FAIL=1`.

**Branch 3 — no env, --yes --dry-run:**

```
> Forge conda env
  ! forge env not found at /tmp/__nonexistent_forge_env_path__
  ✓ auto-creating forge env (--force or --yes set)
    [dry] conda env create -f "/Users/cnoellert/Documents/GitHub/forge-calibrator/forge-env.yml"
  ✓ forge env ready
```

No prompt. `run` wrapper printed the `[dry] conda env create …` line per spec. Continued past conda step into wiretap precheck.

**Branch 4 — healthy host (no flags):**

```
> Forge conda env
  ✓ python: Python 3.11.14
  ✓ deps: numpy 2.4.4 , cv2 4.13.0
```

No prompt. Dep probe ran via the post-create `(( ! PREFLIGHT_FAIL )) && [[ -x "$FORGE_PY" ]]` re-check gate. Advances to wiretap step.

### Diff scope check (install.sh)

Four hunks total, all in expected scopes:

1. **Header docstring (line 22):** +1 line (`./install.sh --yes …` flag mention).
2. **Flag default (line 81):** +1 line (`YES=0`).
3. **Argv parser (line 113):** +1 line (`--yes|-y) YES=1 ; shift ;;` case).
4. **Conda preflight block (lines 277-296):** replaced with new no-conda detect + auto-create prompt + dep-probe re-check (+49 / -14 net within block).

Zero incidental edits in: `set -euo pipefail`, helpers (`ok`/`warn`/`err`/`step`/`run`), forge-bridge resolver/install block, source sanity, wiretap precheck, OCIO precheck, sync block, `__pycache__` purge, Done heredoc.

## Pytest result

```
======================== 542 passed, 2 skipped in 1.64s ========================
```

Unchanged from prior baseline (no test code touched; install.sh is not on import path; README is doc-only).

## Out-of-scope items (deliberate non-changes)

- **Wiretap CLI / OCIO / PyOpenColorIO prechecks** — kept byte-identical. The conda preflight upgrade is scoped to conda detection + env auto-create only; the other three preflight blocks already fail actionably.
- **forge-bridge install block (lines 344-443)** — untouched. Phase 3 deliverable; outside this quick task's scope.
- **Sync block + `__pycache__` purge** — untouched. Phase 04.4 fix shipped at 6a6df75; intentionally preserved.
- **Done heredoc** — untouched. The "Restart Flame, curl 200, FORGE menu" flow it documents is now also surfaced in the README ## Install ### Verify block, but the heredoc serves a different role (post-install console output) and stays as-is.
- **`--yes` does NOT widen to skip the existing `overwrite? [y/N]` prompt at line 458** — that prompt guards an existing-install overwrite, not env creation; `--force` already covers that path. Locked-context spec confines `--yes` to the conda auto-create branch only.
- **`forge-env.yml` recipe** — not edited. The plan's canonical-recipe shift only changed the user-facing hint text in `install.sh` from `pip install numpy opencv-python` to `conda env update -f forge-env.yml --prune`; the env file itself is unchanged.
- **README's "Validation" / "History" / "Troubleshooting" sections** — byte-identical. The gateway role lives only in `## Install`.

## Self-Check: PASSED

- [x] `1dc666c` exists in git log
- [x] `549f33e` exists in git log
- [x] README.md ## Install replaced (3 subsections, ≤40 lines, curl 200 probe, ≥3 pointers — actually 8)
- [x] install.sh adds `--yes` flag; argv parser accepts; default `YES=0` set
- [x] Header docstring lists `--yes`
- [x] Missing-conda branch prints miniconda URL + one-liner (verified live)
- [x] Missing-env branch prompts y/N default N (verified — empty stdin → "create it manually" warn)
- [x] `--yes` triggers no-prompt auto-create (verified live)
- [x] `--dry-run` shows would-be conda env create command (verified — `[dry] conda env create -f "<repo>/forge-env.yml"`)
- [x] Healthy host preflight unchanged (verified — Python 3.11.14, numpy 2.4.4, cv2 4.13.0, no prompt)
- [x] `git diff install.sh` hunks scoped to docstring + flag default + argv parser + conda block
- [x] `bash -n install.sh` clean
- [x] Pytest 542/0/2
