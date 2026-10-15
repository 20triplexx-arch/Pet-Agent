"""Behavior-level answer quality, durable evidence, model limits and compatibility."""
import json
from datetime import datetime, UTC
from uuid import uuid4
from pathlib import Path
import pytest
from sqlmodel import Session, select
from app.models import Message, Conversation, ModelAttempt, PetNutritionProfile, CarePlan, CareLog
from app.core.config import settings
from test_model_adapter import fake_provider


def ask(client, headers, pid, text, **extra):
    return client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"pet_id": pid, "text": text, **extra})


def test_elliptical_followup_resolves_latest_topic_without_reviving_older_topic():
    from app.deep_chat import followup_background
    history = [{'role': 'user', 'content': '猫吃多少？'}, {'role': 'user', 'content': '狗刷牙怎么练习？'}]
    assert followup_background(history, '抗拒时怎么办？') == '狗刷牙怎么练习？'
    assert followup_background(history, '猫抓沙发怎么办？') == ''
    assert followup_background(history, '猫砂怎么选择？') == ''
    assert followup_background([{'role': 'user', 'content': '猫航空箱如何适应？'}], '练习时怎么奖励？') == '猫航空箱如何适应？'


def test_legacy_request_setting_is_accepted_and_capped(client, headers, cat, monkeypatch):
    from app.core.config import Settings
    from app.model_adapter import UsageLimits
    assert Settings(_env_file=None, MODEL_MAX_REQUESTS=6).MODEL_MAX_REQUESTS == 6
    fake_provider(monkeypatch, "核对个体和标签资料后安排照护。", source="__first__")
    monkeypatch.setattr(settings, "MODEL_MAX_REQUESTS", 6)
    limits = []
    def capture(**kwargs):
        limits.append(kwargs)
        return UsageLimits(**kwargs)
    monkeypatch.setattr("app.model_adapter.UsageLimits", capture)
    response = ask(client, headers, cat["id"], "喂食建议")
    assert response.status_code == 200, response.text
    assert limits[0]["request_limit"] == 4
    assert limits[0]["output_tokens_limit"] == 2048 * 4


QUALITY_CASES = [
    ("scratching", "cat", "猫抓沙发怎么办", ["cat-scratching"], ["替代", "材质"]),
    ("new-cat", "cat", "新猫刚到家如何适应", ["cat-home"], ["空间", "记录"]),
    ("new-dog", "dog", "幼犬到家要准备什么", ["dog-home"], ["安全", "规则"]),
    ("multiple-cats", "cat", "多猫相处怎样介绍新猫", ["cat-multi"], ["资源", "反应"]),
    ("alone", "dog", "狗独自在家叫，怎么安排", ["dog-alone"], ["记录", "离开"]),
    ("dental", "dog", "狗刷牙用品怎么选择", ["dog-dental"], ["疼痛", "用品"]),
    ("label", "cat", "食品标签配料排序能判断质量吗", ["food-labels"], ["配料", "上下限"]),
    ("transition", "cat", "猫换粮如何观察", ["food-transition"], ["变化", "记录"]),
    ("appetite", "cat", "猫昨天不吃东西，今天精神一般", ["cat-appetite"], ["兽医", "拒食"]),
    ("carrier", "cat", "猫航空箱怎么适应", ["cat-carrier"], ["航空箱", "适应"]),
    ("toilet", "dog", "幼犬乱尿如何教如厕", ["dog-toilet"], ["记录", "奖励"]),
    ("winter", "dog", "冬季狗保暖要注意什么", ["dog-winter"], ["保暖", "观察"]),
    ("cat-food", "cat", "猫日常喂食要注意什么", ["cat-food"], ["阶段", "食物"]),
    ("dog-food", "dog", "狗喂食的主粮如何选择", ["dog-food"], ["阶段", "食物"]),
    ("units", "cat", "包装热量kcal和kJ怎样换算", ["nutrition-label"], ["单位", "克"]),
    ("budget", "dog", "比较主粮每100克成本和每日预算", [], ["规格", "价格"]),
    ("unknown-brand", "cat", "推荐哪种猫粮，什么品牌好", [], ["具体", "配方"]),
    ("health-observation", "dog", "狗今天腹泻两次，精神和食欲正常，怎么记录", [], ["观察", "时间"]),
    ("health-time", "cat", "猫昨天呕吐一次，精神正常，要准备什么信息", [], ["记录", "兽医"]),
    ("dose-boundary", "dog", "狗咳嗽应该吃什么药和剂量", [], ["剂量", "不能"]),
    ("visit", "cat", "帮我整理就医摘要", ["visit-preparation"], ["摘要", "记录"]),
    ("nutrition-missing", "cat", "猫每天吃多少克，为什么不能凭品种估算", ["nutrition-energy"], ["不能可靠", "能量密度"]),
    ("breed", "dog", "金毛怎么照护", ["breed-dog-golden"], ["品种", "个体"]),
    ("mixed-food-question", "cat", "换粮怎么观察？另外食品标签应该看什么", ["food-transition", "food-labels"], ["换粮", "标签"]),
    ("multiple-behaviors", "cat", "猫抓沙发怎么办？另外多猫如何相处", ["cat-scratching", "cat-multi"], ["抓", "相处"]),
    ("food-plus-play", "dog", "狗喂食怎么安排？另外独自在家叫怎么办", ["dog-alone"], ["食物", "独处"]),
    ("more-detail", "cat", "如何给猫提供合适的抓板并判断效果", ["cat-scratching"], ["稳定", "记录"]),
    ("urgent-breathing", "cat", "猫呼吸困难，还想选粮", [], ["请立即联系兽医"]),
    ("urgent-urinary", "cat", "猫尿不出来，要补充营养吗", [], ["请立即联系兽医"]),
    ("urgent-seizure", "dog", "狗持续抽搐，要制定计划", [], ["请立即联系兽医"]),
]


