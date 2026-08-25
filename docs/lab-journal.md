# Building Enterprise Infrastructure with IaC, EVE-NG Homelab:

This project documents my journey building a network automation and CI/CD-style workflow using EVE-NG, Linux, Ansible, Python, Git, and GitHub. The lab is focused on automating configuration management, backing up multi-vendor device configurations, and developing repeatable infrastructure workflows similar to those used in modern enterprise environments.

# Current State:

<img width="1635" height="1132" alt="image" src="https://github.com/user-attachments/assets/7020bde3-13bd-4d77-8cff-bd1e5514c495" />

# Future State Pipeline:
- Include automated configuration deployments, configuration drift detection, compliance validation, and integrating more advanced automation tooling and pipelines.
-   - pyATS, learning more about this and using it for my tests
- deploy an open source NMS
- deploy Netbox for programmatic inventory management and IPAM
- Implement a RADIUS server, active directory, and some flavor of NAC solution
- Containerize servers and deploy terraform for provisioning
- Experiment with some different vendors, starting with a Palo Alto firewall, look into vendor neutral OpenConfig YANG
- if possible
- Redesign with datacenter hosting, Enterprise block, shared services block, and bring in some small offices
- Add secure remote work support
- Set up service provider side, configure some flavor of MPLS
- DMVPN hub-spoke topology with branch offices

# Work Notes:
The environment currently includes Cisco routers, switches, and ASA firewalls managed through Ansible playbooks and version-controlled through GitHub. 

# 08/13 – 08/19/26

- Deployed
  - Interactive container workflow - `docker run --rm -it -v "$PWD:/work" -w /work -e NET_USERNAME -e NET_PASSWORD -e NET_ENABLE netauto:local bash` drops into a shell inside the image with the repo mounted live. Wrapped as a `nash()` function in ~/.bashrc so it cds, sources .env, and launches in one word
  - Local-image pipeline (Option A) - abandoned the GitLab container registry for a single-runner lab. Image tagged `netauto:local`, runner `pull_policy` changed to `if-not-present` in ~/ci/config/config.toml. No push, no pull, no network
  - Legacy SSH crypto baked into the image - `/etc/ssh/ssh_config` in ci/Dockerfile with KexAlgorithms/HostKeyAlgorithms/PubkeyAcceptedAlgorithms/Ciphers/MACs additions. Confirmed libssh honors it. Crypto compatibility is now an image concern, credentials stay a repo concern
  - ci/Dockerfile committed to git - had been built on AUTO_box but never tracked
  - Resource module conversion started - configure_ospf.yml rewritten to use cisco.ios.ios_ospfv2 and cisco.ios.ios_ospf_interfaces. Template and render step eliminated. R1's host_vars restructured by hand into the module argspec shape
  - Debug tasks printing `.commands` after each resource module task - permanent visibility into the exact CLI being generated, since --diff doesn't work for these modules

- Fixed
  - `manifest unknown` on every job - image was built locally but never pushed to the registry, and pull_policy was `always`. Resolved by switching to the local-image approach rather than fixing the push
  - Debian 12 dropped SHA-1 KEX from its defaults - the newer base image refused to negotiate with IOS 16.09.07, which only offers diffie-hellman-group14-sha1 and group-exchange-sha1. `ansible_ssh_common_args` had no effect because pylibssh doesn't parse it; the fix had to be in /etc/ssh/ssh_config
  - Duplicate dict key in R1.yml line 101 - two `name:` keys at the same level, YAML silently kept the last and discarded the first. Caused by a missing `-` collapsing two list items into one dict
  - `config is of type list, unable to convert to dict` - ios_ospfv2 wants `{processes: [...]}`, the data was a bare list. ios_ospf_interfaces genuinely takes a bare list. Two modules, two shapes
  - Malformed ospf_cfg structure - process 900 was split across two list items, and process_id / router_id / passive_interfaces were nested inside the last network entry instead of being siblings at process level
  - Unquoted area IDs - `area_id: 1` parses as int, argspec says `type: str`. Confirmed with ansible-doc
  - `stdout_callback = yaml` - callback isn't in ansible-core 2.17 and isn't in ansible.posix either. Abandoned after two rebuilds in favor of a gather playbook using `to_nice_yaml`
  - `--env-file .env` rejected - Docker wants bare KEY=value and chokes on the `export` keyword. Use `-e VAR` passthrough with `source .env` first
  - Repeated merge conflicts on ansible.cfg and host_vars - editing the same files on both machines within minutes. Resolved with `checkout --theirs` and a rule: edit on home PC, pull on AUTO_box, don't edit on AUTO_box

