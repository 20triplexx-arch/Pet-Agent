"""Composite workflow tests use fixed, labelled service fixtures, never live Keys."""
import asyncio
import json
import logging

import httpx
import pytest

from app import hospital_agent, hospitals
from app.care_schemas import HospitalQuery
from app.core.config import settings
from test_hospital_search import png


def amap_poi(name="接口测试医院", address="测试路8号", **extra):
    return {"id": name, "name": name, "adcode": "510182", "pname": "四川省", "cityname": "成都市",
        "adname": "彭州市", "address": address, "location": "103.941,30.991",
        "business": {"tel": "028-12345678", "opentime_week": "09:00-18:00"}, **extra}


def tdt_poi(name="接口测试医院", address="测试路8号", **extra):
    return {"hotPointID": name, "name": name, "countyCode": "156510182", "province": "四川省",
        "city": "成都市", "county": "彭州市", "address": address, "phone": "028-12345678", "lonlat": "103.941,30.991", **extra}


def mock_both(monkeypatch, amap=None, tdt=None):
    calls = []
    original = httpx.AsyncClient
    for name in ("AMAP", "TIANDITU"):
        monkeypatch.setattr(settings, name + "_ENABLED", True)
        monkeypatch.setattr(settings, name + "_API_KEY", name.lower() + "-private-fixture")
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("staticmap"):
            return httpx.Response(200, content=png(), headers={"content-type": "image/png"})
        value = ({"status": "1", "pois": [amap_poi()]} if amap is None else amap) if request.url.host == "restapi.amap.com" else (
            {"status": {"infocode": 1000}, "resultType": 1, "pois": [tdt_poi()]} if tdt is None else tdt)
        if isinstance(value, Exception):
            raise value
        return httpx.Response(200, json=value)
    monkeypatch.setattr(hospitals.httpx, "AsyncClient", lambda **kw: original(**kw, transport=httpx.MockTransport(handler)))
    return calls


def query(client, headers, **extra):
    return client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都市", "district": "彭州市", "region_adcode": "510182", **extra})


def test_default_queries_each_once_merges_records_and_private_map(client, headers, account, db, monkeypatch, caplog):
    calls = mock_both(monkeypatch)
    caplog.set_level(logging.INFO, logger="httpx")
    monkeypatch.setattr(settings, "HOSPITAL_MAP_PROVIDER", "tianditu")  # Old setting cannot disable the new workflow.
    response = query(client, headers)
    data = response.json()
    assert response.status_code == 200 and data["provider"] == "auto" and data["status"] == "ok"
    assert len(calls) == 2 and len(data["items"]) == 1 and not data["partial"]
    assert [r["status"] for r in data["provider_results"]] == ["ok", "ok"]
    row = data["items"][0]
    assert [s["provider"] for s in row["sources"]] == ["amap", "tianditu"]
    assert row["map_number"] == "A" and not row["conflicts"]
    assert data["agent_summary"]["merged_duplicates"] == 1 and data["agent_summary"]["mode"] == "local_rules"
    assert "_map_coordinates" not in response.text and "_amap_point" not in response.text
    assert "private-fixture" not in response.text and "private-fixture" not in caplog.text
    assert "api.tianditu.gov.cn" not in caplog.text and "restapi.amap.com" not in caplog.text
    token = data["map_preview_token"]
    other = account("other@example.com")
    assert client.post("/api/v1/hospitals/map", headers=other, json={"token": token}).status_code == 404
    assert client.post("/api/v1/hospitals/map", headers=headers, json={"token": token}).content == png()
    assert hospitals.provider_usage(db, "amap")["day_requests"] == 2
    assert hospitals.provider_usage(db, "tianditu")["day_requests"] == 1
    assert "mid,0x995268,A:" in calls[-1].url.params["markers"]


def test_disagreement_keeps_both_phone_records(client, headers, monkeypatch):
    mock_both(monkeypatch, tdt={"status": {"infocode": 1000}, "resultType": 1, "pois": [tdt_poi(phone="028-87654321")]})
    row = query(client, headers).json()["items"][0]
    assert row["phone"] == "028-12345678" and row["field_sources"]["phone"] == "高德"
    assert {s["phone"] for s in row["sources"]} == {"028-12345678", "028-87654321"}
    assert len(row["conflicts"]) == 1 and "电话" in row["conflicts"][0]