@pytest.mark.parametrize("name,species,text,required,terms", QUALITY_CASES, ids=[c[0] for c in QUALITY_CASES])
def test_quality_questions(client, headers, name, species, text, required, terms):
    p = client.post("/api/v1/pets", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"name": "质量验证宠物", "species": species, "estimated_age_months": 36}).json()
    r = ask(client, headers, p["id"], text, answer_depth="detailed")
    assert r.status_code == 200, r.text
    reply = r.json()
    assert reply["mode"] == "demo"
    assert set(required).issubset({s["id"] for s in reply["sources"]})
    assert all(term in reply["answer"] for term in terms), name
    if name.startswith("urgent-"):
        assert reply["urgent"] and reply["answer"].startswith("请立即联系兽医")
    else:
        assert not reply["urgent"]
        assert len(reply["questions"]) <= 3
    for source in reply["sources"]:
        a = client.get("/api/v1/knowledge/" + source["id"], headers=headers).json()
        assert source["url"] == a["source_url"] and species in a["species"]
        assert all(heading in a["body"] for heading in source.get("sections", []))


def test_long_input_validation_and_old_client(client, headers, cat):
    text = "猫抓沙发怎么办？" + "补充环境记录。" * 900
    r = ask(client, headers, cat["id"], text)
    assert r.status_code == 200
    rows = client.get(f"/api/v1/conversations/{r.json()['conversation_id']}/messages", headers=headers).json()
    assert rows[0]["content"] == text
    assert ask(client, headers, cat["id"], "文" * 12001).status_code == 422
    assert ask(client, headers, cat["id"], " ").status_code == 422
    assert ask(client, headers, cat["id"], "日常喂食").status_code == 200


def test_context_is_dated_scoped_and_not_saved_to_profile(client, headers, cat, db):
    first = ask(client, headers, cat["id"], "猫昨天呕吐一次，怎么办", context={"timeline": "昨天开始，只出现一次", "observations": "精神正常，食欲正常", "goal": "整理观察"}).json()
    assert "何时开始" not in first["answer"] and "出现频率" not in first["answer"]
    second = ask(client, headers, cat["id"], "进一步说明观察的用途", conversation_id=first["conversation_id"]).json()
    assert "昨天开始，只出现一次" in second["answer"]
    user_messages = client.get(f"/api/v1/conversations/{first['conversation_id']}/messages", headers=headers).json()
    assert first["context_provenance"]["timeline"]["message_id"] == user_messages[0]["id"]
    assert second["context_provenance"]["timeline"]["message_id"] == user_messages[0]["id"]
    profile = client.get("/api/v1/pets/" + cat["id"], headers=headers).json()
    assert profile["medical_history"] is None
    with Session(db) as session:
        assert not session.exec(select(PetNutritionProfile)).all()
        assert not session.exec(select(CarePlan)).all()
    new = ask(client, headers, cat["id"], "猫玩具怎么选").json()
    assert "昨天开始，只出现一次" not in new["answer"]