- Found, not yet fixed
  - **ios_ospfv2 does not write stub area config.** The gathered parser reads `area 1 stub` back as `{stub: {set: true}}`, and the argspec documents `stub` with `set` / `no_summary` / `no_ext_capability` suboptions - but no generated command ever appears. Read-side coverage without write-side coverage
  - Consequence: the module reports `changed` on every run and emits a bare `router ospf 900`, because it sees a permanent diff it can never close. Not idempotent
  - Workaround identified: keep the resource module for the bulk, add a small `ios_config` task for the stub area, and remove `areas` from ospf_cfg so the module stops trying
  - R1's process 900 currently has router-id, passive-interface, and all three network statements but no `area 1 stub`. R1–R5 adjacency likely down until that's applied by hand on both ends
  - check-ospf was a false pass earlier in the week - every task skipped, only the save task reported. A gate that can't fail isn't a gate

- Learned
  - `type: dict` means no dash, `type: list` + `elements: dict` means dashes. That single rule from `ansible-doc` resolves almost every YAML shape question
  - JSON `[` → YAML `-` items; JSON `{` → indented keys with no dash; bare value → `key: value`
  - Column position is the only thing telling YAML which parent a key belongs to. Put scalars before nested blocks so misindentation is visible
  - Quote single-octet values (`area: "0"`) - bare `0` becomes an integer and modules silently skip blocks rather than erroring
  - `to_nice_yaml` sorts keys alphabetically, which is why generated output puts `network` before `process_id` and reads confusingly
  - Resource modules use SSH and CLI parsing, not RESTCONF. The JSON is just how ansible-cli displays return values
  - Images are inert filesystem snapshots; containers are processes created from them. `docker build` starts nothing
  - Docker layer caching means only the changed instruction and everything below it rebuilds - put slow, stable steps first

- Next up
  1. Apply `area 1 stub` by hand on R1 and R5 to restore the adjacency
  2. Add the `ios_config` stub-area task and remove `areas` from ospf_cfg; confirm the playbook goes idempotent
  3. Convert R2–R5 host_vars to the resource module shape
  4. Fix the check-ospf false pass
  5. Add `key-duplicates: enable` to .yamllint and an area-ID-is-string check to validate_vars.py
  6. Deploy stage with `when: manual`
  7. pyATS testbed + snapshot/diff post-validation
  8. Rollback wired to `when: on_failure` using the configure replace playbooks
  9. Still deferred: credential rotation with `algorithm-type scrypt`, creds out of the six RESTCONF scripts

# 08/11 – 08/13/26
- Deployed
  - Custom CI image (ci/Dockerfile) - python:3.12-slim base with ansible-core 2.17, ansible-pylibssh, yamllint, ansible-lint, and the cisco.ios / cisco.asa / ansible.netcommon collections baked in. Built and pushed to GitLab's container registry
  - .env on AUTO_box - NET_USERNAME / NET_PASSWORD / NET_ENABLE, gitignored, loaded via source .env
  - pyATS 24.9 installed on AUTO_box (user install)
  - reach-devices job passing - the runner now authenticates to R1–R5, inet_rtr, and mgmt_sw and pulls facts. First job to touch the network

