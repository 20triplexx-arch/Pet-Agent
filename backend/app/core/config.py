from pathlib import Path
import secrets
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
STORAGE = Path(__file__).resolve().parents[2] / "storage"
STORAGE.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    PROJECT_NAME: str = "宠伴"
    DATABASE_URL: str = f"sqlite:///{(STORAGE / 'chongban.db').as_posix()}"
    SECRET_KEY: str = Field(default="", repr=False)
    DEMO_MODE: bool = True
    MODEL_PROVIDER: Literal["compatible", "deepseek", "alibaba"] = "compatible"
    DEEPSEEK_API_KEY: str = Field(default="", repr=False)
    MODEL_API_KEY: str = Field(default="", repr=False)
    MODEL_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL_NAME: str = "qwen3.7-flash"
    DEEPSEEK_MODEL: str = "deepseek-flash"
    DASHSCOPE_API_KEY: str = Field(default="", repr=False)
    DASHSCOPE_WORKSPACE_ID: str = Field(default="", repr=False, pattern=r"^[a-zA-Z0-9_-]*$")
    DASHSCOPE_BASE_URL: str = ""
    DASHSCOPE_MODEL: str = "qwen3.7-flash"
    DASHSCOPE_AUTO_SELECT: bool = False
    DASHSCOPE_FREE_ONLY: bool = True
    DASHSCOPE_FREE_MODELS: str = "auto"
    DASHSCOPE_QUOTA_FILE: str = str(STORAGE / 'alibaba-quota.json')
    DASHSCOPE_QUALIFIED_FILE: str = str(STORAGE / 'alibaba-qualified.json')
    DASHSCOPE_QUOTA_MAX_AGE_SECONDS: int = Field(default=180, ge=60, le=300)
    DASHSCOPE_CLI: str = ""
    DASHSCOPE_CLI_CONFIG_DIR: str = str(STORAGE / 'bailian-cli')
    DASHSCOPE_CLI_PROFILE: str = 'chongban-quota'
    MODEL_LIMITS_ENABLED: bool = True
    # Accept the previous six-request setting; the runtime caps each turn at four.
    MODEL_MAX_REQUESTS: int = Field(default=4, ge=1, le=6)
    MODEL_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=128, le=16384)
    MODEL_MAX_INPUT_TOKENS: int = Field(default=32000, ge=4096, le=131072)
    MODEL_CONTEXT_CHARS: int = Field(default=48000, ge=16000, le=200000)
    MODEL_TIMEOUT_SECONDS: int = Field(default=90, ge=5, le=180)
    MODEL_TURNS_PER_DAY: int = Field(default=20, ge=0, le=10000)
    AMAP_ENABLED: bool = False
    AMAP_API_KEY: str = Field(default="", repr=False)
    MAP_REQUESTS_PER_DAY: int = 50
    MAP_REQUESTS_PER_MONTH: int = 500
    HOSPITAL_MAP_PROVIDER: Literal["amap", "tianditu"] = "amap"
    TIANDITU_ENABLED: bool = False
    TIANDITU_API_KEY: str = Field(default="", repr=False)
    TIANDITU_REQUESTS_PER_DAY: int = Field(default=50, ge=0, le=100000)
    TIANDITU_REQUESTS_PER_MONTH: int = Field(default=500, ge=0, le=1000000)
    OCR_ENABLED: bool = True
    OCR_TIMEOUT_SECONDS: int = 30
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    API_V1_STR: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    EXECUTION_LOG_PATH: str = str(STORAGE / "execution.jsonl")

    @property
    def model_key(self) -> str:
        if self.MODEL_PROVIDER == "alibaba":
            return self.DASHSCOPE_API_KEY
        return self.DEEPSEEK_API_KEY if self.MODEL_PROVIDER == "deepseek" else self.MODEL_API_KEY

    @property
    def model_name(self) -> str:
        if self.MODEL_PROVIDER == "alibaba":
            return self.DASHSCOPE_MODEL
        return self.DEEPSEEK_MODEL if self.MODEL_PROVIDER == "deepseek" else self.MODEL_NAME

    @property
    def dashscope_url(self) -> str:
        if self.DASHSCOPE_BASE_URL.strip():
            return self.DASHSCOPE_BASE_URL.strip().rstrip("/")
        if self.DASHSCOPE_WORKSPACE_ID:
            return f"https://{self.DASHSCOPE_WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @property
    def model_mode(self) -> str:
        if self.DEMO_MODE:
            return "demo"
        return "live" if self.model_key else "configuration_error"


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
