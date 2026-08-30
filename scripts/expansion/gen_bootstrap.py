#!/usr/bin/env python3
"""
Generate VRF MGMT bootstrap configs from a link map.

Usage:
    python3 gen_bootstrap.py links.yml --out bootstrap/

Produces one .txt per device, ready to paste into a console.
"""

import argparse
import ipaddress
import pathlib
import sys

import yaml

MGMT_VLAN = 10
P2P_POOL = ipaddress.ip_network("10.8.4.0/22")
LOOPBACK_NET = "10.8.2"

# Loopback ranges by org prefix, per the addressing schema
LOOPBACK_RANGES = {
    "kc":  (1, 49),
    "fc":  (50, 99),
    "crv": (100, 149), "vtq": (100, 149), "mrd": (100, 149),
    "znt": (100, 149), "hcn": (100, 149), "nmb": (100, 149),
    "ktr": (100, 149),
    "dc":  (150, 199),
}

TEMPLATE = """! ===== {device} =====
enable
configure terminal
!
hostname {device}
ip domain name lab.local
no ip domain lookup
!
vrf definition MGMT
 address-family ipv4
 exit-address-family
!
username admin privilege 15 algorithm-type scrypt secret admin
!
interface Loopback10
 description MGMT loopback
 vrf forwarding MGMT
 ip address {loopback} 255.255.255.255
 no shutdown
!
{interfaces}!
router ospf 1 vrf MGMT
 router-id {loopback}
 passive-interface Loopback10
 network 10.8.0.0 0.0.255.255 area 0
!
ip ssh version 2
ip ssh server algorithm kex diffie-hellman-group14-sha1
!
line vty 0 4
 login local
 transport input ssh
 exec-timeout 30 0
!
end
crypto key generate rsa modulus 2048
write memory
"""

IFACE_BLOCK = """interface {physical}
 no ip address
 no shutdown
!
interface {physical}.{vlan}
 description MGMT to {peer}
 encapsulation dot1Q {vlan}
 vrf forwarding MGMT
 ip address {ip} 255.255.255.254
 ip ospf network point-to-point
 no shutdown
!
"""


def assign_loopbacks(devices):
    """Assign a /32 per device from its org's range, honouring pins."""
    used = set()
    result = {}

    # Explicit pins first, so existing devices keep their addresses
    for name, cfg in devices.items():
        pinned = (cfg or {}).get("loopback")
        if pinned:
            result[name] = pinned
            used.add(int(pinned.split(".")[-1]))

    for name in sorted(devices):
        if name in result:
            continue
        org = name.split("-")[0]
        lo, hi = LOOPBACK_RANGES.get(org, (200, 249))
        for octet in range(lo, hi + 1):
            if octet not in used:
                result[name] = f"{LOOPBACK_NET}.{octet}"
                used.add(octet)
                break
        else:
            sys.exit(f"no free loopback for {name} in range {lo}-{hi}")

    return result


def assign_p2p(links):
    """Walk the pool handing out a /31 per link."""
    subnets = P2P_POOL.subnets(new_prefix=31)
    out = []
    for link in links:
        net = next(subnets)
        a_ip, b_ip = list(net.hosts()) if net.num_addresses > 2 else list(net)
        out.append({**link, "a_ip": str(a_ip), "b_ip": str(b_ip), "net": str(net)})
    return out


def build(devices, links, loopbacks):
    """Collect each device's interface blocks, then render."""
    per_device = {name: [] for name in devices}

    for link in links:
        per_device.setdefault(link["a"], []).append(
            IFACE_BLOCK.format(physical=link["a_int"], vlan=MGMT_VLAN,
                               peer=link["b"], ip=link["a_ip"])
        )
        per_device.setdefault(link["b"], []).append(
            IFACE_BLOCK.format(physical=link["b_int"], vlan=MGMT_VLAN,
                               peer=link["a"], ip=link["b_ip"])
        )

    return {
        name: TEMPLATE.format(
            device=name,
            loopback=loopbacks[name],
            interfaces="".join(blocks),
        )
        for name, blocks in per_device.items()
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("linkfile")
    ap.add_argument("--out", default="bootstrap")
    args = ap.parse_args()

    data = yaml.safe_load(pathlib.Path(args.linkfile).read_text())
    devices = data["devices"]
    links = assign_p2p(data["links"])
    loopbacks = assign_loopbacks(devices)

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    configs = build(devices, links, loopbacks)
    for name, text in configs.items():
        (outdir / f"{name}.txt").write_text(text)

    # A summary you can paste into docs/addressing.md
    print(f"{'DEVICE':<18} {'LOOPBACK':<14} LINKS")
    for name in sorted(configs):
        n = sum(1 for l in links if name in (l["a"], l["b"]))
        print(f"{name:<18} {loopbacks[name]:<14} {n}")

    print(f"\n{'LINK':<40} SUBNET")
    for l in links:
        pair = f"{l['a']}:{l['a_int']} <-> {l['b']}:{l['b_int']}"
        print(f"{pair:<40} {l['net']}  ({l['a_ip']} / {l['b_ip']})")

    print(f"\nWrote {len(configs)} configs to {outdir}/")


if __name__ == "__main__":
    main()
