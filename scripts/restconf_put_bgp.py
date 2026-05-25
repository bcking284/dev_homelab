import json
import requests
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

device_name = "R1"
device_ip = "10.8.2.1"

username = "admin"
password = "admin"

payload_file = Path("/root/ANSIBLE/dev_homelab/scripts/restconf_outputs/bgp/r1_rtr_bgp_put.json")

url = f"https://{device_ip}/restconf/data/Cisco-IOS-XE-native:native/router"

headers = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json"
}

with open(payload_file, "r") as file:
    payload = json.load(file)

print(f"Connecting to {device_name} at {device_ip}")
print(f"PATCH {url}")
print(f"Payload file: {payload_file}")

response = requests.patch(
    url,
    auth=(username, password),
    headers=headers,
    data=json.dumps(payload),
    verify=False,
    timeout=10
)

print(f"Status code: {response.status_code}")

if response.status_code in [200, 201, 204]:
    print("BGP config pushed successfully.")
else:
    print("Request failed.")
    print(response.text)