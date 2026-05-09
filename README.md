# Building a CI/CD Pipeline with EVE-NG Homelab:

This project documents my journey building a network automation and CI/CD-style workflow using EVE-NG, Linux, Ansible, Python, Git, and GitHub. The lab is focused on automating configuration management, backing up multi-vendor device configurations, and developing repeatable infrastructure workflows similar to those used in modern enterprise environments.

# Topology 05/09/26:

<img width="1919" height="1283" alt="image" src="https://github.com/user-attachments/assets/4feeed3e-8c01-41c2-b226-45ab1dab7a12" />

# Work Notes:

The environment currently includes Cisco routers, switches, and ASA firewalls managed through Ansible playbooks and version-controlled through GitHub. Future goals include automated configuration deployments, configuration drift detection, compliance validation, and integrating more advanced automation tooling and pipelines.

05/02/26
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

  05/03/26
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

05/04/26
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

05/09/26
- Network Architecture
  - Wrote down ideas over the week, want to significantly expand on concepts
  - edited Eve topology




























