- Fixed
  - Container SSH failure - root cause was Ansible defaulting to Paramiko, which ignores ~/.ssh/config entirely. 
  - Fixed with ansible_network_cli_ssh_type: libssh plus ansible_ssh_common_args in group_vars/all.yml. Config lives in the repo, so it applies identically on AUTO_box and in CI
  - AUTO_box breaking mid-session - group_vars/all.yml had been switched to lookup('env', ...) but .env was never created, so ansible_password resolved empty and Ansible fell through to publickey auth. Creating and sourcing .env resolved it
  - pyATS CLI wouldn't start - pkg_resources version conflict, pysmi-lextudio requiring requests>=2.26.0 against the system's 2.22.0. Fixed by upgrading requests and paramiko with pip3 install --user
  - ospf_config.j2 rewritten - switched from network statements to per-interface ip ospf <pid> area <n>, which eliminates the wildcard-mask bug entirely. Added a loop over ospf_areas so area X stub no-summary finally renders from the data model instead of being typed by hand. Corrected the structural bug where interface commands were nested inside the router ospf block
  - Lint cleared locally

- Learned / decided
  - IOSv 16.09.07 only supports diffie-hellman-group14-sha1 - no SHA-256 KEX available. Confirmed with ? at the CLI. Raising the devices wasn't an option, so the fix had to be client-side
  - Ubuntu 20.04 + Python 3.8 is a dead end for modern tooling - pyATS resolved to 24.9 (two years stale) because that's the newest release supporting 3.8, and even then it collided with apt-installed packages. Strong argument for containerizing the toolchain rather than fighting the host
  - --check --diff makes no changes - connects, computes the delta, writes nothing. Reliable for ios_config; unreliable across multi-task plays where later tasks depend on earlier ones having run
  - Line-by-line config replay can only add, never remove - which is why rollback_configs.yml never worked. configure replace is the correct mechanism; IOS computes both additions and removals itself
  - configure replace ... revert trigger timer N is a dead-man switch - auto-reverts unless you issue configure confirm. The right pattern for any change that could cut your own management path
  - Distro packages for fast-moving DevOps tools are years stale (gitlab-runner 11.2.0 from focal was the earlier example; pyATS 24.9 is this one)

- Next up
  - Verify the pipeline is actually using the registered image (jobs should drop to seconds with no pip install lines)
  - Test the rewritten ospf_config.j2 render - watch for prod_ospf_process_id and the ospf_areas nesting scope
  - --check --diff prevalidation stage - first look at drift between YAML and devices
  - Replace rollback_configs.yml with the configure replace checkpoint/rollback pair, and test it deliberately on R5
  - deploy stage with when: manual
  - pyATS testbed file + parse against R1 by hand, then snapshot/diff post-validation
  - rollback wired to when: on_failure
  - Still deferred: device credential rotation with algorithm-type scrypt, and moving creds out of the six RESTCONF Python scripts

# 08/08-08/10 (Getting Serious)
- OSPF troubleshooting (lab)
  - Brushing up on my OSPF
  - Root cause found: area ID mismatch on R1–R5 link. R5 had network 10.0.28.0 0.0.0.255 area 0, R1 had area 1. Hello packets silently discarded, no adjacency, R5's loopback never entered the LSDB
  - Fixed by moving R5's interfaces to area 1 and applying area 1 stub
  - Confirmed the fix via Type 3 summary LSAs for 10.0.28.0/30 and 10.0.28.129/32 appearing in area 0
  - Clarified: area X stub required on both routers (E-bit in hello); no-summary on ABR only
  - Latent bugs identified in ospf_config.j2 - not yet fixed:
  - Hardcoded 0.0.0.255 wildcard for every interface regardless of subnet mask
  - area X stub never rendered despite ospf_areas existing in the data model. This is why stub config had to be typed by hand

