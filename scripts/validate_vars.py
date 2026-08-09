#!/usr/bin/env python3
"""Schema and referential integrity checks on host_vars."""
import ipaddress
import pathlib
import sys
import yaml

HOST_VARS = pathlib.Path("inventories/lab/host_vars")
errors = []


def err(host, msg):
    errors.append(f"{host}: {msg}")


for f in sorted(HOST_VARS.glob("*.yml")):
    host = f.stem
    try:
        data = yaml.safe_load(f.read_text()) or {}
    except yaml.YAMLError as e:
        err(host, f"invalid YAML: {e}")
        continue

    bgp = data.get("bgp") or {}
    defined_maps = set()

    for rm in bgp.get("route_maps") or []:
        name = rm.get("name")
        defined_maps.add(name)
        for i, entry in enumerate(rm.get("entries") or []):
            if not isinstance(entry, dict):
                err(host, f"route_map {name} entry {i} is a "
                          f"{type(entry).__name__} ({entry!r}), expected a mapping")
            elif "seq" not in entry or "action" not in entry:
                err(host, f"route_map {name} entry {i} missing seq or action")

    for nbr in bgp.get("neighbors") or []:
        for key in ("inbound_route_map", "outbound_route_map"):
            ref = nbr.get(key)
            if ref and ref not in defined_maps:
                err(host, f"neighbor {nbr.get('name')} {key}={ref} is undefined")

    redist = ((bgp.get("redistribute") or {}).get("ospf") or {}).get("route_map")
    if redist and redist not in defined_maps:
        err(host, f"redistribute ospf route_map={redist} is undefined")

    for net in bgp.get("networks") or []:
        try:
            ipaddress.ip_network(f"{net.get('number')}/{net.get('mask')}", strict=True)
        except ValueError as e:
            err(host, f"network {net.get('number')} {net.get('mask')}: {e}")

    for intf in (data.get("ospf") or {}).get("ospf_interfaces") or []:
        for key in ("name", "ip_address", "subnet_mask", "ospf_area"):
            if key not in intf:
                err(host, f"ospf_interface {intf.get('name', '<unnamed>')} missing '{key}'")

if errors:
    print(f"FAILED: {len(errors)} problem(s)\n")
    for e in errors:
        print(f"  x {e}")
    sys.exit(1)

print(f"All host_vars passed validation.")