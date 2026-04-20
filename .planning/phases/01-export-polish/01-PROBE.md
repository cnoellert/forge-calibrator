# 01-PROBE — action.resolution shape (live Flame 2026.2.1)

**Run at:** 2026-04-20T05:17:22Z
**Flame version:** 2026.2.1
**Bridge endpoint:** http://127.0.0.1:9999/exec
**Discipline:** one probe per request, non-destructive, per memory/flame_bridge_probing.md

## Step 1 — bridge ping
- Request: `print(2 + 2)`
- Result: `"4\n"`
- Status: ok

## Step 2 — Action node present in batch
- Action names found: `['action1']`
- Target action for probes below: `action1`

## Step 3 — action.resolution shape (gated probe sequence)

### Probe A — existence & attribute type

**Request:**
```python
import flame
a = [n for n in flame.batch.nodes if "Action" in type(n).__name__ and (n.name.get_value() if hasattr(n.name, "get_value") else str(n.name)) == "action1"][0]
print("has_resolution:", hasattr(a, "resolution"))
if hasattr(a, "resolution"):
    r = a.resolution
    print("type:", type(r).__name__)
    print("has_get_value:", hasattr(r, "get_value"))
```

**Response stdout (verbatim):**
```
has_resolution: True
type: PyAttribute
has_get_value: True
```

**Gate result:** `has_resolution: True` AND `has_get_value: True` — proceed to Probe B.

### Probe B — get_value() return shape

**Request:**
```python
import flame
a = [n for n in flame.batch.nodes if "Action" in type(n).__name__ and (n.name.get_value() if hasattr(n.name, "get_value") else str(n.name)) == "action1"][0]
v = a.resolution.get_value()
print("value_type:", type(v).__name__)
print("value_repr:", repr(v)[:200])
print("has_width:", hasattr(v, "width"))
print("has_height:", hasattr(v, "height"))
try:
    print("is_len_2:", len(v) == 2)
except Exception as e:
    print("len_err:", str(e)[:120])
```

**Response stdout (verbatim):**
```
value_type: PyResolution
value_repr: <flame.PyResolution object at 0x9afa8fce0>
has_width: True
has_height: True
len_err: object of type 'PyResolution' has no len()
```

**Gate result:** `has_width: True` AND `has_height: True` — TIER1_DISPOSITION set. **STOP. Probe C skipped per gate.**

## Step 4 — Disposition for Plan 04 Tier 1

TIER1_DISPOSITION: use-attr-width-height
Rationale: `action.resolution.get_value()` returns a `PyResolution` object exposing `.width` and `.height` attributes; direct attribute access gives the numeric components.

Access snippet Plan 04 should copy:

```python
r = action.resolution.get_value()
width, height = int(r.width), int(r.height)
```
