#!/usr/bin/env python3
"""
Create cables in NetBox by pairing point-to-point addresses.

    export NETBOX_URL=http://localhost:8080
    export NETBOX_TOKEN=...

    python3 import_cables.py --dry-run
    python3 import_cables.py

Reads IP addresses already in NetBox, groups them by /31 and /30 subnet, and
cables the two ends together. Addresses live on subinterfaces, so the cable is
created between their PARENT physical interfaces - that is where a real cable
would land.

The report is the point. Orphans mean a link that only exists on one side.
"""

import argparse
import ipaddress
import os
import sys
from collections import defaultdict

import requests

NETBOX = os.environ.get("NETBOX_URL", "http://localhost:8080").rstrip("/")
TOKEN = os.environ.get("NETBOX_TOKEN")

if not TOKEN:
    sys.exit("set NETBOX_TOKEN")

S = requests.Session()
S.headers.update({
    "Authorization": f"Token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
})

# Only these prefix lengths are treated as point-to-point links.
P2P_LENGTHS = {30, 31}


def api_get_all(path, **params):
    """Follow pagination and return every result."""
    params = dict(params, limit=500)
    url = f"{NETBOX}/api/{path}/"
    out = []
    while url:
        r = S.get(url, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        out.extend(data["results"])
        url = data.get("next")
        params = None       # 'next' already carries the query string
    return out


def api_post(path, payload):
    r = S.post(f"{NETBOX}/api/{path}/", json=payload, timeout=30)
    return r


def parent_name(name):
    return name.split(".")[0] if "." in name else name


def collect():
    """Return {network: [ {device, iface, parent, iface_id, addr}, ... ]}"""
    print("fetching addresses...")
    addrs = api_get_all("ipam/ip-addresses")
    print(f"  {len(addrs)} addresses")

    print("fetching interfaces...")
    ifaces = api_get_all("dcim/interfaces")
    print(f"  {len(ifaces)} interfaces")

    # interface id -> (device name, interface name)
    iface_by_id = {
        i["id"]: (i["device"]["name"], i["name"])
        for i in ifaces
    }
    # (device, interface name) -> id, for finding parents
    id_by_devif = {
        (i["device"]["name"], i["name"]): i["id"]
        for i in ifaces
    }

    buckets = defaultdict(list)
    unassigned = []

    for a in addrs:
        obj = a.get("assigned_object")
        if not obj or a.get("assigned_object_type") != "dcim.interface":
            unassigned.append(a["address"])
            continue

        iface_id = obj["id"]
        if iface_id not in iface_by_id:
            continue
        device, iface = iface_by_id[iface_id]

        net = ipaddress.ip_interface(a["address"]).network
        if net.prefixlen not in P2P_LENGTHS:
            continue

        parent = parent_name(iface)
        buckets[net].append({
            "device":    device,
            "iface":     iface,
            "parent":    parent,
            "parent_id": id_by_devif.get((device, parent)),
            "addr":      a["address"],
        })

    return buckets, unassigned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--type", default="cat6")
    args = ap.parse_args()

    buckets, unassigned = collect()

    pairs, orphans, crowded, missing_parent = [], [], [], []

    for net, ends in sorted(buckets.items()):
        if len(ends) == 1:
            orphans.append((net, ends[0]))
            continue
        if len(ends) > 2:
            crowded.append((net, ends))
            continue

        a, b = ends
        if a["device"] == b["device"]:
            crowded.append((net, ends))     # both ends on one device
            continue
        if not a["parent_id"] or not b["parent_id"]:
            missing_parent.append((net, ends))
            continue
        pairs.append((net, a, b))

    print(f"\n{'='*72}")
    print(f"{len(pairs)} links to cable")
    print(f"{'='*72}")
    for net, a, b in pairs:
        left = f"{a['device']}:{a['parent']}"
        right = f"{b['device']}:{b['parent']}"
        print(f"  {str(net):<18} {left:<26} <-> {right}")

    if orphans:
        print(f"\n{'='*72}")
        print(f"{len(orphans)} ORPHANS - one end only, the far side does not exist")
        print(f"{'='*72}")
        for net, e in orphans:
            other = [str(h) for h in net.hosts()] if net.prefixlen == 30 else \
                    [str(h) for h in net]
            other = [h for h in other if h != e["addr"].split("/")[0]]
            print(f"  {str(net):<18} {e['device']}:{e['iface']} has {e['addr']}")
            print(f"  {'':<18} nothing holds {', '.join(other)}")

    if crowded:
        print(f"\n{'='*72}")
        print(f"{len(crowded)} AMBIGUOUS - not exactly two distinct devices")
        print(f"{'='*72}")
        for net, ends in crowded:
            print(f"  {net}")
            for e in ends:
                print(f"      {e['device']}:{e['iface']} {e['addr']}")

    if missing_parent:
        print(f"\n{len(missing_parent)} skipped - parent interface not in NetBox")
        for net, ends in missing_parent:
            for e in ends:
                if not e["parent_id"]:
                    print(f"  {e['device']}:{e['iface']} wants parent "
                          f"'{e['parent']}' which does not exist")

    if unassigned:
        print(f"\n{len(unassigned)} addresses not attached to an interface")

    if args.dry_run:
        print("\nnothing written")
        return

    print(f"\n{'='*72}")
    print("creating cables")
    print(f"{'='*72}")

    created = skipped = failed = 0
    for net, a, b in pairs:
        payload = {
            "a_terminations": [
                {"object_type": "dcim.interface", "object_id": a["parent_id"]}
            ],
            "b_terminations": [
                {"object_type": "dcim.interface", "object_id": b["parent_id"]}
            ],
            "status": "connected",
            "type": args.type,
            "label": str(net),
        }
        r = api_post("dcim/cables", payload)

        left = f"{a['device']}:{a['parent']}"
        right = f"{b['device']}:{b['parent']}"

        if r.status_code < 300:
            print(f"  + {left} <-> {right}")
            created += 1
        elif "already has a cable" in r.text or "occupied" in r.text.lower():
            print(f"  = {left} <-> {right}  (already terminated)")
            skipped += 1
        else:
            print(f"  ! {left} <-> {right}")
            print(f"      {r.status_code}: {r.text[:200]}")
            failed += 1

    print(f"\ncreated {created}, skipped {skipped}, failed {failed}")
    if orphans:
        print(f"\n{len(orphans)} orphans above are real topology bugs. "
              f"Fix the device config, re-gather, re-run the interface import.")


if __name__ == "__main__":
    main()