#!/usr/bin/env python3
"""
Create devices in NetBox from the lab inventory.

    export NETBOX_URL=http://localhost:8080
    export NETBOX_TOKEN=...

    python3 import_devices.py --dry-run
    python3 import_devices.py

Idempotent: existing devices are left alone, missing ones are created.
Run --dry-run first and read the table it prints.
"""

import argparse
import os
import sys

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

# ---------------------------------------------------------------------------
# Mapping tables. Hostname prefix -> NetBox slug.
# ---------------------------------------------------------------------------

ORG_TO_TENANT = {
    "kc":   "kingcorp",
    "fc":   "flynncorp",
    "dc":   "kingcorp-cloud",
    "crv":  "corvid",
    "vtq":  "vantiq",
    "mrd":  "meridian",
    "znt":  "zenith",
    "hcn":  "halcyon",
    "nmb":  "nimbus",
    "ktr":  "ku_transit",
    "inet": "kingcorp",          # shared edge; adjust if it gets its own tenant
}

ROLE_TO_SLUG = {
    "cor": "core",
    "nsa": "core",               # NSSA router is still a core router
    "stb": "core",               # stub router likewise
    "edg": "edge",
    "dst": "distribution",
    "acc": "access",
    "spn": "spine",
    "lef": "leaf",
    "pe":  "provider_edge",
    "p":   "provider_core",
    "rtr": "edge",               # inet-rtr01
}

# Site is not derivable from the hostname, so state it.
# PEs sit with the customer they serve; P routers sit in a colo.
SITE_OVERRIDES = {
    "kc-":       "birmingham-hq",
    "fc-":       "huntsville-hq",
    "dc-den-":   "denver-colo",
    "inet-":     "birmingham-hq",

    "mrd-pe":    "huntsville-hq",     # serves FlynnCorp
    "hcn-pe":    "huntsville-hq",     # serves FlynnCorp + KingCorp edge
    "znt-pe":    "birmingham-hq",     # serves KingCorp
    "crv-pe":    "denver-colo",       # serves the DC
    "vtq-pe":    "denver-colo",       # serves the DC

    "mrd-p":     "atlanta-colo",
    "hcn-p":     "atlanta-colo",
    "znt-p":     "atlanta-colo",
    "crv-p":     "denver-colo",
    "vtq-p":     "denver-colo",
    "nmb-p":     "denver-colo",
    "ktr-p04":     "atlanta-colo",      # backbone; split across colos if you prefer
    "ktr-p02":     "atlanta-colo",
    "ktr-p06":     "atlanta-colo",
    "ktr-p03":     "denver-colo",
    "ktr-p01":     "denver-colo",
    "ktr-p05":     "denver-colo",
}

# Which image each device runs. Everything not listed defaults to CSR1000v.
DEVICE_TYPE_OVERRIDES = {
    "dc-den-lef": "vios_l3_switch",
    "dc-den-spn": "vios_l3_switch",
    "fc-hq-acc":  "vios_l3_switch",
    "fc-hq-dst":  "vios_l3_switch",
}
DEFAULT_DEVICE_TYPE = "csr1000v"

PLATFORM_FOR_TYPE = {
    "csr1000v":       "ios_xe",
    "vios_router":    "ios",
    "vios_l3_switch": "ios",
}

# name -> management IP, straight from the inventory
DEVICES = {
    "kc-hq-cor01": "10.8.2.1",
    "kc-hq-cor02": "10.8.2.2",
    "kc-hq-cor03": "10.8.2.3",
    "kc-hq-nsa01": "10.8.2.4",
    "kc-hq-stb01": "10.8.2.5",
    "kc-hq-edg01": "10.8.2.253",
    "fc-hq-acc01": "10.8.2.50",
    "fc-hq-acc02": "10.8.2.51",
    "fc-hq-dst01": "10.8.2.52",
    "fc-hq-edg01": "10.8.2.53",
    "fc-hq-edg02": "10.8.2.54",
    "crv-p01":     "10.8.2.100",
    "crv-pe01":    "10.8.2.101",
    "hcn-p01":     "10.8.2.102",
    "hcn-p02":     "10.8.2.103",
    "hcn-pe01":    "10.8.2.104",
    "ktr-p01":     "10.8.2.105",
    "ktr-p02":     "10.8.2.106",
    "ktr-p03":     "10.8.2.107",
    "ktr-p04":     "10.8.2.108",
    "ktr-p05":     "10.8.2.109",
    "ktr-p06":     "10.8.2.110",
    "mrd-p01":     "10.8.2.111",
    "mrd-pe01":    "10.8.2.112",
    "nmb-p01":     "10.8.2.113",
    "nmb-p02":     "10.8.2.114",
    "vtq-p01":     "10.8.2.115",
    "vtq-pe01":    "10.8.2.116",
    "znt-p01":     "10.8.2.117",
    "znt-pe01":    "10.8.2.118",
    "dc-den-lef01": "10.8.2.150",
    "dc-den-lef02": "10.8.2.151",
    "dc-den-lef03": "10.8.2.152",
    "dc-den-spn01": "10.8.2.153",
    "dc-den-spn02": "10.8.2.154",
    "inet-rtr01":  "10.8.2.254",
}


