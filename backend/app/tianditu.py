"""Optional server-side Tianditu search v2. Never caches entered locations or POIs.

Official contract: https://lbs.tianditu.gov.cn/server/search2.html
This adapter does not load a browser SDK or render Tianditu tiles/static maps.
"""
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from app.core.config import settings
from app.hospitals import MapUnavailable, distance_between, point, region_prefix, reserve_request, scalar, search_link

SOURCE = "https://lbs.tianditu.gov.cn/server/search2.html"


def mainland_code(value):
    """Tianditu uses nine-digit country+administration codes, not AMap adcodes."""
    code = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    if code.startswith("156") and len(code) == 9:
        code = code[3:]
    return code if re.fullmatch(r"[1-6]\d{5}", code) else ""


async def request_search(bind, fields):
    reserve_request(bind, "tianditu")
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
        # A single allowlisted HTTPS endpoint. No vendor URLs or text are logged.
        async with client.stream("GET", "https://api.tianditu.gov.cn/v2/search", params={
            "postStr": json.dumps(fields, ensure_ascii=False, separators=(",", ":")),
            "type": "query", "tk": settings.TIANDITU_API_KEY,
        }) as response:
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise MapUnavailable("天地图返回资料过大，未取得可靠列表。")
        payload = json.loads(body)
        if isinstance(payload, dict) and str(payload.get("code")) == "301012":
            # Translate only a known error enum; never echo vendor text or keys.
            browser_key = "浏览器端" in scalar(payload.get("resolve"), 800)
            raise MapUnavailable("当前天地图Key权限为浏览器端，请更换服务端Key（301012）。" if browser_key
                else "天地图Key权限类型不匹配（301012），请在控制台核对服务端应用。")
        response.raise_for_status()
    status = payload.get("status") if isinstance(payload, dict) else None
    if not isinstance(status, dict) or str(status.get("infocode")) != "1000":
        raise MapUnavailable("天地图接口未返回成功，请检查服务端Key权限及账户配额后手动重试。")
    return payload


def search_fields(keyword, code=None):
    fields = {"keyWord": keyword, "level": 12, "mapBound": "73,18,136,54",
        "queryType": 7, "start": 0, "count": 10, "show": 2}
    if code:
        fields["specify"] = "156" + code
    return fields


async def resolve_region(bind, query):
    keyword = query.city.strip() + query.district.strip()
    payload = await request_search(bind, search_fields(keyword))
    if str(payload.get("resultType")) == "1" and isinstance(payload.get("pois"), list):
        # Live v2 responses can represent an administrative place as a POI.
        # Only explicit administrative classes with a matching hierarchy qualify.
        fields = {"省级地名": "provinceCode", "市级地名": "cityCode", "区县级地名": "countyCode"}
        matches = []
        for row in payload["pois"][:10]:
            if not isinstance(row, dict) or row.get("typeName") not in fields:
                continue
            name = scalar(row.get("name"), 80)
            hierarchy = ""
            for piece in (scalar(row.get("province"), 80), scalar(row.get("city"), 80), name):
                if piece and piece not in hierarchy:
                    hierarchy += piece
            code = mainland_code(row.get(fields[row["typeName"]]))
            if name and code and hierarchy.endswith(keyword) and keyword.endswith(name):
                matches.append({"name": name, "adminCode": code})
        rows = matches
    else:
        rows = payload.get("area")
    rows = [rows] if isinstance(rows, dict) else rows
    if str(payload.get("resultType")) not in {"1", "3"} or not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise MapUnavailable("天地图未能唯一匹配地区，请选择市区候选或核对完整市区名称；没有扩大搜索范围。")
    row = rows[0]
    code, name = mainland_code(row.get("adminCode")), scalar(row.get("name"), 80)
    if str(payload.get("resultType")) == "3" and name not in {keyword, keyword + "市"}:
        raise MapUnavailable("行政区资料没有完整对应输入的市区名称，请选择地区候选；未根据同名区县猜测范围。")
    if not code or len(name.rstrip("市区县")) < 2 or name.rstrip("市区县") not in keyword:
        raise MapUnavailable("天地图返回地区与输入不一致，请核对市区名称。")
    if code.endswith("0000") and code not in {"110000", "120000", "310000", "500000"}:
        raise MapUnavailable("当前仍是省级范围，请选择具体城市或区县。")
    return code, name


