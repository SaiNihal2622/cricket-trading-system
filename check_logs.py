import urllib.request, json, os, subprocess

env = os.environ.copy()
env.pop('GH_TOKEN', None)
t = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10).stdout.strip()
headers = {'Authorization': f'token {t}', 'Accept': 'application/vnd.github.v3+json'}
repo = 'SaiNihal2622/cricket-trading-system'

# Get Run #7 jobs
run_id = 25526918777
req = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs', headers=headers)
jobs = json.loads(urllib.request.urlopen(req).read())

for j in jobs.get('jobs', []):
    if j['name'] == 'deploy-pages':
        for s in j.get('steps', []):
            if s['name'] == 'Build frontend':
                print(f"Step: {s['name']} - {s.get('conclusion', 'pending')}")
                # Get the logs
                step_num = s.get('number', 0)
                print(f"Step number: {step_num}")
                break

# Try to get logs
try:
    req2 = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/jobs/{j["id"]}/logs', headers=headers)
    resp = urllib.request.urlopen(req2)
    logs = resp.read().decode('utf-8', errors='replace')
    # Print last 2000 chars of logs
    print("=== LAST 2000 CHARS OF LOGS ===")
    print(logs[-2000:])
except Exception as e:
    print(f"Could not fetch logs: {e}")
    # Try alternative - get check runs
    try:
        req3 = urllib.request.Request(f'https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs', headers=headers)
        resp3 = urllib.request.urlopen(req3)
        with open('run_logs.zip', 'wb') as f:
            f.write(resp3.read())
        print("Downloaded logs to run_logs.zip")
    except Exception as e2:
        print(f"Alternative also failed: {e2}")