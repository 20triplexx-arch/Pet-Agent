"""Local hospital tool workflow: query authorized services and reconcile facts.

No model call, private position persistence, provider retry or quality scoring.
"""
import asyncio
import re
import unicodedata
from datetime import UTC, datetime

from app.hospitals import map_preview, provider_usage, search_amap_hospitals, search_link
from app.tianditu import search_tianditu_hospitals

NAMES = {"amap": "高德", "tianditu": "天地图"}
RECORD_FIELDS = ("name", "address", "phone", "opening_hours", "registered_region", "poi_type", "source", "source_url")


def normalized(value):
    return re.sub(r"[\s·,，。()（）\[\]【】]+", "", unicodedata.normalize("NFKC", value or ""))


def street_address(item):
    address = normalized(item.get("address"))
    for region in (item.get("registered_region") or "").split(" · "):
        region = normalized(region)
        if region and address.startswith(region):
            address = address[len(region):]
    return address


def same_hospital(first, second):
    # Shared chain phone/name, a street with no door number or missing address
    # cannot prove that two branches are the same hospital.
    address = street_address(first)
    return bool(normalized(first.get("name")) == normalized(second.get("name"))
        and address and re.search(r"\d", address)
        and "未提供" not in address and address == street_address(second)
        and normalized(first.get("registered_region"))
        and normalized(first.get("registered_region")) == normalized(second.get("registered_region")))


def source_record(item, provider, queried_at):
    return {"provider": provider, "provider_name": NAMES[provider], "queried_at": queried_at,
        **{key: item.get(key, "") for key in RECORD_FIELDS}}


def merge_candidates(results, nearby):
    rows = []
    seen_ids = set()
    merged_count = 0
    # Administrative searches have no reliable distances; interleave sources
    # so the second provider isn't discarded merely because the first has ten.
    for index in range(10):
        for provider in ("amap", "tianditu"):
            result = results.get(provider, {})
            items = result.get("items", [])
            if index >= len(items):
                continue
            original = items[index]
            identity = (provider, original.get("id"))
            if identity[1] and identity in seen_ids:
                continue
            seen_ids.add(identity)
            item = dict(original)
            item.pop("map_number", None)
            item["sources"] = [source_record(item, provider, result["queried_at"])]
            item["field_sources"] = {field: NAMES[provider] for field in ("phone", "opening_hours", "address") if item.get(field)}
            item["conflicts"] = []
            coordinate = result.get("_map_coordinates", {}).get(index) if provider == "amap" else None
            if coordinate:
                item["_amap_point"] = coordinate
            match = next((row for row in rows if provider not in {record["provider"] for record in row["sources"]}
                and same_hospital(row, item)), None)
            if not match:
                rows.append(item)
                continue
            merged_count += 1
            match["sources"].extend(item["sources"])
            for field, label in (("phone", "电话"), ("opening_hours", "营业时间")):
                if match.get(field) and item.get(field) and normalized(match[field]) != normalized(item[field]):
                    match["conflicts"].append(f"{label}登记不一致，请分别核实来源记录")
                elif not match.get(field) and item.get(field):
                    match[field] = item[field]
                    match["field_sources"][field] = NAMES[provider]
                    if field == "opening_hours":
                        match["opening_status"] = item["opening_status"]
            if coordinate:
                match["_amap_point"] = coordinate
                # Only use actual AMap coordinates for AMap map/navigation.
                for field in ("navigation_url", "navigation_label", "map_url"):
                    if field in item:
                        match[field] = item[field]
                if "navigation_label" not in item:
                    match.pop("navigation_label", None)
            names = "、".join(record["provider_name"] for record in match["sources"])
            match["match_reason"] = f"{names}的完整名称、地区及带门牌地址对应，合并重复登记；相同资料不代表医疗质量已核实。"
    if nearby:
        rows.sort(key=lambda row: row["distance_m"] if row.get("distance_m") is not None else float("inf"))
    return rows[:10], merged_count, len(rows)


