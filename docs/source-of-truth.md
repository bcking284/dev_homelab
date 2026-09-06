# Source of Truth

How NetBox became the thing that defines this network, and what changed when it did.

---

## The problem it solves

Before NetBox, the network was described by 36 independent YAML files. Each one held one device's half of several links. Two halves that disagreed was not an error state, because nothing related them to each other.

Concretely, this was in the repo for weeks:

```yaml
# ktr-p04.yml
- name: GigabitEthernet5.10
  description: MGMT to hcn-p02          # says one thing
  ipv4:
    - address: 10.8.4.17/31             # pairs with vtq-p01
```

The description and the addressing described different links. Nothing checked, because from a file's point of view both statements were just text.

NetBox models a cable as **one object with two terminations**. `ktr-p04:Gi5` connects to `vtq-p01:Gi2` is a single fact. You cannot describe one end wrong, because there is only one description. And you cannot terminate an interface twice, because NetBox refuses.

That refusal is the entire value proposition.

---

## What it caught

Populating NetBox surfaced five defects in a topology that had been running for weeks and looked healthy.

**Duplicate loopback.** `kc-hq-nsa01` had `10.8.2.5/32` on Loopback10, the same address as `kc-hq-stb01`. Its own router LSA gave it away:

```
Advertising Router: 10.8.2.4
    Link connected to: a Stub Network
     (Link ID) Network/subnet number: 10.8.2.5      <- not .4
```

OSPF router-id is sticky. It does not follow a loopback change until the process is cleared, so the LSA was signed with the old ID while advertising the new address. This produced a ping pattern of exactly five successes and five failures, repeating, as SPF alternated between two advertisers of the same prefix.

`10.8.2.4` was absent from every routing table in the lab, because nothing advertised it.

**Duplicate physical interface.** `ktr-p05` had `GigabitEthernet8.10` defined twice in its bootstrap, once for each of two links. The second definition overwrote the first, so one link silently did not exist. The far end sat waiting for a neighbor that would never appear.

**Missing interface.** `ktr-p02` was created in EVE-NG with fewer Ethernets than the topology needed. The link to `ktr-p01:Gi6` was drawn in the diagram against a port QEMU never presented.

**Mask mismatch.** The KingCorp transit had `10.0.3.1/30` on one end and `10.0.3.2/24` on the other. BGP worked, because both addresses are inside both masks. The two routers disagreed about how large the segment was.

**Six devices with unsaved config**, found while chasing the above:

```bash
ansible -i inventory all -m cisco.ios.ios_command \
  -a "commands='show ip interface brief | include manual'"
```

Including the `kc-hq-nsa01` loopback fix itself. A reload would have undone a morning of work.

None of these would surface from the YAML. All of them surfaced from a data model with relationships.

---

## The model

NetBox holds identity, addressing, and physical connectivity. It does not hold configuration.

| NetBox | The repo |
|---|---|
| Devices, interfaces, cables | OSPF areas, BGP policy |
| IP addresses, prefixes, VRFs | Route-maps, prefix-lists |
| Sites, tenants, roles, tags | Playbooks and templates |
| Management addressing | Everything protocol-shaped |

Trying to put protocol intent in NetBox is the standard early mistake. It has no model for an NSSA area or a route-map, and forcing one in through custom fields produces something worse than a YAML file.

### Hierarchy

```
Tenant groups           Providers / Customers
  Tenants               Corvid, KingCorp, Ku Transit, ...
    Devices             36, each with one role and one site
      Interfaces        physical, with subinterfaces as children
        IP addresses    assigned, VRF-aware
Cables                  one object, two terminations
```

Roles describe **what a device does** and each device gets exactly one: `core`, `edge`, `distribution`, `access`, `spine`, `leaf`, `provider_edge`, `provider_core`.

Tenants describe **who owns it**. Sites describe **where it is**.

Tags carry everything that cuts across those: `tier1`, `tier2`, `providers`, `customers`. A device can have many, which is what makes them the right home for attributes that single-value fields cannot express.

---

## The import

Three scripts in order, all idempotent and all with `--dry-run`.

### `scripts/netbox/device_import_netbox.py`

Creates devices. Role is parsed from the hostname (`kc-hq-cor01` → `cor` → `core`); site, tenant, and device type come from explicit mapping tables, because those are not derivable from a name.

Every slug is resolved before anything is created, so a typo fails the whole run rather than leaving a half-populated database.

### `scripts/netbox/import_interfaces.py`

Reads the output of:

```yaml
cisco.ios.ios_facts:
  gather_subset: min
  gather_network_resources: all
```

One task per device returns every resource module's `gathered` output at once, rather than polling module by module.

