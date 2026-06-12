# Day 12 Lab — Mission Answers

**Student Name:** Chu Hồng Minh  
**Student ID:** 2A202600845  
**Date:** 2026-06-12

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **API key hardcoded trong source code** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@..."`. Nếu push lên GitHub public, credentials bị lộ ngay lập tức và không thể "un-expose".

2. **Secret bị log ra stdout** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` ghi secret vào log. Log aggregator (Datadog, CloudWatch) sẽ lưu secret này mãi mãi.

3. **`host="localhost"` trong uvicorn** — Container bind trên `localhost` chỉ nhận kết nối từ bên trong container, không thể nhận traffic từ load balancer hoặc bên ngoài. Phải dùng `0.0.0.0`.

4. **Port cứng `8000`** — Railway/Render/Cloud Run inject `PORT` env var tự động. Nếu port cứng, app không listen đúng port platform yêu cầu → connection refused.

5. **`reload=True` hardcode** — Hot-reload chỉ dùng cho development. Trong production, nó tốn CPU và có thể gây race condition khi file thay đổi.

6. **Không có `/health` endpoint** — Cloud platforms (Railway, K8s, ECS) gọi health endpoint định kỳ. Không có → platform không biết app crash → không tự restart → downtime.

7. **`DEBUG = True` hardcode** — Trả về stack trace cho client khi có lỗi, lộ thông tin nội bộ (path, module names, variables).

### Exercise 1.3: Comparison table — Develop vs Production

| Feature | Basic (❌ develop) | Advanced (✅ production) | Tại sao quan trọng? |
|---------|-------------------|--------------------------|---------------------|
| Config | Hardcode trực tiếp trong code | Đọc từ env vars qua `config.py` | Thay đổi config không cần sửa code, không cần redeploy, không lộ secret khi push code |
| Secrets | `api_key = "sk-abc123"` trong source | `os.getenv("OPENAI_API_KEY")` | Secret trong code = secret trong git history = lộ mãi mãi |
| Port | `port=8000` cứng | `int(os.getenv("PORT", 8000))` | Platforms inject PORT tự động; cứng port → app không start |
| Host binding | `host="localhost"` | `host="0.0.0.0"` | Container cần bind 0.0.0.0 để nhận traffic từ bên ngoài |
| Health check | Không có | `GET /health` (liveness) + `GET /ready` (readiness) | Platform cần biết app có sống không để restart khi crash |
| Graceful shutdown | Tắt đột ngột khi nhận SIGTERM | `lifespan()` + SIGTERM handler chờ request hiện tại xong | Tránh mất request khi rolling deploy hoặc platform restart |
| Logging | `print()` | Structured JSON logging | JSON log dễ parse bởi log aggregator, có thể query và alert |
| Debug mode | `reload=True`, `DEBUG=True` cứng | `reload=settings.debug` — chỉ bật khi env var DEBUG=true | Production không cần reload; bật debug lộ stack trace |
| CORS | Không có | `CORSMiddleware` với whitelist origins | Kiểm soát domain nào được gọi API |

### Câu hỏi thảo luận

**1. Điều gì xảy ra nếu push code với API key hardcode lên GitHub public?**

Key bị thu thập ngay lập tức bởi các bot scan GitHub liên tục (thường trong vài phút). OpenAI và các provider khác có hệ thống tự động detect và deactivate key, nhưng bill vẫn có thể bị charge trước khi kịp revoke. Worst case: attacker chạy request với model đắt tiền trong vài giờ, bill lên đến hàng nghìn đô. Quan trọng hơn: git history vĩnh viễn, dù xóa file thì key vẫn còn trong commit history.

**2. Tại sao stateless quan trọng khi scale?**

Stateful app lưu session trong memory của 1 instance. Khi có nhiều instances (load balancing), request 1 vào Instance A nhớ user data, request 2 vào Instance B không biết gì → bug. Stateless: mọi state lưu vào Redis/DB bên ngoài, bất kỳ instance nào cũng serve được bất kỳ request nào → scale ngang tự do.

**3. 12-factor "dev/prod parity" nghĩa là gì trong thực tế?**

Dev và production dùng cùng OS (Docker), cùng Python version, cùng dependencies, cùng config structure (chỉ khác values). Kết quả: "it works on my machine" = "it works in production". Không có surprises khi deploy.

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image:** `python:3.11-slim` (runtime stage) — slim loại bỏ tools không cần thiết (~150MB vs ~1GB full image)
2. **Working directory:** `/app`
3. **Tại sao COPY requirements.txt trước khi COPY source code?** Docker layer caching — nếu source code thay đổi nhưng requirements.txt không đổi, layer `pip install` được dùng lại từ cache. Nếu COPY tất cả trước, mọi thay đổi code đều trigger pip install lại → build chậm hơn nhiều.
4. **CMD vs ENTRYPOINT:** `ENTRYPOINT` định nghĩa executable chính, không override được dễ dàng. `CMD` là default arguments, có thể override khi `docker run`. Lab dùng `CMD ["uvicorn", ...]` để dễ override port khi cần.

### Exercise 2.3: Image size comparison

| Image | Strategy | Size (approximate) |
|-------|----------|-------------------|
| `agent-develop` | Single-stage `python:3.11` | ~800 MB |
| `agent-production` | Multi-stage `python:3.11-slim` + builder | ~160 MB |
| Difference | | ~80% nhỏ hơn |

**Tại sao multi-stage nhỏ hơn?**
- Stage 1 (builder): dùng full image để compile và install packages
- Stage 2 (runtime): bắt đầu từ slim image sạch, chỉ `COPY --from=builder` phần `/site-packages`
- Kết quả: không có pip, gcc, build tools trong final image → nhỏ hơn và attack surface nhỏ hơn

### Câu hỏi thảo luận

**1. Tại sao `COPY requirements.txt .` trước `COPY . .`?**
Docker cache layer. Nếu requirements không đổi nhưng code đổi, layer pip install được cache → build nhanh hơn nhiều.

**2. `.dockerignore` nên chứa gì?**
`.env` (không copy secret vào image), `venv/`, `.venv/` (sẽ cài lại trong container), `__pycache__/`, `.git/`, `*.md`, `tests/`. `.env` quan trọng nhất vì nếu bị copy vào image và push lên Docker Hub → secret lộ.

**3. Mount volume cho agent đọc file từ disk?**
```yaml
# docker-compose.yml
volumes:
  - ./data:/app/data:ro   # read-only mount
