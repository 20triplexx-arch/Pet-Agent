"""Server-side AMap adapter. No coordinates, keys or POI mirrors are persisted."""
import asyncio
from collections import OrderedDict
from hashlib import sha256
from time import monotonic
from weakref import WeakKeyDictionary
from secrets import token_urlsafe
from math import atan, degrees, log, pi, radians, sin, sinh, cos, asin, sqrt
from datetime import datetime, UTC
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import re
import struct
import logging
import httpx
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from app.core.config import settings
from app.models import ExternalApiUsage


class HideAMapRequest(logging.Filter):
    def filter(self, record):
        return not any(host in record.getMessage() for host in ("restapi.amap.com", "api.tianditu.gov.cn"))


# HTTPX INFO includes the full external URL; keep keys and entered addresses out.
logging.getLogger("httpx").addFilter(HideAMapRequest())


class MapUnavailable(Exception):
    pass


REGION_SOURCE = "https://developer.amap.com/api/webservice/guide/api/district"
RATING_SOURCE = "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch"
# Public administrative names only, no POIs/coordinates. Bounded six-hour memory cache.
_region_cache = OrderedDict()
_region_locks = WeakKeyDictionary()
REGION_CACHE_SECONDS = 6 * 60 * 60
_map_previews = OrderedDict()
_map_locks = WeakKeyDictionary()


def map_preview(owner, points):
    token = token_urlsafe(32)
    now = monotonic()
    for key in list(_map_previews):
        if now - _map_previews[key][0] >= 600:
            _map_previews.pop(key, None)
    _map_previews[token] = (now, owner, points, None)
    while len(_map_previews) > 100:
        _map_previews.popitem(last=False)
    return token


def static_map_params(points):
    lngs = [point[1] for point in points]
    # Web Mercator bounds keep every hospital in the thumbnail at any latitude.
    ys = [(1 - log((1 + sin(radians(point[2]))) / (1 - sin(radians(point[2])))) / (2 * pi)) / 2 for point in points]
    center_lng = (min(lngs) + max(lngs)) / 2
    center_y = (min(ys) + max(ys)) / 2
    center_lat = degrees(atan(sinh(pi * (1 - 2 * center_y))))
    span_x, span_y = (max(lngs) - min(lngs)) / 360, max(ys) - min(ys)
    zooms = [log(pixels / (256 * span), 2) for pixels, span in ((520, span_x), (220, span_y)) if span > 0]
    zoom = min(16, max(3, int(min(zooms)))) if zooms else 15
    return {"location": f"{center_lng:.6f},{center_lat:.6f}", "zoom": zoom, "size": "600*320",
        "markers": "|".join(f"mid,0x995268,{chr(64 + number)}:{lng:.6f},{lat:.6f}" for number, lng, lat in points)}


async def hospital_map(bind, token, owner):
    lock = _map_locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
    async with lock:
        return await _hospital_map(bind, token, owner)


