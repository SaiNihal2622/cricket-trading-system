#!/bin/sh
# start.sh - write nginx config with dynamic $PORT then launch supervisord
PORT="${PORT:-8080}"
echo "Starting services on port ${PORT}..."

python3 - <<PYEOF
import os, textwrap
port = os.environ.get("PORT", "8080")
cfg = textwrap.dedent(f"""
server {{
    listen {port};
    root /app/frontend/build;
    index index.html;

    location /api/ {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 300;
    }}
    location /ws {{
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
    }}
    location /health {{
        proxy_pass http://127.0.0.1:8000;
    }}
    location /status {{
        proxy_pass http://127.0.0.1:8000;
    }}
    location / {{
        try_files \$uri /index.html;
    }}
}}
""").strip()
with open("/etc/nginx/sites-available/default", "w") as f:
    f.write(cfg)
print(f"nginx config written for port {port}")
PYEOF

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
