import urllib.request, json, os, subprocess

# Get stored token
env = os.environ.copy()
if 'GH_TOKEN' in env:
    del env['GH_TOKEN']
result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10)
token = result.stdout.strip()

repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# Check latest run (should be the new one after push)
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/actions/runs?per_page=5',
    headers=headers
)
resp = json.loads(urllib.request.urlopen(req).read())
for run in resp.get('workflow_runs', []):
    print(f"Run #{run['run_number']}: {run['status']} - {run.get('conclusion', 'pending')} - {run['created_at']}")
    print(f"  URL: {run['html_url']}")
    print(f"  Head SHA: {run['head_sha'][:12]}")
    
    # Get jobs for this run
    req2 = urllib.request.Request(run['jobs_url'], headers=headers)
    jobs = json.loads(urllib.request.urlopen(req2).read())
    for job in jobs.get('jobs', []):
        print(f"  Job: {job['name']} - {job['status']} - {job.get('conclusion', 'pending')}")
        for step in job.get('steps', []):
            if step.get('conclusion') == 'failure':
                print(f"    FAILED STEP: {step['name']} ({step.get('conclusion', '')})")
    print()