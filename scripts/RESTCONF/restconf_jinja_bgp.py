import json
import time
import requests
import urllib3
import yaml

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

project_root = Path("/root/ANSIBLE/dev_homelab")
host_vars_dir = project_root / "inventories/lab/host_vars"
template_dir = project_root / "templates"

devices = ["R1", "inet_rtr"]

env = Environment(
    loader=FileSystemLoader(template_dir),
    trim_blocks=True,
    lstrip_blocks=True
)

headers = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json"
}


def load_host_vars(device_name):
    vars_file = host_vars_dir / f"{device_name}.yml"

    with open(vars_file, "r") as file:
        return yaml.safe_load(file)


def send_restconf_request(method, uri, payload, username, password):
    method = method.lower()

    if method == "put":
        return requests.put(
            uri,
            auth=(username, password),
            headers=headers,
            data=json.dumps(payload),
            verify=False,
            timeout=10
        )

    if method == "patch":
        return requests.patch(
            uri,
            auth=(username, password),
            headers=headers,
            data=json.dumps(payload),
            verify=False,
            timeout=10
        )

    if method == "post":
        return requests.post(
            uri,
            auth=(username, password),
            headers=headers,
            data=json.dumps(payload),
            verify=False,
            timeout=10
        )

    raise ValueError(f"Unsupported HTTP method: {method}")


for device_name in devices:
    vars_data = load_host_vars(device_name)

    device_ip = vars_data["restconf"]["host"]
    username = vars_data["restconf"]["username"]
    password = vars_data["restconf"]["password"]
    bgp_asn = vars_data["bgp"]["asn"]

    requests_to_send = [
        {
            "name": "Configure base BGP",
            "method": "put",
            "template": "bgp_base.j2",
            "uri": f"https://{device_ip}/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-bgp:bgp={bgp_asn}"
        },
        {
            "name": "Configure IPv4 unicast address-family",
            "method": "put",
            "template": "bgp_addrfam_ipv4.j2",
            "uri": f"https://{device_ip}/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-bgp:bgp={bgp_asn}/address-family/no-vrf/ipv4=unicast"
        },
    ]

    print(f"\n==============================")
    print(f"Starting BGP config for {device_name} at {device_ip}")
    print(f"==============================")

    for item in requests_to_send:
        template = env.get_template(item["template"])
        rendered_payload = template.render(**vars_data)

        payload = json.loads(rendered_payload)

        print(f"\n{device_name}: {item['name']}")
        print(f"{item['method'].upper()} {item['uri']}")
        print(f"Template: {item['template']}")

        response = send_restconf_request(
            method=item["method"],
            uri=item["uri"],
            payload=payload,
            username=username,
            password=password
        )

        print(f"Status code: {response.status_code}")

        if response.status_code in [200, 201, 204]:
            print(f"{device_name}: success")
            time.sleep(2)
        else:
            print(f"{device_name}: failed")
            print(response.text)
            break