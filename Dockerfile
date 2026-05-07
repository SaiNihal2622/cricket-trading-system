# ─── Multi-service Dockerfile for Railway deployment ──────────────────────────
# Runs: nginx (frontend) + uvicorn (backend) in a single container
# For Railway: set PORT env var, Railway injects it automatically.

FROM python:3.12-slim

WORKDIR /app

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl nginx supervisor gnupg ca-certificates \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libxrandr2 libxdamage1 libxcomposite1 libxfixes3 libatk1.0-0 \
    libcups2 libpango-1.0-0 libcairo2 \
    fonts-liberation fonts-noto-color-emoji \
    && (apt-get install -y --no-install-recommends libasound2 2>/dev/null || \
        apt-get install -y --no-install-recommends libasound2t64 2>/dev/null || true) \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 LTS (via NodeSource) ───────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────────────────────
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Playwright Chromium (no --with-deps to avoid missing Trixie packages) ─────
RUN playwright install chromium

# ── Frontend build ─────────────────────────────────────────────────────────────
COPY frontend /app/frontend
WORKDIR /app/frontend
RUN npm install && npm run build

# ── Backend ────────────────────────────────────────────────────────────────────
COPY .env /app/.env
COPY backend /app/backend
COPY .env /app/backend/.env
WORKDIR /app/backend
RUN mkdir -p /app/backend/ml_model/artifacts
COPY backend/ml_model/artifacts/*.pkl /app/backend/ml_model/artifacts/

# ── Supervisor config (nginx port set dynamically at runtime via start.sh) ─────
RUN printf '[supervisord]\nnodaemon=true\nlogfile=/dev/null\nlogfile_maxbytes=0\n\n\
[program:backend]\ncommand=uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1\n\
directory=/app/backend\nautorestart=true\nstartretries=5\n\
stdout_logfile=/dev/stdout\nstdout_logfile_maxbytes=0\n\
stderr_logfile=/dev/stderr\nstderr_logfile_maxbytes=0\n\n\
[program:nginx]\ncommand=/usr/sbin/nginx -g "daemon off;"\nautorestart=true\n\
stdout_logfile=/dev/stdout\nstdout_logfile_maxbytes=0\n\
stderr_logfile=/dev/stderr\nstderr_logfile_maxbytes=0\n' \
> /etc/supervisor/conf.d/app.conf

# ── Startup script (sets nginx port from $PORT) ───────────────────────────────
COPY start.sh /start.sh
RUN sed -i 's/\r//' /start.sh && chmod +x /start.sh

EXPOSE 8080

CMD ["/start.sh"]
