"""Check workflow run logs."""
import os
import requests

TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
REPO = "SaiNihal2622/cricket-trading-system"
headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}

# Get jobs for the latest run
run_id = 25558678649
r = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/jobs", headers=headers)
jobs = r.json().get("jobs", [])
for job in jobs:
    print(f"Job: {job['name']} status={job['status']} conclusion={job.get('conclusion')}")
    for step in job.get("steps", []):
        print(f"  Step: {step['name']} status={step['status']} conclusion={step.get('conclusion')}")