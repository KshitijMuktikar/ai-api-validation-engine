# AI API Validation Engine

Production-oriented **FastAPI** service that validates JSON API responses against **OpenAPI 3.x** response schemas using a **hybrid** engine, extended with an **API test runner** (Rest Assured–style execution + the same validation stack).

1. **Rule-based (primary)** — deterministic checks via **JSON Schema** (`jsonschema`): required fields, types, `additionalProperties`, enums, formats, and bounds where the schema defines them.
2. **LLM (secondary, optional)** — **OpenAI** async completions for **semantic** or subtle issues, with prompts designed to treat embedded text as **data**, not instructions.
3. **API testing** — `requests`-based HTTP client with retries; `POST /run-test` and `POST /run-tests` execute calls, then pipe responses into the hybrid validator (with optional **skip LLM when structural rules already fail**).

Results can be **cached** in memory (TTL + max size), **rate-limited** per IP, and **logged** to console and `logs/app.log`. A small **web UI** is served at **`/ui`**. **GitHub Actions** CI runs `pytest` plus an **httpbin** smoke script.

---

## Architecture (text diagram)

```
                    ┌─────────────────────────────────────────┐
  HTTP Client       │  FastAPI (app.main)                      │
        │           │  ├─ SlowAPI middleware (rate limit)    │
        ▼           │  ├─ CORS (configurable origins)        │
POST /validate,     │  ├─ Global exception → {error,details}  │
   /run-test         │  └─ Routers (+ /run-tests, /test-history)│
        │           └─────────────────────────────────────────┘
        │                          │
        │                          ▼
        │           ┌─────────────────────────────────────────┐
        │           │  Pydantic: ValidateRequest               │
        │           │  (reject malformed JSON / invalid spec)  │
        │           └─────────────────────────────────────────┘
        │                          │
        │                          ▼
        │           ┌─────────────────────────────────────────┐
        │           │  OpenAPI loader (inline or async URL)      │
        │           │  + swagger_parser ($ref, path templates) │
        │           └─────────────────────────────────────────┘
        │                          │
        │                          ▼
        │           ┌─────────────────────────────────────────┐
        │           │  Hybrid validation (+ optional HTTP client) │
        │           │  1) api_client (requests + retries)         │
        │           │  2) rule_validator (jsonschema)            │
        │           │  3) optional llm_validator (AsyncOpenAI)   │
        │           │  4) merge + confidence + validation_source  │
        │           │  5) TTL cache (sha256 of inputs)           │
        │           └─────────────────────────────────────────┘
        │                          │
        └──────────────────────────┴──► JSON ValidationResult
```

---

## Project layout

```
ai-api-validation-engine/
├── app/
│   ├── __init__.py
│   ├── main.py              # App factory, middleware, exception handlers
│   ├── config.py            # Pydantic Settings / env
│   ├── logging_config.py    # Console + rotating file logs
│   ├── core/
│   │   └── exceptions.py    # AppError hierarchy
│   ├── middleware/
│   │   └── rate_limit.py    # slowapi Limiter
│   ├── models/
│   │   ├── schemas.py
│   │   └── testing_schemas.py   # APITestCase, TestExecutionReport
│   ├── routers/
│   │   ├── health.py
│   │   ├── validate.py
│   │   ├── batch.py
│   │   ├── export_router.py
│   │   └── run_testing.py       # /run-test, /run-tests, /test-history
│   ├── services/
│   │   ├── openapi_loader.py
│   │   ├── rule_validator.py
│   │   ├── llm_validator.py
│   │   ├── hybrid_validator.py
│   │   ├── cache_service.py
│   │   └── test_history.py
│   ├── testing/
│   │   ├── api_client.py        # requests + retries
│   │   └── test_runner.py       # execute tests → hybrid validation
│   └── utils/
│       └── swagger_parser.py
├── static/
│   └── index.html               # Web UI (mounted at /ui)
├── specs/                       # OpenAPI JSON files for test cases
├── scripts/
│   └── ci_smoke_test.py         # CI: live httpbin smoke
├── .github/workflows/
│   └── ci.yml
├── tests/
│   ├── conftest.py
│   ├── test_rule_validator.py
│   ├── test_validate_api.py
│   ├── test_runner_unit.py
│   ├── test_errors.py
│   └── test_export.py
├── logs/
│   └── .gitkeep             # Log files written at runtime (e.g. app.log)
├── samples/                 # Example OpenAPI + bodies
├── main.py                  # Shim: re-exports app for `uvicorn main:app`
├── requirements.txt
├── pytest.ini
├── Dockerfile
├── .env.example
└── README.md
```

---

## Requirements

- Python **3.10+** (3.12 in Docker)
- **OpenAI API key** if you enable the LLM pass (`use_llm_semantic: true` and `OPENAI_API_KEY` set)