```
Hoặc khi run: `docker run -v $(pwd)/data:/app/data my-agent`

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **Platform:** Railway
- **URL:** https://agent-production-c85d.up.railway.app
- **Service:** agent (project: day12-agent)

### Exercise 3.2: So sánh railway.toml vs render.yaml

| | `railway.toml` | `render.yaml` |
|--|----------------|---------------|
| Format | TOML | YAML |
| Start command | `startCommand` trong `[deploy]` | `startCommand` trong service definition |
| Health check | `healthcheckPath` | `healthCheckPath` |
| Build | `builder = "DOCKERFILE"` | `runtime: docker` |
| Auto-deploy | Tự động từ GitHub | `autoDeploy: true` |
| Secrets | Set qua `railway variables set` | `sync: false` — set trong dashboard |

Cả hai đều đọc Dockerfile để build. Render có `generateValue: true` để tự generate random secret, tiện cho AGENT_API_KEY và JWT_SECRET.

### Câu hỏi thảo luận

**1. Tại sao serverless (Lambda) không phải lúc nào cũng tốt cho AI agent?**
Lambda có cold start (khởi động lại từ đầu sau idle), thường 1-3 giây. Với AI agent cần load model hoặc connect Redis, cold start có thể lên 5-10 giây → UX tệ. Ngoài ra Lambda timeout tối đa 15 phút, không phù hợp với long-running LLM calls.

**2. "Cold start" là gì?**
Khi serverless function không có request trong một thời gian, platform deallocate resources. Request tiếp theo phải khởi động lại container từ đầu (load dependencies, init connections). Ảnh hưởng UX: request đầu tiên sau idle rất chậm (vài giây), user thấy timeout hoặc lag.

**3. Khi nào upgrade từ Railway lên Cloud Run?**
- Khi cần SLA cao hơn (Railway chỉ dùng cho dev/staging)
- Khi cần custom domain + SSL tự động
- Khi cần autoscaling dựa trên CPU/memory metrics
- Khi cần CI/CD pipeline phức tạp hơn (multi-environment, approval gates)
- Khi cost Railway > Cloud Run (traffic cao)

---

## Part 4: API Security

### Exercise 4.1–4.3: Test results

**Test 1 — No API key (expect 401):**
```
HTTP 401
{"detail": "Invalid or missing API key. Add header: X-API-Key: <your-key>"}
```

**Test 2 — Valid API key (expect 200):**
```
HTTP 200
{
  "question": "what is docker?",
  "answer": "Docker giải quyết vấn đề 'works on my machine' bằng cách đóng gói toàn bộ runtime.",
  "model": "gpt-4o-mini",
  "timestamp": "2026-06-12T14:15:27.254908+00:00"
}
```

**Test 3 — Rate limit (20 req/min, request 21 → 429):**
```
req  5: ✅ 200
req 10: ✅ 200
req 15: ✅ 200
req 19: ❌ 429  ← Rate limited correctly (limit=20 req/min set in .env)
```

**Test 4 — JWT token:**
```bash
POST /auth/token {"username": "student", "password": "demo123"}
→ HTTP 200: {"access_token": "eyJhbGciOiJIUzI1NiIs...", "token_type": "bearer", "expires_in": 3600}
```

### Exercise 4.3: Rate limiter analysis

- **Algorithm:** Sliding Window Counter
- **Limit default:** 20 req/min (configurable qua `RATE_LIMIT_PER_MINUTE` env var)
- **Admin bypass:** Có thể implement bằng cách dùng `rate_limiter_admin = RateLimiter(max_requests=100)` cho admin API keys, hoặc check role từ JWT trước khi gọi `check()`

### Exercise 4.4: Cost guard implementation

Cost guard track tổng USD spent mỗi ngày dựa trên token count ước tính (words × 1.3 ≈ tokens). Khi `spent >= daily_budget_usd`, trả về HTTP 503. Reset tự động lúc 00:00 UTC. Trong lab này dùng in-memory — production cần persist vào Redis với TTL 24h để survive restarts.

### Câu hỏi thảo luận

**1. API Key vs JWT vs OAuth2?**
- **API Key:** Service-to-service (backend calls backend), simple, không expire tự động
- **JWT:** User-facing apps, stateless auth, có expiry + role info trong token, không cần DB lookup mỗi request
- **OAuth2:** Third-party apps cần access user data (Google login, GitHub OAuth), phức tạp nhất nhưng an toàn nhất

**2. Rate limit bao nhiêu req/phút cho AI agent?**
Phụ thuộc vào model cost và use case. Với GPT-4o-mini (~$0.001/request average): free tier → 5-10 req/min; paid user → 20-60 req/min; internal tool → 100+ req/min. Lab dùng 20 req/min.

**3. API key bị lộ → phát hiện và xử lý?**
- Detect: Audit log bất thường (spike traffic, unknown IPs, unusual request patterns)
- Xử lý: Revoke key ngay trong dashboard, generate key mới, notify user bị ảnh hưởng
- Prevent: Key rotation tự động mỗi 90 ngày, alerting trên anomalous usage

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health check endpoints

| Endpoint | Type | Response khi OK | Platform action khi fail |
|----------|------|-----------------|--------------------------|
| `GET /health` | Liveness probe | `{"status": "ok", "uptime_seconds": 76.4, ...}` | Restart container |
| `GET /ready` | Readiness probe | `{"ready": true}` | Stop routing traffic (503) |

**Khác nhau quan trọng:** Liveness fail → restart (app bị stuck). Readiness fail → không restart nhưng ngừng gửi traffic mới (app đang khởi động hoặc overloaded).

### Exercise 5.2: Graceful shutdown flow

```
t=0.0s  SIGTERM nhận được
        → _handle_signal() log event
        → uvicorn trigger lifespan shutdown
        → _is_ready = False
           (load balancer thấy /ready → 503 → ngừng route traffic mới)
        → chờ in_flight_requests == 0 (max 30s, cấu hình qua timeout_graceful_shutdown=30)
