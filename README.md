# Network as Code

**A CI/CD pipeline for network configuration, built from scratch in a homelab.**

Push a change to a YAML file. A pipeline lints it, validates it, takes a rollback checkpoint on every device, shows you exactly what would change, and waits. You click deploy. It applies the change, snapshots the network again, and hands you a diff of everything that moved.

That's the whole idea. This repo is how it got built, including the parts that didn't work.

---

## Why

On 05/23 I pushed an OSPF change to five routers. Three of them ended up in states I didn't intend — router-id under the wrong process on one, no network statements on another. I wrote this in my notes at the time:

> *I still have no idea how that happened.*

I fixed it by hand, comparing `show run` output across five terminals. It took an evening. Nothing about that process would have scaled to fifty devices, or 100, or 1000.

The problem wasn't that I was careless. The problem was that **my quality control was me, at the moment of the change, remembering to check things.** That works until you're tired, or it's 2am, or someone else touches the repo.

This pipeline moves the checking from "a person's discipline" to "a property of the system."

---

## The lab

Seven Cisco devices in EVE-NG on an old gaming PC, plus an Ubuntu VM that runs the automation.

<!-- TODO: topology.png -->
![Topology](docs/diagrams/topology.png)

| Zone | Contents |
|---|---|
| **OSPF Area 0** | R1, R2, R3 — backbone |
| **OSPF Area 1 (stub)** | R5, behind R1 as ABR |
| **OSPF Area 2 (NSSA)** | R4, redistributing EIGRP 100 |
| **BGP AS 65512** | The internal network |
| **BGP AS 65513** | `inet_rtr` — internet edge and NAT |
| **BGP AS 65514** | `DMZ_rtr` |
| **Management** | VRF `MGMT`, VLAN 10, separate OSPF process, out-of-band from production |

Everything runs a second OSPF process (`900`) for production routing and process `1` inside VRF MGMT for management. That separation matters: **the pipeline reaches devices over the management plane, so breaking production routing doesn't cut off the tool that fixes it.**

`AUTO_box` is a 2-core / 4 GB Ubuntu VM hanging off the management switch. It runs Docker, the GitLab runner, and nothing else of consequence.

---

## What the pipeline does

<!-- TODO: pipeline-graph.png — the four-stage view with the manual deploy button -->
![Pipeline](docs/images/pipeline.png)

Four stages. Nothing writes to a device until a human clicks a button.

### build — no network contact

| Job | What it catches |
|---|---|
| `lint-yaml` | Malformed YAML, trailing whitespace, duplicate keys, CRLF |
| `validate-vars` | Schema violations and referential integrity in the data model |

`validate_vars.py` is a hundred lines of plain Python. On its first run it found four bugs that had been sitting in the repo for weeks:

```
FAILED: 4 problem(s)

  x R1: route_map BLOCK_OSPF_TO_IBGP entry 0 is a str ('seq'), expected a mapping
  x R1: neighbor inet_rtr outbound_route_map=SEND_OSPF_TO_EBGP is undefined
  x R1: network 10.0.3.2 255.255.255.0 has host bits set
  x R4: network 10.0.34.65 255.255.255.252 has host bits set
```

None of those would have crashed anything. IOS accepts `network 10.0.3.2 255.255.255.0` and silently normalizes it. That's exactly why they survived — **they were wrong in the source of truth and invisible on the device.**

### prevalidation — read-only

| Job | What it does |
|---|---|
| `reach-devices` | Every device answers, credentials work |
| `checkpoint` | Saves a named config checkpoint to flash on each device |
| `snapshot-pre` | pyATS captures OSPF, interface, and routing state |
| `check-config` | Ansible `--check` mode: computes the delta, changes nothing |

The `check-config` artifact is the thing you actually read before deciding. It's also a free compliance report — anything it wants to change is a device that has drifted from intent.

### deploy — manual gate

One button. Nothing happens until it's pressed.

### postvalidation — evidence