@pytest.mark.parametrize("failed", ["amap", "tianditu"])
def test_timeout_keeps_other_source_without_retry(client, headers, db, monkeypatch, failed):
    calls = mock_both(monkeypatch, **{"tdt" if failed == "tianditu" else failed: httpx.ReadTimeout("private-location-and-private-fixture")})
    response = query(client, headers)
    data = response.json()
    assert data["status"] == "ok" and data["partial"] and len(data["items"]) == 1 and len(calls) == 2
    assert data["items"][0]["sources"][0]["provider"] != failed
    assert "部分来源" in data["message"] and "private-location" not in response.text
    assert hospitals.provider_usage(db, failed)["day_requests"] == 1
    if failed == "amap":
        assert not data["map_preview_token"] and not data["items"][0].get("map_number")


def test_exhausted_amap_still_uses_tianditu_and_aggregate_usage(client, headers, db, monkeypatch):
    calls = mock_both(monkeypatch)
    monkeypatch.setattr(settings, "MAP_REQUESTS_PER_DAY", 1)
    hospitals.reserve_request(db, "amap")
    data = query(client, headers).json()
    assert data["status"] == "ok" and data["partial"] and len(calls) == 1
    assert calls[0].url.host == "api.tianditu.gov.cn" and data["provider_results"][0]["status"] == "skipped"
    assert "上限" in data["provider_results"][0]["message"]
    usage = client.get("/api/v1/hospitals/usage", headers=headers).json()
    assert usage["provider"] == "auto" and usage["day_requests"] == 2
    assert [r["day_requests"] for r in usage["providers"]] == [1, 1]


def test_no_keys_no_requests_and_both_empty_not_success(client, headers, monkeypatch):
    with monkeypatch.context() as guard:
        guard.setattr(hospitals.httpx, "AsyncClient", lambda **kw: pytest.fail("no configured service"))
        data = query(client, headers).json()
        assert data["status"] == "unavailable" and not data["items"]
        assert all(r["status"] == "skipped" for r in data["provider_results"])
    calls = mock_both(monkeypatch, amap={"status": "1", "pois": []}, tdt={"status": {"infocode": 1000}, "resultType": 1, "pois": []})
    data = query(client, headers).json()
    assert data["status"] == "empty" and not data["partial"] and len(calls) == 2 and not data["map_preview_token"]


@pytest.mark.parametrize("extra", [{"radius_km": 20}, {"coordinate_system": "gcj02"}])
def test_tianditu_unsupported_nearby_skips_without_shrinking_radius(client, headers, monkeypatch, extra):
    calls = mock_both(monkeypatch)
    data = query(client, headers, longitude=103.94, latitude=30.99, radius_km=extra.get("radius_km", 1),
        coordinate_system=extra.get("coordinate_system", "gcj02")).json()
    assert data["status"] == "ok" and data["provider_results"][1]["status"] == "skipped"
    assert len(calls) == 1 and calls[0].url.host == "restapi.amap.com"
    assert int(calls[0].url.params["radius"]) == extra.get("radius_km", 1) * 1000


def test_foreign_pet_and_unauthenticated_stop_before_maps(client, headers, account, cat, monkeypatch):
    calls = mock_both(monkeypatch)
    other = account("other@example.com")
    assert query(client, other, pet_id=cat["id"]).status_code == 404
    assert query(client, {}, pet_id=cat["id"]).status_code == 401 and not calls


def candidate(name="测试医院", address="四川省成都市彭州市测试路8号", **extra):
    return {"id": name, "name": name, "address": address, "registered_region": "四川省 · 成都市 · 彭州市",
        "phone": "028-12345678", "opening_hours": "", "opening_status": "待核实", "distance_m": None,
        "source": "测试资料", "source_url": "https://example.invalid/fixture", **extra}


def result(rows, **extra):
    return {"status": "ok" if rows else "empty", "items": rows, "queried_at": "2026-10-14T08:00:00Z", "message": "测试资料", **extra}