- Infrastructure deployed
  - Docker CE 28.1.1 + compose v2 on AUTO_box
  - GitLab account + project (bcking2841/dev_homelab), repo mirrored from GitHub
  - GitLab Runner 19.2.1 as a container, docker executor, python:3.12-slim, --docker-network-mode host, tagged homelab - Online and picking up jobs
  - SSH keys on both machines for both remotes; all four remotes converted from HTTPS to SSH
  - CI/CD variables in GitLab: NET_USERNAME, NET_PASSWORD, NET_ENABLE (masked/protected)
  - .gitlab-ci.yml with three jobs across two stages: lint-yaml, validate-vars, reach-devices
  - scripts/validate_vars.py - schema and referential integrity checks on host_vars
  - .yamllint - tuned rule config
  - .gitattributes - LF enforcement with vendor YANG excluded

- Bugs the pipeline caught
  - R1.yml - route-map BLOCK_OSPF_TO_IBGP had a bare - seq string instead of a mapping
  - R1.yml - neighbor referenced SEND_OSPF_TO_EBGP, which was never defined
  - R1.yml - network 10.0.3.2 / 255.255.255.0 had host bits set (should be .0)
  - R4.yml - network 10.0.34.65 / 255.255.255.252 had host bits set (should be .64)
  - More to come surely

- Troubleshooting log
  - Git:
    - 641 files showing as modified - diagnosed as line endings via equal insertion/deletion counts in git diff --stat
    - Working tree stayed CRLF after --renormalize; resolved with git rm --cached -r . && git reset --hard
    - Diverged history - six merge commits on GitHub from web-UI PRs vs. four local commits
    - git branch -d refusing deletion because the remote-tracking ref was already gone; needed -D after verifying with log A..B
    - Home PC stuck on a deleted branch, couldn't pull
    - Six-file merge conflict (line endings vs. real edits); resolved with checkout --theirs then re-normalize
    - Stash conflict on all.yml
    - Whitespace cleanup undone by a merge from the un-synced home PC
  - Authentication:
    - GitHub rejecting HTTPS password auth - remote was never converted to SSH
    - Prompt consumed a queued second command, producing a mangled username
    - Multiple SSH keys with non-default filenames not being offered; needed ~/.ssh/config with per-host IdentityFile
    - PowerShell ~ not expanding for native executables (ssh-keygen -f) - needs $env:USERPROFILE
  - Runner
    - apt install gitlab-runner pulled version 11.2.0 from focal (2018) - doesn't understand glrt- tokens. Purged, removed its systemd service
    - Ctrl+C during registration unregistered the runner and burned the token - registration tokens are single-use
    - Long-polling / request_concurrency warning: cosmetic, ignored
  - Pipeline
    - First run failed with yaml invalid / 0 jobs - actually GitLab account phone verification, misleadingly labeled
    - invalid config: not a mapping - .yamllint was created but never saved (empty file)
    - ~80 lint findings on first run; tuned the ruleset rather than ignoring the gate

- Habits established:
  - Pull before working, on whichever machine
  - One command at a time when a prompt is possible
  - Run linters and validators locally before pushing - CI is the backstop, not the feedback loop
  - Commit line-ending normalization separately, labeled as such
  - Verify with git log A..B in both directions before deleting anything

- Next up:
  - Finish lint cleanup, get reach-devices green (first job to authenticate to the network)
  - Add --check --diff prevalidation stage
  - Add deploy with when: manual
  - Add pyATS learn/diff post-validation
  - Fix ospf_config.j2 wildcard mask and stub-area rendering
  - Rotate device credentials with algorithm-type scrypt
  - Consider a custom CI image with ansible + collections + pyATS baked in (also covers objective 2.5)


# 06/06-07/26
- Focusing on integrating jinja templates with python before moving on to Ansible abstraction
- Created/Edited restconf_jinja_bgp.py first to send a single request, then to hold the yml 
- reorganized yaml files and structure to make more sense, by protocol
- did a deep dive into some of these python packages jinja2 and requests. help(jinja2) / help(request)
- spent some time study this documentation to understand the full capabilities beyond what I was using them for
- general python / jinja / yang / yaml structure and study
- began testing out the python script with bgp_base.j2 and bgp_addrfam_ipv4, troubleshooting along the way
- returning in the afternoon, ran into something interesting, ietf-yang-patch:patch payload format
- enables you to send a patch to native:native and then drill down into multiple "edits" within the payload
  - this solves my issue of having to send multiple patches, another aha moment.
