# Lyftr AI — LLM Chatbot with Key Failover and Response Caching

A production-ready full-stack AI chatbot application built with **FastAPI**, **LiteLLM (Groq)**, **SQLite**, **React + Vite + Tailwind CSS**, and **Docker**. Supports multi-turn conversational memory, sequential API key failover, disk-backed LiteLLM response caching, per-request token tracking, and header-based failure simulation.

---

## 1. Live URLs

- **Frontend (Deployed):** `<FRONTEND_URL_PLACEHOLDER>`
- **Backend API (Deployed):** `<BACKEND_URL_PLACEHOLDER>`
- **Local Frontend:** `http://localhost:3000`
- **Local Backend:** `http://localhost:8000` (Swagger UI at `http://localhost:8000/docs`)

---

## 2. Run locally: with Docker and without

### Option A: With Docker (Recommended)

1. Create your environment file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
2. Add at least two valid Groq API keys (`GROQ_API_KEY_1` and `GROQ_API_KEY_2`) to `.env`.
3. Start the full stack:
   ```bash
   make up
   ```
   *(Or `docker compose up -d --build`)*
4. Open `http://localhost:3000` in your browser.
5. Stop the stack:
   ```bash
   make down
   ```

### Option B: Without Docker (Local Development)

#### Backend
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate | macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
# Edit .env with your GROQ_API_KEY_1 and GROQ_API_KEY_2, and set DATABASE_URL=sqlite:///./data/app.db
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```
The Vite dev server runs on `http://localhost:3000` and proxies `/api/*` requests to `http://localhost:8000`.

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Key Fallback (`KeyManager` + `LLMService`)
- `KeyManager` loads `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, and optional comma-separated `LLM_API_KEYS`, assigning deterministic IDs (`key_1`, `key_2`, ...). Actual key secrets are never exposed in logs or API responses.
- On each `POST /chat` request, `LLMService.execute_with_failover` iterates sequentially through the key pool, explicitly passing each `api_key` to `litellm.completion(...)` while preserving the exact model (`groq/llama-3.3-70b-versatile`) and full conversation message array.
- Transient errors (`429` rate limit/quota, `500`, `502`, `503`, connection/timeout errors) trigger automatic failover to the next key and increment `fallback_attempts`.
- If all keys fail, `AllProvidersUnavailableException` returns HTTP `503` with `{"detail": "all providers unavailable"}` without saving anything to SQLite.

### Caching (LiteLLM Built-in Cache + `FileDiskCache`)
- Uses LiteLLM's `litellm.cache` integration (`Cache(_backend=FileDiskCache(settings.CACHE_DIR))` for disk mode, or `Cache(type="local")` for in-memory mode).
- Cache keys are computed by LiteLLM from the model and full message list (`system` + `history` + new `user` message), ensuring different conversation contexts never collide, while identical first-turn prompts across different sessions produce `LLM_CACHE` hits.
- On cache hits, LiteLLM returns `_hidden_params["cache_hit"] = True`, preserving the reply text and token counts while setting `key_id = null` and `fallback_attempts = 0`.

### SQLite Session Storage
- SQLite is configured via `DATABASE_URL` (`sqlite:////data/app.db` in Docker, backed by the named volume `llm_chatbot_data` mounted at `/data`).
- The `messages` table stores `id`, `session_id`, `role`, `content`, `metadata` (JSON string for assistant replies), and `created_at` (ISO-8601 UTC timestamp), with indexes on `session_id` and `created_at`.
- `ConversationService.save_turn` writes both the user and assistant messages atomically in a single transaction only after a successful LLM/cache response. Failed requests are never persisted.
- `GET /sessions/{session_id}/messages` returns messages in chronological order without exposing system prompts, returning `404` for unknown sessions.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### Per-Message Token Usage
Every assistant message in the UI displays a metadata bar (`MessageMetadata`) showing:
- **Resolution Source** (`LIVE_INFERENCE` or `LLM_CACHE`)
- **Model** (`groq/llama-3.3-70b-versatile`)
- **Latency** (`ms`)
- **Input Tokens** (full prompt including system prompt + history + new message)
- **Output Tokens** (completion tokens for that turn)

### Verifying Cache Hits
1. Send a message in the UI (e.g., `"Explain RAG"`). The metadata badge shows `LIVE_INFERENCE` and `key_1`.
2. Click **New Chat** (or reload the page to generate a new `session_id`) and send the exact same prompt with the same system prompt.
3. The response returns immediately with `LLM_CACHE`, `key_id: null` (hidden/cache badge), `fallback_attempts: 0`, and identical reply and token counts.

