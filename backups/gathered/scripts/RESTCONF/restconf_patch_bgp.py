import json
import requests
import urllib3
from pathlib import Path
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

device_name = "R1"
device_ip = "10.8.1.100"

username = "admin"
password = "admin"

requests_to_send = [
    {
        "payload_file": Path("/root/ANSIBLE/dev_homelab/scripts/restconf_outputs/bgp/configure_base_bgp.json"),
        "uri": f"https://{device_ip}/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-bgp:bgp=123"
    },
    {
        "payload_file": Path("/root/ANSIBLE/dev_homelab/scripts/restconf_outputs/bgp/configure_addrfam_ipv4.json"),
        "uri": f"https://{device_ip}/restconf/data/Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-bgp:bgp=123/address-family/no-vrf/ipv4=unicast"
    }
]

headers = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json"
}

for item in requests_to_send:
    payload_file = item["payload_file"]
    uri = item["uri"]

    with open(payload_file, "r") as file:
        payload = json.load(file)

    print(f"\nConnecting to {device_name} at {device_ip}")
    print(f"PUT {uri}")
    print(f"Payload file: {payload_file}")

    response = requests.put(
        uri,
        auth=(username, password),
        headers=headers,
        data=json.dumps(payload),
        verify=False,
        timeout=10
    )

    print(f"Status code: {response.status_code}")

    time.sleep(1)

    if response.status_code in [200, 201, 204]:
        print("BGP config pushed successfully.")
    else:
        print("Request failed.")
        print(response.text)
        break
