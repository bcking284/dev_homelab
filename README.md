# Building a CI/CD Pipeline with EVE-NG Homelab:

This project documents my journey building a network automation and CI/CD-style workflow using EVE-NG, Linux, Ansible, Python, Git, and GitHub. The lab is focused on automating configuration management, backing up multi-vendor device configurations, and developing repeatable infrastructure workflows similar to those used in modern enterprise environments.

# Intended State:

<img width="1635" height="1132" alt="image" src="https://github.com/user-attachments/assets/7020bde3-13bd-4d77-8cff-bd1e5514c495" />

# Work Notes:

The environment currently includes Cisco routers, switches, and ASA firewalls managed through Ansible playbooks and version-controlled through GitHub. Future goals include automated configuration deployments, configuration drift detection, compliance validation, and integrating more advanced automation tooling and pipelines.

# 05/24/26
- moving from host_vars -> Jinja -> rendered_configs -> push entire file -- to host_vars -> Ansible loops -> exact CLI commands under exact parents
- worked perfectly for R2, just had to fix some IP addressing in my host vars
- R3 needed some troubleshooting
- -vvv showed me I had a bad mask on my interfaces, fixed in host_vars on R1-3
- fixed mask, working like a charm
- fixed some other annoying typos like vlan tags I shouldn't have had added
- 

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




























































