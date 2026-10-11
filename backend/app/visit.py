from datetime import datetime, UTC
from app.models import Pet
from app.services import owned, pet_public
from app.nutrition import care_history, source_cards, get_profile
from app.knowledge import search_knowledge


def build_summary(session, user, pid, data):
    p = pet_public(session, owned(session, Pet, pid, user.id))
    logs = care_history(session, user, pid)
    sources = search_knowledge(session, p["species"], "就医 观察 记录 准备", limit=3)
    def known(value):
        return str(value) if value is not None and value != "" else "未知 / 未填写"
    lines = [f"{p['name']} · 就医资料摘要", "以下由用户档案和照护记录整理，未经医院核实，不是诊断。",
        f"生成时间：{datetime.now(UTC).isoformat()}",
        f"档案来源：用户维护；建档时间 {p['created_at']}；单项资料填写日期未单独记录。",
        f"物种：{p['species']}；品种：{known(p['breed'])}；年龄（月）：{known(p['age_months'])}",
        f"体重（kg）：{known(p['weight'])}；记录时间：{known(p['weight_date'])}",
        f"症状开始：{data.started_at.isoformat() if data.started_at else '未知 / 未填写'}（用户填写）",
        "本次观察（用户填写）：" + known(data.observation),
        "已用药信息（用户填写原意，不核定或调整剂量）：" + known(data.medicines_as_reported),
        "当前饮食（档案）：" + known(p['diet']), "过敏史（档案）：" + known(p['allergies']),
        "既往病史（档案）：" + known(p['medical_history']), "兽医建议（用户录入原意）：" + known(p['vet_advice']),
        "最近30天照护记录（按发生时间，最多100条）："]
    for row in logs:
        lines.append(f"- {row['occurred_at']} [{row['kind']}] " + (f"{row['value']} kg；" if row['kind'] == 'weight' else '') + row['note'])
    if not logs:
        lines.append("没有记录；不代表没有症状或未照护。")
    nutrition = get_profile(session, user, pid)
    if nutrition:
        lines.append(f"营养资料（用户填写，更新时间 {nutrition.updated_at}）：")
        for food in nutrition.data.get("foods", []):
            lines.append(f"- {food['name']}：报告每日摄入 {known(food.get('daily_grams'))} g；包装热量 {known(food.get('energy'))} {food['energy_unit']}。不是兽医处方。")
    from app.agent import risks
    found = risks(data.observation, p["species"])
    urgent = bool(found)
    if urgent:
        lines.insert(0, "请立即联系兽医或宠物急诊，资料整理不应延迟就医。")
        from app.models import KnowledgeArticle
        for rule in found:
            article = session.get(KnowledgeArticle, rule["article_id"])
            if article and article.id not in {a["id"] for a in sources}:
                sources.append(article.model_dump())
    return {"text": "\n".join(lines), "sources": source_cards(sources), "urgent": urgent, "mode": "local_summary"}
