from copy import deepcopy
from datetime import datetime, UTC, timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import pytest
import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import Session, select
from app.core.config import settings
from app.care_schemas import FoodInput
from app.nutrition import kcal_per_gram
from app.models import CarePlan, CareTask, PetNutritionProfile, Reminder, TaskCompletion, IdempotencyRecord, KnowledgeArticle, ExternalApiUsage
from test_acceptance import post, chat


@pytest.fixture
def adult(client, headers):
    pet = post(client, headers, "/pets", {"name": "成年猫", "species": "cat", "estimated_age_months": 36, "neutered": True}).json()
    r = post(client, headers, f"/pets/{pet['id']}/logs", {"kind": "weight", "value": 4, "occurred_at": datetime.now(UTC).isoformat()})
    assert r.status_code == 200
    return pet


def complete_profile():
    return {"life_stage": "adult", "bcs": 5, "muscle": "normal", "assessed_on": datetime.now(UTC).date().isoformat(),
        "assessor": "owner", "activity_level": "normal", "health_status": "healthy", "pregnancy_lactation": "no",
        "weight_confirmed": True, "treats_confirmed": True, "food_shares_confirmed": True,
        "foods": [{"name": "测试主粮（非商品推荐）", "kind": "main", "complete_adult_food": True, "energy": 400, "energy_unit": "kcal_100g", "daily_grams": 60}]}


def preview(client, headers, pet, profile=None):
    r = post(client, headers, f"/pets/{pet['id']}/nutrition/preview", profile or complete_profile())
    assert r.status_code == 200, r.text
    return r.json()


def save_payload(p, profile=None):
    return {"profile": profile if profile is not None else complete_profile(), "revision": p["revision"], "preview_token": p["preview_token"],
        "daily_target_kcal": sum(p["calculation"]["daily_kcal_range"]) / 2 if p["calculation"] else None,
        "meal_times": ["07:30", "19:30"]}


def test_cat_dog_rules_and_real_sources(client, headers, adult, db):
    cat = preview(client, headers, adult)
    assert cat["status"] == "ready"
    assert cat["calculation"]["rer_kcal"] == pytest.approx(70 * 4**0.75)
    assert cat["calculation"]["daily_kcal_range"] == pytest.approx([70 * 4**0.75 * 1.2, 70 * 4**0.75 * 1.4])
    dog = post(client, headers, "/pets", {"name": "成年犬", "species": "dog", "estimated_age_months": 36, "neutered": True}).json()
    post(client, headers, f"/pets/{dog['id']}/logs", {"kind": "weight", "value": 10, "occurred_at": datetime.now(UTC).isoformat()})
    d = preview(client, headers, dog)
    assert d["calculation"]["factor_range"] == [1.4, 1.6]
    assert not any(a["id"] == "nutrition-cat-bcs" for a in d["sources"])
    with Session(db) as s:
        for source in cat["sources"] + d["sources"]:
            article = s.get(KnowledgeArticle, source["id"])
            assert source["url"] == article.source_url


@pytest.mark.parametrize("unit,value,portion", [("kcal_100g",400,None),("kcal_kg",4000,None),("kj_100g",1673.6,None),("kj_kg",16736,None),("kcal_portion",100,25),("kj_portion",418.4,25)])
def test_energy_units(unit, value, portion):
    assert kcal_per_gram(FoodInput(name="测试", energy=value, energy_unit=unit, portion_grams=portion)) == pytest.approx(4)


@pytest.mark.parametrize("field,value", [("energy",0),("energy",-1),("energy",float("inf")),("energy",float("nan")),("daily_grams",-1),("portion_grams",0)])
def test_invalid_food_values(field, value):
    with pytest.raises(ValidationError):
        FoodInput.model_validate({"name":"食物",field:value})


