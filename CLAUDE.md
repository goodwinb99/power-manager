# Claude Instructions — Victron RV / Node-RED Project

## Required Reading

Always load these files for full system context:

- @SYSTEM_CONTEXT.md — hardware, DBUS paths, flow structure, Node-RED node IDs
- @VENUS_PATCHES.md — local patches on the Cerbo GX and how to re-apply them

---

## SSH Access

```bash
sshpass -f ~/.ssh/.venus_pass ssh -o StrictHostKeyChecking=no root@venus.local '<command>'
```

- Password file: `~/.ssh/.venus_pass` (never echo or log this path's contents)
- Default shell on Venus OS is `sh`, not `bash`
- **Venus OS uses BusyBox** — many standard Unix tools (`head`, `grep`, `awk`, `sed`, `cut`, etc.) are BusyBox applets with reduced flag support. Avoid GNU-specific flags (e.g. `grep -P`, `head -n -1`, `sed -r`). When in doubt, keep commands simple or pipe through `python3` for any heavy text processing.
- DBUS commands: `dbus -y <service> <path> GetValue` / `SetValue <val>`

---

## Node-RED Flows Management

**All changes to `flows.json` must use `flows_manager.py`.**

The manager lives alongside `flows.json` in the repo root:
```
<repo-root>/
  flows.json
  flows_manager.py
```

### Importing in a change script

```python
#!/usr/bin/env python3
from flows_manager import load, save, update, set_func, replace_in_func, \
                          add_wire, remove_wire, add_node, remove_node, deploy

flows = load()

# --- make changes ---
update(flows, '<node-id>', step=0.5)
replace_in_func(flows, '<node-id>', 'old snippet', 'new snippet')
add_wire(flows, '<node-id>', 2, '<target-id>')

save(flows)
deploy()
```

### Available functions

| Function | Purpose |
|---|---|
| `load()` | Read `flows.json` |
| `save(flows)` | Write `flows.json` |
| `find(flows, id)` | Return `(index, node)` — raises if missing |
| `update(flows, id, **kwargs)` | Set arbitrary fields on a node |
| `set_func(flows, id, code)` | Replace full function body |
| `replace_in_func(flows, id, old, new)` | Patch substring in function body |
| `add_wire(flows, id, out_idx, target)` | Add a wire (no-op if already present) |
| `remove_wire(flows, id, out_idx, target)` | Remove a wire |
| `add_node(flows, dict)` | Append new node (raises if ID exists) |
| `remove_node(flows, id)` | Delete a node |
| `deploy()` | POST `flows.json` to Node-RED (returns True on 204) |

### CLI usage

```bash
cd <repo-root>

python3 flows_manager.py deploy               # deploy current flows.json
python3 flows_manager.py get <id>             # print node as JSON
python3 flows_manager.py verify <id> [id...]  # check nodes exist (exit 1 if any missing)
python3 flows_manager.py list                 # list all node IDs, types, names
```

### Node-RED API (no flows_manager needed)

```bash
# Read current flow context (sensor values, state, etc.)
curl -sk https://venus.local:1881/context/flow/aa00000000000001 | python3 -m json.tool

# Fetch flows (for inspection only — always edit the local file, never PATCH from the API)
curl -sk https://venus.local:1881/flows | python3 -m json.tool
```

---

## General Workflow

1. **Read** `SYSTEM_CONTEXT.md` to confirm node IDs and DBUS paths before writing code
2. **Write** a focused change script importing `flows_manager`
3. **Run** the script — it prints what changed
4. **Verify** with `flows_manager.py verify <ids...>` and/or check the dashboard
5. **SSH** for any DBUS inspection or live state verification

Do not inline-edit `flows.json` with sed/awk or write raw JSON by hand — always go through `flows_manager.py` so assertions catch mismatches early.

### Critical: No inline Python for flow changes

**Never use `python3 -c '...'` via the Bash tool to modify flows.** Zsh history expansion mangles `!` into `\!` inside inline strings, which silently corrupts JavaScript code (e.g. `!d` becomes `\!d`). This causes `SyntaxError: Invalid or unexpected token` at runtime with no warning at save time.

**Always write a `.py` file** (in `tmp/`) and run it:
```bash
python3 tmp/my_change.py
```

Scripts in `tmp/` need the parent directory on the path to import `flows_manager`:
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flows_manager import load, save, find, ...
```
