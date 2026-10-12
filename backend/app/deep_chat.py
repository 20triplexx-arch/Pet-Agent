"""Evidence assembly shared by demo and live answers; no implicit business writes."""
import json
import re
from datetime import datetime, UTC
from pydantic_ai import RunContext
from sqlmodel import select
from app.core.config import settings
from app.models import Breed, KnowledgeArticle
from app.knowledge import multi_search, evidence_sections, sections, tokenize
from app.care_schemas import NutritionInput, VisitInput
from app.nutrition import care_history, current_plans, get_profile, assess
from app.species import supports

CONTEXT_LABELS = {"goal": "照护目标", "observations": "本次观察", "timeline": "时间线", "diet_activity": "饮食与活动", "environment_changes": "环境变化", "professional_advice": "用户提供的专业建议"}
HEALTH = r"呕吐|腹泻|拉稀|不吃|拒食|食欲下降|食欲不振|咳嗽|瘙痒|疼痛|生病|跛行|便血|尿血|患有|感染"
TOPICS = [
    (r"换粮|更换.*粮", "换粮与观察"), (r"标签|配料|无谷|全价|零食|冻干|生食", "食品标签与选购"),
    (r"吃多少|喂多少|几克|营养|体重|体况|热量", "营养与体重"),
    (r"抓|啃咬|咬家具", "抓挠与啃咬"), (r"独处|独自|在家叫|分离", "独处与互动"),
    (r"多猫|多宠|相处|介绍新猫", "多宠相处"), (r"刷牙|牙齿|口腔", "口腔护理"),
    (HEALTH, "健康观察与就医准备"), (r"新宠|到家|适应", "新宠适应"),
    (r"玩具|用品|航空箱|胸背|牵引|猫砂", "用品选择"),
]


def questions_for(text):
    def query_excerpt(value):
        # Retrieval query excerpts only; the original 12000-character message remains intact.
        return value if len(value) <= 800 else value[:500] + " " + value[-300:]
    parts = [p.strip(" ，。") for p in re.split(r"[？?；;\n]+|另外|同时|还有|以及", text) if p.strip(" ，。")]
    # Preserve explicit questions first, using the complete text in the model payload.
    meaningful = [query_excerpt(p) for p in parts if re.search(r"怎么|如何|怎样|什么|是否|能否|注意|比较|建议|帮|为什么|分析|评估|说明|安排|选择", p)]
    if len(meaningful) > 1:
        topics = [label for pattern, label in TOPICS if re.search(pattern, text)]
        return [((topics[0] + "：") if topics and re.match(r"后续|继续|它|这个|其|接下来|还", p) else "") + p for p in meaningful[:3]]
    topics = [label for pattern, label in TOPICS if re.search(pattern, text)]
    if len(topics) > 1 and re.search(r"和|与|并且|另外|同时|还有|以及", text):
        return [meaningful[0] if meaningful else text[-800:]] + topics[1:3]
    return [meaningful[0] if meaningful else text[-800:]]


def conversation_context(history, supplied):
    values, provenance = {}, {}
    for message in history:
        if message["role"] != "user":
            continue
        for key, value in message.get("metadata_json", {}).get("context", {}).items():
            if value not in (None, "", {}):
                values[key] = value
                provenance[key] = {"message_id": message["id"], "date": message["created_at"], "source": "用户会话补充"}
    for key, value in supplied.items():
        if value not in (None, "", {}):
            values[key] = value
            provenance[key] = {"message_id": "current", "date": datetime.now(UTC).isoformat(), "source": "用户本次补充"}
    return {"values": values, "provenance": provenance}


