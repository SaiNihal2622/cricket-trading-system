import urllib.request, json, os, subprocess

env = os.environ.copy()
env.pop('GH_TOKEN', None)
result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10)
token = result.stdout.strip()

headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

repo = 'SaiNihal2622/cricket-trading-system'
req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs?per_page=2', headers=headers)
resp = json.loads(urllib.request.urlopen(req, timeout=15).read())

for run in resp.get('workflow_runs', []):
    print(f"Run #{run['run_number']}: {run['status']} - {run.get('conclusion', 'pending')}")
    print(f"  URL: {run['html_url']}")

    # Get job details for latest run
    req2 = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs", headers=headers)
    jobs = json.loads(urllib.request.urlopen(req2, timeout=15).read())
    for job in jobs.get('jobs', []):
        print(f"  Job: {job['name']} - {job.get('conclusion', 'pending')}")
        for step in job.get('steps', []):
            icon = '✓' if step.get('conclusion') == 'success' else '✗' if step.get('conclusion') == 'failure' else '...'
            print(f"    {icon} {step['name']} - {step.get('conclusion', 'pending')}")
    print()