def test_mixed_food_treats_and_meals(client, headers, adult):
    data = complete_profile()
    data["foods"] += [{"name":"湿粮", "kind":"main", "complete_adult_food":True, "energy":100,"energy_unit":"kcal_portion","portion_grams":100,"daily_grams":60},
        {"name":"零食", "kind":"treat", "energy":200,"daily_grams":5}]
    p = preview(client, headers, adult, data)
    assert p["calculation"]["current_kcal"] == 310
    assert p["foods"][0]["calorie_share"] == .8
    payload = {**save_payload(p, data), "daily_target_kcal":250,"planned_treat_kcal":10}
    r = post(client, headers, f"/pets/{adult['id']}/nutrition/plans", payload)
    assert r.status_code == 200, r.text
    foods = r.json()["provenance"]["amounts"]
    assert [f["daily_grams"] for f in foods] == pytest.approx([48,48,5])
    assert [f["per_meal_grams"] for f in foods] == pytest.approx([24,24,2.5])
    bad = {**payload, "planned_treat_kcal":30}
    fresh = preview(client, headers, adult, data)
    bad.update(revision=fresh["revision"],preview_token=fresh["preview_token"])
    assert post(client, headers, f"/pets/{adult['id']}/nutrition/plans", bad).status_code == 422


@pytest.mark.parametrize("change", [{"life_stage":"growing"},{"bcs":6},{"muscle":"loss"},{"health_status":"unwell"},{"pregnancy_lactation":"yes"},{"activity_level":"high"}])
def test_risk_no_automatic_quantity(client, headers, adult, change):
    data = {**complete_profile(), **change}
    p = preview(client, headers, adult, data)
    assert p["status"] == "professional_required" and p["calculation"] is None
    assert post(client, headers, f"/pets/{adult['id']}/nutrition/plans", {**save_payload(p,data),"daily_target_kcal":250}).status_code == 422


def test_missing_portion_zero_intake_young_unsupported(client, headers, adult, cat):
    data = complete_profile()
    data["foods"][0].update(energy_unit="kcal_portion",daily_grams=0)
    p = preview(client, headers, adult, data)
    assert p["status"] == "needs_info" and not p["calculation"]
    assert preview(client, headers, cat)["status"] == "professional_required"
    turtle = post(client, headers, "/pets", {"name":"龟", "species":"Trachemys scripta elegans"}).json()
    result = preview(client, headers, turtle)
    assert result["status"] == "professional_required" and result["sources"] == []
    entries = client.get("/api/v1/species", headers=headers).json()
    assert next(v for v in entries if v["id"]=="cat")["capabilities"]["nutrition"] is True


def test_overflowing_label_does_not_produce_quantity(client,headers,adult):
    data=complete_profile()
    data["foods"][0].update(energy=100000,energy_unit="kcal_portion",portion_grams=1e-320)
    p=preview(client,headers,adult,data)
    assert p["status"]=="needs_info" and p["calculation"] is None


def test_capabilities_are_independent(monkeypatch):
    from app import species
    monkeypatch.setattr(species,"SPECIES",[{"id":"new-bird","status":"supported","capabilities":{"knowledge":True}}])
    assert species.supports("new-bird","knowledge")
    assert not species.supports("new-bird","nutrition")


def test_profile_and_pet_changes_invalidate_preview(client,headers,adult):
    p=preview(client,headers,adult)
    data=complete_profile()
    r=client.put(f"/api/v1/pets/{adult['id']}/nutrition/profile",headers={**headers,"Idempotency-Key":str(uuid4())},json={"profile":data,"revision":0})
    assert r.status_code==200
    assert post(client,headers,f"/pets/{adult['id']}/nutrition/plans",save_payload(p)).status_code==409
    p=preview(client,headers,adult)
    r=client.put(f"/api/v1/pets/{adult['id']}",headers={**headers,"Idempotency-Key":str(uuid4())},json={"name":"档案更新","species":"cat","estimated_age_months":36,"neutered":True})
    assert r.status_code==200
    assert post(client,headers,f"/pets/{adult['id']}/nutrition/plans",save_payload(p)).status_code==409


def test_generic_edit_cannot_bypass_nutrition_calculation(client,headers,adult):
    plan=post(client,headers,f"/pets/{adult['id']}/nutrition/plans",save_payload(preview(client,headers,adult))).json()
    body={"title":"绕过计算","basis":"用户填写","revision":1,"tasks":[{"title":"喂食","instructions":"任意数量","basis":"无","local_time":"08:00"}]}
    assert client.put(f"/api/v1/plans/{plan['id']}",headers={**headers,"Idempotency-Key":str(uuid4())},json=body).status_code==422


