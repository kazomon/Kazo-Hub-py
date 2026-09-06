# Kazo-Hub Python

Kazo-Hub is a FastAPI backend with a dependency-light HTML frontend. This Manus WebDev project runs the Python app from the root `Dockerfile` and serves both the API and frontend from one process.

## Local development

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app:app --reload --port 3000
```

Open `http://localhost:3000/`.

## API

- `GET /api/health` — health check
- `GET /api/search?query=...&page=1` — public search metadata
- `GET /api/thumbnail?url=...` — allowlisted thumbnail proxy

The search route checks `robots.txt` first. The thumbnail proxy only accepts HTTPS URLs from `phncdn.com` and its subdomains and limits responses to 5 MiB.
