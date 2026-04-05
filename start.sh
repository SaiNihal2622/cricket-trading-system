#!/bin/bash
# Startup script: use Railway $PORT for nginx, fallback to 80
set -e

PORT="${PORT:-80}"

# Write nginx config with dynamic port
cat > /etc/nginx/sites-available/default << NGINX
server {
    listen ${PORT};
    root /app/frontend/build;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 300;
    }
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
    }
    location /health {
        proxy_pass http://127.0.0.1:8000;
    }
    location / {
        try_files \$uri /index.html;
    }
}
NGINX

echo "Starting services on port ${PORT}..."

# Start supervisor (manages nginx + uvicorn)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
