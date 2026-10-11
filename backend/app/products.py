"""Deterministic product suitability and costs. Labels remain untrusted evidence."""
from fastapi import HTTPException
import math
from app.models import Pet, ProductAssessment
from app.product_schemas import AssessmentInput
from app.services import owned, pet_public, fingerprint
from app.nutrition import get_profile, kcal_per_gram
from app.care_schemas import FoodInput
from app.knowledge import search_knowledge
from app.clock import iso, utc_now

RULE_VERSION = "products-2026-10-11.1"
LABELS = {"incompatible": "不匹配", "caution": "需谨慎", "conditional": "条件下可考虑", "insufficient": "资料不足", "professional": "需专业评估"}
FOOD = {"main", "complement", "treat"}
TOPIC_QUERIES = {"main": "主粮 营养适用 配料 热量", "complement": "补充食品 营养适用", "treat": "零食 热量 训练",
    "bowls": "食盆 饮水机", "litter": "猫砂 砂盆", "carriers": "航空箱 笼箱", "beds": "窝 床垫", "scratch": "抓板 猫爬架", "toys": "玩具 啃咬", "harness": "胸背 牵引", "grooming": "梳子 洗护", "dental": "洁牙 口腔用品", "cleaning": "清洁剂 消毒"}


def numeric(value, digits=4):
    if not math.isfinite(value):
        raise HTTPException(422, "数值超出可计算范围，请核对规格、热量和用量")
    return round(value, digits)


def context_for(session, user, inputs):
    p = pet_public(session, owned(session, Pet, inputs.pet_id, user.id)) if inputs.pet_id else None
    if p and p["species"] != inputs.species:
        raise HTTPException(422, "比较物种必须与当前宠物一致")
    row = get_profile(session, user, p["id"]) if p else None
    return {"pet": p, "nutrition": row.data if row else None, "nutrition_revision": row.revision if row else 0}


