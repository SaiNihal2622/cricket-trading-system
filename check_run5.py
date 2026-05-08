import urllib.request, json, os, subprocess, time

env = os.environ.copy()
env.pop('GH_TOKEN', None)
result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10)
token = result.stdout.strip()

repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# Wait for run to appear
for attempt in range(3):
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs?per_page=3', headers=headers)
    resp = json.loads(urllib.request.urlopen(req).read())
    runs = resp.get('workflow_runs', [])
    if runs:
        latest = runs[0]
        print(f"Latest Run #{latest['run_number']}: {latest['status']} - {latest.get('conclusion', 'pending')}")
        print(f"  URL: {latest['html_url']}")
        print(f"  SHA: {latest['head_sha'][:12]}")
        
        # Get job details
        req2 = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs/{latest['id']}/jobs", headers=headers)
        jobs = json.loads(urllib.request.urlopen(req2).read())
        for job in jobs.get('jobs', []):
            print(f"\n  Job: {job['name']} - {job['status']} - {job.get('conclusion', 'pending')}")
            for step in job.get('steps', []):
                icon = '✓' if step.get('conclusion') == 'success' else '✗' if step.get('conclusion') == 'failure' else '...'
                print(f"    {icon} {step['name']} - {step.get('conclusion', 'pending')}")
        
        if latest['status'] == 'completed':
            break
    if attempt < 2:
        print(f"Waiting 30s... (attempt {attempt+1})")
        time.sleep(30)

# Also check Pages settings
print("\n--- Pages Settings ---")
try:
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/pages', headers=headers)
    resp = json.loads(urllib.request.urlopen(req).read())
    print(f"  URL: {resp.get('html_url')}")
    print(f"  Source: {resp.get('source')}")
    print(f"  Build type: {resp.get('build_type')}")
except urllib.error.HTTPError as e:
    print(f"  Error {e.code}: {e.read().decode()}")