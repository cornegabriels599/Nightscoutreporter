# Nightscout Cockpit v2

Multi-user Nightscout dashboard with **FastAPI** backend + **Streamlit** frontend.  
Built for AAPS / Nightscout CGM + loop data.

## Top 6 Visuals

| # | Visual | Tab | Data source |
|---|--------|-----|-------------|
| 1 | **Live glucose** + trend arrow + data age + gap shading | Live | CGM entries |
| 2 | **Live temp basal** step chart (12/24h) | Live | Treatments (Temp Basal) |
| 3 | **Hypo heatmap** — minutes < 70 mg/dL per hour per day | Insights | CGM 14d |
| 4 | **AGP** — median + P10/P90 band (5-min buckets) | Insights | CGM 14d |
| 5 | **Dagdeelkaart** — TIR/TBR/TAR per daypart, week vs weekend | Insights | CGM 14d |
| 6 | **Loop-activiteit** — % temp basal + mean rate per hour | Insights | Treatments 14d |

## Architecture

```
backend/           FastAPI + SQLAlchemy + Postgres
  app/
    cgm_processing.py    parse, gaps, metrics, resample
    basal_processing.py  parse, step-series, loop activity
    agp.py               AGP percentile bands
    insights.py          hypo heatmap, daypart analysis
    routers/
      cockpit.py         /me/cockpit + /me/insights
      data.py            /me/cgm/window (legacy)
      basal.py           /me/basal/window (legacy)
      me.py              /me/nightscout
      auth.py            register + login
frontend/          Streamlit UI
  app.py           Live + Insights tabs
```

## API Endpoints

| Method | Path | Description | Cache TTL |
|--------|------|-------------|-----------|
| POST | /auth/register | Create account (argon2) | — |
| POST | /auth/login | Login, returns JWT | — |
| POST | /me/nightscout | Save NS URL + token | — |
| GET | /me/nightscout/test | Test NS connection | — |
| GET | /me/cockpit?hours=3..48 | CGM + basal live data | 30s |
| GET | /me/insights?days=7..28 | AGP, heatmap, dayparts, loop | 300s |
| GET | /me/cgm/window?hours=3..168 | Legacy CGM endpoint | 30s |
| GET | /me/basal/window?hours=1..168 | Legacy basal endpoint | 30s |

## Local Development

### 1. Generate keys
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Create `.env`
Copy `.env.example` to `.env` and fill in:
- `APP_ENCRYPTION_KEY` (Fernet key from step 1)
- `JWT_SECRET_KEY` (random string from step 1)

### 3. Build & run
```powershell
cd "C:\Users\...\nightscout-cockpit"
docker compose up --build -d
```

### 4. Open
- Frontend: http://localhost:8501
- Backend docs: http://localhost:8000/docs

### 5. Rebuild after changes
```powershell
cd "C:\Users\...\nightscout-cockpit"
docker compose down
docker compose up --build -d
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Backend crashes with `psycopg2 OperationalError` | Postgres healthcheck + `wait_for_postgres.py` handle this. If it persists: `docker compose down -v` and retry. |
| `experimental_rerun` error | Fixed: `do_rerun()` compat helper handles old/new Streamlit. |
| Password too long error | Argon2 supports up to 128 chars (no bcrypt 72-byte limit). |
| No basal data shown | Ensure your Nightscout has `Temp Basal` treatments (AAPS). |
| Stale data warning | Data age > 10 min triggers stale indicator. Check NS connection. |
| CORS errors | Set `CORS_ORIGINS` in `.env` to match your frontend URL. |

## Security

- Nightscout tokens encrypted at rest (Fernet), never sent to client, never logged.
- CORS restricted to `CORS_ORIGINS`.
- Auth required for all `/me/*` endpoints.
- Rate limiting on auth + data endpoints (in-memory).
- HTTPS assumed in production.

## Deployment (GitHub Actions)

Required secrets: `GHCR_USERNAME`, `GHCR_TOKEN`, `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_COMPOSE_PATH`.

```bash
docker compose -f /path/to/docker-compose.yml pull
docker compose -f /path/to/docker-compose.yml up -d
```