def test_missing_knowledge_prevents_quantity(client,headers,adult,db):
    with Session(db) as s:
        s.delete(s.get(KnowledgeArticle,"nutrition-energy"))
        s.commit()
    p=preview(client,headers,adult)
    assert p["status"]=="needs_info" and p["calculation"] is None


def test_nonquant_and_urgent_first_without_maps(client, headers, adult, monkeypatch):
    p = post(client, headers, f"/pets/{adult['id']}/nutrition/preview",{}).json()
    r = post(client, headers, f"/pets/{adult['id']}/nutrition/plans",save_payload(p,{}))
    assert r.status_code==200, r.text
    assert r.json()["provenance"]["amounts"] == []
    data = {**complete_profile(),"current_symptoms":"呼吸困难"}
    p = preview(client,headers,adult,data)
    assert p["urgent"] and "立即" in p["warnings"][0]
    assert post(client,headers,f"/pets/{adult['id']}/nutrition/plans",save_payload(p,data)).status_code==422
    async def no_map(*args):
        pytest.fail("urgent chat must not wait for map")
    monkeypatch.setattr("app.api.care_routes.search_hospitals",no_map)
    result = chat(client,headers,adult["id"],"呼吸困难，推荐医院").json()
    assert result["answer"].startswith("请立即") and result["cards"][0]["type"]=="hospitals"


def test_save_replace_complete_history_stale_and_timezone(client, headers, adult, db):
    client.patch("/api/v1/users/me",headers=headers,json={"full_name":"测试","timezone":"America/New_York"})
    p = preview(client,headers,adult)
    payload = save_payload(p)
    path=f"/pets/{adult['id']}/nutrition/plans"
    first = post(client,headers,path,payload,"nutrition-repeat")
    assert first.status_code==200, first.text
    assert post(client,headers,path,payload,"nutrition-repeat").json()==first.json()
    reminders=client.get("/api/v1/reminders",headers=headers,params={"pet_id":adult["id"]}).json()
    assert all(r["timezone"]=="America/New_York" for r in reminders)
    # A genuinely due occurrence, rather than checking in tomorrow's feeding.
    with Session(db) as s:
        row = s.get(Reminder,reminders[0]["id"])
        row.due_at = (datetime.now(UTC)-timedelta(days=1)).isoformat()
        reminders[0]["due_at"] = row.due_at
        s.add(row)
        s.commit()
    completion=post(client,headers,f"/reminders/{reminders[0]['id']}/complete",{"occurrence_at":reminders[0]["due_at"]})
    assert completion.status_code==200
    # One ordinary plan is unaffected by nutrition replacement.
    draft=post(client,headers,f"/pets/{adult['id']}/plans/preview",{"available_minutes":20}).json()["draft"]
    ordinary=post(client,headers,f"/pets/{adult['id']}/plans",draft).json()
    fresh=preview(client,headers,adult)
    second=post(client,headers,path,save_payload(fresh)).json()
    with Session(db) as s:
        assert s.get(CarePlan,first.json()["id"]).status=="paused"
        assert s.get(CarePlan,ordinary["id"]).status=="active"
        assert len(s.exec(select(TaskCompletion)).all())==1
        assert all(s.get(Reminder,r["id"]).paused for r in reminders)
    assert client.patch(f"/api/v1/plans/{first.json()['id']}/status",headers={**headers,"Idempotency-Key":str(uuid4())},json={"status":"active"}).status_code==409
    stale=preview(client,headers,adult)
    post(client,headers,f"/pets/{adult['id']}/logs",{"kind":"weight","value":4.1,"occurred_at":datetime.now(UTC).isoformat()})
    assert post(client,headers,path,save_payload(stale)).status_code==409
    profile=client.get(f"/api/v1/pets/{adult['id']}/nutrition/profile",headers=headers).json()
    assert profile["needs_reassessment"] and profile["active_plan_id"]==second["id"]
    # Existing quantities do not silently change with a new weight.
    assert second["provenance"]["daily_target_kcal"]==first.json()["provenance"]["daily_target_kcal"]


