"""Get workflow run logs."""
import os
import requests
import zipfile
import io

TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
REPO = "SaiNihal2622/cricket-trading-system"
headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}

run_id = 25558678649
r = requests.get(f"https://api.github.com/repos/{REPO}/actions/runs/{run_id}/logs", headers=headers, allow_redirects=True)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    z = zipfile.ZipFile(io.BytesIO(r.content))
    for name in z.namelist():
        print(f"\n=== {name} ===")
        content = z.read(name).decode("utf-8", errors="replace")
        # Show last 50 lines
        lines = content.split("\n")
        for line in lines[-50:]:
            print(line)
else:
    print(r.text[:500])