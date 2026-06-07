import json
import requests
import urllib3

urllib3.disable_warnings()

device = "10.8.2.1"
username = "admin"
password = "admin"

url = f"https://{device}/restconf/data/Cisco-IOS-XE-native:native"

headers = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-patch+json"
}

payload = {
    "ietf-yang-patch:yang-patch": {
        "patch-id": "bgp-neighbors",
        "edit": [
            {
                "edit-id": "neighbor-10.0.24.2",
                "operation": "merge",
                "target": "/router/Cisco-IOS-XE-bgp:bgp=65512",
                "value": {
                    "Cisco-IOS-XE-bgp:bgp": {
                        "id": 65512,
                        "neighbor": [
                            {
                            "id": "20.20.20.20",
                            "remote-as": 65512
                            },
                            {
                            "id": "5.5.5.5",
                            "remote-as": 65512
                            },
                            {
                            "id": "6.6.6.6",
                            "remote-as": 65512
                            },
                            {
                            "id": "7.7.7.7",
                            "remote-as": 65512
                            },
                            {
                            "id": "8.8.8.8",
                            "remote-as": 65512
                            }        
                        ]
                    }
                }
            },
            {
                "edit-id": "neighbor-10.0.28.1",
                "operation": "merge",
                "target": "/router/Cisco-IOS-XE-bgp:bgp=65512/address-family/no-vrf/ipv4=unicast",
                "value": {
                    "Cisco-IOS-XE-bgp:ipv4": {
                        "af-name": "unicast",
                        "ipv4-unicast": {
                        "neighbor": [
                            {
                                "id": "20.20.20.20"
                            },

                        ],
                        "network": {
                            "with-mask": [
                            {
                                "number": "2.2.2.2",
                                "mask": "255.255.255.255"
                            },
                            {
                                "number": "9.9.9.9",
                                "mask": "255.255.255.255"
                            },
                            {
                                "number": "10.10.10.10",
                                "mask": "255.255.255.255"
                            },
                            {
                                "number": "11.11.11.11",
                                "mask": "255.255.255.255"
                            },
                            {
                                "number": "12.12.12.12",
                                "mask": "255.255.255.255"
                            }          
                            ]
                        }
                        }
                    }
                }
            }
        ]
    }
}

response = requests.patch(
    url,
    auth=(username, password),
    headers=headers,
    data=json.dumps(payload),
    verify=False
)

print("Status code:", response.status_code)
print(response.text)