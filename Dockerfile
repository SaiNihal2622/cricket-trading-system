# ─── Multi-service Dockerfile for Railway deployment ──────────────────────────
# Runs: nginx (frontend) + uvicorn (backend) in a single container
# For Railway: set PORT env var, Railway injects it automatically.

FROM python:3.12-slim

WORKDIR /app

# ── System deps (includes Playwright + nginx) ──────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl nginx supervisor gnupg ca-certificates \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libxrandr2 libxdamage1 \
    libxcomposite1 libxfixes3 libatk1.0-0 \
    && apt-get install -y --no-install-recommends libasound2 || \
       apt-get install -y --no-install-recommends libasound2t64 || true \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 LTS (via NodeSource) ───────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ────────────────────────────────────────────────────────────
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

# ── Frontend build ─────────────────────────────────────────────────────────
COPY frontend /app/frontend
WORKDIR /app/frontend
RUN npm ci && npm run build

# ── Backend ────────────────────────────────────────────────────────────────
COPY backend /app/backend
WORKDIR /app/backend
RUN mkdir -p /app/ml_model/artifacts

# ── Nginx config ──────────────────────────────────────────────────────────
RUN echo 'server { \
    listen 80; \
    root /app/frontend/build; \
    index index.html; \
    location /api { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; } \
    location /ws  { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; } \
    location /health { proxy_pass http://127.0.0.1:8000; } \
    location / { try_files $uri /index.html; } \
}' > /etc/nginx/sites-available/default

# ── Supervisor (process manager) ─────────────────────────────────────────
RUN echo '[supervisord]\nnodaemon=true\n\
[program:backend]\ncommand=uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1\ndirectory=/app/backend\nautorestart=true\nstdout_logfile=/dev/stdout\nstdout_logfile_maxbytes=0\nstderr_logfile=/dev/stderr\nstderr_logfile_maxbytes=0\n\
[program:nginx]\ncommand=nginx -g "daemon off;"\nautorestart=true\nstdout_logfile=/dev/stdout\nstdout_logfile_maxbytes=0\nstderr_logfile=/dev/stderr\nstderr_logfile_maxbytes=0' \
> /etc/supervisor/conf.d/app.conf

EXPOSE 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/app.conf"]