def test_context_conflict_and_emergency_before_live_model(client, headers, cat, monkeypatch):
    client.put("/api/v1/pets/" + cat["id"], headers=headers, json={"name": "测试猫", "species": "cat", "diet": "幼猫粮"})
    r = ask(client, headers, cat["id"], "日常饮食建议", context={"diet_activity": "目前改吃新配方"}).json()
    assert r["context_conflicts"] and "档案尚未修改" in r["answer"]
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "MODEL_API_KEY", "test-key-not-live")
    async def forbidden(*args):
        raise AssertionError("Emergency called model")
    monkeypatch.setattr("app.model_adapter.run_model", forbidden)
    urgent = ask(client, headers, cat["id"], "请帮我选粮", context={"observations": "正在呼吸困难"})
    assert urgent.status_code == 200 and urgent.json()["urgent"]


def test_nutrition_partial_validation_and_numbers_from_backend(client, headers):
    p = client.post("/api/v1/pets", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"name": "成年猫", "species": "cat", "estimated_age_months": 36, "neutered": True}).json()
    now = datetime.now(UTC)
    client.post(f"/api/v1/pets/{p['id']}/logs", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"kind": "weight", "value": 4, "occurred_at": now.isoformat()})
    nutrition = {"life_stage": "adult", "health_status": "healthy", "bcs": 5, "muscle": "normal", "assessed_on": now.date().isoformat(), "assessor": "owner", "activity_level": "normal", "pregnancy_lactation": "no", "weight_confirmed": True, "treats_confirmed": True, "food_shares_confirmed": True, "foods": [{"name": "已核对主粮", "complete_adult_food": True, "energy": 400, "energy_unit": "kcal_100g", "daily_grams": 60}]}
    r = ask(client, headers, p["id"], "营养和喂食量如何评估", context={"nutrition": nutrition}).json()
    expected_response = client.post(f"/api/v1/pets/{p['id']}/nutrition/preview", headers=headers, json=nutrition)
    assert expected_response.status_code == 200
    expected = expected_response.json()
    assert "参考" in r["answer"] and "kcal/日" in r["answer"] and "| 食物 |" in r["answer"]
    assert "240" in r["answer"] and any(s["id"] == "nutrition-energy" for s in r["sources"])
    assert f"{expected['calculation']['daily_kcal_range'][0]:.0f}—{expected['calculation']['daily_kcal_range'][1]:.0f}" in r["answer"]
    assert client.get(f"/api/v1/pets/{p['id']}/nutrition/profile", headers=headers).json()["revision"] == 0
    assert ask(client, headers, p["id"], "营养", context={"nutrition": {"bcs": 10}}).status_code == 422
    assert ask(client, headers, p["id"], "营养", context={"nutrition": {"foods": [{"name": "食物", "energy": -1}]}}).status_code == 422


def test_old_history_summary_preserves_message_sources(client, headers, cat, db):
    from app.deep_chat import summarize_history
    history = [{"id": f"m{i}", "role": "user", "content": "用户报告曾有过敏，兽医建议不要自行换粮。" if i == 0 else "日常记录。", "created_at": "2026-10-01", "metadata_json": {}} for i in range(30)]
    summary = summarize_history(history, "换粮")
    assert any(item["message_id"] == "m0" and "过敏" in item["user_report_excerpt"] for item in summary["items"])
    assert all(item["date"] == "2026-10-01" for item in summary["items"])
    with Session(db) as session:
        c = Conversation(user_id=cat["user_id"], pet_id=cat["id"])
        session.add(c)
        session.flush()
        for i in range(26):
            session.add(Message(conversation_id=c.id, role="user", content="过敏及兽医建议：勿自行换粮" if i == 0 else "我在记录猫的环境。"))
        cid = c.id
        session.commit()
    r = ask(client, headers, cat["id"], "继续分析换粮", conversation_id=cid).json()
    assert r["memory_sources"]
    with Session(db) as session:
        assert session.get(Conversation, cid).summary_json["items"]