def summarize_history(history, query):
    """Extractive summary: every statement retains its original message ID/date."""
    terms = set(tokenize(query))
    candidates = []
    for index, message in enumerate(history[:-24]):
        if message["role"] != "user":
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[。！？\n])", message["content"]) if s.strip()]
        priority = sorted(sentences, key=lambda s: (bool(re.search(r"过敏|病史|兽医|处方|限制|症状|体重", s)), len(terms & set(tokenize(s)))), reverse=True)
        excerpt = "\n".join(priority[:4])
        if len(excerpt) > 1000:
            excerpt = excerpt[:1000] + "（原消息还有内容，可按消息ID查看）"
        candidates.append((bool(re.search(r"过敏|病史|兽医|处方|限制", excerpt)), index, {
            "message_id": message["id"], "date": message["created_at"], "user_report_excerpt": excerpt,
            "context": message.get("metadata_json", {}).get("context", {}),
        }))
    result, size = [], 0
    for _, _, entry in sorted(candidates, reverse=True):
        cost = len(json.dumps(entry, ensure_ascii=False))
        if size + cost <= 8000:
            result.append(entry)
            size += cost
    return {"method": "extractive-v1", "items": result, "older_messages": max(0, len(history) - 24), "omitted_entries": len(candidates) - len(result)}


def source_cards(ctx, articles):
    cards = []
    for a in articles:
        cards.append({"id": a["id"], "title": a["title"], "url": a["source_url"],
            "organization": a["source_organization"], "sections": getattr(ctx, "citation_headings", {}).get(a["id"], [s["heading"] for s in a.get("matched_sections", evidence_sections(a, "", 3))]),
            "references": a.get("references", []), "review_status": a["review_status"]})
    return cards


def missing_health_info(text, values):
    questions = []
    if not values.get("timeline") and not re.search(r"今天|昨天|前天|小时|刚才|开始于|\d+天|\d{4}-\d{2}-\d{2}", text):
        questions.append("何时开始，近期是否发生变化？")
    if not re.search(r"\d+次|一次|持续|频率|每天|偶尔", text):
        questions.append("出现频率、持续时间和具体表现是什么？")
    if not re.search(r"精神|食欲|排泄|饮水|尿|便|进食", text):
        questions.append("精神、食欲、饮水和排泄有什么变化？")
    return questions[:3]


def facts_and_conflicts(p, values):
    facts, conflicts = [], []
    if p:
        facts.append(f"当前宠物：{p['name']}，{'猫' if p['species'] == 'cat' else '狗'}，" + (f"{p['age_months']} 个月" if p["age_months"] is not None else "年龄未知"))
        if p.get("weight") is not None:
            facts.append(f"档案体重：{p['weight']} kg；记录日期 {p['weight_date']}")
        for key, label in [("allergies", "过敏史"), ("medical_history", "既往病史"), ("vet_advice", "兽医建议")]:
            if p.get(key):
                facts.append(label + "（用户档案）：" + p[key])
        for new, old, label in [("professional_advice", "vet_advice", "专业建议"), ("diet_activity", "diet", "饮食与活动"), ("environment_changes", "environment", "环境")]:
            if values.get(new) and p.get(old) and values[new] != p[old]:
                conflicts.append(f"本次补充的{label}与档案记录不同，请核对时间与适用条件；档案尚未修改。")
    for key, label in CONTEXT_LABELS.items():
        if values.get(key):
            facts.append(label + "（用户会话资料）：" + values[key])
    return facts, conflicts


def add_tool_sources(ctx, cards):
    for source in cards:
        a = ctx.session.get(KnowledgeArticle, source["id"])
        if a and a.id not in ctx.retrieved:
            ctx.retrieved[a.id] = {**a.model_dump(), "matched_sections": evidence_sections(a.model_dump(), "营养 观察 依据")}


def nutrition_facts(ctx, p, values, observation):
    if not p:
        return {"status": "needs_info", "questions": ["请选择对应宠物，或先询问通用营养知识。"]}
    row = get_profile(ctx.session, ctx.user, p["id"])
    supplement = values.get("nutrition", {})
    data = {**(row.data if row else {}), **supplement}
    if "foods" in supplement:
        # A changed food list must not inherit confirmations for a different saved list.
        data["treats_confirmed"] = supplement.get("treats_confirmed", False)
        data["food_shares_confirmed"] = supplement.get("food_shares_confirmed", False)
    if re.search(HEALTH, observation):
        data["current_symptoms"] = observation[-2000:]
    if values.get("professional_advice"):
        data["diet_restrictions"] = "用户本会话提供专业建议，需核对完整原文及适用条件；不会自动制定或更改食量。"
    assessed = assess(ctx.session, ctx.user, p["id"], NutritionInput.model_validate(data))
    add_tool_sources(ctx, [s for s in assessed["sources"] if s["id"] in {"nutrition-energy", "nutrition-risk", "nutrition-feeding", "nutrition-label"}])
    # No preview token: this is an ephemeral evaluation, never authorization to save.
    return {k: assessed[k] for k in ("status", "calculation", "foods", "questions", "warnings", "conditions", "weight", "weight_date", "rule_version")} | {"input_parameters": data, "neutered": p["neutered"]}


