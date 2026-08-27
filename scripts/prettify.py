#!/usr/bin/env python3
"""Read JSON on stdin, write readable YAML to the given path."""
import json
import sys
import yaml

KEY_ORDER = ["name", "process_id", "router_id", "vrf", "area_id", "afi"]


class Dumper(yaml.SafeDumper):
    """Indent list items under their parent key."""
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def reorder(obj):
    """Recursively put identifier keys first, rest alphabetical."""
    if isinstance(obj, dict):
        first = [k for k in KEY_ORDER if k in obj]
        rest = sorted(k for k in obj if k not in first)
        return {k: reorder(obj[k]) for k in first + rest}
    if isinstance(obj, list):
        return [reorder(i) for i in obj]
    return obj


data = reorder(json.load(sys.stdin))
with open(sys.argv[1], "w") as f:
    yaml.dump(data, f, Dumper=Dumper, sort_keys=False,
              default_flow_style=False, indent=2, width=120)