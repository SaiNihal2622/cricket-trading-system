import urllib.request, json, os, subprocess

env = os.environ.copy()
env.pop('GH_TOKEN', None)
t = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10).stdout.strip()
headers = {'Authorization': f'token {t}', 'Accept': 'application/vnd.github.v3+json'}
repo = 'SaiNihal2622/cricket-trading-system'

# Get latest runs
req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs?per_page=3', headers=headers)
resp = json.loads(urllib.request.urlopen(req).read())
runs = resp.get('workflow_runs', [])

for r in runs:
    print(f"Run #{r['run_number']}: {r['status']} - {r.get('conclusion', 'pending')}")
    print(f"  URL: {r['html_url']}")
    
    # Get jobs for this run
    req2 = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs/{r['id']}/jobs", headers=headers)
    jobs = json.loads(urllib.request.urlopen(req2).read())
    for j in jobs.get('jobs', []):
        print(f"  Job: {j['name']} - {j.get('conclusion', 'pending')}")
        for s in j.get('steps', []):
            icon = '✓' if s.get('conclusion') == 'success' else '✗' if s.get('conclusion') == 'failure' else '...'
            print(f"    {icon} {s['name']} - {s.get('conclusion', 'pending')}")
    print()