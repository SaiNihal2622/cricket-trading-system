import subprocess, os, json, urllib.request

# Get stored token
env = os.environ.copy()
env.pop('GH_TOKEN', None)
result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10)
token = result.stdout.strip()
env['GH_TOKEN'] = token

cwd = r'C:\Users\saini\Desktop\iplclaude\cricket-trading-system'

# Commit the fix
print("Committing workflow fix...")
r = subprocess.run(['git', 'add', '.github/workflows/deploy.yml'], capture_output=True, text=True, cwd=cwd, env=env)
print(f"  git add: {r.returncode}")
r = subprocess.run(['git', 'commit', '-m', 'fix: use npm install instead of npm ci for frontend build'], capture_output=True, text=True, cwd=cwd, env=env)
print(f"  git commit: {r.stdout.strip()} {r.stderr.strip()}")

# Push
print("\nPushing...")
r = subprocess.run(['git', 'push', 'origin', 'master'], capture_output=True, text=True, cwd=cwd, env=env, timeout=60)
print(f"  Push: {r.returncode} - {r.stderr.strip()}")

if r.returncode == 0:
    # Fix Pages source to master
    print("\nFixing Pages source branch...")
    repo = 'SaiNihal2622/cricket-trading-system'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    }
    try:
        body = json.dumps({
            'build_type': 'workflow',
            'source': {'branch': 'master', 'path': '/'}
        }).encode()
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/pages',
            data=body, method='PATCH', headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        print(f"  Pages source updated: {resp.get('source', 'N/A')}")
    except Exception as e:
        print(f"  Pages update: {e}")

    # Check latest runs
    print("\nChecking latest runs...")
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/actions/runs?per_page=3',
            headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        for run in resp.get('workflow_runs', []):
            print(f"  Run #{run['run_number']}: {run['status']} - {run.get('conclusion', 'pending')} - {run['html_url']}")
    except Exception as e:
        print(f"  Error: {e}")