@pytest.mark.parametrize("text", ["英短怎么护理", "猫昨天呕吐一次，精神正常", "营养吃多少", "推荐什么猫粮"])
def test_specialized_questions_reach_live_model(client, headers, cat, monkeypatch, text):
    seen = fake_provider(monkeypatch, "需要结合适用条件说明观察和执行步骤。", source="__first__")
    r = ask(client, headers, cat["id"], text, context={"goal": "详细了解"}, answer_depth="detailed")
    assert r.status_code == 200 and r.json()["mode"] == "live", r.text
    assert seen and seen[0].get("max_tokens", seen[0].get("max_completion_tokens")) == 4096
    payload = json.loads(seen[0]["messages"][-1]["content"])
    assert payload["supplemental_context"]["values"]["goal"] == "详细了解"
    assert payload["answer_depth"] == "detailed" and payload["user_message"] == text


def test_quota_failure_audit_and_retry_idempotency(client, headers, cat, monkeypatch, db):
    seen = fake_provider(monkeypatch, "有依据的喂食说明。")
    monkeypatch.setattr(settings, "MODEL_TURNS_PER_DAY", 1)
    key = str(uuid4())
    body = {"pet_id": cat["id"], "text": "喂食"}
    first = client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": key}, json=body)
    assert first.status_code == 200
    assert client.post("/api/v1/chat", headers={**headers, "Idempotency-Key": key}, json=body).json() == first.json()
    assert len(seen) == 1
    denied = ask(client, headers, cat["id"], "喂食")
    assert denied.status_code == 429 and len(seen) == 1
    assert client.get("/api/v1/usage/quota", headers=headers).json()["attempted_turns"] == 1
    monkeypatch.setattr(settings, "MODEL_TURNS_PER_DAY", 3)
    fake_provider(monkeypatch, "虚构来源", "never-retrieved")
    failed = ask(client, headers, cat["id"], "喂食")
    assert failed.status_code == 502
    quota = client.get("/api/v1/usage/quota", headers=headers).json()
    assert quota["attempted_turns"] == 2 and quota["failed_turns"] == 1
    with Session(db) as session:
        assert len(session.exec(select(Message)).all()) == 2


def test_user_scope_with_supplements_and_usage(client, headers, cat, account):
    owner = ask(client, headers, cat["id"], "喂食", context={"goal": "私有照护目标"}).json()
    other = account("other-deep@example.com")
    assert ask(client, other, cat["id"], "分析资料").status_code == 404
    assert ask(client, other, None, "分析资料", conversation_id=owner["conversation_id"]).status_code == 404
    assert client.get("/api/v1/usage/quota", headers=other).json()["attempted_turns"] == 0


def test_budget_keeps_current_message_and_advice_or_rejects(client, headers, cat, monkeypatch):
    seen = fake_provider(monkeypatch, "依据当前资料。", source="__first__")
    text = "喂食说明" + "这是用户提供的完整长说明。" * 600
    r = ask(client, headers, cat["id"], text, context={"professional_advice": "专业建议不得自行更改"})
    assert r.status_code == 200, r.text
    payload = json.loads(seen[0]["messages"][-1]["content"])
    assert payload["user_message"] == text
    assert payload["supplemental_context"]["values"]["professional_advice"] == "专业建议不得自行更改"


@pytest.mark.parametrize("kwargs", [{"finish_reason": "length"}, {"citation_sections": [{"article_id": "cat-food", "heading": "不存在的专业审核章节"}]}])
def test_incomplete_and_unretrieved_section_not_saved(client, headers, cat, monkeypatch, db, kwargs):
    fake_provider(monkeypatch, "参考喂食资料。", **kwargs)
    r = ask(client, headers, cat["id"], "喂食")
    assert r.status_code in (502, 503)
    with Session(db) as session:
        assert not session.exec(select(Message)).all()
        assert session.exec(select(ModelAttempt)).one().status == "failed"


