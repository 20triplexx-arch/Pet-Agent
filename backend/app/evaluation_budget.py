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
    def __init__(self, path, pricing, limit_cny="10", *, run_id=None, run_limit_cny=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pricing = pricing
        from app.alibaba_models import family
        group = family(pricing['model'])
        bounds = {'qwen3.7-flash':[32768, 262144, 1000000], 'qwen3.8-flash':[1000000],
                  'qwen-flash':[131072, 262144, 1000000], 'qwen3.5-flash':[131072, 262144, 1000000],
                  'qwen3.6-flash':[262144, 1000000], 'qwen3.7-plus':[262144, 1000000], 'qwen3.7-max':[1000000]}
        if pricing["currency"] != "CNY" or (pricing['model'] != 'deepseek-flash' and group not in bounds):
            raise ValueError("Unsupported evaluation pricing")
        checked = datetime.fromisoformat(pricing["checked_at"])
        age = (datetime.now(UTC) - checked).total_seconds()
        if not 0 <= age <= 86400:
            raise ValueError("Pricing must be verified within the last 24 hours")
        self.provider = "alibaba" if pricing["model"].startswith('qwen') else "deepseek"
        self.output_token_limit = 4096 if self.provider == "alibaba" else 1800
        if self.provider == "alibaba":
            tiers = pricing.get("tiers", [])
            expected = bounds[group]
            if [t.get("max_input_tokens") for t in tiers] != expected:
                raise ValueError("Verified Alibaba input tiers are required")
        else:
            tiers = [{"max_input_tokens": 1000000, "input_per_million": pricing["peak_input_cache_miss_per_million"],
                      "output_per_million": pricing["peak_output_per_million"]}]
        self.tiers = tiers
        if any(Decimal(str(t[k])) <= 0 for t in tiers for k in ("input_per_million", "output_per_million")):
            raise ValueError("Invalid pricing")
        self.run_id = run_id
        if (run_id is None) != (run_limit_cny is None):
            raise ValueError("Run ID and ceiling must be supplied together")
        run_limit = Decimal(str(run_limit_cny)) if run_id is not None else None
        if run_limit is not None and not Decimal("0") < run_limit <= Decimal("3"):
            raise ValueError("The authorized run ceiling is 3 CNY")
        limit = Decimal(str(limit_cny))
        if not Decimal("0") < limit <= Decimal("10"):
            raise ValueError("The authorized lifetime ceiling is 10 CNY")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), limit_micro INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS charges (id TEXT PRIMARY KEY, amount_micro INTEGER NOT NULL, state TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER)")
            # Additive migration: never delete/reprice historical charges or reservations.
            columns = {r[1] for r in db.execute("PRAGMA table_info(charges)")}
            for name in ("provider", "model", "run_id", "pricing_json"):
                if name not in columns:
                    db.execute(f"ALTER TABLE charges ADD COLUMN {name} TEXT")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, limit_micro INTEGER NOT NULL)")
            existing = db.execute("SELECT limit_micro FROM config WHERE id=1").fetchone()
            requested = int(limit * 1_000_000)
            if existing and requested > existing[0]:
                raise ValueError("An existing budget ceiling cannot be raised")
            db.execute("INSERT INTO config VALUES (1,?) ON CONFLICT(id) DO UPDATE SET limit_micro=excluded.limit_micro", (requested,))
            if self.run_id is not None:
                previous = db.execute("SELECT limit_micro FROM runs WHERE id=?", (self.run_id,)).fetchone()
                requested_run = int(run_limit * 1_000_000)
                if previous and requested_run > previous[0]:
                    raise ValueError("An existing run ceiling cannot be raised")
                db.execute("INSERT INTO runs VALUES (?,?) ON CONFLICT(id) DO UPDATE SET limit_micro=excluded.limit_micro", (self.run_id, requested_run))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def cost(self, inputs, outputs, *, pricing=None):
        # Micro-CNY: peak tariff, no cache discount. Round upward.
        tiers = self.tiers if pricing is None else pricing.get("tiers", [{"max_input_tokens": 1000000,
            "input_per_million": pricing.get("peak_input_cache_miss_per_million"),
            "output_per_million": pricing.get("peak_output_per_million")}])
        tier = next((t for t in tiers if inputs <= t["max_input_tokens"]), None)
        if tier is None:
            raise ValueError("Input exceeds the verified tariff")
        return int((Decimal(inputs) * Decimal(str(tier["input_per_million"])) +
                    Decimal(outputs) * Decimal(str(tier["output_per_million"]))).to_integral_value(rounding=ROUND_CEILING))

    def reserve(self, request):
        if request.get("model") != self.pricing["model"]:
            raise ValueError("Budgeted evaluations require the verified model")
        if request.get('stream') and request.get('stream_options', {}).get('include_usage') is not True:
            raise ValueError('Streaming evaluations require usage reporting')
        extra = request.get("extra_body", {})
        disabled = extra.get("enable_thinking") is False if self.provider == "alibaba" else extra.get("thinking", {}).get("type") == "disabled"
        if not disabled:
            raise ValueError("Budgeted evaluations require thinking to be explicitly disabled")
        maximum = request.get("max_tokens") or request.get("max_completion_tokens")
        if type(maximum) is not int or not 0 < maximum <= self.output_token_limit:
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
            if self.run_id is not None:
                run_limit = db.execute("SELECT limit_micro FROM runs WHERE id=?", (self.run_id,)).fetchone()[0]
                run_used = db.execute("SELECT COALESCE(SUM(amount_micro),0) FROM charges WHERE run_id=?", (self.run_id,)).fetchone()[0]
                if run_used + amount > run_limit:
                    raise BudgetExceeded("Insufficient reserved run budget")
            db.execute("INSERT INTO charges (id,amount_micro,state,provider,model,run_id,pricing_json) VALUES (?,?,'reserved',?,?,?,?)",
                       (ident, amount, self.provider, self.pricing["model"], self.run_id, json.dumps(self.pricing)))
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
            row = db.execute("SELECT amount_micro,model,pricing_json FROM charges WHERE id=?", (ident,)).fetchone()
            if not row or row[1] != self.pricing["model"]:
                raise ValueError("Reservation pricing does not match")
            reserved = row[0]
            actual = self.cost(inputs, outputs, pricing=json.loads(row[2]))
            if actual > reserved:
                raise BudgetExceeded("Provider usage exceeded the reserved upper bound")
            db.execute("UPDATE charges SET amount_micro=?,state='usage_estimate',input_tokens=?,output_tokens=? WHERE id=?", (actual, inputs, outputs, ident))

    def summary(self):
        with self.connect() as db:
            limit = db.execute("SELECT limit_micro FROM config WHERE id=1").fetchone()[0]
            used, requests, unresolved = db.execute("SELECT COALESCE(SUM(amount_micro),0),COUNT(*),SUM(CASE WHEN state='reserved' THEN 1 ELSE 0 END) FROM charges").fetchone()
            run = db.execute("SELECT limit_micro FROM runs WHERE id=?", (self.run_id,)).fetchone()
            run_used = db.execute("SELECT COALESCE(SUM(amount_micro),0) FROM charges WHERE run_id=?", (self.run_id,)).fetchone()[0]
        return {"limit_cny": limit / 1e6, "conservative_used_cny": used / 1e6,
                "run_id": self.run_id, "run_limit_cny": run[0] / 1e6 if run else None, "run_used_cny": run_used / 1e6,
                "reserved_or_billed_requests": requests, "unresolved_reservations": unresolved or 0,
                "pricing": self.pricing, "billing_note": "Peak cache-miss estimate; unresolved requests retain full reservation. Not a provider invoice."}


current_budget: ContextVar[EvaluationBudget | None] = ContextVar("evaluation_budget", default=None)