async def run_provider(bind, query, provider):
    usage = provider_usage(bind, provider)
    reason = None
    if not usage["enabled"]:
        reason = "未启用或未配置密钥"
    elif usage["day_requests"] >= usage["day_limit"] or usage["month_requests"] >= usage["month_limit"]:
        reason = "应用请求上限已达到，未调用"
    elif provider == "tianditu" and (query.longitude is not None or query.street.strip() or query.address_detail.strip()) and query.radius_km > 10:
        reason = "周边仅支持10公里以内，本次保留用户选定的范围"
    elif provider == "tianditu" and query.longitude is not None and query.coordinate_system != "wgs84":
        reason = "本次坐标类型不受支持，未混用地图坐标"
    if reason:
        return {"status": "skipped", "items": [], "queried_at": datetime.now(UTC).isoformat(), "message": reason}
    try:
        return await search_amap_hospitals(bind, query, internal_points=True) if provider == "amap" else await search_tianditu_hospitals(bind, query)
    except Exception:
        # Isolate an adapter/transaction fault without echoing its private URL.
        return {"status": "unavailable", "items": [], "queried_at": datetime.now(UTC).isoformat(), "message": "查询未能完成，可手动重试"}


async def find_hospital_candidates(bind, query, owner=None):
    names = ("amap", "tianditu")
    values = await asyncio.gather(*(run_provider(bind, query, name) for name in names))
    results = dict(zip(names, values))
    outcomes = [{"provider": name, "provider_name": NAMES[name], "status": result["status"],
        "item_count": len(result.get("items", [])), "message": result["message"], "queried_at": result["queried_at"],
        "scope_label": result.get("scope_label"), "scope_note": result.get("scope_note")}
        for name, result in results.items()]
    nearby = bool(query.longitude is not None or query.street.strip() or query.address_detail.strip())
    region_codes = {result.get("region_adcode") for result in values if result["status"] in {"ok", "empty"} and result.get("region_adcode")}
    scope_conflict = not nearby and len(region_codes) > 1
    items, merged, unique = ([], 0, 0) if scope_conflict else merge_candidates(results, nearby)
    completed = [row for row in outcomes if row["status"] in {"ok", "empty"}]
    partial = len(completed) < len(outcomes)
    status = "ok" if items else "empty" if completed and not scope_conflict else "unavailable"
    active = [row["provider_name"] for row in completed]
    message = f"已综合{'、'.join(active)}的资料，展示{len(items)}家医院候选。" if items else "当前可用来源未返回医院候选，可补充地点或主动调整范围。" if completed else "地图查询未能完成，可查看查询状态后手动重试或打开地图搜索。"
    if scope_conflict:
        message = "两家对地区的匹配不一致，请选择具体城市及区县后查询；没有混合不同地区的结果。"
    elif partial:
        message += " 部分来源未完成查询，已保留可用资料。" if completed else ""
    if not completed:
        failure = next((row for row in outcomes if row["status"] == "unavailable" or "上限" in row["message"]), None)
        if failure:
            message += f" {failure['provider_name']}：{failure['message']}"
    points = []
    for number, item in enumerate(items, 1):
        coordinate = item.pop("_amap_point", None)
        if coordinate:
            item["map_number"] = chr(64 + number)
            points.append((number, *coordinate))
    scope = next((result for result in values if result["status"] in {"ok", "empty"}), {})
    return {"provider": "auto", "provider_name": "地图资料综合", "mode": "external" if completed else "map_link",
        "status": status, "items": items, "message": message, "queried_at": datetime.now(UTC).isoformat(),
        "search_url": search_link(query), "search_label": "打开高德搜索", "scope_label": None if scope_conflict else scope.get("scope_label"),
        "scope_note": "两家分别按各自匹配点及坐标核对范围；距离不是医疗质量或行车距离。" if nearby and len(completed) == 2 else scope.get("scope_note"),
        "provider_results": outcomes, "partial": partial, "map_preview_token": map_preview(owner, points) if owner and points else None,
        "map_note": "地图仅标注取得高德坐标的候选，编号对应列表；其他候选可按名称查看地图。" if points else "本次暂无可展示的高德位置资料，可按名称核对医院地图。",
        "agent_summary": {"mode": "local_rules", "merged_duplicates": merged, "unique_candidates": unique,
            "basis": "按指定范围查询，核对重复登记并保留来源差异；附近结果按距离排列，行政区结果交替展示来源。没有给出医院质量排名。"}}