### Verifying Failover (`X-Simulate-Failure`)
Ensure `ENABLE_FAILURE_SIMULATION=true` in `.env`, then run:
```bash
# Simulate key_1 rate limit -> fails over to key_2
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: key_1=429" \
  -d '{"session_id": "verify-failover", "message": "Hello!"}'
# Response metadata: "key_id": "key_2", "fallback_attempts": 1

# Simulate all keys failing -> returns 503
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Simulate-Failure: *=429" \
  -d '{"session_id": "verify-503", "message": "Hello!"}'
# Response: HTTP 503 {"detail": "all providers unavailable"}
```

---

## 5. Setup Used: your editor and AI tools

- **Editor:** VS Code / Antigravity IDE
- **AI Tools:** Antigravity AI coding assistant (used for scaffolding, test generation, and verification)

---

## 6. Bonus features (if any): what you added beyond the requirements and why

- **Live Health Indicator in Header:** Displays real-time backend readiness (`keys_configured` and cache status) on load so users immediately know if the key pool is healthy.
- **New Chat / Session Reset Button:** Allows quickly testing cross-session cache hits without manually refreshing the browser.
- **Cross-Platform Path Normalization:** Automatically maps `/data/...` Docker paths to `./data/...` on Windows local environments for seamless local development without Docker.

---

## Architecture Overview & Request Lifecycle

```
Browser (React + Vite)
   │  POST /api/chat  (or /chat)
   ▼
Nginx (port 3000) ──► FastAPI Backend (port 8000)
                         │
                         ├─► 1. Validate ChatRequest (Pydantic)
                         ├─► 2. Load session history from SQLite
                         ├─► 3. Build context: [system, ...history, user]
                         ├─► 4. LLMService.execute_with_failover()
                         │      ├─ Check LiteLLM FileDiskCache
                         │      └─ On miss: try key_1 -> key_2 via Groq
                         ├─► 5. Save user + assistant turn to SQLite
                         └─► 6. Return reply + metadata JSON
```

## Project Structure

```
llm-chatbot/
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
| `GET` | `/health` | Returns `200` when DB is reachable, `>= 2` keys are configured, and cache is enabled. |
| `POST` | `/chat` | Accepts `{ session_id, message, system_prompt? }`, supports `X-Simulate-Failure` header, returns `{ session_id, reply, metadata }`. |
| `GET` | `/sessions/{session_id}/messages` | Returns chronological user/assistant messages (`404` if session unknown). |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY_1` | Primary Groq API key | `""` |
| `GROQ_API_KEY_2` | Secondary Groq API key for failover | `""` |
| `GROQ_MODEL` | Groq model identifier | `llama-3.3-70b-versatile` |
| `DATABASE_URL` | SQLite connection string | `sqlite:////data/app.db` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://localhost:3000` |
| `ENABLE_FAILURE_SIMULATION` | Enable `X-Simulate-Failure` header | `true` |
| `CACHE_ENABLED` | Enable LiteLLM response caching | `true` |
| `CACHE_TYPE` | `disk` or `local` | `disk` |
| `CACHE_DIR` | Directory for disk cache files | `/data/llm_cache` |

## Testing Commands

Run the full backend test suite (uses mocked LiteLLM responses; no real API credits consumed):
```bash
pytest backend/tests -v
```

Build the frontend production bundle:
```bash
cd frontend && npm install && npm run build
```

## Docker Commands

```bash
make up      # Build and start backend (8000) & frontend (3000) with persistent /data volume
make down    # Stop containers (preserves SQLite volume)
make logs    # Stream container logs
```

## Deployment Instructions

1. Provision a container host (e.g., Render, Railway, Fly.io, or a VPS with Docker Compose).
2. Mount a persistent disk at `/data` for SQLite (`app.db`) and disk cache (`llm_cache`).
3. Set `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `ALLOWED_ORIGINS` (your deployed frontend URL), and `ENABLE_FAILURE_SIMULATION=false` (or `true` if demoing failover).
4. Set `VITE_API_URL` at frontend build time to your deployed backend URL (or use Nginx `/api` proxy).

## Troubleshooting

- **`GET /health` returns 503:** Verify at least two non-empty Groq keys are set in `.env` and `CACHE_ENABLED=true`.
- **CORS errors in browser:** Ensure `ALLOWED_ORIGINS` includes the exact frontend origin (e.g., `http://localhost:3000`).
- **SQLite persistence across restarts:** Confirm `docker compose down` is used without `-v` so the `llm_chatbot_data` volume is retained.

## Security Considerations

- API keys are loaded strictly from environment variables and masked in `KeyEntry.__repr__`; they are never logged or returned in HTTP responses.
- Exception handlers strip internal stack traces and return clean JSON `{"detail": ...}` payloads.
- `.env` is excluded via `.gitignore`.
#   L y f t r A I  
 