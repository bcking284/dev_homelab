#!/usr/bin/env python3
"""
Create interfaces and IP addresses in NetBox from gathered device state.

    export NETBOX_URL=http://localhost:8080
    export NETBOX_TOKEN=...

    python3 import_interfaces.py --dir backups/gathered --dry-run
    python3 import_interfaces.py --dir backups/gathered

Reads one YAML per device, as produced by:
    cisco.ios.ios_facts: gather_network_resources=all

Expects each file to contain the keys 'interfaces', 'l3_interfaces',
'vrf_interfaces' at the top level. Idempotent - existing objects are skipped.

Devices must already exist in NetBox (run import_devices.py first).
"""

import argparse
import os
import pathlib
import re
import sys

import requests
import yaml

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

# The interface this device is managed on. Its address becomes primary_ip4.
MGMT_INTERFACE = "Loopback10"

PHYSICAL_TYPE = "1000base-t"
VIRTUAL_TYPE = "virtual"


def api_get(path, **params):
    r = S.get(f"{NETBOX}/api/{path}/", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path, payload):
    r = S.post(f"{NETBOX}/api/{path}/", json=payload, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"POST {path} failed {r.status_code}: {r.text[:400]}")
    return r.json()


def api_patch(path, obj_id, payload):
    r = S.patch(f"{NETBOX}/api/{path}/{obj_id}/", json=payload, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"PATCH {path}/{obj_id} failed {r.status_code}: {r.text[:400]}")
    return r.json()


def is_sub(name):
    """GigabitEthernet1.10 is a subinterface; GigabitEthernet1 is not."""
    return "." in name


def parent_of(name):
    return name.split(".")[0]


def iface_type(name):
    if is_sub(name) or name.lower().startswith("loopback"):
        return VIRTUAL_TYPE
    return PHYSICAL_TYPE


def load_device_files(directory):
    """Return {device_name: parsed_yaml}. Filename stem before '_' is the host."""
    out = {}
    for path in sorted(pathlib.Path(directory).glob("*.yml")):
        stem = path.stem
        # strip a trailing _all / _interfaces / etc
        host = re.sub(r"_(all|interfaces|ospf|bgp|policy)$", "", stem)
        data = yaml.safe_load(path.read_text())
        if not data:
            print(f"  ! {path.name} is empty, skipping")
            continue
        out.setdefault(host, {}).update(data)
    return out


def build_plan(devices):
    """Flatten the gathered structures into one row per interface."""
    plan = {}

    for host, data in devices.items():
        vrf_by_iface = {
            i["name"]: i.get("vrf_name")
            for i in data.get("vrf_interfaces", []) or []
        }
        ip_by_iface = {}
        for i in data.get("l3_interfaces", []) or []:
            addrs = [a["address"] for a in (i.get("ipv4") or []) if a.get("address")]
            if addrs:
                ip_by_iface[i["name"]] = addrs

        rows = []
        for i in data.get("interfaces", []) or []:
            name = i["name"]
            rows.append({
                "name":        name,
                "type":        iface_type(name),
                "parent":      parent_of(name) if is_sub(name) else None,
                "description": i.get("description", "") or "",
                "enabled":     i.get("enabled", True),
                "vrf":         vrf_by_iface.get(name),
                "addresses":   ip_by_iface.get(name, []),
            })

        # l3_interfaces sometimes lists something 'interfaces' missed
        known = {r["name"] for r in rows}
        for name, addrs in ip_by_iface.items():
            if name not in known:
                rows.append({
                    "name":        name,
                    "type":        iface_type(name),
                    "parent":      parent_of(name) if is_sub(name) else None,
                    "description": "",
                    "enabled":     True,
                    "vrf":         vrf_by_iface.get(name),
                    "addresses":   addrs,
                })

        # parents before children, so the parent id exists when we need it
        rows.sort(key=lambda r: (is_sub(r["name"]), r["name"]))
        plan[host] = rows

    return plan