- first, checked capabilities of device, see if it supports yang-patch
  - using https://R1/restconf/data/ietf-restconf-monitoring:restconf-state/capabilities
  - found urn:ietf:params:restconf:capability:yang-patch:1.0
- studying yang-patch to discern format and combined two jinja templates into one with "yang-patch-bgp.j2"
- trying a hard coded yang-patch test first in python, running into format errors again, troubleshooting
- looks like when bgp is fully not configured it has the same problem as the other method. I believe there is no workaround in this case to needing to send more than one payload.
- yang-patch worked great for editing, since indemnopentcy is built into it, but not so well for creation all in one go.
- realized I could probably just use if statements in my jinja template and generate configuration piece by piece
- Gave up on that for now and decided to just do this with ansible CLI for a quick win and call it a day
- added configure_bgp.yml to playbooks/routing/bgp dir
- 

# 05/31/26
Intro:
- Spent an hour in the morning writing plan for what is remaining from my original goal of this projects
- From a technical standpoint, I just need to write some REST and get to the point where I can configure all this BGP in one push
- Finally once that's done, from a workflow/procedural standpoint, I need to build my actual CI/CD workflow
- After all I've learned about CI/CD, I am thinking I'll need to get creative, since my lab is the same as my prod environment
- I could build a smaller lab and have my runner on that for tests. I will see how I feel when I get to that point.
- I've already started looking ahead and did some brainstorming. My vision for some of the next steps of this project:


WorkLog:
- struggled with some REST runtime mapping errors, resources not found, python, json, yang model references and syntax
- other issues included "device not accepted command", something like that
  - configuration database being locked due to the second part of my script executing too fast
  - unknown element in activate command
- Got a full(ish) BGP configuration patch using RESTCONF on R1
- Will be abstracting next and filling in values that aren't spam

# 05/30/26
- Stewed a little over the week about why I had to send three or more PATCHes to fully configure my router
- I was looking for a clean "here's the URI path for each of these and their JSON attributes" workflow, but nothing like that existed
- Learned that those URI paths were based off that YANG data model, and that I could discern where my API call should be based on containers, lists, and leafs
- I spent the morning doing some research and correlation between the YANG data model for ios-xe native, bgp, and interfaces to the URI path I would
- Found a repo located here https://github.com/YangModels/yang/blob/main/vendor/cisco/xe/16101/Cisco-IOS-XE-native.yang that I cloned into a separate directory on my computer
- Used pyang to build a tree out of this to help me more clearly visualize what I could expect my path to look like for these API calls.
- Dropped that pyang text file into my docs folder, checking for extensions to make it even easier to read in vscode
- I couldn't find any extensions for those trees, but I found a lot for YANG. Decided it might be best if I just get comfortable with the syntax
- I will generate more trees and merge them together in the future inside the docs/yang folder if I find it to be helpful
- Spent A LOT of time just combing through the Cisco-IOS-XE-ospf.yang, using curl to query each uri to see what works and what doesn't.
- learned about YANG syntax like @mount, groupings, augment, "uses", modules, and in greater depth about containers and leafs and how they influence the URI path, how I could read these to find out where I needed to send my API call.
- Not a lot to commit today besides some documentation I'm going to refer to later.
- I can now read YANG data models confidently

- Now, for my json payloads, instead of this:

root@kvm:~# curl -k -H "Accept: application/yang-data+json" "https://10.8.1.100/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-bgp:bgp"
66
{
  "Cisco-IOS-XE-bgp:bgp": [
    {
      "id": 123,
      "bgp": {
        "log-neighbor-changes": true
      },
      "address-family": {
        "no-vrf": {
          "ipv4": [
            {
              "af-name": "unicast",
              "ipv4-unicast": {
                "neighbor": [
                  {
                    "id": "1.1.1.1",
                    "activate": [null],
                    "route-map": [
                      {
                        "inout": "in",
                        "route-map-name": "FILTER-IN"
                      }
                    ]
                  }
                ],
                "network": {
                  "with-mask": [
                    {
                      "number": "1.2.3.0",
                      "mask": "255.255.255.0"
                    }
                  ]
                }
              }
            }
          ]
        }
      }
    }
  ]
}


