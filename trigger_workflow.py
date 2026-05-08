"""Trigger the live-trading workflow via GitHub API."""
import os
import requests
import yaml
import sys

TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
REPO = "SaiNihal2622/cricket-trading-system"
WORKFLOW = "live-trading.yml"

# Validate YAML first
with open(".github/workflows/live-trading.yml", encoding="utf-8") as f:
    data = yaml.safe_load(f)
    print(f"Workflow name: {data['name']}")
    # 'on' is parsed as True (boolean) by PyYAML, so use True key
    triggers = data.get(True) or data.get('on')
    print(f"Triggers: {list(triggers.keys()) if triggers else 'N/A'}")
    print("YAML is valid")

# List workflows
headers = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}

r = requests.get(f"https://api.github.com/repos/{REPO}/actions/workflows", headers=headers)
print(f"\nAll workflows ({r.status_code}):")
for wf in r.json().get("workflows", []):
    print(f"  ID={wf['id']} name={wf['name']} path={wf['path']} state={wf['state']}")

# Try dispatch
print(f"\nTriggering {WORKFLOW}...")
r = requests.post(
    f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
    headers=headers,
    json={"ref": "master", "inputs": {"mode": "demo", "duration_hours": "1", "scan_interval": "120"}},
)
print(f"Dispatch result: {r.status_code}")
if r.status_code != 204:
    print(f"Error: {r.text[:300]}")
    
    # Try by ID
    for wf in r.json().get("workflows", []) if hasattr(r.json(), 'get') else []:
        pass
    
    # Try with workflow ID directly
    print("\nTrying by workflow ID...")
    r2 = requests.get(f"https://api.github.com/repos/{REPO}/actions/workflows", headers=headers)
    for wf in r2.json().get("workflows", []):
        if "live-trading" in wf["path"]:
            wf_id = wf["id"]
            print(f"Found workflow ID: {wf_id}")
            r3 = requests.post(
                f"https://api.github.com/repos/{REPO}/actions/workflows/{wf_id}/dispatches",
                headers=headers,
                json={"ref": "master", "inputs": {"mode": "demo", "duration_hours": "1", "scan_interval": "120"}},
            )
            print(f"Dispatch by ID result: {r3.status_code}")
            if r3.status_code != 204:
                print(f"Error: {r3.text[:300]}")
            else:
                print("SUCCESS! Workflow triggered.")
            break