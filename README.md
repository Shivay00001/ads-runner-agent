# AI Ads Runner Agent

Generates a full Google Ads campaign architecture — ad groups, keywords, and
≤30/90-char ad copy — via a **real LLM call** (LiteLLM, multi-provider), and
exports an import-ready **Google Ads Editor CSV**.

- **Backend:** FastAPI (Python), SQLite (Postgres-ready via `DATABASE_URL`)
- **Frontend:** Next.js (React, Tailwind CSS)

## ⚠️ A real LLM API key is required

Ad generation is performed by a **real** LLM call — there is no mock, stub, or
fallback. A task enqueued without a valid provider key fails with the provider's
authentic error.

Supply a key **one** of these ways:

- **Via the UI:** settings panel — keys are sent as request headers
  (`X-OpenAI-Key`, `X-Anthropic-Key`, `X-Gemini-Key`, `X-GLM-Key`) and can be
  persisted server-side through `POST /api/settings/keys`.
- **Via environment variables:** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `GEMINI_API_KEY`, `ZHIPUAI_API_KEY`.
- **Local Ollama:** choose an `ollama/...` model — no key needed.

Key lookup order for a job: request headers → stored settings → env vars.

## Quickstart (local)

### 1. Backend

```bash
cd backend
cp .env.example .env        # then edit: set API_KEY to a long random secret,
                            # add your provider key, check ALLOWED_ORIGINS
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --port 8007
```

`GET /health` → `{"status":"ok","service":"ads-runner-agent"}` (no auth).

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local   # check NEXT_PUBLIC_API_BASE_URL
npm install
npm run dev
```

Open `http://localhost:3000`, enter the backend **API Key** (matches `API_KEY`
in `backend/.env`) plus your provider key(s), and generate.

### 3. Smoke test

```bash
bash backend/smoke.sh
```

Boots the server with throwaway config, asserts `/health` → 200,
`/api/execute` → 401 without key / 422 on bad input / 200 with key,
`/api/tasks/{id}` → 200, unknown task → 404. No real LLM keys are used.

## Environment variables

### Backend (`backend/.env.example`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `PORT` | no | `8007` | Port the backend listens on |
| `API_KEY` | **yes** | — | Shared secret; every `/api/*` request must send it as the `X-API-Key` header. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ALLOWED_ORIGINS` | no | `http://localhost:3000` | Comma-separated browser origins allowed to call the API with credentials (never `*`) |
| `DATABASE_URL` | no | `sqlite+aiosqlite:///./ads_runner.db` | SQLAlchemy URL; use `postgresql+asyncpg://…` in production |
| `OPENAI_API_KEY` | no | — | Fallback key for `gpt-*` models |
| `ANTHROPIC_API_KEY` | no | — | Fallback key for `claude-*` models |
| `GEMINI_API_KEY` | no | — | Fallback key for `gemini*` models |
| `ZHIPUAI_API_KEY` | no | — | Fallback key for `zhipu*` models |

### Frontend (`frontend/.env.example`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | no | `http://localhost:8007` | Backend base URL (Render service URL in production) |

## API

Auth: all `/api/*` endpoints require the `X-API-Key` header (shared secret from
`API_KEY`). Errors are structured JSON (`{"error": "...", "message": "..."}`);
stack traces are never returned to clients.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | no | Liveness probe |
| `GET` | `/` | no | Service info |
| `POST` | `/api/execute` | yes | Enqueue a campaign job → `{"status":"success","task_id":"…"}`. Body: `product_url` (http/https URL), `description` (10–5000 chars), `budget`, `provider` (litellm model id, e.g. `gpt-4o`, `gemini/gemini-1.5-pro`, `ollama/llama3`). Optional provider-key headers: `X-OpenAI-Key`, `X-Anthropic-Key`, `X-Gemini-Key`, `X-GLM-Key`. |
| `GET` | `/api/tasks/{task_id}` | yes | Poll status (`pending` → `running` → `success`/`error`) + campaign JSON + CSV |
| `POST` | `/api/settings/keys` | yes | Persist provider keys server-side so later runs work without re-entering them |

Example:

```bash
API=http://localhost:8007
KEY=your-api-key

curl -s -X POST $API/api/execute \
  -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  -H "X-OpenAI-Key: sk-your-key" \
  -d '{"product_url":"https://example.com/product","description":"Handmade leather wallets for men","budget":"50.00","provider":"gpt-4o"}'
# {"status":"success","task_id":"…"}

curl -s $API/api/tasks/<task_id> -H "X-API-Key: $KEY"
```

## Deploy

### Backend → Render (Docker)

1. Push this repo to GitHub.
2. Render → New → Web Service → your repo. Render detects the `Dockerfile`.
3. Set environment variables in Render's dashboard (same names as
   `backend/.env.example`): `API_KEY`, `ALLOWED_ORIGINS` (your frontend URL),
   provider key(s). Use a managed Postgres and set `DATABASE_URL` if you want
   persistent storage beyond the container.
4. Health check path: `/health`.

### Backend → Render (native Python, alternative)

Build command: `pip install -r backend/requirements.txt`
(Root directory: leave as repo root and prefix with `backend/`, or set Root
Directory to `backend`.) Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
(working directory `backend`). Health check path: `/health`.

### Frontend → Cloudflare Pages / Vercel / Netlify

Root directory `frontend`, build command `npm run build`, and set
`NEXT_PUBLIC_API_BASE_URL` to your Render backend URL. Add the frontend's URL
to the backend's `ALLOWED_ORIGINS`.

## Security notes

- No secrets are hardcoded anywhere; everything sensitive comes from env/headers.
- `/api/*` requires the shared-secret `X-API-Key` (compared with
  `secrets.compare_digest`); the server fails closed if `API_KEY` is unset.
- CORS is restricted to `ALLOWED_ORIGINS` — never `*` with credentials.
- Inputs are validated (URL format, description length, provider allowlist);
  errors are structured JSON with no stack traces.
- Provider LLM keys can be persisted via `/api/settings/keys` — this is a
  convenience store on your own server, not a vault; rotate keys if exposed.

## Project layout

```
backend/           FastAPI service (server.py, models.py, database.py)
backend/smoke.sh   Boot + endpoint smoke test (keep in repo)
backend/tests/     Regression + production-bar tests (pytest)
frontend/          Next.js UI
Dockerfile         Backend container image (build from repo root)
```

## Coordination & Automation
This agent is part of a larger ecosystem. It can be executed natively via its UI, or coordinated as a node in a multi-agent pipeline using the Central Connector System.
