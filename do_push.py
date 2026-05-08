import subprocess, os, sys

# First, try to get the gh stored token (which now has workflow scope)
env = os.environ.copy()
if 'GH_TOKEN' in env:
    del env['GH_TOKEN']

try:
    result = subprocess.run(
        ['gh', 'auth', 'token'],
        capture_output=True, text=True, env=env, timeout=10
    )
    stored_token = result.stdout.strip()
    if stored_token and len(stored_token) > 10:
        print(f"Found stored gh token (length: {len(stored_token)})")
        # Set it as GH_TOKEN for git operations
        env['GH_TOKEN'] = stored_token
    else:
        print("No stored token found, using existing GH_TOKEN")
        env = os.environ.copy()
except Exception as e:
    print(f"Could not get stored token: {e}")
    env = os.environ.copy()

# Try git push
print("\nPushing to GitHub...")
result = subprocess.run(
    ['git', 'push', 'origin', 'master'],
    capture_output=True, text=True, env=env, cwd=r'C:\Users\saini\Desktop\iplclaude\cricket-trading-system',
    timeout=60
)
print(f"STDOUT: {result.stdout}")
print(f"STDERR: {result.stderr}")
print(f"Return code: {result.returncode}")

if result.returncode == 0:
    print("\nPush successful!")
    
    # Enable GitHub Pages
    print("\nEnabling GitHub Pages...")
    import urllib.request, json
    token = env.get('GH_TOKEN', '')
    repo = 'SaiNihal2622/cricket-trading-system'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    }
    
    # Try to enable Pages
    try:
        pages_body = json.dumps({
            'build_type': 'workflow',
            'source': {'branch': 'master', 'path': '/'}
        }).encode()
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/pages',
            data=pages_body, method='POST', headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        print(f"  Pages enabled: {resp.get('html_url', 'OK')}")
    except Exception as e:
        print(f"  Pages POST: {e}")
        # Try PATCH (already exists)
        try:
            req = urllib.request.Request(
                f'https://api.github.com/repos/{repo}/pages',
                data=pages_body, method='PATCH', headers=headers
            )
            resp = json.loads(urllib.request.urlopen(req).read())
            print(f"  Pages updated: {resp.get('html_url', 'OK')}")
        except Exception as e2:
            print(f"  Pages PATCH: {e2}")
    
    # Check Actions runs
    print("\nChecking Actions runs...")
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/actions/runs?per_page=3',
            headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        for run in resp.get('workflow_runs', []):
            print(f"  Run #{run['run_number']}: {run['status']} - {run.get('conclusion', 'pending')} - {run['html_url']}")
    except Exception as e:
        print(f"  Actions check: {e}")
else:
    print("\nPush failed!")