@pytest.mark.parametrize("identical", [True,False])
def test_concurrent_nutrition_saves(client, headers, adult, db, identical):
    payload=save_payload(preview(client,headers,adult))
    with ThreadPoolExecutor(max_workers=2) as pool:
        rs=list(pool.map(lambda i:post(client,headers,f"/pets/{adult['id']}/nutrition/plans",payload,"same" if identical else str(i)), range(2)))
    assert sorted(r.status_code for r in rs)==([200,200] if identical else [200,409]), [r.text for r in rs]
    with Session(db) as s:
        assert len(s.exec(select(CarePlan)).all())==1
        assert len(s.exec(select(Reminder)).all())==3
        assert len(s.exec(select(PetNutritionProfile)).all())==1


def test_plan_transaction_rollback_and_retry(client, headers, adult, db, monkeypatch):
    from app import nutrition
    original=nutrition.add_plan
    def fail(*args):
        original(*args)
        raise HTTPException(503,"保存失败")
    monkeypatch.setattr(nutrition,"add_plan",fail)
    payload=save_payload(preview(client,headers,adult))
    path=f"/pets/{adult['id']}/nutrition/plans"
    assert post(client,headers,path,payload,"failure").status_code==503
    with Session(db) as s:
        assert not s.exec(select(CarePlan)).all() and not s.exec(select(Reminder)).all() and not s.exec(select(PetNutritionProfile)).all()
        assert not s.exec(select(IdempotencyRecord).where(IdempotencyRecord.key=="failure")).all()
    monkeypatch.setattr(nutrition,"add_plan",original)
    assert post(client,headers,path,payload,"failure").status_code==200


def test_summary_privacy_sources_and_delete_cleanup(client,headers,adult,account,db):
    other=account("other@example.com")
    dog=post(client,other,"/pets",{"name":"秘密犬","species":"dog"}).json()
    post(client,other,f"/pets/{dog['id']}/logs",{"kind":"observation","note":"秘密病史","occurred_at":datetime.now(UTC).isoformat()})
    post(client,headers,f"/pets/{adult['id']}/logs",{"kind":"observation","note":"昨天食欲有变化","occurred_at":datetime.now(UTC).isoformat()})
    post(client,headers,f"/pets/{adult['id']}/logs",{"kind":"observation","note":"超过30天的记录","occurred_at":(datetime.now(UTC)-timedelta(days=40)).isoformat()})
    body={"observation":"呼吸困难","started_at":(datetime.now(UTC)-timedelta(hours=1)).isoformat()}
    summary=post(client,headers,f"/pets/{adult['id']}/visit-summary/preview",body).json()
    assert summary["urgent"] and summary["text"].startswith("请立即")
    assert "昨天食欲有变化" in summary["text"] and "未知 / 未填写" in summary["text"]
    assert "秘密" not in summary["text"] and "超过30天" not in summary["text"]
    for suffix in ["nutrition/preview","nutrition/plans","visit-summary/preview"]:
        payload={} if suffix.endswith("preview") else save_payload(preview(client,headers,adult))
        assert post(client,other,f"/pets/{adult['id']}/{suffix}",payload).status_code==404
    assert client.get(f"/api/v1/pets/{adult['id']}/nutrition/profile",headers=other).status_code==404
    assert post(client,other,"/hospitals/search",{"city":"上海","pet_id":adult["id"]}).status_code==404
    p=preview(client,headers,adult)
    assert post(client,headers,f"/pets/{adult['id']}/nutrition/plans",save_payload(p)).status_code==200
    assert client.delete(f"/api/v1/pets/{adult['id']}",headers={**headers,"Idempotency-Key":str(uuid4())}).status_code==200
    with Session(db) as s:
        assert not s.exec(select(PetNutritionProfile)).all()


def map_mock(monkeypatch, response):
    original=httpx.AsyncClient
    captured=[]
    def handler(request):
        captured.append(request)
        if "coordinate/convert" in request.url.path:
            return httpx.Response(200,json={"status":"1","locations":"120.100000,30.200000"})
        if isinstance(response,Exception):
            raise response
        return httpx.Response(200,json=response)
    monkeypatch.setattr(settings,"AMAP_ENABLED",True)
    monkeypatch.setattr(settings,"AMAP_API_KEY","private-test-key")
    monkeypatch.setattr("app.hospitals.httpx.AsyncClient",lambda **kwargs: original(**kwargs,transport=httpx.MockTransport(handler)))
    return captured