def poi_code(row):
    for field in ("countyCode", "cityCode", "provinceCode"):
        code = mainland_code(row.get(field))
        if code:
            return code
    return ""


def in_region(row, code):
    return poi_code(row).startswith(region_prefix(code))


def place_keyword(query):
    address = ""
    for value in (query.city, query.district, query.street, query.address_detail):
        piece = value.strip()
        if not piece:
            continue
        if address and address in piece:
            address = piece
            continue
        overlap = next((length for length in range(min(len(address), len(piece)), 1, -1)
            if address.endswith(piece[:length])), 0)
        address += piece[overlap:]
    return address


async def resolve_place(bind, query, code):
    address = place_keyword(query)
    payload = await request_search(bind, search_fields(address, code))
    rows = payload.get("pois")
    if str(payload.get("resultType")) != "1" or not isinstance(rows, list):
        raise MapUnavailable("天地图未匹配到具体地点，请补充小区、路名或门牌；没有按行政区中心查询附近。")
    candidates = [row for row in rows if isinstance(row, dict) and in_region(row, code)
        and point(scalar(row.get("lonlat"), 100))]
    detail = query.address_detail.strip() or query.street.strip()
    exact = [row for row in candidates if detail in {scalar(row.get("name")), scalar(row.get("address"))}]
    if exact:
        candidates = exact
    if len(candidates) != 1:
        raise MapUnavailable("具体地点存在多个匹配或未匹配到所选地区，请补充完整小区、路名或门牌；没有扩大范围。")
    row = candidates[0]
    # An unrelated unique POI is not proof that the requested address matched.
    label = scalar(row.get("address")) + scalar(row.get("name"))
    if detail not in label:
        raise MapUnavailable("天地图具体地点与输入不一致，请补充完整地点名称；没有扩大范围。")
    return point(scalar(row.get("lonlat"), 100)), scalar(row.get("name")) or address


def address_for(row):
    detail = scalar(row.get("address"))
    prefix = ""
    for field in ("province", "city", "county"):
        name = scalar(row.get(field), 80)
        if name and name not in prefix and name not in detail:
            prefix += name
    return prefix + detail if detail else prefix + "（地图未提供街道/门牌）" if prefix else ""