# ---------------------------------------------------------------------------


def api_get(path, **params):
    r = S.get(f"{NETBOX}/api/{path}/", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path, payload):
    r = S.post(f"{NETBOX}/api/{path}/", json=payload, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"POST {path} failed {r.status_code}: {r.text[:400]}")
    return r.json()


def lookup_id(path, slug):
    """Resolve a slug to an object id, or exit with something readable."""
    data = api_get(path, slug=slug)
    if data["count"] == 0:
        sys.exit(f"not found in NetBox: {path} slug='{slug}' - create it first")
    return data["results"][0]["id"]


def parse_role(name):
    """kc-hq-cor01 -> cor,  crv-pe01 -> pe,  ktr-p03 -> p"""
    last = name.split("-")[-1]
    stem = last.rstrip("0123456789")
    if stem in ROLE_TO_SLUG:
        return ROLE_TO_SLUG[stem]
    sys.exit(f"cannot derive role from '{name}' (stem '{stem}') - "
             f"add it to ROLE_TO_SLUG")


def pick(name, table, default=None, label=""):
    """Longest matching prefix wins, so 'crv-pe' beats 'crv-p'."""
    best = None
    for prefix, value in table.items():
        if name.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, value)
    if best:
        return best[1]
    if default:
        return default
    sys.exit(f"no {label} mapping for '{name}'")


def plan():
    rows = []
    for name, mgmt_ip in sorted(DEVICES.items()):
        org = name.split("-")[0]
        rows.append({
            "name": name,
            "mgmt_ip": mgmt_ip,
            "role": parse_role(name),
            "tenant": ORG_TO_TENANT.get(org) or sys.exit(
                f"no tenant mapping for org '{org}' in '{name}'"),
            "site": pick(name, SITE_OVERRIDES, label="site"),
            "device_type": pick(name, DEVICE_TYPE_OVERRIDES,
                                default=DEFAULT_DEVICE_TYPE),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = plan()

    print(f"{'DEVICE':<15} {'ROLE':<15} {'TENANT':<16} {'SITE':<16} {'TYPE':<15} MGMT")
    print("-" * 95)
    for r in rows:
        print(f"{r['name']:<15} {r['role']:<15} {r['tenant']:<16} "
              f"{r['site']:<16} {r['device_type']:<15} {r['mgmt_ip']}")

    if args.dry_run:
        print(f"\n{len(rows)} devices planned. Nothing written.")
        return

    # Resolve every slug once up front so a typo fails before we create anything
    print("\nresolving references...")
    ids = {
        "role":     {r: lookup_id("dcim/device-roles", r)
                     for r in {x["role"] for x in rows}},
        "tenant":   {t: lookup_id("tenancy/tenants", t)
                     for t in {x["tenant"] for x in rows}},
        "site":     {s: lookup_id("dcim/sites", s)
                     for s in {x["site"] for x in rows}},
        "type":     {d: lookup_id("dcim/device-types", d)
                     for d in {x["device_type"] for x in rows}},
    }
    ids["platform"] = {
        p: lookup_id("dcim/platforms", p)
        for p in {PLATFORM_FOR_TYPE[x["device_type"]] for x in rows}
    }

    created = skipped = 0
    for r in rows:
        existing = api_get("dcim/devices", name=r["name"])
        if existing["count"]:
            print(f"  = {r['name']} exists")
            skipped += 1
            continue

        api_post("dcim/devices", {
            "name":        r["name"],
            "role":        ids["role"][r["role"]],
            "device_type": ids["type"][r["device_type"]],
            "site":        ids["site"][r["site"]],
            "tenant":      ids["tenant"][r["tenant"]],
            "platform":    ids["platform"][PLATFORM_FOR_TYPE[r["device_type"]]],
            "status":      "active",
            "comments":    f"mgmt {r['mgmt_ip']}",
        })
        print(f"  + {r['name']}")
        created += 1

    print(f"\ncreated {created}, skipped {skipped}")
    print("management IPs go in with the interface import, not here")


if __name__ == "__main__":
    main()