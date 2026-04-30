# Probe 0 — Pre-flight: bridge ping + throwaway batch group setup

Spike: 260430-iv3 — Matchbox Uniform Readback via Flame Channel API
Started: 2026-04-30T20:44:15Z

## Step 1 — PROBE.md skeleton written to disk

Created `260430-iv3-PROBE.md` with skeleton sections (Pre-flight, Findings Table, Probe 1-4, Recommendation Matrix, Next Planning Step, Memory Crumb Candidates, Self-check). All probe rows marked `<PENDING>`. Done before any /exec to protect against mid-spike SIGSEGV (R5).

## Step 2 — Bridge ping (R7)

Timestamp: 2026-04-30T20:45:01Z

**Request:**

```bash
curl -sS -X POST http://127.0.0.1:9999/exec \
  -H 'Content-Type: application/json' \
  -d '{"code": "1+1", "timeout_ms": 2000}' --max-time 5
```

**Response envelope:**

```json
{"result": "2", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

**Verdict:** Bridge alive. `result == "2"` per REPL contract (last expression's repr). Proceed.

## Step 3 — Confirm Flame session has a project + batch

Timestamp: 2026-04-30T20:45:05Z

**Request body:**

```python
import flame
(bool(flame.batch), flame.batch.name.get_value() if flame.batch else None)
```

**Response envelope:**

```json
{"result": "(True, 'Batch')", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

**Verdict:** Flame session is running with an open batch named `Batch` (the default desktop batch). Proceed to Step 4 to create the throwaway.

## Step 4 — Create throwaway batch group `spike_260430_iv3` (R6)

Timestamp: 2026-04-30T20:45:13Z

**Request body:**

```python
import flame
ws = flame.projects.current_project.current_workspace
desktop = ws.desktop
existing = [bg.name.get_value() for bg in desktop.batch_groups]
if 'spike_260430_iv3' not in existing:
    bg = desktop.create_batch_group(name='spike_260430_iv3')
else:
    bg = next(b for b in desktop.batch_groups if b.name.get_value() == 'spike_260430_iv3')
(bg.name.get_value(), [a for a in dir(desktop) if 'active' in a.lower() or 'current' in a.lower()], [b.name.get_value() for b in desktop.batch_groups])
```

**Response envelope:**

```json
{"result": "('spike_260430_iv3', [], ['Batch', 'gen_0460', 'spike_260430_iv3'])", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

**Observations:**

- `desktop.create_batch_group(name='spike_260430_iv3')` succeeded; the new batch group is in the desktop's `batch_groups` list alongside `Batch` and `gen_0460` (a pre-existing batch from a previous session).
- The `desktop` object exposes NO attribute matching `active` or `current` (filtered list is `[]`). So there's no documented Python API to programmatically switch the active batch — but Flame appears to auto-activate on `create_batch_group()` based on Step 5 below.

## Step 5 — Confirm `flame.batch` resolves to `spike_260430_iv3`

Timestamp: 2026-04-30T20:45:17Z

**Request body:**

```python
import flame
flame.batch.name.get_value()
```

**Response envelope:**

```json
{"result": "'spike_260430_iv3'", "stdout": "", "stderr": "", "error": null, "traceback": null}
```

**Verdict:** Active batch is `spike_260430_iv3`. R6 satisfied — all subsequent state-mutating calls in this spike will run in this throwaway batch.

## Pre-flight summary

| Gate                                        | Status | Evidence                              |
|---------------------------------------------|--------|---------------------------------------|
| Bridge alive                                | PASS   | Step 2 — `result: "2"`                |
| Flame session has open batch                | PASS   | Step 3 — `(True, 'Batch')`            |
| Throwaway batch group `spike_260430_iv3`    | PASS   | Step 4 — created via `create_batch_group` |
| Active batch is the throwaway               | PASS   | Step 5 — `flame.batch.name == 'spike_260430_iv3'` |

All four gates green. Proceed to Checkpoint A (user drops Camera Match matchbox into the active throwaway batch and sets `vp1_l1_start = (0.42, 0.69)`).