| Job | What it does |
|---|---|
| `smoke-test` | Every device still answers. Hard gate |
| `snapshot-post` | Second pyATS capture, diffed against the pre-snapshot |
| `rollback` | Manual button. `configure replace` back to the checkpoint |

---

## Design decisions

These are the parts worth arguing about, so here's the reasoning rather than just the config.

### Why the deploy is gated behind a button

It gives me a sense of control, and I can review how the code will be translated into a command structure, which I'm comfortable reading. It also lets me see which devices are currently in compliance, because the prevalidation stage inherently does that compliance check on every run.

### Why `configure replace` instead of replaying a saved config line by line

Because line by line isn't idempotent. Replaying an old config can only *add*. If the change I'm reverting created something the backup doesn't mention, nothing removes it, and I end up with the union of both states.

`configure replace` lets me get rid of config I might not even know will interfere with existing config. It lets me specify intent, and it saves me troubleshooting in the future when something breaks.

It also supports a dead-man switch, which is the right pattern for any change that could cut your own management path:

```
configure replace flash:ckpt-20260823-095159.cfg force revert trigger timer 5
```

If you don't issue `configure confirm` within five minutes, the device reverts itself.

### Why the pyATS diff warns instead of failing the pipeline

Because I may *want* there to be a change in state. New neighbors, new routes, new anything. The diff fails because some operational state changed — which is sometimes exactly what I asked for. I need to make that discernment before making the change, not have a script make it for me.

Part of why a vanilla developer would struggle with this: **you need to understand network engineering to read the diff.** That's a skill with a steep learning curve and it takes years. The tool can tell you *what* moved. It can't tell you whether that was the point.

So the diff is evidence, the human is the gate, and `smoke-test` — every device still reachable — is the only thing that fails the pipeline outright.

### Why the toolchain is containerized

Because with a container I don't have to worry about conflicting version requirements between different use cases. I want to build more containers — NetBox, monitoring, maybe security — and all of those have independent requirements that will cause a headache at some point.

It also saves resources, because they all run on Docker and share a host VM.

The concrete version of this: `AUTO_box` runs Ubuntu 20.04 with Python 3.8, which is EOL. `pip install pyats` there resolves to a two-year-old release and still collides with apt-installed packages. The same install inside `python:3.12-slim` just works. **The host stays legacy; the toolchain stays current.**

---

## Known gaps and workarounds

This section exists because a pipeline that only documents its successes isn't useful to anyone trying to build one.

**`ios_ospfv2` doesn't write stub area config.** The module's parser reads `area 1 stub` back as `{stub: {set: true}}`, and the argspec documents `stub` with `set` / `no_summary` / `no_ext_capability` suboptions — but no generated command ever appears. Read-side coverage without write-side coverage. Worked around with a small `ios_config` task that loops over the area definitions.

**No resource module covers `encapsulation dot1Q`.** Not in `ios_l3_interfaces`, not in `ios_interfaces`, not anywhere. Subinterface encapsulation needs an `ios_config` task, and it has to run *before* addressing or IOS rejects the `ip address` line.

**`ios_ospfv2` reports `changed` on every run.** It emits a bare `router ospf 900` as a container for child commands, finds nothing to put under it, and emits the orphan anyway. `before` and `after` in its own output are byte-identical. Suppressed with:

```yaml
changed_when: >-
  ospf_result.commands | default([])
  | reject('match', '^router ospf \d+( vrf \S+)?$')
  | list | length > 0
```

**Legacy SSH crypto.** IOS-XE 16.09.07 only offers `diffie-hellman-group14-sha1`. Debian 12 dropped SHA-1 KEX from its defaults, so the container couldn't negotiate at all. `ansible_ssh_common_args` had no effect because Ansible was defaulting to Paramiko, which ignores SSH config entirely. Fixed by switching to `ansible_network_cli_ssh_type: libssh` and baking the algorithm config into `/etc/ssh/ssh_config` in the image.

That last one is worth dwelling on. Every year the crypto floor rises and old gear sinks further below it. The long-run answer isn't weakening every client forever — it's a bastion allowed to speak legacy crypto with modern crypto everywhere else. That conversation is coming for a lot of OT networks.

