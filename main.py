import os
import time
import asyncio
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from patchright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("turnstile-solver")

app = FastAPI(title="Turnstile Solver Sidecar")

SOLVER_SECRET = os.getenv("SOLVER_SECRET", "@Ethical_Hacker1")

class SolveRequest(BaseModel):
    site_url: str = "https://ums.lpu.in/lpuums/LoginNew.aspx"
    site_key: str = "0x4AAAAAABqizXa69CuLKKuQ"
    timeout_seconds: int = 15

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Turnstile</title>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</head>
<body style="margin:0;display:flex;justify-content:center;align-items:center;height:100vh;background:#fafafa;">
  <div class="cf-turnstile" data-sitekey="__SITE_KEY__" data-callback="onSuccess"></div>
  <script>
    window.turnstileToken = "";
    function onSuccess(token) {
      window.turnstileToken = token;
    }
  </script>
</body>
</html>"""

@app.get("/health")
def health():
    return {"status": "ok", "service": "turnstile-solver"}

@app.post("/solve")
async def solve(req: SolveRequest, x_secret: Optional[str] = Header(default="")):
    if SOLVER_SECRET and x_secret != SOLVER_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    t0 = time.time()
    logger.info(f"Solving Turnstile for {req.site_url} with key {req.site_key[:12]}...")

    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            # Intercept genuine domain request, fulfill with local widget under genuine origin
            async def handle_route(route):
                if route.request.resource_type == "document":
                    html = HTML_TEMPLATE.replace("__SITE_KEY__", req.site_key)
                    await route.fulfill(
                        status=200,
                        content_type="text/html",
                        body=html,
                    )
                else:
                    await route.continue_()

            await page.route(f"{req.site_url}*", handle_route)

            try:
                await page.goto(req.site_url, timeout=req.timeout_seconds * 1000)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Navigation failed: {str(e)}")

            token = None
            max_polls = int(req.timeout_seconds * 2)
            for i in range(max_polls):
                token = await page.evaluate("window.turnstileToken")
                if token and len(token) > 20:
                    break

                # If interactive challenge, click bounding box of widget
                if i in (4, 8, 14):
                    try:
                        widget = await page.query_selector(".cf-turnstile iframe, iframe, .cf-turnstile")
                        if widget:
                            box = await widget.bounding_box()
                            if box:
                                await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                    except Exception:
                        pass

                await asyncio.sleep(0.5)

            await browser.close()
            browser = None

            if not token:
                logger.warning(f"Turnstile solve timed out after {time.time() - t0:.2f}s")
                raise HTTPException(status_code=504, detail="Turnstile solve timed out")

            elapsed = round((time.time() - t0) * 1000)
            logger.info(f"Turnstile solved successfully in {elapsed}ms")
            return {"ok": True, "token": token, "elapsed_ms": elapsed}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Solve exception")
        raise HTTPException(status_code=500, detail=f"Solver error: {str(e)}")
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