async def search_tianditu_hospitals(bind, query):
    result = {"provider": "tianditu", "provider_name": "天地图", "mode": "map_link", "status": "unavailable",
        "items": [], "queried_at": datetime.now(UTC).isoformat(), "search_url": search_link(query),
        "search_label": "打开高德搜索（按名称）", "map_preview_token": None,
        "map_note": "天地图结果以列表展示；可按名称打开高德核对位置及导航。",
        "message": "天地图未启用或未配置服务端Key，未取得医院列表。"}
    if not settings.TIANDITU_ENABLED or not settings.TIANDITU_API_KEY:
        return result
    specific = bool(query.street.strip() or query.address_detail.strip())
    nearby = query.longitude is not None or specific
    if nearby and query.radius_km > 10:
        return {**result, "message": "天地图周边搜索支持10公里以内，请选择1、3、5或10公里；未调用外部接口。"}
    if query.longitude is not None and query.coordinate_system != "wgs84":
        return {**result, "message": "天地图查询不接受高德GCJ-02坐标，请重新使用浏览器定位或输入地点；未调用外部接口。"}
    try:
        code = query.region_adcode
        center = None
        region_name = " · ".join(filter(None, [query.city, query.district]))
        if query.longitude is None:
            if not code:
                code, region_name = await resolve_region(bind, query)
            if code.endswith("0000") and code not in {"110000", "120000", "310000", "500000"}:
                raise MapUnavailable("当前仍是省级范围，请选择具体城市或区县。")
        if nearby:
            center, label = await resolve_place(bind, query, code) if specific else ((query.longitude, query.latitude), "浏览器定位点")
            fields = {"keyWord": "宠物医院", "level": 12, "queryType": 3, "start": 0, "count": 10,
                "show": 2, "pointLonlat": f"{center[0]:.6f},{center[1]:.6f}", "queryRadius": query.radius_km * 1000}
            result["scope_label"] = f"{label}附近 {query.radius_km} 公里"
            result["scope_note"] = "以天地图匹配点为中心；距离按坐标估算，不是行车距离。" if specific else "本次授权定位周边查询；距离按坐标估算，不保存定位。"
        else:
            fields = {"keyWord": "宠物医院", "specify": "156" + code, "queryType": 12, "start": 0, "count": 10, "show": 2}
            result["scope_label"] = "行政区：" + region_name
            result["scope_note"] = "整片所选行政区；填写具体地点或使用定位后才按公里范围查找。"
        payload = await request_search(bind, fields)
        result["region_adcode"] = code
        rows = payload.get("pois", [])
        if not isinstance(rows, list) or (rows and str(payload.get("resultType")) != "1"):
            raise MapUnavailable("天地图未返回可靠的医院地点列表，未采用推荐的其他城市。")
        seen = set()
        for row in rows[:10]:
            if not isinstance(row, dict) or not scalar(row.get("name")):
                continue
            if not center and not in_region(row, code):
                continue
            destination = point(scalar(row.get("lonlat"), 100))
            if center and (not destination or distance_between(center, destination) > query.radius_km * 1000):
                continue
            name, address = scalar(row.get("name")), address_for(row)
            identity = scalar(row.get("hotPointID"), 100) or name + "|" + address
            if identity in seen:
                continue
            seen.add(identity)
            phone = next((part.strip() for part in re.split(r"[;,；]", scalar(row.get("phone"), 100))
                if re.fullmatch(r"[+\d() -]{5,30}", part.strip())), "")
            # Name/address links only. Never plot geodetic TDT points on a GCJ-02 map.
            url = "https://uri.amap.com/search?" + urlencode({"keyword": name + " " + address, "src": "chongban", "view": "list"})
            result["items"].append({"id": "tianditu:" + identity, "name": name, "address": address, "phone": phone,
                "distance_m": distance_between(center, destination) if center else None, "distance_kind": "estimated",
                "opening_hours": "", "opening_status": "天地图搜索接口未提供营业时间，请电话核实",
                "emergency": "待核实", "species_capability": "待核实", "qualification": "待核实",
                "rating_status": "unavailable", "rating_note": "天地图搜索接口未提供可靠医院评分，不推测星级。",
                "registered_region": " · ".join(filter(None, [scalar(row.get(field), 80) for field in ("province", "city", "county")])),
                "poi_type": scalar(row.get("typeName"), 100), "verification_status": "地图登记，未电话核实",
                "source": "天地图地名搜索", "source_url": SOURCE, "map_url": url, "navigation_url": url,
                "navigation_label": "按名称导航", "match_reason": "用户指定范围内的天地图候选；按名称进入高德后请核对具体机构，不保证两家地图条目完全一致。"})
        if center:
            result["items"].sort(key=lambda row: row["distance_m"])
        result.update(mode="external", status="ok" if result["items"] else "empty",
            message="已取得天地图候选，接诊能力及营业情况需电话核实。" if result["items"] else "天地图在当前范围没有返回医院，可主动调整范围或按名称打开高德搜索。")
    except MapUnavailable as exc:
        result["message"] = str(exc)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        result["message"] = "天地图查询失败或超时，未取得医院列表。可手动重试；未自动调用其他服务。"
    return result