The script creates interfaces with correct types (`virtual` for subinterfaces and loopbacks, `1000base-t` for physical), sets parent relationships so `Gi1.10` nests under `Gi1`, creates VRFs, attaches addresses, and sets `primary_ip4` from Loopback10.

That last part matters more than it looks: `primary_ip4` becomes `ansible_host` in the generated inventory. Without it you get device names with no way to reach them.

### `scripts/netbox/import_cables.py`

Derives links by pairing addresses. Every /31 holds exactly two addresses, so the pairing is unambiguous and self-checking.

Addresses live on subinterfaces, but the cable is created between the **parent physical interfaces** — that is where a real cable would land, and it keeps the topology model independent of the VLAN design.

The report is the point:

```
2 ORPHANS - one end only, the far side does not exist
  10.8.4.40/31       ktr-p01:GigabitEthernet6.10 has 10.8.4.40/31
                     nothing holds 10.8.4.41
```

An orphan is a link configured on one side and not the other. Every one is a real bug.

---

## Dynamic inventory

`inventories/lab/netbox.yml` replaces `hosts.ini` entirely.

```yaml
plugin: netbox.netbox.nb_inventory
api_endpoint: http://10.8.1.22:8080
validate_certs: false
config_context: true
group_names_raw: true

group_by:
  - device_roles
  - tenants
  - sites
  - platforms
  - tags
```

Groups are now **derived, not declared**. A device is in `provider_edge` because its role is provider_edge, not because someone typed it under a heading. That cannot drift.

Adding a device is a NetBox operation. It appears in Ansible, in the right groups, with the right management address, with no file edited anywhere.

### Things that cost time

**`api_endpoint` is not templated.** A Jinja lookup in that field is passed through literally and produces `unknown url type`. The plugin reads `NETBOX_API` and `NETBOX_TOKEN` from the environment on its own, so either hardcode the URL or use those exact variable names.

**`group_names_raw: true`** strips the dimension prefix. Without it you get `device_roles_provider_edge` rather than `provider_edge`, and none of your existing `group_vars` filenames match.

**`tenant_groups` is not a valid `group_by` dimension.** The error message lists every option, which is more helpful than most. Tenant groups exist in the data model but not as an inventory grouping — use tags for that layer.

**`group_by: tags` reads device tags only.** Tagging a tenant or a site does not propagate to its devices.

**NetBox slugs become Ansible group names.** A site slugged `birmingham-hq` produces a group you must reference as `groups['birmingham-hq']`, because `groups.birmingham-hq` parses as subtraction in Jinja. Normalize slugs to underscores before anything references them.

**NetBox enforces IP uniqueness on the host address, not the CIDR.** A stale `10.0.3.2/24` blocks creating `10.0.3.2/30`. Any duplicate check should query by host address and report the conflict, rather than querying the exact prefix and failing on the POST.

---

## The stack

Six containers on the automation host: the app, a worker for background tasks, a housekeeping job, PostgreSQL, and two Redis instances — one for the task queue, one for caching.

```bash
cd ~/netbox
docker compose up -d
docker compose exec netbox /opt/netbox/netbox/manage.py createsuperuser
```

The first start runs migrations and takes several minutes. A `start_period` under about five minutes will mark the container unhealthy while it is still working perfectly well.

It lives on the **management network**, not in the datacenter, despite the datacenter being the more interesting story. NetBox generates the inventory used to fix the network; if it sat behind the fabric, a routing failure would take away the tool needed to repair it. Same principle as running management in its own VRF.

Backup before anything risky:

```bash
docker compose exec -T postgres pg_dump -U netbox netbox | gzip > netbox-$(date +%F).sql.gz
```

---

## What is still missing

**Drift detection.** NetBox currently reflects reality because it was populated from reality yesterday. Nothing keeps it that way. The pipeline needs a job that gathers device state, diffs it against NetBox, and fails on mismatch.

Without that, a source of truth rots — and rots worse than no source of truth, because people trust it.

**Config contexts.** NetBox can hold arbitrary JSON attached by role, site, tenant, platform, or tag, with inheritance it computes itself, surfaced as host variables by `nb_inventory`. That is `group_vars` with the hierarchy living alongside the data. Identity-shaped values (ASN, address blocks) belong there; protocol intent stays in the repo.

**Generating the testbed.** The pyATS testbed is still hand-maintained and duplicates what NetBox already knows. It should be a template over the API, regenerated on every pipeline run.

**Reconciliation in the other direction.** The import scripts create and skip; they never delete. A NetBox object whose device no longer has that interface stays forever. That needs a mode that flags orphaned NetBox records the same way the cable script flags orphaned addresses.