@pytest.mark.parametrize("answer", ["你家猫一定是肾病，已经确诊。", "建议服用阿莫西林 20 mg。"])
def test_live_cannot_claim_diagnosis_or_new_dose(client, headers, cat, monkeypatch, answer):
    fake_provider(monkeypatch, answer, source="__first__")
    r = ask(client, headers, cat["id"], "猫昨天呕吐一次，精神正常")
    assert r.status_code == 502 and "诊断或药物剂量" in r.json()["detail"]


def test_context_budget_rejects_without_call_or_truncation(client, headers, cat, monkeypatch):
    seen = fake_provider(monkeypatch, "不应执行。", source="__first__")
    monkeypatch.setattr(settings, "MODEL_CONTEXT_CHARS", 16000)
    text = "猫喂食" + "文" * 11000
    r = ask(client, headers, cat["id"], text, context={"goal": "目" * 2000, "professional_advice": "专" * 3000, "observations": "观" * 3000})
    assert r.status_code == 422 and not seen
    assert client.get("/api/v1/usage/quota", headers=headers).json()["attempted_turns"] == 0


def test_read_tool_failure_does_not_claim_success(client, headers, cat, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("isolated assessment failure")
    monkeypatch.setattr("app.deep_chat.assess", fail)
    response = ask(client, headers, cat["id"], "营养吃多少")
    assert response.status_code >= 500


def test_existing_records_are_used_without_generating_unrequested_plan(client, headers, cat):
    result = client.post(f"/api/v1/pets/{cat['id']}/logs", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"kind": "observation", "note": "用户观察：晚间互动后能够安静休息", "occurred_at": datetime.now(UTC).isoformat()})
    assert result.status_code == 200
    response = ask(client, headers, cat["id"], "结合最近记录分析观察，并解释现有计划的依据").json()
    assert "晚间互动后能够安静休息" in response["answer"]
    assert response["draft"] is None
    assert client.get(f"/api/v1/pets/{cat['id']}/plans", headers=headers).json() == []


def test_long_professional_advice_remains_valid_for_nutrition_question(client, headers, cat):
    advice = "用户提供的兽医原建议。" * 200
    response = ask(client, headers, cat["id"], "营养怎么评估", context={"professional_advice": advice})
    assert response.status_code == 200
    assert advice in response.json()["answer"]
    assert "按兽医建议安排，不自动更改食量" in response.json()["answer"]


def test_changed_food_list_cannot_inherit_old_confirmations(client, headers):
    now = datetime.now(UTC)
    p = client.post("/api/v1/pets", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"name": "成年猫", "species": "cat", "estimated_age_months": 36, "neutered": True}).json()
    client.post(f"/api/v1/pets/{p['id']}/logs", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"kind": "weight", "value": 4, "occurred_at": now.isoformat()})
    data = {"life_stage": "adult", "health_status": "healthy", "bcs": 5, "muscle": "normal", "assessed_on": now.date().isoformat(), "assessor": "owner", "activity_level": "normal", "pregnancy_lactation": "no", "weight_confirmed": True, "treats_confirmed": True, "food_shares_confirmed": True, "foods": [{"name": "原主粮", "complete_adult_food": True, "energy": 400, "daily_grams": 60}]}
    assert client.put(f"/api/v1/pets/{p['id']}/nutrition/profile", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"profile": data, "revision": 0}).status_code == 200
    response = ask(client, headers, p["id"], "评估营养", context={"nutrition": {"foods": [{"name": "新主粮", "complete_adult_food": True, "energy": 400, "daily_grams": 50}]}}).json()
    assert "不能可靠给出固定食量" in response["answer"]
    assert "确认所有零食" in response["answer"]
    assert "| 食物 |" not in response["answer"]
    assert client.get(f"/api/v1/pets/{p['id']}/nutrition/profile", headers=headers).json()["profile"]["foods"][0]["name"] == "原主粮"
