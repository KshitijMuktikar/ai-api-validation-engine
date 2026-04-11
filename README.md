# AI-Powered API Validation Engine

Production-oriented **FastAPI** service that validates a JSON API response against an **OpenAPI 3.x** response schema using **OpenAI** LLMs. It reports missing fields, type mismatches, unexpected fields, and obvious value violations.

## Features

- OpenAPI 3.x parsing with **`$ref`** resolution under `#/`
- Path template matching (`/pets/{petId}` ↔ `/pets/1`)
- **`POST /validate`** — structured LLM analysis with JSON output
- **`GET /health`** — load balancer friendly
- Centralized **logging** (stdout)
- **Dockerfile** for container deployment

## Requirements

- Python **3.10+** recommended (3.12 in Docker)
- **OpenAI API key** with access to the configured model (default: `gpt-4o-mini`)

> **Note:** This project expects **OpenAPI 3.x**. Swagger 2.0 specs should be converted to OAS3 first.

## Quick start

```bash
cd ai-api-validation-engine
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
copy .env.example .env     # Windows — then edit OPENAI_API_KEY
# cp .env.example .env && nano .env

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://127.0.0.1:8000/docs** for interactive Swagger UI.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | **Yes** (for `/validate`) | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Chat completion model |
| `OPENAI_TIMEOUT_SECONDS` | No | `60` | OpenAI client timeout |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## API

### `POST /validate`

**Request body** (`application/json`):

| Field | Type | Description |
|-------|------|-------------|
| `openapi_spec` | object | Full OpenAPI 3 JSON (optional if `openapi_spec_url` set) |
| `openapi_spec_url` | string | HTTPS URL returning OpenAPI JSON (optional if `openapi_spec` set) |
| `path` | string | Path as in the spec, e.g. `/pets/1` |
| `method` | string | Lowercase HTTP method, e.g. `get` |
| `status_code` | string | Response key, e.g. `200` |
| `response_body` | any | Actual JSON body to validate |
| `include_schema_in_prompt` | boolean | Default `true`; include resolved schema in LLM context |

**Response** (`application/json`):

```json
{
  "missing_fields": [],
  "type_mismatches": [],
  "unexpected_fields": [],
  "value_issues": [],
  "notes": null
}
```

### `GET /health`

Returns `{ "status": "ok", "service": "ai-api-validation-engine" }`.

## Example (curl)

From the project root, with the server running and `.env` configured:

**Windows PowerShell** (inline spec via file):

```powershell
$spec = Get-Content -Raw samples/openapi_pet.json | ConvertFrom-Json
$body = @{
  openapi_spec = $spec
  path = "/pets/1"
  method = "get"
  status_code = "200"
  response_body = (Get-Content -Raw samples/sample_response_bad.json | ConvertFrom-Json)
} | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri http://127.0.0.1:8000/validate -Method POST -Body $body -ContentType "application/json"
```

**bash** (using `jq` if available):

```bash
curl -s -X POST http://127.0.0.1:8000/validate \
  -H "Content-Type: application/json" \
  -d @- <<'EOF'
{
  "openapi_spec": $(cat samples/openapi_pet.json),
  ...
}
EOF
```

Simplest cross-platform approach: use **Postman** or paste JSON into **http://127.0.0.1:8000/docs**.

Example minimal JSON body (paste into Swagger UI “Try it out”):

```json
{
  "openapi_spec": { "openapi": "3.0.3", "info": { "title": "T", "version": "1" }, "paths": {}, "components": { "schemas": {} } }
}
```

Use the real file `samples/openapi_pet.json` as the value of `openapi_spec` in your client.

## Project layout

```
ai-api-validation-engine/
├── main.py                 # FastAPI app, routes
├── swagger_parser.py       # OpenAPI load, $ref, schema extraction
├── validator.py            # LLM prompts + OpenAI call
├── schemas.py              # Pydantic request/response models
├── config.py               # Settings from env
├── logging_config.py       # Logging setup
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
├── README.md
└── samples/
    ├── openapi_pet.json
    ├── sample_response_ok.json
    └── sample_response_bad.json
```

## Deployment

### Render

1. Push this folder to a Git repository.
2. In Render: **New → Web Service**, connect the repo.
3. **Runtime:** Docker (use the included `Dockerfile`) *or* Native:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variable **`OPENAI_API_KEY`** (and optional `OPENAI_MODEL`).
5. Deploy; use the generated **`https://<service>.onrender.com`** URL. **`GET /health`** confirms the service is up; **`POST /validate`** is your public endpoint.

### AWS (high level)

- **ECS Fargate** + **Application Load Balancer**: build and push the Docker image to **ECR**, define task with port **8000**, set secrets in **SSM/Secrets Manager** for `OPENAI_API_KEY`, target group health check on **`/health`**.
- **Lambda + API Gateway** is possible with **Mangum** or container images; this repo is optimized for long-lived **uvicorn** processes.

## Security

- Do not commit **`.env`** or real API keys.
- In production, restrict **CORS** (`main.py`) to your frontend origin instead of `*`.
- Treat uploaded OpenAPI specs and response bodies as **sensitive** if they contain secrets; log only previews (this app already truncates schema in logs).

## License

MIT (adjust as needed for your organization).
