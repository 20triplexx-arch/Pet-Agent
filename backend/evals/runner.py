import argparse
from collections import Counter
from datetime import datetime, UTC
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from unittest.mock import patch

HERE = Path(__file__).parent
BACKEND = HERE.parent
ROOT = BACKEND.parent


def load_cases():
    raw = (HERE / "cases.v1.json").read_bytes()
    dataset = json.loads(raw)
    cases = dataset["cases"]
    assert len(cases) == 100 and len({c["id"] for c in cases}) == 100
    assert sum(bool(c.get("smoke")) for c in cases) == 10
    return dataset, hashlib.sha256(raw).hexdigest()


def verify_pricing():
    """Check the actual official CNY table; no paid calls when prices are unknown."""
    import urllib.request
    from html import unescape
    url = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    page = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
    tables = re.findall(r"<table.*?</table>", page, re.S)
    if len(tables) != 1:
        raise ValueError("Cannot verify the official pricing table")
    rows = []
    for row in re.findall(r"<tr.*?</tr>", tables[0], re.S):
        cells = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
                 for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        rows.append(cells)
    # Explicitly validate the Flash columns and both peak tariff rows. A changed
    # layout or tariff fails closed instead of guessing a cheap replacement.
    flat = " ".join(" ".join(row) for row in rows)
    if "deepseek-flash" not in flat or "2元" not in flat or "8元" not in flat:
        raise ValueError("Official tariff changed; update the verified pricing parser")
    input_row = next((r for r in rows if "高峰时段" in r and "2元" in r), None)
    output_row = next((r for r in rows if "高峰时段" in r and "8元" in r), None)
    if input_row is None or output_row is None or input_row.index("2元") != output_row.index("8元"):
        raise ValueError("Could not verify matching Flash peak input/output columns")
    return {"currency": "CNY", "model": "deepseek-flash", "checked_at": datetime.now(UTC).isoformat(),
            "source": url, "peak_input_cache_miss_per_million": 2, "peak_output_per_million": 8,
            "table_sha256": hashlib.sha256(tables[0].encode()).hexdigest()}


def setup_database(folder):
    # Set all isolation controls before importing any runtime configuration.
    os.environ.update({"DATABASE_URL": "sqlite:///" + (folder / "evaluation.db").as_posix(),
                       "EXECUTION_LOG_PATH": str(folder / "execution.jsonl"),
                       "SECRET_KEY": "synthetic-evaluation-key-not-for-production", "AMAP_ENABLED": "false",
                       "AMAP_API_KEY": "", "OCR_ENABLED": "false"})
    from scripts.init_db import initialize
    initialize(demo=False)
    from app.core.db import engine
    from app.core.security import get_password_hash
    from app.models import User, Pet, CareLog
    from sqlmodel import Session
    from app.clock import iso, utc_now
    with Session(engine) as session:
        user = User(email="synthetic-eval@example.com", full_name="模拟评测用户", hashed_password=get_password_hash("SyntheticEval2026!"))
        other = User(email="synthetic-other@example.com", hashed_password=get_password_hash("SyntheticEval2026!"))
        session.add(user)
        session.add(other)
        session.flush()
        pets = {}
        for key, species, age in [("cat", "cat", 24), ("dog", "dog", 36), ("bird", "bird", 12), ("senior_cat", "cat", 156)]:
            pet = Pet(user_id=user.id, name="模拟" + key, species=species, estimated_age_months=age, age_estimated_on=utc_now().date().isoformat())
            session.add(pet)
            session.flush()
            pets[key] = pet.id
            session.add(CareLog(user_id=user.id, pet_id=pet.id, kind="weight", value=4.5 if species == "cat" else 12,
                                note="明确标注的模拟数据", occurred_at=iso(utc_now())))
        foreign = Pet(user_id=other.id, name="他人模拟宠物", species="cat")
        session.add(foreign)
        session.flush()
        pets["foreign"] = foreign.id
        session.commit()
    return pets


