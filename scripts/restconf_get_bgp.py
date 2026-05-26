import json
import requests
import urllib3
from pathlib import Path

# ignore self-signed certificate warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Output directory
OUTPUT_DIR = Path("/root/ANSIBLE/dev_homelab/scripts/restconf_outputs/bgp")

# Device list
devices = {
    "R1": "10.8.2.1"
}

username = "admin"
password = "admin"

headers = {
    "Accept": "application/yang-data+json"
}

for device_name, ip_address in devices.items():
    url = f"https://{ip_address}/restconf/data/Cisco-IOS-XE-native:native/router/"

    print(f"\nConnecting to {device_name} at {ip_address}")
    print(f"GET {url}")

    try:
        response = requests.get(
            url,
            auth=(username, password),
            headers=headers,
            verify=False,
            timeout=10
        )

        print(f"Status code: {response.status_code}")

        output_file = OUTPUT_DIR / f"{device_name}_bgp_get.json"

        if response.ok:
            data = response.json()

            with open(output_file, "w") as file:
                json.dump(data, file, indent=2)

            print(f"Saved BGP RESTCONF output to {output_file}")

        else:
            error_file = OUTPUT_DIR / f"{device_name}_bgp_error.txt"

            with open(error_file, "w") as file:
                file.write(f"Status code: {response.status_code}\n")
                file.write(response.text)

            print(f"Request failed. Error saved to {error_file}")
            print(response.text)

    except requests.exceptions.RequestException as error:
        error_file = OUTPUT_DIR / f"{device_name}_connection_error.txt"

        with open(error_file, "w") as file:
            file.write(str(error))

        print(f"Connection error for {device_name}. Saved to {error_file}")
        print(error)