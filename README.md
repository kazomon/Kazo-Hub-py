# Kazo-Hub Python API

This directory contains a local-only Python replacement for the current TypeScript backend. It does not modify the React frontend or the GitHub repository.

## Run locally

```bash
cd backend-python
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app:app --reload --port 3000
```

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/search?query=...&page=1` | Search public result metadata |
| `GET` | `/api/thumbnail?url=...` | Proxy allowlisted thumbnail URLs |

The search route checks `robots.txt` before fetching results. The thumbnail proxy only allows HTTPS URLs hosted on `phncdn.com` or its subdomains and limits responses to 5 MiB.

## Test

```bash
python -m unittest test_app.py
```