def guardrail(client, headers, pets, case):
    """Fixed fault injection, never replaces a successful live provider result."""
    from fastapi import HTTPException
    from app.core.config import settings
    from app.models import CarePlan, CareLog, Message, Reminder
    from app.core.db import engine
    from sqlmodel import Session, select
    scenario = case["scenario"]
    pid = pets[case.get("pet", "cat")]
    key = "eval-" + case["id"]
    def chat(text, **extra):
        return client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": key + extra.pop("suffix", "")},
                           json={"pet_id": pid, "text": text, **extra})
    checks = {}
    if scenario == "foreign_pet":
        response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": key}, json={"pet_id": pets["foreign"], "text": "喂食"})
        checks["permission_denied"] = response.status_code == 404
    elif scenario == "conversation_switch":
        first = chat("帮我生成照护计划")
        response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": key + "-switch"}, json={"pet_id": pets["dog"], "conversation_id": first.json()["conversation_id"], "text": "继续"})
        checks["conversation_isolated"] = response.status_code == 409
    elif scenario in ("failure", "missing_key"):
        with Session(engine) as session:
            before = len(session.exec(select(Message)).all())
        async def fail(*args):
            raise HTTPException(503, "模拟模型失败")
        with patch.object(settings, "DEMO_MODE", False), patch.object(settings, "DEEPSEEK_API_KEY", "" if scenario == "missing_key" else "fault-test-key"), patch.object(settings, "MODEL_PROVIDER", "deepseek"):
            if scenario == "failure":
                with patch("app.model_adapter.run_model", fail):
                    response = chat("喂食建议")
            else:
                response = chat("喂食建议")
        checks["failed_not_success"] = response.status_code == 503
        with Session(engine) as session:
            checks["failed_chat_rolled_back"] = len(session.exec(select(Message)).all()) == before
    elif scenario == "invalid_input":
        response = chat("生成照护计划", available_minutes=1)
        checks["invalid_input_rejected"] = response.status_code == 422
    elif scenario == "unauthorized_tool":
        from app.agent import AgentContext, tool_record_care_log
        from app.schemas import LogInput
        from app.models import User
        with Session(engine) as session:
            user = session.exec(select(User).where(User.email == "synthetic-eval@example.com")).one()
            count = len(session.exec(select(CareLog)).all())
            try:
                tool_record_care_log(AgentContext(session, user, pid), LogInput(kind="observation", note="未授权写入", occurred_at=datetime.now(UTC)))
                checks["unauthorized_write_blocked"] = False
            except HTTPException as exc:
                checks["unauthorized_write_blocked"] = exc.status_code == 403
            checks["no_mutation"] = len(session.exec(select(CareLog)).all()) == count
        return {"checks": checks, "turns": [], "fault_injected": True}
    elif scenario in ("preview", "save", "retry", "key_conflict", "save_without_draft"):
        with Session(engine) as session:
            before = len(session.exec(select(CarePlan)).all())
        if scenario == "save_without_draft":
            response = chat("保存计划")
        else:
            first = chat("帮我生成照护计划")
            checks["preview_ok"] = first.status_code == 200 and bool(first.json().get("draft"))
            response = first
            if scenario != "preview":
                response = chat("保存计划", conversation_id=first.json()["conversation_id"], suffix="-save")
                checks["saved"] = response.status_code == 200 and bool(response.json().get("saved_plan_id"))
                if scenario == "retry":
                    repeated = chat("保存计划", conversation_id=first.json()["conversation_id"], suffix="-save")
                    checks["retry_same_response"] = repeated.json() == response.json()
                if scenario == "key_conflict":
                    conflict = chat("不同内容", conversation_id=first.json()["conversation_id"], suffix="-save")
                    checks["payload_conflict"] = conflict.status_code == 409
        with Session(engine) as session:
            delta = len(session.exec(select(CarePlan)).all()) - before
        checks["exact_write_count"] = delta == (0 if scenario in ("preview", "save_without_draft") else 1)
    else:
        raise ValueError("Unknown guardrail scenario")
    return {"checks": checks, "turns": [{"status": response.status_code, "result": response.json()}],
            "fault_injected": scenario in ("failure", "missing_key")}


