# Lyftr AI — LLM Chatbot with Key Failover and Response Caching

A production-ready full-stack AI chatbot application built with **FastAPI**, **LiteLLM (Groq)**, **SQLite**, **React + Vite + Tailwind CSS**, and **Docker**. Supports multi-turn conversational memory, sequential API key failover (`GROQ_API_KEY_1..N`), disk-backed LiteLLM response caching, per-request token usage tracking, and `X-Simulate-Failure` header testing.

---

## Live URLs

- **Frontend (Deployed):** `<FRONTEND_URL_PLACEHOLDER>`
- **Backend API (Deployed):** `<BACKEND_URL_PLACEHOLDER>`
- **Local Frontend:** `http://localhost:3000`
- **Local Backend:** `http://localhost:8000` (Swagger UI at `http://localhost:8000/docs`)

---

## Run locally: with Docker and without

### With Docker

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Add your Groq API keys (`GROQ_API_KEY_1`, `GROQ_API_KEY_2`, and optionally `GROQ_API_KEY_3`, `GROQ_API_KEY_4`) to `.env`.
3. Build and start the full stack:
   ```bash
   make up
   ```
   *(Or `docker compose up -d --build`)*
4. Open `http://localhost:3000` in your browser.
5. Stop the stack:
   ```bash
   make down
   ```

### Without Docker

