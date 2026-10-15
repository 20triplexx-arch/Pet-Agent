import struct
import zlib
import httpx
import pytest
from app.core.config import settings
from app import hospitals


def node(name, code, level, children=None):
    return {"name": name, "adcode": code, "level": level, "districts": children or []}


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 600, 320, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress((b"\0" + b"\xe8\xf1\xeb" * 600) * 320)) + chunk(b"IEND", b"")


@pytest.fixture(autouse=True)
def clear_memory():
    hospitals._region_cache.clear()
    hospitals._map_previews.clear()


def mock_map(monkeypatch, responder):
    original = httpx.AsyncClient
    requests = []
    def handler(request):
        requests.append(request)
        value = responder(request)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, bytes):
            return httpx.Response(200, content=value, headers={"Content-Type": "image/png"})
        return httpx.Response(200, json=value)
    monkeypatch.setattr(settings, "AMAP_ENABLED", True)
    monkeypatch.setattr(settings, "AMAP_API_KEY", "private-test-key")
    monkeypatch.setattr(hospitals.httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    return requests


def test_region_auth_validation_and_no_key(client, headers):
    assert client.get("/api/v1/hospitals/regions?keywords=四川省").status_code == 401
    for query in ("keywords=川", "keywords=四川省&province_code=510100", "keywords=四川省&province_code=710000"):
        assert client.get("/api/v1/hospitals/regions?" + query, headers=headers).status_code == 422
    response = client.get("/api/v1/hospitals/regions?keywords=四川省", headers=headers).json()
    assert response["status"] == "unavailable" and response["regions"] == []
    assert client.get("/api/v1/hospitals/usage", headers=headers).json()["day_requests"] == 0


def test_province_children_cache_and_private_fields(client, headers, db, monkeypatch):
    rows = node("四川省", "510000", "province", [node("成都市", "510100", "city"), node("绵阳市", "510700", "city"), node("南充市", "511300", "city")])
    rows["center"] = "104.1,30.2"
    calls = mock_map(monkeypatch, lambda request: {"status": "1", "districts": [rows]})
    url = "/api/v1/hospitals/regions?keywords=四川省"
    response = client.get(url, headers=headers)
    data = response.json()
    assert data["status"] == "ok" and not data["cached"]
    assert [row["name"] for row in data["regions"][0]["children"]] == ["成都市", "绵阳市", "南充市"]
    assert "private-test-key" not in response.text and "center" not in response.text
    assert client.get(url, headers=headers).json()["cached"]
    assert len(calls) == 1 and calls[0].url.params["extensions"] == "base"
    assert hospitals.map_usage(db)["day_requests"] == 1
    for key, (time, value) in list(hospitals._region_cache.items()):
        hospitals._region_cache[key] = (time - hospitals.REGION_CACHE_SECONDS - 1, value)
    assert not client.get(url, headers=headers).json()["cached"]
    assert len(calls) == 2


def test_municipality_and_province_filter(client, headers, monkeypatch):
    raw = node("北京市", "110000", "province", [node("市辖区", "110100", "city", [node("朝阳区", "110105", "district")])])
    calls = mock_map(monkeypatch, lambda request: {"status": "1", "districts": [raw, node("成都市", "510100", "city")]})
    data = client.get("/api/v1/hospitals/regions?keywords=北京&province_code=110000", headers=headers).json()
    assert len(data["regions"]) == 1
    assert data["regions"][0]["children"][0]["name"] == "朝阳区"
    assert calls[0].url.params["filter"] == "110000"


@pytest.mark.parametrize("payload,status", [({"status": "1", "districts": []}, "empty"), ({"status": "1", "districts": {}}, "unavailable"), ({"status": "0"}, "unavailable"), (httpx.ReadTimeout("mock"), "unavailable")])
def test_region_failures_count_and_manual_retry(client, headers, db, monkeypatch, payload, status):
    calls = mock_map(monkeypatch, lambda request: payload)
    monkeypatch.setattr(settings, "MAP_REQUESTS_PER_DAY", 1)
    data = client.get("/api/v1/hospitals/regions?keywords=成都", headers=headers).json()
    assert data["status"] == status and data["regions"] == []
    assert hospitals.map_usage(db)["day_requests"] == 1
    blocked = client.get("/api/v1/hospitals/regions?keywords=绵阳", headers=headers).json()
    assert blocked["status"] == "unavailable" and "上限" in blocked["message"] and len(calls) == 1


def hospital_payload():
    return {"status": "1", "pois": [
        {"id": "current", "name": "测试医院", "adcode": "510107", "cityname": "成都市", "pname": "四川省", "adname": "武侯区", "location": "104.05,30.63", "business": {"rating": "5", "tel": "028-12345678"}},
        {"id": "outside", "name": "同名地区医院", "adcode": "110105", "location": "116.45,39.9"},
        {"id": "unknown", "name": "未提供区域编码的医院", "location": "104.1,30.6"}]}


def test_region_code_strict_search_no_rating_and_map_privacy(client, headers, monkeypatch):
    calls = mock_map(monkeypatch, lambda request: hospital_payload())
    response = client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都", "district": "武侯区", "region_adcode": "510107"})
    data = response.json()
    assert calls[0].url.params["region"] == "510107" and calls[0].url.params["city_limit"] == "true"
    assert len(data["items"]) == 1 and data["items"][0]["map_number"] == "A"
    assert data["items"][0]["rating_status"] == "unavailable" and "rating" not in data["items"][0]
    assert data["items"][0]["qualification"] == "待核实" and data["map_preview_token"]
    assert "private-test-key" not in response.text and "map_points" not in response.text


def test_map_image_auth_owner_cache_and_token_expiry(client, headers, account, db, monkeypatch):
    calls = mock_map(monkeypatch, lambda request: png() if "staticmap" in request.url.path else hospital_payload())
    data = client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都", "region_adcode": "510100"}).json()
    payload = {"token": data["map_preview_token"]}
    assert client.post("/api/v1/hospitals/map", json=payload).status_code == 401
    other = account("other@example.com")
    assert client.post("/api/v1/hospitals/map", headers=other, json=payload).status_code == 404
    image = client.post("/api/v1/hospitals/map", headers=headers, json=payload)
    assert image.status_code == 200 and image.content == png() and image.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/hospitals/map", headers=headers, json=payload).content == png()
    assert len(calls) == 2 and hospitals.map_usage(db)["day_requests"] == 2
    assert calls[-1].url.params["markers"].startswith("mid,0x995268,A:104.050000,30.630000")
    entry = hospitals._map_previews[payload["token"]]
    hospitals._map_previews[payload["token"]] = (entry[0] - 601, *entry[1:])
    assert client.post("/api/v1/hospitals/map", headers=headers, json=payload).status_code == 404


@pytest.mark.parametrize("value", [b"broken", b'{"status":"0"}', httpx.ReadTimeout("mock")])
def test_map_failure_preserves_list_and_counts(client, headers, db, monkeypatch, value):
    calls = mock_map(monkeypatch, lambda request: value if "staticmap" in request.url.path else hospital_payload())
    data = client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都", "region_adcode": "510100"}).json()
    assert len(data["items"]) == 1
    response = client.post("/api/v1/hospitals/map", headers=headers, json={"token": data["map_preview_token"]})
    assert response.status_code == 503 and len(calls) == 2 and hospitals.map_usage(db)["day_requests"] == 2


def test_map_cap_no_points_and_agent_has_no_map_token(client, headers, db, monkeypatch):
    calls = mock_map(monkeypatch, lambda request: hospital_payload())
    monkeypatch.setattr(settings, "MAP_REQUESTS_PER_DAY", 1)
    data = client.post("/api/v1/hospitals/search", headers=headers, json={"city": "成都", "region_adcode": "510100"}).json()
    assert client.post("/api/v1/hospitals/map", headers=headers, json={"token": data["map_preview_token"]}).status_code == 503
    assert len(calls) == 1
    params = hospitals.static_map_params([(1, 104.05, 30.63)])
    assert params["location"] == "104.050000,30.630000"
    assert hospitals.static_map_params([(1, 75, 20), (2, 130, 50)])["zoom"] <= 4
    ten = hospitals.static_map_params([(number, 104 + number / 100, 30.6) for number in range(1, 11)])
    assert "mid,0x995268,J:" in ten["markers"] and len(ten["markers"].split("|")) == 10