def nutrition_narrative(result):
    if result.get("calculation"):
        c = result["calculation"]
        low, high = c["daily_kcal_range"]
        lines = [f"本地计算的维持热量起始范围约 **{low:.0f}—{high:.0f} kcal/日**；当前输入摄入约 {c['current_kcal']:.0f} kcal/日，其中零食 {c['current_treat_kcal']:.0f} kcal。",
            f"依据：{c['formula']}；RER {c['rer_kcal']:.1f} kcal，系数范围 {c['factor_range'][0]}—{c['factor_range'][1]}。", result["conditions"]]
        inputs = result.get("input_parameters", {})
        lines.append(f"使用的用户资料：体重 {result['weight']} kg（{result['weight_date']}），体况 {inputs.get('bcs', '未知')}/9（{inputs.get('assessed_on', '日期未知')}）；生命阶段、肌肉、活动、健康、孕哺和绝育情况均需符合上述条件。填写者：" + ("用户报告由兽医评估" if inputs.get("assessor") == "vet" else "饲养者填写，未经应用核实"))
        table = ["| 食物 | 当前每日克数 | 当前热量 | 起始参考克数范围 |", "| --- | --- | --- | --- |"]
        for food in result["foods"]:
            bounds = food.get("reference_grams_range")
            table.append(f"| {food['name'].replace('|', '／')} | {food['current_daily_grams']:.1f} g | {food['current_kcal']:.1f} kcal | " + (f"{bounds[0]:.1f}—{bounds[1]:.1f} g" if bounds else "零食计入总量") + " |")
        lines.append("\n".join(table))
        lines.append("这些是起始参考，不是必须达到的目标。先核对标签、实际摄入和体况；记录食欲、体重与耐受，再重新预览。保存目标后才改变任务。")
    else:
        lines = ["目前不能可靠给出固定食量：体重、体况、健康条件或食物能量密度及标签资料需要核对，不能仅凭品种推算。"]
    lines += result.get("warnings", [])
    if result.get("questions"):
        lines.append("优先补充：" + "；".join(result["questions"][:3]))
    return "\n\n".join(lines)