def test_map_conversion_real_fields_not_ratings_and_no_persistence(client,headers,db,monkeypatch):
    captured=map_mock(monkeypatch,{"status":"1","pois":[{"id":"fixture-only","name":"测试接口医院","address":"测试地址","adcode":"330106","location":"120.1,30.2","distance":"300","business":{"tel":"0571-12345678","rating":"5","opentime_today":"全天"}}]})
    query={"longitude":120.12345678,"latitude":30.12345678,"radius_km":10}
    r=post(client,headers,"/hospitals/search",query)
    assert r.status_code==200, r.text
    item=r.json()["items"][0]
    assert item["distance_m"]==300 and item["emergency"]=="待核实" and item["qualification"]=="待核实"
    assert "rating" not in item and "private-test-key" not in r.text
    assert len(captured)==2 and captured[1].url.params["location"]=="120.100000,30.200000"
    usage=client.get("/api/v1/hospitals/usage",headers=headers).json()
    assert usage["day_requests"]==2 and usage["month_requests"]==2
    with Session(db) as s:
        assert not s.exec(select(IdempotencyRecord).where(IdempotencyRecord.key==r.request.headers['Idempotency-Key'])).all()
    regional=post(client,headers,"/hospitals/search",{"city":"杭州","district":"西湖区","region_adcode":"330106"}).json()
    assert regional["items"][0]["distance_m"] is None


@pytest.mark.parametrize("response,expected", [({"status":"1","pois":[]},"empty"),({"status":"0","infocode":"10003"},"unavailable"),(httpx.ReadTimeout("fixture timeout"),"unavailable")])
def test_map_failure_counts_and_limit(client,headers,db,monkeypatch,response,expected):
    captured=map_mock(monkeypatch,response)
    monkeypatch.setattr(settings,"MAP_REQUESTS_PER_DAY",1)
    r=post(client,headers,"/hospitals/search",{"city":"上海","region_adcode":"310000"}).json()
    assert r["status"]==expected and not r["items"]
    again=post(client,headers,"/hospitals/search",{"city":"上海","region_adcode":"310000"}).json()
    assert again["status"]=="unavailable" and "上限" in again["message"]
    assert len(captured)==1
    usage=client.get("/api/v1/hospitals/usage",headers=headers).json()
    assert usage["day_requests"]==1 and usage["month_requests"]==1


def test_no_key_map_fallback_no_call(client,headers,monkeypatch):
    monkeypatch.setattr(settings,"AMAP_API_KEY","")
    r=post(client,headers,"/hospitals/search",{"city":"北京"}).json()
    assert r["status"]=="unavailable" and r["items"]==[] and "uri.amap.com/search" in r["search_url"]
    assert client.get("/api/v1/hospitals/usage",headers=headers).json()["day_requests"]==0


def test_monthly_cap_rolls_back_day_reservation(client,headers,db,monkeypatch):
    from app.hospitals import periods
    captured=map_mock(monkeypatch,{"status":"1","pois":[]})
    monkeypatch.setattr(settings,"MAP_REQUESTS_PER_MONTH",1)
    with Session(db) as s:
        s.add(ExternalApiUsage(provider="amap",period=periods()[1],requests=1))
        s.commit()
    r=post(client,headers,"/hospitals/search",{"city":"上海","region_adcode":"310000"}).json()
    assert r["status"]=="unavailable" and not captured
    usage=client.get("/api/v1/hospitals/usage",headers=headers).json()
    assert usage["month_requests"]==1 and usage["day_requests"]==0 and usage["timezone"]=="Asia/Shanghai"


def test_concurrent_map_cap_is_not_exceeded(db,monkeypatch):
    from app.hospitals import reserve_request, MapUnavailable, map_usage
    monkeypatch.setattr(settings,"MAP_REQUESTS_PER_DAY",1)
    def attempt(_):
        try:
            reserve_request(db)
            return "reserved"
        except MapUnavailable:
            return "limited"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt,range(2)))==["limited","reserved"]
    assert map_usage(db)["day_requests"]==1 and map_usage(db)["month_requests"]==1
