import urllib.request, json
r = urllib.request.urlopen("http://localhost:8080/api/matches")
data = json.loads(r.read().decode())
print(json.dumps(data, indent=2))