def demo_answer(p, facts, conflicts, questions, articles, health_questions, tools, depth):
    intro = (f"结合 {p['name']}（{p['age_months'] if p['age_months'] is not None else '年龄未知'} 个月）的当前资料，" if p else "根据本次明确的物种与问题，")
    if tools.get("nutrition"):
        intro += "先核对营养适用条件，再安排执行与观察。"
    elif health_questions is not None:
        intro += "先整理健康观察和就医准备；这些资料不足以确定病因，也不能用于开药或给剂量。"
    else:
        intro += "可以按下面的条件和步骤处理；品种倾向需要结合个体情况。"
    if any(re.search(r"喂食|主粮", question) for question in questions):
        intro += "喂食前核对食物的营养适用声明与当前生命阶段是否匹配，记录实际摄入；品种不能决定固定克数。"
    answer = [intro]
    if facts and depth != "brief":
        answer.append("## 已知情况\n" + "\n".join("- " + f for f in facts))
    if conflicts:
        answer.append("## 需要核对\n" + "\n".join("- " + c for c in conflicts))
    if tools.get("nutrition"):
        answer.append("## 本地营养评估\n" + nutrition_narrative(tools["nutrition"]))
    if tools.get("products"):
        product = tools["products"]
        if product.get("products"):
            answer.append("## 已提供产品的比较\n" + "\n\n".join("### " + item["name"] + "：" + item["status_label"] + "\n" + "；".join(item.get("strengths", []) + item.get("risks", []) + item.get("missing", [])) for item in product["products"]))
        else:
            answer.append("## 产品资料不足\n请提供具体配方或型号、营养适用声明、规格、热量和带日期的价格。当前可以说明选购原则，但不能据此断言某个品牌好坏。")
    if tools.get("recent_care") and any(re.search(r"近期|最近|记录|趋势|变化|复评", q) for q in questions):
        records = tools["recent_care"][:5]
        answer.append("## 当前宠物近期记录\n" + "\n".join("- " + r["occurred_at"] + " · " + r["kind"] + (f" · {r['value']} kg" if r["kind"] == "weight" else "") + " · 用户记录：" + r["note"][:1000] + "（记录ID：" + r["id"] + "）" for r in records) + "\n这些是用户记录，不是经检查确认的诊断；缺少打卡也不等于未照护。")
    if tools.get("active_plans") and any("计划" in q for q in questions):
        answer.append("## 当前执行中的计划\n" + "\n".join("- " + plan["title"] + f"（版本 {plan['revision']}，来自既有计划记录）" for plan in tools["active_plans"]))
    used = set()
    for question in questions:
        relevant = [a for a in articles if question in a.get("matched_questions", [])]
        if not relevant:
            relevant = articles[:1]
        chosen = next((a for a in relevant if a["id"] not in used), None)
        if not chosen:
            continue
        used.add(chosen["id"])
        excerpts = chosen.get("matched_sections") or evidence_sections(chosen, question)
        if depth == "brief":
            excerpts = excerpts[:1]
        elif len(questions) == 1 and depth == "detailed":
            excerpts = sections(chosen)
        answer.append("## " + chosen["title"] + "\n" + "\n\n".join("### " + s["heading"] + "\n" + s["text"] for s in excerpts) + "\n\n依据：" + chosen["id"] + "，对应章节可在下方来源查看。")
        if depth != "brief" and len(questions) == 1 and re.search(r"年龄|阶段", question) and re.search(r"喂食|饮食|主粮", question):
            feeding = next((a for a in relevant if a["id"] in {"cat-food", "dog-food"} and a["id"] not in used), None)
            if feeding:
                used.add(feeding["id"])
                answer.append("## 结合生命阶段安排喂食\n" + "\n\n".join(s["text"] for s in evidence_sections(feeding, question, 3)) + "\n\n依据：" + feeding["id"] + "，不能用年龄或品种独立推定食量。")
    if health_questions is not None:
        answer.append("## 观察与就医准备\n将开始时间、频率、进食饮水、排泄、接触物及已用药物分别记录；这样能帮助兽医了解变化，而不是靠某个表现自行判断病因。若出现呼吸困难、无法排尿、持续抽搐或误食危险物，立即联系兽医，不等待完善记录。")
        if health_questions:
            answer.append("优先补充：" + " ".join(health_questions))
    if not articles:
        answer.append("本地知识库暂未检索到足够可靠的资料。请补充具体主题；已提供的信息不会被当作未经核实的诊断或产品事实。")
    if depth != "brief" and articles:
        answer.append("## 下一步\n先执行与你当前条件匹配的步骤，记录时间、做法和反应；不要同时改变多个照护因素。补充新信息后可以继续追问，我会沿用本会话资料重新分析。计划、档案和食量不会因为本次回答自动修改。\n\n以上为本地检索和受控整理，未经兽医审核；资料未覆盖的情况会保留不确定性。")
    return "\n\n".join(answer)


