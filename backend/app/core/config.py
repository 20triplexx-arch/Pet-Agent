from pathlib import Path
import secrets
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
STORAGE = Path(__file__).resolve().parents[2] / "storage"
STORAGE.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    PROJECT_NAME: str = "宠伴"
    DATABASE_URL: str = f"sqlite:///{(STORAGE / 'chongban.db').as_posix()}"
    SECRET_KEY: str = ""
    DEMO_MODE: bool = True
    MODEL_API_KEY: str = ""
    MODEL_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL_NAME: str = "qwen3.7-flash"
    MODEL_MAX_REQUESTS: int = Field(default=4, ge=1, le=4)
    MODEL_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=128, le=16384)
    MODEL_MAX_INPUT_TOKENS: int = Field(default=32000, ge=4096, le=131072)
    MODEL_CONTEXT_CHARS: int = Field(default=48000, ge=16000, le=200000)
    MODEL_TIMEOUT_SECONDS: int = Field(default=90, ge=5, le=180)
    MODEL_TURNS_PER_DAY: int = Field(default=20, ge=0, le=10000)
    AMAP_ENABLED: bool = False
    AMAP_API_KEY: str = ""
    MAP_REQUESTS_PER_DAY: int = 50
    MAP_REQUESTS_PER_MONTH: int = 500
    OCR_ENABLED: bool = True
    OCR_TIMEOUT_SECONDS: int = 30
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    API_V1_STR: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440


settings = Settings()
if not settings.SECRET_KEY:
    key_file = STORAGE / ".secret"
    if not key_file.exists():
        try:
            with key_file.open("x", encoding="utf-8") as f:
                f.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
    settings.SECRET_KEY = key_file.read_text(encoding="utf-8").strip()
