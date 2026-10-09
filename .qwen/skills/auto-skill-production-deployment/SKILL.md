---
name: auto-skill-production-deployment
description: Deploy the Bibliography Hallucinations Checker Flask app with gunicorn and Docker
source: auto-skill
extracted_at: '2026-07-10T10:18:06.819Z'
---

# Production Deployment for Bibliography Hallucinations Checker

When deploying the Flask-based Bibliography Hallucinations Checker to production, follow this checklist and use the provided gunicorn and Docker patterns.

## Prerequisites

1. **SECRET_KEY** — Set to a strong, randomly generated value in `.env`. Generate with:
   ```bash
   python -c "import secrets; print(secrets.token_hex(16))"
   ```
2. **FLASK_DEBUG** — Must be **unset** or set to `0`. Debug mode must never be enabled in production.
3. **`.env` file permissions** — On the server, use `chmod 600 .env` so only the running user can read it.

## Gunicorn Deployment

The app exposes a WSGI entry point at `wsgi.py` (the Flask `app` object).

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn (4 workers, bound to localhost)
gunicorn --workers 4 --bind 127.0.0.1:8000 wsgi:app
```

**Worker count guidance:**
- Start with `workers = (2 * CPU_cores) + 1` for CPU-bound workloads.
- For this I/O-bound app (API calls), 4–8 workers is typically sufficient.
- Monitor memory usage; each gunicorn worker consumes ~50–100 MB.

## Reverse Proxy (Required)

Always place gunicorn behind a reverse proxy for TLS termination and static file handling:

**nginx example:**
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_DEBUG=0
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "wsgi:app"]
```

**Build and run:**
```bash
docker build -t bibcheck .
docker run -p 8000:8000 --env-file .env bibcheck
```

## Environment Variables Summary

| Variable | Required | Production Value |
|----------|----------|-----------------|
| `SECRET_KEY` | Yes | Strong random hex string |
| `FLASK_DEBUG` | No | `0` or unset |
| `OPENALEX_EMAIL` | No | Your email for polite pool |
| `OPENALEX_API_KEY` | No | API key for higher rate limits |

## Common Issues

- **Port conflict:** If port 5000 is in use on macOS, disable AirPlay Receiver (System Settings → General → AirDrop & Handoff).
- **Missing `.env` on server:** gunicorn will fail to start if `SECRET_KEY` is not set. Verify with `docker exec <container> printenv SECRET_KEY`.
- **API rate limits in production:** Set `OPENALEX_API_KEY` and `OPENALEX_EMAIL` to access the OpenAlex polite pool and avoid rate-limiting during batch processing.
