# Turnstile Solver Sidecar

Lightweight Cloudflare Turnstile token solving sidecar powered by FastAPI and Patchright with genuine-origin route interception.

## Architecture

- Intercepts requests for `site_url` to serve the Turnstile widget directly under the genuine domain origin without hitting upstream servers or triggering WAF blocks.
- Solves managed/invisible Turnstile widgets in ~1.5 - 2.5s.
- Returns valid `cf-turnstile-response` token via REST API.

## API Endpoints

### 1. `GET /health`
Returns service health status.
```json
{
  "status": "ok",
  "service": "turnstile-solver"
}
```

### 2. `POST /solve`
Solves Cloudflare Turnstile for the given site and key.

**Headers:**
- `Content-Type: application/json`
- `X-Secret: @Ethical_Hacker1` (or your configured `SOLVER_SECRET`)

**Request Body:**
```json
{
  "site_url": "https://ums.lpu.in/lpuums/LoginNew.aspx",
  "site_key": "0x4AAAAAABqizXa69CuLKKuQ",
  "timeout_seconds": 15
}
```

**Response:**
```json
{
  "ok": true,
  "token": "0.XnF...",
  "elapsed_ms": 1820
}
```
