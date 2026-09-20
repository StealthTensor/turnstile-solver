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

## CI/CD and Container Registry

On push to `main`, GitHub Actions automatically builds and publishes the Docker image to GitHub Container Registry:
`ghcr.io/stealthtensor/turnstile-solver:latest`

## Railway Deployment (Zero GitHub Connection Needed)

1. Go to [Railway Dashboard](https://railway.app/).
2. Click **+ New Project** $\rightarrow$ **Deploy from Docker Image**.
3. Enter the image:
   ```text
   ghcr.io/stealthtensor/turnstile-solver:latest
   ```
4. In Railway project settings:
   - **Networking**: Click **Generate Domain** (e.g. `https://turnstile-solver-production.up.railway.app`).
   - **Variables**: Set `SOLVER_SECRET="@Ethical_Hacker1"`.
   - **Port**: Set `PORT="8080"` (default).
5. Done! The service is live and ready to be called by `lpu-worker`.

> **Note on GHCR Package Visibility:**  
> On GitHub: Go to repository **Packages** $\rightarrow$ `turnstile-solver` $\rightarrow$ **Package Settings** $\rightarrow$ change visibility to **Public** so Railway can pull without Docker registry credentials.
