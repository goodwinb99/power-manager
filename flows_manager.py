#!/usr/bin/env python3
"""
flows_manager.py - Utility for managing Node-RED flows.json

Import as a module in change scripts:
    from flows_manager import load, save, find, update, replace_in_func, \
                              add_wire, add_node, deploy

Or use as a CLI:
    python3 flows_manager.py deploy
    python3 flows_manager.py get <id>
    python3 flows_manager.py verify <id> [id ...]
    python3 flows_manager.py list
"""

import json
import os
import subprocess
import argparse
import sys

# flows.json lives in the same directory as this script
FLOWS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flows.json')
NR_URL     = 'https://venus.local:1881'


# ── Core helpers ─────────────────────────────────────────────────────────────

def load(path=FLOWS_PATH):
    """Load flows.json and return the list."""
    with open(path, 'r') as f:
        return json.load(f)


def save(flows, path=FLOWS_PATH):
    """Write flows list back to disk."""
    with open(path, 'w') as f:
        json.dump(flows, f, indent=4)
    print(f"Saved {path}")


def find(flows, nid, required=True):
    """Return (index, node) for the given node ID.
    Raises ValueError if required=True and node is absent."""
    for i, n in enumerate(flows):
        if n.get('id') == nid:
            return i, n
    if required:
        raise ValueError(f"Node not found: {nid}")
    return None, None


# ── Mutation helpers ──────────────────────────────────────────────────────────

def update(flows, nid, **kwargs):
    """Shallow-update arbitrary fields on a node.

    Example:
        update(flows, 'aa000000000000e5', step=0.5, min=10, max=50)
    """
    idx, node = find(flows, nid)
    node.update(kwargs)
    flows[idx] = node
    label = node.get('name') or node.get('type', nid)
    print(f"  updated  {nid}  [{label}]  fields: {list(kwargs.keys())}")
    return node


def replace_in_func(flows, nid, old, new):
    """Replace a substring inside a function node's 'func' field.
    Asserts that the old string is actually present before replacing.

    Example:
        replace_in_func(flows, 'aa00000000000086', 'high - 10', 'high - 1')
    """
    idx, node = find(flows, nid)
    func = node.get('func', '')
    assert old in func, (
        f"Substring not found in {nid} func:\n  looking for: {repr(old[:80])}"
    )
    node['func'] = func.replace(old, new)
    flows[idx] = node
    label = node.get('name') or node.get('type', nid)
    print(f"  patched  {nid}  [{label}]  func")
    return node


def set_func(flows, nid, func_str):
    """Replace the entire func field on a function node.

    Example:
        set_func(flows, 'aa00000000000030', 'return msg;')
    """
    idx, node = find(flows, nid)
    node['func'] = func_str
    flows[idx] = node
    label = node.get('name') or node.get('type', nid)
    print(f"  set func {nid}  [{label}]")
    return node


def add_wire(flows, nid, output_idx, target_id):
    """Append target_id to a node's output wire list (no-op if already wired).

    Example:
        add_wire(flows, 'aa00000000000030', 2, 'aa000000000000e8')
    """
    idx, node = find(flows, nid)
    wires = node.setdefault('wires', [])
    while len(wires) <= output_idx:
        wires.append([])
    if target_id not in wires[output_idx]:
        wires[output_idx].append(target_id)
        flows[idx] = node
        label = node.get('name') or node.get('type', nid)
        print(f"  wired    {nid}[{output_idx}]  [{label}]  -> {target_id}")
    else:
        print(f"  (already wired {nid}[{output_idx}] -> {target_id})")
    return node


def remove_wire(flows, nid, output_idx, target_id):
    """Remove a specific target from a node's output wire list."""
    idx, node = find(flows, nid)
    try:
        node['wires'][output_idx].remove(target_id)
        flows[idx] = node
        label = node.get('name') or node.get('type', nid)
        print(f"  unwired  {nid}[{output_idx}]  [{label}]  -x {target_id}")
    except (IndexError, ValueError):
        print(f"  (wire {nid}[{output_idx}] -> {target_id} not found, skipped)")
    return node


def add_node(flows, node_dict):
    """Append a new node; raises if the ID already exists.

    Example:
        add_node(flows, {"id": "aa000000000000e5", "type": "ui-slider", ...})
    """
    nid = node_dict.get('id', '<no id>')
    _, existing = find(flows, nid, required=False)
    if existing is not None:
        raise ValueError(f"Node {nid} already exists — remove it first or use update()")
    flows.append(node_dict)
    label = node_dict.get('name') or node_dict.get('type', nid)
    print(f"  added    {nid}  [{label}]")
    return node_dict


def remove_node(flows, nid):
    """Remove a node by ID. Raises if not found."""
    idx, node = find(flows, nid)
    label = node.get('name') or node.get('type', nid)
    flows.pop(idx)
    print(f"  removed  {nid}  [{label}]")


# ── Deploy ────────────────────────────────────────────────────────────────────

def deploy(path=FLOWS_PATH, url=NR_URL):
    """POST flows.json to Node-RED. Returns True on HTTP 204."""
    result = subprocess.run(
        ['curl', '-s', '-w', '\nHTTP %{http_code}',
         '-X', 'POST', f'{url}/flows',
         '-H', 'Content-Type: application/json',
         '--data-binary', f'@{path}',
         '--insecure'],
        capture_output=True, text=True
    )
    status_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
    if status_line == 'HTTP 204':
        print("Deploy: OK (204)")
        return True
    else:
        print(f"Deploy FAILED: {result.stdout.strip()} {result.stderr.strip()}")
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    p = argparse.ArgumentParser(
        description='Node-RED flows.json manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = p.add_subparsers(dest='cmd', metavar='command')

    sub.add_parser('deploy', help='POST flows.json to Node-RED')

    pg = sub.add_parser('get', help='Print a node as JSON')
    pg.add_argument('id', help='Node ID')

    pv = sub.add_parser('verify', help='Check that node IDs exist')
    pv.add_argument('ids', nargs='+', metavar='id')

    sub.add_parser('list', help='List all node IDs, types, and names')

    args = p.parse_args()

    if args.cmd == 'deploy':
        ok = deploy()
        sys.exit(0 if ok else 1)

    elif args.cmd == 'get':
        flows = load()
        _, node = find(flows, args.id)
        print(json.dumps(node, indent=2))

    elif args.cmd == 'verify':
        flows = load()
        all_ok = True
        for nid in args.ids:
            _, node = find(flows, nid, required=False)
            if node:
                label = node.get('name') or node.get('type', '')
                print(f"  OK      {nid}  [{label}]")
            else:
                print(f"  MISSING {nid}")
                all_ok = False
        sys.exit(0 if all_ok else 1)

    elif args.cmd == 'list':
        flows = load()
        for n in flows:
            if 'id' not in n or 'type' not in n:
                continue
            name = n.get('name', '')
            print(f"  {n['id']}  {n['type']:<32}  {name}")

    else:
        p.print_help()


if __name__ == '__main__':
    _cli()