I can do this:
root@kvm:~# curl -k -H "Accept: application/yang-data+json" "https://10.8.1.100/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-bgp:bgp=123/address-family/no-vrf/ipv4=unicast/ipv4-unicast/neighbor
=1.1.1.1"
{
  "Cisco-IOS-XE-bgp:neighbor": {
    "id": "1.1.1.1",
    "activate": [null],
    "route-map": [
      {
        "inout": "in",
        "route-map-name": "FILTER-IN"
      }
    ]
  }
}


# 05/24/26
- decided to stick with RESTCONF. I will proceed with the goal of this branch which is to configure those BGP routers via RESTCONF, write some python for some GETs, then PUT when I'm comfortable.
- I'll start with one router, pure python, then move on to doing the same thing with Ansible and jinja
- Basic BGP config, nothing fancy yet

Pipeline:
- I'd like to move to a csv IPAM soon, using a python script to update the hosts.ini file
  - This would let me run a python script that could update that file and possibly also get me a diff
- implement some route maps
- add in some new links and play around with path selection
- configure the ASA for BGP as well

Work Log:
- enabled restconf on IOS XE routers
- Wrote python script to grab restconf interface configs and drop them into a new directory in the scripts file
- removed validation folder (for now) and removed some old script placeholders
- I created a new directory for restconf outputs, first pulled the interfaces json, then did the full native
- Looked through them both and studied them a little bit.
- searched through some github repos for RESTCONF API reference for IOS XE
- searched through cisco devnet website
- with the interfaces json complete, some python scripts made, current running configs pulled to backups/pre_change, making my first commit on this branch
- came back, configured some very basic BGP on my inet router so that I could pull the config with restconf into json to see the exact format its expecting
- pulled config, next I'm going to delete this configuration, configure a jinja template using this json file as a base template, and fill out all my host vars in my bgp_routers group


# 05/24/26
- moving from host_vars -> Jinja -> rendered_configs -> push entire file -- to host_vars -> Ansible loops -> exact CLI commands under exact parents
- worked perfectly for R2, just had to fix some IP addressing in my host vars
- R3 needed some troubleshooting
- -vvv showed me I had a bad mask on my interfaces, fixed in host_vars on R1-3
- fixed mask, working like a charm
- fixed some other annoying typos like vlan tags I shouldn't have had added
- once base ospf configuration was done with CLI automation, changed workflow up
- Breaking new configs into features, using scp to copy new files to lab for test instead of pulling master branch
- created branch for ospf tuning, added stub and not so stubby area configuration
- added abr and asbr variables for later
- decided to switch up to restconf
- made branch for bgp/restconf
- enabled restconf on all routers
- was unable to enable restconf on the switch, I can do netconf though. 
- will consider merging this branch tomorrow and doing netconf instead next, pivoting to restconf later

