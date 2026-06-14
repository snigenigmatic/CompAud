# Deployment Guide — CompAud (PS3)

Steps to deploy the backend (Modal) and frontend (Vercel). The backend is already Modal-ready (`backend/modal_app.py`); the frontend builds as-is with no extra configuration.

## 1. Backend → Modal

```bash
pip install modal           # or: uv tool install modal
modal setup                 # authenticate YOUR Modal account (one time)

cd backend
modal serve modal_app.py    # ephemeral URL — build + smoke test first
# then, for a persistent URL:
modal deploy modal_app.py
```

- First build is slow (installs torch + sentence-transformers and **bakes the embedding
  model** into the image). Subsequent deploys reuse cached layers.
- Secrets come from the repo `.env` via `Secret.from_dotenv` — make sure `.env` has a valid
  `OPENAI_API_KEY` (it does). `NEO4J_URI` is blank → Neo4j skipped. `PHOENIX_ENABLED` is
  forced off in-container.
- `modal deploy` prints your URL, e.g.
  `https://<your-workspace>--compaud-ps3-backend-fastapi-app.modal.run`. Save it.

**Verify the deployed URL** (replace `<URL>`):
```bash
curl <URL>/health                       # 200, openai_enabled:true
curl <URL>/ps3/requirements             # count: 9
curl -X POST <URL>/ps3/analyze          # summary 5 compliant / 3 partial / 1 gap
curl <URL>/ps3/report.pdf -o r.pdf      # starts with %PDF
```

## 2. Frontend → Vercel

```bash
npm i -g vercel
vercel login                # YOUR Vercel account
cd frontend
vercel                      # first deploy (preview);  vercel --prod  for production
```

Vercel project settings:
- **Root Directory:** `frontend`
- **Framework preset:** Next.js (auto-detected); install uses `pnpm` (lockfile present).
- **Environment Variable:** `NEXT_PUBLIC_API_BASE_URL = <your Modal URL>` (no trailing slash).
  This is what `frontend/lib/api.ts` reads (`apiBaseUrl`) — defaults to `http://localhost:8000`
  for local dev. The generated SDK in `frontend/api-client/` is committed, so the build needs
  no backend access.

## 3. Close the CORS loop

After the Vercel URL exists, let the backend accept it:
1. Add to repo `.env`: `FRONTEND_ORIGIN=https://<your-app>.vercel.app`
2. Redeploy the backend: `cd backend && modal deploy modal_app.py`
   (`modal_app.py` builds `CORS_ORIGINS` from `FRONTEND_ORIGIN` + `http://localhost:3000`).

## Notes
- **Cold start** is ~8–10 s (torch + model load). For a live demo, set `min_containers=1` in
  `backend/modal_app.py` `@app.function(...)` to keep one container warm (costs idle time).
- **Regenerating the SDK** against the deployed backend (optional): set
  `frontend/openapi-ts.config.js` `input` to `<your Modal URL>/openapi.json`, run
  `pnpm openapi-ts`, commit `frontend/api-client/`. Not required — the committed SDK already
  matches the current API.
- **Local dev is unchanged:** backend `uv run rakshak-api` on `:8000`, frontend `pnpm dev` on
  `:3000` (homepage `/` is the dashboard).
