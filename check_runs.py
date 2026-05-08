"""Check workflow run status."""
import os
import requests

TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
REPO = "SaiNihal2622/cricket-trading-system"
headers = {"Authorization": f"token {TOKEN}"}

r = requests.get(f"https://api.github.com/repos/{REPO}/actions/workflows/273285405/runs?per_page=3", headers=headers)
runs = r.json().get("workflow_runs", [])
for run in runs:
    print(f"ID={run['id']} status={run['status']} conclusion={run.get('conclusion', 'N/A')} created={run['created_at']}")