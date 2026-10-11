from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.routes import router
from app.api.care_routes import router as care_router
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
