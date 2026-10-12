"""Request-scoped metadata only; never logs prompts, tool values or provider errors."""
import json
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from uuid import uuid4

log = logging.getLogger("chongban.execution")


def configure_logging(path):
    if not log.handlers:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)


@dataclass
class Execution:
    request_id: str = field(default_factory=lambda: str(uuid4()))
    started: float = field(default_factory=time.perf_counter)
    model_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tools: list = field(default_factory=list)
    retrieval: dict = field(default_factory=dict)
    mode: str | None = None
    error_type: str | None = None
    replayed: bool = False

    def retrieved(self, articles):
        for article in articles.values():
            self.retrieval[article["id"]] = {
                "id": article["id"], "source_version": article["source_version"],
                "updated_at": article["updated_at"],
            }

    def summary(self):
        return {
            "request_id": self.request_id, "mode": self.mode,
            "model_requests": self.model_requests,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "retrieval": list(self.retrieval.values()), "tools": list(self.tools),
            "error_type": self.error_type, "replayed": self.replayed,
        }


current_execution: ContextVar[Execution | None] = ContextVar("execution", default=None)
current_tool: ContextVar[str | None] = ContextVar("execution_tool", default=None)


def traced_tool(fn):
    @wraps(fn)
    def wrapped(ctx, *args, **kwargs):
        name = fn.__name__.removeprefix("tool_")
        if current_tool.get() == name:
            return fn(ctx, *args, **kwargs)
        trace = current_execution.get()
        token = current_tool.set(name)
        started = time.perf_counter()
        event = {"name": name, "status": "failed"}
        try:
            value = fn(ctx, *args, **kwargs)
            event["status"] = "succeeded"
            return value
        except Exception as exc:
            event["error_type"] = type(exc).__name__
            raise
        finally:
            current_tool.reset(token)
            if trace:
                event["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                trace.tools.append(event)
                trace.retrieved(getattr(ctx, "deps", ctx).retrieved)
    return wrapped


class ExecutionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (scope["path"].startswith("/api/") or scope["path"] == "/health"):
            return await self.app(scope, receive, send)
        trace = Execution()
        token = current_execution.set(trace)
        status = 500

        async def traced_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []), (b"x-request-id", trace.request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        except Exception as exc:
            trace.error_type = type(exc).__name__
            raise
        finally:
            log.info(json.dumps({**trace.summary(), "http_status": status}, ensure_ascii=True))
            current_execution.reset(token)
