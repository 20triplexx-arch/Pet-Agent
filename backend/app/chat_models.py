"""Server-owned model choices; clients cannot supply model names, URLs or keys."""
from dataclasses import dataclass, field
from typing import Literal
from app.core.config import settings

ModelId = Literal["default", "demo", "deepseek", "compatible", "alibaba", "alibaba-auto"]


@dataclass(frozen=True)
class ModelSelection:
    id: str
    name: str
    provider: str | None
    key: str = field(repr=False)
    base_url: str = field(repr=False)

    @property
    def demo(self):
        return self.id == "demo"

    def public(self):
        prefixes = {"deepseek": "DeepSeek · ", "alibaba": "阿里千问 · ", "compatible": "兼容接口 · "}
        label = "演示模式 · 本地" if self.demo else prefixes[self.provider] + self.name
        available = self.demo or bool(self.key)
        reason = None
        if self.id == 'alibaba-auto':
            label = '阿里千问 · 免费优先（自动）'
        if self.provider == 'alibaba' and self.key and settings.DASHSCOPE_FREE_ONLY:
            from app.alibaba_quota import available_models
            available = self.name in available_models(qualified=self.id == 'alibaba-auto')
            if not available:
                reason = '免费额度或质量验证待核对'
        return {"id": self.id, "name": self.name, "label": label, "provider": self.provider,
                "available": available, "mode": "demo" if self.demo else "live" if available else "configuration_error",
                **({'availability_reason': reason} if reason else {})}


def select_model(model_id: ModelId = "default"):
    if model_id == "default":
        model_id = "demo" if settings.DEMO_MODE else settings.MODEL_PROVIDER
        if model_id == 'alibaba' and settings.DASHSCOPE_AUTO_SELECT:
            model_id = 'alibaba-auto'
    if model_id == "demo":
        return ModelSelection("demo", "本地演示", None, "", "")
    if model_id == "deepseek":
        return ModelSelection("deepseek", settings.DEEPSEEK_MODEL, "deepseek", settings.DEEPSEEK_API_KEY, "https://api.deepseek.com")
    if model_id == "alibaba":
        return ModelSelection("alibaba", settings.DASHSCOPE_MODEL, "alibaba", settings.DASHSCOPE_API_KEY, settings.dashscope_url)
    if model_id == 'alibaba-auto':
        from app.alibaba_quota import available_models, configured_models
        options = available_models()
        name = options[0] if options else (configured_models() or ['未找到免费模型'])[0]
        return ModelSelection('alibaba-auto', name, 'alibaba', settings.DASHSCOPE_API_KEY, settings.dashscope_url)
    if model_id == "compatible":
        return ModelSelection("compatible", settings.MODEL_NAME, "compatible", settings.MODEL_API_KEY, settings.MODEL_BASE_URL)
    raise ValueError("Unknown server model choice")


def catalog():
    return {"default_id": select_model().id,
            "options": [select_model(model_id).public() for model_id in ("demo", "alibaba-auto", "alibaba", "deepseek", "compatible")]}
