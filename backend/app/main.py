from pathlib import Path
import math
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from app.api.routes import router
from app.api.care_routes import router as care_router
from app.api.product_routes import router as product_router
from app.core.config import settings

app = FastAPI(title="宠伴", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(care_router)
app.include_router(product_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        if isinstance(value, Exception):
            return str(value)
        return value
    # Never echo packaging, credentials or raw multipart images in validation errors.
    errors = [{k: clean(v) for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


class BoundedOCRUpload:
    """Bound multipart bodies before parsing, including chunked transfers."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/api/v1/products/ocr" and scope.get("method") == "POST":
            messages, size = [], 0
            while True:
                msg = await receive()
                if msg["type"] == "http.disconnect":
                    return
                size += len(msg.get("body", b""))
                if size > 16 * 1024 * 1024:
                    await JSONResponse({"detail": "本次图片请求最多16 MB"}, status_code=413)(scope, receive, send)
                    return
                messages.append(msg)
                if not msg.get("more_body", False):
                    break
            it = iter(messages)
            async def bounded_receive():
                return next(it, {"type": "http.request", "body": b"", "more_body": False})
            await self.app(scope, bounded_receive, send)
        else:
            await self.app(scope, receive, send)


app.add_middleware(BoundedOCRUpload)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": "demo" if settings.DEMO_MODE or not settings.MODEL_API_KEY else "live",
    }


dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
# Docker copies frontend into backend/frontend/dist; local development uses Vite.
if not dist.exists():
    dist = Path(__file__).resolve().parents[2].parent / "frontend" / "dist"


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/"):
                return await super().get_response("index.html", scope)
            raise


if dist.exists():
    app.mount("/", SPAFiles(directory=dist, html=True), name="frontend")
