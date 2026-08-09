import requests
import urllib3
import json

#suppress warnings for self-signed HTTPS certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

devices = {
    "R1": "10.8.2.1",
    "R2": "10.8.2.2",
    "R3": "10.8.2.3",
    "R4": "10.8.2.4",
    "R5": "10.8.2.5",
    "inet_rtr": "10.8.2.254"
}

username = "admin"
password = "admin"

headers = {
    "Accept": "application/yang-data+json"
}

for device_name, ip_address in devices.items():
    url = f"https://{ip_address}/restconf/data/ietf-interfaces:interfaces"

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

        if response.ok:
            data = response.json()

            output_file = f"restconf_outputs/interfaces/{device_name}_interfaces.json"

            with open(output_file, "w") as file:
                json.dump(data, file, indent=2)

            print(f"Saved output to {output_file}")

        else:
            print("Request failed.")
            print(response.text)

    except requests.exceptions.RequestException as error:
        print(f"Connection error for {device_name}: {error}")