OpenAPI **3.x** is required for schema extraction (Swagger 2.0 is rejected with a clear error).

---

## Quick start

```bash
cd ai-api-validation-engine
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
copy .env.example .env          # Windows — then set OPENAI_API_KEY if using LLM
# cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# or: uvicorn main:app ...   (root shim)
```

Open **http://127.0.0.1:8000/docs** for interactive OpenAPI UI, or **http://127.0.0.1:8000/ui/** for the test runner page.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | For LLM pass | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Chat model |
| `OPENAI_TIMEOUT_SECONDS` | No | `60` | Client timeout |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_FILE` | No | `logs/app.log` | Rotating log file path |
| `CORS_ORIGINS` | No | `*` | Comma-separated origins (restrict in production) |
| `RATE_LIMIT_PER_MINUTE` | No | `60` | Per-IP requests/minute (SlowAPI) |
| `VALIDATION_CACHE_TTL_SECONDS` | No | `300` | In-memory cache TTL (0 disables) |
| `VALIDATION_CACHE_MAX_ENTRIES` | No | `512` | Max cached validation entries |
| `BATCH_MAX_ITEMS` | No | `20` | Max items per `POST /validate/batch` |
| `HTTP_CLIENT_TIMEOUT_SECONDS` | No | `30` | Outbound API test request timeout |
| `HTTP_CLIENT_MAX_RETRIES` | No | `3` | urllib3 retry count for test HTTP client |
| `HTTP_CLIENT_RETRY_BACKOFF_FACTOR` | No | `0.5` | Backoff between retries |
| `SWAGGER_SPECS_DIRECTORY` | No | `specs` | Where `expected_swagger` filenames are resolved |
| `SWAGGER_SPECS_FALLBACK_DIRECTORIES` | No | `samples` | Extra comma-separated dirs to search |
| `TEST_ENV_BASE_URLS_JSON` | No | `{}` | `{"dev":"http://localhost:8080"}` for relative test URLs |
| `TEST_HISTORY_MAX_ENTRIES` | No | `500` | In-memory cap for `GET /test-history` |
| `TEST_RUN_PARALLEL_MAX` | No | `5` | Max concurrent tests in `POST /run-tests` |
| `TEST_RUN_BATCH_MAX_ITEMS` | No | `50` | Max tests per `POST /run-tests` |

---

## API

### `POST /validate`

Validates `response_body` against the resolved JSON Schema for `path`, `method`, and `status_code`.

**Request** (JSON): `openapi_spec` *or* `openapi_spec_url`, plus:

| Field | Description |
|-------|-------------|
| `path` | e.g. `/pets/1` |
| `method` | lowercase, e.g. `get` |
| `status_code` | e.g. `200` |
| `response_body` | any JSON value |
| `include_schema_in_prompt` | include full schema in LLM context (default `true`) |
| `use_llm_semantic` | run secondary LLM pass when API key is set (default `true`) |

**Response** (`ValidationResult`):

```json
{
  "missing_fields": [],
  "type_mismatches": [],
  "unexpected_fields": [],
  "value_issues": [],
  "confidence_score": 1.0,
  "validation_source": "rule_based",
  "notes": null,
  "cached": false
}
```

`validation_source` is one of: `rule_based`, `llm`, `hybrid`.

### `GET /health`

Liveness: `status`, `service`, `version`, `llm_configured`.

### `POST /validate/batch`

Body: `{ "items": [ /* ValidateRequest, ... */ ] }` (capped by `BATCH_MAX_ITEMS`). Per-item OpenAPI/network errors are returned as `ValidationResult` rows with `value_issues` instead of failing the whole batch.

### `POST /validate/export`

Body:

```json
{
  "validation_request": { /* same fields as POST /validate */ },
  "format": "json"
}
```

`format` can be `json` or `csv`. Returns a downloadable attachment.

### `POST /run-test`

Executes one **APITestCase**: performs the HTTP call (`requests`, with retries), then validates the JSON body against the operation in the OpenAPI file named by `expected_swagger` (resolved under `specs/` and fallback dirs). Appends a report to **test history**.

**Example body** (see also `samples/test_cases/`):

```json
{
  "name": "Httpbin JSON GET",
  "method": "GET",
  "url": "https://httpbin.org/json",
  "headers": {},
  "body": null,
  "expected_swagger": "httpbin_get_json.json",
  "enable_ai_validation": false,
  "openapi_path": "/json",
  "openapi_method": "get"
}
```

**Response** (`TestExecutionReport`): `test_name`, `status` (`PASS` / `FAIL`), `validation` (same shape as `ValidationResult`), **`response_time_ms`** (milliseconds), `timestamp` (ISO-8601 UTC), `http_status`, optional `error`, `request_url`, `response_body_preview`.

When `skip_llm_on_structural_failure` is `true` (default), the hybrid engine **does not call the LLM** if rule-based validation already reports missing fields, type mismatches, or unexpected fields (saves cost; semantic `value_issues` alone can still trigger LLM).

### `POST /run-tests`

Body: `{ "tests": [ /* APITestCase */ ], "parallel": true }`. Bounded by `TEST_RUN_BATCH_MAX_ITEMS` and parallel concurrency `TEST_RUN_PARALLEL_MAX`. Each result is stored in history.

### `GET /test-history`

Query: `limit` (default 50, max 200). Returns newest reports first (JSON list).

### Web UI

After starting the server, open **http://127.0.0.1:8000/ui/** to paste test JSON, call `/run-test`, and view PASS/FAIL plus validation issues.

---

## Example (PowerShell) — `/validate`

```powershell
$spec = Get-Content -Raw samples/openapi_pet.json | ConvertFrom-Json
$body = @{
  openapi_spec = $spec
  path = "/pets/1"
  method = "get"
  status_code = "200"
  response_body = (Get-Content -Raw samples/sample_response_bad.json | ConvertFrom-Json)
  use_llm_semantic = $false
} | ConvertTo-Json -Depth 30
Invoke-RestMethod -Uri http://127.0.0.1:8000/validate -Method POST -Body $body -ContentType "application/json"
```

---

## Testing

```bash
pytest tests -q
```

Tests cover: validation API, rule engine, export, **mocked test runner**, and related edge cases.

### CI/CD (GitHub Actions)

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — on push/PR: install deps, `pytest`, then `python scripts/ci_smoke_test.py` (live **https://httpbin.org/json**). If outbound access is blocked in your org, remove or replace the smoke step with an in-process mock.

**Local smoke (same as CI):**

```bash
python scripts/ci_smoke_test.py
```

---

## Backward compatibility

Existing endpoints **`POST /validate`**, **`GET /health`**, **`POST /validate/batch`**, and **`POST /validate/export`** are unchanged. New routes and the `/ui` static mount are additive.

---

## Example (PowerShell) — `/run-test`

```powershell
$tc = Get-Content -Raw samples/test_cases/httpbin_json_get.json
Invoke-RestMethod -Uri http://127.0.0.1:8000/run-test -Method POST -Body $tc -ContentType "application/json"
```

---

<<<<<<< HEAD
## Deployment

### Docker

```bash
docker build -t ai-api-validation-engine .
docker run -p 8000:8000 -e OPENAI_API_KEY=... ai-api-validation-engine
```

The image runs `uvicorn app.main:app` on port **8000** (or `PORT` if set).

### Render / generic host

- **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health check path:** `/health`
- Inject **`OPENAI_API_KEY`** via secret manager.

---

## Security checklist

| Topic | What this project does |
|-------|-------------------------|
| **API keys** | Loaded from environment / `.env` via Pydantic Settings; never logged in full |
| **`.env`** | Listed in `.gitignore`; use `.env.example` as a template only |
| **Input validation** | Strict Pydantic models; 422 with structured `{ "error", "details" }` for bad bodies |
| **Prompt injection** | System prompt states SCHEMA/RESPONSE blocks are untrusted data; model instructed to ignore embedded “instructions” in JSON strings |
| **CORS** | Default `*` for dev; set **`CORS_ORIGINS`** to explicit origins in production |
| **Rate limiting** | Per-IP limit via SlowAPI (tune `RATE_LIMIT_PER_MINUTE`) |
| **Error leakage** | Unhandled exceptions return generic message unless `LOG_LEVEL=DEBUG` |
| **Sensitive payloads** | Treat OpenAPI specs and bodies as sensitive; logs use short schema previews where applicable |
| **Outbound HTTP from server** | `POST /run-test` issues real requests from the server process; restrict exposure (auth, network policy) in production |

---

## Bonus: simple UI suggestion

For internal tools, a minimal **static page** (or **Streamlit** / **Gradio**) with:

- File upload for OpenAPI JSON
- Text areas for path, method, status, and response JSON
- POST to `/validate` and render the result as tables for each issue list

Alternatively, use the built-in **Swagger UI** at `/docs` for quick manual calls.

---

## Screenshots (placeholders)

- **[Screenshot 1]** — Swagger UI at `http://127.0.0.1:8000/docs` showing `POST /validate`.
- **[Screenshot 2]** — Example `ValidationResult` with `validation_source: "hybrid"` after enabling the LLM pass.

---

=======
>>>>>>> 15cb08f111305397217fbd4ab1bebdb91e676c98
## License

MIT (adjust as needed for your organization).
