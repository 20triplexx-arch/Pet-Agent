import logging
import httpx
import pytest
from app import hospitals
from test_hospital_search import mock_map, node


@pytest.fixture(autouse=True)
def clear_region_cache():
    hospitals._region_cache.clear()


def geocode(code="510182", level="乡镇", location="103.94,30.99", label="四川省成都市彭州市天彭街道"):
    return {"status": "1", "geocodes": [{"adcode": code, "level": level, "location": location, "formatted_address": label}]}


def query(client, headers, **kwargs):
    return client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都市", "district": "彭州市", "region_adcode": "510182", **kwargs})


def near_pois():
    return {"status": "1", "pois": [
        {"id": "near", "name": "测试近处医院", "adcode": "510182", "pname": "四川省", "cityname": "成都市", "adname": "彭州市", "address": "测试路8号", "location": "103.941,30.991", "distance": "200"},
        {"id": "far", "name": "错误远处医院", "adcode": "510182", "location": "103.99,31.09", "distance": "50"},
        {"id": "no-location", "name": "位置未核实", "adcode": "510182"}]}


def test_streets_keep_same_district_codes_and_distinct_names(client, headers, monkeypatch):
    rows = node("彭州市", "510182", "district", [node("天彭街道", "510182", "street"), node("致和街道", "510182", "street"), node("九尺镇", "510182", "street")])
    mock_map(monkeypatch, lambda request: {"status": "1", "districts": [rows]})
    response = client.get("/api/v1/hospitals/regions?keywords=510182", headers=headers)
    data = response.json()
    assert [child["name"] for child in data["regions"][0]["children"]] == ["天彭街道", "致和街道", "九尺镇"]
    assert "location" not in response.text and "center" not in response.text


def test_street_one_km_uses_matched_point_and_filters_far_pois(client, headers, db, monkeypatch):
    calls = mock_map(monkeypatch, lambda request: geocode() if "geocode/geo" in request.url.path else near_pois())
    response = query(client, headers, street="天彭街道", radius_km=1)
    data = response.json()
    assert data["status"] == "ok" and len(data["items"]) == 1
    assert data["items"][0]["name"] == "测试近处医院"
    assert data["items"][0]["address"] == "四川省成都市彭州市测试路8号"
    assert calls[0].url.params["address"] == "成都市彭州市天彭街道"
    assert calls[0].url.params["city"] == "510100"
    assert calls[1].url.path.endswith("place/around") and calls[1].url.params["radius"] == "1000"
    assert calls[1].url.params["location"] == "103.940000,30.990000"
    assert "天彭街道" in data["scope_label"] and "1 公里" in data["scope_label"]
    assert "不是实时定位" in data["scope_note"] and hospitals.map_usage(db)["day_requests"] == 2
    assert not hospitals._region_cache, "No precise address cache"


def test_combined_manual_city_county_resolves_adcode_never_beijing(client, headers, monkeypatch):
    payload = near_pois()
    payload["pois"].append({"id": "beijing", "name": "错误北京医院", "adcode": "110102"})
    calls = mock_map(monkeypatch, lambda request: geocode(level="区县", label="四川省成都市彭州市") if "geocode/geo" in request.url.path else payload)
    response = client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都市彭州市"})
    data = response.json()
    assert data["status"] == "ok" and all(item["name"] != "错误北京医院" for item in data["items"])
    assert calls[1].url.params["region"] == "510182" and calls[1].url.params["city_limit"] == "true"
    assert "彭州市" in data["scope_label"] and "整片" in data["scope_note"]


@pytest.mark.parametrize("payload", [
    {"status": "1", "geocodes": []},
    {"status": "1", "geocodes": [{"adcode": "510182"}, {"adcode": "110102"}]},
    geocode(code="110102"), geocode(level="区县"), geocode(level="市"), geocode(level="未知"), geocode(location="bad"),
    httpx.ReadTimeout("fixture")])
def test_bad_coarse_ambiguous_or_outside_point_never_widens(client, headers, monkeypatch, payload):
    calls = mock_map(monkeypatch, lambda request: payload)
    data = query(client, headers, street="天彭街道", radius_km=1).json()
    assert data["status"] == "unavailable" and not data["items"]
    assert len(calls) == 1 and calls[0].url.path.endswith("geocode/geo")
    assert "place/text" not in str(calls[0].url) and not data.get("map_preview_token")


def test_precise_detail_three_km_no_duplicate_address_and_no_secret_log(client, headers, monkeypatch, caplog):
    calls = mock_map(monkeypatch, lambda request: geocode(level="门牌号", label="四川省成都市彭州市测试路8号") if "geocode/geo" in request.url.path else near_pois())
    caplog.set_level(logging.INFO, logger="httpx")
    data = query(client, headers, street="天彭街道", address_detail="测试路8号", radius_km=3).json()
    assert data["status"] == "ok" and calls[1].url.params["radius"] == "3000"
    assert "private-test-key" not in caplog.text and "restapi.amap.com" not in caplog.text
    assert hospitals.full_address({"pname":"北京市", "cityname":"北京市", "adname":"朝阳区", "address":"北京市朝阳区测试路8号"}) == "北京市朝阳区测试路8号"
    assert "未提供街道/门牌" in hospitals.full_address({"pname":"四川省", "cityname":"成都市", "adname":"彭州市"})


def test_precision_validation_and_quota_stop_before_poi(client, headers, db, monkeypatch):
    calls = mock_map(monkeypatch, lambda request: geocode())
    monkeypatch.setattr(hospitals.settings, "MAP_REQUESTS_PER_DAY", 1)
    data = query(client, headers, street="天彭街道", radius_km=1).json()
    assert data["status"] == "unavailable" and "上限" in data["message"] and len(calls) == 1
    assert hospitals.map_usage(db)["day_requests"] == 1
    assert query(client, headers, radius_km=0).status_code == 422
    assert query(client, headers, street="天彭街道", longitude=103.94, latitude=30.99).status_code == 422
