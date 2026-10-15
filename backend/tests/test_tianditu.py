import json
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from app import hospitals, tianditu
from app.core.config import settings


def poi(name="接口测试医院", code="156510182", lonlat="103.941,30.991", **extra):
    return {"hotPointID": name, "name": name, "countyCode": code, "province": "四川省", "city": "成都市",
        "county": "彭州市", "address": "测试路8号", "phone": "028-12345678;INVALID", "lonlat": lonlat, **extra}


def payload(rows=None, **extra):
    return {"status": {"infocode": 1000}, "resultType": 1, "pois": [poi()] if rows is None else rows, **extra}


def mock_tdt(monkeypatch, responder):
    original, calls = httpx.AsyncClient, []
    def handler(request):
        calls.append(request)
        assert request.url.host == "api.tianditu.gov.cn" and request.url.path == "/v2/search"
        result = responder(request)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json=result)
    monkeypatch.setattr(settings, "TIANDITU_ENABLED", True)
    monkeypatch.setattr(settings, "TIANDITU_API_KEY", "tdt-private-test-key")
    monkeypatch.setattr(tianditu.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    return calls


def fields(request):
    return json.loads(request.url.params["postStr"])


def query(client, headers, **extra):
    return client.post("/api/v1/hospitals/search", headers=headers, json={"provider": "tianditu",
        "city": "成都市", "district": "彭州市", "region_adcode": "510182", **extra})


def usage(client, headers):
    return client.get("/api/v1/hospitals/usage?provider=tianditu", headers=headers).json()


def test_no_key_provider_validation_and_no_call(client, headers, db, monkeypatch):
    monkeypatch.setattr(tianditu.httpx, "AsyncClient", lambda **kwargs: pytest.fail("No external call without Key"))
    data = query(client, headers).json()
    assert data["status"] == "unavailable" and not data["items"] and "服务端Key" in data["message"]
    assert usage(client, headers)["day_requests"] == 0
    assert client.get("/api/v1/hospitals/usage?provider=unknown", headers=headers).status_code == 422
    assert query(client, headers, provider="https://evil.invalid").status_code == 422
    assert client.post("/api/v1/hospitals/search", json={"provider": "tianditu", "city": "成都"}).status_code == 401


def test_regional_fields_sources_privacy_and_filtered_codes(client, headers, db, monkeypatch, caplog):
    calls = mock_tdt(monkeypatch, lambda request: payload([poi(), poi("错误北京医院", "156110102"), poi("错误省级医院", "156510000"), poi()]))
    caplog.set_level(logging.INFO, logger="httpx")
    response = query(client, headers)
    data = response.json()
    assert data["status"] == "ok" and len(data["items"]) == 1
    assert fields(calls[0]) == {"keyWord": "宠物医院", "specify": "156510182", "queryType": 12, "start": 0, "count": 10, "show": 2}
    assert calls[0].url.params["tk"] == "tdt-private-test-key"
    item = data["items"][0]
    assert item["source_url"] == tianditu.SOURCE and item["source"] == "天地图地名搜索"
    assert item["address"] == "四川省成都市彭州市测试路8号" and item["phone"] == "028-12345678"
    assert item["distance_m"] is None and item["opening_hours"] == ""
    assert item["emergency"] == item["qualification"] == "待核实" and item["rating_status"] == "unavailable"
    assert data["map_preview_token"] is None and "按名称" in item["match_reason"]
    assert "103.941" not in response.text and "tdt-private-test-key" not in response.text
    assert "api.tianditu.gov.cn" not in caplog.text and "tdt-private-test-key" not in caplog.text
    assert "center=" not in data["search_url"] and "to=" not in item["navigation_url"]
    assert usage(client, headers)["day_requests"] == 1 and hospitals.map_usage(db, "amap")["day_requests"] == 0


def test_manual_region_resolution_uses_returned_country_code(client, headers, monkeypatch):
    def respond(request):
        if fields(request)["keyWord"] == "成都市彭州市":
            return {"status": {"infocode": "1000"}, "resultType": 3, "area": {"name": "成都市彭州市", "adminCode": 156510182}}
        return payload()
    calls = mock_tdt(monkeypatch, respond)
    data = query(client, headers, region_adcode=None).json()
    assert data["status"] == "ok" and len(calls) == 2 and fields(calls[1])["specify"] == "156510182"


@pytest.mark.parametrize("area", [[], [{"name": "北京市", "adminCode": "156110000"}], [{"name": "四川省", "adminCode": "156510000"}],
    [{"name": "彭州市", "adminCode": "156510182"}, {"name": "彭州市", "adminCode": "156510183"}]])
def test_unreliable_manual_region_never_searches_hospitals(client, headers, monkeypatch, area):
    calls = mock_tdt(monkeypatch, lambda request: {"status": {"infocode": 1000}, "resultType": 3, "area": area})
    data = query(client, headers, region_adcode=None).json()
    assert data["status"] == "unavailable" and not data["items"] and len(calls) == 1


def test_specific_point_radius_does_not_mix_gps_or_coordinates(client, headers, monkeypatch):
    def respond(request):
        if fields(request)["queryType"] == 7:
            return payload([poi("测试小区", lonlat="103.94,30.99", address="成都市彭州市测试小区")])
        return payload([poi(), poi("错误远处医院", lonlat="104.0,31.1"), poi("无坐标医院", lonlat=""), poi("错误坐标", lonlat="nan,nan")])
    calls = mock_tdt(monkeypatch, respond)
    data = query(client, headers, street="天彭街道", address_detail="测试小区", radius_km=1).json()
    assert data["status"] == "ok" and len(data["items"]) == 1 and len(calls) == 2
    assert "测试小区附近 1 公里" in data["scope_label"]
    assert fields(calls[1])["pointLonlat"] == "103.940000,30.990000" and fields(calls[1])["queryRadius"] == 1000
    assert fields(calls[1])["queryType"] == 3 and data["items"][0]["distance_m"] < 1000


@pytest.mark.parametrize("rows,result_type", [([], 1), ([poi("其他地点")], 1), ([poi("测试小区"), poi("测试小区", lonlat="103.942,30.992")], 1), ([], 3), ([poi("测试小区", code="156110102")], 1)])
def test_ambiguous_coarse_or_wrong_place_stops_before_around(client, headers, monkeypatch, rows, result_type):
    calls = mock_tdt(monkeypatch, lambda request: payload(rows, resultType=result_type))
    data = query(client, headers, address_detail="测试小区", radius_km=1).json()
    assert data["status"] == "unavailable" and not data["items"] and len(calls) == 1


def test_gps_native_coordinate_search_and_unsupported_inputs_no_request(client, headers, monkeypatch):
    calls = mock_tdt(monkeypatch, lambda request: payload())
    data = query(client, headers, longitude=103.94, latitude=30.99, radius_km=3).json()
    assert data["status"] == "ok" and len(calls) == 1 and fields(calls[0])["queryRadius"] == 3000
    for extra in ({"radius_km": 20}, {"coordinate_system": "gcj02"}):
        blocked = query(client, headers, longitude=103.94, latitude=30.99, **extra).json()
        assert blocked["status"] == "unavailable" and len(calls) == 1


@pytest.mark.parametrize("value", [{"status": {"infocode": 1006}}, {"status": "0"}, ["invalid"],
    {"status": {"infocode": 1000}, "pois": "invalid"}, httpx.ReadTimeout("private-test-address")])
def test_errors_count_once_without_success_or_auto_fallback(client, headers, db, monkeypatch, value):
    calls = mock_tdt(monkeypatch, lambda request: value)
    data = query(client, headers).json()
    assert data["status"] == "unavailable" and not data["items"] and len(calls) == 1
    assert usage(client, headers)["day_requests"] == 1 and hospitals.map_usage(db, "amap")["day_requests"] == 0
    assert "private-test-address" not in data["message"]


def test_empty_response_is_not_success(client, headers, monkeypatch):
    mock_tdt(monkeypatch, lambda request: payload([]))
    data = query(client, headers).json()
    assert data["status"] == "empty" and not data["items"]


@pytest.mark.parametrize("resolve,expected", [("Key权限类型为:浏览器端，请使用浏览器访问！", "浏览器端"), ("private-test-address and tdt-private-test-key", "权限类型不匹配")])
def test_real_http_403_permission_type_is_actionable_without_echo(client, headers, db, monkeypatch, resolve, expected):
    calls = mock_tdt(monkeypatch, lambda request: httpx.Response(403, json={"code": 301012, "msg": "权限类型错误", "resolve": resolve}))
    response = query(client, headers)
    data = response.json()
    assert data["status"] == "unavailable" and not data["items"] and "301012" in data["message"] and expected in data["message"]
    assert "tdt-private-test-key" not in response.text and "private-test-address" not in response.text
    assert len(calls) == 1 and hospitals.map_usage(db, "tianditu")["day_requests"] == 1


def test_independent_limit_rollbacks_concurrency_and_settings_privacy(client, headers, db, monkeypatch):
    calls = mock_tdt(monkeypatch, lambda request: payload())
    monkeypatch.setattr(settings, "TIANDITU_REQUESTS_PER_DAY", 1)
    def attempt(_):
        try:
            hospitals.reserve_request(db, "tianditu")
            return "reserved"
        except hospitals.MapUnavailable:
            return "limited"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ["limited", "reserved"]
    data = query(client, headers).json()
    assert data["status"] == "unavailable" and "上限" in data["message"] and not calls
    assert usage(client, headers)["day_requests"] == 1
    monkeypatch.setattr(settings, "TIANDITU_REQUESTS_PER_DAY", 50)
    monkeypatch.setattr(settings, "TIANDITU_REQUESTS_PER_MONTH", 1)
    assert query(client, headers).json()["status"] == "unavailable" and not calls
    assert usage(client, headers)["day_requests"] == 1
    response = client.get("/api/v1/hospitals/usage", headers=headers)
    assert "tdt-private-test-key" not in response.text and "TIANDITU_API_KEY" not in repr(settings)
    assert [row["provider"] for row in response.json()["providers"]] == ["amap", "tianditu"]


def test_other_users_pet_stops_before_service(client, headers, account, cat, monkeypatch):
    calls = mock_tdt(monkeypatch, lambda request: payload())
    other = account("other@example.com")
    assert query(client, other, pet_id=cat["id"]).status_code == 404 and not calls


def test_default_combines_maps_and_keeps_explicit_adapter_compatibility(client, headers, monkeypatch):
    calls = mock_tdt(monkeypatch, lambda request: payload())
    monkeypatch.setattr(settings, "HOSPITAL_MAP_PROVIDER", "tianditu")
    data = query(client, headers, provider=None).json()
    assert data["provider"] == "auto" and len(calls) == 1
    assert data["items"][0]["sources"][0]["provider"] == "tianditu"
    assert client.get("/api/v1/hospitals/usage", headers=headers).json()["provider"] == "auto"
    assert query(client, headers, provider="amap").json()["provider"] == "amap" and len(calls) == 1


def test_live_administrative_poi_class_and_hierarchy(client, headers, monkeypatch):
    def respond(request):
        if fields(request)["queryType"] == 7:
            return payload([poi("彭州市", typeName="区县级地名"), poi("成都市彭州市其他机构", typeName="政府机关")])
        return payload()
    calls = mock_tdt(monkeypatch, respond)
    data = query(client, headers, region_adcode=None).json()
    assert data["status"] == "ok" and len(calls) == 2 and fields(calls[1])["specify"] == "156510182"


@pytest.mark.parametrize("rows", [[poi("彭州市", city="其他市", typeName="区县级地名")],
    [poi("彭州市", typeName="政府机关")], [poi("彭州市", typeName="区县级地名"), poi("彭州市", typeName="区县级地名")]])
def test_poi_region_rejects_wrong_hierarchy_class_or_duplicate(client, headers, monkeypatch, rows):
    calls = mock_tdt(monkeypatch, lambda request: payload(rows))
    data = query(client, headers, region_adcode=None).json()
    assert data["status"] == "unavailable" and not data["items"] and len(calls) == 1


def test_exact_landmark_outranks_fuzzy_names_without_picking_first(client, headers, monkeypatch):
    def respond(request):
        if fields(request)["queryType"] == 7:
            assert fields(request)["keyWord"] == "成都市彭州市人民政府"
            return payload([poi("彭州市人民政府第二办公区"), poi("彭州市人民政府", lonlat="103.94,30.99"), poi("彭州市人民政府停车场")])
        assert fields(request)["pointLonlat"] == "103.940000,30.990000"
        return payload()
    calls = mock_tdt(monkeypatch, respond)
    data = query(client, headers, address_detail="彭州市人民政府", radius_km=1).json()
    assert data["status"] == "ok" and len(calls) == 2 and "1 公里" in data["scope_label"]


def test_area_without_parent_must_not_guess_same_named_county(client, headers, monkeypatch):
    calls = mock_tdt(monkeypatch, lambda request: {"status": {"infocode": 1000}, "resultType": 3,
        "area": {"name": "鼓楼区", "adminCode": "156320302"}})
    data = query(client, headers, city="南京市", district="鼓楼区", region_adcode=None).json()
    assert data["status"] == "unavailable" and not data["items"] and len(calls) == 1