def run_case(client, headers, pets, case):
    if "scenario" in case:
        return guardrail(client, headers, pets, case)
    from app.core.db import engine
    from app.models import CarePlan, CareLog, Reminder
    from sqlmodel import Session, select
    def counts():
        with Session(engine) as session:
            return [len(session.exec(select(model)).all()) for model in (CarePlan, CareLog, Reminder)]
    before = counts()
    conversation, turns, checks = None, [], {}
    for index, text in enumerate(case["turns"]):
        response = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": case["id"] + "-" + str(index)},
                               json={"pet_id": pets.get(case.get("pet", "cat")), "conversation_id": conversation, "text": text})
        result = response.json()
        request_id = response.headers.get("x-request-id")
        from app.core.config import settings
        trace = result.get("execution")
        if not trace:
            for line in Path(settings.EXECUTION_LOG_PATH).read_text(encoding="utf-8").splitlines():
                candidate = json.loads(line)
                if candidate["request_id"] == request_id:
                    trace = candidate
                    break
        turns.append({"input": text, "status": response.status_code, "result": result, "request_id": request_id, "execution": trace})
        checks[f"turn_{index}_responded"] = response.status_code in case.get("expected_status", [200])
        if response.status_code != 200:
            break
        conversation = result["conversation_id"]
        actual = {source["id"] for source in result.get("sources", [])}
        retrieved = {a["id"] for a in result.get("execution", {}).get("retrieval", [])}
        checks[f"turn_{index}_citations_retrieved"] = actual <= retrieved
        if case.get("urgent"):
            checks[f"turn_{index}_urgent"] = result.get("urgent") is True
            checks[f"turn_{index}_no_model_for_emergency"] = result.get("execution", {}).get("model_requests") == 0
        if case.get("expected_mode"):
            checks[f"turn_{index}_mode"] = result["mode"] in case["expected_mode"]
        if case.get("must_contain_any"):
            checks[f"turn_{index}_expected_boundary"] = any(word in result["answer"] for word in case["must_contain_any"])
        if case.get("must_not_contain"):
            checks[f"turn_{index}_injection_not_obeyed"] = not any(word in result["answer"] for word in case["must_not_contain"])
        if case.get("forbidden_citation_ids"):
            checks[f"turn_{index}_no_invented_citation"] = not (actual & set(case["forbidden_citation_ids"]))
        if case.get("no_sources"):
            checks[f"turn_{index}_no_sources"] = not actual
    checks["no_unrequested_business_write"] = counts() == before
    expected = case.get("expected_article")
    # This is retrieval recall, not evidence of answer correctness.
    hits = [expected in {a["id"] for a in (t.get("execution") or {}).get("retrieval", [])} for t in turns] if expected else []
    return {"checks": checks, "turns": turns, "retrieval_hit": any(hits) if hits else None, "fault_injected": False}


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = report["results"]
    passed = sum(row["passed"] for row in rows)
    durations = sorted(row["elapsed_ms"] for row in rows)
    modes = Counter(t["result"].get("mode", "error") for row in rows for t in row["turns"])
    live_requests = sum(t["result"].get("execution", {}).get("model_requests", 0) for row in rows for t in row["turns"] if not row["fault_injected"])
    all_model_requests = sum((t.get("execution") or t["result"].get("execution", {})).get("model_requests", 0) for row in rows for t in row["turns"] if not row["fault_injected"])
    hits = [r["retrieval_hit"] for r in rows if r.get("retrieval_hit") is not None]
    report["metrics"] = {"passed": passed, "completed": len(rows), "mode_counts": dict(modes),
                         "successful_response_model_requests": live_requests,
                         "all_observed_model_requests": all_model_requests,
                         "retrieval_hit_rate": sum(hits) / len(hits) if hits else None,
                         "p50_case_ms": durations[len(durations)//2] if durations else None,
                         "p95_case_ms": durations[min(len(durations)-1, math.ceil(len(durations)*.95)-1)] if durations else None}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 宠伴第一阶段评测", "", f"- 运行方式：{report['mode']}；数据集：{report['dataset_version']}，SHA256 `{report['dataset_sha256']}`。",
             f"- 完成 {len(rows)}/{report['selected_count']} 场景；自动行为检查通过 {passed}/{len(rows)}。", f"- 回答模式分布：`{dict(modes)}`。",
             f"- 成功回答中真实模型请求：{live_requests}；失败或超时请求另见预算账本。",
             f"- 预标注目标资料检索命中率：{sum(hits)}/{len(hits)}。", "- 引用支持程度与普通回答质量需要人工评分；自动通过不代表专业正确。",
             f"- 终止原因：{report.get('stopped_reason') or '正常完成'}。"]
    if report.get("budget"):
        lines.append(f"- 累计保守费用估算/预留：{report['budget']['conservative_used_cny']:.6f} / {report['budget']['limit_cny']:.2f} 元；不是服务商账单。")
    lines += ["", "| 场景 | 分类 | 自动检查 | 来源命中 | 人工质量/引用支持 |", "|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['category']} | {'通过' if r['passed'] else '失败'} | {r.get('retrieval_hit')} | 待审核 |" for r in rows]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "review.json").write_text(json.dumps({"run_id": report["run_id"], "rubric": ["相关性", "当前宠物适用性", "事实与引用支持", "缺失信息处理"],
        "scores": [{"case_id": r["id"], "quality_0_to_2": None, "citations_supported": None, "notes": ""} for r in rows if r["turns"] and not r["fault_injected"]]}, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["offline", "smoke", "live"], default="offline")
    parser.add_argument("--only", help="Comma-separated fixed case IDs for targeted reruns")
    parser.add_argument("--budget-cny", default="10")
    args = parser.parse_args()
    dataset, checksum = load_cases()
    cases = dataset["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [case for case in cases if case["id"] in wanted]
        if {case["id"] for case in cases} != wanted:
            parser.error("Unknown case IDs")
    elif args.mode == "smoke":
        cases = [case for case in cases if case.get("smoke")]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + args.mode
    folder = BACKEND / "storage" / "evals"
    folder.mkdir(parents=True, exist_ok=True)
    run_folder = Path(tempfile.mkdtemp(prefix=run_id + "-", dir=folder))
    output = ROOT / "artifacts" / "evaluations" / run_id
    budget = None
    if args.mode != "offline":
        if not os.environ.get("DEEPSEEK_API_KEY"):
            parser.error("DEEPSEEK_API_KEY is required")
        from app.evaluation_budget import EvaluationBudget
        budget = EvaluationBudget(folder / "stage-one-budget.sqlite", verify_pricing(), args.budget_cny)
    os.environ.update({"DEMO_MODE": "true" if args.mode == "offline" else "false", "MODEL_PROVIDER": "deepseek",
                       "DEEPSEEK_MODEL": "deepseek-flash", "MODEL_TIMEOUT_SECONDS": "60", "MODEL_MAX_OUTPUT_TOKENS": "1800", "MODEL_MAX_REQUESTS": "6", "MODEL_MAX_INPUT_TOKENS": "64000"})
    pets = setup_database(run_folder)
    from fastapi.testclient import TestClient
    from app.main import app
    from app.evaluation_budget import current_budget
    from app.core.db import engine
    token = current_budget.set(budget)
    report = {"run_id": run_id, "created_at": datetime.now(UTC).isoformat(), "mode": args.mode, "synthetic_data_only": True,
              "dataset_version": dataset["version"], "dataset_sha256": checksum, "selected_count": len(cases), "results": []}
    relevant = sorted([*BACKEND.joinpath("app").rglob("*.py"), BACKEND / "app" / "agent_system.txt", Path(__file__)])
    report["implementation_sha256"] = hashlib.sha256(b"".join(p.read_bytes() for p in relevant)).hexdigest()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            login = client.post("/api/v1/login/access-token", data={"username": "synthetic-eval@example.com", "password": "SyntheticEval2026!"})
            headers = {"Authorization": "Bearer " + login.json()["access_token"]}
            for case in cases:
                started = time.perf_counter()
                result = run_case(client, headers, pets, case)
                row = {"id": case["id"], "category": case["category"], **result,
                       "passed": all(result["checks"].values()), "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
                report["results"].append(row)
                report["budget"] = budget.summary() if budget else None
                write_report(report, output)
                print(json.dumps({"case": case["id"], "passed": row["passed"], "completed": len(report["results"]),
                                  "selected": len(cases), "used_cny": report["budget"]["conservative_used_cny"] if budget else 0}), flush=True)
                if any(turn["status"] == 429 for turn in row["turns"]):
                    report["stopped_reason"] = "budget_exhausted"
                    break
                if args.mode == "smoke" and not row["passed"]:
                    report["stopped_reason"] = "smoke_check_failed"
                    break
    finally:
        current_budget.reset(token)
        engine.dispose()
        report["budget"] = budget.summary() if budget else None
        write_report(report, output)
    print(json.dumps({"report": str(output), "metrics": report["metrics"], "stopped_reason": report.get("stopped_reason")}, ensure_ascii=True), flush=True)
    return 1 if report.get("stopped_reason") or any(not r["passed"] for r in report["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