async def answer_question(ctx, text, history, minutes):
    from app.agent import profile, infer_species, profile_stage, make_draft, assess_pet_products, clean_answer
    from app.breeds import AMBIGUOUS
    p = profile(ctx)
    context = conversation_context(history, ctx.supplement)
    values = context["values"]
    user_history = " ".join(m["content"] for m in history[-12:] if m["role"] == "user")
    background = " ".join(v for v in values.values() if isinstance(v, str))
    contextual = text + " " + background + (" " + user_history if len(text) < 140 else "")
    breeds = ctx.session.exec(select(Breed)).all()
    explicit = [b for b in breeds if any(term.lower() in text.lower() for term in [b.name, *b.aliases] if len(term) >= 2)]
    target = explicit[0] if len(explicit) == 1 else None
    species = (target.species if target else (p["species"] if p else infer_species(contextual)))
    demo = settings.DEMO_MODE
    mode = "demo" if demo else "live"
    cards, tools = [], {}
    ambiguous = next((word for word in AMBIGUOUS if word in text), None)
    if ambiguous and not target and not species:
        return {"answer": AMBIGUOUS[ambiguous] + "未知时仍可使用猫狗通用照护，档案不会自动改写。", "mode": "demo" if demo else "scope", "urgent": False, "sources": [], "draft": None, "cards": [{"type": "knowledge", "title": "确认品种与浏览资料", "href": "/knowledge?content_kind=breed"}]}
    if not species or not supports(species, "knowledge"):
        message = "为了检索适用资料，请告诉我想了解猫还是狗；普通知识无需建档。" if not species else "首版完整支持猫和狗。当前具体物种暂缺已收录的可靠资料，不能套用猫狗方法。请提供具体物种或学名。"
        if not species and re.search(r"营养|食量|喂多少|热量", text):
            message += "个体食量请先选择宠物，不能仅凭品种确定。还需核对带日期的体重与体况、健康限制，以及实际摄入与食品热量。"
        return {"answer": message, "mode": "demo" if demo else "scope", "urgent": False, "sources": [], "draft": None}
    if ambiguous and not target:
        cards.append({"type": "knowledge", "title": "确认品种与浏览资料", "href": "/knowledge?content_kind=breed"})
    ctx.species_scope = species
    ctx.breed_scope = target.id if target else (p.get("breed_id") if p else None)
    questions = questions_for(text if len(text) >= 25 else contextual)
    other_nutrition = bool(target and p and target.id != p.get("breed_id") and re.search(r"营养|吃多少|喂多少|几克|热量", text))
    queries = [question + " 热量 食物标签" for question in questions] if other_nutrition else questions
    articles = multi_search(ctx.session, species, queries, breed_id=ctx.breed_scope,
        life_stage=profile_stage(p) if p and (not target or target.id == p.get("breed_id")) else None,
        content_kind="food" if other_nutrition else None, personal=True)
    if other_nutrition:
        for a in articles:
            a["matched_questions"] = questions
    if target and not other_nutrition:
        a = ctx.session.get(KnowledgeArticle, target.article_id)
        if a and a.id not in {a["id"] for a in articles}:
            articles.append({**a.model_dump(), "matched_sections": evidence_sections(a.model_dump(), text), "matched_questions": questions})
        cards.append({"type": "knowledge", "title": "查看完整品种指南", "href": "/knowledge/" + target.article_id})
    ctx.retrieved.update({a["id"]: a for a in articles})
    facts, conflicts = facts_and_conflicts(p, values)
    if target and p and target.id != p.get("breed_id"):
        conflicts.append(f"这是关于{target.name}的普通知识；当前档案为{p['name']}，不会自动关联或修改，不能使用它的资料替另一只宠物确定食量。")
    health = bool(re.search(HEALTH + r"|疫苗|驱虫|健康观察|绝育", contextual))
    health_questions = missing_health_info(contextual, values) if health else None
    if health:
        emergency_article = ctx.session.get(KnowledgeArticle, "first-aid")
        if emergency_article:
            ctx.retrieved[emergency_article.id] = {**emergency_article.model_dump(), "matched_sections": evidence_sections(emergency_article.model_dump(), "就医 观察 准备")}
    nutrition = bool(re.search(r"营养|吃多少|喂多少|几克|热量|体况|调整.*饮食|调整.*喂食", text))
    if nutrition and (not target or (p and target.id == p.get("breed_id"))):
        tools["nutrition"] = nutrition_facts(ctx, p, values, contextual)
        cards.append({"type": "nutrition", "title": "核对并预览营养方案", "href": "/nutrition", "status": tools["nutrition"]["status"]})
    if re.search(r"产品比较|比较.*(粮|零食|用品)|推荐.*(粮|用品)|选粮|这.*粮.*好|什么.*粮.*好", text):
        tools["products"] = assess_pet_products(RunContext(deps=ctx, model=None, usage=None, prompt=text))
        cards.append({"type": "products", "title": "比较具体食品与用品", "href": "/products"})
    if re.search(r"找.*医院|附近.*医院|推荐.*医院|医院.*推荐", text):
        tools["hospital_status"] = "未执行地点搜索。请在医院页面定位或输入地区，不编造医院。"
        cards.append({"type": "hospitals", "title": "查找医院", "href": "/hospitals"})
    if re.search(r"就医摘要|就医资料|复诊资料|看医生.*资料", text):
        from app.visit import build_summary
        summary = build_summary(ctx.session, ctx.user, ctx.pet_id, VisitInput(observation=values.get("observations", ""))) if p else None
        tools["visit_summary"] = summary
        if summary:
            add_tool_sources(ctx, summary["sources"])
        cards.append({"type": "visit_summary", "title": "就医资料摘要", "href": "/hospitals#visit-summary", "text": summary["text"] if summary else "请先选择宠物。"})
    wants_draft = bool(re.search(r"(?:生成|制定|创建|安排|调整).*计划|计划.*(?:生成|制定|调整)", text))
    draft = make_draft(ctx, minutes).model_dump(mode="json") if wants_draft and p and not nutrition and not (target and target.id != p.get("breed_id")) else None
    if draft:
        tools["plan_draft"] = draft
    if p and (not target or target.id == p.get("breed_id")):
        tools["recent_care"] = care_history(ctx.session, ctx.user, p["id"])[:20]
        tools["active_plans"] = current_plans(ctx.session, ctx.user, p["id"])
        row = get_profile(ctx.session, ctx.user, p["id"])
        tools["saved_nutrition"] = row.data if row else None
    ctx.effective_context = context
    ctx.analysis = {"questions": questions, "facts": facts, "conflicts": conflicts, "health_questions": health_questions, "tool_results": tools}
    ctx.memory = summarize_history(history, contextual)
    depth = ctx.answer_depth if ctx.answer_depth != "auto" else ("detailed" if len(questions) > 1 or len(text) > 180 or bool(values) else "standard")
    ctx.resolved_depth = depth
    if demo:
        answer = demo_answer(p if not target or not p or target.id == p.get("breed_id") else None, facts, conflicts, questions, articles, health_questions, tools, depth)
        if ambiguous and not target:
            answer = AMBIGUOUS[ambiguous] + "未知时可使用猫狗通用照护。\n\n" + answer
        if draft:
            answer = "已生成可编辑草稿，尚未保存。请核对每项依据和时间，确认后保存。\n\n" + answer
        if tools.get("hospital_status"):
            answer = "可授权定位或输入城市、区县查询医院候选；本次未执行地图查询，能力和营业情况需核实。\n\n" + answer
        if tools.get("visit_summary"):
            answer = "已根据档案与最近30天记录整理就医摘要，可在下方展开、补充并编辑，不是诊断。\n\n" + answer
    else:
        from app.model_adapter import run_model
        result = await run_model(ctx, text, history, p, list(ctx.retrieved.values()))
        answer = clean_answer(result.answer)
        if not answer.strip():
            from fastapi import HTTPException
            raise HTTPException(502, "模型未返回完整回答，本次未完成。")
        articles = [ctx.retrieved[i] for i in result.citation_ids]
    return {"answer": answer, "mode": mode, "urgent": False, "sources": source_cards(ctx, list(ctx.retrieved.values()) if demo else articles), "draft": draft,
        "cards": cards, "answer_depth": depth, "questions": questions, "context_conflicts": conflicts,
        "context_provenance": context["provenance"], "memory_sources": ctx.memory["items"], "context_budget_notes": getattr(ctx, "context_budget_notes", []), "complete": True}