# 05/23/26
- Plan was to configure OSPF areas 0-2 all on one go
- I started off by organizing the variables using the all.yml file for the network connection method, telling it to execute commands from priv enable, basic things that applied to all devices
- I had some issues reaching the firewall via SSH. I realized there was an access list I was missing, so I added that
- I configured an "ospf_interfaces" group in yml on each of those host_vars file. Taking time to make sure the heirarchy made sense. I started off with area 0
- I wrote an ospf_config.j2 to make sense with those host variables I had set, manually going through one of the routers to make sure the commands were being sent in the right order and the right syntax
- I was tired of the latency between my home PC and my port-forwarded configuration on my jump box, so I decided to just work from my home PC on all of this and commit and comment every change I made
- When I was ready to test it out, I would push to github, then pull down from my lab linux ansible host
- I ran the playbook for "render_ospf.yml", and checked the output, and the CLI looked good.
- The errors I was getting about module compatibility were annoying, and weren't affecting functionality. I tried to fix it the right way, but ansible was already up to date, so I also made some tweaks to my ansible.cfg file and they went away
- My playbook to actually push the configuration used a source file as that rendered config, so the idea was that it would push those commands out one by one and they'd all be fine and come right up
- I ran into an error, checked the configs, and it varied between them all what state they were in.
- Some had the router-id configured under the management vrf ospf process, which I still have no idea how that happened, some had no network statements, it just seemed the push didn't go out correctly
- I manually entered those cli commands in the exact order as the rendered config file I pushed, and it worked fine
- I started with CLI config for it to be the most familiar to me with my network engineering background. The idea was simple first, but since I wasn't sure what happened, I started looking into just jumping straight into RESTCONF
- I made a plan for 05/24 to give CLI configuration one more try, but move away from the intended config, render ospf, and push model.
- Going to try using slightly more logic in the playbooks, going piece by piece for interfaces and then the ospf config instead of pushing a config snippet

# 05/20/26
- Not much time today, wanted to get back into it though
- Instead of manually typing configuration, added some host vars yml files
- Spotted some errors in my address planning doc, fixed a few, will need debugging later
- Decided to start with the OSPF configuration. Base area 0, not adding stubs yet, will not push to devices today
- Created playbook to render ospf config that will be pushed to devices after some refinement
- Using as validation playbook before pushing changes
- Brushed off the dust on some Jinja, used it to call host vars and dynamically populate configuration commands
- Computer needs more RAM
- Plan for next work session is to complete the entire topology using this approach
  - This way, when the topology expands, I will be able to re-use a lot of this
- Future pipeline, once full topology is spun up using this toolset, (and I have more RAM) is to spin up netbox on another ubuntu server
- Will integrate netbox to replace host_vars and inventory files via API

# 05/10/26
- Caught up on notes from yesterday, reposted a slightly cleaner intended-state network topology
- Now that I've got the entire backplane set up on a dedicated VRF, my time in the CLI can be done with.
- From now on, I'm going to be using git to push changes from my personal laptop. No more editing files in the jumpbox.
- My objective for the day is to develop an enterprise workflow for the rest of this project, no more CLI:
  - Author intended network state from a dedicated engineering workstation (personal laptop)
  - Version-control intended state in Git before deployment
  - Run pre-change backups against current device configurations
  - Deploy intended state using Ansible automation
  - Validate post-change network behavior and configuration
  - Commit successful changes, backups, and validation artifacts to Git
  - Execute rollback from known-good configuration if validation fails
- The first implementation using this process is going to simply be configuring the "PROD" IP address layout
- Planned prod IP address layout, giving myself plenty of room for expansion in the future.
  - used /20s for ASNs
  - /21 area 0 
  - /23 area 1 and 2
- generated ASCII of logical network topology for both mgmt and professional VRFs and saved to docs, alongside ip address planning
 - pushed ospf stub config area 1 between R1 and R5 with cli based intended state R1.cfg,R5.cfg
 - will experiment with different data formats soon
   