**The pattern across all of these:** resource modules cover maybe 85% of a feature. You plan for the rest with `ios_config` and stop being surprised by it.

---

## Repo layout

```
├── .gitlab-ci.yml              pipeline definition
├── ansible.cfg
├── ci/Dockerfile               the toolchain image
├── inventories/lab/
│   ├── hosts.ini
│   ├── group_vars/             shared config shape
│   ├── host_vars/              per-device values — the source of truth
│   └── gathered/               device state pulled back as YAML
├── playbooks/
│   ├── prevalidation/          backup, checkpoint, state gathering
│   ├── routing/ospf/           OSPF via resource modules
│   ├── routing/bgp/
│   ├── interfaces/
│   ├── rollback/               configure replace
│   └── quickies/               one-off operational tasks
├── pyats/
│   ├── testbeds/lab.yml
│   └── snapshots/              pre and post state captures
├── scripts/
│   ├── validate_vars.py        schema and referential integrity
│   ├── prettify.py             readable YAML from gathered state
│   ├── RESTCONF/               direct API work against IOS-XE
│   └── validation/
└── docs/
    ├── lab-journal.md          daily notes since 05/02/26
    ├── diagrams/
    └── addressing/
```

---

## Running it

**Requirements:** Docker, a GitLab project, and devices you can reach.

Build the toolchain image:

```bash
docker build -t netauto:local ci/
```

Register a runner with `pull_policy = ["if-not-present"]` so it uses the local image rather than reaching for a registry.

Set `NET_USERNAME`, `NET_PASSWORD`, and `NET_ENABLE` as masked CI/CD variables in GitLab. Locally, the same names live in a gitignored `.env`. One mechanism, two environments:

```yaml
ansible_user: "{{ lookup('env', 'NET_USERNAME') }}"
ansible_password: "{{ lookup('env', 'NET_PASSWORD') }}"
```

Working interactively:

```bash
docker run --rm -it -v "$PWD:/work" -w /work \
  -e NET_USERNAME -e NET_PASSWORD -e NET_ENABLE \
  netauto:local bash
```

Check before you push. CI is the backstop, not the feedback loop:

```bash
yamllint inventories/ playbooks/
python scripts/validate_vars.py
ansible-playbook -i inventories/lab/hosts.ini playbooks/routing/ospf/configure_ospf.yml --check
```

---

## What I'd tell someone starting this

**Start with one thing that catches one bug.** My first pipeline job printed "hello" and told me nothing. The second one found four real defects in data I'd been reading for weeks. That's the moment it stops being an exercise.

**Run the checks locally first.** I burned three CI round trips on lint findings a two-second local command would have shown me.

**The tests are the product; the pipeline is just the trigger.** An empty pipeline that always passes is theater. So is a job where every task skips — I had one of those for a week and the recap said `failed=0` the whole time.

**Automation multiplies mistakes.** A bad manual change hits one device. A bad playbook hits two hundred. The gates matter *more* in automation than they did in the CLI era, not less.

**Most of the difficulty isn't the network.** It was git, line endings, version skew, and container plumbing. The OSPF was the easy part.

---

## Roadmap

- NetBox as source of truth, generating inventory and host_vars
- Nornir for gather and drift detection at scale — threads rather than processes
- BGP fully configured, including via RESTCONF with a proper session class
- Topology redesign: switching redundancy, and moving `DMZ_rtr` somewhere that makes sense instead of a separate ASN off to the right
- More RAM on the EVE-NG host, which unblocks CML as a digital twin
- MPLS with simulated field sites
- QoS
- A Flask front end over the whole thing

Full daily notes going back to the first day of the lab are in [docs/lab-journal.md](docs/lab-journal.md).

---

*Built while studying for CCNP Automation. The pipeline maps closely to the AUTOCOR v2.0 blueprint — infrastructure as code, change validation, secret management — which was a happy accident rather than a plan.*