async def _hospital_map(bind, token, owner):
    entry = _map_previews.get(token)
    if not entry or entry[1] != owner or monotonic() - entry[0] >= 600:
        raise HTTPException(404, "地图预览已过期，请重新查询医院。")
    if not settings.AMAP_ENABLED or not settings.AMAP_API_KEY:
        raise HTTPException(503, "地图服务未启用，可打开高德搜索。")
    if entry[3] is not None:
        return entry[3]
    try:
        reserve_request(bind)
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.get("https://restapi.amap.com/v3/staticmap",
                params={**static_map_params(entry[2]), "key": settings.AMAP_API_KEY})
            response.raise_for_status()
            image = response.content
        if (len(image) < 45 or len(image) > 2 * 1024 * 1024 or not image.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
            or struct.unpack(">II", image[16:24]) != (600, 320) or not image.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")):
            raise MapUnavailable("地图图片暂不可用，医院列表仍可查看。")
        _map_previews[token] = (*entry[:3], image)
        return image
    except MapUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    except httpx.HTTPError:
        raise HTTPException(503, "地图图片加载失败或超时，医院列表仍可查看。") from None


def region_node(raw, depth=0):
    if not isinstance(raw, dict) or depth > 1:
        return None
    code, name, level = scalar(raw.get("adcode"), 6), scalar(raw.get("name"), 80), raw.get("level")
    if not re.fullmatch(r"[1-6]\d{5}", code) or not name or level not in {"province", "city", "district", "street"}:
        return None
    children = raw.get("districts", [])
    if not isinstance(children, list):
        raise MapUnavailable("区域资料格式异常，请手动输入城市和区县。")
    if depth == 0 and code in {"110000", "120000", "310000", "500000"}:
        children = [district for child in children for district in (child.get("districts", []) if isinstance(child, dict) and child.get("level") == "city" else [child])]
    return {"adcode": code, "name": name, "level": level,
        "children": [node for child in children[:100] if (node := region_node(child, depth + 1))] if depth == 0 else []}


async def search_regions(bind, keywords, province_code=None):
    result = {"status": "unavailable", "regions": [], "source": "高德行政区域查询",
        "source_url": REGION_SOURCE, "queried_at": datetime.now(UTC).isoformat(), "cached": False,
        "message": "区域候选未启用，可手动输入城市和区县。"}
    if not settings.AMAP_ENABLED or not settings.AMAP_API_KEY:
        return result
    keyword = keywords.strip()
    if len(keyword) < 2:
        return {**result, "status": "empty", "message": "请输入至少两个字的省市名称。"}
    key = (str(bind.url), sha256(settings.AMAP_API_KEY.encode()).hexdigest(), keyword, province_code)
    loop = asyncio.get_running_loop()
    lock = _region_locks.setdefault(loop, asyncio.Lock())
    async with lock:
        cached = _region_cache.get(key)
        if cached and monotonic() - cached[0] < REGION_CACHE_SECONDS:
            _region_cache.move_to_end(key)
            return {**cached[1], "cached": True}
        _region_cache.pop(key, None)
        try:
            params = {"keywords": keyword, "subdistrict": 2, "extensions": "base", "offset": 20, "page": 1}
            if province_code:
                params["filter"] = province_code
            payload = await amap_request(bind, "v3/config/district", params)
            raw = payload.get("districts")
            if not isinstance(raw, list):
                raise MapUnavailable("区域资料格式异常，请手动输入城市和区县。")
            nodes = [node for row in raw[:20] if (node := region_node(row))]
            if province_code:
                nodes = [node for node in nodes if node["adcode"][:2] == province_code[:2]]
            result.update(status="ok" if nodes else "empty", regions=nodes,
                message="选择城市后可继续选择区县。" if nodes else "未找到匹配区域，可手动输入城市和区县。")
            _region_cache[key] = (monotonic(), result)
            while len(_region_cache) > 128:
                _region_cache.popitem(last=False)
        except MapUnavailable as exc:
            result["message"] = str(exc).replace("未取得医院列表", "未取得区域候选")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            result["message"] = "区域候选查询失败或超时，可手动重试或输入城市和区县。"
    return result


def periods():
    time = datetime.now(ZoneInfo("Asia/Shanghai"))
    return "day:" + time.strftime("%Y-%m-%d"), "month:" + time.strftime("%Y-%m")


def provider_enabled(provider):
    return bool(settings.TIANDITU_ENABLED and settings.TIANDITU_API_KEY) if provider == "tianditu" else bool(settings.AMAP_ENABLED and settings.AMAP_API_KEY)


def provider_usage(bind, provider):
    limits = (settings.TIANDITU_REQUESTS_PER_DAY, settings.TIANDITU_REQUESTS_PER_MONTH) if provider == "tianditu" else (settings.MAP_REQUESTS_PER_DAY, settings.MAP_REQUESTS_PER_MONTH)
    with Session(bind) as s:
        counts = []
        for period in periods():
            row = s.exec(select(ExternalApiUsage).where(ExternalApiUsage.provider == provider, ExternalApiUsage.period == period)).first()
            counts.append(row.requests if row else 0)
    return {"provider": provider, "provider_name": "天地图" if provider == "tianditu" else "高德",
        "enabled": provider_enabled(provider),
        "day_requests": counts[0], "month_requests": counts[1],
        "day_limit": limits[0], "month_limit": limits[1],
        "timezone": "Asia/Shanghai", "note": "应用请求计数，含失败请求；不是服务商余额。"}


def map_usage(bind, provider=None):
    providers = [provider_usage(bind, name) for name in ("amap", "tianditu")]
    selected = provider or "auto"
    data = next((row for row in providers if row["provider"] == selected), None)
    if data is None:
        data = {"provider": "auto", "provider_name": "地图综合查询", "enabled": any(row["enabled"] for row in providers),
            **{field: sum(row[field] for row in providers) for field in ("day_requests", "month_requests", "day_limit", "month_limit")},
            "timezone": "Asia/Shanghai", "note": "两家分别限额，合计仅供查看；含失败请求，不是供应商余额。"}
    return {**data, "providers": providers,
        "region_enabled": provider_enabled("amap"), "region_provider_name": "高德"}


def reserve_request(bind, provider="amap"):
    limits = (settings.TIANDITU_REQUESTS_PER_DAY, settings.TIANDITU_REQUESTS_PER_MONTH) if provider == "tianditu" else (settings.MAP_REQUESTS_PER_DAY, settings.MAP_REQUESTS_PER_MONTH)
    # Independent commit survives failed searches and outer business rollbacks.
    for attempt in range(3):
        with Session(bind) as s:
            try:
                for period, limit in zip(periods(), limits):
                    row = s.exec(select(ExternalApiUsage).where(ExternalApiUsage.provider == provider, ExternalApiUsage.period == period)).first()
                    if not row:
                        row = ExternalApiUsage(provider=provider, period=period)
                        s.add(row)
                        s.flush()
                    changed = s.execute(update(ExternalApiUsage).where(
                        ExternalApiUsage.id == row.id, ExternalApiUsage.requests < limit
                    ).values(requests=ExternalApiUsage.requests + 1))
                    if changed.rowcount != 1:
                        raise MapUnavailable("应用地图请求上限已达到，未继续调用。可打开地图搜索。")
                s.commit()
                return
            except IntegrityError:
                s.rollback()
                if attempt == 2:
                    raise MapUnavailable("地图请求计数冲突，请稍后手动重试。")


async def amap_request(bind, endpoint, params):
    reserve_request(bind)
    # Fixed host/paths, no model-provided URLs, no SDK retries or response logging.
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        response = await client.get("https://restapi.amap.com/" + endpoint,
            params={**params, "key": settings.AMAP_API_KEY})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or payload.get("status") != "1":
        raise MapUnavailable("地图服务暂不可用或账号额度不足，未取得医院列表。")
    return payload


def search_link(query):
    params = {"keyword": " ".join(filter(None, [query.city, query.district, query.street, query.address_detail, "宠物医院"])), "src": "chongban", "view": "list"}
    if query.longitude is not None and query.coordinate_system == "gcj02":
        params["center"] = f"{query.longitude},{query.latitude}"
    return "https://uri.amap.com/search?" + urlencode(params)


def scalar(value, limit=300):
    return value[:limit].strip() if isinstance(value, str) else ""


def region_prefix(code):
    return code[:2] if code.endswith("0000") else code[:4] if code.endswith("00") else code


def point(location):
    if not re.fullmatch(r"\d+(\.\d+)?,\d+(\.\d+)?", location):
        return None
    lng, lat = map(float, location.split(","))
    return (lng, lat) if 73 <= lng <= 136 and 18 <= lat <= 54 else None


def distance_between(center, destination):
    lng, lat = map(radians, center)
    x, y = map(radians, destination)
    value = sin((y - lat) / 2) ** 2 + cos(lat) * cos(y) * sin((x - lng) / 2) ** 2
    return round(6371000 * 2 * asin(sqrt(min(1, value))), 1)


def full_address(poi):
    detail = scalar(poi.get("address"))
    prefix = ""
    for field in ("pname", "cityname", "adname"):
        name = scalar(poi.get(field), 80)
        if name and name not in prefix and name not in detail:
            prefix += name
    return prefix + detail if detail else prefix + "（地图未提供街道/门牌）" if prefix else ""


async def resolve_address(bind, query):
    # Never cache addresses or their matched coordinates. Do not guess invalid regions.
    address = "".join(filter(None, [query.city.strip(), query.district.strip(), query.street.strip(), query.address_detail.strip()]))
    params = {"address": address, "output": "JSON"}
    if query.region_adcode:
        code = query.region_adcode
        params["city"] = code[:2] + "0000" if code[:2] in {"11", "12", "31", "50"} else code[:4] + "00"
    payload = await amap_request(bind, "v3/geocode/geo", params)
    rows = payload.get("geocodes")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise MapUnavailable("地点未能唯一匹配，请选择正确市区或补充路名、门牌/小区；没有扩大搜索范围。")
    row = rows[0]
    code, level = scalar(row.get("adcode"), 6), scalar(row.get("level"), 30)
    if not re.fullmatch(r"[1-6]\d{5}", code) or not level:
        raise MapUnavailable("没有取得可靠的地区信息，请重新选择市区。")
    if query.region_adcode and not code.startswith(region_prefix(query.region_adcode)):
        raise MapUnavailable("地点与所选市区不一致，请核对地址；没有扩大搜索范围。")
    specific = bool(query.street.strip() or query.address_detail.strip())
    if specific and level in {"国家", "省", "市", "地级市", "县级市", "区县", "区", "县", "城区", "未知"}:
        raise MapUnavailable("地图只匹配到较大的行政区，未按附近范围查询。请补充街道、小区或门牌。")
    location = point(scalar(row.get("location"), 100))
    if specific and not location:
        raise MapUnavailable("未取得具体地点的位置，请补充路名、门牌或小区。")
    if not specific and level in {"国家", "省"} and code not in {"110000", "120000", "310000", "500000"}:
        raise MapUnavailable("地区仍是省级范围，请选择具体城市或区县。")
    return {"adcode": code, "location": location, "level": level,
        "label": scalar(row.get("formatted_address"), 300) or address}


async def search_hospitals(bind, query, map_owner=None):
    if query.provider == "tianditu":
        from app.tianditu import search_tianditu_hospitals
        return await search_tianditu_hospitals(bind, query)
    if query.provider == "amap":
        return await search_amap_hospitals(bind, query, map_owner)
    from app.hospital_agent import find_hospital_candidates
    return await find_hospital_candidates(bind, query, map_owner)


async def search_amap_hospitals(bind, query, map_owner=None, internal_points=False):
    result = {"mode": "map_link", "status": "unavailable", "items": [],
        "provider": "amap", "provider_name": "高德", "search_label": "打开高德搜索",
        "queried_at": datetime.now(UTC).isoformat(), "search_url": search_link(query),
        "message": "地图接口未启用或未配置密钥，未取得医院列表。可打开高德搜索。"}
    if not settings.AMAP_ENABLED or not settings.AMAP_API_KEY:
        return result
    try:
        map_points = []
        point_by_item = {}
        search_center = None
        region_code = query.region_adcode
        matched = None
        specific = bool(query.street.strip() or query.address_detail.strip())
        if query.longitude is None and (specific or not region_code):
            matched = await resolve_address(bind, query)
            region_code = matched["adcode"]
        params = {"keywords": "宠物医院", "page_size": 10, "show_fields": "business", "page_num": 1}
        if query.longitude is not None or specific:
            if specific:
                lng, lat = matched["location"]
            else:
                lng, lat = query.longitude, query.latitude
            if not specific and query.coordinate_system == "wgs84":
                converted = await amap_request(bind, "v3/assistant/coordinate/convert", {
                    "locations": f"{lng},{lat}", "coordsys": "gps"})
                lng, lat = map(float, converted["locations"].split(","))
                if not (73 <= lng <= 136 and 18 <= lat <= 54):
                    raise MapUnavailable("坐标转换未返回有效的中国大陆查询坐标。")
            params.update(location=f"{lng:.6f},{lat:.6f}", radius=query.radius_km * 1000, sortrule="distance")
            search_center = (lng, lat)
            result["scope_label"] = f"{matched['label'] if specific else '浏览器定位点'}附近 {query.radius_km} 公里"
            result["scope_note"] = "以地图匹配点为中心，不是实时定位；可补充门牌或小区提高准确性。" if specific else "本次授权定位周边查询，不保存定位。"
            endpoint = "v5/place/around"
        else:
            params.update(region=region_code, city_limit="true", keywords="宠物医院")
            result["scope_label"] = "行政区：" + (matched["label"] if matched else " · ".join(filter(None, [query.city, query.district])))
            result["scope_note"] = "整片所选行政区；公里范围仅用于具体地点或浏览器定位查询。"
            endpoint = "v5/place/text"
        payload = await amap_request(bind, endpoint, params)
        pois = payload.get("pois", [])
        if not isinstance(pois, list):
            raise MapUnavailable("地图返回格式异常，未取得可靠的医院列表。")
        for poi in pois[:10]:
            if not isinstance(poi, dict):
                continue
            if not isinstance(poi, dict) or not scalar(poi.get("name")):
                continue
            if search_center is None and region_code:
                # Never mix a same-named district outside the explicitly selected region.
                prefix = region_prefix(region_code)
                if not re.fullmatch(r"[1-6]\d{5}", scalar(poi.get("adcode"), 6)) or not poi["adcode"].startswith(prefix):
                    continue
            business = poi.get("business") if isinstance(poi.get("business"), dict) else {}
            destination = point(scalar(poi.get("location"), 100))
            if search_center:
                if not destination or distance_between(search_center, destination) > query.radius_km * 1000:
                    continue
            tel = scalar(business.get("tel"), 100)
            phone = next((p for p in re.split(r"[;,；]", tel) if re.fullmatch(r"[+\d() -]{5,30}", p)), "")
            distance = scalar(poi.get("distance"), 20)
            distance = float(distance) if re.fullmatch(r"\d+(\.\d+)?", distance) and search_center else distance_between(search_center, destination) if search_center and destination else None
            if search_center and distance is not None and distance > query.radius_km * 1000:
                continue
            params = {"keyword": scalar(poi["name"]), "city": scalar(poi.get("cityname")) or query.city, "src": "chongban"}
            item = {"id": scalar(poi.get("id"), 100), "name": scalar(poi["name"]),
                "address": full_address(poi), "phone": phone, "distance_m": distance,
                "opening_hours": scalar(business.get("opentime_today")) or scalar(business.get("opentime_week")),
                "opening_status": "地图登记信息，出发前请电话核实",
                "emergency": "待核实", "species_capability": "待核实", "qualification": "待核实",
                "rating_status": "unavailable", "rating_note": "暂无可靠评分：高德此接口的评分字段不覆盖宠物医院；不代表医院质量差。",
                "rating_source_url": RATING_SOURCE,
                "registered_region": " · ".join(filter(None, [scalar(poi.get("pname"), 80), scalar(poi.get("cityname"), 80), scalar(poi.get("adname"), 80)])),
                "poi_type": scalar(poi.get("type"), 100), "verification_status": "地图登记，未电话核实",
                "source": "高德地点搜索", "source_url": "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch",
                "map_url": "https://uri.amap.com/search?" + urlencode(params),
                "navigation_url": "https://uri.amap.com/search?" + urlencode(params),
                "match_reason": "在用户选择范围内检索到的宠物医院候选；医疗质量与接诊能力尚未核实。"}
            location = scalar(poi.get("location"), 100)
            if re.fullmatch(r"\d+(\.\d+)?,\d+(\.\d+)?", location):
                item["navigation_url"] = "https://uri.amap.com/navigation?" + urlencode({
                    "to": location + "," + item["name"], "mode": "car", "src": "chongban", "callnative": 0})
                lng, lat = map(float, location.split(","))
                if 73 <= lng <= 136 and 18 <= lat <= 54:
                    point_by_item[id(item)] = (lng, lat)
            result["items"].append(item)
        if search_center:
            result["items"].sort(key=lambda item: item["distance_m"] if item["distance_m"] is not None else float("inf"))
        result.update(mode="external", status="ok" if result["items"] else "empty",
            message="已取得地图候选，接诊能力需电话核实。" if result["items"] else "当前范围没有返回医院，可扩大范围或打开地图搜索。")
        result["region_adcode"] = region_code
        if internal_points:
            result["_map_coordinates"] = {index: point_by_item[id(item)] for index, item in enumerate(result["items"]) if id(item) in point_by_item}
        if map_owner:
            for number, item in enumerate(result["items"], 1):
                item["map_number"] = chr(64 + number)
                if id(item) in point_by_item:
                    map_points.append((number, *point_by_item[id(item)]))
            result["map_preview_token"] = map_preview(map_owner, map_points) if map_points else None
    except MapUnavailable as exc:
        result["message"] = str(exc)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        result["message"] = "地图查询失败或超时，未取得医院列表。可手动重试或打开地图搜索。"
    return result