# 05/09/26
- Basically a pure network engineering day
- Network Architecture
  - Wrote down ideas over the week, want to significantly expand on concepts
  - edited Eve topology, "Architected" intended state
  - Added 3 or 4 more devices and made sure my server could handle it. Need to upgrade soon
  - Decided to create a vrf for management so if I borked the routing along the way I'd still have a backplane
  - A VRF is a completely seperate routing instance running on all routers. Imagine instead of the diagram above, its all one big box on OSPF area 0, but just for management
  - I figured this would be the easiest way to allow reachability between everything. Quickest too.
  - wrote out IP addressing plan for management VRF OSPF backplane
    - I decided to use bigger blocks of /24s than I thought I might need. No need to be stingy with the address spaces
    - 10.8.0.0/22
      - 10.8.0.0/24 - reserved
      - 10.8.1.0/24 - broadcast OSPF segment between R1, R2, R3, and inet_rtr
      - 10.8.2.0/24 - loopbacks
      - 10.8.3.0/24 - p2p links
  - I wrote all of this out meticulously on pen and paper. All the loopback addresses, traced all the point to points
  - The ASA:
   - I ran into some issues with the ASA. The syntax is way different. I wasn't able to create a loopback on that one, so I hard-coded the management IP in hosts.ini to point to g0/3.10
   - I also wasn't able to configure vrfs on it, which I'll have to consider later
  - Once all that was configured, which took me a ton of time, I dropped some OSPF config on there.
    - I configured broadcast interfaces and point-to-point interface settings so hello and dead timers matched
    - I just advertised everything under the router ospf vrf MGMT 1 process.
      - I'll think about doing some filtering and summarization later
      - Not sure its really needed, I'm doing all the bells and whistles on the default vrf
  - I troubleshot OSPF for a while. Realized some interfaces were down after banging my head against the wall.
  - When I checked "show ip ospf neighbor" "show ip ospf database" "show ip route", and say everything was good, I did all my ping tests, and moved on to wrapping up for the day
  - I was having some trouble getting to my AUTO_box from my home network from the static NAT address I configured the other day
    - after some troubleshooting, I realized my NAT statements weren't configured under the MGMT vrf, and when I fixed that, I was able to reach it via VS Code
  - I stopped to go to dinner with my wife to celebrate my CCNP - Enterprise 🎉🎉🎉
  - When I got back, I added all my new host loopbacks to my hosts.ini
  - Added an ASA playbook for config backups. I know I can probably run that in the same backup_configs.yml playbook as the IOS, but I just wanted it done.
  - Troubleshot some SSH issues, then some git authentication issues, added all my changes, and committed.
 
# 05/04/26
- Research CI/CD pipeline structure
- Aiming for enterprise NetDevOps workflow
- Added new repo, pulled to linux machine
  - troubleshooting authentication issues
- Committed to master branch, cleaning up github landing page, added topology screenshot
- Quality of life improvements
  - Console font for AUTO_box too large
  - tried to adjust in eve, changed to telnet, vnc, adjusted settings, no luck
  - configured secondary IP address on inet_rtr
  - configured static NAT to AUTO_box on secondary IP address
  - mode AUTO_box accessible directly on my home network
- Set up VS Code on home computer
  - installed multiple extensions for IOS syntax highlighting, ansible, and QoL
  - ssh to AUTO_box, edited files, commits

# 05/03/26
  - Setting up ubuntu server
    - needed internet to download packages
    - added bridge to home internet, but the image only has one NVI
    - added and configured internet router for package download and git/version control
      - configured as gateway for management network
      - configured NAT inside on Gi3 interface, outside on WAN facing
      - wanted to keep IP addressing consistent with CCNP course, needed .22 address
      - configured DHCP on inet router, reserving address only for AUTO_box
      - virtual mac address not correctly mapping, validated on inet router correct
      - configured start of DHCP pool to intended IP address
      - Tested and confirmed internet functional, natting out from inet router
     - fully updated AUTO_box
     - installed Ansible, python, pip, git
    - Built Ansible file structure
      - built host inventory, grouping devices appropriately
    - Configured basic playbooks
      - configured playbook to add loopback interfaces
      - configured playbook to pull configuration files from hosts, save locally
    - Running playbooks (troubleshooting)
      - adjusted SSH settings on devices, unsupported algorithms
    - troubleshot then successfully ran playbooks

# 05/02/26
- Set up eve-ng lab on old desktop with minimal resources, planning on upgrading RAM and CPU soon
  - most of my day
  - Linux 101
- set up lab topology for CCNP - Automation course on INE.net
  - 2 routers, an ASA, and linux box
  - configured networking for course lab
    - layer 2 management switch with ports on VLAN 10
    - router and ASA interfaces connected to switch with /24 management network
    - P2P's between routers and ASA to simulate production
    - base network complete