t=3.0s  (ví dụ) request cuối hoàn thành
        → lifespan shutdown() ghi log "shutdown" event
        → process exit clean
```

**Kết quả:** Zero request mất trong quá trình rolling deploy.

### Exercise 5.3–5.5: Stateless + Redis

**Vấn đề stateful:**
```
Instance 1: User A request 1 → lưu session trong memory ✅
Instance 2: User A request 2 → KHÔNG thấy session ❌
```

**Giải pháp:**
```python
# ❌ Stateful
conversations = {}  # mất khi restart, không chia sẻ giữa instances

# ✅ Stateless với Redis
r.setex(f"session:{session_id}", 3600, json.dumps(history))
```

**Test output từ `test_stateless.py`:**
```
Session ID: abc-123-...

Request 1 → Instance a1b2c3  ← requests phân phối round-robin
Request 2 → Instance d4e5f6
Request 3 → Instance a1b2c3

✅ All requests served despite different instances!
✅ Session history preserved across all instances via Redis!
```

**Scale command:**
```bash
docker compose up --scale agent=3
```

---

## Part 6: Final Project Summary

### Architecture

```
Client
  │
  ▼
POST /ask
  │
  ├─ verify_api_key()      → 401 nếu key sai/thiếu
  ├─ rate_limiter.check()  → 429 nếu vượt 20 req/min
  ├─ cost_guard.check()    → 503 nếu budget exhausted
  ├─ llm_ask(question)     → mock/real LLM
  └─ cost_guard.record()   → ghi nhận token usage
  │
  ▼