def assess_products(session, user, inputs: AssessmentInput):
    context = context_for(session, user, inputs)
    p = context["pet"]
    nutrition = context["nutrition"] or {}
    category = inputs.category
    species = inputs.species
    professional = bool(p and (p.get("medical_history") or p.get("allergies") or p.get("vet_advice"))) or nutrition.get("health_status") == "unwell" or nutrition.get("pregnancy_lactation") == "yes" or bool(nutrition.get("diet_restrictions") or nutrition.get("current_symptoms")) or nutrition.get("muscle") == "loss" or (nutrition.get("bcs") is not None and nutrition["bcs"] not in (4, 5))
    stage = nutrition.get("life_stage", "unknown")
    if stage == "unknown" and p and p["age_months"] is not None:
        age = p["age_months"]
        stage = "growing" if age < 12 else "adult" if (species == "cat" or age >= 24) else "unknown"
    results = []
    for product in inputs.products:
        missing, risks, strengths = [], [], []
        incompatible = False
        if not product.target_species:
            missing.append("包装适用物种")
        elif species not in product.target_species:
            incompatible = True
            risks.append("产品声明的适用物种与所选宠物不匹配")
        else:
            strengths.append("用户确认的适用物种一致")
        energy = None
        if product.energy is not None:
            food = FoodInput(name=product.name[:100], energy=product.energy, energy_unit=product.energy_unit, portion_grams=product.portion_grams)
            energy = kcal_per_gram(food)
            if energy is not None:
                numeric(energy, 6)
            if energy is None:
                missing.append("每份克重；不能推测杯、勺或罐的重量")
        if category in FOOD:
            if p and stage == "unknown":
                missing.append("当前宠物的生命阶段，犬成长结束时间需结合个体确认")
            if product.life_stage == "unknown":
                missing.append("食品适用生命阶段")
            if category == "main":
                if product.adequacy == "complement":
                    incompatible = True
                    risks.append("补充性食品不应承担完整主粮")
                elif product.adequacy != "complete" or not product.adequacy_statement.strip():
                    missing.append("完整主粮的营养适用声明原文")
                else:
                    strengths.append("已记录完整食品声明原文；尚未由应用核实厂家")
                if stage == "growing" and product.life_stage in ("adult", "senior"):
                    incompatible = True
                    risks.append("成年维持声明不覆盖当前成长阶段")
                if stage in ("adult", "senior") and product.life_stage == "growing":
                    risks.append("只声明成长阶段，成年使用需要核对厂家与专业建议")
            else:
                risks.append("按补充食品或零食管理，不能凭喜好替代完整日粮")
            if energy is None:
                missing.append("可靠的热量及单位，无法比较热量成本")
            if not product.ingredients.strip():
                missing.append("配料原文与已有饮食限制的核对依据")
            if not product.manufacturer_evidence.strip():
                missing.append("厂家配方人员、质量控制或研究的可追溯资料")
            if product.processing == "raw":
                risks.append("生食及生食冻干有病原风险；CDC不建议猫狗喂生食及生食零食")
            if category == "main" and product.processing == "unknown":
                missing.append("加工方式，无法判断是否涉及生食风险")
            risks.extend(["保证分析保留最小、最大或典型值，不等于实测营养；本次不做精准干物质排名", "配料顺序、无谷、高蛋白宣传及价格不能单独证明质量"])
        else:
            for value, label in [(product.material, "材料标注"), (product.dimensions, "尺寸规格"), (product.cleaning_method, "清洁方法"), (product.warnings, "使用警示")]:
                if not value.strip():
                    missing.append(label)
            if product.size_confirmed is False:
                incompatible = True
                risks.append("用户确认规格与宠物或使用空间不匹配")
            elif product.size_confirmed is not True:
                missing.append("实测尺寸、承重或用途匹配确认")
            else:
                strengths.append("用户已核对尺寸或用途；不是安全认证")
            if category in ("litter", "scratch") and species != "cat":
                incompatible = True
                risks.append("本类指南仅适用于猫，不能套用于犬")
            risks.append("核对首次接受度及损坏、清洁和替换条件，具体安全警示以说明书为准")
        costs = {"currency": product.currency, "price_date": str(product.price_date) if product.price_date else None,
                 "per_100g": None, "per_100kcal": None, "daily": None, "monthly": None, "monthly_ownership": None, "basis": []}
        if product.price is not None:
            if product.price_date is None:
                missing.append("价格日期（价格可能变化）")
            if category in FOOD and product.net_grams:
                per_g = product.price / product.net_grams
                costs["per_100g"] = numeric(per_g * 100)
                if energy:
                    costs["per_100kcal"] = numeric(per_g * 100 / energy)
                if product.daily_grams is not None:
                    costs["daily"] = numeric(per_g * product.daily_grams)
                    costs["monthly"] = numeric(per_g * product.daily_grams * 30)
                    costs["basis"].append("用户确认的实际每日克数；月按30天，仅计算本产品")
                costs["basis"].append("用户提供成交价与净含量，不含运费和损耗")
            elif category in FOOD:
                missing.append("净含量，无法计算克价")
            elif product.expected_lifetime_months:
                costs["monthly_ownership"] = numeric(product.price / product.expected_lifetime_months + (product.monthly_consumables or 0))
                costs["basis"].append("按用户预计使用寿命摊销，加已填月耗材；寿命为假设")
        else:
            missing.append("实际价格，成本暂不计算")
        needs_professional = category in FOOD and (professional or product.therapeutic)
        if needs_professional:
            risks.append("已有病史、过敏、专业饮食建议或处方用途，需专业核对；应用不修改原建议")
        status = "incompatible" if incompatible else "professional" if needs_professional else "caution" if product.processing == "raw" or (stage in ("adult", "senior") and product.life_stage == "growing" and category == "main") else "insufficient" if missing else "conditional"
        results.append({"name": product.name, "status": status, "status_label": LABELS[status], "strengths": strengths, "risks": risks, "missing": list(dict.fromkeys(missing)), "costs": costs, "kcal_per_gram": round(energy, 6) if energy else None, "analysis": [a.model_dump() for a in product.analysis], "provenance": "用户核对资料，未经厂家核实", "origin": product.origin})
    queries = TOPIC_QUERIES[category] + " 预算" + (" 生食" if any(p.processing == "raw" for p in inputs.products) else "")
    docs = search_knowledge(session, species, queries, limit=5, content_kind="food" if category in FOOD else "supplies", breed_id=p.get("breed_id") if p else None, personal=True)
    sources = [{"id": a["id"], "title": a["title"], "url": a["source_url"], "organization": a["source_organization"]} for a in docs]
    return {"rule_version": RULE_VERSION, "evaluated_at": iso(utc_now()), "origin": "本地规则计算", "context": context,
        "products": results, "sources": sources, "note": "比较仅针对所填配方与规格；不同币种不自动换汇。没有质量总分或品牌排名，资料确认不等于厂家核实。",
        "preview_token": fingerprint(RULE_VERSION, {"user_id": user.id, "inputs": inputs.model_dump(mode="json"), "context": context})}


def save_assessment(session, user, data):
    result = assess_products(session, user, data.inputs)
    if data.preview_token != result["preview_token"]:
        raise HTTPException(409, "产品资料或宠物状态已变化，请重新比较后保存")
    row = ProductAssessment(user_id=user.id, pet_id=data.inputs.pet_id, inputs=data.inputs.model_dump(mode="json"), result=result, rule_version=RULE_VERSION)
    session.add(row)
    session.flush()
    return row.model_dump()
