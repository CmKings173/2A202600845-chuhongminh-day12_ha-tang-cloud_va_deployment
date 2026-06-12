# Deployment Information

**Student:** Chu Hồng Minh — 2A202600845  
**Platform:** Railway  
**Date:** 2026-06-12

---

## Public URL

```
https://agent-production-c85d.up.railway.app
```

---

## Deploy Steps

```bash
# 1. Vào thư mục lab complete
cd 06-lab-complete

# 2. Login Railway
railway login

# 3. Init project
railway init

# 4. Set environment variables
railway variables set AGENT_API_KEY=<generate-a-strong-random-key>
railway variables set JWT_SECRET=<generate-a-strong-random-secret>
railway variables set ENVIRONMENT=production
railway variables set LOG_LEVEL=INFO
railway variables set RATE_LIMIT_PER_MINUTE=20
railway variables set DAILY_BUDGET_USD=5.0

# 5. Deploy
railway up

# 6. Lấy public URL
railway domain
```

---

## Environment Variables Set

| Variable | Value |
|----------|-------|
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | _(set via railway variables)_ |
| `JWT_SECRET` | _(set via railway variables)_ |
| `RATE_LIMIT_PER_MINUTE` | `20` |
| `DAILY_BUDGET_USD` | `5.0` |
| `LOG_LEVEL` | `INFO` |

---

## Test Commands

### Health Check
```bash
curl https://agent-production-c85d.up.railway.app/health
# Expected:
# {
#   "status": "ok",
#   "version": "1.0.0",
#   "environment": "production",
#   "uptime_seconds": ...,
#   ...
# }
```

### Readiness Check
```bash
curl https://agent-production-c85d.up.railway.app/ready
# Expected: {"ready": true}
```

### Authentication required (no key → 401)
```bash
curl -X POST https://agent-production-c85d.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "hello"}'
# Expected: HTTP 401
```

### Authenticated request (→ 200)
```bash
curl -X POST https://agent-production-c85d.up.railway.app/ask \
  -H "X-API-Key: d69b6e31a59ccc899e6f0686fb2871b7" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is Docker?"}'
# Expected: HTTP 200 with answer
```

### Rate limiting test (→ 429 after 20 req/min)
```bash
for i in $(seq 1 25); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST https://agent-production-c85d.up.railway.app/ask \
    -H "X-API-Key: d69b6e31a59ccc899e6f0686fb2871b7" \
    -H "Content-Type: application/json" \
    -d '{"question": "test"}')
  echo "Request $i: HTTP $STATUS"
done
# Expected: requests 1-20 → 200, request 21+ → 429
```

### JWT token (bonus)
```bash
curl -X POST https://agent-production-c85d.up.railway.app/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "student", "password": "demo123"}'
# Expected: {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600}
```

---

## Screenshots

Place screenshots in `screenshots/` folder:

- `screenshots/dashboard.png` — Railway deployment dashboard
- `screenshots/running.png` — Service running (health check green)
- `screenshots/test.png` — curl test results showing 200/401/429

---

## Architecture

```
Internet
    │
    ▼
Railway (HTTPS + TLS termination)
    │
    ▼
Docker Container (uvicorn, 2 workers)
    │
    ├─ GET  /health     → liveness probe
    ├─ GET  /ready      → readiness probe
    ├─ POST /ask        → auth → rate limit → cost guard → LLM
    ├─ POST /auth/token → JWT (bonus)
    └─ GET  /metrics    → stats (auth required)
```

---

## Notes

- App dùng **mock LLM** (không cần OpenAI API key)
- Rate limit: **20 req/min** per API key (sliding window)
- Daily budget: **$5.00** (reset midnight UTC)
- Graceful shutdown: waits up to **30 seconds** for in-flight requests
- Logs: structured JSON, viewable in Railway dashboard → Logs tab