def ensure_vrfs(plan, dry_run):
    """Create any VRF referenced by an interface."""
    names = {r["vrf"] for rows in plan.values() for r in rows if r["vrf"]}
    ids = {}
    for name in sorted(names):
        found = api_get("ipam/vrfs", name=name)
        if found["count"]:
            ids[name] = found["results"][0]["id"]
            continue
        if dry_run:
            print(f"  + would create VRF {name}")
            ids[name] = None
            continue
        ids[name] = api_post("ipam/vrfs", {"name": name})["id"]
        print(f"  + VRF {name}")
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="backups/gathered")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", help="only this device")
    args = ap.parse_args()

    devices = load_device_files(args.dir)
    if args.limit:
        devices = {k: v for k, v in devices.items() if k == args.limit}
    if not devices:
        sys.exit(f"no device files found in {args.dir}")

    plan = build_plan(devices)

    total_ifaces = sum(len(r) for r in plan.values())
    total_ips = sum(len(i["addresses"]) for r in plan.values() for i in r)
    print(f"{len(plan)} devices, {total_ifaces} interfaces, {total_ips} addresses\n")

    for host in sorted(plan):
        rows = plan[host]
        n_ip = sum(len(r["addresses"]) for r in rows)
        print(f"{host:<16} {len(rows):>3} interfaces, {n_ip:>2} addresses")

    if args.dry_run:
        print("\nnothing written")
        for host in sorted(plan):
            print(f"\n--- {host} ---")
            for r in plan[host]:
                addr = ", ".join(r["addresses"]) or "-"
                vrf = r["vrf"] or "-"
                print(f"  {r['name']:<26} {r['type']:<12} vrf={vrf:<8} {addr}")
        return

    vrf_ids = ensure_vrfs(plan, args.dry_run)

    for host in sorted(plan):
        dev = api_get("dcim/devices", name=host)
        if not dev["count"]:
            print(f"  ! {host} not in NetBox, skipping")
            continue
        dev_id = dev["results"][0]["id"]
        print(f"\n{host}")

        iface_ids = {}
        mgmt_ip_id = None

        for r in plan[host]:
            found = api_get("dcim/interfaces", device_id=dev_id, name=r["name"])
            if found["count"]:
                iface_id = found["results"][0]["id"]
                print(f"  = {r['name']}")
            else:
                payload = {
                    "device":      dev_id,
                    "name":        r["name"],
                    "type":        r["type"],
                    "enabled":     r["enabled"],
                    "description": r["description"],
                }
                if r["parent"] and r["parent"] in iface_ids:
                    payload["parent"] = iface_ids[r["parent"]]
                if r["vrf"] and vrf_ids.get(r["vrf"]):
                    payload["vrf"] = vrf_ids[r["vrf"]]
                iface_id = api_post("dcim/interfaces", payload)["id"]
                print(f"  + {r['name']}")

            iface_ids[r["name"]] = iface_id

            for addr in r["addresses"]:
                found = api_get("ipam/ip-addresses", address=addr)
                if found["count"]:
                    ip_id = found["results"][0]["id"]
                    print(f"      = {addr}")
                else:
                    payload = {
                        "address":               addr,
                        "assigned_object_type":  "dcim.interface",
                        "assigned_object_id":    iface_id,
                        "status":                "active",
                    }
                    if r["vrf"] and vrf_ids.get(r["vrf"]):
                        payload["vrf"] = vrf_ids[r["vrf"]]
                    ip_id = api_post("ipam/ip-addresses", payload)["id"]
                    print(f"      + {addr}")

                if r["name"] == MGMT_INTERFACE:
                    mgmt_ip_id = ip_id

        if mgmt_ip_id:
            api_patch("dcim/devices", dev_id, {"primary_ip4": mgmt_ip_id})
            print(f"  * primary_ip4 set from {MGMT_INTERFACE}")

    print("\ndone. cables are the next step.")


if __name__ == "__main__":
    main()