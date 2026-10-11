import json
import pytest
import httpx2
from openai import AsyncOpenAI as RealClient
from sqlmodel import Session, select
from app.core.config import settings
from app.models import ModelUsage, Message, IdempotencyRecord
from app.agent import agent


def fake_provider(monkeypatch, answer, source="cat-food"):
    captured = []

    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        assert request.url.path.endswith("/chat/completions")
        assert body["model"] == "mock-model"
        names = {t["function"]["name"] for t in body["tools"]}
        assert {
            "get_pet_profile",
            "search_pet_knowledge",
            "save_care_plan",
            "create_reminder",
            "record_care_log",
        }.issubset(names)
        output = next(
            n
            for n in names
            if n
            not in {
                "get_pet_profile",
                "search_pet_knowledge",
                "save_care_plan",
                "create_reminder",
                "record_care_log",
                "get_care_history",
                "get_current_care_plans",
                "assess_nutrition",
                "search_nearby_hospitals",
                "build_vet_visit_summary",
                "get_breed_knowledge",
                "assess_pet_products",
            }
        )
        return httpx2.Response(
            200,
            json={
                "id": "mock-response",
                "object": "chat.completion",
                "created": 1,
                "model": "mock-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "out",
                                    "type": "function",
                                    "function": {
                                        "name": output,
                                        "arguments": json.dumps(
                                            {
                                                "answer": answer,
                                                "citation_ids": [source],
                                                "draft": None,
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 320,
                    "completion_tokens": 70,
                    "total_tokens": 390,
                },
            },
        )

    def factory(**kwargs):
        return RealClient(
            **kwargs,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        )

    monkeypatch.setattr("app.model_adapter.AsyncOpenAI", factory)
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "MODEL_API_KEY", "test-key-not-live")
    monkeypatch.setattr(settings, "MODEL_NAME", "mock-model")
    return captured


def test_compatible_model_structured_result_and_usage(
    client, headers, cat, db, monkeypatch
):
    seen = fake_provider(monkeypatch, "根据档案使用适合成长阶段的完整均衡食物。")
    r = client.post(
        "/api/v1/chat",
        headers={**headers, "Idempotency-Key": "live-test"},
        json={"pet_id": cat["id"], "text": "喂食建议"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "live" and r.json()["sources"][0]["id"] == "cat-food"
    assert len(seen) == 1
    assert "8" in json.dumps(seen[0]["messages"], ensure_ascii=False)
    usage = client.get("/api/v1/usage", headers=headers).json()
    assert usage == {"requests": 1, "input_tokens": 320, "output_tokens": 70}


def test_unretrieved_citation_rejected_and_rolled_back(
    client, headers, cat, db, monkeypatch
):
    fake_provider(monkeypatch, "假的参考来源", "invented-article")
    r = client.post(
        "/api/v1/chat",
        headers={**headers, "Idempotency-Key": "fake-cite"},
        json={"pet_id": cat["id"], "text": "喂食"},
    )
    assert r.status_code == 502
    with Session(db) as s:
        assert s.exec(select(Message)).all() == []
        assert (
            s.exec(
                select(IdempotencyRecord).where(IdempotencyRecord.key == "fake-cite")
            ).first()
            is None
        )


def test_twelve_pydantic_tools_registered():
    assert set(agent._function_toolset.tools) == {
        "get_pet_profile",
        "search_pet_knowledge",
        "save_care_plan",
        "create_reminder",
        "record_care_log",
        "get_care_history",
        "get_current_care_plans",
        "assess_nutrition",
        "search_nearby_hospitals",
        "build_vet_visit_summary",
        "get_breed_knowledge",
        "assess_pet_products",
    }
