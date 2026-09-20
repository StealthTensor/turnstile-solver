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
  <script>
    window.turnstileToken = "";
    window.turnstileError = "";
    function onSuccess(token) {
      console.log("[Turnstile] onSuccess called");
      window.turnstileToken = token;
    }
    function onError(code) {
      console.error("[Turnstile] onError called:", code);
      window.turnstileError = String(code);
    }
    function onExpired() {
      window.turnstileToken = "";
    }
  </script>
  <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
</head>
<body style="margin:0;display:flex;justify-content:center;align-items:center;height:100vh;background:#fafafa;">
  <div class="cf-turnstile"
       id="cf-turnstile"
       data-sitekey="__SITE_KEY__"
       data-callback="onSuccess"
       data-error-callback="onError"
       data-expired-callback="onExpired"></div>
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
                    "--enable-unsafe-swiftshader",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            context = await browser.new_context(
                locale="en-US",
                timezone_id="Asia/Kolkata",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()

            console_logs = []
            failed_requests = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: console_logs.append(f"[pageerror] {err}"))
            page.on("requestfailed", lambda r: failed_requests.append(f"{r.url}: {r.failure}"))

            # Intercept genuine domain request, fulfill with local widget under genuine origin
            async def handle_route(route):
                if route.request.resource_type == "document":
                    html = HTML_TEMPLATE.replace("__SITE_KEY__", req.site_key)
                    await route.fulfill(
                        status=200,
                        headers={"content-type": "text/html; charset=utf-8"},
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
            eval_res = {}
            max_polls = int(req.timeout_seconds * 2)
            for i in range(max_polls):
                # Fallback: if turnstile API loaded but hasn't rendered into div, trigger render
                if i == 3:
                    await page.evaluate("""() => {
                        if (window.turnstile && !window.turnstileToken && !window.turnstileManualRendered) {
                            window.turnstileManualRendered = true;
                            try {
                                const el = document.getElementById('cf-turnstile') || document.querySelector('.cf-turnstile');
                                if (el && !el.shadowRoot) {
                                    window.turnstile.render(el, {
                                        sitekey: '__SITE_KEY__',
                                        callback: function(t) { window.turnstileToken = t; },
                                        'error-callback': function(e) { window.turnstileError = String(e); }
                                    });
                                }
                            } catch(e) { console.error('[Turnstile] manual render failed:', e); }
                        }
                    }""".replace("__SITE_KEY__", req.site_key))

                eval_res = await page.evaluate("""() => {
                    const el = document.getElementById('cf-turnstile') || document.querySelector('.cf-turnstile');
                    return {
                        token: window.turnstileToken ||
                               document.querySelector('[name="cf-turnstile-response"]')?.value ||
                               document.querySelector('input[name="g-recaptcha-response"]')?.value ||
                               "",
                        error: window.turnstileError || "",
                        hasTurnstile: typeof window.turnstile !== "undefined",
                        hasShadow: Boolean(el && el.shadowRoot),
                        iframes: document.querySelectorAll('iframe').length
                    };
                }""")

                token = eval_res.get("token")
                err_code = eval_res.get("error")

                if token and len(token) > 20:
                    break

                if err_code:
                    logger.error(f"Turnstile error callback: {err_code}, console: {console_logs}")
                    await browser.close()
                    browser = None
                    raise HTTPException(status_code=400, detail={
                        "error": f"Turnstile error: {err_code}",
                        "console": console_logs[-5:],
                    })

                # Interactive challenge handling: click checkbox
                if i in (2, 4, 7, 10, 14):
                    try:
                        clicked = False
                        for frame in page.frames:
                            if "challenges.cloudflare.com" in frame.url:
                                cb = await frame.query_selector("input[type=checkbox], #challenge-stage, .ctp-checkbox-label, body")
                                if cb:
                                    await cb.click(timeout=1000)
                                    logger.info(f"Clicked in frame: {frame.url[:45]}")
                                    clicked = True
                                    break
                        if not clicked:
                            widget = await page.query_selector(".cf-turnstile, #cf-turnstile")
                            if widget:
                                box = await widget.bounding_box()
                                if box and box["width"] > 0 and box["height"] > 0:
                                    await page.mouse.click(box["x"] + 30, box["y"] + box["height"] / 2)
                                    logger.info(f"Clicked widget at {box['x'] + 30}, {box['y'] + box['height'] / 2}")
                    except Exception as click_err:
                        logger.debug(f"Click attempt {i}: {click_err}")

                await asyncio.sleep(0.5)

            await browser.close()
            browser = None

            if not token:
                cf_frames = [f.url for f in page.frames if "challenges.cloudflare.com" in f.url]
                logger.warning(f"Turnstile solve timed out after {time.time() - t0:.2f}s: {eval_res}, console: {console_logs}")
                raise HTTPException(status_code=504, detail={
                    "message": "Turnstile solve timed out",
                    "state": eval_res,
                    "cf_frames": len(cf_frames),
                    "console": console_logs[-10:],
                    "failed_requests": failed_requests[-5:],
                })

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

