"""Server-side AMap adapter. No coordinates, keys or POI mirrors are persisted."""
import asyncio
from datetime import datetime, UTC
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import re
import httpx
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from app.core.config import settings
from app.models import ExternalApiUsage


class MapUnavailable(Exception):
    pass


def periods():
    time = datetime.now(ZoneInfo("Asia/Shanghai"))
    return "day:" + time.strftime("%Y-%m-%d"), "month:" + time.strftime("%Y-%m")


def map_usage(bind):
    with Session(bind) as s:
        counts = []
        for period in periods():
            row = s.exec(select(ExternalApiUsage).where(ExternalApiUsage.provider == "amap", ExternalApiUsage.period == period)).first()
            counts.append(row.requests if row else 0)
    return {"enabled": bool(settings.AMAP_ENABLED and settings.AMAP_API_KEY),
        "day_requests": counts[0], "month_requests": counts[1],
        "day_limit": settings.MAP_REQUESTS_PER_DAY, "month_limit": settings.MAP_REQUESTS_PER_MONTH,
        "timezone": "Asia/Shanghai", "note": "应用请求计数，含失败请求；不是服务商余额。"}


def reserve_request(bind):
    # Independent commit survives failed searches and outer business rollbacks.
    for attempt in range(3):
        with Session(bind) as s:
            try:
                for period, limit in zip(periods(), (settings.MAP_REQUESTS_PER_DAY, settings.MAP_REQUESTS_PER_MONTH)):
                    row = s.exec(select(ExternalApiUsage).where(ExternalApiUsage.provider == "amap", ExternalApiUsage.period == period)).first()
                    if not row:
                        row = ExternalApiUsage(provider="amap", period=period)
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
    params = {"keyword": (query.district + " 宠物医院").strip(), "src": "chongban", "view": "list"}
    if query.city:
        params["city"] = query.city
    if query.longitude is not None and query.coordinate_system == "gcj02":
        params["center"] = f"{query.longitude},{query.latitude}"
    return "https://uri.amap.com/search?" + urlencode(params)


def scalar(value, limit=300):
    return value[:limit].strip() if isinstance(value, str) else ""


async def search_hospitals(bind, query):
    result = {"mode": "map_link", "status": "unavailable", "items": [],
        "queried_at": datetime.now(UTC).isoformat(), "search_url": search_link(query),
        "message": "地图接口未启用或未配置密钥，未取得医院列表。可打开高德搜索。"}
    if not settings.AMAP_ENABLED or not settings.AMAP_API_KEY:
        return result
    try:
        params = {"keywords": "宠物医院", "page_size": 10, "show_fields": "business", "page_num": 1}
        if query.longitude is not None:
            lng, lat = query.longitude, query.latitude
            if query.coordinate_system == "wgs84":
                converted = await amap_request(bind, "v3/assistant/coordinate/convert", {
                    "locations": f"{lng},{lat}", "coordsys": "gps"})
                lng, lat = map(float, converted["locations"].split(","))
                if not (73 <= lng <= 136 and 18 <= lat <= 54):
                    raise MapUnavailable("坐标转换未返回有效的中国大陆查询坐标。")
            params.update(location=f"{lng:.6f},{lat:.6f}", radius=query.radius_km * 1000, sortrule="distance")
            endpoint = "v5/place/around"
        else:
            params.update(region=query.city, city_limit="true", keywords=(query.district + " 宠物医院").strip())
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
            business = poi.get("business") if isinstance(poi.get("business"), dict) else {}
            tel = scalar(business.get("tel"), 100)
            phone = next((p for p in re.split(r"[;,；]", tel) if re.fullmatch(r"[+\d() -]{5,30}", p)), "")
            distance = scalar(poi.get("distance"), 20)
            distance = float(distance) if re.fullmatch(r"\d+(\.\d+)?", distance) and query.longitude is not None else None
            params = {"keyword": scalar(poi["name"]), "city": scalar(poi.get("cityname")) or query.city, "src": "chongban"}
            item = {"id": scalar(poi.get("id"), 100), "name": scalar(poi["name"]),
                "address": scalar(poi.get("address")), "phone": phone, "distance_m": distance,
                "opening_hours": scalar(business.get("opentime_today")) or scalar(business.get("opentime_week")),
                "opening_status": "地图登记信息，出发前请电话核实",
                "emergency": "待核实", "species_capability": "待核实", "qualification": "待核实",
                "source": "高德地点搜索", "source_url": "https://developer.amap.com/api/webservice/guide/api-advanced/newpoisearch",
                "map_url": "https://uri.amap.com/search?" + urlencode(params),
                "navigation_url": "https://uri.amap.com/search?" + urlencode(params),
                "match_reason": "在用户选择范围内检索到的宠物医院候选；医疗质量与接诊能力尚未核实。"}
            location = scalar(poi.get("location"), 100)
            if re.fullmatch(r"\d+(\.\d+)?,\d+(\.\d+)?", location):
                item["navigation_url"] = "https://uri.amap.com/navigation?" + urlencode({
                    "to": location + "," + item["name"], "mode": "car", "src": "chongban", "callnative": 0})
            result["items"].append(item)
        if query.longitude is not None:
            result["items"].sort(key=lambda item: item["distance_m"] if item["distance_m"] is not None else float("inf"))
        result.update(mode="external", status="ok" if result["items"] else "empty",
            message="已取得地图候选，接诊能力需电话核实。" if result["items"] else "当前范围没有返回医院，可扩大范围或打开地图搜索。")
    except MapUnavailable as exc:
        result["message"] = str(exc)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        result["message"] = "地图查询失败或超时，未取得医院列表。可手动重试或打开地图搜索。"
    return result