@pytest.mark.parametrize("second", [candidate(address="测试路9号"), candidate(address="测试路"), candidate(address=""),
    candidate(registered_region="四川省 · 绵阳市 · 涪城区"), candidate(name="其他医院"), candidate(address="地址未提供8")])
def test_shared_chain_phone_or_missing_address_cannot_merge(second):
    rows, count, unique = hospital_agent.merge_candidates({"amap": result([candidate()]), "tianditu": result([second])}, False)
    assert len(rows) == unique == 2 and count == 0


def test_merge_fills_missing_fields_and_preserves_hours_conflict():
    first = candidate(phone="", opening_hours="09:00-18:00")
    second = candidate(address="测试路8号", phone="028-87654321", opening_hours="24小时")
    rows, count, _ = hospital_agent.merge_candidates({"amap": result([first]), "tianditu": result([second])}, False)
    assert count == 1 and rows[0]["phone"] == second["phone"] and rows[0]["field_sources"]["phone"] == "天地图"
    assert "营业时间" in rows[0]["conflicts"][0] and rows[0]["opening_hours"] == first["opening_hours"]


def test_administrative_interleave_and_nearby_distance_order_and_cap():
    amap = [candidate(name=f"高德测试{i}", distance_m=1000 + i) for i in range(10)]
    tdt = [candidate(name=f"天地图测试{i}", distance_m=100 + i, distance_kind="estimated") for i in range(10)]
    source = {"amap": result(amap), "tianditu": result(tdt)}
    rows, _, unique = hospital_agent.merge_candidates(source, False)
    assert unique == 20 and len(rows) == 10 and [r["sources"][0]["provider"] for r in rows[:4]] == ["amap", "tianditu"] * 2
    rows, _, _ = hospital_agent.merge_candidates(source, True)
    assert all(r["name"].startswith("天地图") for r in rows) and [r["distance_m"] for r in rows] == sorted(r["distance_m"] for r in rows)


def test_only_visible_amap_points_get_corresponding_map_numbers(db, monkeypatch):
    hospitals._map_previews.clear()
    amap = [candidate(name=f"高德测试{i}") for i in range(10)]
    tdt = [candidate(name=f"天地图测试{i}") for i in range(10)]
    async def provider(bind, query, name):
        return result(amap if name == "amap" else tdt, _map_coordinates={i: (104 + i / 100, 30.6) for i in range(10)} if name == "amap" else {})
    monkeypatch.setattr(hospital_agent, "run_provider", provider)
    data = asyncio.run(hospital_agent.find_hospital_candidates(db, HospitalQuery(city="成都"), "test-owner"))
    assert [r.get("map_number") for r in data["items"]] == ["A", None, "C", None, "E", None, "G", None, "I", None]
    points = hospitals._map_previews[data["map_preview_token"]][2]
    assert [point[0] for point in points] == [1, 3, 5, 7, 9] and all(point[1] < 104.05 for point in points)
    assert "_amap_point" not in json.dumps(data) and "_map_coordinates" not in json.dumps(data)


def test_region_disagreement_never_mixes_cities(db, monkeypatch):
    async def provider(bind, query, name):
        return result([candidate()], region_adcode="510182" if name == "amap" else "110102")
    monkeypatch.setattr(hospital_agent, "run_provider", provider)
    data = asyncio.run(hospital_agent.find_hospital_candidates(db, HospitalQuery(city="成都"), "test-owner"))
    assert data["status"] == "unavailable" and not data["items"] and "匹配不一致" in data["message"] and not data["map_preview_token"]


def test_unexpected_adapter_fault_is_isolated_and_private(db, monkeypatch):
    monkeypatch.setattr(hospital_agent, "provider_usage", lambda *args: {"enabled": True, "day_requests": 0, "day_limit": 50, "month_requests": 0, "month_limit": 500})
    async def broken(*args, **kwargs):
        raise RuntimeError("secret-key-and-private-position")
    monkeypatch.setattr(hospital_agent, "search_amap_hospitals", broken)
    data = asyncio.run(hospital_agent.run_provider(db, HospitalQuery(city="成都"), "amap"))
    assert data["status"] == "unavailable" and "secret" not in json.dumps(data)