#### Backend
```powershell
cd C:\lyftrAI\backend
..\venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
```
*(Or create a fresh virtual environment: `python -m venv venv`, activate it, `pip install -r requirements.txt`, and run `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.)*

#### Frontend
```powershell
cd C:\lyftrAI\frontend
npm install
npm run dev
```
The Vite dev server runs on `http://localhost:3000` and proxies `/api/*` requests to `http://localhost:8000`.

---

## Design decisions: key fallback, caching, SQLite session storage

### Key Fallback
- `KeyManager` ([key_manager.py](backend/app/utils/key_manager.py)) loads `GROQ_API_KEY_1..N` (sorted numerically) and optional comma-separated `LLM_API_KEYS`, assigning deterministic IDs (`key_1`, `key_2`, ...). Secrets are masked in `__repr__` and never exposed in logs or API responses.
- `LLMService.execute_with_failover` ([llm_service.py](backend/app/services/llm_service.py)) attempts keys sequentially, explicitly passing each `api_key` to `litellm.completion(...)` while preserving the same model and full conversation context.
- Transient failures (`429` rate limit/quota, `500`, `502`, `503`, connection/timeout errors) trigger automatic failover to the next key and increment `fallback_attempts`.
- When all keys fail, `AllProvidersUnavailableException` returns HTTP `503` with `{"detail": "all providers unavailable"}`.

### Caching
- Uses LiteLLM's built-in `litellm.cache` ([cache_service.py](backend/app/services/cache_service.py)) with a custom `FileDiskCache` backend (`CACHE_TYPE=disk`, `CACHE_DIR=/data/llm_cache`) or in-memory local cache (`CACHE_TYPE=local`).
- LiteLLM keys cache entries on the model and full message array (`system` + `history` + `user`), ensuring different conversation contexts never collide while identical first-turn prompts across different sessions produce `LLM_CACHE` hits.
- Cache hits preserve reply text and token counts, set `resolution_source="LLM_CACHE"`, `key_id=null`, and `fallback_attempts=0`.

### SQLite Session Storage
- Stored in SQLite via SQLAlchemy ([models.py](backend/app/database/models.py), [connection.py](backend/app/database/connection.py)), defaulting to `sqlite:////data/app.db` (persisted in Docker via the `llm_chatbot_data` volume).
- The `messages` table stores `id`, `session_id`, `role`, `content`, `metadata` (JSON for assistant responses), and `created_at` (ISO-8601 UTC), with indexes on `session_id` and `created_at`.
- `ConversationService.save_turn` ([conversation_service.py](backend/app/services/conversation_service.py)) writes user and assistant turns atomically only after a successful response; failed requests are never saved.
- `GET /sessions/{session_id}/messages` returns messages in chronological order without exposing system prompts, returning `404` for unknown sessions.

---

## Verification: how to see failover, cache hits and per-message token usage

### Per-Message Token Usage
Every assistant message in the UI renders a metadata bar (`MessageMetadata`) showing:
- **Resolution source:** `LIVE_INFERENCE` or `LLM_CACHE` (`data-testid="meta-source"`)
- **Model:** e.g. `groq/llama-3.3-70b-versatile` (`data-testid="meta-model"`)
- **Latency:** server-measured `ms` (`data-testid="meta-latency"`)
- **Input tokens:** full prompt tokens (`data-testid="meta-input-tokens"`)
- **Output tokens:** completion tokens (`data-testid="meta-output-tokens"`)

### Cache Hits
1. Send a message in the UI (e.g., `"Explain RAG"`). The badge displays `LIVE_INFERENCE` and `key_1`.
2. Click **New Chat** (or reload the page to generate a new `session_id`) and send the exact same prompt with the same system prompt.
3. The response displays the green `LLM_CACHE` badge with identical reply text, preserved token counts, and `key_id = null`.

### Failover Simulation (`X-Simulate-Failure`)
Ensure `ENABLE_FAILURE_SIMULATION=true` in `.env`:
```powershell
# Simulate key_1=429 -> fails over to key_2 (key_id="key_2", fallback_attempts=1)
curl.exe -X POST http://localhost:8000/chat -H "Content-Type: application/json" -H "X-Simulate-Failure: key_1=429" -d "{\"session_id\":\"verify-failover\",\"message\":\"Hello\"}"

# Simulate all keys failing -> HTTP 503 {"detail":"all providers unavailable"}
curl.exe -i -X POST http://localhost:8000/chat -H "Content-Type: application/json" -H "X-Simulate-Failure: *=429" -d "{\"session_id\":\"verify-503\",\"message\":\"Hello\"}"
```

---

## Setup Used: your editor and AI tools

- **Editor:** VS Code / Antigravity IDE
- **AI Tools:** Antigravity AI coding assistant (scaffolding, debugging, test suite, and documentation)

---

## Bonus features (if any): what you added beyond the requirements and why

- **Dynamic 4+ Key Pool Support (`GROQ_API_KEY_1..N`):** Automatically discovers and orders any number of numbered Groq keys in `.env` or environment variables, plus `MAX_TOKENS` configuration to help manage free-tier TPM quotas.
- **Header Health Status Indicator:** Displays live backend readiness (`keys_configured` and cache status) in the UI header.
- **New Chat Button:** Resets the session cleanly for quick multi-session cache testing.
- **Cross-Platform `/data` Path Normalization:** Automatically maps `/data/...` Docker paths to `./data/...` when running locally on Windows.

---

## Architecture Overview

```
Browser (React + Vite)
   │  POST /api/chat
   ▼
Nginx (port 3000) ──► FastAPI Backend (port 8000)
                         │
                         ├─► Validate request (Pydantic)
                         ├─► Load session history (SQLite)
                         ├─► Build context [system, ...history, user]
                         ├─► LLMService.execute_with_failover()
                         │      ├─ Check LiteLLM FileDiskCache
                         │      └─ On miss: sequential failover across key_1..key_N
                         ├─► Save user + assistant turn (SQLite)
                         └─► Return reply + metadata JSON
```

## Request Lifecycle

1. Client generates a fresh `session_id` on page load and sends `{ session_id, message, system_prompt? }` to `POST /chat`.
2. Backend validates inputs (`session_id` 1–128 chars, trimmed `message` 1–4000 chars) and parses `X-Simulate-Failure` if `ENABLE_FAILURE_SIMULATION=true`.
3. `ConversationService` fetches prior turns for `session_id` from SQLite and builds the full message array.
4. `LLMService` checks LiteLLM cache and, on miss, tries each configured Groq key in order until one succeeds or all fail (`503`).
5. On success, both the user message and assistant reply (with metadata JSON) are committed to SQLite and returned to the client.

## Project Structure

```
lyftrAI/
├── backend/
│   ├── app/
│   │   ├── api/routes.py
│   │   ├── database/{connection.py,models.py}
│   │   ├── schemas/chat_schema.py
│   │   ├── services/{cache_service.py,conversation_service.py,llm_service.py}
│   │   ├── utils/{exceptions.py,key_manager.py}
│   │   ├── config.py
│   │   └── main.py
│   ├── tests/{test_caching.py,test_chat.py,test_failover.py,test_health.py,test_sessions.py}
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/{ChatInput.jsx,ChatMessage.jsx,ChatWindow.jsx,MessageMetadata.jsx,SystemPrompt.jsx}
│   │   ├── hooks/useChat.js
│   │   ├── services/api.js
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml
├── Makefile
├── .env.example
└── README.md
```

## API Documentation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Returns `200` only when SQLite is reachable, `>= 2` keys are configured, and `CACHE_ENABLED=true`. |
| `POST` | `/chat` | Processes a chat turn with multi-turn memory, failover, and caching. |
| `GET` | `/sessions/{session_id}/messages` | Returns chronological user/assistant messages (`404` if session not found; never returns system prompt). |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY_1` | Primary Groq API key | `""` |
| `GROQ_API_KEY_2` | Secondary Groq API key | `""` |
| `GROQ_API_KEY_3` / `_4` | Optional additional Groq API keys | `""` |
| `LLM_API_KEYS` | Optional comma-separated Groq API keys | `""` |
| `GROQ_MODEL` | Groq model identifier | `llama-3.3-70b-versatile` |
| `MAX_TOKENS` | Optional completion `max_tokens` cap | `1024` |
| `DATABASE_URL` | SQLite connection URL | `sqlite:////data/app.db` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://localhost:3000` |
| `ENABLE_FAILURE_SIMULATION` | Enable `X-Simulate-Failure` header | `false` |
| `CACHE_ENABLED` | Enable LiteLLM response caching | `true` |
| `CACHE_TYPE` | `disk` or `local` | `disk` |
| `CACHE_DIR` | Directory for disk cache files | `/data/llm_cache` |

## Docker Commands

```bash
make up      # Build and start backend (8000) and frontend (3000)
make down    # Stop containers while preserving /data volume
make build   # Rebuild images
make logs    # Follow container logs
```

## Testing Commands

```powershell
# Backend unit & integration tests (mocked LLM calls, no API credits used)
c:\lyftrAI\venv\Scripts\python.exe -m pytest backend/tests -v

# Frontend production build check
cd C:\lyftrAI\frontend; npm run build
```

## Deployment Instructions

1. Provision a Docker-capable host (Render, Railway, Fly.io, or VPS) with a persistent disk mounted at `/data`.
2. Configure environment variables (`GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `ALLOWED_ORIGINS` matching your frontend origin, and `ENABLE_FAILURE_SIMULATION=false` unless testing).
3. If frontend and backend are deployed on separate domains, pass `VITE_API_URL=https://your-backend-domain` when building the frontend image.
4. Update the **Live URLs** section at the top of this README after deployment.

## Troubleshooting

- **`GET /health` returns `503`:** Ensure at least 2 valid Groq keys are set in `.env` and `CACHE_ENABLED=true`.
- **`POST /chat` returns `503` under rapid requests:** Groq enforces TPM/RPM limits per organization/account. Use keys from separate Groq accounts, lower `MAX_TOKENS`, or use a higher-throughput model such as `llama-3.1-8b-instant`.
- **CORS errors in browser:** Add your exact frontend origin to `ALLOWED_ORIGINS`.

## Security Considerations

- API keys are loaded from `.env`/environment variables, masked in `KeyEntry.__repr__` and error logs, and never returned in HTTP responses.
- Exception handlers return clean JSON `{"detail": ...}` responses without stack traces.
- `.env`, `*.db`, and `data/` are excluded via `.gitignore`.