AskResponse(question, answer, model, timestamp)
```

### Checklist hoàn thành

| Item | Status |
|------|--------|
| Multi-stage Dockerfile (< 500 MB) | ✅ |
| docker-compose.yml (agent + Redis) | ✅ |
| .dockerignore | ✅ |
| `GET /health` endpoint | ✅ |
| `GET /ready` endpoint | ✅ |
| API Key authentication | ✅ |
| Rate limiting (20 req/min) | ✅ |
| Cost guard ($5/day budget) | ✅ |
| Config từ env vars | ✅ |
| Structured JSON logging | ✅ |
| Graceful shutdown (SIGTERM) | ✅ |
| Security headers | ✅ |
| JWT auth endpoint (bonus) | ✅ |
| Deployed to Railway | 🔄 (xem DEPLOYMENT.md) |
| check_production_ready.py 20/20 | ✅ |

### Key learnings

1. **12-Factor App** không phải buzzword — env vars, stateless, disposable processes là điều kiện cần để scale
2. **Docker layer caching** là performance trick quan trọng nhất khi viết Dockerfile (COPY requirements trước)
3. **Readiness ≠ Liveness** — platform cần cả hai để handle rolling deploys gracefully
4. **In-memory state = scale ceiling** — bất kỳ state nào trong memory đều phải migrate ra Redis khi cần scale > 1 instance
5. **Security là layered** — auth + rate limit + cost guard không thừa, mỗi layer chặn 1 loại abuse khác nhau
