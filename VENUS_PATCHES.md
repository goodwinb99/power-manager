# Venus OS — Local Patches

These patches live on the Cerbo GX at `/data/venus-patches/` (survives firmware updates).
After any Venus OS update, re-apply with:

```sh
sshpass -f ~/.ssh/.venus_pass ssh root@venus.local 'sh /data/venus-patches/apply-patches.sh'
```

---

## Patch: Shore Power Shows "Disconnected" in GUI v2

**Bug:** [github.com/victronenergy/gui-v2/issues/1805](https://github.com/victronenergy/gui-v2/issues/1805)
**Status:** Open upstream, targeted for Venus OS v3.80 / gui-v2 v1.3.0
**File:** `/opt/victronenergy/dbus-systemcalc-py/delegates/acinput.py`

### Root Cause

The compiled GUI v2 (WASM for web, native binary for GX Touch) compares the
system `inputIndex` against the VE.Bus `/Ac/ActiveIn/ActiveInput` (physical
input number). The backend (`acinput.py`) skips type 0 ("Not Available") inputs
when populating `/Ac/In/0/...` and `/Ac/In/1/...`, causing system indices to
diverge from physical indices:

```
AC Input 1 = "Not Available" (type 0) → skipped by backend
AC Input 2 = "Shore" (type 3) → published at system /Ac/In/0

GUI sees: inputIndex (0) !== ActiveInput (1) → "Disconnected"
```

The QML files are compiled into the WASM/native binaries, so they cannot be
patched on the device. The fix must be in the Python backend.

### Fix

In `acinput.py`, instead of skipping type 0 inputs entirely, publish an empty
placeholder (no service info) so the system index counter stays aligned with
physical input numbers. The placeholder has `ServiceName=None`,
`ServiceType=None` so the GUI's `AcInputSystemInfo.valid` returns false and
no widget is rendered for it.

```python
# In update_values(), the loop over input_types:
# Before:
if t is None or (not 0 < t < 4):  # skips type 0 entirely
    continue

# After:
if t is None or t < 0 or t > 3:  # only skip truly invalid
    continue
if t == 0:
    # Empty placeholder — keeps indices aligned, GUI ignores it
    newvalues.update({'/Ac/In/{idx}/ServiceName': None, ...})
    input_count += 1
    continue
```

### DBUS State After Patch

```
/Ac/In/0/Source      = 0 (placeholder, Not Available)
/Ac/In/0/ServiceType = None (GUI ignores — no widget rendered)
/Ac/In/0/Connected   = 0
/Ac/In/1/Source      = 3 (Shore)
/Ac/In/1/ServiceType = vebus
/Ac/In/1/Connected   = 1
NumberOfAcInputs     = 2
ActiveInput          = 1 (physical AC-in 2)

GUI: inputIndex (1) === ActiveInput (1) → shows Shore with power ✓
```

### Files on Device

| File | Purpose |
|------|---------|
| `/data/venus-patches/acinput.py.original` | Unmodified original |
| `/data/venus-patches/acinput.py.patched` | Patched version to deploy |
| `/data/venus-patches/apply-patches.sh` | Re-application script |

### Known Side Effect

The gauge auto-max settings (`Settings/Gui/Gauges/Ac/In/1/Current/Max`) may
start low after the patch shifts shore from index 0 to index 1. With
`AutoMax = 1`, they self-correct as the system observes higher current values.
If the shore/inverter gauge shows orange/red at normal loads, it will resolve
over time as AutoMax recalibrates.

### When to Remove

Remove this patch when Venus OS includes the fix for issue #1805.
Check the upstream issue for status.
