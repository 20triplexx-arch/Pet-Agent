"""Durable, atomic evaluation spending ceiling, independent of business transactions."""
import json
import sqlite3
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, UTC
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from uuid import uuid4


class BudgetExceeded(Exception):
    pass


class EvaluationBudget:
    def __init__(self, path, pricing, limit_cny="10"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pricing = pricing
        if pricing["currency"] != "CNY" or pricing["model"] != "deepseek-flash":
            raise ValueError("Unsupported evaluation pricing")
        checked = datetime.fromisoformat(pricing["checked_at"])
        age = (datetime.now(UTC) - checked).total_seconds()
        if not 0 <= age <= 86400:
            raise ValueError("Pricing must be verified within the last 24 hours")
        self.input_rate = Decimal(str(pricing["peak_input_cache_miss_per_million"]))
        self.output_rate = Decimal(str(pricing["peak_output_per_million"]))
        if self.input_rate <= 0 or self.output_rate <= 0:
            raise ValueError("Invalid pricing")
        limit = Decimal(str(limit_cny))
        if not Decimal("0") < limit <= Decimal("10"):
            raise ValueError("The authorized lifetime ceiling is 10 CNY")
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), limit_micro INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS charges (id TEXT PRIMARY KEY, amount_micro INTEGER NOT NULL, state TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER)")
            existing = db.execute("SELECT limit_micro FROM config WHERE id=1").fetchone()
            requested = int(limit * 1_000_000)
            if existing and requested > existing[0]:
                raise ValueError("An existing budget ceiling cannot be raised")
            db.execute("INSERT INTO config VALUES (1,?) ON CONFLICT(id) DO UPDATE SET limit_micro=excluded.limit_micro", (requested,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def cost(self, inputs, outputs):
        # Micro-CNY: peak tariff, no cache discount. Round upward.
        return int((Decimal(inputs) * self.input_rate + Decimal(outputs) * self.output_rate).to_integral_value(rounding=ROUND_CEILING))

    def reserve(self, request):
        if request.get("model") != self.pricing["model"] or request.get("stream"):
            raise ValueError("Budgeted evaluations require the verified non-streaming model")
        if request.get("extra_body", {}).get("thinking", {}).get("type") != "disabled":
            raise ValueError("Budgeted evaluations require thinking to be explicitly disabled")
        maximum = request.get("max_tokens") or request.get("max_completion_tokens")
        if not isinstance(maximum, int) or not 0 < maximum <= 1800:
            raise ValueError("A bounded output is required")
        # UTF-8 bytes upper-bound byte-tokenized prompt content. Include wire JSON,
        # tools and an additional 8192 tokens for protocol formatting overhead.
        payload = {k: v for k, v in request.items() if k in ("messages", "tools", "response_format")}
        inputs = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) + 8192
        amount = self.cost(inputs, maximum)
        ident = str(uuid4())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            limit = db.execute("SELECT limit_micro FROM config WHERE id=1").fetchone()[0]
            used = db.execute("SELECT COALESCE(SUM(amount_micro),0) FROM charges").fetchone()[0]
            if used + amount > limit:
                raise BudgetExceeded("Insufficient reserved evaluation budget")
            db.execute("INSERT INTO charges VALUES (?,?, 'reserved',NULL,NULL)", (ident, amount))
        return ident

    def settle(self, ident, usage):
        # Missing usage or transport failure retains the entire reservation:
        # the provider may already have billed a timed-out request.
        if usage is None:
            return
        inputs, outputs = usage.prompt_tokens, usage.completion_tokens
        if not isinstance(inputs, int) or not isinstance(outputs, int) or inputs < 0 or outputs < 0:
            return
        with self.connect() as db:
            reserved = db.execute("SELECT amount_micro FROM charges WHERE id=?", (ident,)).fetchone()[0]
            actual = self.cost(inputs, outputs)
            if actual > reserved:
                raise BudgetExceeded("Provider usage exceeded the reserved upper bound")
            db.execute("UPDATE charges SET amount_micro=?,state='usage_estimate',input_tokens=?,output_tokens=? WHERE id=?", (actual, inputs, outputs, ident))

    def summary(self):
        with self.connect() as db:
            limit = db.execute("SELECT limit_micro FROM config WHERE id=1").fetchone()[0]
            used, requests, unresolved = db.execute("SELECT COALESCE(SUM(amount_micro),0),COUNT(*),SUM(CASE WHEN state='reserved' THEN 1 ELSE 0 END) FROM charges").fetchone()
        return {"limit_cny": limit / 1e6, "conservative_used_cny": used / 1e6,
                "reserved_or_billed_requests": requests, "unresolved_reservations": unresolved or 0,
                "pricing": self.pricing, "billing_note": "Peak cache-miss estimate; unresolved requests retain full reservation. Not a provider invoice."}


current_budget: ContextVar[EvaluationBudget | None] = ContextVar("evaluation_budget", default=None)
